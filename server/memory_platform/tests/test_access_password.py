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
from memory_platform.errors import MemoryError, Unauthorized
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
        real = passwords.verify_password

        def changed_meanwhile(password, encoded):
            result = real(password, encoded)
            self.set_hash(pw.old_hash('somebody-else-789'))
            return result
        with patch('memory_platform.store_access.passwords.verify_password', changed_meanwhile):
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

    # ---- fix1 of the review of phase 2 (2026-11-23): gaps 1, 6 and 8 ----
    def busy_gate(self):
        gate = passwords.LoginGate(1, wait=0.0, clock=pw.Clock(), wait_on=pw.no_wait)
        taken = gate.hold('198.51.100.99')
        taken.__enter__()
        self.addCleanup(taken.__exit__, None, None, None)
        return gate

    def test_more_than_five_correct_changes_in_fifteen_minutes_get_429_without_deriving_or_taking_a_slot(self):
        """Gap 1: the limit counts the CORRECT changes too (the failures were already counted): a session cannot alternate the route without end and fill the gate of the others."""
        client, headers = self.session()
        current = pw.PASSWORD
        for number in range(5):
            new = 'rotating-password-%d-xyz' % number
            self.assertEqual(self.change(client, headers, current=current, new=new).status_code, 200)
            current = new
        before = self.count('SELECT count(*) FROM memory.login_attempts')
        with patch.object(passwords, 'GATE', self.busy_gate()), pw.Derivations() as spy:  # a full gate: the 429 is decided before the slot, so it is not a 503
            blocked = self.change(client, headers, current=current, new=NEW)
        self.assertEqual((blocked.status_code, blocked.json()['error']['code'], spy.calls), (429, 'too_many_attempts', []))
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts'), before, 'it is not a failed login either')
        self.assertTrue(passwords.verify_password(current, self.stored_hash()), 'nothing changed')
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='password.changed'"), 5)

    def test_the_limit_is_five_per_user_in_the_last_fifteen_minutes_and_nothing_else_counts(self):
        client, headers = self.session()
        ana, root = self.count("SELECT id FROM memory.actors WHERE username='ana'"), self.admin['id']
        with self.psycopg.connect(self.dsn) as c:
            for actor, minutes, count in ((ana, 16, 5), (root, 1, 5), (ana, 14, 4)):  # old ones of the same user, recent ones of ANOTHER user, and four recent ones of this one
                for _ in range(count):
                    c.execute("INSERT INTO memory.audit_events(actor_id,action,happened_at) VALUES(%s,'password.changed',clock_timestamp()-make_interval(mins => %s))", (actor, minutes))
            c.execute("INSERT INTO memory.audit_events(actor_id,action) VALUES(%s,'password.reset')", (ana,))  # another action is not a change
        self.assertEqual(self.change(client, headers).status_code, 200, 'the fifth in the window is the last allowed')
        self.assertEqual(self.change(client, headers, current=NEW, new='sixth-password-789').status_code, 429)

    def test_the_429_of_the_failures_is_decided_before_the_slot(self):
        """Gap 8 (DC-5): order = 429, then slot, then scrypt."""
        client, headers = self.session()
        with self.psycopg.connect(self.dsn) as c:
            for _ in range(10):
                c.execute("INSERT INTO memory.login_attempts(username,client_ip) VALUES('someone','testclient')")
        with patch.object(passwords, 'GATE', self.busy_gate()), pw.Derivations() as spy:
            blocked = self.change(client, headers)
        self.assertEqual((blocked.status_code, blocked.json()['error']['code'], spy.calls), (429, 'rate_limited', []))

    def test_the_failure_of_the_current_password_is_recorded_under_the_advisory_locks_of_the_login(self):
        client, headers = self.session()
        seen = []
        real = self.psycopg.Cursor.execute

        def spy(cursor, query, params=None, *args, **kwargs):
            seen.append((str(query), params))
            return real(cursor, query, params, *args, **kwargs)
        with patch.object(self.psycopg.Cursor, 'execute', spy):
            self.assertEqual(self.change(client, headers, current='not-the-password-999').status_code, 403)
        insert = next(i for i, (query, _) in enumerate(seen) if query.startswith('INSERT INTO memory.login_attempts'))
        locks = [params for query, params in seen[:insert] if 'pg_advisory_xact_lock' in query]
        self.assertEqual(locks[-2:], [('login-ip:testclient',), ('login-user:ana',)], 'the two locks of Auth.login, in its order, right before the recount and the insert')

    def test_a_failure_recorded_meanwhile_by_other_requests_is_recounted_under_the_lock(self):
        """Ten failures of the IP may arrive while this request derives: under the lock the recount sees them and the eleventh is not written (429, like the login)."""
        client, headers = self.session()
        real = passwords.verify_password

        def failures_arrive(password, encoded):
            result = real(password, encoded)
            with self.psycopg.connect(self.dsn) as c:  # the login of the fixture made one: nine more make ten
                for _ in range(9):
                    c.execute("INSERT INTO memory.login_attempts(username,client_ip) VALUES('someone','testclient')")
            return result
        with patch('memory_platform.store_access.passwords.verify_password', failures_arrive):
            refused = self.change(client, headers, current='not-the-password-999')
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (429, 'rate_limited'))
        self.assertEqual(self.count("SELECT count(*) FROM memory.login_attempts WHERE client_ip='testclient'"), 10, 'the eleventh was not written')

    def test_an_old_hash_costs_the_cheap_check_and_one_target_derivation_not_two(self):
        """Gap 6: `change_password` no longer derives the rehash of the current password (the login's) when the stored hash is an old one."""
        client, headers = self.session()
        self.set_hash(pw.old_hash())
        with pw.Derivations() as spy:
            self.assertEqual(self.change(client, headers).status_code, 200)
        self.assertEqual(spy.calls, [pw.OLD, passwords.TARGET])
        self.assertTrue(passwords.verify_password(NEW, self.stored_hash()))


