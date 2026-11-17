"""T-68 (CA-33): the project `kairos-probe` and the key that reaches nothing else.

Every test has its OWN database (created and dropped here, on the isolated PostgreSQL of the test target): `kairos-probe` is a fixed name, and the shared test database must never receive it.
`ClientApi`, `IsolatedDatabase` and `settings_for` are the helpers of `test_probe.py` too.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient

from memory_platform import admin, probe
from memory_platform.app import create_app
from memory_platform.auth import Auth, hash_password
from memory_platform.config import Settings
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings

ORIGIN = 'http://localhost:8790'
ROOT = Path(__file__).resolve().parents[3]
USER_PROJECT = 'user-notes'


def settings_for():
    return Settings('unused', allowed_origins=[ORIGIN], lease_seconds=60, request_timeout=30.0, embedding_query_timeout=30.0, mount_mcp=False)


class IsolatedDatabase:
    """Mixin: `self.make_store()` is a migrated database of its own (with an administrator unless `admin=False`), dropped at the end of the test."""

    def make_store(self, admin=True):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        name = 'pr_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(f'CREATE DATABASE {name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        self.addCleanup(drop)
        store = Store(make_conninfo(dsn, dbname=name), embedding_enabled=True)
        store.migrate()
        self.actor = None
        if admin:
            with store.transaction() as c:
                aid = str(uuid.uuid4())
                c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (aid, 'op-' + aid[:8], hash_password('fixture-password-123')))
            self.actor = {'id': aid, 'credential_type': 'bootstrap'}
        return store

    def make_app(self, store):
        settings = settings_for()
        return create_app(settings, store=store, auth=Auth(store, [ORIGIN]), retrieval=Retrieval(store, settings, FakeEmbeddings(settings)))


class ClientApi:
    """The `api` of `probe.Probe` over a test client of the server application, with a bearer token."""

    def __init__(self, client, token):
        self.client, self.headers = client, {'Authorization': 'Bearer ' + token}
        self.requests = []

    def call(self, method, path, body=None, timeout=None):
        response = self.client.request(method, path, json=body, headers=self.headers)
        self.requests.append((method, path, response.status_code))
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data if isinstance(data, dict) else None


def user_event(project, **changes):
    event = {'event_id': str(uuid.uuid4()), 'project_id': project, 'session_id': 's', 'agent_id': 'a', 'event_type': 'note', 'occurred_at': '2026-11-17T10:00:00Z', 'item_id': str(uuid.uuid4()),
             'version': 1, 'generate': False, 'payload': {'title': 'User note', 'content': 'A note of a user project', 'source': {'uri': 'fixture://user'}}}
    event.update(changes)
    return event


class ProvisioningTests(IsolatedDatabase, unittest.TestCase):
    def setUp(self):
        self.store = self.make_store()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.key_file = Path(directory.name) / 'probe' / 'kairos-probe.key'
        self.store.create_project(self.actor, {'id': USER_PROJECT, 'title': 'A user project'})
        self.store.set_policy(self.actor, USER_PROJECT, {'capture_mode': 'summary', 'temporal_projection': False})

    def provision(self):
        return probe.provision(self.store, self.key_file)

    def rows(self, sql, *parameters):
        with self.store.transaction() as c:
            return c.execute(sql, parameters).fetchall()

    def user_state(self):
        """Everything the database holds about the user project, and the audit rows that name it."""
        tables = ('memory_items', 'documents', 'events', 'jobs', 'sessions', 'project_grants', 'item_versions', 'document_versions')
        state = {table: self.rows(f'SELECT count(*) AS n FROM memory.{table} WHERE project_id=%s', USER_PROJECT)[0]['n'] for table in tables}
        state['audit'] = self.rows('SELECT action FROM memory.audit_events WHERE project_id=%s ORDER BY id', USER_PROJECT)
        state['policy'] = self.rows('SELECT policy,title FROM memory.projects WHERE id=%s', USER_PROJECT)
        return state

    def test_it_makes_the_project_and_a_key_with_read_and_write_on_it_alone(self):
        report = self.provision()
        self.assertEqual((report['status'], report['project'], report['key']), ('provisioned', 'created', 'created'))
        self.assertEqual(self.rows('SELECT policy FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['policy'], probe.PROBE_POLICY)
        keys = self.rows('SELECT id,name,project_ids,scopes,revoked_at FROM memory.api_keys WHERE name=%s', probe.PROBE_KEY_NAME)
        self.assertEqual([(k['project_ids'], sorted(k['scopes']), k['revoked_at']) for k in keys], [([probe.PROBE_PROJECT], ['read', 'write'], None)])
        self.assertEqual(report['key_id'], keys[0]['id'])
        self.assertEqual(self.key_file.read_text(encoding='utf-8').strip().startswith('mp_'), True)
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(self.key_file.stat().st_mode), 0o600)

    def test_the_key_is_refused_everywhere_but_its_project_a_write_elsewhere_is_not_even_found(self):
        """CA-33. Outside its project a key is answered 404 (`NotFound`: `store_auth._require` does not reveal that the project exists, so an out-of-scope write is no 403);
        inside it, what the key lacks (publish, admin) is 403. Nothing reaches the user project."""
        self.provision()
        token = self.key_file.read_text(encoding='utf-8').strip()
        before = self.user_state()
        with TestClient(self.make_app(self.store), base_url=ORIGIN, raise_server_exceptions=False) as client:
            api = ClientApi(client, token)
            statuses = {
                'write elsewhere': api.call('POST', '/v1/events', user_event(USER_PROJECT))[0],
                'read elsewhere': api.call('GET', '/v1/projects/%s/policy' % USER_PROJECT)[0],
                'search elsewhere': api.call('POST', '/v1/search', {'project_ids': [USER_PROJECT], 'q': 'note', 'semantic': False})[0],
                'write in its own project': api.call('POST', '/v1/events', user_event(probe.PROBE_PROJECT))[0],
                'publish a document': api.call('POST', '/v1/projects/%s/documents' % probe.PROBE_PROJECT,
                                               {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 't', 'content': 'c', 'source': {'uri': 'fixture://x', 'sha256': hashlib.sha256(b'c').hexdigest()},
                                                'validation': {'status': 'validated', 'validated_by': 'x', 'evidence': ['e']}})[0],
                'create a project': api.call('POST', '/v1/projects', {'id': 'other-project', 'title': 'x'})[0],
                'create a key': api.call('POST', '/v1/keys', {'name': 'wider', 'project_ids': [probe.PROBE_PROJECT], 'scopes': ['admin']})[0],
                'create a key elsewhere': api.call('POST', '/v1/keys', {'name': 'wider', 'project_ids': [USER_PROJECT], 'scopes': ['read']})[0],
            }
        self.assertEqual(statuses, {'write elsewhere': 404, 'read elsewhere': 404, 'search elsewhere': 404, 'write in its own project': 202, 'publish a document': 403,
                                    'create a project': 403, 'create a key': 403, 'create a key elsewhere': 404})
        self.assertEqual(self.user_state(), before)
        self.assertEqual(self.rows("SELECT count(*) AS n FROM memory.projects WHERE id='other-project'")[0]['n'], 0)

    def test_a_second_run_changes_nothing_and_no_run_writes_in_a_user_project(self):
        before = self.user_state()
        first = self.provision()
        token = self.key_file.read_bytes()
        keys = self.rows('SELECT id FROM memory.api_keys ORDER BY id')
        audit = self.rows('SELECT count(*) AS n FROM memory.audit_events')[0]['n']
        second = self.provision()
        self.assertEqual((second['project'], second['key'], second['key_id']), ('present', 'reused', first['key_id']))
        self.assertEqual(self.key_file.read_bytes(), token)
        self.assertEqual(self.rows('SELECT id FROM memory.api_keys ORDER BY id'), keys)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.audit_events')[0]['n'], audit)  # not even an audit row: nothing was written
        self.assertEqual(self.user_state(), before)

    def test_a_key_file_the_database_does_not_accept_is_replaced_and_the_older_probe_key_revoked(self):
        first = self.provision()
        self.key_file.write_text('mp_' + 'x' * 64 + '\n', encoding='utf-8')
        second = self.provision()
        self.assertEqual(second['key'], 'created')
        self.assertNotEqual(second['key_id'], first['key_id'])
        active = self.rows('SELECT id FROM memory.api_keys WHERE name=%s AND revoked_at IS NULL', probe.PROBE_KEY_NAME)
        self.assertEqual([row['id'] for row in active], [second['key_id']])

    def test_a_key_with_a_wider_reach_is_never_reused_and_is_not_ours_to_revoke(self):
        self.provision()
        self.store.create_project(self.actor, {'id': 'second-project', 'title': 'x'})
        wider = self.store.create_key(self.actor, {'name': 'someone-else', 'project_ids': [probe.PROBE_PROJECT, 'second-project'], 'scopes': ['read', 'write']})
        self.key_file.write_text(wider['token'] + '\n', encoding='utf-8')
        report = self.provision()
        self.assertEqual(report['key'], 'created')
        self.assertNotEqual(self.key_file.read_text(encoding='utf-8').strip(), wider['token'])
        self.assertEqual(self.rows('SELECT revoked_at FROM memory.api_keys WHERE id=%s', wider['id'])[0]['revoked_at'], None)
        broad_scope = self.store.create_key(self.actor, {'name': 'kairos-probe', 'project_ids': [probe.PROBE_PROJECT], 'scopes': ['read', 'write', 'admin']})
        self.key_file.write_text(broad_scope['token'] + '\n', encoding='utf-8')
        self.assertEqual(self.provision()['key'], 'created')  # same project, wider scope: not reused

    def test_a_key_file_that_cannot_be_written_leaves_no_active_key(self):
        with patch('memory_platform.probe.write_atomic', side_effect=OSError('disk full')), self.assertRaises(OSError):
            self.provision()
        self.assertEqual(self.rows('SELECT id FROM memory.api_keys WHERE revoked_at IS NULL'), [])

    def test_a_link_or_a_directory_as_the_key_file_is_refused_before_anything_is_written(self):
        self.key_file.parent.mkdir(parents=True)
        target = self.key_file.parent / 'elsewhere'
        target.write_text('keep', encoding='utf-8')
        os.symlink(target, self.key_file)
        with self.assertRaises(probe.ProbeError) as raised:
            self.provision()
        self.assertEqual(raised.exception.code, 'key_file_unsafe')
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['n'], 0)
        self.key_file.unlink()
        self.key_file.mkdir()
        with self.assertRaises(probe.ProbeError):
            self.provision()

    def test_the_command_prints_the_key_id_and_the_path_and_never_the_token(self):
        out, err = io.StringIO(), io.StringIO()
        with patch('memory_platform.admin.Settings.from_env', return_value=Settings(self.store.dsn)), patch('memory_platform.admin.Store', return_value=self.store), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            admin.main(['probe-provision', '--key-file', str(self.key_file)])
        token = self.key_file.read_text(encoding='utf-8').strip()
        self.assertNotIn(token, out.getvalue() + err.getvalue())
        self.assertNotIn(token[:12], out.getvalue() + err.getvalue())
        report = json.loads(out.getvalue())
        self.assertEqual((report['status'], report['key']), ('provisioned', 'created'))
        self.assertNotIn('token', report)

    def test_the_default_key_file_is_outside_the_repository_on_the_volume_of_the_operator_service(self):
        self.assertFalse(Path(probe.DEFAULT_KEY_FILE).is_relative_to(ROOT))
        self.assertTrue(probe.DEFAULT_KEY_FILE.startswith('/backups/'))  # the volume of memory-admin

    def test_without_an_administrator_nothing_is_made(self):
        store = self.make_store(admin=False)
        with self.assertRaises(probe.ProbeError) as raised:
            probe.provision(store, self.key_file)
        self.assertEqual(raised.exception.code, 'no_admin')
        self.assertFalse(self.key_file.exists())

    def test_a_project_that_exists_with_the_off_policy_is_adopted_not_created_again(self):
        """The provisioning asks first (a restart of a half-done provisioning finds the project and goes on); a policy that refuses notes is set to the one the probe needs."""
        self.store.create_project(self.actor, {'id': probe.PROBE_PROJECT, 'title': 'made by hand'})  # every new project starts with capture off
        report = self.provision()
        self.assertEqual(report['project'], 'present')
        self.assertEqual(self.rows('SELECT policy FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['policy'], probe.PROBE_POLICY)


if __name__ == '__main__':
    unittest.main()
