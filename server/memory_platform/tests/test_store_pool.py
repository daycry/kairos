"""The connection pool of the services (I3 / CA-15): `Store.transaction()` takes its connections from `psycopg_pool`, a warm search opens none, nothing leaks between requests, the
pool is closed on shutdown and `admin` never uses it.

Real PostgreSQL (the isolated test database); no test waits for a clock to observe a state: what is waited for is an event (a thread holding a connection, a server session ending)."""
import asyncio
import os
import threading
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

import psycopg

from memory_platform import models as m
from memory_platform.config import DEFAULT_POOL_MAX, DEFAULT_POOL_MIN, DEFAULT_POOL_TIMEOUT, Settings, pool_settings
from memory_platform.errors import StoreUnavailable
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import StorePool, attach_pool, close_pool
from memory_platform.tests.test_store import create_core


def pool_store(dsn=None, minimum=1, maximum=4, timeout=5.0):
    """A direct `Store` on the test database with a pool of its own; the caller closes it (`addCleanup(close_pool, store)`)."""
    store = Store(dsn or os.environ['MEMORY_TEST_DSN'])
    attach_pool(store, Settings('unused', pool_min=minimum, pool_max=maximum, pool_timeout=timeout), 'api')
    return store


class PoolSettingsTests(unittest.TestCase):
    def test_defaults_are_one_ten_and_five_seconds(self):
        self.assertEqual((DEFAULT_POOL_MIN, DEFAULT_POOL_MAX, DEFAULT_POOL_TIMEOUT), (1, 10, 5.0))
        self.assertEqual(pool_settings({}), (1, 10, 5.0))
        settings = Settings('unused')
        self.assertEqual((settings.pool_min, settings.pool_max, settings.pool_timeout), (1, 10, 5.0))

    def test_explicit_values_are_read_and_the_same_ranges_hold_for_settings(self):
        self.assertEqual(pool_settings({'MEMORY_POOL_MIN': '2', 'MEMORY_POOL_MAX': '20', 'MEMORY_POOL_TIMEOUT': '0.5'}), (2, 20, 0.5))
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_POOL_MAX': '7', 'MEMORY_POOL_MIN': '3'}, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.pool_min, settings.pool_max, settings.pool_timeout), (3, 7, 5.0))

    def test_invalid_values_stop_the_start_with_a_message_that_names_the_variable(self):
        bad = [{'MEMORY_POOL_MIN': '0'}, {'MEMORY_POOL_MIN': '-1'}, {'MEMORY_POOL_MIN': '1.5'}, {'MEMORY_POOL_MIN': 'many'}, {'MEMORY_POOL_MIN': ''},
               {'MEMORY_POOL_MAX': '0'}, {'MEMORY_POOL_MAX': '101'}, {'MEMORY_POOL_MAX': '2', 'MEMORY_POOL_MIN': '3'}, {'MEMORY_POOL_MAX': 'x'},
               {'MEMORY_POOL_TIMEOUT': '0'}, {'MEMORY_POOL_TIMEOUT': '0.05'}, {'MEMORY_POOL_TIMEOUT': '301'}, {'MEMORY_POOL_TIMEOUT': 'nan'}, {'MEMORY_POOL_TIMEOUT': 'inf'},
               {'MEMORY_POOL_TIMEOUT': 'slow'}, {'MEMORY_POOL_TIMEOUT': '-3'}]
        for environ in bad:
            with self.subTest(environ=environ):
                with self.assertRaisesRegex(ValueError, 'MEMORY_POOL_'):
                    pool_settings(environ)
        for changes in ({'pool_min': 0}, {'pool_max': 101}, {'pool_min': 5, 'pool_max': 4}, {'pool_timeout': 0.0}, {'pool_timeout': float('nan')}, {'pool_min': True}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, 'MEMORY_POOL_'):
                    Settings('unused', **changes)


class PoolTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.dsn = os.environ['MEMORY_TEST_DSN']

    def pid(self, store):
        with store.transaction() as c:
            return c.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']

    def test_a_store_without_a_pool_connects_directly_as_before(self):
        store = Store(self.dsn)
        self.assertIsNone(store.pool)
        with patch('psycopg.connect', wraps=psycopg.connect) as connect:
            self.pid(store)
            self.pid(store)
        self.assertEqual(connect.call_count, 2)  # one connection per transaction: the behaviour the pool replaces for the services only

    def test_a_warm_hybrid_search_opens_no_connection_and_the_backend_pids_are_stable(self):
        store, actor, project = create_core()
        attach_pool(store, Settings('unused', pool_min=4, pool_max=4), 'api')  # min = max: the pool is full after `wait` and never grows, so any new connection is a failure
        self.addCleanup(close_pool, store)
        store.pool.wait()
        embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0] * 4, 'model': 'nomic-embed-text', 'verified': True}))
        retrieval = Retrieval(store, Settings('unused', request_timeout=30), embeddings)
        request = m.Search(project_ids=[project], q='anything', layers=['episodic', 'documental'], semantic=True, limit=5)
        seen, opened = set(), []
        real_getconn, real_connect = StorePool.connection, psycopg.Connection.connect.__func__

        def connect(cls, *args, **kwargs):
            opened.append(1)
            return real_connect(cls, *args, **kwargs)
        from contextlib import contextmanager

        @contextmanager
        def recording(pool):
            with real_getconn(pool) as connection:
                seen.add(connection.info.backend_pid)
                yield connection

        async def search():
            return await retrieval.search(actor, request)
        for _ in range(3):
            asyncio.run(search())  # warm up
        warm = set()
        with patch.object(StorePool, 'connection', recording):
            for _ in range(3):
                asyncio.run(search())
            warm, seen = set(seen), set()
            with patch.object(psycopg.Connection, 'connect', classmethod(connect)), patch('psycopg.connect', side_effect=AssertionError('a direct connection')):
                for _ in range(10):
                    asyncio.run(search())
        self.assertEqual(opened, [], 'a warm search opened a connection')
        self.assertTrue(seen and seen <= warm, 'the set of backend pids changed: %r vs %r' % (seen, warm))
        self.assertLessEqual(len(warm), 4)

    def test_commit_rollback_and_savepoints_behave_as_with_a_direct_connection(self):
        table = 'pool_probe_' + uuid.uuid4().hex[:8]
        with psycopg.connect(self.dsn, autocommit=True) as direct:
            direct.execute(f'CREATE TABLE public.{table}(id text)')
        self.addCleanup(lambda: psycopg.connect(self.dsn, autocommit=True).execute(f'DROP TABLE IF EXISTS public.{table}').connection.close())
        store = pool_store(maximum=2)
        self.addCleanup(close_pool, store)

        def ids():
            with store.transaction() as c:
                return sorted(r['id'] for r in c.execute(f'SELECT id FROM public.{table}').fetchall())
        with store.transaction() as c:
            c.execute(f'INSERT INTO public.{table} VALUES (%s)', ('committed',))
        with self.assertRaises(ValueError):
            with store.transaction() as c:
                c.execute(f'INSERT INTO public.{table} VALUES (%s)', ('rolled-back',))
                raise ValueError('the caller failed')
        with store.transaction() as c:
            c.execute(f'INSERT INTO public.{table} VALUES (%s)', ('outer',))
            try:
                with c.transaction():  # a savepoint, as `bounded_fallback` and the vector paths use
                    c.execute(f'INSERT INTO public.{table} VALUES (%s)', ('inner',))
                    raise ValueError('the savepoint fails')
            except ValueError:
                pass
        self.assertEqual(ids(), ['committed', 'outer'])

    def test_session_settings_never_leak_to_the_next_transaction_of_the_same_connection(self):
        store = pool_store(minimum=1, maximum=1)  # one connection: the next transaction is on the very same session
        self.addCleanup(close_pool, store)
        with store.transaction() as c:
            first = c.execute('SELECT pg_backend_pid() AS pid, current_setting(%s) AS timeout, current_setting(%s) AS name', ('statement_timeout', 'application_name')).fetchone()
            c.execute("SET statement_timeout = '7ms'")  # session-level on purpose: nothing in the code does it, the reset is the net under whoever does
            c.execute("SET application_name = 'leaked'")
            c.execute("SET search_path = pg_catalog")
        with store.transaction() as c:
            second = c.execute('SELECT pg_backend_pid() AS pid, current_setting(%s) AS timeout, current_setting(%s) AS name, current_setting(%s) AS path',
                               ('statement_timeout', 'application_name', 'search_path')).fetchone()
        self.assertEqual(first['pid'], second['pid'], 'the second transaction must reuse the connection for this test to mean anything')
        self.assertEqual((second['timeout'], second['name']), (first['timeout'], first['name']))
        self.assertNotEqual(second['path'], 'pg_catalog')

    def test_a_connection_that_cannot_be_reset_is_dropped_and_replaced_not_reused(self):
        store = pool_store(minimum=1, maximum=1, timeout=10.0)
        self.addCleanup(close_pool, store)
        first = self.pid(store)
        with patch('memory_platform.store_pool.reset_session', side_effect=psycopg.errors.InternalError('boom')),                 patch('memory_platform.store_pool.log_failure') as logged:
            with store.transaction() as c:
                c.execute('SELECT 1')
        logged.assert_called_once()
        self.assertEqual(logged.call_args.args[0], 'pool_reset_failed')
        self.assertNotEqual(self.pid(store), first, 'the connection that failed its reset was given to the next transaction')

    def test_transaction_local_settings_do_not_outlive_their_transaction(self):
        store = pool_store(minimum=1, maximum=1)
        self.addCleanup(close_pool, store)
        with store.transaction() as c:
            before = c.execute("SELECT current_setting('statement_timeout') AS value").fetchone()['value']
            c.execute("SELECT set_config('statement_timeout', '9ms', true)")
            self.assertEqual(c.execute("SELECT current_setting('statement_timeout') AS value").fetchone()['value'], '9ms')
        with store.transaction() as c:
            self.assertEqual(c.execute("SELECT current_setting('statement_timeout') AS value").fetchone()['value'], before)

    def test_an_exception_in_a_transaction_gives_the_connection_back(self):
        store = pool_store(minimum=1, maximum=1, timeout=1.0)  # a leaked connection would leave the next transaction without one
        self.addCleanup(close_pool, store)
        for number in range(20):
            with self.assertRaises(RuntimeError):
                with store.transaction() as c:
                    c.execute('SELECT 1')
                    raise RuntimeError(number)
            with self.assertRaises(psycopg.errors.UndefinedTable):
                with store.transaction() as c:
                    c.execute('SELECT * FROM public.no_such_table_' + uuid.uuid4().hex[:6])
        self.assertGreater(self.pid(store), 0)
        self.assertEqual(store.pool.stats()['pool_available'], 1)

    def test_the_pool_never_holds_more_than_its_maximum_under_concurrency(self):
        store = pool_store(minimum=1, maximum=3)
        self.addCleanup(close_pool, store)
        pids, errors = set(), []

        def work():
            try:
                for _ in range(8):
                    with store.transaction() as c:
                        c.execute('SELECT pg_sleep(0.01)')
                        pids.add(c.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'])
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
        threads = [threading.Thread(target=work) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        self.assertLessEqual(len(pids), 3)

    def server_sessions(self, pids):
        with psycopg.connect(self.dsn, autocommit=True) as direct:
            return {r[0] for r in direct.execute('SELECT pid FROM pg_stat_activity WHERE pid = ANY(%s)', (list(pids),)).fetchall()}

    def test_closing_the_pool_ends_every_server_session_and_later_transactions_fail_cleanly(self):
        store = pool_store(minimum=2, maximum=3)
        pids = set()
        threads = [threading.Thread(target=lambda: pids.add(self.pid(store))) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertTrue(pids and self.server_sessions(pids) == pids)
        close_pool(store)
        close_pool(store)  # idempotent
        self.assertTrue(store.pool.closed)
        deadline = threading.Event()
        timer = threading.Timer(30, deadline.set)
        timer.start()
        try:
            while self.server_sessions(pids) and not deadline.is_set():
                deadline.wait(0.05)  # the server ends a session when it sees the socket close: wait for that event, bounded
        finally:
            timer.cancel()
        self.assertEqual(self.server_sessions(pids), set(), 'a connection of the closed pool is still open in the server')
        with self.assertRaises(StoreUnavailable):
            self.pid(store)

    def test_a_pool_that_was_never_used_is_never_opened_and_closes_without_error(self):
        store = pool_store()
        close_pool(store)
        self.assertTrue(store.pool.closed)
        self.assertFalse(store.pool._opened)

    def test_the_app_closes_the_pool_it_built_and_leaves_the_store_it_was_given_alone(self):
        from fastapi.testclient import TestClient
        from memory_platform.app import create_app
        create_core()  # the shared test database is migrated
        settings = Settings(self.dsn, mount_mcp=False, pool_min=1, pool_max=2)
        app = create_app(settings)
        pool = app.state.store.pool
        self.assertIsNotNone(pool)
        with TestClient(app) as client:
            self.assertEqual(client.get('/health/ready').status_code, 200)
            self.assertFalse(pool.closed)
        self.assertTrue(pool.closed)
        given = Store(self.dsn)
        app = create_app(Settings(self.dsn, mount_mcp=False), store=given)
        self.assertIs(app.state.store, given)
        self.assertIsNone(given.pool)
        with TestClient(app) as client:
            self.assertEqual(client.get('/health/ready').status_code, 200)
        self.assertIsNone(given.pool)

    def test_the_app_with_the_mounted_mcp_closes_the_pool_too(self):
        from fastapi.testclient import TestClient
        from memory_platform.app import create_app
        create_core()
        app = create_app(Settings(self.dsn, mount_mcp=True))
        pool = app.state.store.pool
        with TestClient(app):
            self.assertFalse(pool.closed)
        self.assertTrue(pool.closed)

    def test_the_worker_attaches_a_pool_and_closes_it_when_it_stops_or_fails(self):
        import memory_platform.worker as worker_module
        for failure in (None, RuntimeError('boom')):
            with self.subTest(failure=failure):
                made = []

                def attach(store, settings, role):
                    made.append((role, attach_pool(store, settings, role)))
                    return made[-1][1]
                with patch.dict(os.environ, {'MEMORY_DSN': self.dsn, 'MEMORY_POOL_MAX': '3'}), patch.object(worker_module, 'attach_pool', attach), \
                        patch.object(worker_module.Worker, 'run', AsyncMock(side_effect=failure)):
                    if failure:
                        with self.assertRaises(RuntimeError):
                            asyncio.run(worker_module.serve())
                    else:
                        asyncio.run(worker_module.serve())
                self.assertEqual([role for role, _ in made], ['worker'])
                self.assertTrue(made[0][1].closed)

    def test_admin_commands_connect_directly_and_never_get_a_pool(self):
        import memory_platform.admin as admin
        seen = []
        with patch.dict(os.environ, {'MEMORY_DSN': self.dsn, 'MEMORY_POOL_MAX': '2'}), patch.object(admin, 'inspect_store', side_effect=lambda store: seen.append(store) or {}):
            admin.main(['inspect'])
        self.assertEqual(len(seen), 1)
        self.assertIsNone(seen[0].pool)
        self.assertNotIn('store_pool', open(admin.__file__, encoding='utf-8').read(), 'admin must not import the pool')


if __name__ == '__main__':
    unittest.main()