class CreateUserOrderTests(pw.Fixture):
    """Gap 2: `POST /v1/users` authorizes and refuses a duplicate BEFORE deriving and before taking a slot; it derives outside the transaction and inserts in one that authorizes again."""
    BODY = {'username': 'newbie', 'password': 'another-password-123', 'project_ids': ['p1'], 'scopes': ['read']}

    def setUp(self):
        super().setUp()
        self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        self.admin_key = self.store.create_key(self.admin, {'name': 'admin', 'project_ids': ['p1'], 'scopes': ['read', 'admin']})
        self.reader_key = self.store.create_key(self.admin, {'name': 'reader', 'project_ids': ['p1'], 'scopes': ['read']})

    def post(self, key, body=None):
        with TestClient(self.app) as client:
            return client.post('/v1/users', json=body or self.BODY, headers={'Authorization': 'Bearer ' + key['token']})

    def users(self, username='newbie'):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute('SELECT count(*) FROM memory.actors WHERE username=%s', (username,)).fetchone()[0]

    def busy_gate(self):
        gate = passwords.LoginGate(1, wait=0.0, clock=pw.Clock(), wait_on=pw.no_wait)
        taken = gate.hold('198.51.100.99')
        taken.__enter__()
        self.addCleanup(taken.__exit__, None, None, None)
        return gate

    def test_a_credential_without_permission_gets_403_with_no_derivation_and_no_slot(self):
        with patch.object(passwords, 'GATE', self.busy_gate()), pw.Derivations() as spy:  # a full gate would say 503 to a request that reached it
            refused = self.post(self.reader_key)
        self.assertEqual((refused.status_code, refused.json()['error']['code'], spy.calls), (403, 'forbidden', []))
        self.assertEqual(self.users(), 0)

    def test_a_duplicate_username_gets_409_with_no_derivation_and_no_slot(self):
        with patch.object(passwords, 'GATE', self.busy_gate()), pw.Derivations() as spy:
            refused = self.post(self.admin_key, dict(self.BODY, username='ana'))
        self.assertEqual((refused.status_code, refused.json()['error']['code'], spy.calls), (409, 'conflict', []))

    def test_an_authorized_creation_derives_once_and_outside_any_transaction(self):
        open_during = []
        real = passwords._derive

        def watch(password, salt, params):
            with self.psycopg.connect(self.dsn) as c:
                open_during.append(c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state LIKE 'idle in transaction%'").fetchone()[0])
            return real(password, salt, params)
        with patch.object(passwords, '_derive', watch):
            created = self.post(self.admin_key)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(open_during, [0], 'no transaction is open while scrypt runs')
        self.assertTrue(passwords.verify_password(self.BODY['password'], self.stored_hash('newbie')))

    def test_a_key_revoked_while_the_password_was_derived_creates_nothing(self):
        """The insert re-authorizes: the permissions may have changed during the derivation."""
        real = passwords._derive

        def revoke_meanwhile(password, salt, params):
            with self.psycopg.connect(self.dsn) as c:
                c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE id=%s', (self.admin_key['id'],))
            return real(password, salt, params)
        with patch.object(passwords, '_derive', revoke_meanwhile):
            refused = self.post(self.admin_key)
        self.assertEqual(refused.status_code, 401)
        self.assertEqual(self.users(), 0)

    def test_a_username_taken_while_the_password_was_derived_is_409(self):
        real = passwords._derive

        def taken_meanwhile(password, salt, params):
            with self.psycopg.connect(self.dsn) as c:
                c.execute("INSERT INTO memory.actors(id,username,password_hash) VALUES('u-rival','newbie','!')")
            return real(password, salt, params)
        with patch.object(passwords, '_derive', taken_meanwhile):
            refused = self.post(self.admin_key)
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (409, 'conflict'))
        self.assertEqual(self.users(), 1)


