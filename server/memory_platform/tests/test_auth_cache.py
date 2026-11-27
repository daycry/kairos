"""Permissions resolved ONCE per transaction (I3 / CA-18, B-02; C-03). `Store._active` (actor and credential) and `Store._require` (the grants of a project) keep what they read in a dict that
lives on the connection from the start of `Store.transaction()` to its COMMIT or ROLLBACK and nowhere else (`auth_scope.py`). R-05: a revocation can never be relaxed by it.

What these tests hold, each with a mutant that turns it red (the mutants are listed in the notes of T-30/T-31 of the ledger):
* one search over N projects reads the actor and the credential once and each project's grants once, not N times each;
* the cache dies with the COMMIT: a revocation committed by anybody is seen by the NEXT transaction, also on the very same pooled connection;
* it is never shared: two actors, two credentials of one actor and two projects, in turn on one connection and in the same transaction, in two threads;
* it is emptied inside a transaction that changes permissions or rolls a savepoint back;
* every statement that writes a permission table (literal or composed SQL: an unrecognised write fails) is followed by the function emptying it; every wait for a lock (advisory, `FOR UPDATE`,
  `FOR SHARE`, `FOR NO KEY UPDATE`, `FOR KEY SHARE`, `LOCK TABLE`, also through a helper that takes the connection) is followed by emptying it BEFORE the next permission check; no savepoint is
  opened but by `auth_scope.savepoint`, whatever the connection is called (a static walk over the package; the behaviour of the waits is in `test_auth_race.py`, with two connections);
* every function that opens a transaction either resolves permissions or is on the reviewed list of those that do not (the walk over the transactions of the package);
* every `/v1` route and every `Store` method that takes an actor answers 401/`Unauthorized` right after the credential is revoked, on a pool of ONE connection.

Real PostgreSQL (the isolated test database); no test waits for a clock."""
import ast
import functools
import hashlib
import inspect
import itertools
import os
import re
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from pglast import ast as pg, parse_sql  # the parser of PostgreSQL 17 (a dependency of the test image only: server/requirements-test.txt)

from memory_platform import admin, auth_scope
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


LOCK = re.compile(r'pg_(try_)?advisory_(xact_)?lock|\bFOR\s+(NO\s+KEY\s+UPDATE|UPDATE|KEY\s+SHARE|SHARE)\b|\bLOCK\s+TABLE\b', re.I)
WRITE_VERB = r'(?<!FOR )(?<!DO )(?<!KEY )(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(?:\s+TABLE)?)\s+(?:ONLY\s+)?'  # not the `FOR UPDATE` / `DO UPDATE` of a lock or an upsert
PERMISSION_WRITE = re.compile(WRITE_VERB + r'memory\.(actors|api_keys|web_sessions|project_grants|projects)\b', re.I)
COMPOSED_WRITE = re.compile(WRITE_VERB + r'(?:memory\.)?(?![A-Za-z_])', re.I)  # a write whose table is not spelled out: a placeholder, a `{}`, a variable
RESOLVERS = {'_require', '_active', '_global_admin', '_delegate', 'require_permission', '_authorized', '_generation', '_protect_validated', '_corpus'}
SELF_REFRESHING = {'_authorized', '_generation', '_protect_validated'}  # each one empties the cache after its own waits and before its checks (this walk proves it of each)
EMPTIES = 'invalidate_auth'
CHANGED = '_access_changed'  # `store_access.py`: audits a change of access and calls `invalidate_auth`; a writer that ends in it has emptied the cache


def text_of(node, consts, seen=frozenset()):
    """The SQL text a node can build: string constants, the pieces of an f-string (a hole is NUL), `sql.SQL('...').format(...)`, concatenations and the module-level constants it names."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ''
    if isinstance(node, ast.JoinedStr):
        return ''.join(text_of(v, consts, seen) if isinstance(v, ast.Constant) else '\x00' for v in node.values)
    if isinstance(node, ast.Name) and node.id in consts and node.id not in seen:
        return text_of(consts[node.id], consts, seen | {node.id})
    return ' '.join(text_of(child, consts, seen) for child in ast.iter_child_nodes(node))


def module_constants(tree):
    return {node.targets[0].id: node.value for node in tree.body if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}


def functions():
    for file in sorted(PACKAGE.glob('*.py')):
        tree = ast.parse(file.read_text(encoding='utf-8'))
        consts = module_constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield file.name, node, consts


def called(call):
    return call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id if isinstance(call.func, ast.Name) else ''


def argument_text(call, consts):
    return ' '.join(text_of(a, consts) for a in [*call.args, *(k.value for k in call.keywords)])


def lock_helpers():
    """Private functions of the package that take the connection `c` and wait for a lock in it: calling one is waiting, in the caller's transaction. (Public methods open their own transaction.)"""
    found = set()
    for _, node, consts in functions():
        if node.name.startswith('_') and 'c' in {a.arg for a in node.args.args} and node.name not in SELF_REFRESHING and node.name != '_require':
            if any(isinstance(n, ast.Call) and LOCK.search(argument_text(n, consts)) for n in ast.walk(node)):
                found.add(node.name)
    return found


def timeline(name, node, consts, helpers):
    """The calls of one function in source order: ('lock', end) a wait for a lock, ('empty', start) the cache is emptied, ('check', start) permissions are resolved from the cache."""
    events = []
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        start, end, function = (call.lineno, call.col_offset), (call.end_lineno, call.end_col_offset), called(call)
        refreshing = function in SELF_REFRESHING or (name == 'extended_store.py' and function == '_require' and ast.unparse(call.func) == 'self._require')
        if function in (EMPTIES, CHANGED) or refreshing:
            events.append((start, 'empty'))
        elif function in RESOLVERS:
            events.append((start, 'check'))
        if LOCK.search(argument_text(call, consts)) or function in helpers:
            events.append((end, 'lock'))
    return sorted(events)


def stale_checks(events):
    """The checks that follow a wait for a lock with no emptying of the cache in between."""
    waited, bad = False, []
    for position, kind in events:
        if kind == 'lock':
            waited = True
        elif kind == 'empty':
            waited = False
        elif waited:
            bad.append(position)
    return bad


class WritersEmptyTheCacheTests(unittest.TestCase):
    """Every statement that writes who may do what is followed by the emptying of the cache, and every wait for a lock by it BEFORE the next check (a static walk over the package, so a new
    writer or a new lock fails here until it does)."""

    def test_every_function_that_writes_a_permission_table_empties_the_cache_after_the_write(self):
        # admin.py (the operator's retention, which only deletes expired sessions and runs on a direct connection) and the migration are not request paths
        exempt = {('admin.py', name) for name in ('prune_tables', 'main')} | {('store_auth.py', 'migrate')}
        writers = set()
        for name, node, consts in functions():
            if (name, node.name) in exempt:
                continue
            writes = [(c.end_lineno, c.end_col_offset) for c in ast.walk(node) if isinstance(c, ast.Call) and PERMISSION_WRITE.search(argument_text(c, consts))]
            if writes:
                writers.add((name, node.name))
                empties = [(c.lineno, c.col_offset) for c in ast.walk(node) if isinstance(c, ast.Call) and called(c) in (EMPTIES, CHANGED)]
                self.assertTrue(empties and max(empties) > max(writes), '%s:%s writes a permission table and does not empty the cache after the last write' % (name, node.name))
        self.assertTrue({('store_auth.py', 'revoke_key'), ('store_auth.py', 'create_key'), ('store_auth.py', 'create_user'), ('store_auth.py', 'create_project'),
                         ('store_auth.py', 'bootstrap_user'), ('auth.py', 'logout'), ('auth.py', 'login'), ('auth.py', 'refresh_csrf'), ('store_access.py', 'change_password')} <= writers, sorted(writers))

    def test_every_writer_of_store_access_ends_in_the_door_and_the_door_audits_and_empties(self):
        # design.md O2: `_access_changed` is the end of EVERY writer of `store_access.py` (not only "somewhere after the write"): after its call nothing is written, and the door itself
        # records the audit event and empties the cache (a mutant that drops either leaves a writer that audits nothing or keeps a revoked permission alive in its transaction)
        sources = {name: node for name, node, _ in functions() if name == 'store_access.py'}
        self.assertTrue(sources)
        door, writers = None, []
        for name, node, consts in functions():
            if name != 'store_access.py':
                continue
            if node.name == CHANGED:
                door = node
                continue
            writes = [(c.end_lineno, c.end_col_offset) for c in ast.walk(node) if isinstance(c, ast.Call) and PERMISSION_WRITE.search(argument_text(c, consts))]
            if not writes:
                continue
            writers.append(node.name)
            ends = [(c.lineno, c.col_offset) for c in ast.walk(node) if isinstance(c, ast.Call) and called(c) == CHANGED]
            self.assertTrue(ends and min(ends) > max(writes), '%s writes a permission table and does not end in `%s`' % (node.name, CHANGED))
        self.assertTrue({'change_password', 'set_password', '_set_disabled', 'replace_grants', 'revoke_other_sessions', 'revoke_user_sessions', 'rotate_key'} <= set(writers), 'the walk sees the writers of T-09, T-10, T-13, T-14, T-15 and T-20: a scan that finds none would pass for the wrong reason')
        self.assertIsNotNone(door, '`_access_changed` is gone from store_access.py')
        inside = {called(c) for c in ast.walk(door) if isinstance(c, ast.Call)}
        self.assertTrue({'_audit', EMPTIES} <= inside, '`_access_changed` must audit and empty the cache, it calls %s' % sorted(inside))
        audit, empty = (min((c.lineno, c.col_offset) for c in ast.walk(door) if isinstance(c, ast.Call) and called(c) == name) for name in ('_audit', EMPTIES))
        self.assertLess(audit, empty, 'audit first, then empty the cache')

    def test_a_write_to_a_table_that_is_not_spelled_out_fails_unless_it_is_reviewed(self):
        # `sql.SQL('UPDATE memory.{}')`, an f-string or a concatenation can write the permission tables without the literal name: any write whose target is not a plain table fails
        reviewed = {('admin.py', 'prune_tables'): 'operator retention on a list of tables of its own, direct connection, only expired sessions and finished jobs'}
        composed = {(name, node.name) for name, node, consts in functions()
                    if COMPOSED_WRITE.search(re.sub(r'\s+', ' ', ' '.join(text_of(c, consts) for c in node.body if not (isinstance(c, ast.Expr) and isinstance(c.value, ast.Constant)))))}
        self.assertEqual(sorted(composed - set(reviewed)), [], 'a write whose table is composed at run time: spell it out or review it here')
        self.assertEqual(sorted(set(reviewed) - composed), [], 'reviewed but no longer composed (or gone): remove it from the list')

    def test_every_wait_for_a_lock_is_followed_by_emptying_the_cache_before_the_next_permission_check(self):
        # advisory locks, FOR UPDATE / SHARE / NO KEY UPDATE / KEY SHARE and LOCK TABLE, in this function or in a helper that takes the connection: a revocation committed while it waited must be read (CWE-367)
        helpers, guarded, stale = lock_helpers(), set(), []
        for name, node, consts in functions():
            events = timeline(name, node, consts, helpers)
            if any(kind == 'lock' for _, kind in events) and any(kind in ('check', 'empty') for _, kind in events):
                guarded.add((name, node.name))
            stale += [(name, node.name, line) for line, _ in stale_checks(events)]
        self.assertEqual(stale, [], 'a permission check after a wait for a lock that reads what the transaction cached before the wait: call `invalidate_auth(c)` after the lock')
        self.assertTrue({('store_ingest.py', 'ingest_event'), ('store_ingest.py', '_protect_validated'), ('store_documents.py', 'publish_document'), ('store_documents.py', 'delete_document'),
                         ('store_jobs.py', 'retry_job'), ('extended_store.py', '_require'), ('corpus_answers.py', '_authorized')} <= guarded, sorted(guarded))
        self.assertTrue({'_lock', '_corpus', '_verify_entries'} <= helpers, sorted(helpers))

    def test_the_walk_sees_a_lock_taken_in_any_form_and_a_check_that_comes_too_early(self):
        # the detector itself: each of these sources must be reported (or, with the emptying between the lock and the check, accepted)
        template = 'def f(self, c, actor, p):\n    self._require(c, actor, p, "read")\n    %s\n    %s\n'
        waits = ["c.execute('SELECT pg_advisory_xact_lock(1)')", "c.execute('SELECT 1 FROM memory.t FOR UPDATE')", "c.execute('select 1 from memory.t for share')", "c.execute('SELECT 1 FOR NO KEY UPDATE')",
                 "c.execute('SELECT 1 FOR KEY SHARE')", "c.execute('LOCK TABLE memory.t')", "c.execute(f'SELECT 1 FROM {t} FOR UPDATE')", "c.execute(LOCKED)", "self._lock(c)"]
        for wait in waits:
            for check, accepted in (("self._require(c, actor, p, 'validate')", False), ("invalidate_auth(c)\n    self._require(c, actor, p, 'validate')", True),
                                    ("self._require(c, actor, p, 'validate')\n    invalidate_auth(c)", False)):
                tree = ast.parse(template % (wait, check))
                consts = {**module_constants(tree), 'LOCKED': ast.parse("'SELECT 1 FOR UPDATE'").body[0].value}
                self.assertEqual(not stale_checks(timeline('x.py', tree.body[0], consts, {'_lock'})), accepted, (wait, check))

    def test_no_function_opens_a_savepoint_without_the_helper_whatever_the_connection_is_called(self):
        # a savepoint is `<connection>.transaction()` inside a transaction. The receivers that are NOT a connection: the store (`self`, `self.store`, `store`) and the three places that open one
        allowed = {'self', 'self.store', 'store'}
        reviewed = {('store.py', 'connection'), ('admin.py', 'restored'), ('auth_scope.py', 'c')}
        for file in sorted(PACKAGE.glob('*.py')):
            source = file.read_text(encoding='utf-8')
            tree = ast.parse(source)
            attributes = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == 'transaction']
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'transaction']
            self.assertEqual(len(attributes), len(calls), '%s refers to `.transaction` without calling it (an alias of a savepoint)' % file.name)
            for call in calls:
                receiver = ast.unparse(call.func.value)
                self.assertTrue(receiver in allowed or (file.name, receiver) in reviewed, '%s opens a savepoint on `%s`: use `auth_scope.savepoint(c)`' % (file.name, receiver))
            consts = module_constants(tree)
            for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
                self.assertNotRegex(argument_text(call, consts), r'(?i)^\s*(SAVEPOINT\s+\w|RELEASE\s+SAVEPOINT|ROLLBACK\s+TO\b)', '%s opens a savepoint in SQL: use `auth_scope.savepoint(c)`' % file.name)


