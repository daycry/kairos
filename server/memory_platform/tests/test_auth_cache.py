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
        if function == EMPTIES or refreshing:
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
                empties = [(c.lineno, c.col_offset) for c in ast.walk(node) if isinstance(c, ast.Call) and called(c) == EMPTIES]
                self.assertTrue(empties and max(empties) > max(writes), '%s:%s writes a permission table and does not empty the cache after the last write' % (name, node.name))
        self.assertTrue({('store_auth.py', 'revoke_key'), ('store_auth.py', 'create_key'), ('store_auth.py', 'create_user'), ('store_auth.py', 'create_project'),
                         ('store_auth.py', 'bootstrap_user'), ('auth.py', 'logout'), ('auth.py', 'login'), ('auth.py', 'refresh_csrf')} <= writers, sorted(writers))

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
    RESOLVERS = {'_require', '_active', '_global_admin', '_delegate', 'require_permission', '_authorized', '_generation'}
    NOT_REQUEST_PATHS = {
        ('admin.py', 'store_fingerprints'): 'operator command on a direct connection', ('admin.py', 'inspect_store'): 'operator command', ('admin.py', 'content_manifest'): 'operator command',
        ('backup.py', 'create_backup'): 'operator command: one exported snapshot for the fingerprints and the dump', ('admin.py', 'mark_stale_unchunked'): 'operator command', ('admin.py', 'backfill_chunks'): 'operator command', ('admin.py', 'prune_tables'): 'operator command', ('admin.py', 'main'): 'operator command',
        ('auth.py', 'authenticate_bearer'): 'it IS the credential check (reads the key itself, every request, no cache)', ('auth.py', 'authenticate_session'): 'it IS the credential check',
        ('auth.py', 'login'): 'proves a password; opens the session', ('auth.py', 'logout'): 'revokes the session of the cookie it holds', ('auth.py', 'require_csrf'): 'reads the live session row itself',
        ('observability.py', '_read'): 'metrics read, no actor', ('store.py', 'transaction'): 'the provider of the transaction', ('auth_scope.py', 'savepoint'): 'a savepoint, not a transaction',
        ('store_auth.py', 'migrate'): 'schema', ('store_auth.py', 'bootstrap_user'): 'creates the first actor', ('store_jobs.py', 'stored_item_vector'): 'worker, no actor',
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
RESOLVER = {('store_auth.py', name) for name in ('_load_active', '_active', '_global_admin', '_require', '_delegate', '_describe', '_visible_projects', '_admin_somewhere')} | {
    ('auth.py', 'authenticate_bearer'), ('auth.py', 'authenticate_session')}
# The closed list of reads that do NOT decide an access (DC-1). (file, function) -> (tables it may read, only `FOR SHARE` locks?, why it does not decide). '*' is every function of the file.
READ_EXCEPTIONS = {
    ('corpus_answers.py', '_authorized'): ({'project_grants', 'api_keys'}, True, 'a FOR SHARE lock: it discards the rows and calls the resolver afterwards, after `invalidate_auth`'),
    ('extended_store.py', '_require'): ({'project_grants', 'api_keys'}, True, 'a FOR SHARE lock: it discards the rows and calls the resolver afterwards, after `invalidate_auth`'),
    ('store_auth.py', 'list_users'): ({'project_grants'}, False, 'shows the permissions of other users to someone `_global_admin` already admitted'),
    ('store_auth.py', 'list_keys'): ({'api_keys'}, False, 'reads keys as the resource listed, not the credential of the caller; each row goes through `_require`'),
    ('store_auth.py', 'revoke_key'): ({'api_keys'}, False, 'reads the key to revoke as the resource; each of its projects goes through `_require`'),
    ('probe.py', '*'): ({'project_grants', 'api_keys', 'is_admin'}, False, 'operator command on a direct connection, with no request actor'),
}
# The only modules that may write the tables of permissions and credentials (design.md O2: `store_access.py` is the new door for access changes).
PERMISSION_WRITERS = {'store_auth.py', 'store_access.py', 'auth.py', 'probe.py'}
READ_TABLES = ('project_grants', 'api_keys')
WRITE_TABLES = ('actors', 'project_grants', 'api_keys', 'web_sessions')
_TABLE = r'(?:ONLY\s+)?(?:"?memory"?\s*\.\s*)?"?(%s)"?\b'
_READ = re.compile(r'(?<!DELETE )\b(?:FROM|JOIN|USING)\s+' + _TABLE % '|'.join(READ_TABLES) + r'|,\s*' + _TABLE % '|'.join(READ_TABLES), re.I)
_WRITE = re.compile(r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|MERGE\s+INTO)\s+' + _TABLE % '|'.join(WRITE_TABLES), re.I)


def sql_reads(text):
    """(kind, locked) of every restricted read in one SQL string; `kind` is a table of READ_TABLES or 'is_admin'."""
    sql = ' '.join(text.split())
    found = {(m.group(1) or m.group(2)).lower() for m in _READ.finditer(sql)}
    statement = re.match(r'\(?\s*(INSERT|UPDATE|DELETE|TRUNCATE|MERGE)\b', sql, re.I)
    tail = re.split(r'\b(?:WHERE|SELECT)\b', sql, maxsplit=1, flags=re.I)[1:]  # a write names `is_admin` as a column it sets or returns: that is not a read
    if re.search(r'\bis_admin\b', sql, re.I) and (not statement or tail and re.search(r'\bis_admin\b', tail[0], re.I)):
        found.add('is_admin')
    return {(kind, bool(re.search(r'\bFOR\s+SHARE\b', sql, re.I))) for kind in found}


def sql_writes(text):
    return {m.group(1).lower() for m in _WRITE.finditer(' '.join(text.split()))}


class _Scan(ast.NodeVisitor):
    """Each restricted read, attributed to the innermost function that holds it (docstrings and bare strings are prose)."""
    def __init__(self):
        self.stack, self.reads, self.writes = ['<module>'], [], []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Expr(self, node):
        if not isinstance(node.value, ast.Constant):
            self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            self.reads += [(self.stack[-1], kind, locked) for kind, locked in sql_reads(node.value)]
            self.writes += [(self.stack[-1], table) for table in sql_writes(node.value)]

    def visit_Subscript(self, node):
        if isinstance(node.slice, ast.Constant) and node.slice.value == 'is_admin':
            self.reads.append((self.stack[-1], 'is_admin', False))
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'is_admin':
            self.reads.append((self.stack[-1], 'is_admin', False))
        self.generic_visit(node)


@functools.lru_cache(maxsize=None)
def scan(source):
    visitor = _Scan()
    visitor.visit(ast.parse(source))
    return visitor


def reads_outside_the_resolver(sources):
    """({'file:function': kinds}, stale exceptions): each read that is neither in the resolver nor within its listed exception, and the exceptions that no longer cover any read."""
    outside, used = {}, set()
    for file, source in sorted(sources.items()):
        for function, kind, locked in scan(source).reads:
            if (file, function) in RESOLVER:
                continue
            entry = next((key for key in ((file, function), (file, '*')) if key in READ_EXCEPTIONS), None)
            if entry and kind in READ_EXCEPTIONS[entry][0] and (locked or not READ_EXCEPTIONS[entry][1]):
                used.add(entry)
                continue
            outside.setdefault('%s:%s' % (file, function), set()).add(kind)
    return {key: sorted(kinds) for key, kinds in outside.items()}, sorted(set(READ_EXCEPTIONS) - used)


def writes_outside_the_writers(sources):
    return sorted({'%s:%s %s' % (file, function, table) for file, source in sources.items() if file not in PERMISSION_WRITERS for function, table in scan(source).writes})


def package_sources():
    return {str(path.relative_to(PACKAGE)).replace('\\', '/'): path.read_text(encoding='utf-8') for path in sorted(PACKAGE.rglob('*.py'))
            if 'tests' not in path.relative_to(PACKAGE).parts and '__pycache__' not in path.parts}


class ResolverBoundaryTests(unittest.TestCase):
    """Only the resolver decides an access (CA-38 a): a read of `project_grants`, of the permissions of a key or of `actors.is_admin` anywhere else fails here unless it is one of the
    closed list of DC-1, each with its reason. And only four modules write the tables of permissions and credentials."""

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
        self.assertEqual({file for file, source in sources.items() if scan(source).writes} & PERMISSION_WRITERS, {'store_auth.py', 'auth.py', 'probe.py'})

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
        base = package_sources()
        for read in reads:
            with self.subTest(read=read):
                outside, _ = reads_outside_the_resolver({**base, 'newmod.py': read + '\n'})
                self.assertTrue(any(key.startswith('newmod.py:') for key in outside), read)
        # the same text inside a listed function is covered only for the tables and the locks that exception names
        outside, _ = reads_outside_the_resolver({**base, 'store_auth.py': base['store_auth.py'] + "\n\ndef list_users(c):\n    return c.execute('SELECT * FROM memory.api_keys')\n"})
        self.assertIn('store_auth.py:list_users', outside)
        outside, _ = reads_outside_the_resolver({**base, 'corpus_answers.py': base['corpus_answers.py'] + "\n\ndef _authorized(c):\n    return c.execute('SELECT * FROM memory.api_keys WHERE id=%s')\n"})
        self.assertIn('corpus_answers.py:_authorized', outside)

    def test_the_read_scan_does_not_flag_what_is_not_a_read(self):
        # precision: writes, prose and unrelated tables are not decisions
        quiet = [
            "def w(c):\n    c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (1,))",
            "def w(c):\n    c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true) RETURNING id,username,is_admin', (1, 2, 3))",
            "def w(c):\n    c.execute('UPDATE memory.api_keys SET revoked_at=now() WHERE id=%s', (1,))",
            "def w(c):\n    '''Reads project_grants FROM memory.project_grants and is_admin: prose'''\n    return 1",
            "def w(c):\n    return c.execute('SELECT id FROM memory.projects')",
            "def w(c):\n    return c.execute('SELECT id FROM memory.actors WHERE id=%s FOR SHARE', (1,))",
            "def w(row):\n    return row['username'], row.get('disabled')",
        ]
        for source in quiet:
            with self.subTest(source=source):
                self.assertEqual(scan(source).reads, [])

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
        'capture_policy': lambda: store.capture_policy(actor, pid), 'create_key': lambda: store.create_key(actor, {'name': 'n', 'project_ids': [pid], 'scopes': ['read']}),
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
        'timeline': lambda: store.timeline(actor, {'project_ids': [pid]}),
    }


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


if __name__ == '__main__':
    unittest.main()
