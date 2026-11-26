"""CA-03 (T-13): disabling and enabling a user, from `PATCH /v1/users/{id}` and from `admin disable-user`/`enable-user`, on one writer of `store_access.py`.

The oracle: with a session and two keys, after the user is disabled the three get 401 on their next request and the login answers as a wrong password; once enabled, the keys that were not
revoked work again and the sessions do not. Disabling oneself or the last active administrator is 409, also with two requests at once.
"""
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import passwords
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import Conflict, MemoryError, Unauthorized
from memory_platform.tests import test_passwords as pw

ORIGIN = 'http://127.0.0.1:5173'


class UsersFixture(pw.Fixture):
    def setUp(self):
        super().setUp()
        self.auth = Auth(self.store, [ORIGIN])
        self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        self.bea = self.store.create_user(self.admin, {'username': 'bea', 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['id']
        self.observer = self.psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.observer.close)

    def client(self):
        client = TestClient(self.app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def session(self, username='bea', password=pw.PASSWORD):
        """A client with its own cookie jar and the headers its state-changing requests need (origin and CSRF)."""
        client = self.client()
        login = client.post('/v1/auth/login', json={'username': username, 'password': password}, headers={'Origin': ORIGIN})
        self.assertEqual(login.status_code, 200, login.text)
        return client, {'Origin': ORIGIN, 'X-CSRF-Token': login.json()['csrf_token']}

    def root(self):
        return self.session('root-user', 'root-password-123')

    def key_of(self, username='bea'):
        self.logins = getattr(self, 'logins', 0) + 1
        actor = self.auth.login(username, pw.PASSWORD, '198.51.100.%d' % self.logins)['actor']
        return self.store.create_key(actor, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read']})['token']

    def with_key(self, token, path='/v1/projects'):
        return self.client().get(path, headers={'Authorization': 'Bearer ' + token}).status_code

    def count(self, query, *args):
        return self.observer.execute(query, args).fetchone()[0]

    def events(self, action, resource):
        return self.count('SELECT count(*) FROM memory.audit_events WHERE action=%s AND resource_id=%s', action, resource)

    def make_admin(self, username):
        self.observer.execute('UPDATE memory.actors SET is_admin=true WHERE username=%s', (username,))

    def disabled(self, username):
        return self.count('SELECT disabled::int FROM memory.actors WHERE username=%s', username) == 1

    def someone_waits_for_a_lock(self):
        return self.observer.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()").fetchone()[0] > 0

    def run_pair(self, first, second, hold_action):
        """`first` runs on a thread and stops, with its transaction open, right after it audits `hold_action`; `second` starts then and its wait for a lock is seen in `pg_stat_activity`;
        `first` is released. No sleep, no clock. Returns (waited, outcome of first, outcome of second)."""
        entered, release, out = threading.Event(), threading.Event(), {}
        real = self.store._audit

        def hold(c, actor, action, *args, **kwargs):
            result = real(c, actor, action, *args, **kwargs)
            if action == hold_action and threading.current_thread() is one:
                entered.set()
                release.wait(60)
            return result

        def run(name, call):
            try:
                out[name] = call()
            except BaseException as exc:  # reported by the assertions
                out[name] = exc
        with patch.object(self.store, '_audit', hold):
            one = threading.Thread(target=run, args=('first', first))
            one.start()
            try:
                self.assertTrue(entered.wait(60), 'the first transaction never reached its audit event')
                two = threading.Thread(target=run, args=('second', second))
                two.start()
                deadline = time.monotonic() + 60
                while two.is_alive() and not self.someone_waits_for_a_lock() and time.monotonic() < deadline:
                    pass  # no sleep: each pass is a round trip to the database
                waited = self.someone_waits_for_a_lock()
            finally:
                release.set()
            one.join(60)
            two.join(60)
        self.assertFalse(one.is_alive() or two.is_alive())
        return waited, out.get('first'), out.get('second')


class DisableRouteTests(UsersFixture):
    def patch_user(self, client, headers, user_id, body):
        return client.patch('/v1/users/' + user_id, json=body, headers=headers)

    def test_the_oracle_the_session_and_two_keys_get_401_and_after_enabling_only_the_keys_come_back(self):
        session, _ = self.session()
        keys = [self.key_of(), self.key_of()]
        root, headers = self.root()
        self.assertEqual(session.get('/v1/auth/me').status_code, 200)
        self.assertEqual([self.with_key(k) for k in keys], [200, 200])
        done = self.patch_user(root, headers, self.bea, {'disabled': True})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual((done.json()['id'], done.json()['username'], done.json()['disabled']), (self.bea, 'bea', True))
        self.assertEqual(session.get('/v1/auth/me').status_code, 401, 'the session gets 401 on its next request')
        self.assertEqual([self.with_key(k) for k in keys], [401, 401], 'both keys get 401 while the user is disabled')
        self.assertEqual(self.events('user.disabled', self.bea), 1)
        enabled = self.patch_user(root, headers, self.bea, {'disabled': False})
        self.assertEqual((enabled.status_code, enabled.json()['disabled']), (200, False), enabled.text)
        self.assertEqual([self.with_key(k) for k in keys], [200, 200], 'the keys that were not revoked work again')
        self.assertEqual(session.get('/v1/auth/me').status_code, 401, 'the sessions do not come back')
        self.assertEqual(self.events('user.enabled', self.bea), 1)
        self.session()  # and the user may sign in again

    def test_a_revoked_key_stays_revoked_after_enabling(self):
        token = self.key_of()
        kid = self.observer.execute("SELECT id FROM memory.api_keys WHERE actor_id=%s", (self.bea,)).fetchone()[0]
        root, headers = self.root()
        self.assertEqual(self.patch_user(root, headers, self.bea, {'disabled': True}).status_code, 200)
        self.store.revoke_key(self.admin, kid)
        self.assertEqual(self.patch_user(root, headers, self.bea, {'disabled': False}).status_code, 200)
        self.assertEqual(self.with_key(token), 401)

    def test_the_login_of_a_disabled_user_answers_as_a_wrong_password(self):
        root, headers = self.root()
        self.assertEqual(self.patch_user(root, headers, self.bea, {'disabled': True}).status_code, 200)
        client = self.client()
        right = client.post('/v1/auth/login', json={'username': 'bea', 'password': pw.PASSWORD}, headers={'Origin': ORIGIN})
        wrong = client.post('/v1/auth/login', json={'username': 'bea', 'password': 'not-the-password-999'}, headers={'Origin': ORIGIN})
        self.assertEqual((right.status_code, right.json()['error']), (wrong.status_code, wrong.json()['error']))
        self.assertEqual(right.status_code, 401)
        with pw.Derivations() as spy, self.assertRaises(Unauthorized):
            self.auth.login('bea', pw.PASSWORD, '192.0.2.90')
        self.assertEqual(spy.calls, [passwords.TARGET], 'the same cost as a wrong password')

    def test_disabling_oneself_is_409_and_changes_nothing(self):
        self.make_admin('bea')  # root is not the last active administrator: the refusal is Â«never oneselfÂ»
        root, headers = self.root()
        refused = self.patch_user(root, headers, self.admin['id'], {'disabled': True})
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (409, 'conflict'))
        self.assertEqual(refused.json()['error']['message'], 'An administrator cannot disable itself')
        self.assertFalse(self.disabled('root-user'))

        self.assertEqual(root.get('/v1/auth/me').status_code, 200)
        self.assertEqual(self.events('user.disabled', self.admin['id']), 0)

    def test_only_a_global_administrator_with_a_session_and_csrf_may_do_it(self):
        bea, bea_headers = self.session()  # administrator of p1, not global
        self.assertEqual(self.patch_user(bea, bea_headers, self.admin['id'], {'disabled': True}).status_code, 403)
        root_key = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        by_key = self.client().patch('/v1/users/' + self.bea, json={'disabled': True}, headers={'Authorization': 'Bearer ' + root_key})
        self.assertEqual(by_key.status_code, 403, 'a key of the global administrator is not the global administrator')
        root, headers = self.root()
        self.assertEqual(root.patch('/v1/users/' + self.bea, json={'disabled': True}).status_code, 403, 'no origin, no CSRF')
        self.assertEqual(root.patch('/v1/users/' + self.bea, json={'disabled': True}, headers={'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}).status_code, 403)
        self.assertEqual(self.client().patch('/v1/users/' + self.bea, json={'disabled': True}).status_code, 401)
        self.assertFalse(self.disabled('bea'))

    def test_an_unknown_user_is_404_and_a_body_without_a_change_is_422(self):
        root, headers = self.root()
        self.assertEqual(self.patch_user(root, headers, 'nobody', {'disabled': True}).status_code, 404)
        for body in ({}, {'disabled': None}, {'disabled': True, 'is_admin': True}, {'disabled': 'yes'}):
            with self.subTest(body=body):
                self.assertEqual(self.patch_user(root, headers, self.bea, body).status_code, 422)
        self.assertFalse(self.disabled('bea'))

    def test_the_writer_is_idempotent_and_audits_each_call(self):
        root, headers = self.root()
        for _ in range(2):
            self.assertEqual(self.patch_user(root, headers, self.bea, {'disabled': True}).status_code, 200)
        self.assertTrue(self.disabled('bea'))
        self.assertEqual(self.events('user.disabled', self.bea), 2)


class LastAdministratorTests(UsersFixture):
    def setUp(self):
        super().setUp()
        self.make_admin('bea')

    def test_the_last_active_administrator_cannot_be_disabled_by_the_operator(self):
        self.assertEqual(self.store.operator_set_disabled('bea', True)['disabled'], True)
        with self.assertRaises(Conflict):
            self.store.operator_set_disabled('root-user', True)
        self.assertFalse(self.disabled('root-user'))
        self.assertEqual(self.events('user.disabled', self.admin['id']), 0)

    def test_a_disabled_administrator_does_not_count_as_active(self):
        self.store.operator_set_disabled('bea', True)
        with self.assertRaises(Conflict):
            self.store.operator_set_disabled('root-user', True)
        self.store.operator_set_disabled('bea', False)
        self.assertTrue(self.store.operator_set_disabled('root-user', True)['disabled'], 'with bea enabled again, root is not the last one')

    def test_two_operators_at_once_leave_one_active_administrator(self):
        waited, first, second = self.run_pair(lambda: self.store.operator_set_disabled('bea', True), lambda: self.store.operator_set_disabled('root-user', True), 'user.disabled')
        self.assertTrue(waited, 'the second disabling did not wait for the first (no lock that serialises them)')
        self.assertIsInstance(first, dict, first)
        self.assertIsInstance(second, Conflict, second)
        self.assertEqual(self.count('SELECT count(*) FROM memory.actors WHERE is_admin AND NOT disabled'), 1)

    def test_two_administrators_who_disable_each_other_at_once_leave_one(self):
        root = self.auth.login('root-user', 'root-password-123', '192.0.2.91')['actor']
        bea = self.auth.login('bea', pw.PASSWORD, '192.0.2.92')['actor']
        waited, first, second = self.run_pair(lambda: self.store.set_user_disabled(root, self.bea, True), lambda: self.store.set_user_disabled(bea, self.admin['id'], True), 'user.disabled')
        self.assertTrue(waited)
        self.assertIsInstance(first, dict, first)
        self.assertIsInstance(second, Unauthorized, 'the second administrator was disabled while it waited: its credential is checked again after the lock')
        self.assertEqual(self.count('SELECT count(*) FROM memory.actors WHERE is_admin AND NOT disabled'), 1)

    def test_an_administrator_and_the_operator_at_once(self):
        root = self.auth.login('root-user', 'root-password-123', '192.0.2.93')['actor']
        waited, first, second = self.run_pair(lambda: self.store.set_user_disabled(root, self.bea, True), lambda: self.store.operator_set_disabled('root-user', True), 'user.disabled')
        self.assertTrue(waited)
        self.assertIsInstance(first, dict, first)
        self.assertIsInstance(second, Conflict, 'root is the last active administrator once bea is disabled')
        self.assertFalse(self.disabled('root-user'))


class DisableLoginRaceTests(UsersFixture):
    """A login in progress and the disabling of its user: no session of that login outlives the disabling, also after the user is enabled again."""

    def test_a_user_disabled_during_the_derivation_of_the_login_gets_no_session(self):
        real, fired = passwords._derive, []

        def derive(password, salt, params):
            digest = real(password, salt, params)
            if not fired:
                fired.append(1)
                self.store.operator_set_disabled('bea', True)
            return digest
        with patch.object(passwords, '_derive', derive), self.assertRaises(Unauthorized):
            self.auth.login('bea', pw.PASSWORD, '192.0.2.94')
        self.assertEqual(self.count('SELECT count(*) FROM memory.web_sessions WHERE actor_id=%s', self.bea), 0)

    def test_a_session_the_login_opens_while_the_disabling_waits_is_revoked_with_the_others(self):
        """The login has inserted its session and not committed (it holds `FOR SHARE` on the row of the user); the disabling waits for it and then closes that session too: enabling the user
        later does not bring it back."""
        entered, release, out = threading.Event(), threading.Event(), {}
        real = self.store._describe

        def describe(c, row, credential_type, credential_id=None):
            actor = real(c, row, credential_type, credential_id)
            if threading.current_thread() is login:
                entered.set()
                release.wait(60)
            return actor

        def run():
            try:
                out['login'] = self.auth.login('bea', pw.PASSWORD, '192.0.2.95')
            except BaseException as exc:
                out['login'] = exc
        with patch.object(self.store, '_describe', describe):
            login = threading.Thread(target=run)
            login.start()
            self.assertTrue(entered.wait(60))
            disabling = threading.Thread(target=lambda: out.setdefault('disable', self.store.operator_set_disabled('bea', True)))
            disabling.start()
            deadline = time.monotonic() + 60
            while disabling.is_alive() and not self.someone_waits_for_a_lock() and time.monotonic() < deadline:
                pass
            waited = self.someone_waits_for_a_lock()
            release.set()
            login.join(60)
            disabling.join(60)
        self.assertTrue(waited, 'the disabling did not wait for the login in progress')
        self.assertIsInstance(out['login'], dict, out['login'])
        self.assertEqual(out['disable']['sessions_revoked'], 1, 'the session of the login is closed by the disabling')
        self.store.operator_set_disabled('bea', False)
        with self.assertRaises(Unauthorized):
            self.auth.authenticate_session(out['login']['session_token'])


if __name__ == '__main__':
    unittest.main()