class EveryTransactionTests(unittest.TestCase):
    """The walk over the transactions of the package: each function that opens one (`.transaction()`) resolves permissions through the cached helpers, or is one of the reviewed few that
    do not and why. A new transaction that skips the permission check, or that resolves it with its own query, fails here."""
    RESOLVERS = {'_require', '_active', '_global_admin', '_delegate', '_visible_projects', '_admin_somewhere', 'require_permission', '_authorized', '_generation'}
    NOT_REQUEST_PATHS = {
        ('admin.py', 'store_fingerprints'): 'operator command on a direct connection', ('admin.py', 'inspect_store'): 'operator command', ('admin.py', 'content_manifest'): 'operator command',
        ('backup.py', 'create_backup'): 'operator command: one exported snapshot for the fingerprints and the dump', ('admin.py', 'mark_stale_unchunked'): 'operator command', ('admin.py', 'backfill_chunks'): 'operator command', ('admin.py', 'prune_tables'): 'operator command', ('admin.py', 'main'): 'operator command',
        ('auth.py', 'authenticate_bearer'): 'it IS the credential check (reads the key itself, every request, no cache)', ('auth.py', 'authenticate_session'): 'it IS the credential check',
        ('auth.py', 'login'): 'proves a password; opens the session', ('auth.py', 'logout'): 'revokes the session of the cookie it holds', ('auth.py', 'require_csrf'): 'reads the live session row itself',
        ('observability.py', '_read'): 'metrics read, no actor', ('store.py', 'transaction'): 'the provider of the transaction', ('auth_scope.py', 'savepoint'): 'a savepoint, not a transaction',
        ('store_auth.py', 'migrate'): 'schema', ('store_auth.py', 'bootstrap_user'): 'creates the first actor', ('store_access.py', 'set_password'): 'operator command (admin set-password): recovers an account, no request actor',
        ('store_access.py', 'operator_set_disabled'): 'operator command (admin disable-user/enable-user): no request actor; the writer it shares with the route (`_set_disabled`) checks the actor when there is one', ('store_jobs.py', 'stored_item_vector'): 'worker, no actor',
        ('store_jobs.py', 'job_outcome'): 'worker, keyed by fence', ('store_jobs.py', 'claim_job'): 'worker', ('store_jobs.py', 'renew_lease'): 'worker', ('store_jobs.py', 'complete_job'): 'worker, keyed by fence',
        ('store_jobs.py', 'fail_job'): 'worker, keyed by fence', ('store_pool.py', 'ready_probe'): 'health probe, no actor',
        ('probe.py', 'admin_actor'): 'operator command (admin probe-provision): the administrator the command acts as', ('probe.py', 'provision'): 'operator command: the advisory lock that serialises two provisionings',
        ('probe.py', 'provision_locked'): 'operator command: makes the probe project, its service actor and key', ('probe.py', 'purge_retired'): 'operator command (admin probe): deletes the rows of the retired notes of kairos-probe, that project only',
    }

    def test_every_transaction_resolves_permissions_or_is_on_the_reviewed_list(self):
        sites, without = 0, {}
        for path in sorted(PACKAGE.glob('*.py')):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                opens = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'transaction' and not n.args]
                if not opens:
                    continue
                sites += len(opens)
                called = {n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)} | {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
                if not called & self.RESOLVERS:
                    without[(path.name, node.name)] = len(opens)
        self.assertGreaterEqual(sites, 86)
        unreviewed = sorted(set(without) - set(self.NOT_REQUEST_PATHS))
        self.assertEqual(unreviewed, [], 'a transaction that does not resolve permissions through the cached helpers: add the check or review it here')
        stale = sorted(set(self.NOT_REQUEST_PATHS) - set(without))
        self.assertEqual(stale, [], 'on the reviewed list but it now resolves permissions (or no longer exists): remove it from the list')


# ---- who decides an access and who may write the permission tables (CA-38 a, DC-1, design.md O2) ----
# The resolver: the only code that READS `project_grants`, the permissions of a key (`api_keys`) or `actors.is_admin` to decide whether a request goes on or which rows it sees.
# Functions are named WITH THEIR CLASS (`Class.method`, `outer.inner`): a homonym in another class, or a second definition of the same name, does not inherit the entry (and is red).
RESOLVER = {('store_auth.py', '_load_active')} | {('store_auth.py', 'AuthMixin.' + name) for name in ('_active', '_global_admin', '_require', '_delegate', '_describe', '_visible_projects', '_admin_somewhere')} | {
    ('auth.py', 'Auth.authenticate_bearer'), ('auth.py', 'Auth.authenticate_session')}
# The closed list of reads that do NOT decide an access (DC-1). (file, function) -> (tables it may read, only `FOR SHARE` locks?, why it does not decide). Every function is named: no wildcard,
# and every table named must be read (an entry that no longer reads what it declares is stale).
_PROBE = 'operator command (admin probe-provision) on a direct connection, with no request actor: '
READ_EXCEPTIONS = {
    ('corpus_answers.py', 'CorpusAnswers._authorized'): ({'project_grants', 'api_keys'}, True, 'a FOR SHARE lock: it discards the rows and calls the resolver afterwards, after `invalidate_auth`'),
    ('extended_store.py', 'ExtendedStore._require'): ({'project_grants', 'api_keys'}, True, 'a FOR SHARE lock: it discards the rows and calls the resolver afterwards, after `invalidate_auth`'),
    ('store_auth.py', 'AuthMixin.list_users'): ({'project_grants'}, False, 'shows the permissions of other users to someone `_global_admin` already admitted'),
    ('store_auth.py', 'AuthMixin.list_keys'): ({'api_keys'}, False, 'reads keys as the resource listed, not the credential of the caller; each row goes through `_require`'),
    ('store_auth.py', 'AuthMixin.revoke_key'): ({'api_keys'}, False, 'reads the key to revoke as the resource; each of its projects goes through `_require`'),
    # `is_admin:row` is a read of the WHOLE row (`SELECT *`, `a.*` on `actors`), not of the column by name: login may do the first and not the second
    ('auth.py', 'Auth.login'): ({'is_admin:row'}, False, 'proves a password: `SELECT *` of the actor row, handed whole to `_actor` -> `_describe` of the resolver, which is the only code that looks at `is_admin` in it'),
    ('store_auth.py', 'AuthMixin.bootstrap_user'): ({'is_admin'}, False, 'first start only: writes `is_admin=true` of the first actor and returns the row it stored; it decides no access (the advisory lock and the `Conflict` when an actor exists limit it to the first run)'),
    ('store_access.py', 'AccessMixin._set_disabled'): ({'is_admin'}, False, 'reads `is_admin` of the TARGET user and counts the active administrators, to keep at least one (409); the caller is decided by `_global_admin` before and again after the locks, not by this read'),
    ('store_access.py', 'AccessMixin.replace_grants'): ({'project_grants'}, False, 'reads the grants of the TARGET user (the resource it replaces) only to audit the ones before; the caller is decided by `_global_admin`, before and again after the locks'),
    # T-20, listed in DC-1 with `list_keys` and `revoke_key` («la rotación nueva»): the key read is the resource rotated, not the credential of the caller
    ('store_access.py', 'AccessMixin.rotate_key'): ({'api_keys'}, False, 'reads the key it rotates as the resource (its owner, to lock that row; its name, projects, permissions and state, to copy them and to refuse a revoked, expired or rotated one); the caller is decided by `_active` and, after the locks, by `_delegate` on the projects and permissions of that key'),
    ('probe.py', 'probe_state'): ({'project_grants', 'is_admin'}, False, _PROBE + 'it reads whether the probe project already has grants of another actor and whether the service actor is an administrator, to refuse to adopt them'),
    ('probe.py', 'admin_actor'): ({'is_admin'}, False, _PROBE + 'it finds the administrator the command acts as (named by the operator, or the first one), no request is being decided'),
    ('probe.py', 'provision_locked'): ({'is_admin', 'api_keys', 'project_grants'}, False, _PROBE + 'it refuses a service actor that became administrator, WRITES its own `is_admin=false` when it creates it (`probe.py` INSERT of the service actor), inserts the grants of that actor and reads `RETURNING 1` to know which were new, and looks up its own key by hash to rotate it, under an advisory lock'),
}
# The only modules that may write the tables of permissions and credentials (design.md O2: `store_access.py` is the new door for access changes).
PERMISSION_WRITERS = {'store_auth.py', 'store_access.py', 'auth.py', 'probe.py'}
READ_TABLES = ('project_grants', 'api_keys')
WRITE_TABLES = ('actors', 'project_grants', 'api_keys', 'web_sessions')
# SQL whose table name is not spelled out (an f-string, a `+`, `%`, `.format`, `sql.Identifier`): the scan cannot see WHICH table, so it is an unknown table everywhere except here. Each entry
# is (the tables it can reach, read from the source of truth; None = any table of the schema), (the restricted tables it may WRITE), why, and an extra check returning problems.
# Invariant 2 (design.md:71) for `prune_tables`: it deletes sessions that are already dead (expired, or revoked and past the window): no access changes, so there is nothing for
# `invalidate_auth` to empty (an operator transaction on a direct connection resolves no permissions), and the run leaves ONE `retention_prune` audit event with the rows deleted per table.


WEB_SESSIONS_DEAD = '(t.expires_at < %(cutoff)s OR (t.revoked_at IS NOT NULL AND t.revoked_at < %(cutoff)s))'  # the predicate of `admin.py` RETENTION_TABLES: expired, or revoked before the cutoff


def _web_sessions_only_dead():
    """The exact predicate, blanks normalised. A web_sessions that leaves the retention is NOT a failure (it deletes nothing); any other predicate must be reviewed and put here."""
    keys = [key for key in admin.RETENTION_TABLES if str(key).replace('"', '').strip().lower() == 'web_sessions']  # `'WEB_SESSIONS'` and `'"web_sessions"'` are that table too
    problems = ['web_sessions appears under several keys of the retention: %r' % keys] if len(keys) > 1 else []
    for key in keys:
        predicate = ' '.join(str(admin.RETENTION_TABLES[key][0]).split())
        if predicate != WEB_SESSIONS_DEAD:
            problems.append('the retention of web_sessions (key %r) changed: %r is not %r; review that it deletes only dead sessions, then update WEB_SESSIONS_DEAD' % (key, predicate, WEB_SESSIONS_DEAD))
    return problems


DYNAMIC_SQL = {
    ('admin.py', 'prune_tables'): (lambda sources: set(admin.RETENTION_TABLES), {'web_sessions'}, 'operator retention over its own list of tables; the only restricted table in it is web_sessions, and only dead ones', _web_sessions_only_dead),
    ('admin.py', 'inspect_store'): (None, set(), 'operator command: `SELECT count(*)` over every table of the schema, a number per table', None),
    ('backup.py', 'table_digest'): (None, set(), 'operator backup: one SELECT per table of the schema, hashed row by row into a fingerprint; nothing is returned or written', None),
    ('admin.py', 'derive_single_fragment'): (lambda sources: spelled_tables(sources, 'admin.py', 'derive_single_fragment'), set(), 'operator command: reads the body of one document or item; the two tables are constants of the function', None),
    ('store_jobs.py', 'JobsMixin._job_payload'): (lambda sources: spelled_tables(sources, 'store_jobs.py', 'JobsMixin._job_payload'), set(), 'worker: reads the resource of a job; the two tables are constants of the function', None),
    ('store_jobs.py', 'JobsMixin.claim_job'): (lambda sources: spelled_tables(sources, 'store_jobs.py', 'JobsMixin.claim_job'), set(), 'worker: reads the resource of a job; the two tables are constants of the function', None),
    ('store_jobs.py', 'JobsMixin._current_job'): (lambda sources: spelled_tables(sources, 'store_jobs.py', 'JobsMixin._current_job'), set(), 'worker: locks and reads the resource of a job; the two tables are constants of the function', None),
    ('store_jobs.py', 'JobsMixin.complete_job'): (lambda sources: spelled_tables(sources, 'store_jobs.py', 'JobsMixin.complete_job'), set(), 'worker: reads the resource of a job; the two tables are constants of the function', None),
    ('store_vectors.py', 'migrate_vector_indexes'): (lambda sources: {'embeddings', 'embedding_chunks'}, set(), 'migration: `CREATE INDEX` on the two embedding tables', None),
}
# ---- the SQL of a literal, read with the parser of PostgreSQL 17 (pglast) ----
# EVERY literal, once its constants are filled in and up to 32 768 characters, is parsed: there is no lexical gate (parsing the 33 252 literals of the package costs 0.15-0.2 s). Every hole (a
# non-constant expression, the `{}` `{name}` `{0}` of a template, a `%s` `%(x)s` `%d` placeholder) is replaced by an identifier no one writes (`kairos_hole_N_`) before parsing; a table position is
# decided by the tree (a RangeVar whose name or schema is or contains the identifier). The tree says which tables the text reads and writes, whether it takes a whole row of `actors` and which
# `FOR SHARE` locks it holds. A text that does not parse (or is too big, too deep or has a block comment that never closes) is reported by what it names, outside comments: `memory.` followed by
# a hole is `unknown table`; `memory.<table of the guard>`, or a table of the guard with a word of SQL, is `unparseable SQL` plus that table. A text that does not parse and only has holes is prose
# and is silent. The message of a RAISE is read like any text. When in doubt, red.
_SENTINEL = 'kairos_hole_'
_MAX_PARSED = 32768  # characters; the parser of libpg_query crashes (SIGSEGV) on about 50 000 terms and the largest literal of the package is 1 896 characters
_MAX_DEPTH = 4  # a string of SQL inside a string of SQL inside ...: the text of the deeper ones is read as one that does not parse
_RESTRICTED_WORD = re.compile(r'\b(?:%s)\b' % '|'.join(sorted(set(READ_TABLES) | set(WRITE_TABLES) | {'actors'})), re.I)
_SQL_WORD = re.compile(r'\b(?:SELECT|FROM|JOIN|INTO|UPDATE|DELETE|INSERT|MERGE|TABLE|USING|COPY|TRUNCATE|WITH|VALUES|RETURNING|WHERE|EXISTS|ALTER|DROP|CREATE|LOCK|EXECUTE)\b', re.I)
_WRITE_WORD = re.compile(r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|COPY|ALTER|DROP|CREATE|GRANT|COMMENT)\b', re.I)  # not the bare INTO of PL/pgSQL (`SELECT x INTO v`)
_MEMORY_HOLE = re.compile(r'\bmemory"?\s*\.\s*"?\w*' + _SENTINEL, re.I)  # `memory.` followed by a hole, quoted or not, or with a prefix (`memory.api_<hole>`)
_MEMORY_TABLE = re.compile(r'\bmemory"?\s*\.\s*"?(%s)\b' % '|'.join(sorted(set(READ_TABLES) | set(WRITE_TABLES) | {'actors'})), re.I)
_WHOLE_ROW_WORD = re.compile(r'(?:\w|"|\))\s*\.\s*\*|(?:\bSELECT|\bRETURNING|,)\s*(?:ALL\s+|DISTINCT\s+)?\*|\bTABLE\s+(?:memory\s*\.\s*)?actors\b|\bCOPY\s+(?:memory\s*\.\s*)?actors\s+TO\b', re.I)
_PLACEHOLDER = re.compile(r'%%|%\(\w+\)[sbtdi]|%[sbtdi]')
_BRACE = re.compile(r'\{[^{}]*\}')
_PLAIN = re.compile(r"[^'\"\-/$%{]+")
_DOLLAR = re.compile(r'\$(\w*)\$')
_QUERIES = ('SelectStmt', 'InsertStmt', 'UpdateStmt', 'DeleteStmt', 'MergeStmt')


def _reads_is_admin(sql):
    """Any `is_admin` in a SQL literal, written or read, `%(is_admin)s` included (it names the column too). NO silence by the shape of the SQL: a legitimate writer of `is_admin` is declared BY
    FUNCTION on READ_EXCEPTIONS with its reason, and inside that function anything passes (as in the functions of `probe.py`): that is the accepted cost. The parser does not replace this rule."""
    return bool(re.search(r'\bis_admin\b', sql, re.I))


def _prepare(text):
    """The text the parser gets, in ONE linear pass: every hole is an identifier (a NUL, the `{}` of a template, a psycopg placeholder `%s`/`%(x)s`; `%%` is a `%`); quoted text, dollar quotes
    are copied as they are; comments are cut out (a line comment ends at a line feed or a carriage return, a block comment becomes a space and one that never closes marks the text as not closed).
    A quote or dollar quote that never closes takes the rest of the text, so the cost is the length of the text."""
    counter, closed = itertools.count(), True

    def hole():
        return '%s%d_' % (_SENTINEL, next(counter))
    text = re.sub(r'\x00', lambda m: hole(), text)
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "'":
            escapes = i > 0 and text[i - 1] in 'eE' and (i < 2 or not (text[i - 2].isalnum() or text[i - 2] in '_$'))
            j = i + 1
            if escapes:
                while j < n:
                    if text[j] == '\\':
                        j += 2
                    elif text[j] == "'":
                        if text[j + 1:j + 2] == "'":
                            j += 2
                        else:
                            j += 1
                            break
                    else:
                        j += 1
                j = min(j, n)
            else:
                j = text.find("'", j)
                while j != -1 and text[j + 1:j + 2] == "'":
                    j = text.find("'", j + 2)
                j = n if j == -1 else j + 1
            out.append(text[i:j])
            i = j
        elif c == '"':
            j = text.find('"', i + 1)
            while j != -1 and text[j + 1:j + 2] == '"':
                j = text.find('"', j + 2)
            j = n if j == -1 else j + 1
            token = text[i:j]
            if re.fullmatch(r'"%(?:\(\w+\))?[sbtdi]"', token) and re.search(r'\bmemory\s*\.\s*$', ''.join(out[-3:])):
                out.append(hole())
            else:
                out.append(re.sub(r'\{[^{}]*\}', lambda m: hole(), token))
            i = j
        elif c == '-' and text.startswith('--', i):  # a comment names nothing the statement does, and the lexer of the parser is quadratic in the number of block comments
            ends = [k for k in (text.find('\n', i), text.find('\r', i)) if k != -1]  # as in the lexer of PostgreSQL, a line comment ends at a line feed or a carriage return
            i = min(ends) if ends else n
        elif c == '/' and text.startswith('/*', i):
            j = text.find('*/', i + 2)
            closed = closed and j != -1
            out.append(' ')
            i = n if j == -1 else j + 2
        elif c == '$':
            m = _DOLLAR.match(text, i)
            j = i + 1
            if m:
                k = text.find(m.group(0), m.end())
                j = n if k == -1 else k + len(m.group(0))
            out.append(text[i:j])
            i = j
        elif c == '%':
            m = _PLACEHOLDER.match(text, i)
            out.append('%' if m and m.group(0) == '%%' else hole() if m else '%')
            i = m.end() if m else i + 1
        elif c == '{':
            m = _BRACE.match(text, i)
            out.append(hole() if m else '{')
            i = m.end() if m else i + 1
        else:
            m = _PLAIN.match(text, i)
            out.append(m.group(0) if m else c)
            i = m.end() if m else i + 1
    return ''.join(out), closed


def _children(node):
    for name in type(node).__slots__:
        value = getattr(node, name, None)
        if isinstance(value, pg.Node):
            yield name, value
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, pg.Node):
                    yield name, item
                elif isinstance(item, (tuple, list)):
                    for inner in item:
                        if isinstance(inner, pg.Node):
                            yield name, inner


def _names_in_from(items, table):
    """The names (the table's, and its alias when it has one) under which `table` is in a FROM list."""
    found = set()
    for item in items:
        if isinstance(item, pg.RangeTableSample):
            item = item.relation
        if isinstance(item, pg.RangeVar) and item.relname.lower() == table:
            found |= {table} | ({item.alias.aliasname.lower()} if item.alias else set())
        elif isinstance(item, pg.JoinExpr):
            inner = _names_in_from([item.larg, item.rarg], table)
            found |= inner | ({item.alias.aliasname.lower()} if inner and item.alias else set())  # `(actors a JOIN projects p ON ...) j`: `j.*` carries the row
    return found


def _row_ref(node, names, star_ok):
    """A ColumnRef that is a whole row of the table whose names these are: `*` (when the level has the table), `a.*`, `memory.actors.*`, or the name alone (`a`, in a function, a cast, a ROW)."""
    fields = node.fields
    last = fields[-1]
    if isinstance(last, pg.A_Star):
        if len(fields) == 1:
            return star_ok
        qualifier = fields[-2]
        return isinstance(qualifier, pg.String) and qualifier.sval.lower() in names
    return len(fields) == 1 and isinstance(last, pg.String) and last.sval.lower() in names


def _indirection_row(node, names):
    """`(a).*` and `(memory.actors).*` take the whole row; `(a).id` takes one field of it."""
    last = node.arg.fields[-1]
    return isinstance(node.indirection[0], pg.A_Star) and isinstance(last, pg.String) and last.sval.lower() in names


