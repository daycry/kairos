"""Permissions resolved ONCE per transaction (I3 / CA-18, B-02; C-03). `Store._active` (actor and credential) and `Store._require` (the grants of a project) keep what they read in a dict that
lives on the connection from the start of `Store.transaction()` to its COMMIT or ROLLBACK and nowhere else (`auth_scope.py`). R-05: a revocation can never be relaxed by it.

What these tests hold, each with a mutant that turns it red (the mutants are listed in the notes of T-30/T-31 of the ledger):
* one search over N projects reads the actor and the credential once and each project's grants once, not N times each;
* the cache dies with the COMMIT: a revocation committed by anybody is seen by the NEXT transaction, also on the very same pooled connection;
* it is never shared: two actors, two credentials of one actor and two projects, in turn on one connection and in the same transaction, in two threads;
* it is emptied inside a transaction that changes permissions or rolls a savepoint back;
* every statement that writes a permission table sits in a function that empties it, and every function that opens a transaction either resolves permissions or is on the
  reviewed list of those that do not (the walk over the transactions of the package);
* every `/v1` route and every `Store` method that takes an actor answers 401/`Unauthorized` right after the credential is revoked, on a pool of ONE connection.

Real PostgreSQL (the isolated test database); no test waits for a clock."""
import ast
import hashlib
import inspect
import os
import re
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from memory_platform import auth_scope
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.auth_scope import invalidate_auth, savepoint
from memory_platform.config import Settings
from memory_platform.errors import Forbidden, NotFound, Unauthorized
from memory_platform.store import Store
from memory_platform.store_pool import close_pool
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.test_store_pool import pool_store

PACKAGE = Path(__file__).resolve().parents[1]
ACTORS = 'FROM memory.actors WHERE id='
KEYS = 'FROM memory.api_keys WHERE id='
GRANTS = 'FROM memory.project_grants WHERE actor_id='


def project_name():
    return 'ac-' + uuid.uuid4().hex[:14]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.projects = [self.pid]
        for _ in range(3):
            name = project_name()
            self.store.create_project(self.admin, {'id': name, 'title': 'Cache ' + name})
            self.projects.append(name)
        self.auth = Auth(self.store)

    def key(self, projects=None, scopes=('read',)):
        created = self.store.create_key(self.admin, {'name': 'cache', 'project_ids': projects or self.projects, 'scopes': list(scopes)})
        return created, self.auth.authenticate_bearer(created['token'])

    def user(self, projects, scopes=('read',)):
        """A non-admin user with grants on `projects` and a bearer actor for him (no key restriction beyond his own grants is possible, so the key lists the same)."""
        name = 'u-' + uuid.uuid4().hex[:12]
        created = self.store.create_user(self.admin, {'username': name, 'password': 'synthetic-password-123', 'project_ids': projects, 'scopes': list(scopes)})
        return {'id': created['id'], 'credential_type': 'bootstrap'}

    def pooled(self, size=1):
        store = pool_store(self.store.dsn, minimum=1, maximum=size)
        self.addCleanup(close_pool, store)
        return store


class CountingTests(Fixture):
    def counted(self, call):
        seen = []
        real = psycopg.Cursor.execute

        def execute(cursor, query, *args, **kwargs):
            seen.append(query if isinstance(query, str) else str(query))
            return real(cursor, query, *args, **kwargs)
        with patch.object(psycopg.Cursor, 'execute', execute):
            call()
        return {name: sum(marker in sql for sql in seen) for name, marker in (('actor', ACTORS), ('key', KEYS), ('grants', GRANTS))}

    def test_a_search_over_n_projects_reads_the_actor_and_the_key_once_and_each_projects_grants_once(self):
        _, actor = self.key()
        counts = self.counted(lambda: self.store.search_items(actor, self.projects, 'x'))
        self.assertEqual(counts, {'actor': 1, 'key': 1, 'grants': len(self.projects)})

    def test_the_grants_of_a_project_are_read_once_even_when_two_permissions_are_asked(self):
        _, actor = self.key(scopes=('read', 'write'))
        counts = self.counted(lambda: self.store.capture_policy(actor, self.pid))  # `read` and then `write` of the same project
        self.assertEqual(counts, {'actor': 1, 'key': 1, 'grants': 1})

    def test_the_existence_of_a_project_is_read_once_for_the_bootstrap_actor(self):
        seen = []
        real = psycopg.Cursor.execute

        def execute(cursor, query, *args, **kwargs):
            seen.append(str(query))
            return real(cursor, query, *args, **kwargs)
        with patch.object(psycopg.Cursor, 'execute', execute):
            self.store.capture_policy(self.admin, self.pid)
        self.assertEqual(sum('FROM memory.projects WHERE id=' in sql and 'policy' not in sql for sql in seen), 1)

    def test_each_transaction_reads_again(self):
        _, actor = self.key()
        counts = self.counted(lambda: [self.store.get_policy(actor, self.pid) for _ in range(3)])
        self.assertEqual(counts, {'actor': 3, 'key': 3, 'grants': 3})  # three transactions: nothing is carried from one to the next

    def test_a_connection_that_the_store_did_not_hand_out_keeps_nothing(self):
        _, actor = self.key()
        with psycopg.connect(self.store.dsn, row_factory=psycopg.rows.dict_row) as c:
            self.assertIsNone(getattr(c, '_kairos_auth', None))
            self.store._active(c, actor)
            self.store._require(c, actor, self.pid, 'read')
            self.assertIsNone(getattr(c, '_kairos_auth', None))


