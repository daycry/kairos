"""Additive FTS migration (schema version 9): unaccent + pg_trgm, Spanish/English vectors and their indexes."""
import json
import os
from pathlib import Path
import unittest
import uuid

from memory_platform.admin import content_manifest
from memory_platform.store import Store

SCHEMA = Path(__file__).parents[1] / 'schema.sql'
MARKER = '-- fts-language (schema version 9)'
CONTENT = 'La configuración de las canciones se guarda en el servidor.'


def previous_schema():
    """schema.sql exactly as the previous release (pgvector, version 8) left the database."""
    text = SCHEMA.read_text(encoding='utf-8')
    return text[:text.index(MARKER)] if MARKER in text else text


class FtsMigrationTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg = psycopg
        self.name = 'fts_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.admin_dsn = make_conninfo(dsn, dbname=self.name)
        self.base_dsn = dsn
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def seed_previous_version(self):
        """A database in version 8 with rows whose text needs unaccent and stemming."""
        from memory_platform.agent_store import migrate_agent_schema
        from memory_platform.corpus_answers import migrate_corpus_answers
        from memory_platform.extended_store import migrate_extended_schema
        from memory_platform.store_vectors import migrate_vector_indexes
        import hashlib
        with self.psycopg.connect(self.admin_dsn) as c:
            c.execute(previous_schema())
            migrate_vector_indexes(c)
            migrate_agent_schema(c)
            migrate_extended_schema(c)
            migrate_corpus_answers(c)
            self.assertIsNone(c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='memory' AND table_name='documents' AND column_name='search_vector_es'").fetchone(), 'the fixture must be the previous version')
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
            for number, title in enumerate(('Configuración de canciones', 'Deployment failed after rollout', 'Nota sin relación'), 1):
                body = {'title': title, 'content': CONTENT, 'tags': ['fixture'], 'source': {'uri': f'fixture://{number}', 'sha256': hashlib.sha256(CONTENT.encode('utf-8')).hexdigest()}}
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES('p1',%s,1,repeat('a',64),%s::jsonb)", (f'd{number}', json.dumps(body)))
                payload = {'title': title, 'content': CONTENT, 'category': 'note'}
                c.execute("""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector)
                             VALUES('p1',%s,1,repeat('b',64),'learning',%s::jsonb,'s','a',clock_timestamp(),
                             setweight(to_tsvector('simple',%s),'A') || setweight(to_tsvector('simple',%s),'B'))""", (f'i{number}', json.dumps(payload), title, CONTENT))

    def test_migration_adds_language_columns_without_touching_content(self):
        self.seed_previous_version()
        store = Store(self.admin_dsn)
        before = content_manifest(store)['sha256']
        store.migrate()
        self.assertEqual(content_manifest(store)['sha256'], before)
        with self.psycopg.connect(self.admin_dsn) as c:
            for extension in ('unaccent', 'pg_trgm'):
                self.assertEqual(c.execute('SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname=%s', (extension,)).fetchone()[0], 'public')
            self.assertEqual({row[0] for row in c.execute('SELECT version FROM memory.schema_versions').fetchall()}, set(range(1, 10)),
                             'version 9 must follow 8 (pgvector) without colliding with 5, 6 and 7')
            for table in ('documents', 'memory_items'):
                for column in ('search_vector_es', 'search_vector_en'):
                    self.assertEqual(c.execute(f'SELECT count(*) FROM memory.{table} WHERE {column} IS NULL').fetchone()[0], 0, (table, column))
                self.assertEqual(c.execute(f'SELECT count(*) FROM memory.{table}').fetchone()[0], 3)
            # The `simple` vectors stay in place and answer as before.
            self.assertEqual(c.execute("SELECT count(*) FROM memory.memory_items WHERE search_vector @@ plainto_tsquery('simple','configuración')").fetchone()[0], 3)
            self.assertEqual(c.execute("SELECT count(*) FROM memory.documents WHERE search_vector @@ plainto_tsquery('simple','configuración')").fetchone()[0], 3)
            # The new vectors answer without accents and with another inflection.
            for table in ('documents', 'memory_items'):
                self.assertEqual(c.execute(f"SELECT count(*) FROM memory.{table} WHERE search_vector_es @@ plainto_tsquery('spanish',memory.kairos_unaccent('configuracion cancion'))").fetchone()[0], 3, table)
                self.assertEqual(c.execute(f"SELECT count(*) FROM memory.{table} WHERE search_vector_en @@ plainto_tsquery('english',memory.kairos_unaccent('deploying fails'))").fetchone()[0], 1, table)

    def test_unaccent_wrapper_is_immutable_and_documents_columns_are_generated(self):
        self.seed_previous_version()
        Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual(c.execute("SELECT provolatile FROM pg_proc WHERE oid='memory.kairos_unaccent(text)'::regprocedure").fetchone()[0], 'i')
            self.assertEqual(c.execute("SELECT memory.kairos_unaccent('Canción ÁÉÍÓÚ ñ')").fetchone()[0], 'Cancion AEIOU n')
            generated = c.execute("SELECT attname,attgenerated FROM pg_attribute WHERE attrelid='memory.documents'::regclass AND attname LIKE 'search_vector_%' ORDER BY 1").fetchall()
            self.assertEqual([tuple(row) for row in generated], [('search_vector_en', 's'), ('search_vector_es', 's')])

    def test_indexes_for_language_vectors_and_trigram_exist(self):
        self.seed_previous_version()
        Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            definitions = ' '.join(row[0] for row in c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='memory' AND tablename IN ('documents','memory_items')").fetchall())
        for column in ('search_vector_es', 'search_vector_en'):
            self.assertEqual(definitions.count(f'USING gin ({column})'), 2, column)
        self.assertEqual(definitions.count('gin_trgm_ops'), 2)

    def test_items_written_without_the_new_columns_are_completed_by_the_database(self):
        """What the previous release does after a rollback: it only knows `search_vector`."""
        self.seed_previous_version()
        Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            payload = json.dumps({'title': 'Rollback sin tilde', 'content': 'Las canciones siguen buscables'})
            c.execute("""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector)
                         VALUES('p1','late',1,repeat('c',64),'learning',%s::jsonb,'s','a',clock_timestamp(),to_tsvector('simple','Rollback'))""", (payload,))
            self.assertEqual(c.execute("SELECT count(*) FROM memory.memory_items WHERE id='late' AND search_vector_es @@ plainto_tsquery('spanish',memory.kairos_unaccent('cancion'))").fetchone()[0], 1)
            c.execute("UPDATE memory.memory_items SET payload=%s::jsonb,search_vector=to_tsvector('simple','x') WHERE id='late'", (json.dumps({'title': 'Otra cosa', 'content': 'Llaves nuevas'}),))
            self.assertEqual(c.execute("SELECT count(*) FROM memory.memory_items WHERE id='late' AND search_vector_es @@ plainto_tsquery('spanish',memory.kairos_unaccent('llave'))").fetchone()[0], 1,
                             'a replaced search_vector must refresh the language vectors')

    def storage_identity(self, c):
        files = dict(c.execute("SELECT relname,relfilenode::text FROM pg_class WHERE relnamespace='memory'::regnamespace AND (relname IN ('documents','memory_items') OR relname LIKE '%search%' OR relname LIKE '%trgm%')").fetchall())
        rows = c.execute("SELECT array_agg(xmin::text ORDER BY id) FROM memory.memory_items").fetchone()[0], c.execute("SELECT array_agg(xmin::text ORDER BY id) FROM memory.documents").fetchone()[0]
        return files, rows

    def test_repeated_migrate_neither_rewrites_tables_nor_rebuilds_indexes(self):
        self.seed_previous_version()
        store = Store(self.admin_dsn)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            first = self.storage_identity(c)
        self.assertGreaterEqual(len(first[0]), 8, first)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual(self.storage_identity(c), first)

    def test_repeated_new_section_takes_no_exclusive_lock_on_the_content_tables(self):
        """Earlier versions (`ADD COLUMN IF NOT EXISTS` of 2 and 3) still lock briefly; the new section must not."""
        self.seed_previous_version()
        store = Store(self.admin_dsn)
        store.migrate()
        section = SCHEMA.read_text(encoding='utf-8')
        section = section[section.index(MARKER):]
        reader = self.psycopg.connect(self.admin_dsn)
        self.addCleanup(reader.close)
        reader.execute('LOCK TABLE memory.documents, memory.memory_items IN ACCESS SHARE MODE')
        with self.psycopg.connect(self.admin_dsn) as writer:
            writer.execute("SET lock_timeout='1500ms'")  # an ACCESS EXCLUSIVE request would abort here
            writer.execute(section)

    def test_the_new_schema_section_is_additive_only(self):
        import re
        text = SCHEMA.read_text(encoding='utf-8')
        self.assertIn(MARKER, text)
        self.assertNotRegex(text[text.index(MARKER):], re.compile(r'\b(DROP|TRUNCATE|DELETE)\b|ALTER\s+.*\s+TYPE', re.I))


if __name__ == '__main__':
    unittest.main()