class _Tree:
    """What one statement does to the tables of the guard. `chain` is the names of `actors` visible at the level (this query and the ones around it), `own` the ones of this level alone (what an
    unqualified `*` expands), `lock` the `FOR SHARE` of the query: None, '*' or the names it limits itself to. A CTE body and a statement after `;` start again with nothing."""
    def __init__(self, depth=0):
        self.reads, self.writes, self.dynamic, self.depth = set(), set(), False, depth

    def string(self, text):
        """A string inside a statement is read again as SQL (`query_to_xml('...')`, `dblink_exec`, the body of DO or of a function): the same function, one level deeper."""
        self.merge(_analysis(text, self.depth + 1) if self.depth < _MAX_DEPTH else _fallback(text))

    def merge(self, other):
        self.reads |= other.reads
        self.writes |= other.writes
        self.dynamic = self.dynamic or other.dynamic

    def row(self):
        self.reads.add(('is_admin:row', False))

    def holes_as_row(self, items, own):
        """A hole alone as an item of a select or RETURNING list of a level that has `actors` may be `a` or `*`."""
        for item in items or ():
            val = getattr(item, 'val', None)
            if own and isinstance(val, pg.ColumnRef) and len(val.fields) == 1 and isinstance(val.fields[0], pg.String) and _SENTINEL in val.fields[0].sval:
                self.row()

    def hole(self, range_var):
        if _SENTINEL in (range_var.relname or '') or _SENTINEL in (range_var.schemaname or ''):
            self.dynamic = True

    def write(self, range_var):
        self.hole(range_var)
        if range_var.relname.lower() in WRITE_TABLES:
            self.writes.add(range_var.relname.lower())

    def visit(self, node, chain=(), own=frozenset(), lock=None):
        kind = type(node).__name__
        skip = ()
        if kind in _QUERIES:
            lock = None
            if kind == 'SelectStmt':
                own = _names_in_from(node.fromClause or (), 'actors')
                self.holes_as_row(node.targetList, own)
                for clause in node.lockingClause or ():
                    if clause.strength.name == 'LCS_FORSHARE':
                        lock = '*' if not clause.lockedRels or lock == '*' else (lock or frozenset()) | {r.relname.lower() for r in clause.lockedRels}
                skip = ('lockingClause',)
            else:
                items = [node.relation] + list(getattr(node, 'fromClause', None) or getattr(node, 'usingClause', None) or ()) + ([node.sourceRelation] if kind == 'MergeStmt' and node.sourceRelation else [])
                own = _names_in_from(items, 'actors')
                self.holes_as_row(node.returningList, own)
                self.write(node.relation)
                target = node.relation.relname.lower()
                if target in READ_TABLES and node.returningList:
                    self.reads.add((target, False))  # the rows it returns, whole or by column, are read from the table
                skip = ('relation',)
            chain = tuple(chain) + (own,)
        elif kind == 'CommonTableExpr':
            self.visit(node.ctequery)
            return
        elif kind == 'RangeVar':
            self.hole(node)
            if node.relname.lower() in READ_TABLES:
                alias = node.alias.aliasname.lower() if node.alias else ''
                self.reads.add((node.relname.lower(), lock == '*' or bool(lock and ({node.relname.lower(), alias} & lock))))
        elif kind == 'ColumnRef':
            if _row_ref(node, frozenset().union(*chain) if chain else frozenset(), bool(own)):
                self.row()
        elif kind == 'String':
            if node.sval.lower() == 'is_admin':
                self.reads.add(('is_admin', False))  # the column by any spelling the parser decodes (`U&"is\\005fadmin"`)
        elif kind == 'A_Const':
            if isinstance(node.val, pg.String):
                self.string(node.val.sval)  # SQL given as a string, whatever it begins with
        elif kind == 'DefElem' and node.defname == 'as':
            for part in node.arg if isinstance(node.arg, (tuple, list)) else [node.arg]:  # the body of DO, CREATE FUNCTION, CREATE PROCEDURE: a string for the parser
                if isinstance(part, pg.String):
                    self.string(part.sval)
            return
        elif kind in ('LockStmt', 'VacuumStmt'):  # LOCK TABLE, ANALYZE, VACUUM take no row and name nothing that is read: neither a read nor an unknown table
            return
        elif kind in ('AlterTableStmt', 'IndexStmt', 'RenameStmt', 'CreateTrigStmt', 'RuleStmt', 'AlterObjectSchemaStmt', 'CreateStmt') and getattr(node, 'relation', None) is not None:
            self.write(node.relation)  # ALTER TABLE, CREATE INDEX/TRIGGER/RULE, RENAME, SET SCHEMA on a table of the guard is a write: only the four writers may do it
            skip = ('relation',)
        elif kind == 'CreatePolicyStmt':
            self.write(node.table)
            skip = ('table',)
        elif kind == 'GrantStmt':
            for target in node.objects or ():
                if isinstance(target, pg.RangeVar):
                    self.write(target)
            return
        elif kind in ('DropStmt', 'CommentStmt'):
            for names in (node.objects if kind == 'DropStmt' else [node.object]) or ():
                parts = [n.sval for n in (names if isinstance(names, (tuple, list)) else [names]) if isinstance(n, pg.String)]
                if kind == 'DropStmt' and any(_SENTINEL in part for part in parts):
                    self.dynamic = True
                self.writes |= {part.lower() for part in parts if part.lower() in WRITE_TABLES}
                if kind == 'DropStmt' and [part.lower() for part in parts] == ['memory']:
                    self.writes |= set(WRITE_TABLES)  # DROP SCHEMA memory
            return
        elif kind == 'Constraint':
            skip = ('pktable',)  # REFERENCES reads no row
        elif kind == 'TableLikeClause':
            return  # CREATE TABLE (LIKE t) copies a definition
        elif kind == 'A_Indirection' and isinstance(node.arg, pg.ColumnRef):
            if _indirection_row(node, frozenset().union(*chain) if chain else frozenset()):
                self.row()
            skip = ('arg',)  # the argument is the row itself or the table of a field: `(a).id` takes one field
        elif kind == 'TruncateStmt':
            for relation in node.relations or ():
                self.write(relation)
            return
        elif kind == 'CopyStmt':
            if node.relation is not None:
                self.hole(node.relation)
                table = node.relation.relname.lower()
                if node.is_from:
                    self.write(node.relation)
                else:
                    if table in READ_TABLES:
                        self.reads.add((table, False))
                    if table == 'actors' and not node.attlist:
                        self.row()
            if node.query is not None:
                self.visit(node.query)
            return
        for name, child in _children(node):
            if name not in skip:
                self.visit(child, chain, own, lock)


class _Analysis:
    __slots__ = ('reads', 'writes', 'dynamic')

    def __init__(self, reads=frozenset(), writes=frozenset(), dynamic=False):
        self.reads, self.writes, self.dynamic = frozenset(reads), frozenset(writes), dynamic


def _fallback(text, prepared=None):
    """What a text that cannot be parsed (a syntax error, an unclosed comment, too big, too deep) is reported as. `memory.` followed by a hole (`memory."<hole>"`, `"memory".<hole>`,
    `memory.api_<hole>`) is always `unknown table`; `memory.<table of the guard>` is always that table; a name without `memory.` counts only with a word of SQL (a bare name like the keys of the
    retention windows is not SQL). A table named is `unparseable SQL` and a read, a write when a word of writing comes before it, and `actors` is a whole row only with a star, `a.*` or
    `TABLE`/`COPY ... TO`. Comments are not read (unless the block comment never closes: then the whole text is). The message of a RAISE is read like any text (a message that names a table of the
    guard is red: declared). A hole alone as the name of a table, with no `memory.`, is NOT seen in a text that does not parse (a declared limit)."""
    stripped, closed = _prepare(text)
    prepared = stripped if prepared is None else prepared
    text = stripped if closed else text
    qualified = {match.group(1).lower() for match in _MEMORY_TABLE.finditer(text)}
    named = qualified | ({word.lower() for word in _RESTRICTED_WORD.findall(text)} if _SQL_WORD.search(text) else set())
    reads = ({('unparseable SQL', False)} if named else set()) | {(table, False) for table in named if table in READ_TABLES} | ({('is_admin:row', False)} if 'actors' in named and _WHOLE_ROW_WORD.search(text) else set())
    writes = set()
    for table in named & set(WRITE_TABLES):
        first = re.search(r'\b%s\b' % table, text, re.I)
        if _WRITE_WORD.search(text[:first.start()]):
            writes.add(table)
    return _Analysis(reads, writes, bool(_MEMORY_HOLE.search(prepared)))


@functools.lru_cache(maxsize=None)
def _analysis(text, depth=0):
    prepared, closed = _prepare(text)
    if len(prepared) > _MAX_PARSED or not closed:
        return _fallback(text, prepared)
    try:
        statements = parse_sql(prepared)
        tree = _Tree(depth)
        for statement in statements:
            tree.visit(statement.stmt)
    except Exception:  # a syntax error (pglast.parser.ParseError), RecursionError on a deep tree, anything else: report, never fail
        return _fallback(text, prepared)
    return _Analysis(tree.reads, tree.writes, tree.dynamic)


def sql_reads(text):
    """(kind, locked) of every restricted read in one SQL literal; `kind` is a table of READ_TABLES, 'is_admin' (the literal names the column), 'is_admin:row' (a whole row of `actors`) or
    'unparseable SQL'. `locked` is True when that read of the table is only a `FOR SHARE` lock (`FOR SHARE OF x` counts only for `x`). A write target is not a read, except that a RETURNING
    of its whole row reads a restricted table."""
    reads = set(_analysis(text).reads)
    if _reads_is_admin(text):
        reads.add(('is_admin', False))
    return reads


def sql_writes(text):
    """The tables of WRITE_TABLES this literal inserts into, updates, deletes from, merges into, truncates or copies into."""
    return set(_analysis(text).writes)


def sql_dynamic(text):
    """True when a table name of the literal is, or contains, a hole that is not a constant (any position: FROM, JOIN, USING, target, TRUNCATE, COPY, a suffix like `memory.api_{kind}`)."""
    return _analysis(text).dynamic


