"""Additive pgvector migration (schema version 8) over a database in the previous version."""
import hashlib
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

from memory_platform.admin import content_manifest
from memory_platform.store import Store

SCHEMA = Path(__file__).parents[1] / 'schema.sql'
MODEL = 'nomic-embed-text'


def previous_schema():
    """schema.sql up to and including the last version before pgvector (5)."""
    text = SCHEMA.read_text(encoding='utf-8')
    marker = 'INSERT INTO memory.schema_versions(version) VALUES (5) ON CONFLICT DO NOTHING;'
    return text[:text.index(marker) + len(marker)]


def unit(seed, size):
    return [((seed * 31 + index * 17) % 97 + 1) / 97.0 for index in range(size)]


class PgvectorMigrationTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg = psycopg
        self.name = 'pgv_' + uuid.uuid4().hex[:12]
        self.roles = []
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.admin_dsn = make_conninfo(dsn, dbname=self.name)
        self.base_dsn = dsn
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')
            for role in self.roles:
                admin.execute(f'DROP ROLE IF EXISTS {role}')

    def seed_previous_version(self, dsn):
        """A database exactly as the previous release left it, with 2 and 768 dimension embeddings."""
        content = 'Synthetic pgvector migration fixture'
        body = {'title': 'Fixture', 'content': content, 'tags': ['fixture'], 'source': {'uri': 'fixture://pgvector', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}}
        import json
        from memory_platform.agent_store import migrate_agent_schema
        from memory_platform.corpus_answers import migrate_corpus_answers
        from memory_platform.extended_store import migrate_extended_schema
        with self.psycopg.connect(dsn) as c:
            c.execute(previous_schema())
            # The previous release also registered versions 5, 6 and 7 through these domain migrations.
            migrate_agent_schema(c)
            migrate_extended_schema(c)
            migrate_corpus_answers(c)
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','Project 1')")
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES('p1','d1',1,repeat('a',64),%s::jsonb)", (json.dumps(body),))
            for number in range(1, 4):
                c.execute('INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,%s,1,repeat(%s,64),%s,%s)',
                          ('p1', f'two-{number}', 'document', 'b', 'other-model', unit(number, 2)))
                c.execute('INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,%s,1,repeat(%s,64),%s,%s)',
                          ('p1', f'big-{number}', 'document', 'c', MODEL, unit(number, 768)))

    def vector_hashes(self, dsn):
        with self.psycopg.connect(dsn) as c:
            return dict(c.execute("SELECT item_id||'/'||model,md5(vector::text) FROM memory.embeddings ORDER BY 1").fetchall())

    def test_migration_adds_vector_columns_and_keeps_every_existing_value(self):
        self.seed_previous_version(self.admin_dsn)
        store = Store(self.admin_dsn)
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual({row[0] for row in c.execute('SELECT version FROM memory.schema_versions').fetchall()}, set(range(1, 8)))
        before_hashes = self.vector_hashes(self.admin_dsn)
        before_manifest = content_manifest(store)['sha256']
        self.assertEqual(len(before_hashes), 6)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            version = c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            self.assertIsNotNone(version, 'extension vector must exist after migrate')
            self.assertEqual(c.execute("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname='vector'").fetchone()[0], 'public')
            self.assertGreaterEqual(tuple(int(v) for v in version[0].split('.')[:3]), (0, 8, 0))
            rows = c.execute('SELECT item_id,dims,array_length(vector,1),embedding IS NOT NULL,vector_dims(embedding) FROM memory.embeddings').fetchall()
            self.assertEqual(len(rows), 6)
            self.assertEqual({row[1] for row in rows}, {2, 768})
            for _, dims, length, filled, embedded in rows:
                self.assertEqual((dims, filled, embedded), (length, True, length))
            versions = {row[0] for row in c.execute('SELECT version FROM memory.schema_versions').fetchall()}
            self.assertEqual(versions, set(range(1, 12)), 'versions 1..11 exactly: the new version must not collide with the 6 and 7 of the domain migrations')
            indexes = [row[0] for row in c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='memory' AND tablename='embeddings'").fetchall()]
            self.assertTrue(any('USING hnsw' in definition and 'vector_cosine_ops' in definition and MODEL in definition and 'dims = 768' in definition for definition in indexes), indexes)
        self.assertEqual(self.vector_hashes(self.admin_dsn), before_hashes)
        self.assertEqual(content_manifest(store)['sha256'], before_manifest)
        store.migrate()  # idempotent
        self.assertEqual(self.vector_hashes(self.admin_dsn), before_hashes)

    def test_rows_written_without_the_new_column_are_completed_by_the_database(self):
        self.seed_previous_version(self.admin_dsn)
        Store(self.admin_dsn).migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            # What a previous release does after a rollback: insert and replace only `vector`.
            c.execute('INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,%s,1,repeat(%s,64),%s,%s)',
                      ('p1', 'late', 'document', 'd', MODEL, unit(9, 768)))
            self.assertEqual(c.execute("SELECT vector_dims(embedding) FROM memory.embeddings WHERE item_id='late'").fetchone()[0], 768)
            c.execute("UPDATE memory.embeddings SET vector=%s WHERE item_id='late'", (unit(10, 768),))
            same = c.execute("SELECT embedding=%s::vector FROM memory.embeddings WHERE item_id='late'", (unit(10, 768),)).fetchone()[0]
            self.assertTrue(same, 'embedding must follow a replaced vector')

    def test_missing_extension_privilege_fails_before_any_change(self):
        role = 'pgv_role_' + uuid.uuid4().hex[:8]
        self.roles.append(role)
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'CREATE ROLE {role} LOGIN NOSUPERUSER')
            admin.execute(f'ALTER DATABASE {self.name} OWNER TO {role}')
        from psycopg.conninfo import make_conninfo
        limited = make_conninfo(self.admin_dsn, user=role)
        self.seed_previous_version(limited)
        store = Store(limited)
        before = self.vector_hashes(limited)
        with self.assertRaises(self.psycopg.Error):
            store.migrate()
        with self.psycopg.connect(limited) as c:
            columns = {row[0] for row in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='memory' AND table_name='embeddings'").fetchall()}
            self.assertNotIn('embedding', columns)
            self.assertNotIn('dims', columns)
            self.assertIsNone(c.execute('SELECT 1 FROM memory.schema_versions WHERE version=8').fetchone())
        self.assertEqual(self.vector_hashes(limited), before)

    def test_new_schema_text_is_additive_only(self):
        import re
        text = SCHEMA.read_text(encoding='utf-8')
        section = text[text.index('VALUES (5) ON CONFLICT DO NOTHING;'):]
        self.assertNotRegex(section, re.compile(r'\b(DROP|TRUNCATE|DELETE)\b|ALTER\s+.*\s+TYPE', re.I))

    def test_vector_index_setting_is_parsed_strictly(self):
        from memory_platform.config import vector_indexes
        self.assertEqual(vector_indexes({}), (('nomic-embed-text', 768),))
        self.assertEqual(vector_indexes({'MEMORY_VECTOR_INDEXES': 'a:b:384, other:1024'}), (('a:b', 384), ('other', 1024)))
        self.assertEqual(vector_indexes({'MEMORY_VECTOR_INDEXES': ''}), ())
        for bad in ('nomic', 'nomic:0', 'nomic:2001', 'nomic:x', ':768', 'nomic:768,nomic:768'):
            with self.assertRaises(ValueError):
                vector_indexes({'MEMORY_VECTOR_INDEXES': bad})

    def storage_identity(self, c):
        """relfilenode and row versions change when a table or index is rewritten or rebuilt."""
        files = dict(c.execute("SELECT relname,relfilenode::text FROM pg_class WHERE relnamespace='memory'::regnamespace AND relname='embeddings' OR relname LIKE 'memory_embedding_hnsw_%'").fetchall())
        rows = c.execute('SELECT array_agg(xmin::text ORDER BY item_id) FROM memory.embeddings').fetchone()[0]
        return files, rows

    def test_repeated_migrate_neither_rewrites_the_table_nor_rebuilds_the_index(self):
        self.seed_previous_version(self.admin_dsn)
        store = Store(self.admin_dsn)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            first = self.storage_identity(c)
        self.assertEqual(len(first[0]), 2, first)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            self.assertEqual(self.storage_identity(c), first)

    def test_new_index_is_built_once_on_a_migrated_database(self):
        self.seed_previous_version(self.admin_dsn)
        store = Store(self.admin_dsn)
        store.migrate()
        with self.psycopg.connect(self.admin_dsn) as c:
            before = self.storage_identity(c)
        with patch.dict(os.environ, {'MEMORY_VECTOR_INDEXES': 'nomic-embed-text:768,second-model:512'}):
            store.migrate()
            with self.psycopg.connect(self.admin_dsn) as c:
                after = self.storage_identity(c)
                self.assertEqual(len(after[0]), 3)
                self.assertEqual({k: v for k, v in after[0].items() if k in before[0]}, before[0], 'existing table and index untouched')
                self.assertEqual(after[1], before[1])
            store.migrate()
            with self.psycopg.connect(self.admin_dsn) as c:
                self.assertEqual(self.storage_identity(c), after)

    def test_migration_sets_a_configurable_maintenance_memory_and_builds_serially(self):
        from contextlib import contextmanager
        self.seed_previous_version(self.admin_dsn)
        store = Store(self.admin_dsn)
        statements = []
        original = store.transaction

        @contextmanager
        def spied():
            with original() as connection:
                class Spy:
                    def execute(_, query, params=None, **kw):
                        statements.append((str(query), params))
                        return connection.execute(query, params, **kw)

                    def __getattr__(_, name):
                        return getattr(connection, name)
                yield Spy()
        with patch.object(store, 'transaction', spied):
            store.migrate()
            with patch.dict(os.environ, {'MEMORY_MIGRATION_MAINTENANCE_WORK_MEM': '64MB'}):
                store.migrate()
        settings = [params for query, params in statements if 'maintenance_work_mem' in query]
        self.assertEqual(settings, [('256MB',), ('64MB',)])
        self.assertTrue(all('max_parallel_maintenance_workers' in query for query, params in statements if 'maintenance_work_mem' in query))

    def test_maintenance_memory_setting_is_validated(self):
        from memory_platform.config import migration_maintenance_work_mem
        self.assertEqual(migration_maintenance_work_mem({}), '256MB')
        self.assertEqual(migration_maintenance_work_mem({'MEMORY_MIGRATION_MAINTENANCE_WORK_MEM': '1GB'}), '1GB')
        for bad in ('', '0MB', 'lots', '256', '1MB; DROP', '-1MB'):
            with self.assertRaises(ValueError):
                migration_maintenance_work_mem({'MEMORY_MIGRATION_MAINTENANCE_WORK_MEM': bad})

    def test_repeated_migrate_takes_no_exclusive_lock_on_embeddings(self):
        """A reader (ACCESS SHARE) on memory.embeddings must not block a repeated migrate (lock_timeout is 5 s)."""
        import time
        self.seed_previous_version(self.admin_dsn)
        store = Store(self.admin_dsn)
        store.migrate()
        reader = self.psycopg.connect(self.admin_dsn)
        self.addCleanup(reader.close)
        reader.execute('LOCK TABLE memory.embeddings IN ACCESS SHARE MODE')
        started = time.monotonic()
        store.migrate()
        self.assertLess(time.monotonic() - started, 4)
