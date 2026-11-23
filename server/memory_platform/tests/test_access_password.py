"""CA-01 (T-09): `POST /v1/auth/password` and `store_access.py`, the one door of the changes of access.

The oracle of A-01: with two sessions open, changing the password from one closes the other on its next request, keeps the first, keeps the keys, and leaves an audit event.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import passwords
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import MemoryError
from memory_platform.tests import test_passwords as pw

ORIGIN = 'http://127.0.0.1:5173'
NEW = 'brand-new-password-456'


class PasswordRouteTests(pw.Fixture):
    def setUp(self):
        super().setUp()
        self.auth = Auth(self.store, [ORIGIN])
        self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        self.clients = []

    def session(self, username='ana', password=pw.PASSWORD):
        """A client with its own cookie jar and the CSRF token its login gave."""
        client = TestClient(self.app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        login = client.post('/v1/auth/login', json={'username': username, 'password': password}, headers={'Origin': ORIGIN})
        self.assertEqual(login.status_code, 200, login.text)
        return client, {'Origin': ORIGIN, 'X-CSRF-Token': login.json()['csrf_token']}

    def change(self, client, headers, current=pw.PASSWORD, new=NEW):
        return client.post('/v1/auth/password', json={'current_password': current, 'new_password': new}, headers=headers)

    def count(self, query, *args):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute(query, args).fetchone()[0]

    def test_the_oracle_the_other_session_is_closed_this_one_stays_and_the_event_is_written(self):
        first, first_headers = self.session()
        second, _ = self.session()
        self.assertEqual(second.get('/v1/auth/me').status_code, 200)
        done = self.change(first, first_headers)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(second.get('/v1/auth/me').status_code, 401, 'the other session is closed on its next request')
        self.assertEqual(first.get('/v1/auth/me').status_code, 200, 'the session that changed it stays')
        with self.assertRaises(MemoryError) as old:
            self.auth.login('ana', pw.PASSWORD, '192.0.2.70')
        self.assertEqual(old.exception.status_code, 401)
        self.assertEqual(self.auth.login('ana', NEW, '192.0.2.70')['actor']['username'], 'ana')
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='password.changed' AND resource_id=(SELECT id FROM memory.actors WHERE username='ana')"), 1)

    def client_get_with_key(self, token):
        with TestClient(self.app) as client:
            return client.get('/v1/projects', headers={'Authorization': 'Bearer ' + token}).status_code

    def test_the_keys_of_the_user_survive_the_change(self):
        self.store.create_user(self.admin, {'username': 'owner', 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read', 'admin']})
        owner, owner_headers = self.session('owner')
        key = owner.post('/v1/keys', json={'name': 'mine', 'project_ids': ['p1'], 'scopes': ['read']}, headers=owner_headers)
        self.assertEqual(key.status_code, 200, key.text)
        self.assertEqual(self.change(owner, owner_headers, new=NEW).status_code, 200)
        self.assertEqual(self.client_get_with_key(key.json()['token']), 200)

    def test_a_wrong_current_password_changes_nothing_and_counts_as_a_failed_login_of_that_ip(self):
        client, headers = self.session()
        before = self.count('SELECT count(*) FROM memory.login_attempts')
        refused = self.change(client, headers, current='not-the-password-999')
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (403, 'invalid_current_password'))
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts WHERE username=%s AND client_ip=%s', 'ana', 'testclient'), 2, 'the login of the fixture and the wrong current password')
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts'), before + 1)
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='password.changed'"), 0)
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.71')['actor']['username'], 'ana', 'the old password still works')
        self.assertEqual(client.get('/v1/auth/me').status_code, 200)

    def test_ten_wrong_currents_block_the_ip_with_429_before_any_derivation(self):
        client, headers = self.session()
        for _ in range(9):  # the login of the fixture is the first of the ten attempts of this IP
            self.assertEqual(self.change(client, headers, current='not-the-password-999').status_code, 403)
        with pw.Derivations() as spy:
            blocked = self.change(client, headers)  # even the right one: the IP is blocked
        self.assertEqual((blocked.status_code, blocked.json()['error']['code'], spy.calls), (429, 'rate_limited', []))

    def test_a_new_password_under_twelve_characters_is_422_and_derives_nothing(self):
        client, headers = self.session()
        with pw.Derivations() as spy:
            short = self.change(client, headers, new='short')
        self.assertEqual((short.status_code, short.json()['error']['code'], spy.calls), (422, 'invalid_password', []))
        self.assertEqual(self.count("SELECT count(*) FROM memory.login_attempts WHERE username='ana'"), 1, 'only the login of the fixture')

    def test_only_a_session_with_csrf_may_change_it_a_key_gets_403(self):
        client, headers = self.session()
        self.assertEqual(client.post('/v1/auth/password', json={'current_password': pw.PASSWORD, 'new_password': NEW}).status_code, 403, 'no CSRF, no origin')
        self.assertEqual(client.post('/v1/auth/password', json={'current_password': pw.PASSWORD, 'new_password': NEW}, headers={'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}).status_code, 403)
        key = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.post('/v1/auth/password', json={'current_password': 'x' * 12, 'new_password': NEW}).status_code, 401)
            by_key = anonymous.post('/v1/auth/password', json={'current_password': 'root-password-123', 'new_password': NEW}, headers={'Authorization': 'Bearer ' + key['token']})
        self.assertEqual(by_key.status_code, 403)
        self.assertTrue(passwords.verify_password('root-password-123', self.stored_hash('root-user')), 'nothing changed')

    def test_the_change_costs_two_target_derivations_and_none_of_them_is_the_new_password_stored_in_clear(self):
        client, headers = self.session()
        with pw.Derivations() as spy:
            self.assertEqual(self.change(client, headers).status_code, 200)
        self.assertEqual(spy.calls, [passwords.TARGET, passwords.TARGET])
        self.assertNotIn(NEW, self.stored_hash())
        self.assertTrue(passwords.verify_password(NEW, self.stored_hash()))

    def test_a_password_changed_meanwhile_is_not_overwritten(self):
        client, headers = self.session()
        real = passwords.check_login

        def changed_meanwhile(password, encoded):
            result = real(password, encoded)
            self.set_hash(pw.old_hash('somebody-else-789'))
            return result
        with patch('memory_platform.store_access.passwords.check_login', changed_meanwhile):
            raced = self.change(client, headers)
        self.assertEqual((raced.status_code, raced.json()['error']['code']), (409, 'conflict'))
        self.assertTrue(passwords.verify_password('somebody-else-789', self.stored_hash()))

    def test_a_full_gate_answers_503_and_counts_no_failure(self):
        client, headers = self.session()
        gate = passwords.LoginGate(1, wait=0.0, clock=pw.Clock(), wait_on=pw.no_wait)
        before = self.count('SELECT count(*) FROM memory.login_attempts')
        with patch.object(passwords, 'GATE', gate), gate.hold('198.51.100.99'):
            busy = self.change(client, headers)
        self.assertEqual((busy.status_code, busy.json()['error']['code'], busy.headers['Retry-After']), (503, 'login_busy', '2'))
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts'), before)


class AccessChangedTests(pw.Fixture):
    """`_access_changed` audits and empties the permission cache of the transaction that changed access: by construction, for every writer that ends in it."""
    def test_it_writes_the_event_and_empties_the_cache(self):
        with self.store.transaction() as c:
            self.store._active(c, self.admin)
            self.assertTrue(getattr(c, '_kairos_auth'), 'the permission cache holds what was resolved')
            self.store._access_changed(c, self.admin, 'access.tested', project_id='p1', resource_id='r1')
            self.assertEqual(getattr(c, '_kairos_auth'), {}, 'emptied after the change')
        with self.psycopg.connect(self.dsn) as c:
            row = c.execute("SELECT project_id,resource_id FROM memory.audit_events WHERE action='access.tested'").fetchone()
        self.assertEqual(row, ('p1', 'r1'))


if __name__ == '__main__':
    unittest.main()