def sql_text(node):
    """The SQL an expression spells: a literal, an f-string and a `+` chain (every hole is NUL), a `%` or `.format` through its template, `sql.SQL('...')` through its argument."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else node.value.decode('utf-8', 'replace') if isinstance(node.value, bytes) else '\x00'
    if isinstance(node, ast.JoinedStr):  # a hole whose expression is a constant is that constant (`f'is_{"admin"}'`)
        return ''.join(sql_text(v) if isinstance(v, ast.Constant) else str(v.value.value) if isinstance(v.value, ast.Constant) and isinstance(v.value.value, str) and v.conversion == -1 and v.format_spec is None else '\x00' for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return sql_text(node.left) + sql_text(node.right)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):  # each `%s` / `%(x)s` of the template is a hole, or the string constant that fills it; `%%` is a `%`
        args = list(node.right.elts) if isinstance(node.right, ast.Tuple) else [node.right]
        named = {k.value: v for k, v in zip(node.right.keys, node.right.values) if isinstance(k, ast.Constant)} if isinstance(node.right, ast.Dict) else {}
        positional = iter(args)

        def fill(m):
            if m.group(0) == '%%':
                return '%'
            for _ in range(m.group(0).count('*')):  # `%*d`: the width is an argument too
                next(positional, None)
            arg = named.get(m.group(1)) if m.group(1) else next(positional, None)
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)) or m.group(2) == '*':
                return '\x00'
            return arg.value[:int(m.group(2) or 0)] if m.group(2) is not None and m.group(3) in 'sra' else arg.value  # `%.15s` truncates the constant as Python does
        return re.sub(r'%%|%(?:\((\w+)\))?[#0\- +]*(?:\*|\d+)?(?:\.(\*|\d*))?[hlL]?([diouxXeEfFgGcrsa])', fill, sql_text(node.left))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format':  # constant arguments fill the template (`'is_{}'.format('admin')`)
        template = sql_text(node.func.value)

        def argument(value):
            return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else '\x00'
        try:
            return template.format(*[argument(a) for a in node.args], **{k.arg: argument(k.value) for k in node.keywords if k.arg})
        except (IndexError, KeyError, ValueError, AttributeError):
            return template
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'SQL' and node.args:
        return sql_text(node.args[0])
    return '\x00'


class _Scan(ast.NodeVisitor):
    """Each restricted read, attributed to EVERY function that holds it (the innermost and the ones around it: a nested function does not exempt the outer one; docstrings and bare strings
    are prose), and each SQL whose table name is not literal (kind 'dynamic')."""
    def __init__(self):
        self.stack, self.reads, self.writes, self.dynamics, self.defs = [], [], [], [], {}

    def owners(self):
        names = [name for name, _ in self.stack]
        return ['.'.join(names[:i + 1]) for i, (_, is_function) in enumerate(self.stack) if is_function] or ['<module>']

    def read(self, kind, locked=False):
        self.reads += [(owner, kind, locked) for owner in self.owners()]

    def sql(self, text):
        for kind, locked in sql_reads(text):
            self.read(kind, locked)
        self.writes += [(self.owners()[-1], table) for table in sql_writes(text)]
        if sql_dynamic(text):
            self.read('dynamic')
            self.dynamics += [(owner, ' '.join(text.split())) for owner in self.owners()]

    def visit_FunctionDef(self, node):
        qualified = '.'.join([name for name, _ in self.stack] + [node.name])
        self.defs[qualified] = self.defs.get(qualified, 0) + 1
        self.stack.append((node.name, True))
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.stack.append((node.name, False))
        self.generic_visit(node)
        self.stack.pop()

    def visit_Expr(self, node):
        if not isinstance(node.value, ast.Constant):
            self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            self.sql(node.value)
        elif isinstance(node.value, bytes):
            self.sql(node.value.decode('utf-8', 'replace'))

    def pieces(self, node):
        """The parts of a composition that was already read whole (`sql_text`): its constants are not read again one by one, and what is not text (an argument, an expression) is visited as usual."""
        if isinstance(node, ast.Constant):
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            self.pieces(node.left)
            if isinstance(node.op, ast.Add):
                self.pieces(node.right)
            else:
                self.visit(node.right)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    self.visit(value.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format':
            self.pieces(node.func.value)
            for argument in [*node.args, *(k.value for k in node.keywords)]:
                self.visit(argument)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'SQL' and node.args:
            self.pieces(node.args[0])
        else:
            self.visit(node)

    def visit_JoinedStr(self, node):
        self.sql(sql_text(node))
        self.pieces(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, (ast.Add, ast.Mod)):  # the whole composition once: its prefixes are not statements, and a hole in a prefix is not a hole of a table name
            self.sql(sql_text(node))
            self.pieces(node)
        else:
            self.generic_visit(node)

    def visit_Subscript(self, node):
        if isinstance(node.slice, ast.Constant) and node.slice.value == 'is_admin':
            self.read('is_admin')
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr == 'is_admin' and isinstance(node.ctx, ast.Load):
            self.read('is_admin')
        self.generic_visit(node)

    def visit_Call(self, node):
        name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
        literal = node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value
        if name == 'get' and isinstance(node.func, ast.Attribute) and literal == 'is_admin' or name == 'getattr' and len(node.args) > 1 and getattr(node.args[1], 'value', None) == 'is_admin':
            self.read('is_admin')
        if name == 'format' and isinstance(node.func, ast.Attribute):
            self.sql(sql_text(node))
            self.pieces(node)
            return
        if name == 'dict' and any(keyword.arg == 'is_admin' for keyword in node.keywords):  # `dict(is_admin=...)` names the field like a literal key does: a read
            self.read('is_admin')
        if name == 'Identifier':  # a table named by an identifier object is as unseen as an f-string
            self.read('dynamic')
            self.dynamics += [(owner, '') for owner in self.owners()]
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value in READ_TABLES:
                    self.read(arg.value)
        self.generic_visit(node)


@functools.lru_cache(maxsize=None)
def scan(source):
    visitor = _Scan()
    try:
        visitor.visit(ast.parse(source))
    except RecursionError:  # a source nested deeper than the walk can follow: red for the whole module, never an error
        visitor.reads.append(('<module>', 'unparseable SQL', False))
    return visitor


def reads_outside_the_resolver(sources):
    """({'file:function': kinds}, stale entries): each read that is neither in the resolver nor within its listed exception (and each SQL with a table that is not literal and not on
    DYNAMIC_SQL), and the entries of the closed lists that no longer cover what they declare."""
    outside, used, dynamic = {}, set(), set()
    for file, source in sorted(sources.items()):
        scanned = scan(source)
        for function, kind, locked in scanned.reads:
            key = (file, function)
            if scanned.defs.get(function, 0) > 1 and (key in RESOLVER or key in READ_EXCEPTIONS or key in DYNAMIC_SQL):  # two definitions of one qualified name: neither inherits the entry
                outside.setdefault('%s:%s' % key, set()).add('duplicate definition')
                continue
            if kind == 'dynamic':
                if key in DYNAMIC_SQL:
                    dynamic.add(key)
                else:
                    outside.setdefault('%s:%s' % key, set()).add('unknown table')
                continue
            if key in RESOLVER:
                continue
            if key in READ_EXCEPTIONS and kind in READ_EXCEPTIONS[key][0] and (locked or not READ_EXCEPTIONS[key][1]):
                used.add((key, kind))
                continue
            outside.setdefault('%s:%s' % key, set()).add(kind)
    stale = ['%s:%s reads %s' % (key + (kind,)) for key, (tables, _, _) in READ_EXCEPTIONS.items() for kind in sorted(tables) if (key, kind) not in used]
    stale += ['%s:%s composes no table' % key for key in DYNAMIC_SQL if key not in dynamic]
    return {key: sorted(kinds) for key, kinds in outside.items()}, sorted(stale)


def _find_function(tree, qualified):
    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if '.'.join(prefix + [child.name]) == qualified:
                    return child
                found = walk(child, prefix + [child.name])
            else:
                found = walk(child, prefix + [child.name] if isinstance(child, ast.ClassDef) else prefix)
            if found:
                return found
    return walk(tree, [])


def spelled_tables(sources, file, function):
    """The tables a function names as constants (`'memory.documents'`): what a statement composed from its variables can reach. Read from the function (named with its class), so a new one added there is seen."""
    node = _find_function(ast.parse(sources[file]), function)
    if node is None:
        return set()
    return {m.group(1) for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) for m in [re.fullmatch(r'memory\.(\w+)', n.value)] if m}


def dynamic_table_violations(sources=None):
    """The tables a DYNAMIC_SQL entry can reach, against the source of truth: a credential or grant table where nobody reads it as a resource, or a write to a restricted table the entry
    does not declare, is a problem. An entry that can reach 'any table' may only compose SELECTs."""
    sources, problems = sources or package_sources(), []
    for (file, function), (tables, writes, _, extra) in sorted(DYNAMIC_SQL.items()):
        reach = {str(name).replace('"', '').strip().lower() for name in tables(sources)} if tables else None  # `'API_KEYS'`, `'"actors"'` and `'api_keys '` are those tables
        if reach is None:
            texts = [text for owner, text in scan(sources[file]).dynamics if owner == function and text]
            if not texts or any(not re.match(r'\s*SELECT\b', text, re.I) for text in texts):
                problems.append('%s:%s may reach any table and composes something that is not a SELECT' % (file, function))
        else:
            problems += ['%s:%s spells no table: what can it reach?' % (file, function)] if not reach else []
            problems += ['%s:%s can reach %s, a table whose rows decide an access' % (file, function, table) for table in sorted(reach & set(READ_TABLES))]
            problems += ['%s:%s can write %s, which it does not declare' % (file, function, table) for table in sorted(reach & set(WRITE_TABLES) - writes)]
        problems += extra() if extra else []
    return problems


def writes_outside_the_writers(sources):
    return sorted({'%s:%s %s' % (file, function, table) for file, source in sources.items() if file not in PERMISSION_WRITERS for function, table in scan(source).writes})


@functools.lru_cache(maxsize=None)
def _package_sources():
    return {str(path.relative_to(PACKAGE)).replace('\\', '/'): path.read_text(encoding='utf-8') for path in sorted(PACKAGE.rglob('*.py'))
            if 'tests' not in path.relative_to(PACKAGE).parts and '__pycache__' not in path.parts}


def package_sources():
    return dict(_package_sources())  # read once per process; a copy, so a test may add a module


def inject(source, qualified, body):
    """`source` with `body` (a statement or several, written with a 4-space base) put at the start of the function `qualified` ('Class.name' or 'name'): the mutant lives INSIDE the real function."""
    name = qualified.split('.')[-1]
    m = re.search(r'^( *)(?:async )?def %s\(.*\):[ ]*\n' % re.escape(name), source, re.M)
    assert m, qualified
    pad = m.group(1) + '    '
    lines = body.split('\n')
    text = '\n'.join([pad + lines[0]] + [pad + line[4:] for line in lines[1:]]) + '\n'
    return source[:m.end()] + text + source[m.end():]


class ResolverBoundaryTests(unittest.TestCase):
    """Only the resolver decides an access (CA-38 a): a read of `project_grants`, of the permissions of a key or of `actors.is_admin` anywhere else fails here unless it is one of the
    closed list of DC-1, each with its reason. And only four modules write the tables of permissions and credentials.

    METHOD (fix8 to fix10): EVERY SQL literal, once its constants are filled in and up to 32 768 characters, is parsed with the parser of PostgreSQL 17 (`pglast`, a dependency of the test image
    only); there is no lexical gate. Every hole (a non-constant expression, the `{}` `{name}` `{0}` of a template, a `%s` `%(x)s` `%d` placeholder) is an identifier no one writes before parsing;
    the tree decides what the text does: which tables it reads and writes (a RangeVar whose name or schema holds the hole is `unknown table`, in any position), whether it takes a whole row of
    `actors` (`*`, `a.*`, `a`, `(a).*`, `RETURNING *`, `TABLE`, `COPY ... TO`; scoped by query, CTE, subquery and statement), which `FOR SHARE` locks it holds. A write target is not a read, except
    that what a RETURNING gives back from a restricted table (whole or by column) is read from it; `LOCK TABLE`, `ANALYZE` and `VACUUM` read nothing; `ALTER TABLE`, `CREATE INDEX`, `RENAME` and
    `DROP` on a table of WRITE_TABLES write it. Every string inside the tree (an argument of `query_to_xml` or `dblink_exec`, the body of DO, CREATE FUNCTION or CREATE PROCEDURE) is read again
    by the same function, up to four levels deep. `is_admin` is the one rule that is not the parser's: any literal that spells the word, or any identifier the parser decodes to it, is a read.
    A text that does not parse (a syntax error, an unclosed comment, more than 32 768 characters, too deep for the walk) is reported by what it names: `memory.` followed by a hole
    (`memory."<hole>"`, `"memory".<hole>`, `MEMORY.<hole>`, `memory.api_<hole>`) is `unknown table`; `memory.<table of the guard>` is that table (`unparseable SQL`, a read, a write when
    a word of writing comes before it, `actors` as a whole row only with a star, `a.*`, `TABLE` or `COPY ... TO`); a table named without `memory.` counts only with a word of SQL. A text that does
    not parse and only has holes is prose and is silent. Both rules look at the text without its comments, except when a block comment never closes (then the whole text). Prose, a RAISE message or a
    PL/pgSQL string that names a table of the guard (with `memory.` or with a word of SQL) is red, and the package has none.

    The scan is a DETECTOR OF REGRESSIONS, not a proof of absence. Known limits, accepted:
    * SQL built in several steps (`sql += ...`, `' '.join(...)`) that never reaches one literal is judged piece by piece: a piece that spells `is_admin`, or parses and names a table, is caught
      by itself; a bare piece (`'memory.api_keys'`, `' WHERE x'`) is not;
    * a table name that is ENTIRELY a hole, without `memory.` (`FROM {}`), inside a statement that does not parse is not seen (with `memory.` it always is); the composition that uses it is, if it
      parses whole; `format('%I.%I', ...)` and `'memory.' || 'api_keys'` inside the SQL are not seen either;
    * block comments that nest (`/* /* */ */`) are cut at the first `*/`; `a$x$` is taken for the opening of a dollar quote; DDL on a whole schema (`GRANT ... ON ALL TABLES IN SCHEMA memory`,
      `ALTER SCHEMA memory ...`, `DROP OWNED`) and `INHERITS (memory.actors)` are not classified;
    * the body of a PL/pgSQL function or DO is not parsed as PL/pgSQL (`pglast.parse_plpgsql` needs a complete CREATE FUNCTION and every variable declared): it is read as a text that does not parse,
      and a bare INTO is not a write; a RAISE message that names a table of the guard is a false positive (red), the package has none;
    * prose that parses as SQL (`f'table {x}'`, `f'drop table {a}'`) is an unknown table; the package has none;
    * a hole whose value is DATA and names a table is `unknown table` where it stands in a table position, and the tables it may take are checked only per function (`DYNAMIC_SQL`), not per statement;
      a hole in a select list is taken for `a` or `*` when it stands alone and the level has `actors`; a hole in an alias or in any other column position is not;
    * inside a function of the closed list any `is_admin` passes, as in the functions of `probe.py` (the cost of having no silence by the shape of the SQL);
    * a literal that names no table of the guard (a variable holds it at run time) is out of reach, and a bare name with no word of SQL (`'web_sessions'`, a key of the retention windows) is not SQL;
    * a table reached through a function in FROM (`FROM {fn}(...)`), a view or a rule is not a RangeVar of the guard; a column named like the alias of `actors` is taken for its row;
    * `sql.Composed` / `sql.SQL(...).join(...)` with a write verb in a function that may reach any table (`inspect_store`, `table_digest`) is not told apart from a SELECT beyond its text;
    * the column `is_admin` is searched in the raw literal: a comment that names it is a false positive worth an exception, never a hole;
    * the parser is the one of PostgreSQL 17: syntax a later server accepts does not parse (and then the report above applies);
    * cost, measured in fix9 to fix12 (notes of T-02): the parser's lexer is quadratic in the number of block comments (`'/*' * 16000` took 1.7-1.8 s, `'/**/' * 16000 + 'x'` 1.75 s), so comments
      are cut out before parsing and an unclosed one is not parsed; series of `+` or `-` are quadratic in the lexer too and are bounded only by the cap of 32 768 characters;
      `test_the_cost_grows_linearly_with_the_input` compares n and 4n, and in practice acts as an absolute bound of 0.5 s on inputs that cost less than 0.06 s.
    PRINCIPLE (fix5): there is no silence by the shape of the SQL. Any `is_admin` in a literal outside the resolver is a read, also when it is written; a legitimate writer (`bootstrap_user`,
    `provision_locked`) is declared BY FUNCTION on the closed list. A new way of reading goes in `reads` below with its mutant, and a legitimate new reader or writer goes on the closed lists
    with its reason."""

    def test_only_the_resolver_and_the_closed_list_read_permissions_and_is_admin(self):
        sources = package_sources()
        self.assertGreaterEqual(len(sources), 30)
        outside, stale = reads_outside_the_resolver(sources)
        self.assertEqual(outside, {}, 'these functions read permissions or `is_admin` outside the resolver (move the read into it, or add the DC-1 exception with its reason): '
                         + '; '.join('%s [%s]' % (k, ', '.join(v)) for k, v in outside.items()))
        self.assertEqual(stale, [], 'on the closed list but it no longer reads (or no longer exists): remove it')
        for key, (tables, locked, reason) in READ_EXCEPTIONS.items():
            self.assertGreater(len(reason), 30, key)

    def test_only_four_modules_write_the_tables_of_permissions_and_credentials(self):
        sources = package_sources()
        self.assertEqual(writes_outside_the_writers(sources), [], 'only %s may write actors, project_grants, api_keys or web_sessions' % sorted(PERMISSION_WRITERS))
        # the writers do write: a scan that finds nothing would pass for the wrong reason
        self.assertEqual({file for file, source in sources.items() if scan(source).writes} & PERMISSION_WRITERS, {'store_auth.py', 'store_access.py', 'auth.py', 'probe.py'})

    def test_the_read_scan_sees_each_way_of_reading_outside_the_resolver(self):
        # mutants: a source that adds ONE read to the package must be reported; each variant is a way of dodging a plain text search
        reads = [
            "def leak(c):\n    return c.execute('SELECT g.* FROM memory.project_grants AS g WHERE g.actor_id=%s', (1,))",
            "def leak(c):\n    return c.execute('SELECT * FROM project_grants')",
            "def leak(c):\n    return c.execute('select permission  from\\n   MEMORY . project_grants')",
            "def leak(c):\n    return c.execute('WITH g AS (SELECT * FROM memory.project_grants) SELECT count(*) FROM g')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON k.id=p.id')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM memory.projects p, memory.api_keys k')",
            "def leak(c):\n    return c.execute('INSERT INTO memory.audit_events SELECT 1 FROM memory.project_grants')",
            "def leak(c):\n    return c.execute('DELETE FROM memory.audit_events USING memory.project_grants g')",
            "def leak(c):\n    return c.execute('SELECT id FROM memory.actors WHERE is_admin')",
            "def leak(c):\n    return c.execute('SELECT a.is_admin FROM memory.actors a')",
            "def leak(c):\n    return c.execute('UPDATE memory.audit_events SET x=1 WHERE EXISTS (SELECT 1 FROM memory.actors WHERE is_admin)')",
            "def leak(row):\n    return row['is_admin']",
            "def leak(actor):\n    return actor.get('is_admin')",
            "def leak(actor):\n    def inner():\n        return actor['is_admin']\n    return inner",
            "def leak(c):\n    return c.execute(f'SELECT * FROM memory.api_keys WHERE id=%s {x}')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM memory.api_keys FOR SHARE')",  # a lock outside the two listed functions is not covered by their exception
        ]
        reads += [  # fix1 gap 3: indirect reads of `actors.is_admin` (a star, an alias star, an attribute); gap 4: the other ways of reading; gap 5: nesting; gap 2: a table that is not literal
            "def leak(c):\n    return c.execute('SELECT * FROM memory.actors WHERE id=%s')",
            "def leak(c):\n    return c.execute('SELECT a.* FROM memory.actors a')",
            "def leak(c):\n    return c.execute('SELECT id, a.* FROM memory.actors AS a')",
            "def leak(actor):\n    return actor.is_admin",
            "def leak(actor):\n    return getattr(actor, 'is_admin')",
            "def leak(c):\n    return c.execute('TABLE memory.project_grants')",
            "def leak(c):\n    return c.execute('COPY memory.api_keys TO STDOUT')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM /* x */ memory.project_grants')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM -- x\\n memory.api_keys')",
            "def leak(c):\n    return c.execute('UPDATE memory.audit_events SET y=a.is_admin FROM memory.actors a WHERE a.id=%s')",
            "def leak(c):\n    return c.execute('SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON true FOR SHARE OF p')",  # it locks `p`, not the credentials
            "def _authorized(c):\n    return c.execute('SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON true FOR SHARE OF p')",
            "def leak(c):\n    def _active(c):\n        return c.execute('SELECT * FROM memory.project_grants')\n    return _active(c)",
            "def leak(actor):\n    def _global_admin():\n        return actor['is_admin']\n    return _global_admin()",
            "def leak(c, t):\n    return c.execute(f'SELECT count(*) FROM memory.{t}')",
            "def leak(c, t):\n    return c.execute(f'DELETE FROM {t} WHERE id=%s')",
            "def leak(c, t):\n    return c.execute('SELECT count(*) FROM memory.' + t)",
            "def leak(c, t):\n    return c.execute('SELECT * FROM mem' + 'ory.project_' + 'grants')",
            "def leak(c, t):\n    return c.execute('DELETE FROM memory.%s WHERE id=%%s' % t)",
            "def leak(c, t):\n    return c.execute('UPDATE memory.{} SET x=1'.format(t))",
            "def leak(c):\n    return c.execute('SELECT scopes FROM %s WHERE id=%%s' % 'memory.api_keys')",  # fix2 gap 2: a Python `%` whose hole is a table
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM %s' % t)",
            "def leak(c, t):\n    return c.execute('COPY %s TO STDOUT' % t)",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM memory.projects p JOIN %s k ON true' % (t,))",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM memory.projects p, %s k' % t)",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM %(t)s' % {'t': t})",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM %(t)s' % {'t': 'memory.project_grants'})",
            "def leak(c, t):\n    return c.execute('DELETE FROM %s WHERE id=%%s' % t)",
            "def leak(c, t):\n    return c.execute('UPDATE %s SET x=1' % t)",
            "def leak(c, t):\n    return c.execute('INSERT INTO %s VALUES(1)' % t)",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM memory.projects p, memory.documents d, %s k' % t)",  # fix3 gap 3: the third table of a list, and a quoted hole
            "def leak(c, t):\n    return c.execute(f'SELECT 1 FROM memory.projects p, memory.documents d, {t} k')",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM memory.projects, memory.documents, memory.items, %s' % t)",
            "def leak(c, t):\n    return c.execute('SELECT 1 FROM memory.\"%s\"' % t)",
            "def leak(c, t):\n    return c.execute(f'SELECT 1 FROM \"{t}\"')",
            "def leak(c, t):\n    return c.execute(f'DELETE FROM memory.\"{t}\" WHERE id=%s')",
            "def leak(c):\n    from psycopg import sql\n    return c.execute(sql.SQL('SELECT 1 FROM {}').format(sql.Identifier('memory', 'project_grants')))",
            "def leak(c, t):\n    from psycopg import sql\n    return c.execute(sql.SQL('SELECT 1 FROM memory.{}').format(sql.Identifier(t)))",
        ]
        base = package_sources()
        for read in reads:
            with self.subTest(read=read):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': read + '\n'})
                self.assertTrue(any(key.startswith('newmod.py:') for key in outside), read)
        # the same text inside a listed function is covered only for the tables and the locks that exception names
        outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': inject(base['store_auth.py'], 'AuthMixin.list_users', "c.execute('SELECT * FROM memory.api_keys')")})
        self.assertIn('store_auth.py:AuthMixin.list_users', outside)
        outside, _ = reads_outside_the_resolver({**base, 'corpus_answers.py': inject(base['corpus_answers.py'], 'CorpusAnswers._authorized', "c.execute('SELECT * FROM memory.api_keys WHERE id=%s')")})
        self.assertIn('corpus_answers.py:CorpusAnswers._authorized', outside)

    def test_the_access_writers_read_is_admin_only_where_the_closed_list_says(self):
        # T-13 and T-14: `_set_disabled` reads `is_admin` of the target and counts the active administrators, `replace_grants` reads the grants it replaces; without its entry each one is
        # outside the resolver, and an entry does not cover a sibling
        base = package_sources()
        for key in (('store_access.py', 'AccessMixin._set_disabled'), ('store_access.py', 'AccessMixin.replace_grants'), ('store_access.py', 'AccessMixin.rotate_key')):
            with patch.dict(READ_EXCEPTIONS):
                del READ_EXCEPTIONS[key]
                outside, _ = reads_outside_the_resolver(base)
            self.assertEqual(sorted(outside), ['%s:%s' % key], key)
        outside, _ = reads_outside_the_resolver({**base, 'store_access.py': inject(base['store_access.py'], 'AccessMixin.set_user_disabled', "self.c.execute('SELECT 1 FROM memory.project_grants')")})
        self.assertEqual(sorted(outside), ['store_access.py:AccessMixin.set_user_disabled'])

    def test_probe_is_listed_by_function_not_by_wildcard(self):
        # fix1 gap 1: DC-1 closes the probe exception to three functions; a new function of probe.py that reads the grants is outside the resolver
        base = package_sources()
        for read in ("c.execute('SELECT * FROM memory.project_grants')", "c.execute('SELECT 1 FROM memory.api_keys')", "c.execute('SELECT is_admin FROM memory.actors')"):
            outside, _ = reads_outside_the_resolver({**base, 'probe.py': base['probe.py'] + '\n\ndef sneaky(c):\n    return ' + read + '\n'})
            self.assertIn('probe.py:sneaky', outside, read)
        self.assertEqual({function for (file, function) in READ_EXCEPTIONS if file == 'probe.py'}, {'probe_state', 'admin_actor', 'provision_locked'})
        self.assertNotIn(('probe.py', '*'), READ_EXCEPTIONS)

    def test_a_table_name_that_is_not_literal_is_unknown_unless_it_is_on_the_closed_list_and_its_tables_are_checked(self):
        # fix1 gap 2: the dynamic SQL of the package is the closed list DYNAMIC_SQL; each entry's possible tables are checked against the source of truth
        base = package_sources()
        outside, stale = reads_outside_the_resolver(base)
        self.assertEqual(outside, {})
        self.assertEqual(stale, [])
        self.assertEqual(dynamic_table_violations(), [])
        with patch.dict(admin.RETENTION_TABLES, {'api_keys': ('true', '')}):
            self.assertTrue(dynamic_table_violations(), 'a credential table in the retention list must fail')
        with patch.dict(admin.RETENTION_TABLES, {'project_grants': ('true', '')}):
            self.assertTrue(dynamic_table_violations())
        with patch.dict(admin.RETENTION_TABLES, {'actors': ('true', '')}):
            self.assertTrue(dynamic_table_violations())
        with patch.dict(admin.RETENTION_TABLES, {'web_sessions': ('true', '')}):
            self.assertTrue(dynamic_table_violations(), 'the retention of sessions must keep to dead sessions')
        # an entry that spells a credential table as a constant of its function (the two tables of a job) is caught as well
        jobs = base['store_jobs.py'].replace("table='memory.documents' if row['resource_type']=='document' else 'memory.memory_items'", "table='memory.api_keys' if row['resource_type']=='document' else 'memory.memory_items'")
        self.assertNotEqual(jobs, base['store_jobs.py'])
        self.assertTrue(dynamic_table_violations({**base, 'store_jobs.py': jobs}))
        # an entry that may reach any table and composes something other than a SELECT is caught too
        backup = base['backup.py'].replace("sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t')", "sql.SQL('DELETE FROM memory.{} t')")
        self.assertNotEqual(backup, base['backup.py'])
        self.assertTrue(dynamic_table_violations({**base, 'backup.py': backup}))
        # the statements of the package that compose a table are what the list holds
        self.assertEqual({function for (file, function) in DYNAMIC_SQL if file == 'admin.py'}, {'prune_tables', 'inspect_store', 'derive_single_fragment'})

    def test_login_may_read_the_whole_row_and_nothing_else_of_is_admin(self):
        # fix2 gap 1: the exception of `login` is the `SELECT *` of the actor row, not any read of `is_admin`
        base = package_sources()
        for body in ("return row['is_admin']", "return row.get('is_admin')", "return row.is_admin", "return c.execute('SELECT 1 FROM memory.actors WHERE is_admin')",
                     "return c.execute('SELECT id FROM memory.actors WHERE username=%s AND NOT is_admin')"):
            outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
            self.assertIn('auth.py:Auth.login', outside, body)
        for body in ("return c.execute('SELECT * FROM memory.actors WHERE username=%s AND NOT disabled')", "return c.execute('SELECT a.* FROM memory.actors a WHERE a.username=%s')"):
            outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
            self.assertNotIn('auth.py:Auth.login', outside, body)
        # and the same star anywhere else is a read of the whole row
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': "def leak(c):\n    return c.execute('SELECT * FROM memory.actors')\n"})
        self.assertEqual(outside['newmod.py:leak'], ['is_admin:row'])

    def test_a_literal_is_admin_is_a_read_wherever_it_is_and_inside_login_only_the_whole_row_is(self):
        # fix3 gap 1: no SQL word is needed in the literal: each of these reads `is_admin` and is a violation in a new module and inside `login`
        bodies = [
            "return itemgetter('is_admin')(row)", "return attrgetter('is_admin')(row)", "return row.__getitem__('is_admin')", "return row.pop('is_admin')", "return row.setdefault('is_admin', 0)",
            "return 'is_admin' in row", "k = 'is_admin'\n    return row[k]", "match row:\n        case {'is_admin': True}:\n            return 1", "return row['is_' + 'admin']",
            "q = 'SELECT id FROM memory.actors WHERE username=%s'\n    q += ' AND is_admin'\n    return c.execute(q)",
            "COLS = 'id, username, is_admin'\n    return c.execute(f'SELECT {COLS} FROM memory.actors')",
            "q = 'SELECT id FROM memory.actors'\n    return c.execute(q + ' ORDER BY is_admin DESC')",
            "q = 'SELECT id'\n    q += ', bool_or(a.is_admin)'\n    return c.execute(q + ' FROM memory.actors a')",
        ]
        base = package_sources()
        for body in bodies:
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(row, c):\n    ' + body + '\n'})
                self.assertIn('newmod.py:leak', outside, body)
                outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
                self.assertIn('auth.py:Auth.login', outside, body)
    def test_every_is_admin_literal_is_a_read_outside_the_closed_list_even_when_it_is_written(self):
        # fix4 and fix5: there is NO silence by the shape of the SQL; a legitimate writer is declared by function on READ_EXCEPTIONS (and inside it anything passes, as in probe.py)
        bodies = [
            "return c.execute('SELECT 1 FROM memory.projects WHERE %(is_admin)s OR owner_id=%(id)s', actor)", "return c.execute('SELECT %(is_admin)s', actor)",
            "return c.execute('SELECT CASE WHEN %(is_admin)s THEN 1 ELSE 0 END', actor)", "return c.execute('INSERT INTO memory.audit_events(action) VALUES (%(is_admin)s)', actor)",
            "return c.execute('UPDATE memory.actors SET disabled=true WHERE id=%(is_admin)s', actor)",
            "PUBLIC = {'username': 'name', 'is_admin': 'admin'}\n    return {v: row[k] for k, v in PUBLIC.items()}", "return {'is_admin': True}.items() <= row.items()",
            "for k in {'is_admin': 1}:\n        return row[k]", "return {'x': 1, 'is_admin': 2}", "return dict(is_admin=True).items() <= row.items()",
            "return c.execute('UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING is_admin')", "return c.execute('DELETE FROM memory.actors WHERE id=%s RETURNING is_admin')",
            "return c.execute('UPDATE memory.audit_events SET x=1 FROM memory.actors a WHERE a.id=%s RETURNING a.is_admin')",
            "return c.execute('DELETE FROM memory.audit_events USING memory.actors a WHERE true RETURNING a.is_admin')",
            "return c.execute('INSERT INTO memory.actors(id,username) VALUES(%s,%s) RETURNING (SELECT is_admin FROM memory.actors WHERE id=%s)')",
            "return c.execute('INSERT INTO memory.audit_events(action) VALUES(%s) RETURNING (SELECT is_admin FROM memory.actors WHERE id=%s)')",
            "return c.execute('SELECT id, is_admin = true FROM memory.actors')", "return c.execute('UPDATE memory.audit_events SET a=1, is_admin = 2')",
            "return c.execute('INSERT INTO memory.audit_events(id,is_admin) VALUES(%s,%s)')",
            # fix5 gaps 1-5: the right side of a SET tuple, the statement after `;`, the stored value an upsert returns, the placeholder in a VALUES, a comparison inside a function
            "return c.execute('UPDATE memory.actors SET (disabled) = (SELECT is_admin FROM memory.actors WHERE id=%s)')", "return c.execute('UPDATE memory.actors SET (disabled, username) = (NOT is_admin, %s)')",
            "return c.execute('INSERT INTO memory.actors(id) VALUES(%s) RETURNING id; UPDATE memory.actors SET disabled = NOT is_admin')",
            "return c.execute('INSERT INTO memory.actors(id,username) VALUES(%s,%s) ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username RETURNING id, is_admin')",
            "return c.execute('INSERT INTO memory.actors(id,is_admin) VALUES(%s,%s) ON CONFLICT (id) DO UPDATE SET is_admin=EXCLUDED.is_admin RETURNING id')",
            "return c.execute('INSERT INTO memory.actors(id,is_admin) VALUES(%s, NOT %(is_admin)s)', actor)", "return c.execute('INSERT INTO memory.actors(id,is_admin) VALUES(%s, CASE WHEN %(is_admin)s THEN 1 END)', actor)",
            "return c.execute('UPDATE memory.actors SET disabled = coalesce(%s, is_admin = true)')", "return c.execute('UPDATE memory.actors SET disabled=true; SELECT is_admin FROM memory.actors')",
            # and the plain writes, which are reads of the literal too outside the list
            "return c.execute('INSERT INTO memory.actors(id,username,is_admin) VALUES(%(id)s,%(username)s,%(is_admin)s)', actor)", "return c.execute('UPDATE memory.actors SET is_admin = %s')",
            "return c.execute('UPDATE memory.actors SET is_admin=%(is_admin)s WHERE id=%(id)s', actor)", "return c.execute('UPDATE memory.actors SET (disabled, is_admin) = (%s, %s)')",
            "return c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true) RETURNING id,username,is_admin')",
            "return c.execute('UPDATE memory.actors SET disabled=true, is_admin=false WHERE id=%s')",
        ]
        base = package_sources()
        for body in bodies:
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(row, c, actor):\n    ' + body + '\n'})
                self.assertIn('newmod.py:leak', outside, body)
                outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
                self.assertIn('auth.py:Auth.login', outside, body)
        # a value that is stored in the dict of a response is a read too, and the real INSERT of `bootstrap_user` is not
        self.assertTrue(any(kind == 'is_admin' for _, kind, _ in scan("def w(row):\n    return {'x': row['is_admin']}").reads))
        # the one legitimate writer of the package is declared BY FUNCTION: bootstrap_user stays green, a function that does the same without being declared is red, and a ghost entry is stale
        self.assertIn(('store_auth.py', 'AuthMixin.bootstrap_user'), READ_EXCEPTIONS)
        self.assertEqual(reads_outside_the_resolver(base), ({}, []))
        copy = base['store_auth.py'].replace('def bootstrap_user(', 'def bootstrap_user_renamed(')
        self.assertNotEqual(copy, base['store_auth.py'])
        outside, stale = reads_outside_the_resolver({**base, 'store_auth.py': copy})
        self.assertEqual(outside['store_auth.py:AuthMixin.bootstrap_user_renamed'], ['is_admin'])
        self.assertEqual(stale, ['store_auth.py:AuthMixin.bootstrap_user reads is_admin'])
        with patch.dict(READ_EXCEPTIONS, {('store_auth.py', 'ghost'): ({'is_admin'}, False, 'a function that does not exist and must be stale, as the entries above are')}):
            self.assertEqual(reads_outside_the_resolver(base)[1], ['store_auth.py:ghost reads is_admin'])
        # a whole row through a parenthesised alias, and the precision `.` of a conversion without digits
        self.assertEqual(sql_reads('SELECT (a).* FROM memory.actors a'), {('is_admin:row', False)})
        self.assertEqual(sql_text(ast.parse("'FROM %.s %s' % ('x', 'memory.api_keys')", mode='eval').body), 'FROM  memory.api_keys')

    def test_the_closed_lists_name_the_function_with_its_class_and_a_homonym_does_not_inherit(self):
        # fix6 gap 2: `AuthMixin.bootstrap_user`, not `bootstrap_user`; a second definition of the same qualified name, or a method of another class, is red
        base = package_sources()
        write = "c.execute('SELECT is_admin FROM memory.actors')"
        outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + '\n\nclass Other:\n    def bootstrap_user(self, c):\n        return ' + write + '\n'})
        self.assertEqual(outside['store_auth.py:Other.bootstrap_user'], ['is_admin'])
        outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + '\n\ndef bootstrap_user(c):\n    return ' + write + '\n'})
        self.assertEqual(outside['store_auth.py:bootstrap_user'], ['is_admin'])
        for second in ('\n\nclass AuthMixin:\n    def bootstrap_user(self, c):\n        return 1\n', '\n\nclass AuthMixin:\n    def list_keys(self, c):\n        return 1\n'):
            outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + second})
            self.assertTrue(any('duplicate definition' in kind for kinds in outside.values() for kind in kinds), second)
        # the real one stops writing and a homonym exists: the entry is stale
        quiet = base['store_auth.py'].replace('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true) RETURNING id,username,is_admin', 'INSERT INTO memory.actors(id,username,password_hash) VALUES(%s,%s,%s) RETURNING id,username')
        self.assertNotEqual(quiet, base['store_auth.py'])
        _, stale = reads_outside_the_resolver({**base, 'store_auth.py': quiet + '\n\nclass Other:\n    def bootstrap_user(self, c):\n        return ' + write + '\n'})
        self.assertIn('store_auth.py:AuthMixin.bootstrap_user reads is_admin', stale)
        for second in ('\n\nclass AuthMixin:\n    def _active(self, c):\n        return c.execute("SELECT * FROM memory.project_grants")\n',):  # RESOLVER
            outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + second})
            self.assertTrue(any('duplicate definition' in kind for kinds in outside.values() for kind in kinds), second)
        outside, _ = reads_outside_the_resolver({**base, 'store_jobs.py': base['store_jobs.py'] + '\n\nclass JobsMixin:\n    def claim_job(self, c, t):\n        return c.execute("SELECT 1 FROM memory." + t)\n'})  # DYNAMIC_SQL
        self.assertTrue(any('duplicate definition' in kind for kinds in outside.values() for kind in kinds))
        before = 'class Other:\n    def claim_job(self):\n        return "memory.api_keys"\n\n' + base['store_jobs.py']  # a homonym BEFORE the real class does not change what the real one can reach
        self.assertEqual(spelled_tables({**base, 'store_jobs.py': before}, 'store_jobs.py', 'JobsMixin.claim_job'), spelled_tables(base, 'store_jobs.py', 'JobsMixin.claim_job'))
        self.assertTrue(spelled_tables(base, 'store_jobs.py', 'JobsMixin.claim_job'))
        # the resolver and the dynamic entries are qualified too: a homonym of `_active` or of a job function does not inherit
        outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + '\n\nclass Other:\n    def _active(self, c):\n        return c.execute(\'SELECT * FROM memory.project_grants\')\n'})
        self.assertIn('store_auth.py:Other._active', outside)
        outside, _ = reads_outside_the_resolver({**base, 'store_jobs.py': base['store_jobs.py'] + '\n\nclass Other:\n    def claim_job(self, c, t):\n        return c.execute("SELECT 1 FROM memory." + t)\n'})
        self.assertIn('store_jobs.py:Other.claim_job', outside)

    def test_a_whole_row_of_actors_is_is_admin_row_however_it_is_asked_for_and_nothing_swallows_what_follows(self):
        # fix6 gaps 1 and 5: no `RETURNING` is cut before the search; `*`, `a.*`, `(a).*`, the whole table and the alias itself are a whole row
        base = package_sources()
        forms = [
            "SELECT * FROM memory.actors", "INSERT INTO memory.audit_events(id) VALUES(%s) RETURNING id; SELECT * FROM memory.actors WHERE id=%s", "DELETE FROM memory.audit_events WHERE id=%s RETURNING id; SELECT a.* FROM memory.actors a",
            "UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING *", "INSERT INTO memory.actors(id) VALUES(%s) ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username RETURNING *",
            "DELETE FROM memory.actors a WHERE id=%s RETURNING a.*", "TABLE memory.actors", "SELECT ALL * FROM memory.actors", "SELECT DISTINCT * FROM memory.actors", "SELECT memory.actors.* FROM memory.actors",
            "SELECT (memory.actors).* FROM memory.actors", "SELECT (a).* FROM memory.actors a", "SELECT a FROM memory.actors a", "SELECT id, a FROM memory.actors AS a", "SELECT actors FROM memory.actors",
            "SELECT ROW(a.*) FROM memory.actors a", "SELECT to_json(a.*) FROM memory.actors a",
            # fix7 gap 1: DISTINCT ON; gap 4: the target of a write is a source, a list item may be the alias, a cast, a parenthesised alias, a subselect, an item after a FROM inside a function
            "SELECT DISTINCT ON (username) * FROM memory.actors", "SELECT DISTINCT ON(username)* FROM memory.actors", "SELECT DISTINCT ON (a.x) * FROM memory.actors a",
            "SELECT DISTINCT ON (lower(username)) * FROM memory.actors", "SELECT DISTINCT ON (id) a FROM memory.actors a",
            "UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING id, *", "UPDATE memory.actors a SET disabled=true RETURNING (a).*", "UPDATE memory.actors a SET disabled=true RETURNING a",
            "UPDATE memory.actors a SET disabled=true RETURNING to_json(a.*)", "MERGE INTO memory.actors a USING x ON true WHEN MATCHED THEN DELETE RETURNING *", "COPY memory.actors TO STDOUT",
            "UPDATE memory.audit_events SET x=1 FROM memory.actors a WHERE a.id=%s RETURNING a.*", "SELECT extract(epoch FROM now()), a FROM memory.actors a", "SELECT (a) FROM memory.actors a",
            "SELECT a::text FROM memory.actors a", "SELECT ARRAY(SELECT a FROM memory.actors a)",
            # fix8: what the regular expressions could not see
            "SELECT x IS DISTINCT FROM y, a.* FROM memory.actors a", "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY x), a.* FROM memory.actors a",
            "SELECT t.j FROM memory.actors a, LATERAL (SELECT to_jsonb(a.*) AS j) t", "SELECT 1 FROM memory.actors a WHERE to_jsonb(a.*) @> %s", "SELECT 1 FROM memory.actors a ORDER BY row(a.*)",
            "UPDATE memory.actors SET note='admin update' WHERE id=%s RETURNING *", "MERGE INTO memory.actors a USING x ON a.id=x.id WHEN MATCHED THEN UPDATE SET disabled=true RETURNING *",
            "SELECT $$x$$, a.* FROM memory.actors a", "SELECT $$ ' $$, a.* FROM memory.actors a", "SELECT E'\\'', a.* FROM memory.actors a", "SELECT DISTINCT ON (lower(trim(username))) * FROM memory.actors",
            'SELECT "a" FROM memory.actors AS "a"', "SELECT a FROM memory.actors AS a(i,u,p,adm)", "SELECT CAST(a AS text) FROM memory.actors a", "SELECT ((a)).* FROM memory.actors a",
            "WITH x AS (SELECT 1) SELECT * FROM memory.actors", "SELECT * FROM (SELECT * FROM memory.actors) t", "SELECT 1 FROM x WHERE EXISTS (SELECT a FROM memory.actors a)",
            "DELETE FROM memory.web_sessions s USING memory.actors a WHERE s.actor_id=a.id RETURNING *",
        ]
        for form in forms:
            with self.subTest(form=form):
                self.assertIn(('is_admin:row', False), sql_reads(form), form)
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c):\n    return c.execute(%r)\n' % form})
                self.assertEqual(outside['newmod.py:leak'], ['is_admin:row'], form)
        for form in ("SELECT count(*) FROM memory.actors", "SELECT * FROM memory.projects", "INSERT INTO memory.projects(id) VALUES(%s) RETURNING *", "SELECT a FROM memory.projects a",
                     "SELECT 1 FROM memory.actors a WHERE a.id=%s", "UPDATE memory.projects SET title=%s WHERE id=%s RETURNING a.*", "SELECT a.id FROM memory.actors a", "SELECT count(a.*) FROM memory.projects a",
                     # fix7 gap 3: a RETURNING that is not the one of a write on `actors`, and `count(p.*)` over another alias, are not a whole row
                     "WITH u AS (UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING id) INSERT INTO memory.audit_events(id) VALUES(%s) RETURNING *",
                     "UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING id; INSERT INTO memory.audit_events(id) VALUES(%s) RETURNING *",
                     "SELECT count(p.*) FROM memory.projects p JOIN memory.actors a ON true", "UPDATE memory.actors SET disabled=true WHERE id=%s RETURNING id, username",
                     "INSERT INTO memory.actors(id,username) VALUES(%s,%s) RETURNING id",
                     # fix8: other tables, each by name
                     "DELETE FROM memory.web_sessions s USING memory.actors a WHERE s.actor_id=a.id RETURNING s.*", "DELETE FROM memory.web_sessions WHERE id=%s RETURNING *",
                     "INSERT INTO memory.audit_events(id) SELECT a.id FROM memory.actors a RETURNING *", "UPDATE memory.web_sessions s SET revoked_at=now() RETURNING s.*",
                     "COPY memory.actors FROM STDIN", "SELECT s.* FROM memory.web_sessions s JOIN memory.actors a ON a.id=s.actor_id", "WITH u AS (SELECT 1) UPDATE memory.audit_events SET x=1 RETURNING *"):
            self.assertEqual(sql_reads(form), set(), form)

    def test_the_parser_tells_which_table_a_statement_reads_writes_and_locks(self):
        # fix8: kinds by the tree of the statement
        self.assertEqual(sql_reads("UPDATE memory.api_keys k SET revoked_at=now() FROM memory.actors a WHERE k.actor_id=a.id RETURNING k.*"), {('api_keys', False)})
        self.assertEqual(sql_reads("UPDATE memory.api_keys SET revoked_at=now() WHERE id=%s"), set())  # a write target is not a read
        self.assertEqual(sql_reads("UPDATE memory.api_keys SET revoked_at=now() WHERE id=%s RETURNING id"), {('api_keys', False)})  # but what it returns is
        self.assertEqual(sql_reads("DELETE FROM memory.project_grants WHERE actor_id=%s RETURNING *"), {('project_grants', False)})
        self.assertEqual(sql_writes("COPY memory.actors FROM STDIN"), {'actors'})
        self.assertEqual(sql_writes("WITH d AS (DELETE FROM memory.api_keys RETURNING id) SELECT count(*) FROM d"), {'api_keys'})
        self.assertEqual(sql_writes("TRUNCATE TABLE memory.project_grants, memory.projects"), {'project_grants'})
        self.assertEqual(sql_reads("SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON true FOR SHARE OF k"), {('api_keys', True)})
        self.assertEqual(sql_reads("SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON true FOR SHARE OF p"), {('api_keys', False)})
        self.assertEqual(sql_reads("SELECT 1 FROM memory.api_keys FOR NO KEY UPDATE"), {('api_keys', False)})
        self.assertEqual(sql_reads("SELECT 1 FROM memory.api_keys k WHERE k.id IN (SELECT id FROM memory.api_keys)"), {('api_keys', False)})
        self.assertEqual(sql_reads("SELECT 1 FROM memory.projects FOR SHARE"), set())
        self.assertEqual(sql_reads("SELECT FROM WHERE memory.api_keys (("), {('unparseable SQL', False), ('api_keys', False)})
        self.assertEqual(sql_reads("SELECT \x00 FROM memory.embeddings e WHERE e.v \x00"), set())  # a hole outside a table position, in a text that names none of the tables: nothing
        self.assertEqual(sql_reads("Update the cache and say so"), set())  # prose that begins like a statement and names none of the tables: nothing
        for text in ("SELECT 1 FROM memory.api_{kind}", "SELECT 1 FROM {}", "DELETE FROM memory.{t} WHERE true", "SELECT 1 FROM a, \x00 b", "SELECT 1 FROM memory.\x00", "SELECT 1 FROM \"{t}\"", "TRUNCATE {t}", "COPY \x00 TO STDOUT",
                     "SELECT 1 FROM ONLY {t}", "SELECT 1 FROM a, LATERAL (SELECT 1 FROM {t}) x", "COPY {t} TO STDOUT", "SELECT 1 FROM /* c */ {t}", "SELECT 1 FROM {0}", "SELECT 1 FROM memory.%d"):
            self.assertTrue(sql_dynamic(text), text)
        self.assertFalse(sql_dynamic("SELECT {x}, 1 FROM memory.projects WHERE a = {y}"))
        self.assertEqual(sql_reads("Update {x} failed"), set())  # prose with braces and no table of the guard: not analysed
        for text in ("DELETE FROM memory.%s WHERE id=%s", 'DELETE FROM memory."%s" WHERE id=%s', "SELECT 1 FROM a JOIN b ON a.x=b.x, memory.%(t)s"):
            self.assertTrue(sql_dynamic(text), text)  # a raw `%s` after the schema can only be a hole of a Python `%` applied elsewhere
        self.assertFalse(sql_dynamic("SELECT 1 FROM memory.projects WHERE id IS DISTINCT FROM %s"))

    def test_every_literal_that_names_a_table_of_the_guard_or_holds_a_hole_is_analysed_whatever_it_begins_with(self):
        # fix9 gaps 1 and 2: fragments, EXPLAIN, PREPARE, CALL, DECLARE, CREATE ... AS SELECT, SET LOCAL; and the tables a literal that does not parse names
        base = package_sources()
        for body in ("return c.execute(' JOIN memory.project_grants g ON true')", "q = ''\n    q += ' WHERE EXISTS (SELECT 1 FROM memory.project_grants)'\n    return c.execute(q)",
                     "return c.execute(f'{cols} FROM memory.api_keys')", "return c.execute('SET LOCAL x = 1; SELECT 1 FROM memory.api_keys')", "return c.execute('EXPLAIN ANALYZE SELECT 1 FROM memory.api_keys')",
                     "return c.execute('PREPARE p AS SELECT * FROM memory.api_keys')", "return c.execute('CALL f((SELECT 1 FROM memory.api_keys))')",
                     "return c.execute('DECLARE c CURSOR FOR SELECT * FROM memory.api_keys')", "return c.execute('CREATE TEMP TABLE t AS SELECT * FROM memory.api_keys')",
                     "return c.execute(\"SELECT query_to_xml('select * from memory.api_keys', true, true, '')\")", "return c.execute('SELECT 1 FROM memory.api_keys WHERE x = (( )')"):
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, cols):\n    ' + body + '\n'})
                self.assertIn('api_keys' if 'project_grants' not in body else 'project_grants', outside.get('newmod.py:leak', []), body)
        # writes the parser sees through EXPLAIN, and a body of DO that the parser gives as a string
        for statement in ('EXPLAIN ANALYZE DELETE FROM memory.project_grants WHERE true', 'DO $$ BEGIN DELETE FROM memory.api_keys; END $$', 'EXPLAIN (ANALYZE) UPDATE memory.actors SET disabled=true'):
            self.assertTrue(writes_outside_the_writers({**base, 'newmod.py': 'def w(c):\n    c.execute(%r)\n' % statement}), statement)
        # what the guard reports of a literal that does not parse: the unparseable kind AND each table it names, its writes, its non-literal tables
        reads = sql_reads('DO $$ BEGIN DELETE FROM memory.api_keys; END $$')
        self.assertEqual(reads, {('unparseable SQL', False), ('api_keys', False)})
        self.assertEqual(sql_writes('DO $$ BEGIN DELETE FROM memory.api_keys; END $$'), {'api_keys'})
        self.assertEqual(sql_reads('SELECT FROM WHERE memory.actors ((')  , {('unparseable SQL', False)})  # no star: not a whole row (fix11)
        for text in ('SELECT x FROM \x00 WHERE (( ', 'FROM a, \x00 WHERE (('):
            self.assertFalse(sql_dynamic(text), text)  # fix10/fix11: a name WITHOUT `memory.` that is only a hole, in a text that does not parse, is not seen (declared); with `memory.` it is always seen
        # the exempt functions waive ONLY `unparseable SQL`: a table of the guard or a hole of a table, injected in each of them (and at module level and in a class body), is red by its own kind
        for name, qualified in (('admin.py', 'backfill_query'), ('store_vectors.py', 'VectorsMixin._vector_candidates')):
            for piece, kinds in (("c.execute('SELECT k.scopes FROM memory.api_keys k WHERE ' + a + ' ' + b)", {'api_keys'}), ("c.execute(f'SELECT 1 FROM memory.{t} WHERE {cond} {extra}')", {'unknown table'})):
                outside, _ = reads_outside_the_resolver({**base, name: inject(base[name], qualified, piece)})
                self.assertTrue(kinds <= set(outside['%s:%s' % (name, qualified)]), (qualified, piece))
        for name in ('admin.py', 'store_jobs.py'):
            for piece, kinds in (("q = 'SELECT k.scopes FROM memory.api_keys k WHERE ' + a + ' ' + b", {'api_keys'}), ("q = f'SELECT 1 FROM memory.{t} WHERE {cond} {extra}'", {'unknown table'}),
                                 ("class C:\n    q = 'SELECT k.scopes FROM memory.api_keys k WHERE ' + a + ' ' + b", {'api_keys'})):
                outside, _ = reads_outside_the_resolver({**base, name: base[name] + '\n\n' + piece + '\n'})
                self.assertTrue(kinds <= set(outside['%s:<module>' % name]), (name, piece))

    def test_templates_in_constants_prose_strings_of_sql_and_statements_that_do_not_read(self):
        # fix10 gaps 1-6: no lexical gate; the table position comes from the tree; prose with a hole is silent; every string is read again; LOCK/ANALYZE/VACUUM read nothing; ALTER/INDEX/DROP write
        base = package_sources()
        for module in ("Q = 'SELECT * FROM memory.{}'\n", "Q = 'DELETE FROM MEMORY.%s'\n", "Q = 'SELECT 1 FROM \"memory\".%s'\n", "Q = 'TRUNCATE {t}'\n", "Q = 'SELECT 1 FROM ONLY {t}'\n",
                       "Q = 'COPY {t} TO STDOUT'\n", "Q = 'SELECT 1 FROM /* c */ {t}'\n", "Q = 'SELECT 1 FROM memory.api_{kind}'\n"):
            with self.subTest(module=module):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': module})
                self.assertEqual(outside['newmod.py:<module>'], ['unknown table'], module)
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'Q = r\'SELECT 1 FROM memory.U&"api\\005fkeys"\'\n'})
        self.assertEqual(outside['newmod.py:<module>'], ['api_keys'])
        # prose with a hole is not SQL, in a new module and inside the resolver; prose that names a table of the guard with a word of SQL stays red (declared)
        for body in ("return f'cannot restore from {path}'", "return f'could not update {name}'", "return 'copied from {src}'.format(src=path)", "return f'insert into {x} failed'"):
            outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(path, name, x):\n    ' + body + '\n'})
            self.assertEqual(outside, {}, body)
            outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': inject(base['store_auth.py'], 'AuthMixin._active', body)})
            self.assertEqual(outside, {}, body)
        self.assertIn(('unparseable SQL', False), sql_reads('cannot restore from the actors table'))
        # a string of SQL inside a statement, and the bodies of DO, CREATE FUNCTION and CREATE PROCEDURE, are read again whatever they begin with
        for statement in ("SELECT dblink_exec('conn', 'DELETE FROM memory.api_keys')", "SELECT query_to_xml('  delete from memory.project_grants', true, true, '')",
                          "CREATE FUNCTION f() RETURNS void AS $$ DELETE FROM memory.api_keys $$ LANGUAGE sql", "CREATE PROCEDURE p() LANGUAGE plpgsql AS $$ BEGIN DELETE FROM memory.project_grants; END $$",
                          "DO $$ BEGIN EXECUTE 'DELETE FROM memory.api_keys'; END $$"):
            self.assertTrue(writes_outside_the_writers({**base, 'newmod.py': 'def w(c):\n    c.execute(%r)\n' % statement}), statement)
        deep = 'SELECT 1 FROM memory.api_keys'
        for _ in range(8):
            deep = "SELECT f('%s')" % deep.replace("'", "''")
        self.assertIn(('api_keys', False), sql_reads(deep))  # deeper than the limit: read as one text that does not parse
        for statement in ("LOCK TABLE memory.api_keys IN SHARE MODE", "ANALYZE memory.api_keys", "VACUUM memory.project_grants", "VACUUM (ANALYZE) memory.api_keys, memory.actors"):
            self.assertEqual(sql_reads(statement), set(), statement)
        for statement in ("ALTER TABLE memory.api_keys ADD COLUMN x int", "CREATE INDEX i ON memory.actors(id)", "DROP TABLE memory.web_sessions", "ALTER TABLE memory.actors RENAME TO x", "DROP TABLE IF EXISTS memory.project_grants, memory.x"):
            self.assertTrue(sql_writes(statement), statement)
            self.assertTrue(writes_outside_the_writers({**base, 'newmod.py': 'def w(c):\n    c.execute(%r)\n' % statement}), statement)
        self.assertEqual(sql_writes("ALTER TABLE memory.projects ADD COLUMN x int"), set())
        self.assertTrue(sql_dynamic("DROP TABLE memory.{t}"))
        self.assertEqual(sql_reads("SELECT 1 FROM memory.projects WHERE id=%s"), set())  # a parameter parses as a hole

    def test_a_statement_that_does_not_parse_and_writes_memory_dot_a_hole_or_a_table_of_the_guard_is_red(self):
        # fix11 gap 1: `memory.` followed by a hole is always `unknown table`; `memory.<table of the guard>` is always that table; in a new module and inside `Auth.login`
        base = package_sources()
        bodies = [
            ("return c.execute(f'SELECT 1 FROM memory.{t} WHERE {cond} {order}')", 'unknown table'), ("return c.execute(f'SELECT 1 FROM memory.{t} ORDER BY {col} {direction}')", 'unknown table'),
            ("return c.execute(f'UPDATE memory.{t} SET {sets} WHERE id = %s')", 'unknown table'), ("return c.execute(f'SELECT 1 FROM memory.{t} x {join} WHERE true')", 'unknown table'),
            ("return c.execute(f'SELECT 1 FROM memory.{t} WHERE id IN %s')", 'unknown table'), ("return c.execute(f'{verb} id FROM memory.{t} WHERE true')", 'unknown table'),
            ("return c.execute(f'SELECT 1 FROM memory.{t} WHERE {col} {op} %s')", 'unknown table'), ("return c.execute(f'SELECT 1 FROM MEMORY.{t} WHERE {cond} {extra}')", 'unknown table'),
            ("return c.execute(f'SELECT 1 FROM \"memory\".{t} WHERE {cond} {extra}')", 'unknown table'), ("return c.execute(f'SELECT 1 FROM memory.\"{t}\" WHERE {cond} {extra}')", 'unknown table'),
            ("return c.execute(f'SELECT 1 FROM memory.api_{t} WHERE {cond} {extra}')", 'unknown table'),
            ("frm = f'FROM memory.{table} k WHERE k.id = %s'\n    return c.execute('SELECT k.scopes ' + frm)", 'unknown table'),
            ("frm = 'FROM memory.%s k WHERE k.id = %%s' % TABLE\n    return c.execute('SELECT k.scopes ' + frm)", 'unknown table'),
            ("on = 'memory.api_keys k ON k.id = x.id'\n    return c.execute('SELECT 1 FROM x JOIN ' + on)", 'api_keys'),
            ("return c.execute(f'SELECT 1 FROM memory.project_grants g WHERE {cond} {order}')", 'project_grants'),
            ("return c.execute(f'SELECT 1 FROM memory.{t} WHERE ' + '" + 'a OR ' * 8000 + "b')", 'unknown table'),
        ]
        for body, kind in bodies:
            with self.subTest(body=body[:90]):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, t, table, cond, order, col, direction, sets, join, verb, op, extra):\n    ' + body + '\n'})
                self.assertIn(kind, outside.get('newmod.py:leak', []), body[:90])
                outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
                self.assertIn(kind, outside.get('auth.py:Auth.login', []), body[:90])
        # the mutants of fix10 inside Auth.login: a template in a constant, a string of SQL given to a function
        for body, kind in (("q = 'SELECT * FROM memory.{}'", 'unknown table'), ("q = 'DELETE FROM MEMORY.%s'", 'unknown table'), ("q = 'TRUNCATE {t}'", 'unknown table'), ("q = 'COPY {t} TO STDOUT'", 'unknown table'),
                           ("q = 'SELECT 1 FROM ONLY {t}'", 'unknown table'), ("return c.execute(\"SELECT query_to_xml('select * from memory.api_keys', true, true, '')\")", 'api_keys')):
            outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
            self.assertIn(kind, outside.get('auth.py:Auth.login', []), body)
        self.assertEqual(sql_reads('UPDATE memory.api_keys SET {sets} WHERE x {y}'), {('unparseable SQL', False), ('api_keys', False)})

    def test_the_report_of_a_text_that_does_not_parse_has_no_false_positive_in_templates_prose_and_plpgsql(self):
        # fix11 gap 2
        base = package_sources()
        self.assertEqual(sql_reads('SELECT id FROM memory.actors a WHERE {cond} {order}'), {('unparseable SQL', False)})  # names `actors` without `*` or the row: not a whole row
        self.assertEqual(sql_reads('UPDATE memory.actors SET {sets} WHERE id = %s RETURNING id, username'), {('unparseable SQL', False)})
        self.assertEqual(sql_writes('UPDATE memory.actors SET {sets} WHERE id = %s RETURNING id, username'), {'actors'})
        self.assertIn(('is_admin:row', False), sql_reads('SELECT * FROM memory.actors a WHERE {cond} {order}'))
        self.assertIn(('is_admin:row', False), sql_reads('SELECT a.* FROM memory.actors a WHERE {cond} {order}'))
        body = "DO $$ BEGIN RAISE NOTICE 'could not read from actors'; SELECT 1 INTO x FROM memory.projects; END $$"
        self.assertEqual(sql_reads(body), {('unparseable SQL', False)})  # fix12: the message of a RAISE that names a table of the guard is red (declared); it was silent in fix11
        self.assertEqual(sql_writes("DO $$ DECLARE v text; BEGIN SELECT scopes INTO v FROM memory.api_keys; END $$"), set())  # INTO of PL/pgSQL is not a write
        self.assertEqual(sql_reads("DO $$ DECLARE v text; BEGIN SELECT scopes INTO v FROM memory.api_keys; END $$"), {('unparseable SQL', False), ('api_keys', False)})
        for text in ('ANALYZE {x}', 'LOCK TABLE {x}', 'VACUUM {x}', "COMMENT ON TABLE {x} IS 'y'"):
            self.assertFalse(sql_dynamic(text), text)  # a hole as the target of a statement that reads nothing is not an unknown table
        self.assertEqual(sql_reads('CREATE TABLE memory.x (a int REFERENCES memory.api_keys(id))'), set())
        self.assertEqual(sql_reads('CREATE TABLE memory.y (LIKE memory.api_keys)'), set())
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': "def leak(path):\n    return f'cannot restore from {path}', f'analyze {path}', f'could not update {path}'\n"})
        self.assertEqual(outside, {})

    def test_the_word_raise_hides_nothing_and_the_comments_follow_the_lexer(self):
        # fix12 gaps 1-4: raise as an alias, in a comment, in a literal; a comment that ends at a carriage return; a comment inside `memory . name`; the controls of `closed` and `CreateStmt`
        base = package_sources()
        bodies = [
            ("return c.execute(f'SELECT k.scopes AS raise FROM memory.api_keys k WHERE {cond} {order}')", 'api_keys'),
            ("return c.execute(f'-- raise the limit\\nUPDATE memory.api_keys SET {sets} WHERE id = %s')", 'api_keys'),
            ("return c.execute(f'SELECT 1 /* raise if none */ FROM memory.api_keys k WHERE {cond} {order}')", 'api_keys'),
            ("return c.execute(f\"SELECT 'raise' AS action, g.permission FROM memory.project_grants g WHERE {cond} {order}\")", 'project_grants'),
            ("return c.execute(\"DO $$ BEGIN RAISE NOTICE '%', (SELECT count(*) FROM memory.api_keys); END $$\")", 'api_keys'),
            ("return c.execute(f'-- note\\rUPDATE memory.api_keys SET {sets} WHERE id = %s')", 'api_keys'),
            ("return c.execute('memory /*x*/ .api_keys k ON k.id = x.id ' + cond + ' ' + order)", 'api_keys'),
            ("return c.execute('SELECT 1 /* x FROM memory.api_keys')", 'api_keys'),
        ]
        for body, kind in bodies:
            with self.subTest(body=body[:80]):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, cond, order, sets):\n    ' + body + '\n'})
                self.assertIn(kind, outside.get('newmod.py:leak', []), body)
                outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
                self.assertIn(kind, outside.get('auth.py:Auth.login', []), body)
        self.assertEqual(sql_writes('-- raise the limit\nUPDATE memory.api_keys SET {sets} WHERE id = %s'), {'api_keys'})
        self.assertEqual(sql_writes('-- note\rUPDATE memory.api_keys SET {sets} WHERE id = %s'), {'api_keys'})
        self.assertEqual(sql_writes('CREATE TABLE memory.api_keys (id int)'), {'api_keys'})
        self.assertIn(('api_keys', False), sql_reads('SELECT 1 /* x FROM memory.api_keys'))

    def test_ddl_on_the_tables_of_the_guard_is_a_write(self):
        # fix11 gap 3
        base = package_sources()
        for statement in ("CREATE TRIGGER t BEFORE INSERT ON memory.api_keys FOR EACH ROW EXECUTE FUNCTION f()", "CREATE RULE r AS ON INSERT TO memory.actors DO NOTHING",
                          "CREATE POLICY p ON memory.api_keys USING (true)", "COMMENT ON TABLE memory.web_sessions IS 'x'", "COMMENT ON COLUMN memory.actors.id IS 'x'",
                          "GRANT SELECT ON memory.project_grants TO bob", "ALTER TABLE memory.actors SET SCHEMA other", "DROP SCHEMA memory CASCADE"):
            self.assertTrue(sql_writes(statement), statement)
            self.assertTrue(writes_outside_the_writers({**base, 'newmod.py': 'def w(c):\n    c.execute(%r)\n' % statement}), statement)
        self.assertEqual(sql_writes("COMMENT ON TABLE memory.projects IS 'x'"), set())
        self.assertEqual(sql_writes("GRANT SELECT ON memory.projects TO bob"), set())

    def test_the_cost_grows_linearly_with_the_input(self):
        # fix11 gap 4: four times the input must not cost more than eight times as much (a quadratic growth costs sixteen)
        import time

        def cost(text):
            started = time.monotonic()
            sql_reads(text)
            sql_dynamic(text)
            return time.monotonic() - started
        for make in (lambda n: '/*' * n, lambda n: '/**/' * n + ' FROM memory.api_keys', lambda n: '$a$' * n, lambda n: "'" * n, lambda n: "E'" * n, lambda n: '-- ' * n,
                     lambda n: 'FROM a, ' * n, lambda n: 'SELECT 1 FROM a ' * n, lambda n: 'UPDATE memory.actors SET a=1 RETURNING a; ' * (n // 2)):
            small, large = cost(make(3000)), cost(make(12000))
            self.assertLess(large, max(8 * small, 0.5), make(5)[:30])

    def test_a_raw_placeholder_in_the_position_of_a_table_is_a_hole_and_a_value_is_not(self):
        # fix9 gap 4
        base = package_sources()
        for body in ("return c.execute('DELETE FROM %s WHERE id=%%s' % t)", "return c.execute('SELECT 1 FROM memory.projects p JOIN %s k ON true' % t)", "return c.execute('SELECT 1 FROM \"memory\".%s' % t)",
                     "return c.execute('SELECT 1 FROM memory.projects p, %s k' % (t,))", "return c.execute('INSERT INTO %s(id) VALUES(%%s)' % t)", "return c.execute('TRUNCATE %s' % t)"):
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, t):\n    ' + body + '\n'})
                self.assertEqual(outside['newmod.py:leak'], ['unknown table'], body)
        for text in ("SELECT 1 FROM memory.projects WHERE id=%s", "SELECT 1 FROM memory.projects WHERE id=%(id)s AND a IS DISTINCT FROM %s", "SELECT * FROM memory.projects LIMIT %s OFFSET %s",
                     "UPDATE memory.projects SET title=%s WHERE id=%s", "SELECT 1 FROM memory.projects WHERE id=ANY(%s::text[])"):
            self.assertEqual(sql_reads(text), set(), text)
            self.assertFalse(sql_dynamic(text), text)

    def test_the_guard_does_not_break_on_deep_nesting_a_huge_literal_or_odd_input(self):
        # fix9 gap 5: RecursionError, the size the parser cannot take, openers that never close
        base = package_sources()
        nested = 'SELECT 1 FROM memory.api_keys WHERE x IN (' * 800 + 'SELECT 1' + ')' * 800
        self.assertEqual(sql_reads(nested) & {('unparseable SQL', False), ('api_keys', False)}, {('unparseable SQL', False), ('api_keys', False)})
        huge = 'SELECT 1 FROM memory.api_keys WHERE ' + 'a OR ' * 20000 + 'b'
        self.assertEqual(sql_reads(huge) & {('unparseable SQL', False), ('api_keys', False)}, {('unparseable SQL', False), ('api_keys', False)})
        deep = 'def f(a):\n    return ' + ' + '.join(['a'] * 1500) + '\n'
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': deep})
        self.assertEqual(outside['newmod.py:<module>'], ['unparseable SQL'])
        for odd in ('/*' * 5000 + ' FROM memory.api_keys', "$a$" * 3000 + ' FROM memory.api_keys', "'" * 5000 + ' FROM memory.api_keys', "E'" * 3000 + ' FROM memory.api_keys', '"' * 5000 + ' FROM memory.api_keys'):
            self.assertIn(('api_keys', False), sql_reads(odd), odd[:20])

    def test_more_forms_of_a_whole_row_and_of_the_column(self):
        # fix9 gap 6
        base = package_sources()
        for form in ("SELECT j.* FROM (memory.actors a JOIN memory.projects p ON true) j", "SELECT a.* FROM memory.actors a TABLESAMPLE SYSTEM (10)", "SELECT a FROM memory.actors a TABLESAMPLE BERNOULLI (5)"):
            self.assertIn(('is_admin:row', False), sql_reads(form), form)
        self.assertEqual(sql_reads("SELECT x.* FROM memory.projects p JOIN memory.projects x ON true"), set())
        self.assertEqual(sql_reads("SELECT 1 FROM memory.api_keys k TABLESAMPLE SYSTEM (10)"), {('api_keys', False)})
        for text in ("INSERT INTO memory.api_keys(id) VALUES(%s) RETURNING id", "UPDATE memory.project_grants SET permission=%s WHERE true RETURNING actor_id", "DELETE FROM memory.api_keys WHERE id=%s RETURNING 1"):
            self.assertEqual(len(sql_reads(text)), 1, text)  # the rows it returns are read from the table
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': "def leak(c, cols):\n    return c.execute(f'SELECT {cols} FROM memory.actors a')\n"})
        self.assertEqual(outside['newmod.py:leak'], ['is_admin:row'])  # a hole in a select list may be `a` or `*`
        self.assertEqual(sql_reads('SELECT 1 FROM memory.projects WHERE x = %s'), set())
        for text in ('SELECT U&"is\\005fadmin" FROM memory.actors', 'SELECT a.U&"is\\005fadmin" FROM memory.actors a', 'SELECT (a).U&"is\\005fadmin" FROM memory.actors a'):
            self.assertIn(('is_admin', False), sql_reads(text), text)

    def test_the_column_is_read_in_any_case_in_bytes_and_when_a_format_or_an_f_string_spells_it(self):
        # fix6 gaps 3 and 6: `IS_ADMIN`, a `bytes` query, `'is_{}'.format('admin')` and `f'is_{"admin"}'`
        base = package_sources()
        for body in ("return c.execute('SELECT IS_ADMIN FROM memory.actors')", "return c.execute('SELECT Is_Admin FROM memory.actors')", "return c.execute(b'SELECT is_admin FROM memory.actors')",
                     "return row['is_{}'.format('admin')]", "return row[f'is_{\"admin\"}']", "return row['is_%s' % 'admin']", "return c.execute('SELECT {} FROM memory.actors'.format('is_admin'))",
                     "return c.execute(f'SELECT {\"is_admin\"} FROM memory.actors')", "return c.execute(('SELECT is_adm' 'in FROM memory.actors'))",
                     "return c.execute(\"SELECT 1 FROM memory.projects WHERE note <> '--' AND is_admin\")", "return c.execute('SELECT 1 /* x */ FROM memory.actors WHERE is_admin')"):
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(row, c):\n    ' + body + '\n'})
                self.assertIn('newmod.py:leak', outside, body)
                outside, _ = reads_outside_the_resolver({**base, 'auth.py': inject(base['auth.py'], 'Auth.login', body)})
                self.assertIn('auth.py:Auth.login', outside, body)
        outside, _ = reads_outside_the_resolver({**base, 'newmod.py': "def leak(c):\n    return c.execute('SELECT FROM WHERE memory.api_keys ((')\n"})
        self.assertEqual(outside['newmod.py:leak'], ['api_keys', 'unparseable SQL'])
        # a hole in a table list after a `JOIN ... ON` comma is a hole whatever builds it; a hole that is not a table is not
        for body in ("return c.execute('SELECT 1 FROM a JOIN b ON a.x=b.y, ' + t)", "return c.execute(f'SELECT 1 FROM a JOIN b ON a.x=b.y, {t}')", "return c.execute('SELECT 1 FROM a JOIN b ON a.x=b.y, %s' % t)",
                     "return c.execute('SELECT 1 FROM a JOIN b ON a.x=b.y, {}'.format(t))", "return c.execute('DELETE FROM x USING ' + t)", "return c.execute(f'SELECT 1 FROM a JOIN b ON a.x=b.y, memory.{t}')"):
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, t):\n    ' + body + '\n'})
                self.assertEqual(outside['newmod.py:leak'], ['unknown table'], body)
        for body in ("return c.execute(f\"SELECT 1 FROM a JOIN b ON a.k = 'x)', {t}\")", "return c.execute(f'SELECT 1 FROM memory.api_{kind}')",
                     "return c.execute(f\"SELECT $$a'b$$ FROM memory.{t}\")", "return c.execute(f\"SELECT E'\\\\'', 1 FROM memory.{t}\")", "return c.execute(f'SELECT 1 FROM memory.\"order\", {t}')", "return c.execute('SELECT 1 FROM \"order\", ' + t)",
                     "return c.execute('SELECT 1 FROM a; ' + 'SELECT 1 FROM b, ' + t)"):
            with self.subTest(body=body):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': 'def leak(c, t):\n    ' + body + '\n'})
                self.assertEqual(outside['newmod.py:leak'], ['unknown table'], body)
        for body in ("return c.execute(f'SELECT 1 FROM memory.projects WHERE id IN (1, {t})')",
                     "return c.execute(f'INSERT INTO memory.audit_events(id) SELECT id FROM memory.projects ON CONFLICT (id) DO UPDATE SET title = {t}')",
                     "return c.execute(f'SELECT 1 FROM memory.projects; SELECT a, {t} FROM memory.projects')", "return c.execute(f'SELECT {t}, 1 FROM memory.projects ORDER BY a, {t}')",
                     "return c.execute(f'SELECT coalesce(a, {t}) FROM memory.projects GROUP BY 1')"):
            self.assertEqual(scan('def w(c, t):\n    ' + body + '\n').reads, [], body)

    def test_the_scans_stay_linear_on_artificial_input(self):
        # fix7 gap 2: each of these took tens of seconds in fix6; a generous bound so that a slow machine does not fail it (they take well under a second)
        import time
        for text in ('FROM a, ' * 4000, 'SELECT 1 FROM a ' * 4000, 'copied from the source and ' * 4000, 'INSERT INTO x SELECT y FROM b; ' * 2000, 'SELECT ' * 4000, 'UPDATE memory.actors SET a=1 RETURNING a; ' * 2000,
                     '/**/' * 30 + 'x', '/*' * 10000, '$a$' * 5000, "'" * 10000, "E'" * 5000, '/**/' * 5000 + ' memory.api_keys', '-- ' * 5000):
            started = time.monotonic()
            sql_dynamic(text)
            sql_reads(text)
            self.assertLess(time.monotonic() - started, 5, text[:30])

    def test_the_percent_fill_follows_the_conversion_specifications(self):
        # fix3 gap 4: width, flags, precision and other types each consume ONE argument; `%%` is a `%` and consumes none
        def text(source):
            return sql_text(ast.parse(source, mode='eval').body)
        self.assertEqual(text("'SELECT %5d, %-3s, %.3s, %i FROM %s' % (1, 'x', 'y', 2, 'memory.api_keys')"), 'SELECT \x00, x, y, \x00 FROM memory.api_keys')
        self.assertEqual(text("'WHERE id=%%s AND n>=%5.2f FROM %s' % (1.5, 'memory.api_keys')"), 'WHERE id=%s AND n>=\x00 FROM memory.api_keys')
        self.assertEqual(text("'100%% FROM %(t)s' % {'t': 'memory.api_keys'}"), '100% FROM memory.api_keys')
        self.assertEqual(text("'FROM %*d x %s' % (5, 1, 'memory.api_keys')"), 'FROM \x00 x memory.api_keys')
        self.assertEqual(text("'FROM %.15s' % 'memory.api_keys_'"), 'FROM memory.api_keys')  # fix4 gap 7: the precision truncates the constant as Python does
        outside, _ = reads_outside_the_resolver({**package_sources(), 'newmod.py': "def leak(c):\n    return c.execute('SELECT 1 FROM %.15s' % 'memory.api_keys_')\n"})
        self.assertEqual(outside['newmod.py:leak'], ['api_keys'])
        outside, _ = reads_outside_the_resolver({**package_sources(), 'newmod.py': "def leak(c):\n    return c.execute('SELECT %5d, %-3s FROM %s' % (1, 'x', 'memory.api_keys'))\n"})
        self.assertEqual(outside['newmod.py:leak'], ['api_keys', 'unparseable SQL'])  # the bare piece 'memory.api_keys' is now a table of the guard by itself (fix11)

    def test_each_control_of_the_closed_lists_has_its_mutant(self):
        # fix2 gaps 3, 4 and 5: the exact predicate, the normalised scope, and the three kinds of stale or empty entry
        base = package_sources()
        self.assertEqual(dynamic_table_violations(), [])
        for predicate in ('(t.expires_at < %(cutoff)s OR (t.revoked_at IS NOT NULL AND t.revoked_at < %(cutoff)s)) OR true', '(t.expires_at > %(cutoff)s OR t.revoked_at IS NOT NULL)', 'true'):
            with patch.dict(admin.RETENTION_TABLES, {'web_sessions': (predicate, '')}):
                self.assertTrue(dynamic_table_violations(), predicate)
        with patch.dict(admin.RETENTION_TABLES, {'web_sessions': ('(t.expires_at < %(cutoff)s  OR\n (t.revoked_at IS NOT NULL AND t.revoked_at < %(cutoff)s))', '')}):
            self.assertEqual(dynamic_table_violations(), [], 'blanks do not matter')
        with patch.dict(admin.RETENTION_TABLES):
            del admin.RETENTION_TABLES['web_sessions']
            self.assertEqual(dynamic_table_violations(), [], 'a web_sessions that leaves the retention deletes nothing: not a failure')
        for name in ('WEB_SESSIONS', '"web_sessions"', ' Web_Sessions '):
            with patch.dict(admin.RETENTION_TABLES, {name: ('true', '')}):  # fix3 gap 2: the predicate control looks at the normalised key too
                admin.RETENTION_TABLES.pop('web_sessions', None)
                self.assertTrue(dynamic_table_violations(), name)
        for name in ('API_KEYS', '"actors"', 'api_keys ', ' Project_Grants'):
            with patch.dict(admin.RETENTION_TABLES, {name: ('true', '')}):
                self.assertTrue(dynamic_table_violations(), name)
        # fix4 gap 5: two keys of web_sessions at once, the culprit named; the quote of a hole after `memory.` where no keyword precedes it
        with patch.dict(admin.RETENTION_TABLES, {'WEB_SESSIONS': (WEB_SESSIONS_DEAD, '')}):
            self.assertTrue(any('several keys' in problem for problem in dynamic_table_violations()))
        with patch.dict(admin.RETENTION_TABLES, {'WEB_SESSIONS': ('true', '')}):
            admin.RETENTION_TABLES.pop('web_sessions')
            self.assertTrue(any("'WEB_SESSIONS'" in problem for problem in dynamic_table_violations()), 'the message names the key that changed')
        self.assertTrue(sql_dynamic('SELECT 1 FROM a JOIN b ON a.x=b.x, memory."{}"'))
        self.assertTrue(sql_dynamic('SELECT 1 FROM a JOIN b ON a.x=b.x, memory.{}'))
        self.assertFalse(sql_dynamic('SELECT 1 FROM memory.projects WHERE id=%s'))
        key = ('store_auth.py', 'AuthMixin.list_keys')
        with patch.dict(READ_EXCEPTIONS, {key: ({'api_keys', 'project_grants'}, False, READ_EXCEPTIONS[key][2])}):
            self.assertEqual(reads_outside_the_resolver(base)[1], ['store_auth.py:AuthMixin.list_keys reads project_grants'])
        with patch.dict(DYNAMIC_SQL, {('admin.py', 'main'): (None, set(), 'a function that composes no table', None)}):
            self.assertEqual(reads_outside_the_resolver(base)[1], ['admin.py:main composes no table'])
        with patch.dict(DYNAMIC_SQL, {('admin.py', 'prune_tables'): (lambda sources: set(), {'web_sessions'}, 'reaches nothing: what is it?', None)}):
            self.assertTrue(any('spells no table' in problem for problem in dynamic_table_violations()))

    def test_the_read_scan_does_not_flag_what_is_not_a_read(self):
        # precision: writes, prose and unrelated tables are not decisions
        quiet = [
            "def w(c):\n    c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (1,))",
            "def w(c):\n    c.execute('UPDATE memory.api_keys SET revoked_at=now() WHERE id=%s', (1,))",
            "def w(c):\n    '''Reads project_grants FROM memory.project_grants and is_admin: prose'''\n    return 1",
            "def w(c):\n    return c.execute('SELECT id FROM memory.projects')",
            "def w(c):\n    return c.execute('SELECT id FROM memory.actors WHERE id=%s FOR SHARE', (1,))",
            "def w(row):\n    return row['username'], row.get('disabled')",
            "def w(c):\n    return c.execute('SELECT count(*) AS n FROM memory.actors')",  # fix1: `count(*)` is not a star
            "def w(c):\n    return c.execute('SELECT 1 FROM memory.projects /* project_grants */ WHERE id=%s -- FROM memory.api_keys')",
            "def w(actor):\n    actor.is_admin = False",
            "def w(c):\n    return c.execute('COPY memory.audit_events TO STDOUT')",
            # fix2 gap 2: `FROM %s` with the parameters of `execute` is not a Python `%`; and a `%` that fills no table
            "def w(c, x):\n    return c.execute('SELECT 1 FROM memory.projects WHERE id IS DISTINCT FROM %s', (x,))",
            "def w(c, x):\n    return c.execute('SELECT 1 FROM memory.projects WHERE title=%s' % 'x')",
            "def w(x):\n    return '%d ms' % x",
            # fix2 gap 9: `is_admin` as a parameter name, a column that is written, or a key of a dict
        ]
        for source in quiet:
            with self.subTest(source=source):
                self.assertEqual(scan(source).reads, [])
        # `FOR SHARE OF x` locks the credentials only when `x` is the table or its alias
        self.assertEqual(sql_reads('SELECT 1 FROM memory.projects p JOIN memory.api_keys k ON true FOR SHARE OF k'), {('api_keys', True)})
        self.assertEqual(sql_reads('SELECT 1 FROM memory.projects p JOIN memory.api_keys AS k ON true FOR SHARE OF p'), {('api_keys', False)})
        self.assertEqual(sql_reads('SELECT 1 FROM memory.api_keys FOR SHARE OF memory.api_keys'), {('api_keys', True)})
        self.assertEqual(sql_reads('SELECT 1 FROM memory.api_keys FOR SHARE'), {('api_keys', True)})
        self.assertEqual(sql_reads('SELECT 1 FROM memory.api_keys FOR UPDATE'), {('api_keys', False)})

    def test_the_write_scan_sees_each_way_of_writing_the_permission_tables_outside_the_four_modules(self):
        writes = [
            "def w(c):\n    c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s)')",
            "def w(c):\n    c.execute('insert  into\\n memory.api_keys(id) values(1)')",
            "def w(c):\n    c.execute('UPDATE memory.actors SET is_admin=true WHERE id=%s')",
            "def w(c):\n    c.execute('UPDATE ONLY memory.actors a SET disabled=true')",
            "def w(c):\n    c.execute('DELETE FROM memory.web_sessions WHERE actor_id=%s')",
            "def w(c):\n    c.execute('WITH d AS (DELETE FROM memory.api_keys RETURNING id) SELECT count(*) FROM d')",
            "def w(c):\n    c.execute('UPDATE actors SET disabled=false')",
            "def w(c):\n    c.execute('TRUNCATE TABLE memory.project_grants')",
            "def w(c):\n    c.execute('MERGE INTO memory.project_grants g USING x ON true WHEN MATCHED THEN DELETE')",
            "def w(c):\n    c.execute('INSERT INTO \"memory\".\"web_sessions\" VALUES(1)')",
            "def w(c):\n    c.execute('COPY memory.api_keys FROM STDIN')",
            "def w(c):\n    c.execute('DELETE FROM /* x */ memory.api_keys')",
        ]
        base = package_sources()
        for write in writes:
            for module in ('store.py', 'admin.py', 'newmod.py', 'portal_store.py'):
                with self.subTest(write=write, module=module):
                    self.assertTrue(writes_outside_the_writers({**base, module: base.get(module, '') + '\n' + write + '\n'}), write)
            # the same text in an allowed module is not a violation
            self.assertEqual(writes_outside_the_writers({'store_access.py': write}), [])
        for text in ("SELECT * FROM memory.actors", "INSERT INTO memory.audit_events VALUES(1)", "UPDATE memory.projects SET title=%s"):
            self.assertEqual(sql_writes(text), set(), text)


def store_calls(store, actor, pid, other, key_id):
    """Every `Store` method that takes an actor, with arguments that are valid, so the refusal that follows a revocation can only be the credential's."""
    document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'T', 'content': 'C', 'source': {'uri': 'fixture://d', 'sha256': hashlib.sha256(b'C').hexdigest()},
                'validation': {'status': 'validated', 'evidence': ['e'], 'validated_by': 't'}}
    return {
        'capture_policy': lambda: store.capture_policy(actor, pid), 'change_password': lambda: store.change_password(actor, 'synthetic-password-123', 'another-password-456'), 'create_key': lambda: store.create_key(actor, {'name': 'n', 'project_ids': [pid], 'scopes': ['read']}),
        'create_project': lambda: store.create_project(actor, {'id': project_name(), 'title': 't'}),
        'create_user': lambda: store.create_user(actor, {'username': 'u-' + uuid.uuid4().hex[:10], 'password': 'synthetic-password-123', 'project_ids': [pid], 'scopes': ['read']}),
        'delete_document': lambda: store.delete_document(actor, pid, 'nope', 1), 'document_manifest': lambda: store.document_manifest(actor, pid),
        'document_status': lambda: store.document_status(actor, pid, 'nope'), 'get_current_items': lambda: store.get_current_items(actor, pid),
        'get_document': lambda: store.get_document(actor, pid, 'nope'), 'get_event_receipt': lambda: store.get_event_receipt(actor, 'nope'), 'get_item': lambda: store.get_item(actor, pid, 'nope'),
        'get_job': lambda: store.get_job(actor, 'nope'), 'get_native_fact': lambda: store.get_native_fact(actor, pid, 'nope', 1, 0), 'get_policy': lambda: store.get_policy(actor, pid),
        'graph_data': lambda: store.graph_data(actor, {'project_ids': [pid], 'q': '', 'layers': ['episodic']}), 'has_vectors': lambda: store.has_vectors(actor, [pid], 'm'),
        'history': lambda: store.history(actor, pid), 'ingest_event': lambda: store.ingest_event(actor, event(pid)), 'list_activity': lambda: store.list_activity(actor, pid),
        'list_documents': lambda: store.list_documents(actor, pid), 'list_jobs': lambda: store.list_jobs(actor, pid), 'list_keys': lambda: store.list_keys(actor),
        'list_notes': lambda: store.list_notes(actor, pid), 'list_projects': lambda: store.list_projects(actor), 'list_sessions': lambda: store.list_sessions(actor, pid),
        'list_users': lambda: store.list_users(actor), 'native_history': lambda: store.native_history(actor, pid), 'publish_document': lambda: store.publish_document(actor, pid, document),
        'reconcile_capture': lambda: store.reconcile_capture(actor, pid, 'nope'), 'require_permission': lambda: store.require_permission(actor, pid, 'read'),
        'retry_job': lambda: store.retry_job(actor, 'nope'), 'revoke_key': lambda: store.revoke_key(actor, key_id), 'search_documents': lambda: store.search_documents(actor, [pid], 'x'),
        'search_items': lambda: store.search_items(actor, [pid], 'x'), 'search_native_facts': lambda: store.search_native_facts(actor, [pid], 'x'),
        'search_vectors': lambda: store.search_vectors(actor, [pid], [0.1, 0.2], 'm'),
        'set_policy': lambda: store.set_policy(actor, pid, {'capture_mode': 'summary', 'temporal_projection': True}), 'stats': lambda: store.stats(actor, pid),
        'set_user_disabled': lambda: store.set_user_disabled(actor, 'nobody', True), 'replace_grants': lambda: store.replace_grants(actor, 'nobody', []),
        'list_own_sessions': lambda: store.list_own_sessions(actor), 'revoke_other_sessions': lambda: store.revoke_other_sessions(actor), 'revoke_user_sessions': lambda: store.revoke_user_sessions(actor, 'nobody'),
        'list_user_sessions': lambda: store.list_user_sessions(actor, 'nobody'), 'rotate_key': lambda: store.rotate_key(actor, key_id),
        'timeline': lambda: store.timeline(actor, {'project_ids': [pid]}),
    }


