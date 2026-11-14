"""The portal e2e fixture (`Dockerfile.e2e` -> `e2e_portal.py`) seeds against an isolated PostgreSQL, so CI notices when it breaks."""
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from memory_platform.tests import e2e_fixture
from memory_platform.tests.test_store import create_core


class E2EFixtureSeedTests(unittest.TestCase):
    def test_start_seeds_the_synthetic_failed_job_with_extraction_off_by_default(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        shared, _, _ = create_core()  # only to read MEMORY_TEST_DSN (skips without an isolated PostgreSQL)
        # The fixture bootstraps the first admin, so it needs an empty database of its own, never the shared test one.
        name = 'e2e_fixture_' + uuid.uuid4().hex[:12]
        with psycopg.connect(shared.dsn, autocommit=True) as admin_connection:
            admin_connection.execute('CREATE DATABASE ' + name)
        self.addCleanup(self.drop_database, shared.dsn, name)
        web = tempfile.TemporaryDirectory()
        self.addCleanup(web.cleanup)
        with patch.dict(os.environ, {'KAIROS_E2E_WEB_ROOT': web.name}):
            store, _, server = e2e_fixture.start(make_conninfo(shared.dsn, dbname=name))
        self.addCleanup(server.fixture_corpus_patch.stop)
        self.addCleanup(setattr, server, 'should_exit', True)
        with store.transaction() as c:
            jobs = c.execute("SELECT project_id FROM memory.jobs WHERE destination='extract' AND state='failed' AND error_code='synthetic_unavailable'").fetchall()
        self.assertEqual([row['project_id'] for row in jobs], ['project-a'])
        self.assertIs(store.extraction_enabled, False)  # seeded, then back to the default: the running portal does not extract

    @staticmethod
    def drop_database(dsn, name):
        import psycopg
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute('DROP DATABASE IF EXISTS ' + name + ' WITH (FORCE)')


if __name__ == '__main__':
    unittest.main()
