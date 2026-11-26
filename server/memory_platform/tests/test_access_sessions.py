"""CA-05 (T-15): a user lists its sessions and closes every one but the current; the global administrator closes every session of another user. Each closed session gets 401 on its next request.

The list shows creation, expiry, client address and which one is the current (DC-6), never a token or a hash.
"""
import threading
import time
import unittest
from unittest.mock import patch

from memory_platform.errors import Forbidden, Unauthorized
from memory_platform.tests import test_passwords as pw
from memory_platform.tests.test_access_users import ORIGIN, UsersFixture

FIELDS = {'id', 'created_at', 'expires_at', 'client_ip', 'current'}


class SessionsTests(UsersFixture):
    def events(self, resource):
        return self.count("SELECT count(*) FROM memory.audit_events WHERE action='sessions.revoked' AND resource_id=%s", resource)

    def test_the_list_shows_the_live_sessions_with_their_address_and_the_current_one_and_no_secret(self):
        first, _ = self.session()
        self.session()
        other = self.auth.login('bea', pw.PASSWORD, '198.51.100.7')
        gone = self.auth.login('bea', pw.PASSWORD, '198.51.100.8')
        self.auth.logout(gone['session_token'])
        listed = first.get('/v1/auth/sessions')
        self.assertEqual(listed.status_code, 200, listed.text)
        items = listed.json()['items']
        self.assertEqual(len(items), 3, 'the closed one is not listed')
        self.assertTrue(all(set(item) == FIELDS for item in items), items)
        self.assertEqual(sum(item['current'] for item in items), 1)
        self.assertEqual(sorted(item['client_ip'] for item in items), ['198.51.100.7', 'testclient', 'testclient'])
        self.assertTrue(all(item['created_at'] and item['expires_at'] for item in items))
        text = listed.text
        for secret in [first.cookies.get('memory_session'), other['session_token'], other['csrf_token']] + [r[0] for r in self.observer.execute(
                'SELECT token_hash FROM memory.web_sessions WHERE actor_id=%s UNION ALL SELECT csrf_hash FROM memory.web_sessions WHERE actor_id=%s', (self.bea, self.bea)).fetchall()]:
            self.assertNotIn(secret, text)

    def test_the_login_keeps_the_client_address_of_the_session(self):
        self.auth.login('bea', pw.PASSWORD, '203.0.113.9')
        self.assertEqual(self.count('SELECT count(*) FROM memory.web_sessions WHERE actor_id=%s AND client_ip=%s AND created_at IS NOT NULL', self.bea, '203.0.113.9'), 1)

    def test_closing_the_others_keeps_the_current_one(self):
        first, headers = self.session()
        second, _ = self.session()
        third = self.auth.login('bea', pw.PASSWORD, '198.51.100.9')
        done = first.post('/v1/auth/sessions/revoke-others', headers=headers)
        self.assertEqual((done.status_code, done.json()), (200, {'revoked': 2}), done.text)
        self.assertEqual(second.get('/v1/auth/me').status_code, 401, 'each closed session gets 401 on its next request')
        with self.assertRaises(Unauthorized):
            self.auth.authenticate_session(third['session_token'])
        self.assertEqual(first.get('/v1/auth/me').status_code, 200, 'the current one stays')
        self.assertEqual([item['current'] for item in first.get('/v1/auth/sessions').json()['items']], [True])
        self.assertEqual(self.events(self.bea), 1)

    def test_the_administrator_closes_every_session_of_another_user(self):
        first, _ = self.session()
        second, _ = self.session()
        root, headers = self.root()
        done = root.post('/v1/users/%s/sessions/revoke' % self.bea, headers=headers)
        self.assertEqual((done.status_code, done.json()), (200, {'id': self.bea, 'revoked': 2}), done.text)
        self.assertEqual([first.get('/v1/auth/me').status_code, second.get('/v1/auth/me').status_code], [401, 401])
        me = root.get('/v1/auth/me')  # `me` gives a new CSRF token to a session
        self.assertEqual(me.status_code, 200)
        self.assertEqual(self.events(self.bea), 1)
        self.assertEqual(root.post('/v1/users/nobody/sessions/revoke', headers={'Origin': ORIGIN, 'X-CSRF-Token': me.json()['csrf_token']}).status_code, 404)


    def test_closing_the_sessions_of_another_user_is_only_for_the_global_administrator(self):
        bea, headers = self.session()  # administrator of p1, not global
        root, root_headers = self.root()
        self.assertEqual(bea.post('/v1/users/%s/sessions/revoke' % self.admin['id'], headers=headers).status_code, 403)
        self.assertEqual(root.get('/v1/auth/me').status_code, 200, 'nothing was closed')
        key = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        anonymous = self.client()
        bearer = {'Authorization': 'Bearer ' + key}
        for method, path in (('GET', '/v1/auth/sessions'), ('POST', '/v1/auth/sessions/revoke-others'), ('POST', '/v1/users/%s/sessions/revoke' % self.bea)):
            with self.subTest(path=path):
                self.assertEqual(anonymous.request(method, path, headers=bearer).status_code, 403, 'a key is not a signed-in session')
                self.assertEqual(anonymous.request(method, path).status_code, 401)
        for path in ('/v1/auth/sessions/revoke-others', '/v1/users/%s/sessions/revoke' % self.bea):
            with self.subTest(csrf=path):
                self.assertEqual(root.post(path).status_code, 403, 'no origin, no CSRF')
                self.assertEqual(root.post(path, headers={'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}).status_code, 403)
        self.assertEqual(bea.get('/v1/auth/me').status_code, 200)
        self.assertEqual(self.events(self.bea) + self.events(self.admin['id']), 0)


class SessionsRaceTests(UsersFixture):
    def hold_login(self, username, password, then):
        """A login of `username` stops with its session inserted and not committed (it holds `FOR SHARE` on the row of the user); `then()` runs on another thread and must wait for it."""
        entered, release, out = threading.Event(), threading.Event(), {}
        real = self.store._describe

        def describe(c, row, credential_type, credential_id=None):
            actor = real(c, row, credential_type, credential_id)
            if threading.current_thread() is login:
                entered.set()
                release.wait(60)
            return actor

        def run(name, call):
            try:
                out[name] = call()
            except BaseException as exc:
                out[name] = exc
        with patch.object(self.store, '_describe', describe):
            login = threading.Thread(target=run, args=('login', lambda: self.auth.login(username, password, '198.51.100.20')))
            login.start()
            self.assertTrue(entered.wait(60))
            other = threading.Thread(target=run, args=('other', then))
            other.start()
            deadline = time.monotonic() + 60
            while other.is_alive() and not self.someone_waits_for_a_lock() and time.monotonic() < deadline:
                pass  # no sleep: each pass is a round trip to the database
            waited = self.someone_waits_for_a_lock()
            release.set()
            login.join(60)
            other.join(60)
        self.assertFalse(login.is_alive() or other.is_alive())
        return waited, out['login'], out['other']

    def test_a_login_in_progress_while_the_others_are_closed_gets_closed_too(self):
        current = self.auth.login('bea', pw.PASSWORD, '198.51.100.21')['actor']
        waited, login, closed = self.hold_login('bea', pw.PASSWORD, lambda: self.store.revoke_other_sessions(current))
        self.assertTrue(waited, 'the closing did not wait for the login in progress (no lock on the row of the user)')
        self.assertEqual(closed, {'revoked': 1})
        with self.assertRaises(Unauthorized):
            self.auth.authenticate_session(login['session_token'])
        self.assertEqual([item['current'] for item in self.store.list_own_sessions(current)], [True], 'the current one stays')

    def test_a_login_in_progress_while_the_administrator_closes_them_gets_closed_too(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.22')['actor']
        waited, login, closed = self.hold_login('bea', pw.PASSWORD, lambda: self.store.revoke_user_sessions(root, self.bea))
        self.assertTrue(waited)
        self.assertEqual(closed, {'id': self.bea, 'revoked': 1})
        with self.assertRaises(Unauthorized):
            self.auth.authenticate_session(login['session_token'])

    def test_a_session_closed_while_the_closing_waits_is_401(self):
        """The password changes from another session (it holds the row of the user and has closed this one, uncommitted): the closing of the others waits for it, then its own credential
        is checked again and is gone."""
        mine = self.auth.login('bea', pw.PASSWORD, '198.51.100.23')['actor']
        other = self.auth.login('bea', pw.PASSWORD, '198.51.100.24')['actor']
        waited, changed, closed = self.run_pair(lambda: self.store.change_password(other, pw.PASSWORD, 'brand-new-password-456', '198.51.100.24'),
                                                lambda: self.store.revoke_other_sessions(mine), 'password.changed')
        self.assertTrue(waited)
        self.assertEqual(changed, {'changed': True})
        self.assertIsInstance(closed, Unauthorized, closed)

    def test_an_administrator_disabled_while_the_closing_waits_is_401(self):
        self.make_admin('bea')
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.25')['actor']
        bea = self.auth.login('bea', pw.PASSWORD, '198.51.100.26')['actor']
        waited, disabled, closed = self.run_pair(lambda: self.store.set_user_disabled(bea, self.admin['id'], True), lambda: self.store.revoke_user_sessions(root, self.bea), 'user.disabled')
        self.assertTrue(waited)
        self.assertIsInstance(disabled, dict, disabled)
        self.assertIsInstance(closed, Unauthorized, closed)
        self.assertEqual(self.count('SELECT count(*) FROM memory.web_sessions WHERE actor_id=%s AND revoked_at IS NULL', self.bea), 1, 'the session of bea stays')

    def test_the_store_refuses_a_key_with_403_after_checking_it(self):
        token = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        actor = self.auth.authenticate_bearer(token)
        for call in (lambda: self.store.list_own_sessions(actor), lambda: self.store.revoke_other_sessions(actor), lambda: self.store.revoke_user_sessions(actor, self.bea)):
            with self.assertRaises(Forbidden):
                call()


if __name__ == '__main__':
    unittest.main()