class MetricsAdminModeRealStoreTests(Fixture):
    """fix1 gap 6: `/metrics` in `admin` mode asks the REAL resolver (`Store._global_admin`), not a double: an administrator's session is let in, the key of an administrator is not,
    and neither is the session of a user who is not an administrator."""

    def test_admin_session_200_admin_key_403_non_admin_session_403(self):
        app = create_app(Settings(self.store.dsn, metrics_mode='admin'), store=self.store)
        admin_session = self.auth.login(self.pid, 'fixture-password-123', 'fixture-' + uuid.uuid4().hex)['session_token']  # `create_core` names the administrator like the project
        name = 'u-' + uuid.uuid4().hex[:12]
        self.store.create_user(self.admin, {'username': name, 'password': 'synthetic-password-123', 'project_ids': [self.pid], 'scopes': ['read']})
        user_session = self.auth.login(name, 'synthetic-password-123', 'fixture-' + uuid.uuid4().hex)['session_token']
        key = self.store.create_key(self.admin, {'name': 'metrics', 'project_ids': self.projects, 'scopes': ['read', 'admin']})['token']
        with TestClient(app) as client:
            self.assertEqual(client.get('/metrics', cookies={'memory_session': admin_session}).status_code, 200)
            self.assertEqual(client.get('/metrics', headers={'Authorization': 'Bearer ' + key}).status_code, 403)
            self.assertEqual(client.get('/metrics', cookies={'memory_session': user_session}).status_code, 403)
            self.assertEqual(client.get('/metrics').status_code, 401)


