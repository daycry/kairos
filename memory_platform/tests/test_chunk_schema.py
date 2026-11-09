"""Additive fragment table (schema version 10): `memory.embedding_chunks`, its keys and its partial HNSW index."""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import uuid

from memory_platform.admin import content_manifest
from memory_platform.store import Store

SCHEMA = Path(__file__).parents[1] / 'schema.sql'
MARKER = '-- embedding-chunks (schema version 10)'
MODEL = 'nomic-embed-text'


def previous_schema():
    """schema.sql exactly as the previous release (FTS, version 9) left the database."""
    text = SCHEMA.read_text(encoding='utf-8')
    return text[:text.index(MARKER)] if MARKER in text else text


class ChunkSchemaTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg = psycopg
        self.name = 'chk_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.admin_dsn = make_conninfo(dsn, dbname=self.name)
        self.base_dsn = dsn
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def seed_previous_version(self):
        """A database in version 9 with a document, an item and an item-level embedding."""
        import hashlib
        from memory_platform.agent_store import migrate_agent_schema
        from memory_platform.corpus_answers import migrate_corpus_answers
        from memory_platform.extended_store import migrate_extended_schema
        from memory_platform.store_vectors import migrate_vector_indexes
        with self.psycopg.connect(self.admin_dsn) as c:
            c.execute(previous_schema())
            migrate_vector_indexes(c)  # must tolerate the missing fragment table
            migrate_agent_schema(c)
            migrate_extended_schema(c)
            migrate_corpus_answers(c)
            self.assertIsNone(c.execute("SELECT to_regclass('memory.embedding_chunks')").fetchone()[0], 'the fixture must be the previous version')
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
            content = 'Contenido de ejemplo'
            body = {'title': 'Doc', 'content': content, 'source': {'uri': 'fixture://1', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}}
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES('p1','d1',1,repeat('a',64),%s::jsonb)", (json.dumps(body),))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES('p1','d1','document',1,repeat('a',64),%s,%s)", (MODEL, [0.5] * 768))

    def test_migration_creates_the_table_without_touching_existing_data(self):
        self.seed_previous_version()
        store = Store(self.admin_dsn)
        before = content_manifest(store)['sha256']
        with self.psycopg.connect(self.admin_dsn) as c:
            vectors_before = c.execute('SELECT md5(string_agg(md5(vector::text),$$,$$ ORDER BY item_id)) FROM memory.embeddings').fetchone()[0]
        store.migrate()
        self.assertEqual(content_manifest(store)['sha256'], before)
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual({row[0] for row in c.execute('SELECT version FROM memory.schema_versions').fetchall()}, set(range(1, 11)),
                             'version 10 must follow 9 (FTS) without colliding with 5, 6, 7 and 8')
            self.assertEqual(c.execute('SELECT md5(string_agg(md5(vector::text),$$,$$ ORDER BY item_id)) FROM memory.embeddings').fetchone()[0], vectors_before)
            columns = {row[0]: row[1] for row in c.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='memory' AND table_name='embedding_chunks'").fetchall()}
            self.assertEqual(set(columns), {'project_id', 'item_id', 'resource_type', 'version', 'canonical_hash', 'model', 'ordinal', 'char_start', 'char_end', 'embedding', 'dims', 'created_at'})
            # The key of the item-level table is untouched; fragments add `ordinal` to the same identity.
            key = lambda table: [row[0] for row in c.execute(
                "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) WHERE i.indrelid=%s::regclass AND i.indisprimary ORDER BY array_position(i.indkey::int2[],a.attnum)", (table,)).fetchall()]
            self.assertEqual(key('memory.embeddings'), ['project_id', 'item_id', 'resource_type', 'version', 'model'])
            self.assertEqual(key('memory.embedding_chunks'), ['project_id', 'item_id', 'resource_type', 'version', 'model', 'ordinal'])
            self.assertEqual(c.execute("SELECT count(*) FROM memory.embedding_chunks").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT confrelid::regclass::text FROM pg_constraint WHERE conrelid='memory.embedding_chunks'::regclass AND contype='f'").fetchone()[0], 'memory.projects')

    def test_constraints_reject_inconsistent_fragments_and_dims_follow_the_vector(self):
        Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
            insert = "INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding) VALUES('p1','d1','document',1,'h',%s,%s,%s,%s,%s::vector)"
            c.execute(insert, (MODEL, 0, 0, 10, '[1,0,0]'))
            self.assertEqual(c.execute('SELECT dims FROM memory.embedding_chunks').fetchone()[0], 3)
            for params in ((MODEL, 0, 0, 10, '[1,0,0]'), (MODEL, 1, 10, 10, '[1,0,0]'), (MODEL, -1, 0, 10, '[1,0,0]'), (MODEL, 2, -1, 10, '[1,0,0]')):
                with self.assertRaises(self.psycopg.errors.Error, msg=params):
                    with c.transaction():
                        c.execute(insert, params)

    def test_hnsw_index_is_partial_to_the_configured_model_and_dimensions(self):
        with patch.dict(os.environ, {'MEMORY_VECTOR_INDEXES': 'alpha-model:3,nomic-embed-text:768'}):
            Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            definitions = [row[0] for row in c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='memory' AND tablename='embedding_chunks' AND indexname LIKE 'memory_chunk_hnsw_%'").fetchall()]
        self.assertEqual(len(definitions), 2, definitions)
        joined = '\n'.join(definitions)
        for model, dims in (('alpha-model', 3), (MODEL, 768)):
            self.assertRegex(joined, re.escape(f"model = '{model}'") + r'.*' + re.escape(f'dims = {dims}'))
        self.assertTrue(all('USING hnsw' in d and 'vector_cosine_ops' in d and 'WHERE' in d for d in definitions), definitions)
        self.assertNotIn('other-model', joined)

    def test_repeated_migrate_creates_nothing_and_rewrites_nothing(self):
        store = Store(self.admin_dsn)
        store.migrate()
        identity = lambda c: sorted(c.execute("SELECT relname,relfilenode::text,oid::text FROM pg_class WHERE relnamespace='memory'::regnamespace AND relname LIKE '%chunk%'").fetchall())
        with self.psycopg.connect(self.admin_dsn) as c:
            first = identity(c)
        self.assertGreaterEqual(len(first), 3, first)  # table, primary key, HNSW index
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual(identity(c), first)
            self.assertEqual(c.execute('SELECT count(*) FROM memory.schema_versions WHERE version=10').fetchone()[0], 1)

    def test_repeated_new_section_takes_no_lock_on_the_embedding_tables(self):
        Store(self.admin_dsn).migrate()
        section = SCHEMA.read_text(encoding='utf-8')
        section = section[section.index(MARKER):]
        holder = self.psycopg.connect(self.admin_dsn)
        self.addCleanup(holder.close)
        holder.execute('LOCK TABLE memory.embeddings, memory.embedding_chunks, memory.projects IN ACCESS SHARE MODE')
        with self.psycopg.connect(self.admin_dsn) as runner:
            runner.execute("SET lock_timeout='1500ms'")  # any stronger request would abort here
            runner.execute(section)

    def test_the_new_schema_section_is_additive_only(self):
        text = SCHEMA.read_text(encoding='utf-8')
        self.assertIn(MARKER, text)
        self.assertNotRegex(text[text.index(MARKER):], re.compile(r'\b(DROP|TRUNCATE|DELETE)\b|ALTER\s+.*\s+TYPE', re.I))


    def test_the_queue_priority_and_the_chunked_flag_are_additive_columns_with_a_cheap_probe(self):
        """Gaps 1 and 2: `jobs.priority` (live writes first) and `embeddings.chunked` (the item-vector route only when something needs it)."""
        self.seed_previous_version()
        Store(self.admin_dsn, embedding_enabled=True).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            columns = dict(((t, n), (d, nullable)) for t, n, d, nullable in c.execute(
                "SELECT table_name,column_name,column_default,is_nullable FROM information_schema.columns WHERE table_schema='memory' AND column_name IN ('priority','chunked')").fetchall())
            self.assertEqual(columns[('jobs', 'priority')], ('0', 'NO'))
            self.assertEqual(columns[('embeddings', 'chunked')], ('false', 'NO'))
            self.assertEqual(c.execute("SELECT count(*) FROM memory.embeddings WHERE chunked").fetchone()[0], 0)  # rows of the previous release: not chunked
            index = c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='memory' AND indexname='memory_embeddings_unchunked'").fetchone()[0]
            self.assertIn('WHERE (NOT chunked)', index)
        Store(self.admin_dsn, embedding_enabled=True).migrate()  # idempotent


if __name__ == '__main__':
    unittest.main()