class LoginRaceTests(pw.Fixture):
    """Gap 3: between verifying the password and opening the session another transaction may change it (`admin set-password`, `POST /v1/auth/password`) or disable the user. The session
    must be opened under a lock on the actor row, checking that the hash is still the verified one and the user is enabled; otherwise 401 and no session."""
    def hook_derive(self, then):
        """After the FIRST derivation of the login (the password is verified) `then()` runs on the same thread: the other writer commits between the check and the session."""
        real, fired = passwords._derive, []

        def derive(password, salt, params):
            digest = real(password, salt, params)
            if not fired:
                fired.append(1)
                then()
            return digest
        return patch.object(passwords, '_derive', derive)

    def sessions(self):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute("SELECT count(*) FROM memory.web_sessions WHERE actor_id=(SELECT id FROM memory.actors WHERE username='ana')").fetchone()[0]

    def test_set_password_during_the_derivation_leaves_no_session(self):
        for rehash in (False, True):
            with self.subTest(rehash=rehash):
                self.set_hash(pw.old_hash() if rehash else passwords.hash_password(pw.PASSWORD))
                with self.hook_derive(lambda: self.store.set_password('ana', NEW)), self.assertRaises(Unauthorized):
                    self.auth.login('ana', pw.PASSWORD, '192.0.2.80')
                self.assertEqual(self.sessions(), 0)
                self.assertTrue(passwords.verify_password(NEW, self.stored_hash()), 'the hash of the writer stays (the rehash did not overwrite it)')

    def test_change_password_during_the_derivation_leaves_no_session_and_keeps_the_one_that_changed_it(self):
        for rehash in (False, True):
            with self.subTest(rehash=rehash):
                self.set_hash(passwords.hash_password(pw.PASSWORD))
                first = self.auth.login('ana', pw.PASSWORD, '192.0.2.81')['actor']
                if rehash:
                    self.set_hash(pw.old_hash())
                with self.hook_derive(lambda: self.store.change_password(first, pw.PASSWORD, NEW, '192.0.2.82')), self.assertRaises(Unauthorized):
                    self.auth.login('ana', pw.PASSWORD, '192.0.2.83')
                self.assertEqual(self.sessions(), 1, 'only the session that changed it')
                self.assertTrue(passwords.verify_password(NEW, self.stored_hash()))
                with self.psycopg.connect(self.dsn) as c:
                    c.execute("DELETE FROM memory.web_sessions WHERE actor_id=(SELECT id FROM memory.actors WHERE username='ana')")
                self.set_hash(passwords.hash_password(pw.PASSWORD))

    def test_a_user_disabled_during_the_derivation_gets_no_session(self):
        def disable():
            with self.psycopg.connect(self.dsn) as c:
                c.execute("UPDATE memory.actors SET disabled=true WHERE username='ana'")
        with self.hook_derive(disable), self.assertRaises(Unauthorized):
            self.auth.login('ana', pw.PASSWORD, '192.0.2.84')
        self.assertEqual(self.sessions(), 0)

    def someone_waits_for_a_lock(self, observer):
        return observer.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()").fetchone()[0] > 0

    def uncommitted_writer(self, statement, params=()):
        """A writer whose transaction is OPEN (uncommitted) while the login reaches the insert of its session: the login must wait for it, then see what it wrote."""
        import threading
        import time
        writer = self.psycopg.connect(self.dsn)
        self.addCleanup(writer.close)
        writer.execute(statement, params)  # the transaction stays open
        observer = self.psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(observer.close)
        outcome = {}

        def login():
            try:
                outcome['session'] = self.auth.login('ana', pw.PASSWORD, '192.0.2.85')
            except BaseException as exc:  # reported below
                outcome['error'] = exc
        thread = threading.Thread(target=login)
        thread.start()
        deadline = time.monotonic() + 60
        while thread.is_alive() and not self.someone_waits_for_a_lock(observer) and time.monotonic() < deadline:
            pass  # no sleep: each pass is a round trip to the database
        waited = self.someone_waits_for_a_lock(observer)
        writer.commit()
        thread.join(60)
        self.assertFalse(thread.is_alive())
        self.assertTrue(waited, 'the login did not wait for the transaction of the writer (no lock on the actor row)')
        return outcome

    def test_a_writer_that_has_not_committed_makes_the_login_wait_and_then_refuses_it(self):
        other = pw.old_hash('somebody-else-789', pw.OLD)
        for label, rehash, statement, params in (('new hash', False, 'UPDATE memory.actors SET password_hash=%s WHERE username=%s', (other, 'ana')),
                                                  ('new hash over an old one', True, 'UPDATE memory.actors SET password_hash=%s WHERE username=%s', (other, 'ana')),
                                                  ('disabled', False, 'UPDATE memory.actors SET disabled=true WHERE username=%s', ('ana',))):
            with self.subTest(label):
                self.set_hash(pw.old_hash() if rehash else passwords.hash_password(pw.PASSWORD))
                with self.psycopg.connect(self.dsn, autocommit=True) as c:
                    c.execute("UPDATE memory.actors SET disabled=false WHERE username='ana'")
                outcome = self.uncommitted_writer(statement, params)
                self.assertIsInstance(outcome.get('error'), Unauthorized, outcome)
                self.assertEqual(self.sessions(), 0)
                if label != 'disabled':
                    self.assertEqual(self.stored_hash(), other, 'the hash of the writer was not overwritten')


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