class RevocationTableTests(Fixture):
    def setUp(self):
        super().setUp()
        self.pooled_store = self.pooled(1)

    def test_the_table_covers_every_store_method_that_takes_an_actor(self):
        taking = {name for name in dir(Store) if not name.startswith('_') and callable(getattr(Store, name)) and list(inspect.signature(getattr(Store, name)).parameters)[1:2] == ['actor']}
        self.assertEqual(sorted(taking - set(store_calls(self.store, {}, 'p', 'q', 'k'))), [], 'a new method that takes an actor needs its row in `store_calls`')

    def test_every_store_method_refuses_the_credential_right_after_it_is_revoked(self):
        calls = store_calls(self.pooled_store, {}, 'p', 'q', 'k')
        for name in sorted(calls):
            with self.subTest(method=name):
                created = self.store.create_key(self.admin, {'name': name, 'project_ids': self.projects, 'scopes': ['read', 'write', 'publish', 'validate', 'admin']})
                actor = self.auth.authenticate_bearer(created['token'])
                call = store_calls(self.pooled_store, actor, self.pid, self.projects[1], created['id'])[name]
                try:
                    call()  # with the live key: whatever it answers (some arguments are placeholders), it is not the credential that is refused
                except Unauthorized:
                    self.fail('%s refused a live key' % name)
                except Exception:
                    pass
                self.store.revoke_key(self.admin, created['id'])
                call = store_calls(self.pooled_store, actor, self.pid, self.projects[1], created['id'])[name]
                with self.assertRaises(Unauthorized):
                    call()


