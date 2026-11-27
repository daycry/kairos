"""CA-06 (T-19): an optional expiry for a key, shown in the list and in `/v1/auth/me`, and the last use of a key written at most once a minute.

A key created without `expires_at` never expires (P-03); one created with it gets 401 once it passes (the row is dated back, no sleep); an expiry in the past is 422, decided
after the caller is authorized. `last_used_at` is written by the authentication of a key in a short transaction of its own, with a short `lock_timeout`: a hundred requests
in a row write it once (injected clock), and a `FOR SHARE` held on the row of the key does not make the request fail (the write is deferred to the next request).
"""
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import auth as auth_module
from memory_platform.app import create_app
from memory_platform.auth import Auth, token_hash
from memory_platform.config import Settings
from memory_platform.store import Store
from memory_platform.tests import test_passwords as pw
from memory_platform.tests.test_access_users import ORIGIN, UsersFixture

KEY_FIELDS = {'id', 'name', 'prefix', 'expires_at'}
# Every update of `last_used_at` that moves it forward is one write (a row dated back by the test is not)
COUNT_WRITES = """
CREATE TABLE public.key_touches(n serial PRIMARY KEY, key_id text NOT NULL);
CREATE FUNCTION public.count_key_touch() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO public.key_touches(key_id) VALUES (NEW.id); RETURN NEW; END $$;
CREATE TRIGGER count_key_touch AFTER UPDATE OF last_used_at ON memory.api_keys FOR EACH ROW
    WHEN (OLD.last_used_at IS NULL OR NEW.last_used_at > OLD.last_used_at) EXECUTE FUNCTION public.count_key_touch();
"""


class KeysFixture(UsersFixture):
    def bearer(self, token):
        return {'Authorization': 'Bearer ' + token}

    def key_id(self, token):
        return self.observer.execute('SELECT id FROM memory.api_keys WHERE token_hash=%s', (token_hash(token),)).fetchone()[0]

    def admin_session(self):
        """bea, administrator of p1, signed in: she may create and list the keys of p1."""
        return self.session()


