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
from memory_platform.auth import Auth, hash_password, verify_password
from memory_platform.errors import Unauthorized
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

    def test_a_half_done_provisioning_is_adopted_not_created_again(self):
        """The provisioning asks first (a restart of a half-done provisioning finds the project it made, with its title, and goes on); a policy that refuses notes is set to the one the probe needs."""
        self.store.create_project(self.actor, {'id': probe.PROBE_PROJECT, 'title': probe.PROBE_TITLE})  # every new project starts with capture off
        report = self.provision()
        self.assertEqual(report['project'], 'present')
        self.assertEqual(self.rows('SELECT policy FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['policy'], probe.PROBE_POLICY)
    # -- fix1 of the review of phase 11 (items 2, 6, 7, 8) ----------------------------------------------------------------------------

    def service_actor(self):
        return self.rows('SELECT id,is_admin,disabled,password_hash FROM memory.actors WHERE username=%s', probe.SERVICE_USERNAME)[0]

    def test_the_key_belongs_to_a_service_actor_that_is_no_administrator_and_cannot_log_in(self):
        """Item 8: the audit of a run names `kairos-probe`, not the first administrator by name; the actor has no global role, no usable password and the least grants on one project."""
        report = self.provision()
        service = self.service_actor()
        self.assertEqual((service['is_admin'], service['disabled'], report['actor']), (False, False, probe.SERVICE_USERNAME))
        self.assertEqual(self.rows('SELECT actor_id FROM memory.api_keys WHERE id=%s', report['key_id'])[0]['actor_id'], service['id'])
        grants = self.rows('SELECT project_id,permission FROM memory.project_grants WHERE actor_id=%s ORDER BY permission', service['id'])
        self.assertEqual([(g['project_id'], g['permission']) for g in grants], [(probe.PROBE_PROJECT, 'admin'), (probe.PROBE_PROJECT, 'read'), (probe.PROBE_PROJECT, 'write')])
        auth = Auth(self.store, [ORIGIN])
        for password in ('', '!service-account', 'fixture-password-123', 'a-password-of-twelve+'):
            with self.subTest(password=password), self.assertRaises(Unauthorized):
                auth.login(probe.SERVICE_USERNAME, password)
        self.assertFalse(verify_password('anything-at-all-12', service['password_hash']))

    def test_what_a_run_writes_is_audited_as_the_service_actor_and_provisioning_as_the_operator(self):
        report = self.provision()
        token = self.key_file.read_text(encoding='utf-8').strip()
        service = self.service_actor()
        with TestClient(self.make_app(self.store), base_url=ORIGIN, raise_server_exceptions=False) as client:
            self.assertEqual(ClientApi(client, token).call('POST', '/v1/events', user_event(probe.PROBE_PROJECT))[0], 202)
        by = {row['action']: row['actor_id'] for row in self.rows('SELECT action,actor_id FROM memory.audit_events WHERE actor_id IS NOT NULL ORDER BY id')}
        self.assertEqual(by['event.accepted'], service['id'])
        self.assertEqual(by['project.created'], self.actor['id'])  # one-off: the administrator that made the project
        self.assertEqual(by['key.created'], service['id'])
        self.assertEqual(report['key'], 'created')

    def test_as_names_the_administrator_that_makes_the_project_and_an_unknown_one_is_refused_before_any_write(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (str(uuid.uuid4()), 'zz-operator', hash_password('fixture-password-123')))
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,false)', (str(uuid.uuid4()), 'plain-user', hash_password('fixture-password-123')))
        for name in ('plain-user', 'nobody'):
            with self.subTest(name), self.assertRaises(probe.ProbeError) as raised:
                probe.provision(self.store, self.key_file, operator=name)
            self.assertEqual(raised.exception.code, 'operator_unknown')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['n'], 0)
        probe.provision(self.store, self.key_file, operator='zz-operator')
        zz = self.rows('SELECT id FROM memory.actors WHERE username=%s', 'zz-operator')[0]['id']
        self.assertEqual(self.rows("SELECT actor_id FROM memory.audit_events WHERE action='project.created' AND project_id=%s", probe.PROBE_PROJECT)[0]['actor_id'], zz)

    def test_a_disabled_owner_is_never_a_reused_key_and_is_an_explicit_error(self):
        """Item 2, the repro of the review: with the owner disabled the API answers 401, so provisioning must not say `reused`."""
        first = self.provision()
        with self.store.transaction() as c:
            c.execute('UPDATE memory.actors SET disabled=true WHERE username=%s', (probe.SERVICE_USERNAME,))
        token = self.key_file.read_text(encoding='utf-8').strip()
        with TestClient(self.make_app(self.store), base_url=ORIGIN, raise_server_exceptions=False) as client:
            self.assertEqual(ClientApi(client, token).call('POST', '/v1/events', user_event(probe.PROBE_PROJECT))[0], 401)
        self.assertIsNone(probe.valid_key(self.store, token, probe.PROBE_PROJECT, self.service_actor()['id']))
        with self.assertRaises(probe.ProbeError) as raised:
            self.provision()
        self.assertEqual(raised.exception.code, 'actor_disabled')
        self.assertEqual(self.key_file.read_text(encoding='utf-8').strip(), token)
        self.assertEqual(self.rows('SELECT id FROM memory.api_keys WHERE revoked_at IS NULL')[0]['id'], first['key_id'])
        with self.store.transaction() as c:
            c.execute('UPDATE memory.actors SET disabled=false WHERE username=%s', (probe.SERVICE_USERNAME,))
        self.assertEqual(self.provision()['key'], 'reused')

    def test_valid_key_is_what_the_api_says_the_owner_without_a_grant_or_a_revoked_or_expired_key_are_not_valid(self):
        """The predicate is the API's own (`Auth.authenticate_bearer` and `require_permission`): every way the API refuses a key makes `valid_key` None."""
        report = self.provision()
        token = self.key_file.read_text(encoding='utf-8').strip()
        owner = self.service_actor()['id']
        self.assertEqual(probe.valid_key(self.store, token, probe.PROBE_PROJECT, owner), report['key_id'])
        self.assertIsNone(probe.valid_key(self.store, token, probe.PROBE_PROJECT, 'somebody-else'))
        self.assertIsNone(probe.valid_key(self.store, 'mp_nothing', probe.PROBE_PROJECT, owner))
        with self.store.transaction() as c:
            c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s AND permission=%s', (owner, 'write'))
            from memory_platform.auth_scope import invalidate_auth
            invalidate_auth(c)
        self.assertIsNone(probe.valid_key(self.store, token, probe.PROBE_PROJECT, owner))  # an owner without the role the key needs
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,%s)', (owner, probe.PROBE_PROJECT, 'write'))
            c.execute("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (report['key_id'],))
        self.assertIsNone(probe.valid_key(self.store, token, probe.PROBE_PROJECT, owner))
        with self.store.transaction() as c:
            c.execute('UPDATE memory.api_keys SET expires_at=NULL, revoked_at=clock_timestamp() WHERE id=%s', (report['key_id'],))
        self.assertIsNone(probe.valid_key(self.store, token, probe.PROBE_PROJECT, owner))

    def test_checking_the_key_is_not_a_use_of_it(self):
        """fix1 of the review of phase 4, gap 9: `valid_key` asks what the API would answer, it is not a request: the last use of the key stays what the requests left."""
        report = self.provision()
        token = self.key_file.read_text(encoding='utf-8').strip()
        self.assertEqual(probe.valid_key(self.store, token, probe.PROBE_PROJECT, self.service_actor()['id']), report['key_id'])
        self.assertEqual(self.provision()['key'], 'reused')
        self.assertIsNone(self.rows('SELECT last_used_at FROM memory.api_keys WHERE id=%s', report['key_id'])[0]['last_used_at'])

    def test_a_key_of_an_earlier_provisioning_owned_by_an_administrator_is_rotated_to_the_service_actor(self):
        """The keys made before this change belong to an administrator; they are replaced (and revoked), so the audit stops naming a human."""
        self.store.create_project(self.actor, {'id': probe.PROBE_PROJECT, 'title': probe.PROBE_TITLE})
        legacy = self.store.create_key(self.actor, {'name': probe.PROBE_KEY_NAME, 'project_ids': [probe.PROBE_PROJECT], 'scopes': list(probe.PROBE_SCOPES)})
        self.key_file.parent.mkdir(parents=True)
        self.key_file.write_text(legacy['token'] + '\n', encoding='utf-8')
        report = self.provision()
        self.assertEqual(report['key'], 'created')
        self.assertIsNotNone(self.rows('SELECT revoked_at FROM memory.api_keys WHERE id=%s', legacy['id'])[0]['revoked_at'])
        self.assertEqual(self.rows('SELECT actor_id FROM memory.api_keys WHERE id=%s', report['key_id'])[0]['actor_id'], self.service_actor()['id'])

    def test_a_project_named_kairos_probe_that_is_not_the_probes_is_an_error_and_is_left_alone(self):
        """Item 7: another title, or a grant to somebody else, means somebody else's project: no policy change, no actor, no key, no file."""
        self.store.create_project(self.actor, {'id': probe.PROBE_PROJECT, 'title': 'made by hand'})
        before = self.rows('SELECT policy,title FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)
        with self.assertRaises(probe.ProbeError) as raised:
            self.provision()
        self.assertEqual(raised.exception.code, 'project_foreign')
        self.assertEqual(self.rows('SELECT policy,title FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT), before)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.actors WHERE username=%s', probe.SERVICE_USERNAME)[0]['n'], 0)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.api_keys')[0]['n'], 0)
        self.assertFalse(self.key_file.exists())

    def test_a_project_with_the_title_of_the_probe_and_a_grant_to_a_user_is_somebody_elses(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.projects(id,title) VALUES(%s,%s)', (probe.PROBE_PROJECT, probe.PROBE_TITLE))
            c.execute('INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,%s)', (self.actor['id'], probe.PROBE_PROJECT, 'read'))
        with self.assertRaises(probe.ProbeError) as raised:
            self.provision()
        self.assertEqual(raised.exception.code, 'project_foreign')
        self.assertEqual(self.rows('SELECT policy FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['policy'], {'capture_mode': 'off', 'temporal_projection': False})

    def test_a_user_named_kairos_probe_that_is_not_the_service_account_is_an_error_and_is_left_alone(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (str(uuid.uuid4()), probe.SERVICE_USERNAME, hash_password('fixture-password-123')))
        with self.assertRaises(probe.ProbeError) as raised:
            self.provision()
        self.assertEqual(raised.exception.code, 'actor_foreign')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.projects WHERE id=%s', probe.PROBE_PROJECT)[0]['n'], 0)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.project_grants')[0]['n'], 0)

    def test_two_provisionings_at_once_never_leave_both_keys_revoked(self):
        """Item 6: each used to revoke the key the other had just made. Serialised by the advisory lock, the loser finds the winner's key valid and reuses it."""
        import threading
        self.provision()
        self.key_file.write_text('mp_' + 'x' * 64 + '\n', encoding='utf-8')  # the file is invalid: both runs want to make a key
        barrier = threading.Barrier(2)
        results, errors = [], []

        def work():
            try:
                barrier.wait(10)
                results.append(probe.provision(self.store, self.key_file))
            except BaseException as error:
                errors.append(error)
        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(result['key'] for result in results), ['created', 'reused'])
        active = self.rows('SELECT id FROM memory.api_keys WHERE name=%s AND revoked_at IS NULL', probe.PROBE_KEY_NAME)
        self.assertEqual(len(active), 1)
        token = self.key_file.read_text(encoding='utf-8').strip()
        self.assertEqual(probe.valid_key(self.store, token, probe.PROBE_PROJECT, self.service_actor()['id']), active[0]['id'])
        self.assertEqual({result['key_id'] for result in results}, {active[0]['id']})

    def retired_note(self, project_id):
        """A retired note (a `delete` at version 2) of `project_id` with its jobs finished, so nothing but the owner check can keep the purge from deleting it."""
        item = str(uuid.uuid4())
        note = {'event_id': str(uuid.uuid4()), 'project_id': project_id, 'session_id': 's', 'agent_id': 'a', 'event_type': 'note', 'occurred_at': '2026-11-17T10:00:00Z', 'item_id': item,
                'version': 1, 'generate': False, 'payload': {'title': 'Old note', 'content': 'A retired note', 'source': {'uri': 'fixture://old'}}}
        self.store.ingest_event(self.actor, note)
        self.store.ingest_event(self.actor, dict(note, event_id=str(uuid.uuid4()), event_type='delete', version=2))
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='succeeded' WHERE project_id=%s", (project_id,))
        return item

    def test_the_purge_of_a_project_named_kairos_probe_that_is_not_the_probes_deletes_nothing(self):
        """fix2 item 1: the same check as the provisioning (title and grants) runs before any row is deleted; a foreign project is `project_foreign`, never purged."""
        self.store.create_project(self.actor, {'id': probe.PROBE_PROJECT, 'title': 'made by hand'})
        self.store.set_policy(self.actor, probe.PROBE_PROJECT, {'capture_mode': 'summary', 'temporal_projection': False})
        item = self.retired_note(probe.PROBE_PROJECT)
        count = lambda: self.rows('SELECT (SELECT count(*) FROM memory.memory_items WHERE project_id=%s) AS items, (SELECT count(*) FROM memory.events WHERE project_id=%s) AS events',
                                  probe.PROBE_PROJECT, probe.PROBE_PROJECT)[0]
        before = count()
        self.assertEqual(before['items'], 1)
        with self.assertRaises(probe.ProbeError) as raised:
            probe.purge_retired(self.store, [item], older_than=0)
        self.assertEqual(raised.exception.code, 'project_foreign')
        self.assertIsNone(probe.purge_after(lambda: self.store, {'item_id': item}))  # the command logs the code and goes on
        self.assertEqual(count(), before)
        with self.store.transaction() as c:  # control: with the title of the probe (and no other grantee) the same call does purge, so the test above is not vacuous
            c.execute('UPDATE memory.projects SET title=%s WHERE id=%s', (probe.PROBE_TITLE, probe.PROBE_PROJECT))
        self.assertEqual(probe.purge_retired(self.store, [item], older_than=0), 1)

    def test_a_grant_to_a_user_makes_the_project_foreign_for_the_purge_too(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.projects(id,title) VALUES(%s,%s)', (probe.PROBE_PROJECT, probe.PROBE_TITLE))
            c.execute('INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,%s)', (self.actor['id'], probe.PROBE_PROJECT, 'read'))
        with self.assertRaises(probe.ProbeError) as raised:
            probe.purge_retired(self.store, older_than=0)
        self.assertEqual(raised.exception.code, 'project_foreign')

    def test_the_rotation_never_revokes_the_key_of_a_human_administrator(self):
        """fix2 item 2: only the keys of the service account (and the one in the key file) are rotated; an administrator's key with the same name and reach stays active."""
        first = self.provision()
        human = self.store.create_key(self.actor, {'name': probe.PROBE_KEY_NAME, 'project_ids': [probe.PROBE_PROJECT], 'scopes': list(probe.PROBE_SCOPES)})
        self.key_file.write_text('mp_' + 'x' * 64 + '\n', encoding='utf-8')  # the file is no longer valid: the key is rotated
        second = self.provision()
        self.assertEqual(second['key'], 'created')
        self.assertIsNone(self.rows('SELECT revoked_at FROM memory.api_keys WHERE id=%s', human['id'])[0]['revoked_at'])
        self.assertIsNotNone(self.rows('SELECT revoked_at FROM memory.api_keys WHERE id=%s', first['key_id'])[0]['revoked_at'])  # the service account's own previous key does go

    def audit(self):
        return self.rows('SELECT action,actor_id,project_id,resource_id FROM memory.audit_events ORDER BY id')

    def test_the_service_account_and_its_grants_are_audited_as_the_operator_and_a_second_run_adds_nothing(self):
        """fix2 item 3 (CWE-778): the creation of the actor and of its three grants, and the issuing of the key, leave rows through the same `_audit` as `store_auth`."""
        report = self.provision()
        service = self.service_actor()
        rows = self.audit()
        created = [row for row in rows if row['action'] == 'user.created']
        self.assertEqual([(row['actor_id'], row['resource_id']) for row in created], [(self.actor['id'], service['id'])])
        grants = [row for row in rows if row['action'] == 'grant.created']
        self.assertEqual(len(grants), len(probe.SERVICE_GRANTS))
        self.assertEqual({(row['actor_id'], row['project_id'], row['resource_id']) for row in grants}, {(self.actor['id'], probe.PROBE_PROJECT, service['id'])})
        issued = [row for row in rows if row['action'] == 'probe.key_issued']
        self.assertEqual([(row['actor_id'], row['project_id'], row['resource_id']) for row in issued], [(self.actor['id'], probe.PROBE_PROJECT, report['key_id'])])
        self.assertEqual(self.provision()['key'], 'reused')
        self.assertEqual(self.audit(), rows)

    def test_as_is_always_validated_and_a_rotation_is_attributed_to_the_operator(self):
        """fix2 item 3: `--as` was ignored when the project already existed; now an unknown one is refused, and a given one signs the rotation."""
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (str(uuid.uuid4()), 'zz-operator', hash_password('fixture-password-123')))
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,false)', (str(uuid.uuid4()), 'plain-user', hash_password('fixture-password-123')))
        self.provision()  # the project exists from now on
        self.key_file.write_text('mp_' + 'x' * 64 + '\n', encoding='utf-8')
        before = self.audit()
        for name in ('plain-user', 'nobody'):
            with self.subTest(name), self.assertRaises(probe.ProbeError) as raised:
                probe.provision(self.store, self.key_file, operator=name)
            self.assertEqual(raised.exception.code, 'operator_unknown')
        self.assertEqual(self.audit(), before)
        report = probe.provision(self.store, self.key_file, operator='zz-operator')
        zz = self.rows('SELECT id FROM memory.actors WHERE username=%s', 'zz-operator')[0]['id']
        issued = [row for row in self.audit() if row['action'] == 'probe.key_issued' and row['resource_id'] == report['key_id']]
        self.assertEqual([row['actor_id'] for row in issued], [zz])

    def test_probe_provision_takes_as_and_reports_the_actor(self):
        out = io.StringIO()
        with patch('memory_platform.admin.Settings.from_env', return_value=Settings(self.store.dsn)), patch('memory_platform.admin.Store', return_value=self.store), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            admin.main(['probe-provision', '--key-file', str(self.key_file), '--as', self.rows('SELECT username FROM memory.actors WHERE is_admin')[0]['username']])
        self.assertEqual(json.loads(out.getvalue())['actor'], probe.SERVICE_USERNAME)


if __name__ == '__main__':
    unittest.main()