class RouteTableTests(Fixture):
    def setUp(self):
        super().setUp()
        self.pooled_store = self.pooled(1)
        self.client = TestClient(create_app(Settings(self.store.dsn), store=self.pooled_store, activity_duration=0.025, activity_poll_interval=0.005))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def routes(self):
        found = []
        for route in self.client.app.routes:
            path = getattr(route, 'path', '')
            if not path.startswith('/v1') or path == '/v1/auth/login':
                continue  # login proves a password and takes no credential; `/v1/auth/me` and `/v1/auth/logout` accept a bearer and are in the table
            for method in sorted(getattr(route, 'methods', set()) - {'HEAD', 'OPTIONS'}):
                found.append((method, path))
        return found

    def url(self, path):
        return re.sub(r'\{(\w+)(?::path)?\}', lambda match: self.pid if match.group(1) == 'project_id' else 'x', path)

    def test_every_v1_route_answers_401_right_after_the_key_is_revoked_on_a_pool_of_one_connection(self):
        routes = self.routes()
        self.assertGreaterEqual(len(routes), 40)
        self.assertLessEqual({('GET', '/v1/auth/me'), ('POST', '/v1/auth/logout')}, set(routes))  # the two cookie routes that also accept a bearer
        self.assertNotIn(('POST', '/v1/auth/login'), routes)
        for method, path in routes:
            with self.subTest(route='%s %s' % (method, path)):
                created = self.store.create_key(self.admin, {'name': 'route', 'project_ids': self.projects, 'scopes': ['read', 'write', 'publish', 'validate', 'admin']})
                headers = {'Authorization': 'Bearer ' + created['token']}
                kwargs = {'headers': headers, **({} if method in ('GET', 'DELETE') else {'json': {}})}
                first = self.client.request(method, self.url(path), **kwargs)
                self.assertNotEqual(first.status_code, 401, first.text[:200])
                self.pooled_store.revoke_key(self.admin, created['id'])
                second = self.client.request(method, self.url(path), **kwargs)
                self.assertEqual(second.status_code, 401, second.text[:200])


