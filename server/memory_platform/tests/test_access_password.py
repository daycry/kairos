"""CA-01 (T-09): `POST /v1/auth/password` and `store_access.py`, the one door of the changes of access.

The oracle of A-01: with two sessions open, changing the password from one closes the other on its next request, keeps the first, keeps the keys, and leaves an audit event.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import passwords
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import MemoryError, Unauthorized
from memory_platform.store_access import password_changes_left
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
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts WHERE username=%s AND client_ip=%s', 'ana', 'testclient'), 1, 'the wrong current password (the correct login of the fixture is not a failure, T-26)')
        self.assertEqual(self.count('SELECT count(*) FROM memory.login_attempts'), before + 1)
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='password.changed'"), 0)
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.71')['actor']['username'], 'ana', 'the old password still works')
        self.assertEqual(client.get('/v1/auth/me').status_code, 200)

    def test_ten_wrong_currents_block_the_ip_with_429_before_any_derivation(self):
        client, headers = self.session()
        for _ in range(10):  # only failures count (T-26): the correct login of the fixture is not one of them
            self.assertEqual(self.change(client, headers, current='not-the-password-999').status_code, 403)
        with pw.Derivations() as spy:
            blocked = self.change(client, headers)  # even the right one: the IP is blocked
        self.assertEqual((blocked.status_code, blocked.json()['error']['code'], spy.calls), (429, 'rate_limited', []))
        seconds = int(blocked.headers['Retry-After'])  # DC-2: the one constructor of the 429 (review of phase 2, attempt 2, gap 6)
        self.assertTrue(1 <= seconds <= 900, seconds)
        self.assertEqual(blocked.json()['error'], {'code': 'rate_limited', 'message': f'Rate limit exceeded [code=rate_limited retry_after={seconds}]', 'retry_after': seconds})

    def test_a_new_password_under_twelve_characters_is_422_and_derives_nothing(self):
        client, headers = self.session()
        with pw.Derivations() as spy:
            short = self.change(client, headers, new='short')
        self.assertEqual((short.status_code, short.json()['error']['code'], spy.calls), (422, 'invalid_password', []))
        self.assertEqual(self.count("SELECT count(*) FROM memory.login_attempts WHERE username='ana'"), 0, 'nothing: the correct login of the fixture is not a failure (T-26)')

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
        seconds = int(blocked.headers['Retry-After'])  # DC-2: the one constructor of the 429; the oldest of the five changes leaves the window in about 15 minutes
        self.assertTrue(880 <= seconds <= 900, seconds)
        self.assertEqual(blocked.json()['error'], {'code': 'too_many_attempts', 'message': f'Too many password changes [code=too_many_attempts retry_after={seconds}]', 'retry_after': seconds})
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

    def test_the_last_transaction_recounts_the_changes_so_two_requests_at_once_cannot_pass_the_limit(self):
        """Both requests pass the first count (four changes); the other one commits its change (the fifth) while this one derives: the count under the lock of the row refuses this one."""
        client, headers = self.session()
        ana = self.count("SELECT id FROM memory.actors WHERE username='ana'")
        with self.psycopg.connect(self.dsn) as c:
            for _ in range(4):
                c.execute("INSERT INTO memory.audit_events(actor_id,action) VALUES(%s,'password.changed')", (ana,))
        real = passwords.verify_password

        def another_change_lands(password, encoded):
            result = real(password, encoded)
            with self.psycopg.connect(self.dsn) as c:
                c.execute("INSERT INTO memory.audit_events(actor_id,action) VALUES(%s,'password.changed')", (ana,))
            return result
        with patch('memory_platform.store_access.passwords.verify_password', another_change_lands):
            refused = self.change(client, headers)
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (429, 'too_many_attempts'))
        self.assertTrue(passwords.verify_password(pw.PASSWORD, self.stored_hash()), 'nothing changed')

    def test_the_last_transaction_waits_for_a_change_that_has_not_committed_and_then_recounts(self):
        """The lock of the row: another request holds it with its fifth change not yet committed; this one waits for it (it is seen waiting) and, once it commits, the recount refuses it."""
        import threading
        import time
        client, headers = self.session()
        ana = self.count("SELECT id FROM memory.actors WHERE username='ana'")
        with self.psycopg.connect(self.dsn) as c:
            for _ in range(4):
                c.execute("INSERT INTO memory.audit_events(actor_id,action) VALUES(%s,'password.changed')", (ana,))
        real, seen = passwords.verify_password, {}

        def other_request_holds_the_row(password, encoded):
            result = real(password, encoded)
            other = self.psycopg.connect(self.dsn)
            observer = self.psycopg.connect(self.dsn, autocommit=True)
            other.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR NO KEY UPDATE', (ana,))
            other.execute("INSERT INTO memory.audit_events(actor_id,action) VALUES(%s,'password.changed')", (ana,))  # the fifth, uncommitted

            def commit_when_someone_waits():
                deadline, waited = time.monotonic() + 15, False
                while not waited and time.monotonic() < deadline:  # no sleep: each pass is a round trip
                    waited = observer.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()").fetchone()[0] > 0
                seen['waited'] = waited
                other.commit()
                other.close()
                observer.close()
            seen['thread'] = threading.Thread(target=commit_when_someone_waits)
            seen['thread'].start()
            return result
        with patch('memory_platform.store_access.passwords.verify_password', other_request_holds_the_row):
            refused = self.change(client, headers)
        seen['thread'].join(30)
        self.assertTrue(seen.get('waited'), 'the request did not wait for the transaction that holds the row of the user')
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (429, 'too_many_attempts'))
        self.assertTrue(passwords.verify_password(pw.PASSWORD, self.stored_hash()), 'nothing changed')

    def test_the_429_of_the_failures_is_decided_before_the_slot(self):
        """Gap 8 (DC-5): order = 429, then slot, then scrypt."""
        client, headers = self.session()
        with self.psycopg.connect(self.dsn) as c:
            for _ in range(10):
                c.execute("INSERT INTO memory.login_attempts(username,client_ip) VALUES('someone','testclient')")
        with patch.object(passwords, 'GATE', self.busy_gate()), pw.Derivations() as spy:
            blocked = self.change(client, headers)
        self.assertEqual((blocked.status_code, blocked.json()['error']['code'], spy.calls), (429, 'rate_limited', []))
        self.assertGreaterEqual(int(blocked.headers['Retry-After']), 1)

    def test_the_failures_of_the_user_block_the_change_with_the_plazo_of_the_user(self):
        """DC-5 keeps the user bucket for the change of password (an attacker with a stolen session and many IPs): ten failures of the name from other IPs, the oldest 14 minutes ago."""
        client, headers = self.session()
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.login_attempts(username,client_ip,happened_at) SELECT 'ana','198.51.100.'||g,clock_timestamp()-make_interval(mins => 14) FROM generate_series(1,10) g")
        blocked = self.change(client, headers)
        self.assertEqual((blocked.status_code, blocked.json()['error']['code']), (429, 'rate_limited'))
        self.assertTrue(1 <= int(blocked.headers['Retry-After']) <= 60, blocked.headers['Retry-After'])

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
            with self.psycopg.connect(self.dsn) as c:  # ten failures of the IP (the correct login of the fixture is not one, T-26)
                for _ in range(10):
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

    def test_a_username_taken_between_the_last_check_and_the_insert_is_409_by_the_unique_violation(self):
        """Fix2 of the review of phase 2 (attempt 2, gap 4): the rival lands AFTER the check of the last transaction and BEFORE its INSERT (at `new_id`, the call between both), so only
        the `except UniqueViolation` of `create_user` can turn it into a 409: without it the database error of the creation that lost
        reaches the client as 503 `service_unavailable` (mutant run 2026-11-26)."""
        from memory_platform import store_auth
        real = store_auth.new_id
        landed = []
        created_before = self.audited('user.created')

        def rival_before_the_insert():
            if not landed:
                with self.psycopg.connect(self.dsn) as c:
                    c.execute("INSERT INTO memory.actors(id,username,password_hash) VALUES('u-rival','newbie','!')")
                landed.append(True)
            return real()
        with patch.object(store_auth, 'new_id', rival_before_the_insert), TestClient(self.app, raise_server_exceptions=False) as client:
            refused = client.post('/v1/users', json=self.BODY, headers={'Authorization': 'Bearer ' + self.admin_key['token']})
        self.assertEqual(landed, [True], 'the rival is inserted once, between the check and the insert')
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (409, 'conflict'))
        self.assertEqual(self.users(), 1)
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute("SELECT id FROM memory.actors WHERE username='newbie'").fetchone()[0], 'u-rival', 'the rival stays and nothing of the creation that lost')
        self.assertEqual(self.audited('user.created'), created_before, 'the creation that lost audits nothing')

    def audited(self, action):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute('SELECT count(*) FROM memory.audit_events WHERE action=%s', (action,)).fetchone()[0]


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


class LoginRetryTests(pw.Fixture):
    """Fix2 of the review of phase 2 (attempt 2, gap 3): two correct logins of one user with an old hash at once. The first replaces the hash; the second, which verified against the old one,
    sees the new hash under the lock. It must not answer 401 to a correct password: it closes that transaction, verifies ONCE against the new hash (inside the same slot of the gate) and tries
    once more; if the hash changed again or the password does not verify, 401. The branch that takes `FOR NO KEY UPDATE` (a login that is going to write the hash) has its own test: with a
    `FOR SHARE` for everybody the two logins end up waiting for each other."""
    def setUp(self):
        super().setUp()
        self.observer = self.psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.observer.close)

    def attempts(self):
        return self.observer.execute("SELECT count(*) FROM memory.login_attempts").fetchone()[0]

    def sessions(self):
        return self.observer.execute("SELECT count(*) FROM memory.web_sessions WHERE actor_id=(SELECT id FROM memory.actors WHERE username='ana')").fetchone()[0]

    def someone_waits_for_a_lock(self):
        return self.observer.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()").fetchone()[0] > 0

    def test_two_simultaneous_logins_with_an_old_hash_both_succeed_and_nothing_waits_in_a_circle(self):
        import threading
        import time
        from memory_platform import auth as auth_module, observability
        self.set_hash(pw.old_hash())
        verified, seen_first = threading.Barrier(2), set()
        reached = []
        real_check, real_savepoint = auth_module.check_login, auth_module.savepoint

        def check(password, stored):
            result = real_check(password, stored)
            me = threading.get_ident()
            if me not in seen_first:  # only the first verification of each login waits for the other: both have verified before either takes the lock
                seen_first.add(me)
                verified.wait(60)
            return result

        def savepoint(c):
            # The login is about to write the new hash. A login that holds `FOR NO KEY UPDATE` makes the other wait for the lock, and then goes on; two that hold `FOR SHARE` both arrive here
            # and each waits for the other's share lock to write: PostgreSQL ends that circle with a deadlock error after a second.
            reached.append(1)
            deadline = time.monotonic() + 60
            while len(reached) < 2 and not self.someone_waits_for_a_lock() and time.monotonic() < deadline:
                pass  # no sleep: each pass is a round trip to the database
            return real_savepoint(c)
        outcome = {}

        def login(n):
            try:
                outcome[n] = self.auth.login('ana', pw.PASSWORD, '192.0.2.%d' % (90 + n))
            except BaseException as exc:  # reported below
                outcome[n] = exc
        with patch.object(auth_module, 'check_login', check), patch.object(auth_module, 'savepoint', savepoint), patch.object(observability, 'log_failure') as failed:
            threads = [threading.Thread(target=login, args=(n,)) for n in (1, 2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(120)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual({n: type(v).__name__ for n, v in outcome.items()}, {1: 'dict', 2: 'dict'}, outcome)
        self.assertEqual(self.sessions(), 2)
        self.assertEqual(json.loads(self.stored_hash())['n'], passwords.TARGET[0], 'the hash was replaced by one of the two')
        self.assertEqual([call.args[0] for call in failed.call_args_list if call.args], [], 'the write of the new hash did not fail (no deadlock)')
        self.assertEqual(self.attempts(), 0, 'two correct logins, no failure (T-26: a success removes its own row); the retry of the second is not another attempt')

    def test_the_retry_verifies_once_against_the_new_hash_and_only_once(self):
        """The hash changes again while the retry verifies: 401, no session, and exactly two verifications (the first and the single retry)."""
        from memory_platform import auth as auth_module
        self.set_hash(passwords.hash_password(pw.PASSWORD))
        calls = []
        real_check = auth_module.check_login

        def check(password, stored):
            result = real_check(password, stored)
            calls.append(stored)
            self.set_hash(passwords.hash_password(pw.PASSWORD))  # the same password, a new salt: after the first and after the second verification
            return result
        with patch.object(auth_module, 'check_login', check), self.assertRaises(Unauthorized):
            self.auth.login('ana', pw.PASSWORD, '192.0.2.95')
        self.assertEqual(len(calls), 2, 'the verification and one retry')
        self.assertEqual(self.sessions(), 0)

    def test_a_hash_that_changed_to_another_password_is_401_after_one_more_verification(self):
        """The race of `set-password` of the first review stays closed: the old password does not open a session with the new hash."""
        from memory_platform import auth as auth_module
        self.set_hash(passwords.hash_password(pw.PASSWORD))
        real_check, calls = auth_module.check_login, []

        def check(password, stored):
            calls.append(1)
            result = real_check(password, stored)
            if len(calls) == 1:
                self.store.set_password('ana', NEW)
            return result
        with patch.object(auth_module, 'check_login', check), self.assertRaises(Unauthorized) as raised:
            self.auth.login('ana', pw.PASSWORD, '192.0.2.96')
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual((len(calls), self.sessions()), (2, 0))
        self.assertTrue(passwords.verify_password(NEW, self.stored_hash()))
        self.assertEqual(self.auth.login('ana', NEW, '192.0.2.97')['actor']['username'], 'ana')


class RecentChangesCostTests(pw.Fixture):
    """Fix2 of the review of phase 2 (attempt 2, gap 2): the count of the correct changes of the last 15 minutes must not read `audit_events` whole. It is bounded by the primary key
    (`id` is an identity assigned in the same row as `happened_at`, so both grow together) with no new index: the last `id` older than the window is found by a backward walk of the
    key that stops at the first old row, and only the `id` above it is counted. The tests run the statements the function really issues, with `EXPLAIN (ANALYZE, BUFFERS)`."""
    OLD_ROWS = 200_000

    def fill(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.audit_events(actor_id,action,happened_at) SELECT 'u'||(g%%500), CASE WHEN g%%9=0 THEN 'password.changed' ELSE 'key.created' END, "
                      "clock_timestamp()-interval '3 days'+g*interval '0.2 seconds' FROM generate_series(1,%s) g", (self.OLD_ROWS,))
            c.execute('ANALYZE memory.audit_events')

    def add(self, actor, action, minutes_ago=0):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.audit_events(actor_id,action,happened_at) VALUES(%s,%s,clock_timestamp()-%s*interval '1 minute')", (actor, action, minutes_ago))

    def changes(self, actor_id):
        """(still free?, the statements the function sent). A 429 is `not free`."""
        class Spy:
            def __init__(self, c):
                self.c, self.seen = c, []

            def execute(self, sql, params=()):
                self.seen.append((sql, params))
                return self.c.execute(sql, params)
        with self.store.transaction() as c:
            spy = Spy(c)
            try:
                password_changes_left(spy, {'id': actor_id})
                return True, spy.seen
            except MemoryError as exc:
                self.assertEqual((exc.status_code, exc.code), (429, 'too_many_attempts'))
                return False, spy.seen

    def test_the_limit_counts_the_window_of_the_user_and_the_action_only(self):
        from memory_platform.store_access import PASSWORD_CHANGES_PER_WINDOW
        for minutes in (40, 16):
            self.add('u-a', 'password.changed', minutes)   # outside the window: never counted
        for n in range(PASSWORD_CHANGES_PER_WINDOW):
            self.add('u-b', 'password.changed', 0)         # another user
            self.add('u-a', 'key.created', 0)              # another action
        for n in range(PASSWORD_CHANGES_PER_WINDOW - 1):
            self.add('u-a', 'password.changed', 14 - n)    # four inside
        self.assertTrue(self.changes('u-a')[0], 'four inside the window, the rest outside, another user or another action: still free')
        self.assertFalse(self.changes('u-b')[0], 'five of its own')
        self.assertTrue(self.changes('u-nobody')[0], 'a table with no event of the user')
        self.add('u-a', 'password.changed', 0)
        self.assertFalse(self.changes('u-a')[0], 'the fifth inside the window')

    def test_an_empty_table_and_one_with_nothing_old_are_free(self):
        self.assertTrue(self.changes('u-a')[0])
        self.add('u-a', 'password.changed', 1)
        self.assertTrue(self.changes('u-a')[0], 'every row is inside the window: there is no old id to bound by')

    def test_the_statements_do_not_grow_with_the_table(self):
        self.fill()
        self.add('u7', 'password.changed', 14)
        self.add('u7', 'password.changed', 0)
        free, seen = self.changes('u7')
        self.assertTrue(free)
        self.assertGreaterEqual(len(seen), 1)
        total = 0

        def nodes(node):
            yield node
            for child in node.get('Plans', ()):
                yield from nodes(child)
        with self.psycopg.connect(self.dsn) as c:
            for sql, params in seen:
                plan = c.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql, params).fetchone()[0][0]['Plan']
                for node in nodes(plan):
                    self.assertNotIn(node['Node Type'], ('Seq Scan', 'Parallel Seq Scan'), 'the table is walked whole: ' + sql)
                total += plan['Shared Hit Blocks'] + plan['Shared Read Blocks']
        self.assertLess(total, 100, 'read %d buffers: walking %d rows takes about %d, a bounded count takes a handful (8 measured)' % (total, self.OLD_ROWS, self.OLD_ROWS // 125))

    def test_both_counts_of_change_password_are_this_function(self):
        import ast
        from memory_platform import store_access
        tree = ast.parse(Path(store_access.__file__).read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'change_password')
        calls = [n for n in ast.walk(method) if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'password_changes_left']
        self.assertEqual(len(calls), 2, 'the one before the slot and the one of the last transaction')
        self.assertFalse([n for n in ast.walk(method) if isinstance(n, ast.Name) and n.id == 'CHANGES_WAIT'], 'no count of its own')


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