class ExpiryTests(KeysFixture):
    def test_a_key_without_expiry_never_expires_and_one_with_expiry_gets_401_once_it_passes(self):
        client, headers = self.admin_session()
        plain = client.post('/v1/keys', json={'name': 'plain', 'project_ids': ['p1'], 'scopes': ['read']}, headers=headers)
        self.assertEqual(plain.status_code, 200, plain.text)
        self.assertIsNone(plain.json()['expires_at'])
        self.assertIsNone(self.count('SELECT expires_at FROM memory.api_keys WHERE id=%s', plain.json()['id']), 'without expiry the key does not expire (P-03)')
        dated = client.post('/v1/keys', json={'name': 'dated', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2999-01-01T00:00:00Z'}, headers=headers)
        self.assertEqual(dated.status_code, 200, dated.text)
        self.assertTrue(dated.json()['expires_at'].startswith('2999-01-01T00:00:00'), dated.json())
        self.assertEqual([self.with_key(plain.json()['token']), self.with_key(dated.json()['token'])], [200, 200])
        self.observer.execute("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (dated.json()['id'],))
        self.assertEqual(self.with_key(dated.json()['token']), 401, 'the key with expiry gets 401 once it passes')
        self.assertEqual(self.with_key(plain.json()['token']), 200)

    def test_an_expiry_in_the_past_is_422_and_creates_nothing(self):
        client, headers = self.admin_session()
        for value in ('2000-01-01T00:00:00Z', '2000-01-01T00:00:00+02:00'):
            with self.subTest(expires_at=value):
                refused = client.post('/v1/keys', json={'name': 'past', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': value}, headers=headers)
                self.assertEqual((refused.status_code, refused.json()['error']['code']), (422, 'invalid_key_expiry'), refused.text)
        self.assertEqual(self.count("SELECT count(*) FROM memory.api_keys WHERE name='past'"), 0)
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='key.created'"), 0)

    def test_authorization_comes_before_the_422_of_the_expiry(self):
        reader, headers = self.session('ana')  # read on p1, no admin: she may not issue keys
        refused = reader.post('/v1/keys', json={'name': 'past', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2000-01-01T00:00:00Z'}, headers=headers)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_the_list_shows_the_expiry_and_the_last_use_of_each_key(self):
        client, headers = self.admin_session()
        token = client.post('/v1/keys', json={'name': 'listed', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2999-01-01T00:00:00Z'}, headers=headers).json()['token']
        before = {item['name']: item for item in client.get('/v1/keys').json()['items']}
        self.assertIn('expires_at', before['listed'])
        self.assertTrue(before['listed']['expires_at'].startswith('2999-01-01'))
        self.assertIsNone(before['listed']['last_used_at'], 'a key never used has no last use')
        self.assertEqual(self.with_key(token), 200)
        after = {item['name']: item for item in client.get('/v1/keys').json()['items']}
        self.assertIsNotNone(after['listed']['last_used_at'], 'the request with the key is its last use')
        self.assertNotIn(token, client.get('/v1/keys').text)

    def test_me_shows_the_key_of_a_bearer_and_no_key_for_a_session(self):
        client, headers = self.admin_session()
        created = client.post('/v1/keys', json={'name': 'mine', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2999-01-01T00:00:00Z'}, headers=headers).json()
        me = self.client().get('/v1/auth/me', headers=self.bearer(created['token']))
        self.assertEqual(me.status_code, 200, me.text)
        key = me.json()['key']
        self.assertEqual(set(key), KEY_FIELDS)
        self.assertEqual((key['id'], key['name'], key['prefix']), (created['id'], 'mine', created['token'][:10]))
        self.assertTrue(key['expires_at'].startswith('2999-01-01'))
        self.assertNotIn(created['token'], me.text)
        plain = client.post('/v1/keys', json={'name': 'plain', 'project_ids': ['p1'], 'scopes': ['read']}, headers=headers).json()
        self.assertIsNone(self.client().get('/v1/auth/me', headers=self.bearer(plain['token'])).json()['key']['expires_at'])
        self.assertNotIn('key', client.get('/v1/auth/me').json(), 'a session has no key')


class KeysOfTheEarlierReleaseTests(unittest.TestCase):
    """The keys made before version 13 keep «no expiry» after the migration and show it in the list and in `/v1/auth/me`."""

    def setUp(self):
        from memory_platform.tests import test_migrations_additive as migrations
        self.case = migrations.AccessSchemaTests('test_upgrade_from_release_041_keeps_users_sessions_and_keys_valid')
        self.case.setUp()  # a database of its own, as release 0.4.1 left it
        self.addCleanup(self.case.doCleanups)
        self.case.seed_release_041()  # with key `k1` (token `mp_old-key`), no expiry, of `ana`, read on p1
        self.store = Store(self.case.dsn)
        self.store.migrate()

    def test_an_old_key_keeps_no_expiry_and_says_so(self):
        with TestClient(create_app(Settings(self.case.dsn, mount_mcp=False), store=self.store, auth=Auth(self.store))) as client:
            me = client.get('/v1/auth/me', headers={'Authorization': 'Bearer mp_old-key'})
            self.assertEqual(me.status_code, 200, me.text)
            self.assertEqual(me.json()['key'], {'id': 'k1', 'name': 'old', 'prefix': 'mp_old', 'expires_at': None})
        with self.case.psycopg.connect(self.case.dsn) as c:
            self.assertEqual(c.execute("SELECT expires_at, last_used_at IS NOT NULL FROM memory.api_keys WHERE id='k1'").fetchone(), (None, True))


class LastUsedTests(KeysFixture):
    def setUp(self):
        super().setUp()
        self.observer.execute(COUNT_WRITES)
        self.now = [1000.0]
        self.auth = Auth(self.store, [ORIGIN], clock=lambda: self.now[0])
        self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        self.token = self.key_of()
        self.kid = self.key_id(self.token)

    def writes(self):
        return self.count('SELECT count(*) FROM public.key_touches WHERE key_id=%s', self.kid)

    def attempts(self):
        """A spy on the transactions of the write: the only `invalidate_auth` of `auth.py` that a request with a key makes is the one at the end of that transaction."""
        seen, real = [], auth_module.invalidate_auth

        def spy(c):
            seen.append(c.execute('SHOW lock_timeout').fetchone()['lock_timeout'])
            return real(c)
        return seen, patch.object(auth_module, 'invalidate_auth', spy)

    def test_a_hundred_requests_in_a_row_write_the_last_use_once(self):
        client = self.client()
        seen, spying = self.attempts()
        with spying:
            for _ in range(100):
                self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 1)
        self.assertEqual(seen, [auth_module.LAST_USED_LOCK_TIMEOUT], 'one short transaction, not one per request: the clock of the process keeps the others away from the database')
        self.now[0] += 59
        self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 1, 'within the minute nothing more is written')
        self.now[0] += 2
        self.observer.execute("UPDATE memory.api_keys SET last_used_at=last_used_at-interval '2 minutes' WHERE id=%s", (self.kid,))
        self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 2, 'after a minute the next request writes it again')

    def test_the_write_of_another_process_within_the_minute_is_not_repeated(self):
        # the database guard: a row written less than a minute ago (by another process, or another Auth) is left alone
        self.observer.execute('UPDATE memory.api_keys SET last_used_at=clock_timestamp() WHERE id=%s', (self.kid,))
        before = self.writes()
        self.assertEqual(self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), before)

    def test_a_share_lock_on_the_row_of_the_key_does_not_fail_the_request_and_the_write_is_deferred(self):
        holder = self.psycopg.connect(self.dsn)  # a transaction that holds FOR SHARE on the row, as `extended_store.py` and `corpus_answers.py` do
        self.addCleanup(holder.close)
        holder.execute('SELECT 1 FROM memory.api_keys WHERE id=%s FOR SHARE', (self.kid,))
        out = {}

        def request():
            out['status'] = self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code
        thread = threading.Thread(target=request)
        thread.start()
        thread.join(20)
        stuck = thread.is_alive()
        holder.rollback()  # whatever happened, the lock goes away and the thread ends
        thread.join(20)
        self.assertFalse(stuck, 'the request waited for the lock instead of giving up on the write')
        self.assertEqual(out.get('status'), 200)
        self.assertEqual(self.writes(), 0, 'the write did not get in')
        self.assertEqual(self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 1, 'the next request writes it')

    def test_the_write_runs_in_a_transaction_of_its_own_with_a_short_lock_timeout(self):
        seen, spying = self.attempts()
        with spying:
            self.assertEqual(self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(seen, [auth_module.LAST_USED_LOCK_TIMEOUT], 'the write runs with its own short lock_timeout')
        self.assertEqual(self.writes(), 1)


if __name__ == '__main__':
    unittest.main()