# T-16 (CA-37, R-01): the routes of the changes of access (T-09, T-13, T-14, T-15, and the rotation of a key of T-20). Every route under /v1/auth, /v1/users and /v1/keys that is not one of
# the eight that were there before is here (`GET /v1/users/{user_id}/sessions`: fix1 of the review of phase 3, gap 10, CA-42).
ACCESS_ROUTES = (('POST', '/v1/auth/password'), ('PATCH', '/v1/users/{user_id}'), ('PUT', '/v1/users/{user_id}/grants'), ('GET', '/v1/auth/sessions'),
                 ('POST', '/v1/auth/sessions/revoke-others'), ('POST', '/v1/users/{user_id}/sessions/revoke'), ('GET', '/v1/users/{user_id}/sessions'),
                 ('POST', '/v1/keys/{key_id}/rotate'))
EARLIER_ACCOUNT_ROUTES = {('POST', '/v1/auth/login'), ('GET', '/v1/auth/me'), ('POST', '/v1/auth/logout'), ('GET', '/v1/users'), ('POST', '/v1/users'),
                          ('GET', '/v1/keys'), ('POST', '/v1/keys'), ('DELETE', '/v1/keys/{key_id}')}
ORIGIN = 'http://127.0.0.1:5173'


class AccessRoutesTableTests(Fixture):
    """Each access route answers 401 to a key that is revoked, expired or of a disabled user and to a session that is closed, expired or of a disabled user; and every one that changes
    state with a session demands an allowed origin and the CSRF token, before anything changes."""

    def setUp(self):
        super().setUp()
        self.auth = Auth(self.store, [ORIGIN])
        self.client = TestClient(create_app(Settings(self.store.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.target = self.user([self.pid])['id']
        self.target_key = self.store.create_key(self.admin, {'name': 'target', 'project_ids': [self.pid], 'scopes': ['read']})['id']  # what a live call of the rotation rotates

    def call(self, method, path, **kwargs):
        body = {'/v1/auth/password': {'current_password': 'synthetic-password-123', 'new_password': 'another-password-456'}, '/v1/users/{user_id}': {'disabled': True},
                '/v1/users/{user_id}/grants': {'grants': []}}.get(path)
        return self.client.request(method, path.replace('{user_id}', self.target).replace('{key_id}', self.target_key), **({'json': body} if body is not None else {}), **kwargs)

    def dead(self, kind):
        """A fresh credential of a fresh user (administrator of the project), alive, and the function that kills it the way `kind` says."""
        name = 'd-' + uuid.uuid4().hex[:12]
        self.store.create_user(self.admin, {'username': name, 'password': 'synthetic-password-123', 'project_ids': [self.pid], 'scopes': ['read', 'admin']})
        login = self.auth.login(name, 'synthetic-password-123', 'fixture-' + uuid.uuid4().hex)
        key = self.store.create_key(login['actor'], {'name': 'dead', 'project_ids': [self.pid], 'scopes': ['read', 'admin']})

        def sql(statement, *args):
            with psycopg.connect(self.store.dsn, autocommit=True) as c:
                c.execute(statement, args)
        kill = {'revoked': lambda: self.store.revoke_key(self.admin, key['id']) if credential == 'key' else self.auth.logout(login['session_token']),
                'expired': lambda: sql("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", key['id']) if credential == 'key'
                else sql("UPDATE memory.web_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", login['actor']['session_id']),
                # the column itself, not the writer: `_set_disabled` also closes the sessions (T-13), and here the check of the credential must answer on its own
                'disabled': lambda: sql('UPDATE memory.actors SET disabled=true WHERE username=%s', name)}
        credential, cause = kind
        sent = {'headers': {'Authorization': 'Bearer ' + key['token']}} if credential == 'key' else {'cookies': {'memory_session': login['session_token']}}
        return sent, kill[cause]

    def test_the_table_is_every_new_route_of_account_and_users(self):
        found = {(method, route.path) for route in self.client.app.routes for method in getattr(route, 'methods', set()) - {'HEAD', 'OPTIONS'}
                 if route.path.startswith(('/v1/auth', '/v1/users', '/v1/keys'))}
        self.assertEqual(found - EARLIER_ACCOUNT_ROUTES, set(ACCESS_ROUTES), 'a new route of account or users needs its row here')

    def test_every_access_route_answers_401_to_a_dead_credential(self):
        for method, path in ACCESS_ROUTES:
            for kind in itertools.product(('key', 'session'), ('revoked', 'expired', 'disabled')):
                with self.subTest(route='%s %s' % (method, path), credential=kind):
                    sent, kill = self.dead(kind)
                    alive = self.call(method, path, **sent)  # no CSRF header: a state change with a session stops at 403, nothing changes
                    self.assertNotEqual(alive.status_code, 401, alive.text[:200])
                    kill()
                    dead = self.call(method, path, **sent)
                    self.assertEqual(dead.status_code, 401, dead.text[:200])
        with psycopg.connect(self.store.dsn) as c:  # no live call changed the target
            self.assertFalse(c.execute('SELECT disabled FROM memory.actors WHERE id=%s', (self.target,)).fetchone()[0])


    def test_every_access_route_that_changes_state_demands_the_origin_and_the_csrf_token(self):
        login = self.auth.login(self.pid, 'fixture-password-123', 'fixture-' + uuid.uuid4().hex)  # `create_core` names the global administrator like the project
        cookies, token = {'memory_session': login['session_token']}, login['csrf_token']
        for method, path in ACCESS_ROUTES:
            if method == 'GET':
                continue
            for headers in ({}, {'Origin': ORIGIN}, {'X-CSRF-Token': token}, {'Origin': ORIGIN, 'X-CSRF-Token': 'wrong'}, {'Origin': 'https://elsewhere.example', 'X-CSRF-Token': token}):
                with self.subTest(route='%s %s' % (method, path), headers=sorted(headers)):
                    refused = self.call(method, path, cookies=cookies, headers=headers)
                    self.assertEqual((refused.status_code, refused.json()['error']['code']), (403, 'forbidden'), refused.text[:200])
        with psycopg.connect(self.store.dsn) as c:
            self.assertFalse(c.execute('SELECT disabled FROM memory.actors WHERE id=%s', (self.target,)).fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM memory.project_grants WHERE actor_id=%s', (self.target,)).fetchone()[0], 1, 'the grants of the target are untouched')
            self.assertEqual(c.execute('SELECT count(*) FROM memory.web_sessions WHERE id=%s AND revoked_at IS NULL', (login['actor']['session_id'],)).fetchone()[0], 1)
        self.assertEqual(self.call('PATCH', '/v1/users/{user_id}', cookies=cookies, headers={'Origin': ORIGIN, 'X-CSRF-Token': token}).status_code, 200, 'with both, the same request passes')


if __name__ == '__main__':
    unittest.main()