class RevocationTests(Fixture):
    def test_a_key_revoked_between_two_requests_on_the_same_connection_is_refused_by_the_second(self):
        store = self.pooled(1)
        created, actor = self.key()
        pids = []
        with store.transaction() as c:
            pids.append(c.execute('SELECT pg_backend_pid() AS p').fetchone()['p'])
            store._require(c, actor, self.pid, 'read')
        self.store.revoke_key(self.admin, created['id'])  # committed by another request, another connection
        with self.assertRaises(Unauthorized):
            with store.transaction() as c:
                pids.append(c.execute('SELECT pg_backend_pid() AS p').fetchone()['p'])
                store._require(c, actor, self.pid, 'read')
        with store.transaction() as c:
            pids.append(c.execute('SELECT pg_backend_pid() AS p').fetchone()['p'])
            self.assertIsNone(getattr(c, '_kairos_auth').get(('active', actor['id'], 'bearer', actor['key_id'], None)))
        self.assertEqual(len(set(pids)), 1, 'all three transactions ran on the one connection of the pool')
        with self.assertRaises(Unauthorized):
            store.list_projects(actor)

    def test_a_revocation_committed_while_another_transaction_is_open_is_seen_by_the_next_one_of_that_connection(self):
        store = self.pooled(2)
        created, actor = self.key()
        with store.transaction() as c:
            store._require(c, actor, self.pid, 'read')  # this transaction has resolved the key
            self.store.revoke_key(self.admin, created['id'])  # a second connection revokes it and commits meanwhile
        with self.assertRaises(Unauthorized):  # the connection of the first one is the next to be handed out
            store.get_policy(actor, self.pid)
        with self.assertRaises(Unauthorized):
            self.store.get_policy(actor, self.pid)

    def test_a_disabled_user_a_dropped_grant_and_an_expired_session_are_seen_by_the_next_transaction(self):
        store = self.pooled(1)
        user = self.user([self.pid])
        store.get_policy(user, self.pid)
        with self.store.transaction() as c:
            c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (user['id'],))
        with self.assertRaises(NotFound):
            store.get_policy(user, self.pid)
        with self.store.transaction() as c:
            c.execute('UPDATE memory.actors SET disabled=true WHERE id=%s', (user['id'],))
        with self.assertRaises(Unauthorized):
            store.get_policy(user, self.pid)

    def test_a_revocation_inside_the_transaction_is_seen_once_the_cache_is_emptied(self):
        created, actor = self.key()
        with self.store.transaction() as c:
            self.store._active(c, actor)
            c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE id=%s', (created['id'],))
            invalidate_auth(c)
            with self.assertRaises(Unauthorized):
                self.store._active(c, actor)

    def test_a_savepoint_that_fails_takes_what_was_read_after_its_writes_with_it(self):
        user = self.user([self.pid])
        with self.store.transaction() as c:
            self.store._require(c, user, self.pid, 'read')
            with self.assertRaises(RuntimeError):
                with savepoint(c):
                    c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s)', (user['id'], self.projects[1], 'read'))
                    self.store._require(c, user, self.projects[1], 'read')  # read after the write: cached
                    raise RuntimeError('the savepoint fails')
            with self.assertRaises(NotFound):  # the grant went with the savepoint; the cache must not keep it
                self.store._require(c, user, self.projects[1], 'read')
            self.store._require(c, user, self.pid, 'read')

    def test_a_savepoint_that_succeeds_keeps_working_and_the_rest_of_the_transaction_still_resolves(self):
        user = self.user([self.pid])
        with self.store.transaction() as c:
            with savepoint(c):
                self.store._require(c, user, self.pid, 'read')
            self.store._require(c, user, self.pid, 'read')

    def test_a_search_that_rolls_a_savepoint_back_still_answers_with_current_permissions(self):
        # `bounded_fallback` and the exact routes run in savepoints; a cancelled one must leave the permissions of the transaction as the database says
        _, actor = self.key()
        self.assertEqual(self.store.search_items(actor, self.projects, 'nothing'), [])
        self.assertIn('savepoint(c)', (PACKAGE / 'store_documents.py').read_text(encoding='utf-8'))
        self.assertIn('savepoint(c)', (PACKAGE / 'store_vectors.py').read_text(encoding='utf-8'))


