"""CA-03 (T-13): disabling and enabling a user, from `PATCH /v1/users/{id}` and from `admin disable-user`/`enable-user`, on one writer of `store_access.py`.

The oracle: with a session and two keys, after the user is disabled the three get 401 on their next request and the login answers as a wrong password; once enabled, the keys that were not
revoked work again and the sessions do not. Disabling oneself or the last active administrator is 409, also with two requests at once.
"""
import json
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import auth as auth_module, passwords, store_auth
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import Conflict, Forbidden, MemoryError, Unauthorized
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
        return self.run_held(first, second, self.store, '_audit', lambda c, actor, action, *args, **kwargs: action == hold_action)

    def run_held(self, first, second, owner, name, when=lambda *args, **kwargs: True):
        """`run_pair` with the stop anywhere: `first` stops, with its transaction open, right after its first call of `owner.name` for which `when` is true (`store_auth.new_id` stops
        `create_user` between its last check and its insert)."""
        entered, release, out = threading.Event(), threading.Event(), {}
        real = getattr(owner, name)

        def hold(*args, **kwargs):
            result = real(*args, **kwargs)
            if threading.current_thread() is one and not entered.is_set() and when(*args, **kwargs):
                entered.set()
                release.wait(60)
            return result

        def run(name, call):
            try:
                out[name] = call()
            except BaseException as exc:  # reported by the assertions
                out[name] = exc
        with patch.object(owner, name, hold):
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

    def test_a_caller_that_is_not_the_global_administrator_gets_403_before_the_422_of_a_body_without_a_change(self):
        # fix1 of the review of phase 3 (gap 11): authorize first, then say what is wrong with the request
        bea, headers = self.session()
        for body in ({}, {'disabled': None}):
            with self.subTest(body=body):
                self.assertEqual(self.patch_user(bea, headers, self.admin['id'], body).status_code, 403)
        root, root_headers = self.root()
        self.assertEqual(self.patch_user(root, root_headers, self.bea, {}).status_code, 422, 'the global administrator still gets the 422')


