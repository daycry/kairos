"""CA-05 (T-15): a user lists its sessions and closes every one but the current; the global administrator lists and closes every session of another user (CA-42). Each closed session gets
401 on its next request.

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


    def test_the_list_hides_the_expired_sessions(self):
        # fix1 of the review of phase 3 (gap 6): a session that expired is dead, as a closed one
        first, _ = self.session()
        gone = self.auth.login('bea', pw.PASSWORD, '198.51.100.10')['actor']
        self.observer.execute("UPDATE memory.web_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (gone['session_id'],))
        self.assertEqual([item['current'] for item in first.get('/v1/auth/sessions').json()['items']], [True])

    def test_the_administrator_who_names_itself_closes_its_current_session_too(self):
        # fix1 of the review of phase 3 (gap 6): `users/{id}/sessions/revoke` closes EVERY session of the user, the caller's own current one when it names itself (T-15 decision)
        root, headers = self.root()
        self.auth.login('root-user', 'root-password-123', '198.51.100.11')
        done = root.post('/v1/users/%s/sessions/revoke' % self.admin['id'], headers=headers)
        self.assertEqual((done.status_code, done.json()), (200, {'id': self.admin['id'], 'revoked': 2}), done.text)
        self.assertEqual(root.get('/v1/auth/me').status_code, 401, 'the current session is closed too')
        self.assertEqual(self.count('SELECT count(*) FROM memory.web_sessions WHERE actor_id=%s AND revoked_at IS NULL', self.admin['id']), 0)

    def test_the_administrator_lists_the_live_sessions_of_another_user_and_no_secret(self):
        # fix1 of the review of phase 3 (gap 10, CA-42): `GET /v1/users/{id}/sessions`, the same fields as `GET /v1/auth/sessions`
        first, _ = self.session()
        other = self.auth.login('bea', pw.PASSWORD, '198.51.100.12')
        closed = self.auth.login('bea', pw.PASSWORD, '198.51.100.13')
        self.auth.logout(closed['session_token'])
        expired = self.auth.login('bea', pw.PASSWORD, '198.51.100.14')['actor']
        self.observer.execute("UPDATE memory.web_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (expired['session_id'],))
        root, _ = self.root()
        listed = root.get('/v1/users/%s/sessions' % self.bea)
        self.assertEqual(listed.status_code, 200, listed.text)
        items = listed.json()['items']
        self.assertEqual(sorted(item['client_ip'] for item in items), ['198.51.100.12', 'testclient'], 'only the live ones')
        self.assertTrue(all(set(item) == FIELDS for item in items), items)
        self.assertEqual([item['current'] for item in items], [False, False], 'none of them is the session of the caller')
        for secret in [first.cookies.get('memory_session'), other['session_token'], other['csrf_token']] + [r[0] for r in self.observer.execute(
                'SELECT token_hash FROM memory.web_sessions WHERE actor_id=%s UNION ALL SELECT csrf_hash FROM memory.web_sessions WHERE actor_id=%s', (self.bea, self.bea)).fetchall()]:
            self.assertNotIn(secret, listed.text)
        mine = root.get('/v1/users/%s/sessions' % self.admin['id']).json()['items']
        self.assertEqual([item['current'] for item in mine], [True], 'its own list marks the current one')
        self.assertEqual(root.get('/v1/users/nobody/sessions').status_code, 404)

    def test_listing_the_sessions_of_another_user_is_only_for_the_global_administrator(self):
        bea, _ = self.session()  # administrator of p1, not global
        self.assertEqual(bea.get('/v1/users/%s/sessions' % self.admin['id']).status_code, 403)
        self.assertEqual(bea.get('/v1/users/%s/sessions' % self.bea).status_code, 403, 'not even its own: that is `GET /v1/auth/sessions`')
        key = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        self.assertEqual(self.client().get('/v1/users/%s/sessions' % self.bea, headers={'Authorization': 'Bearer ' + key}).status_code, 403, 'a key is not a signed-in session')
        self.assertEqual(self.client().get('/v1/users/%s/sessions' % self.bea).status_code, 401)

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

    def change_while(self, closing, hold_action):
        """The change of password of a session of bea derives while `closing` closes that session (and holds the row of bea, uncommitted): its last transaction waits for it."""
        mine = self.auth.login('bea', pw.PASSWORD, '198.51.100.27')['actor']
        before = self.count('SELECT count(*) FROM memory.audit_events')
        stored = self.stored_hash('bea')
        waited, closed, changed = self.run_pair(lambda: closing(mine), lambda: self.store.change_password(mine, pw.PASSWORD, 'brand-new-password-456', '198.51.100.27'), hold_action)
        self.assertTrue(waited, 'the change did not wait for the row of the user')
        self.assertIsInstance(closed, dict, closed)
        self.assertIsInstance(changed, Unauthorized, 'a session closed while the change waited changed the password')
        self.assertEqual(self.stored_hash('bea'), stored, 'nothing changed')
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='password.changed'"), 0, 'no event')
        self.assertGreater(self.count('SELECT count(*) FROM memory.audit_events'), before)

    def test_a_change_of_password_from_a_session_closed_by_a_disabling_is_401(self):
        # fix1 of the review of phase 3 (gap 2): the session is checked again under the lock of the row of the user
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.28')['actor']
        self.change_while(lambda mine: self.store.set_user_disabled(root, self.bea, True), 'user.disabled')

    def test_a_change_of_password_from_a_session_closed_by_the_administrator_is_401(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.29')['actor']
        self.change_while(lambda mine: self.store.revoke_user_sessions(root, self.bea), 'sessions.revoked')

    def test_a_change_of_password_from_a_session_closed_by_another_session_is_401(self):
        other = self.auth.login('bea', pw.PASSWORD, '198.51.100.30')['actor']
        self.change_while(lambda mine: self.store.revoke_other_sessions(other), 'sessions.revoked')

    def test_the_store_refuses_a_key_with_403_after_checking_it(self):
        token = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        actor = self.auth.authenticate_bearer(token)
        for call in (lambda: self.store.list_own_sessions(actor), lambda: self.store.revoke_other_sessions(actor), lambda: self.store.revoke_user_sessions(actor, self.bea),
                     lambda: self.store.list_user_sessions(actor, self.bea)):
            with self.assertRaises(Forbidden):
                call()


if __name__ == '__main__':
    unittest.main()
