"""CA-13: the job queue has partial indexes (schema version 12) that a migrated and a new database share, and `claim_job` reads the queue through them."""
import os
from pathlib import Path
import unittest
import uuid

from memory_platform.store import Store
from memory_platform.tests.test_migrations_additive import additive_violations, assert_contiguous_versions, catalog_snapshot

SCHEMA = Path(__file__).parents[1] / 'schema.sql'
VERSION_12 = '-- queue-indexes (schema version 12)'


def schema_before_version_12():
    """`schema.sql` as it stood at version 11: everything before the section of version 12 (the whole text when that section does not exist yet)."""
    return SCHEMA.read_text(encoding='utf-8').split(VERSION_12)[0]


class QueueDatabase(unittest.TestCase):
    """A database of its own per test: the queue holds only what the test seeds."""
    prefix = 'qix_'

    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = self.prefix + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def seed_version_11(self):
        """A database exactly as the previous release leaves it (versions 1 to 11), with a project and jobs in every state."""
        from memory_platform.agent_store import migrate_agent_schema
        from memory_platform.corpus_answers import migrate_corpus_answers
        from memory_platform.extended_store import migrate_extended_schema
        from memory_platform.store_vectors import migrate_vector_indexes
        with self.psycopg.connect(self.dsn) as c:
            c.execute(schema_before_version_12())
            migrate_vector_indexes(c)
            migrate_agent_schema(c)
            migrate_extended_schema(c)
            migrate_corpus_answers(c)
            self.assertEqual({v for (v,) in c.execute('SELECT version FROM memory.schema_versions').fetchall()}, set(range(1, 12)), 'the fixture must be version 11')
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
            for index, state in enumerate(('pending', 'running', 'succeeded', 'failed', 'unknown', 'succeeded')):
                c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,attempts,lease_until) "
                          "VALUES(%s,'p1',%s,1,repeat('a',64),'item','embed','upsert',%s,%s,%s)",
                          (f'j{index}', f'i{index}', state, index, '2001-01-01T00:00:00Z' if state == 'running' else None))


class QueueIndexMigrationTests(QueueDatabase):
    def indexes(self, c):
        return {name: definition for name, definition in c.execute("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='memory' AND tablename='jobs'").fetchall()}

    def test_a_database_at_version_11_reaches_12_with_both_indexes_and_no_row_or_column_changes(self):
        self.seed_version_11()
        with self.psycopg.connect(self.dsn) as c:
            before = catalog_snapshot(c)
            rows = c.execute('SELECT md5(string_agg(to_jsonb(j)::text, $$,$$ ORDER BY id)), count(*) FROM memory.jobs j').fetchone()
            self.assertNotIn('memory_jobs_claim', self.indexes(c))
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            after = catalog_snapshot(c)
            self.assertEqual(c.execute('SELECT md5(string_agg(to_jsonb(j)::text, $$,$$ ORDER BY id)), count(*) FROM memory.jobs j').fetchone(), rows, 'no job row changed')
            assert_contiguous_versions(self, c, 12)
            self.assertEqual(c.execute('SELECT count(*) FROM memory.schema_versions WHERE version=12').fetchone()[0], 1)
            indexes = self.indexes(c)
        self.assertEqual(additive_violations(before, after), [], 'version 12 only adds')
        self.assertEqual({k: v for k, v in after['columns'].items() if k[0] == 'jobs'}, {k: v for k, v in before['columns'].items() if k[0] == 'jobs'}, 'no column of jobs changed')
        self.assertEqual(set(after['indexes']) - set(before['indexes']), {('jobs', 'memory_jobs_claim'), ('jobs', 'memory_jobs_running_lease')})
        self.assertIn('memory_job_queue', indexes, 'the index of version 1 stays')
        claim = indexes['memory_jobs_claim']
        self.assertRegex(claim, r"\(priority, available_at, created_at, id\) WHERE")
        self.assertIn("'pending'", claim)
        self.assertIn("'unknown'", claim)
        self.assertNotIn("'running'", claim)
        self.assertRegex(indexes['memory_jobs_running_lease'], r"\(lease_until\) WHERE \(state = 'running'::text\)")

    def test_a_new_database_and_a_migrated_one_have_the_same_catalog(self):
        """Compared from the catalog (columns, indexes, constraints, functions, triggers, extensions, versions), not from the SQL text."""
        self.seed_version_11()
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            migrated = catalog_snapshot(c)
        fresh = QueueIndexMigrationTests('test_a_new_database_and_a_migrated_one_have_the_same_catalog')
        fresh.setUp()
        try:
            Store(fresh.dsn).migrate()
            with fresh.psycopg.connect(fresh.dsn) as c:
                new = catalog_snapshot(c)
        finally:
            fresh.doCleanups()
        self.assertEqual(new, migrated)
        self.assertIn(('jobs', 'memory_jobs_claim'), new['indexes'])

    def test_a_repeated_migrate_does_not_rebuild_the_queue_indexes_nor_register_again(self):
        Store(self.dsn).migrate()
        identity = lambda c: c.execute("SELECT relname,relfilenode::text,oid::text FROM pg_class WHERE relname IN ('memory_jobs_claim','memory_jobs_running_lease') ORDER BY relname").fetchall()
        with self.psycopg.connect(self.dsn) as c:
            first = identity(c)
            self.assertEqual(len(first), 2)
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(identity(c), first)
            self.assertEqual(c.execute("SELECT count(*) FROM memory.schema_versions WHERE version=12 AND applied_at < timestamptz '2002-01-01'").fetchone()[0], 1)

    def test_a_lost_index_is_rebuilt_and_the_registered_version_keeps_its_date(self):
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
            c.execute('DROP INDEX memory.memory_jobs_running_lease')
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertIn('memory_jobs_running_lease', self.indexes(c))
            self.assertEqual(c.execute("SELECT count(*) FROM memory.schema_versions WHERE version=12 AND applied_at < timestamptz '2002-01-01'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
