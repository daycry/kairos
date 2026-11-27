"""CA-06 (T-19) and CA-07 (T-20): an optional expiry for a key, shown in the list and in `/v1/auth/me`, and the last use of a key written at most once a minute.

A key created without `expires_at` never expires (P-03); one created with it gets 401 once it passes (the row is dated back, no sleep); an expiry in the past is 422, decided
after the caller is authorized. `last_used_at` is written by the authentication of a key in a short transaction of its own, with a short `lock_timeout`: a hundred requests
in a row write it once (injected clock), and a `FOR SHARE` held on the row of the key does not make the request fail (the write is deferred to the next request).
The rotation of a key (T-20) is at the end: `RotationTests`.
"""
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import auth as auth_module
from memory_platform.app import create_app
from memory_platform.auth import LAST_USED_EVERY, Auth, token_hash
from memory_platform.config import Settings
from memory_platform.errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from memory_platform.store import Store
from memory_platform.store_pool import close_pool
from memory_platform.tests import test_passwords as pw
from memory_platform.tests.test_access_users import ORIGIN, UsersFixture
from memory_platform.tests.test_store_pool import pool_store

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
        for value in ('2000-01-01T00:00:00Z', '9999-12-31T23:00:00-05:00'):
            with self.subTest(expires_at=value):
                refused = reader.post('/v1/keys', json={'name': 'past', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': value}, headers=headers)
                self.assertEqual(refused.status_code, 403, refused.text)

    def test_an_expiry_after_the_last_one_a_key_may_have_is_422_and_one_on_it_is_kept(self):
        # fix1 of the review of phase 4, gap 5: an expiry past the year 9999 in UTC was a 503 (the driver cannot load it); it is a 422 of the request, and nothing is created
        client, headers = self.admin_session()
        for value in ('9999-12-31T23:00:00-05:00', '9999-12-31T00:00:01Z'):
            with self.subTest(expires_at=value):
                refused = client.post('/v1/keys', json={'name': 'far', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': value}, headers=headers)
                self.assertEqual((refused.status_code, refused.json()['error']['code']), (422, 'invalid_key_expiry'), refused.text)
        self.assertEqual(self.count("SELECT count(*) FROM memory.api_keys WHERE name='far'"), 0)
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='key.created'"), 0)
        kept = client.post('/v1/keys', json={'name': 'far', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '9999-12-31T00:00:00Z'}, headers=headers)
        self.assertEqual(kept.status_code, 200, kept.text)
        self.assertTrue(kept.json()['expires_at'].startswith('9999-12-31T00:00:00'), kept.json())

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
        self.now[0] += LAST_USED_EVERY  # a write that did not get in is tried again a minute later (fix1 of the review of phase 4, gap 8)
        self.assertEqual(self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 1, 'the next request after the minute writes it')

    def test_a_write_that_did_not_get_in_is_not_tried_again_within_the_minute_and_warns_once(self):
        # fix1 of the review of phase 4, gap 8: the clock of the process moves on every attempt, not only on a write that got in; else every request of the key tries again and warns
        holder = self.psycopg.connect(self.dsn)
        self.addCleanup(holder.close)
        holder.execute('SELECT 1 FROM memory.api_keys WHERE id=%s FOR SHARE', (self.kid,))
        client, warnings = self.client(), []
        real = auth_module.observability.log_failure

        def spy(event, exc, level='error', **fields):
            warnings.append((event, type(exc).__name__))
            return real(event, exc, level, **fields)
        with patch.object(auth_module.observability, 'log_failure', spy):
            for _ in range(5):
                self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
            holder.rollback()  # the lock goes away: within the same minute nothing is tried again
            self.now[0] += LAST_USED_EVERY - 1
            self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(warnings, [('key_last_used_deferred', 'LockNotAvailable')], 'one attempt and one warning in the minute, not one per request')
        self.assertEqual(self.writes(), 0)
        self.now[0] += 1
        self.assertEqual(client.get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(self.writes(), 1, 'a minute after the attempt the write gets in')

    def test_with_the_pool_full_the_write_waits_for_a_connection_only_a_short_margin(self):
        # fix1 of the review of phase 4, gap 8: the write is not worth a request waiting the whole MEMORY_POOL_TIMEOUT (5 s) for a connection; it gives up after LAST_USED_POOL_WAIT
        pooled = pool_store(self.dsn, minimum=1, maximum=1, timeout=5.0)
        self.addCleanup(close_pool, pooled)
        auth = Auth(pooled, [ORIGIN], clock=lambda: self.now[0])
        token = self.key_of()
        kid = self.key_id(token)
        real, calls, got, release, warnings = pooled.transaction, [], threading.Event(), threading.Event(), []

        def hold():
            with pooled.pool.connection():
                got.set()
                release.wait(30)
        holder = threading.Thread(target=hold)

        @contextmanager
        def transaction(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:  # the write of the last use: the only connection of the pool is taken by somebody else first
                holder.start()
                self.assertTrue(got.wait(30))
            with real(*args, **kwargs) as c:
                yield c
        real_log = auth_module.observability.log_failure

        def spy(event, exc, level='error', **fields):
            warnings.append((event, type(exc).__name__))
            return real_log(event, exc, level, **fields)
        try:
            with patch.object(pooled, 'transaction', transaction), patch.object(auth_module.observability, 'log_failure', spy):
                started = time.monotonic()
                actor = auth.authenticate_bearer(token)
                took = time.monotonic() - started
        finally:
            release.set()
            if holder.is_alive():
                holder.join(30)
        self.assertEqual(actor['key_id'], kid, 'the request goes on')
        self.assertLess(took, 2.0, 'the write waited %.2f s for a connection (MEMORY_POOL_TIMEOUT is 5 s)' % took)
        self.assertEqual(warnings, [('key_last_used_deferred', 'StoreBusy')])
        self.assertIsNone(self.count('SELECT last_used_at FROM memory.api_keys WHERE id=%s', kid))

    def test_the_write_runs_in_a_transaction_of_its_own_with_a_short_lock_timeout(self):
        seen, spying = self.attempts()
        with spying:
            self.assertEqual(self.client().get('/v1/projects', headers=self.bearer(self.token)).status_code, 200)
        self.assertEqual(seen, [auth_module.LAST_USED_LOCK_TIMEOUT], 'the write runs with its own short lock_timeout')
        self.assertEqual(self.writes(), 1)


class RotationTests(KeysFixture):
    """CA-07 (T-20): `POST /v1/keys/{id}/rotate` issues a new key with the name, projects, permissions and OWNER of the old one, shown once; the old one keeps working until the
    end of the grace (24 h by default, 0 = at once) and keeps `replaced_by`. A revoked, expired or already rotated key is 409 and nothing is issued, also with two rotations at once."""

    def setUp(self):
        super().setUp()
        self.bea_client, self.headers = self.admin_session()
        made = self.bea_client.post('/v1/keys', json={'name': 'machine', 'project_ids': ['p1'], 'scopes': ['read', 'write']}, headers=self.headers)
        self.assertEqual(made.status_code, 200, made.text)
        self.old = made.json()

    def rotate(self, key_id=None, body=None, client=None, headers=None):
        return (client or self.bea_client).post('/v1/keys/%s/rotate' % (key_id or self.old['id']), headers=self.headers if headers is None else headers,
                                                **({} if body is None else {'json': body}))

    def keys(self):
        return self.count('SELECT count(*) FROM memory.api_keys')

    def row(self, key_id, columns='actor_id,name,prefix,project_ids,scopes,expires_at,replaced_by,revoked_at'):
        return self.observer.execute('SELECT %s FROM memory.api_keys WHERE id=%%s' % columns, (key_id,)).fetchone()

    def seconds_left(self, key_id):
        return self.count('SELECT extract(epoch FROM expires_at-clock_timestamp()) FROM memory.api_keys WHERE id=%s', key_id)

    def test_the_new_key_has_the_name_projects_permissions_and_owner_of_the_old_one_and_is_shown_once(self):
        done = self.rotate()
        self.assertEqual(done.status_code, 200, done.text)
        new = done.json()
        self.assertEqual(set(new), {'id', 'name', 'token', 'project_ids', 'scopes', 'expires_at', 'previous_id', 'previous_expires_at'})
        self.assertEqual((new['name'], new['project_ids'], sorted(new['scopes']), new['expires_at'], new['previous_id']), ('machine', ['p1'], ['read', 'write'], None, self.old['id']))
        self.assertNotEqual(new['id'], self.old['id'])
        self.assertNotEqual(new['token'], self.old['token'])
        owner, name, prefix, projects, scopes, expires, replaced, revoked = self.row(new['id'])
        self.assertEqual((owner, name, prefix, projects, sorted(scopes), expires, replaced, revoked), (self.bea, 'machine', new['token'][:10], ['p1'], ['read', 'write'], None, None, None))
        self.assertEqual(self.row(self.old['id'], 'actor_id,replaced_by'), (self.bea, new['id']), 'the old key keeps its successor')
        self.assertEqual([self.with_key(new['token']), self.with_key(self.old['token'])], [200, 200], 'both work during the grace')
        self.assertNotIn(new['token'], self.bea_client.get('/v1/keys').text, 'the new key is only in the answer of the rotation')
        events = self.observer.execute("SELECT actor_id,resource_id FROM memory.audit_events WHERE action='key.rotated'").fetchall()
        self.assertEqual(events, [(self.bea, '{"key":"%s","replaced_by":"%s"}' % (self.old['id'], new['id']))])
        stored = ' '.join(str(value) for row in self.observer.execute('SELECT * FROM memory.audit_events').fetchall() for value in row)
        self.assertNotIn(new['token'], stored)
        self.assertNotIn(token_hash(new['token']), stored)

    def test_a_key_rotated_by_the_global_administrator_keeps_its_owner(self):
        # the answer to «does the rotated key keep the actor_id of the old one?»: yes, whoever rotates it (here the global administrator, another actor)
        root, headers = self.root()
        done = self.rotate(client=root, headers=headers)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(self.row(done.json()['id'], 'actor_id')[0], self.bea)
        root_id = self.count("SELECT id FROM memory.actors WHERE username='root-user'")
        self.assertEqual(self.count("SELECT actor_id FROM memory.audit_events WHERE action='key.rotated'"), root_id, 'the event names who rotated it')
        me = self.client().get('/v1/auth/me', headers=self.bearer(done.json()['token'])).json()
        self.assertEqual(me['actor']['id'], self.bea)

    def test_the_old_key_works_until_the_end_of_the_grace_and_then_gets_401(self):
        done = self.rotate()
        self.assertEqual(done.status_code, 200, done.text)
        left = self.seconds_left(self.old['id'])
        self.assertTrue(86400 - 120 < left <= 86400, left)
        self.assertEqual(self.with_key(self.old['token']), 200)
        self.observer.execute("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (self.old['id'],))  # the end of the grace
        self.assertEqual([self.with_key(self.old['token']), self.with_key(done.json()['token'])], [401, 200])

    def test_with_a_grace_of_zero_the_old_key_stops_on_the_next_request(self):
        done = self.rotate(body={'grace_seconds': 0})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual([self.with_key(self.old['token']), self.with_key(done.json()['token'])], [401, 200])

    def test_the_grace_never_extends_the_old_key_and_the_new_one_keeps_the_lifetime(self):
        made = self.bea_client.post('/v1/keys', json={'name': 'dated', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2999-01-01T00:00:00Z'}, headers=self.headers).json()
        # made 5 days ago, expires in an hour: its lifetime is 5 days and an hour, and it has less left than the grace of 24 h
        self.observer.execute("UPDATE memory.api_keys SET created_at=clock_timestamp()-interval '5 days', expires_at=clock_timestamp()+interval '1 hour' WHERE id=%s", (made['id'],))
        done = self.rotate(made['id'])
        self.assertEqual(done.status_code, 200, done.text)
        self.assertLessEqual(self.seconds_left(made['id']), 3600, 'the grace does not extend the old key')
        lifetime = self.seconds_left(done.json()['id'])
        self.assertTrue(5 * 86400 + 3600 - 120 < lifetime <= 5 * 86400 + 3600, 'the new key lasts what the old one was given: %s' % lifetime)
        self.assertIsNotNone(done.json()['expires_at'])

    def test_a_revoked_an_expired_and_an_already_rotated_key_are_409_and_issue_nothing(self):
        revoked = self.bea_client.post('/v1/keys', json={'name': 'revoked', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
        self.assertEqual(self.bea_client.delete('/v1/keys/' + revoked['id'], headers=self.headers).status_code, 200)
        expired = self.bea_client.post('/v1/keys', json={'name': 'expired', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
        self.observer.execute("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (expired['id'],))
        self.assertEqual(self.rotate().status_code, 200)
        before = self.keys()
        for key_id in (revoked['id'], expired['id'], self.old['id']):
            with self.subTest(key=key_id):
                refused = self.rotate(key_id)
                self.assertEqual((refused.status_code, refused.json()['error']['code']), (409, 'conflict'), refused.text)
        self.assertEqual(self.keys(), before, 'no key issued')
        self.assertEqual(self.count("SELECT count(*) FROM memory.audit_events WHERE action='key.rotated'"), 1)

    def test_two_rotations_at_once_issue_one_key(self):
        actor = self.auth.login('bea', pw.PASSWORD, '198.51.100.90')['actor']
        before = self.keys()
        waited, first, second = self.run_pair(lambda: self.store.rotate_key(actor, self.old['id']), lambda: self.store.rotate_key(actor, self.old['id']), 'key.rotated')
        self.assertTrue(waited, 'the second rotation did not wait for the first')
        self.assertIsInstance(first, dict, first)
        self.assertIsInstance(second, Conflict, second)
        self.assertEqual(self.keys(), before + 1)

    def test_a_revocation_of_every_key_of_the_owner_that_comes_after_the_rotation_takes_the_new_key_too(self):
        # the rotation locks the row of the OWNER: `admin set-password --revoke-keys` (which updates it) waits for the rotation and then revokes the key it issued
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.91')['actor']
        waited, rotated, reset = self.run_pair(lambda: self.store.rotate_key(root, self.old['id']),
                                               lambda: self.store.set_password('bea', 'another-password-456', revoke_keys=True), 'key.rotated')
        self.assertTrue(waited, 'set-password did not wait for the rotation')
        self.assertIsInstance(rotated, dict, rotated)
        self.assertIsInstance(reset, dict, reset)
        self.assertIsNotNone(self.row(rotated['id'], 'revoked_at')[0], 'the key issued by the rotation is revoked with the others')
        self.assertEqual(self.with_key(rotated['token']), 401)

    def test_a_rotation_that_comes_after_the_revocation_of_every_key_of_the_owner_issues_nothing(self):
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.92')['actor']
        before = self.keys()
        waited, reset, rotated = self.run_pair(lambda: self.store.set_password('bea', 'another-password-456', revoke_keys=True),
                                               lambda: self.store.rotate_key(root, self.old['id']), 'keys.revoked')
        self.assertTrue(waited, 'the rotation did not wait for set-password')
        self.assertIsInstance(reset, dict, reset)
        self.assertIsInstance(rotated, Conflict, rotated)
        self.assertEqual(self.keys(), before)

    def test_authorization_and_existence_come_before_the_state_of_the_key(self):
        self.assertEqual(self.bea_client.delete('/v1/keys/' + self.old['id'], headers=self.headers).status_code, 200)
        reader, headers = self.session('ana')  # read on p1, neither the owner nor the global administrator
        self.assertEqual(self.rotate(client=reader, headers=headers).status_code, 404, 'a revoked key of another user is 404 to her, as an unknown one, not 409')
        self.assertEqual(self.rotate('nobody').status_code, 404)
        self.assertEqual(self.rotate(headers={}).status_code, 403, 'a session needs the origin and the CSRF token')
        reading_key = self.bea_client.post('/v1/keys', json={'name': 'reader', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
        target = self.bea_client.post('/v1/keys', json={'name': 'target', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
        self.assertEqual(self.client().post('/v1/keys/%s/rotate' % target['id'], headers=self.bearer(reading_key['token'])).status_code, 403, 'a key without admin may not')
        self.assertEqual(self.client().post('/v1/keys/%s/rotate' % self.old['id'], headers=self.bearer(reading_key['token'])).status_code, 403,
                         'a revoked key is 403 to its owner when her credential may not rotate it, not 409')
        for body in ({'grace_seconds': -1}, {'grace_seconds': 7 * 86400 + 1}, {'grace_seconds': '10'}, {'other': 1}):
            with self.subTest(body=body):
                self.assertEqual(self.rotate(target['id'], body=body).status_code, 422)
        self.assertEqual(self.rotate(target['id'], body={'grace_seconds': 7 * 86400}).status_code, 200)
        with self.assertRaises(MemoryError) as raised:
            self.store.rotate_key(self.auth.login('bea', pw.PASSWORD, '198.51.100.93')['actor'], reading_key['id'], -5)
        self.assertEqual(raised.exception.code, 'invalid_rotation')

    def rotated(self, key_id):
        return self.count("SELECT count(*) FROM memory.audit_events WHERE action='key.rotated' AND resource_id LIKE %s", '{"key":"%s"%%' % key_id)

    def test_only_the_owner_or_the_global_administrator_may_rotate_a_key_anyone_else_gets_the_404_of_an_unknown_one(self):
        # fix1 of the review of phase 4, gaps 1 and 3 (decision of the user, 2026-11-27: «owner or global admin»). cid administers p1 with every permission of bea's key, so
        # she could issue one like it; rotating bea's key would hand her a token that acts as bea. She gets what an unknown id gets, and nothing changes.
        self.store.create_user(self.admin, {'username': 'cid', 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read', 'write', 'admin']})
        cid, cid_headers = self.session('cid')
        cid_key = cid.post('/v1/keys', json={'name': 'cid', 'project_ids': ['p1'], 'scopes': ['read', 'write', 'admin']}, headers=cid_headers).json()
        root_key = self.store.create_key(self.admin, {'name': 'root', 'project_ids': ['p1'], 'scopes': ['read', 'write', 'admin']})  # a key is never the global administrator
        before = self.keys()
        unknown = self.rotate('nobody', client=cid, headers=cid_headers)
        self.assertEqual(unknown.status_code, 404, unknown.text)
        for who, sent in (('project administrator', {'client': cid, 'headers': cid_headers}), ('her key', {'client': self.client(), 'headers': self.bearer(cid_key['token'])}),
                          ('a key of the global administrator', {'client': self.client(), 'headers': self.bearer(root_key['token'])})):
            with self.subTest(who=who):
                refused = self.rotate(**sent)
                self.assertEqual(refused.status_code, 404, refused.text)
                self.assertEqual(refused.json()['error'], unknown.json()['error'], 'the answer of a key that does not exist')
        self.assertEqual(self.keys(), before, 'no key issued')
        self.assertEqual(self.rotated(self.old['id']), 0, 'no `key.rotated`')
        self.assertEqual(self.row(self.old['id'], 'actor_id,replaced_by,revoked_at,expires_at'), (self.bea, None, None, None), 'the key of bea is untouched')
        self.assertEqual(self.with_key(self.old['token']), 200)
        root, root_headers = self.root()
        done = self.rotate(client=root, headers=root_headers)
        self.assertEqual(done.status_code, 200, 'the global administrator with a session may')
        self.assertEqual(self.row(done.json()['id'], 'actor_id')[0], self.bea)
        self.assertEqual(cid.delete('/v1/keys/' + done.json()['id'], headers=cid_headers).status_code, 200, 'the project administrator still revokes it: that policy does not change')

    def test_the_owner_rotates_her_key_with_that_key_and_the_new_one_is_still_hers(self):
        # the plugin rotates the key it runs with: the owner (here with a key that has admin and the permissions of the key) may, and the new key keeps her `actor_id`
        own = self.bea_client.post('/v1/keys', json={'name': 'plugin', 'project_ids': ['p1'], 'scopes': ['read', 'write', 'admin']}, headers=self.headers).json()
        done = self.client().post('/v1/keys/%s/rotate' % own['id'], headers=self.bearer(own['token']))
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(self.row(done.json()['id'], 'actor_id')[0], self.bea)
        self.assertEqual(self.client().get('/v1/auth/me', headers=self.bearer(done.json()['token'])).json()['actor']['id'], self.bea)

    def test_a_caller_that_may_not_rotate_the_key_is_refused_before_it_waits_for_any_lock(self):
        # fix1 of the review of phase 4, gap 4: the caller is authorized without locks first; only then the rows of the owner and of the key are locked (and the caller authorized again)
        root = self.auth.login('root-user', 'root-password-123', '198.51.100.94')['actor']
        ana = self.auth.login('ana', pw.PASSWORD, '198.51.100.95')['actor']
        reading = self.bea_client.post('/v1/keys', json={'name': 'reader', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
        reader = self.auth.authenticate_bearer(reading['token'])
        for refused, expected in ((lambda: self.store.rotate_key(ana, self.old['id']), NotFound), (lambda: self.store.rotate_key(reader, self.old['id']), Forbidden)):
            with self.subTest(expected=expected.__name__):
                other = self.bea_client.post('/v1/keys', json={'name': 'other', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
                # the revocation of another key of bea holds the rows of bea and of root (`FOR NO KEY UPDATE`) with its transaction open
                waited, revoked, outcome = self.run_pair(lambda: self.store.revoke_key(root, other['id']), refused, 'key.revoked')
                self.assertFalse(waited, 'a credential that may not rotate the key waited for a lock')
                self.assertIsInstance(revoked, dict, revoked)
                self.assertIsInstance(outcome, expected, outcome)
        self.assertEqual(self.rotated(self.old['id']), 0)

    def test_the_end_of_the_credential_of_the_caller_and_a_rotation_wait_for_each_other(self):
        # fix1 of the review of phase 4, gap 2: the rotation locks the row of the CALLER too (here the global administrator, not the owner). If the end of her session gets there
        # first, the rotation waits for it and is refused with 401 without issuing a key; if the rotation gets there first, the end of the session waits for it.
        for order, n in (('the end of the session first', 96), ('the rotation first', 97)):
            with self.subTest(order=order):
                login = self.auth.login('root-user', 'root-password-123', '198.51.100.%d' % n)
                made = self.bea_client.post('/v1/keys', json={'name': 'm', 'project_ids': ['p1'], 'scopes': ['read']}, headers=self.headers).json()
                before = self.keys()
                if order == 'the end of the session first':
                    waited, ended, rotated = self.run_held(lambda: self.auth.logout(login['session_token']), lambda: self.store.rotate_key(login['actor'], made['id']), auth_module, 'invalidate_auth')
                    self.assertTrue(waited, 'the rotation did not wait for the end of the session of its caller')
                    self.assertIsInstance(rotated, Unauthorized, rotated)
                    self.assertEqual((self.keys(), self.rotated(made['id'])), (before, 0), 'no key issued')
                else:
                    waited, rotated, ended = self.run_pair(lambda: self.store.rotate_key(login['actor'], made['id']), lambda: self.auth.logout(login['session_token']), 'key.rotated')
                    self.assertTrue(waited, 'the end of the session did not wait for the rotation in progress')
                    self.assertIsInstance(rotated, dict, rotated)
                    self.assertEqual(self.keys(), before + 1)
                self.assertNotIsInstance(ended, BaseException, ended)
                with self.assertRaises(Unauthorized):
                    self.store.list_keys(login['actor'])  # and the session is closed

    def test_a_key_that_expires_on_the_last_day_a_key_may_have_is_rotated_and_the_new_one_keeps_that_day(self):
        # fix1 of the review of phase 4, gap 5: its lifetime counted from now passes the year 9999; the new key gets KEY_EXPIRY_MAX instead of a 503
        far = self.bea_client.post('/v1/keys', json={'name': 'far', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '9999-12-31T00:00:00Z'}, headers=self.headers)
        self.assertEqual(far.status_code, 200, far.text)
        self.observer.execute("UPDATE memory.api_keys SET created_at=created_at-interval '1 day' WHERE id=%s", (far.json()['id'],))
        done = self.rotate(far.json()['id'])
        self.assertEqual(done.status_code, 200, done.text)
        self.assertTrue(done.json()['expires_at'].startswith('9999-12-31T00:00:00'), done.json())
        self.assertTrue(86400 - 120 < self.seconds_left(far.json()['id']) <= 86400, 'the old one keeps the grace')

    def test_the_new_key_lasts_the_seconds_the_old_one_was_given_whatever_the_time_zone_of_the_session(self):
        # fix1 of the review of phase 4, gap 7: the lifetime is added in seconds; an interval of days would follow the calendar of the session's time zone (one hour more or less
        # across a change of summer time in Europe/Madrid)
        real = self.store.transaction

        @contextmanager
        def madrid():
            with real() as c:
                c.execute("SET LOCAL TimeZone='Europe/Madrid'")
                yield c
        with madrid() as c:  # a day after the first number of days from now whose calendar days are not as many times 86400 seconds: it crosses one change of the hour
            days = 1 + c.execute("SELECT d FROM (SELECT clock_timestamp() AS t0) n, generate_series(1, 400) d WHERE t0+d*interval '1 day'<>t0+d*interval '86400 seconds' ORDER BY d LIMIT 1").fetchone()['d']
        made = self.bea_client.post('/v1/keys', json={'name': 'dst', 'project_ids': ['p1'], 'scopes': ['read'], 'expires_at': '2999-01-01T00:00:00Z'}, headers=self.headers).json()
        self.observer.execute("UPDATE memory.api_keys SET created_at=t0, expires_at=t0+%s*interval '1 second' FROM (SELECT clock_timestamp()-interval '1 hour' AS t0) n WHERE id=%s",
                              (days * 86400, made['id']))  # one instant for both: the lifetime is exactly that many days
        bea = self.auth.login('bea', pw.PASSWORD, '198.51.100.98')['actor']
        with patch.object(self.store, 'transaction', madrid):
            done = self.store.rotate_key(bea, made['id'])
        given = float(self.count('SELECT extract(epoch FROM expires_at-created_at) FROM memory.api_keys WHERE id=%s', done['id']))
        self.assertAlmostEqual(given, days * 86400, delta=60, msg='the new key lasts %s s, the old one was given %s s (%d days)' % (given, days * 86400, days))

    def test_the_route_publishes_its_body_answer_and_errors(self):
        document = self.app.openapi()
        operation = document['paths']['/v1/keys/{key_id}/rotate']['post']
        self.assertEqual(operation['operationId'], 'memory_rotate_key')
        self.assertFalse(operation['requestBody'].get('required', False), 'the body is optional: an empty request rotates with the default grace')
        self.assertEqual(operation['responses']['200']['content']['application/json']['schema'], {'$ref': '#/components/schemas/KeyRotated'})
        for status in ('401', '403', '404', '409'):
            self.assertEqual(operation['responses'][status]['content']['application/json']['schema'], {'$ref': '#/components/schemas/Error'}, status)
        self.assertNotIn('required', document['components']['schemas']['KeyRotation'])
        self.assertEqual(self.rotate().status_code, 200, 'no body at all')


if __name__ == '__main__':
    unittest.main()