class ClosingSkipsTheExpiredSessionsTests(UsersFixture):
    """fix1 of the review of phase 3 (gap 5): disabling, `admin set-password` and the change of password close only the sessions that are still alive, as the two closings of T-15 do: a
    session that expired is already dead, rewriting it costs a write per row of a table without pruning, and `sessions_revoked` counts what `users/{id}/sessions/revoke` counts."""

    def sessions(self, n):
        return [self.auth.login('bea', pw.PASSWORD, '198.51.100.%d' % (80 + i))['actor'] for i in range(n)]

    def expire(self, actor):
        self.observer.execute("UPDATE memory.web_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (actor['session_id'],))

    def revoked(self, actor):
        return self.count('SELECT (revoked_at IS NOT NULL)::int FROM memory.web_sessions WHERE id=%s', actor['session_id']) == 1

    def test_disabling_closes_only_the_live_sessions(self):
        gone, live = self.sessions(2)
        self.expire(gone)
        self.assertEqual(self.store.operator_set_disabled('bea', True)['sessions_revoked'], 1)
        self.assertEqual((self.revoked(gone), self.revoked(live)), (False, True))

    def test_set_password_closes_only_the_live_sessions(self):
        gone, live = self.sessions(2)
        self.expire(gone)
        self.assertEqual(self.store.set_password('bea', 'another-password-456')['sessions_revoked'], 1)
        self.assertEqual((self.revoked(gone), self.revoked(live)), (False, True))

    def test_the_change_of_password_closes_only_the_other_live_sessions(self):
        mine, gone, other = self.sessions(3)
        self.expire(gone)
        self.assertEqual(self.store.change_password(mine, pw.PASSWORD, 'another-password-456', '198.51.100.89'), {'changed': True})
        self.assertEqual((self.revoked(mine), self.revoked(gone), self.revoked(other)), (False, False, True))


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


class CallerLockTests(UsersFixture):
    """fix1 of the review of phase 3 (gap 4): the disabling locks the row of its caller too (with the target, in the order of their ids, as `replace_grants` does) and checks the credential
    again after the wait: an administrator whose session is closed meanwhile disables nobody. Two administrators who disable each other at once do not wait in a circle
    (`LastAdministratorTests.test_two_administrators_who_disable_each_other_at_once_leave_one`)."""

    def test_an_administrator_whose_session_is_closed_while_the_disabling_waits_is_401(self):
        first = self.auth.login('root-user', 'root-password-123', '198.51.100.71')['actor']
        other = self.auth.login('root-user', 'root-password-123', '198.51.100.72')['actor']
        waited, closed, disabled = self.run_pair(lambda: self.store.revoke_other_sessions(other), lambda: self.store.set_user_disabled(first, self.bea, True), 'sessions.revoked')
        self.assertTrue(waited, 'the disabling did not wait for the row of its caller')
        self.assertEqual(closed, {'revoked': 1})
        self.assertIsInstance(disabled, Unauthorized, disabled)
        self.assertFalse(self.disabled('bea'))
        self.assertEqual(self.events('user.disabled', self.bea), 0)


class CreateUserRaceTests(UsersFixture):
    """fix1 of the review of phase 3 (gap 1): the insert of `create_user` locks the row of the delegate (`FOR SHARE`) before it authorizes again, as `create_key` does. A disabling or a
    replacement of grants of the delegate that got there first makes the creation wait and then refuse it; a creation that got there first makes them wait, and they see it.

    What happens to the user created in the second order: it stays, with its grants. Its creation was authorized when it committed, and disabling the delegate or taking its grants away does
    not undo the users it created (they are people of their own, not credentials of the delegate); the audit shows `user.created` before the `user.disabled` or `grants.replaced` that followed."""

    def setUp(self):
        super().setUp()
        self.delegate = self.auth.login('bea', pw.PASSWORD, '198.51.100.70')['actor']  # administrator of p1, not global: it delegates
        self.root_actor = self.auth.login('root-user', 'root-password-123', '198.51.100.73')['actor']
        self.since = self.count('SELECT coalesce(max(id), 0) FROM memory.audit_events')  # the events of the fixture (bea's own `user.created`) are not this test's

    def create(self):
        return self.store.create_user(self.delegate, {'username': 'shadow', 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read', 'admin']})

    def shadow(self):
        return self.count("SELECT count(*) FROM memory.actors WHERE username='shadow'")

    def order(self, *actions):
        return [r[0] for r in self.observer.execute('SELECT action FROM memory.audit_events WHERE id>%s AND action=ANY(%s) ORDER BY id', (self.since, list(actions))).fetchall()]

    def test_a_delegate_disabled_before_the_insert_creates_nothing(self):
        waited, disabled, created = self.run_pair(lambda: self.store.set_user_disabled(self.root_actor, self.bea, True), self.create, 'user.disabled')
        self.assertTrue(waited, 'the creation did not wait for the row of its delegate')
        self.assertIsInstance(disabled, dict, disabled)
        self.assertIsInstance(created, Unauthorized, created)
        self.assertEqual((self.shadow(), self.order('user.created')), (0, []))

    def test_grants_taken_from_the_delegate_before_the_insert_create_nothing(self):
        waited, replaced, created = self.run_pair(lambda: self.store.replace_grants(self.root_actor, self.bea, [{'project_id': 'p1', 'permissions': ['read']}]), self.create, 'grants.replaced')
        self.assertTrue(waited, 'the creation did not wait for the row of its delegate')
        self.assertIsInstance(replaced, dict, replaced)
        self.assertIsInstance(created, Forbidden, created)
        self.assertEqual((self.shadow(), self.order('user.created')), (0, []))

    def test_a_creation_that_got_there_first_is_seen_by_the_disabling_that_follows(self):
        waited, created, disabled = self.run_held(self.create, lambda: self.store.set_user_disabled(self.root_actor, self.bea, True), store_auth, 'new_id')
        self.assertTrue(waited, 'the disabling did not wait for the creation in progress')
        self.assertIsInstance(created, dict, created)
        self.assertIsInstance(disabled, dict, disabled)
        self.assertEqual(self.order('user.created', 'user.disabled'), ['user.created', 'user.disabled'])
        self.assertEqual(self.shadow(), 1, 'the user created stays')
        self.assertFalse(self.disabled('shadow'))
        with self.assertRaises(Unauthorized):
            self.store.list_own_sessions(self.delegate)

    def test_a_creation_that_got_there_first_is_seen_by_the_replacement_that_follows(self):
        waited, created, replaced = self.run_held(self.create, lambda: self.store.replace_grants(self.root_actor, self.bea, [{'project_id': 'p1', 'permissions': ['read']}]), store_auth, 'new_id')
        self.assertTrue(waited, 'the replacement did not wait for the creation in progress')
        self.assertIsInstance(created, dict, created)
        self.assertIsInstance(replaced, dict, replaced)
        self.assertEqual(self.order('user.created', 'grants.replaced'), ['user.created', 'grants.replaced'])
        self.assertEqual(self.count("SELECT count(*) FROM memory.project_grants g JOIN memory.actors a ON a.id=g.actor_id WHERE a.username='shadow'"), 2, 'the user created keeps its grants')


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


class GrantsTests(UsersFixture):
    """CA-04 (T-14): `PUT /v1/users/{id}/grants` replaces the permissions per project of a user; the next request of its session and of its keys on a project taken away answers as a
    project without access (404, the current contract of `_require`), and the change is audited with the grants before and after."""

    def setUp(self):
        super().setUp()
        self.store.create_project(self.admin, {'id': 'p2', 'title': 'Project 2'})
        self.observer.execute("INSERT INTO memory.project_grants VALUES(%s,'p2','read'),(%s,'p2','write')", (self.bea, self.bea))

    def put(self, client, headers, user_id, grants):
        return client.put('/v1/users/%s/grants' % user_id, json={'grants': grants}, headers=headers)

    def grants(self, user_id):
        return [tuple(r) for r in self.observer.execute('SELECT project_id,permission FROM memory.project_grants WHERE actor_id=%s ORDER BY 1,2', (user_id,)).fetchall()]

    def audit(self):
        return [json.loads(r[0]) for r in self.observer.execute("SELECT resource_id FROM memory.audit_events WHERE action='grants.replaced' ORDER BY id").fetchall()]

    def test_the_oracle_the_session_and_the_key_lose_the_project_taken_away_on_their_next_request(self):
        session, _ = self.session()
        actor = self.auth.login('bea', pw.PASSWORD, '198.51.100.50')['actor']
        token = self.store.create_key(actor, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read']})['token']
        self.observer.execute('UPDATE memory.api_keys SET project_ids=%s::jsonb WHERE actor_id=%s', ('["p1","p2"]', self.bea))  # a key over both projects
        for path in ('/v1/projects/p1/policy', '/v1/projects/p2/policy'):
            self.assertEqual(session.get(path).status_code, 200, path)
            self.assertEqual(self.with_key(token, path), 200, path)
        root, headers = self.root()
        done = self.put(root, headers, self.bea, [{'project_id': 'p1', 'permissions': ['read', 'admin']}])
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(done.json(), {'id': self.bea, 'username': 'bea', 'grants': [{'project_id': 'p1', 'permissions': ['admin', 'read']}]})
        self.assertEqual(session.get('/v1/projects/p2/policy').status_code, 404, 'a project without access, as the contract answers today')
        self.assertEqual(self.with_key(token, '/v1/projects/p2/policy'), 404)
        self.assertEqual(session.get('/v1/projects/p1/policy').status_code, 200)
        self.assertEqual(self.with_key(token, '/v1/projects/p1/policy'), 200)
        self.assertEqual(self.grants(self.bea), [('p1', 'admin'), ('p1', 'read')])
        self.assertEqual(self.audit(), [{'user': self.bea, 'before': {'p1': ['admin', 'read'], 'p2': ['read', 'write']}, 'after': {'p1': ['admin', 'read']}}])

    def test_a_permission_taken_away_is_refused_on_the_next_request(self):
        session, headers = self.session()
        self.assertEqual(session.put('/v1/projects/p1/policy', json={'capture_mode': 'summary', 'temporal_projection': False}, headers=headers).status_code, 200)
        root, root_headers = self.root()
        self.assertEqual(self.put(root, root_headers, self.bea, [{'project_id': 'p1', 'permissions': ['read']}, {'project_id': 'p2', 'permissions': ['read']}]).status_code, 200)
        self.assertEqual(session.put('/v1/projects/p1/policy', json={'capture_mode': 'off', 'temporal_projection': False}, headers=headers).status_code, 403)

    def test_an_empty_list_takes_every_project_away(self):
        root, headers = self.root()
        done = self.put(root, headers, self.bea, [])
        self.assertEqual((done.status_code, done.json()['grants']), (200, []))
        self.assertEqual(self.grants(self.bea), [])

    def test_an_unknown_project_or_permission_or_a_project_named_twice_is_422_and_nothing_changes(self):
        root, headers = self.root()
        before = self.grants(self.bea)
        for grants in ([{'project_id': 'p1', 'permissions': ['read']}, {'project_id': 'nope', 'permissions': ['read']}],
                       [{'project_id': 'p1', 'permissions': ['read', 'own']}],
                       [{'project_id': 'p1', 'permissions': []}],
                       [{'project_id': 'p1', 'permissions': ['read']}, {'project_id': 'p1', 'permissions': ['write']}],
                       [{'project_id': 'P1!', 'permissions': ['read']}]):
            with self.subTest(grants=grants):
                self.assertEqual(self.put(root, headers, self.bea, grants).status_code, 422)
        self.assertEqual(self.grants(self.bea), before)
        self.assertEqual(self.audit(), [])

    def test_a_caller_that_is_not_the_global_administrator_gets_403_before_the_422_of_a_project_named_twice(self):
        # fix1 of the review of phase 3 (gap 11): authorize first, then say what is wrong with the grants
        twice = [{'project_id': 'p1', 'permissions': ['read']}, {'project_id': 'p1', 'permissions': ['write']}]
        bea, headers = self.session()
        self.assertEqual(self.put(bea, headers, self.bea, twice).status_code, 403)
        root, root_headers = self.root()
        self.assertEqual(self.put(root, root_headers, self.bea, twice).status_code, 422, 'the global administrator still gets the 422')
        self.assertEqual(self.audit(), [])

    def test_only_a_global_administrator_with_a_session_and_csrf_may_do_it(self):
        bea, bea_headers = self.session()
        body = [{'project_id': 'p1', 'permissions': ['read']}]
        self.assertEqual(self.put(bea, bea_headers, self.bea, body).status_code, 403, 'an administrator of p1 is not the global administrator')
        root_key = self.store.create_key(self.admin, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})['token']
        self.assertEqual(self.client().put('/v1/users/%s/grants' % self.bea, json={'grants': body}, headers={'Authorization': 'Bearer ' + root_key}).status_code, 403)
        root, root_headers = self.root()
        self.assertEqual(root.put('/v1/users/%s/grants' % self.bea, json={'grants': body}).status_code, 403, 'no origin, no CSRF')
        self.assertEqual(self.client().put('/v1/users/%s/grants' % self.bea, json={'grants': body}).status_code, 401)
        self.assertEqual(self.put(root, root_headers, 'nobody', body).status_code, 404)
        self.assertEqual(len(self.grants(self.bea)), 4)

    def test_two_replacements_of_one_user_at_once_wait_for_each_other(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.60')['actor']
        first = [{'project_id': 'p1', 'permissions': ['read']}]
        second = [{'project_id': 'p2', 'permissions': ['write']}]
        waited, one, two = self.run_pair(lambda: self.store.replace_grants(root, self.bea, first), lambda: self.store.replace_grants(root, self.bea, second), 'grants.replaced')
        self.assertTrue(waited, 'the second replacement did not wait for the first (no lock on the row of the user)')
        self.assertIsInstance(one, dict, one)
        self.assertIsInstance(two, dict, two)
        self.assertEqual(self.grants(self.bea), [('p2', 'write')])
        self.assertEqual(self.audit()[1]['before'], {'p1': ['read']}, 'the second read the grants the first left')

    def test_a_caller_disabled_while_it_waits_is_401(self):
        self.make_admin('bea')
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.61')['actor']
        bea = self.auth.login('bea', pw.PASSWORD, '198.51.100.62')['actor']
        waited, disabled, replaced = self.run_pair(lambda: self.store.set_user_disabled(bea, self.admin['id'], True), lambda: self.store.replace_grants(root, self.bea, []), 'user.disabled')
        self.assertTrue(waited)
        self.assertIsInstance(disabled, dict, disabled)
        self.assertIsInstance(replaced, Unauthorized, replaced)
        self.assertEqual(len(self.grants(self.bea)), 4)

    def test_a_caller_that_is_not_the_global_administrator_is_refused_before_it_waits_for_any_lock(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.63')['actor']
        bea = self.auth.login('bea', pw.PASSWORD, '198.51.100.64')['actor']
        for refused in (lambda: self.store.replace_grants(bea, self.bea, []), lambda: self.store.set_user_disabled(bea, self.admin['id'], True)):
            waited, replaced, outcome = self.run_pair(lambda: self.store.replace_grants(root, self.bea, [{'project_id': 'p1', 'permissions': ['read']}]), refused, 'grants.replaced')
            self.assertFalse(waited, 'a credential that may not do it took a lock')
            self.assertIsInstance(replaced, dict, replaced)
            self.assertIsInstance(outcome, Forbidden, outcome)


class CredentialEndRaceTests(UsersFixture):
    """T-22 (revision of phase 3, attempt 2, gap 1): `revoke_key` and the logout lock the row of the OWNER of the credential they end (`FOR NO KEY UPDATE`), and `create_key` and
    `create_user` lock it with `FOR SHARE` before they check the credential again. If the end of the credential gets there first, the creation in progress with that credential
    waits for it and fails with 401, and nothing is created; if the creation gets there first, the end waits for it and the creation stays (it was authorized when it committed)."""

    def setUp(self):
        super().setUp()
        self.root_actor = self.auth.login('root-user', 'root-password-123', '198.51.100.80')['actor']

    def made(self):
        return self.count("SELECT count(*) FROM memory.api_keys WHERE name='made'"), self.count("SELECT count(*) FROM memory.actors WHERE username='made'")

    def create(self, what, actor):
        if what == 'key':
            return lambda: self.store.create_key(actor, {'name': 'made', 'project_ids': ['p1'], 'scopes': ['read']})
        return lambda: self.store.create_user(actor, {'username': 'made', 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read']})

    def end(self, credential):
        return (lambda: self.store.revoke_key(self.root_actor, self.key_id)) if credential == 'key' else (lambda: self.auth.logout(self.session_token))

    def actor_of(self, credential):
        return self.key_actor if credential == 'key' else self.session_actor

    def run_end_first(self, credential, first, second):
        """The end of the credential stops with its transaction open: right after its audit event (`key.revoked`) or, for the logout, right after it empties the cache."""
        if credential == 'key':
            return self.run_pair(first, second, 'key.revoked')
        return self.run_held(first, second, auth_module, 'invalidate_auth')

    def test_a_creation_with_a_credential_that_ends_before_its_insert_waits_and_fails_with_401(self):
        for credential in ('key', 'session'):
            for what in ('key', 'user'):
                with self.subTest(credential=credential, creates=what):
                    self.setUp_case(credential)
                    waited, ended, created = self.run_end_first(credential, self.end(credential), self.create(what, self.actor_of(credential)))
                    self.assertTrue(waited, 'the creation did not wait for the end of its credential')
                    self.assertNotIsInstance(ended, BaseException, ended)
                    self.assertIsInstance(created, Unauthorized, created)
                    self.assertEqual(self.made(), (0, 0), 'nothing is created')

    def test_an_end_of_the_credential_that_comes_after_the_creation_waits_for_it_and_the_creation_stays(self):
        for credential in ('key', 'session'):
            for what in ('key', 'user'):
                with self.subTest(credential=credential, creates=what):
                    self.setUp_case(credential)
                    hold = ('key.created' if what == 'key' else 'user.created')
                    waited, created, ended = self.run_pair(self.create(what, self.actor_of(credential)), self.end(credential), hold)
                    self.assertTrue(waited, 'the end of the credential did not wait for the creation in progress')
                    self.assertIsInstance(created, dict, created)
                    self.assertNotIsInstance(ended, BaseException, ended)
                    self.assertEqual(self.made(), (1, 0) if what == 'key' else (0, 1))
                    with self.assertRaises(Unauthorized):
                        self.store.list_keys(self.actor_of(credential))  # and the credential is dead

    def setUp_case(self, credential):
        """A fresh credential for each case (the previous one ended) and nothing made yet."""
        self.observer.execute("DELETE FROM memory.project_grants WHERE actor_id IN (SELECT id FROM memory.actors WHERE username='made')")
        self.observer.execute("DELETE FROM memory.actors WHERE username='made'")
        self.observer.execute("DELETE FROM memory.api_keys WHERE name='made'")
        login = self.auth.login('bea', pw.PASSWORD, '198.51.100.%d' % (82 + self.count('SELECT count(*) FROM memory.web_sessions') % 100))
        self.session_actor, self.session_token = login['actor'], login['session_token']
        key = self.store.create_key(self.session_actor, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})
        self.key_id, self.key_actor = key['id'], self.auth.authenticate_bearer(key['token'])


class RevokeKeyLocksTests(UsersFixture):
    """fix1 of the review of phase 4, gaps 4 and 6: `revoke_key` authorizes the caller without any lock first, then locks the rows of the caller and of the owner of the key
    (`FOR NO KEY UPDATE`, in the order of their ids) and authorizes again. The end of the caller's own credential and the revocation wait for each other; a caller that may not
    revoke the key is refused before it waits for the rows of the owner."""

    def setUp(self):
        super().setUp()
        self.bea_actor = self.auth.login('bea', pw.PASSWORD, '198.51.100.120')['actor']

    def key(self):
        return self.store.create_key(self.bea_actor, {'name': 'k', 'project_ids': ['p1'], 'scopes': ['read']})

    def revoked(self, key_id):
        return self.count('SELECT revoked_at IS NOT NULL FROM memory.api_keys WHERE id=%s', key_id)

    def test_the_end_of_the_session_of_the_caller_and_a_revocation_wait_for_each_other(self):
        for order, n in (('the end of the session first', 121), ('the revocation first', 122)):
            with self.subTest(order=order):
                login = self.auth.login('root-user', 'root-password-123', '198.51.100.%d' % n)
                made = self.key()
                if order == 'the end of the session first':
                    waited, ended, revoked = self.run_held(lambda: self.auth.logout(login['session_token']), lambda: self.store.revoke_key(login['actor'], made['id']), auth_module, 'invalidate_auth')
                    self.assertTrue(waited, 'the revocation did not wait for the end of the session of its caller')
                    self.assertIsInstance(revoked, Unauthorized, revoked)
                    self.assertFalse(self.revoked(made['id']), 'nothing revoked by a session that ended first')
                    self.assertEqual(self.events('key.revoked', made['id']), 0)
                else:
                    waited, revoked, ended = self.run_pair(lambda: self.store.revoke_key(login['actor'], made['id']), lambda: self.auth.logout(login['session_token']), 'key.revoked')
                    self.assertTrue(waited, 'the end of the session did not wait for the revocation in progress')
                    self.assertIsInstance(revoked, dict, revoked)
                    self.assertTrue(self.revoked(made['id']))
                self.assertNotIsInstance(ended, BaseException, ended)
                with self.assertRaises(Unauthorized):
                    self.store.list_keys(login['actor'])

    def test_a_caller_that_may_not_revoke_the_key_is_refused_before_it_waits_for_any_lock(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.123')['actor']
        ana = self.auth.login('ana', pw.PASSWORD, '198.51.100.124')['actor']  # read on p1: may not revoke the keys of p1
        target, other = self.key(), self.key()
        # the revocation of another key of bea holds the rows of bea and of root with its transaction open
        waited, revoked, refused = self.run_pair(lambda: self.store.revoke_key(root, other['id']), lambda: self.store.revoke_key(ana, target['id']), 'key.revoked')
        self.assertFalse(waited, 'a credential that may not revoke the key waited for a lock')
        self.assertIsInstance(revoked, dict, revoked)
        self.assertIsInstance(refused, Forbidden, refused)
        self.assertFalse(self.revoked(target['id']))


if __name__ == '__main__':
    unittest.main()