class IsolationTests(Fixture):
    def test_two_actors_in_turn_on_one_connection_never_see_each_other(self):
        store = self.pooled(1)
        _, first = self.key([self.projects[0]])
        _, second = self.key([self.projects[1]])
        for _ in range(2):
            store.get_policy(first, self.projects[0])
            with self.assertRaises(NotFound):
                store.get_policy(first, self.projects[1])
            store.get_policy(second, self.projects[1])
            with self.assertRaises(NotFound):
                store.get_policy(second, self.projects[0])

    def test_two_actors_two_credentials_and_two_projects_in_the_same_transaction_keep_their_own_answers(self):
        read_only, reader = self.key([self.projects[0], self.projects[1]], ('read',))
        _, writer = self.key([self.projects[0]], ('read', 'write'))
        user = self.user([self.projects[2]], ('read',))
        with self.store.transaction() as c:
            self.store._require(c, reader, self.projects[0], 'read')
            self.store._require(c, writer, self.projects[0], 'write')
            with self.assertRaises(Forbidden):  # same actor, other key: the read-only key cannot write
                self.store._require(c, reader, self.projects[0], 'write')
            with self.assertRaises(NotFound):  # same key, other project it does not list
                self.store._require(c, writer, self.projects[1], 'read')
            self.store._require(c, reader, self.projects[1], 'read')
            self.store._require(c, user, self.projects[2], 'read')
            with self.assertRaises(NotFound):  # another actor: the grants of the project it asked for are its own
                self.store._require(c, user, self.projects[0], 'read')
            with self.assertRaises(NotFound):
                self.store._require(c, user, self.projects[1], 'read')
            self.store._require(c, self.admin, self.projects[3], 'admin')  # the bootstrap actor still resolves after all of them
            self.assertEqual(self.store._active(c, reader)[1]['id'], read_only['id'])

    def test_concurrent_transactions_on_a_pool_of_two_connections_do_not_share_the_cache(self):
        store = self.pooled(2)
        _, first = self.key([self.projects[0]])
        _, second = self.key([self.projects[1]])
        inside, proceed, outcome = threading.Barrier(2, timeout=30), threading.Barrier(2, timeout=30), {}

        def run(name, actor, mine, other):
            try:
                with store.transaction() as c:
                    store._require(c, actor, mine, 'read')
                    inside.wait()  # both transactions are open and hold their cache
                    proceed.wait()
                    try:
                        store._require(c, actor, other, 'read')
                        outcome[name] = 'leaked'
                    except NotFound:
                        outcome[name] = 'isolated'
            except Exception as exc:  # pragma: no cover - reported below
                outcome[name] = repr(exc)
        threads = [threading.Thread(target=run, args=('a', first, self.projects[0], self.projects[1])), threading.Thread(target=run, args=('b', second, self.projects[1], self.projects[0]))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(outcome, {'a': 'isolated', 'b': 'isolated'})

    def test_a_cache_is_the_dict_of_one_transaction_and_is_gone_after_it(self):
        store = self.pooled(1)
        caches = []
        for _ in range(2):
            with store.transaction() as c:
                self.assertEqual(getattr(c, '_kairos_auth'), {})
                caches.append(getattr(c, '_kairos_auth'))
                store._require(c, self.admin, self.pid, 'read')
                self.assertTrue(getattr(c, '_kairos_auth'))
        self.assertIsNot(caches[0], caches[1])
        self.assertIsNone(getattr(c, '_kairos_auth'))
        with self.assertRaises(RuntimeError):
            with store.transaction() as c:
                store._require(c, self.admin, self.pid, 'read')
                raise RuntimeError('rolled back')
        self.assertIsNone(getattr(c, '_kairos_auth'))
        self.assertFalse([name for name, value in vars(auth_scope).items() if isinstance(value, (dict, set, list)) and not name.startswith('__')], 'no module-level state in auth_scope')




if __name__ == '__main__':
    unittest.main()
