"""`connect_timeout` and `statement_timeout` as connection options of the services (I3 / CA-16, CA-17): the server cancels what runs too long, a server that does not answer cannot hold a
connect, the long statements that are legitimate are exempt on purpose, and `admin` never inherits the plazo.

No test observes a state by waiting for a clock: a `pg_sleep` that must be cancelled is cancelled by the server (the exception carries SQLSTATE 57014), and the two bounds that are
checked against a real clock (a mute server, a pool with nothing to give) are asserted as "finished within the plazo plus a margin" on a thread that is always released."""
import asyncio
from contextlib import contextmanager, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

import psycopg
from fastapi.testclient import TestClient
from psycopg import errors as pgerrors
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from memory_platform import admin, store_documents, store_vectors
from memory_platform.app import create_app
from memory_platform.config import DEFAULT_CONNECT_TIMEOUT, DEFAULT_STATEMENT_TIMEOUT_MS, Settings, connection_timeouts, service_statement_timeout
from memory_platform.errors import (MemoryError, STORE_BUSY_MESSAGE, STORE_TIMEOUT_MESSAGE, StoreBusy, StoreUnavailable, is_statement_timeout, is_store_transient, is_store_unavailable,
                                    public_store_failure)
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import attach_pool, close_pool, service_conninfo
from memory_platform.tests import test_vector_search_paths as vector_paths
from memory_platform.tests.fault_proxy import FaultProxy
from memory_platform.tests.test_observability import fake_app
from memory_platform.tests.test_store import create_core, event, extraction_receipt
from memory_platform.tests.test_worker_db_down import Recorder, settings as worker_settings
from memory_platform.worker import IDLE_SECONDS, WRITE_RETRY_MAX, Worker


def plazo_store(dsn=None, role='api', **changes):
    """A `Store` with a pool of one connection (so the next transaction is the same session) and the plazos of `changes`; the caller closes it."""
    store = Store(dsn or os.environ['MEMORY_TEST_DSN'])
    attach_pool(store, Settings('unused', pool_min=1, pool_max=1, pool_timeout=10.0, **changes), role)
    return store


def milliseconds(c):
    return float(c.execute("SELECT EXTRACT(EPOCH FROM current_setting('statement_timeout')::interval) * 1000 AS ms").fetchone()['ms'])


class TimeoutSettingsTests(unittest.TestCase):
    def test_defaults_are_five_seconds_and_fifteen_or_thirty_thousand_milliseconds_by_role(self):
        self.assertEqual(DEFAULT_CONNECT_TIMEOUT, 5)
        self.assertEqual(DEFAULT_STATEMENT_TIMEOUT_MS, {'api': 15000, 'worker': 30000})
        self.assertEqual(connection_timeouts({}), (5, None))
        default = Settings('unused')
        self.assertEqual((default.connect_timeout, default.statement_timeout_ms), (5, None))
        self.assertEqual((service_statement_timeout(default, 'api'), service_statement_timeout(default, 'worker')), (15000, 30000))

    def test_an_explicit_statement_timeout_applies_to_both_roles(self):
        self.assertEqual(connection_timeouts({'MEMORY_CONNECT_TIMEOUT': '8', 'MEMORY_STATEMENT_TIMEOUT_MS': '2500'}), (8, 2500))
        explicit = Settings('unused', statement_timeout_ms=2500)
        self.assertEqual((service_statement_timeout(explicit, 'api'), service_statement_timeout(explicit, 'worker')), (2500, 2500))
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_CONNECT_TIMEOUT': '3', 'MEMORY_STATEMENT_TIMEOUT_MS': '9000'}, clear=True):
            read = Settings.from_env()
        self.assertEqual((read.connect_timeout, read.statement_timeout_ms), (3, 9000))

    def test_invalid_values_stop_the_start_and_name_the_variable(self):
        bad = [{'MEMORY_CONNECT_TIMEOUT': v} for v in ('0', '1', '121', '-3', '2.5', 'soon', '')] + \
              [{'MEMORY_STATEMENT_TIMEOUT_MS': v} for v in ('0', '99', '3600001', '-1', '1e3', '15s', '2.5')]
        for environ in bad:
            with self.subTest(environ=environ):
                with self.assertRaisesRegex(ValueError, 'MEMORY_(CONNECT|STATEMENT)_TIMEOUT'):
                    connection_timeouts(environ)
        for changes in ({'connect_timeout': 1}, {'connect_timeout': 121}, {'connect_timeout': 2.5}, {'statement_timeout_ms': 0}, {'statement_timeout_ms': 99}, {'statement_timeout_ms': True}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, 'MEMORY_(CONNECT|STATEMENT)_TIMEOUT'):
                    Settings('unused', **changes)


class ServicePlazoTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.dsn = os.environ['MEMORY_TEST_DSN']

    def test_the_dsn_of_the_service_gets_both_plazos_and_keeps_its_own_options(self):
        self.assertEqual(service_conninfo(self.dsn), self.dsn)  # with no plazo it is the DSN itself
        plain = conninfo_to_dict(service_conninfo(self.dsn, 5, 15000))
        self.assertEqual((plain['connect_timeout'], plain['options']), ('5', '-c statement_timeout=15000'))
        own = conninfo_to_dict(service_conninfo(make_conninfo(self.dsn, options='-c application_name=mine'), 2, 400))
        self.assertEqual(own['options'], '-c application_name=mine -c statement_timeout=400')

    def test_every_connection_of_the_pool_starts_with_the_default_plazo_of_its_role(self):
        for role, changes, expected in (('api', {}, 15000.0), ('worker', {}, 30000.0), ('api', {'statement_timeout_ms': 2500}, 2500.0), ('worker', {'statement_timeout_ms': 2500}, 2500.0)):
            with self.subTest(role=role, changes=changes):
                store = plazo_store(role=role, **changes)
                self.addCleanup(close_pool, store)
                with store.transaction() as c:
                    self.assertEqual(milliseconds(c), expected)
                    self.assertEqual(c.execute("SELECT current_setting('application_name') AS name").fetchone()['name'], '')  # the option did not disturb the others

    def test_a_dsn_with_its_own_options_keeps_them_in_the_pool(self):
        store = Store(make_conninfo(self.dsn, options='-c application_name=kairos-test-own'))
        attach_pool(store, Settings('unused', pool_min=1, pool_max=1), 'api')
        self.addCleanup(close_pool, store)
        with store.transaction() as c:
            self.assertEqual(c.execute("SELECT current_setting('application_name') AS name").fetchone()['name'], 'kairos-test-own')
            self.assertEqual(milliseconds(c), 15000.0)

    def test_a_query_longer_than_the_plazo_is_cancelled_by_the_server_and_the_connection_comes_back_usable(self):
        store = plazo_store(statement_timeout_ms=300)
        self.addCleanup(close_pool, store)
        with store.transaction() as c:
            pid = c.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
        with self.assertRaises(pgerrors.QueryCanceled) as raised:
            with store.transaction() as c:
                c.execute('SELECT pg_sleep(30)')  # without the plazo this runs 30 seconds
        self.assertEqual(raised.exception.sqlstate, '57014')  # it is the SERVER that says so: the query did not keep running behind a thread that gave up
        self.assertFalse(is_store_unavailable(raised.exception))  # an answered error, not an outage
        self.assertTrue(is_store_transient(raised.exception))  # the worker repeats it within its write budget
        with psycopg.connect(self.dsn, autocommit=True) as direct:
            running = direct.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = %s AND state = 'active' AND query LIKE '%%pg_sleep%%'", (pid,)).fetchone()[0]
        self.assertEqual(running, 0)
        with store.transaction() as c:  # the same session, usable: nothing was left half done
            self.assertEqual(c.execute('SELECT pg_backend_pid() AS pid, 1 AS one').fetchone(), {'pid': pid, 'one': 1})

    def test_a_server_that_accepts_and_never_answers_fails_the_connection_within_the_connect_timeout(self):
        proxy = FaultProxy().start()
        self.addCleanup(proxy.stop)
        proxy.mute()
        outcome = {}

        def connect():
            started = time.monotonic()
            try:
                psycopg.connect(service_conninfo(proxy.dsn(), connect_timeout=2))
            except Exception as exc:
                outcome['error'] = exc
            outcome['seconds'] = time.monotonic() - started
        thread = threading.Thread(target=connect, daemon=True)
        thread.start()
        thread.join(2 + 1)  # MEMORY_CONNECT_TIMEOUT + 1 second (CA-17)
        stuck = thread.is_alive()
        proxy.stop()  # releases the thread whatever happened
        thread.join(10)
        self.assertFalse(stuck, 'the connect to a mute server was still waiting after the connect timeout plus a second')
        self.assertIsInstance(outcome['error'], psycopg.OperationalError)
        self.assertTrue(is_store_unavailable(outcome['error']))  # no SQLSTATE: the server never said anything
        self.assertLessEqual(outcome['seconds'], 3.0)

    def test_a_transaction_against_a_mute_server_fails_as_unavailable_within_the_pool_wait(self):
        proxy = FaultProxy().start()
        self.addCleanup(proxy.stop)
        proxy.mute()
        store = Store(proxy.dsn())
        attach_pool(store, Settings('unused', pool_min=1, pool_max=1, pool_timeout=1.0, connect_timeout=2), 'api')
        self.addCleanup(close_pool, store)
        outcome = {}

        def attempt():
            try:
                with store.transaction():
                    outcome['entered'] = True
            except Exception as exc:
                outcome['error'] = exc
        thread = threading.Thread(target=attempt, daemon=True)
        thread.start()
        thread.join(1.0 + 2)
        stuck = thread.is_alive()
        proxy.stop()
        thread.join(10)
        self.assertFalse(stuck, 'a transaction against a mute server hung beyond the pool wait')
        self.assertNotIn('entered', outcome)
        self.assertIsInstance(outcome['error'], StoreUnavailable)

    def test_the_local_settings_of_the_fallbacks_restore_the_plazo_of_the_service(self):
        store = plazo_store(statement_timeout_ms=15000)
        self.addCleanup(close_pool, store)
        with store.transaction() as c:
            rows, timed_out = store_documents.bounded_fallback(c, lambda: c.execute('SELECT 1 AS one').fetchall())
            self.assertEqual((rows, timed_out, milliseconds(c)), ([{'one': 1}], False, 15000.0))
            with patch.object(store_documents, 'TRIGRAM_FALLBACK_MS', 100):
                rows, timed_out = store_documents.bounded_fallback(c, lambda: c.execute('SELECT pg_sleep(30)').fetchall())
            self.assertEqual((rows, timed_out, milliseconds(c)), ([], True, 15000.0))  # cancelled by the fallback's own plazo; the service's is back and the transaction lives
            self.assertEqual(c.execute('SELECT 1 AS one').fetchone(), {'one': 1})


class VectorPlazoTests(unittest.TestCase):
    """The vector search sets its OWN statement_timeout (what is left of the semantic budget): the explicit exemption from the plazo of the service."""
    setUp = vector_paths.VectorSearchPathTests.setUp
    drop_database = staticmethod(vector_paths.VectorSearchPathTests.drop_database)
    add = vector_paths.VectorSearchPathTests.add

    def seen_plazo(self, **search):
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=1, statement_timeout_ms=200), 'api')
        self.addCleanup(close_pool, self.store)
        self.add([[1.0, 0.0]])
        seen = []
        real = store_vectors.rank_exact

        def spy(c, *args, **kwargs):
            seen.append(milliseconds(c))
            return real(c, *args, **kwargs)
        with patch.object(store_vectors, 'rank_exact', spy):
            found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], vector_paths.MODEL, **search)
        self.assertEqual(len(found), 1)
        return seen

    def test_a_semantic_deadline_governs_the_vector_statements_not_the_plazo_of_the_service(self):
        seen = self.seen_plazo(deadline=time.monotonic() + 20)
        self.assertEqual(len(seen), 1)
        self.assertGreater(seen[0], 1000, 'the semantic budget (about 20 s) is what bounds the scan, not the 200 ms of the service')

    def test_without_a_deadline_the_vector_statements_run_under_the_plazo_of_the_service(self):
        self.assertEqual(self.seen_plazo(), [200.0])


class AdminPlazoTests(unittest.TestCase):
    """`migrate`, `backfill-chunks`, `backup`, `content-manifest`, `inspect` and `prune-tables` run with the plazos of the API in the environment and do not inherit them."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.name = 'plazo_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin_connection:
            admin_connection.execute(f'CREATE DATABASE {self.name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as admin_connection:
                admin_connection.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')
        self.addCleanup(drop)
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.environ = {'MEMORY_DSN': self.dsn, 'MEMORY_STATEMENT_TIMEOUT_MS': '100', 'MEMORY_CONNECT_TIMEOUT': '2', 'MEMORY_POOL_MAX': '2'}
        self.seen = []
        seen = self.seen

        class Recording(Store):
            @contextmanager
            def transaction(self):
                with super().transaction() as connection:
                    seen.append(connection.execute("SHOW statement_timeout").fetchone()['statement_timeout'])
                    yield connection
        self.Recording = Recording

    def run_admin(self, *argv):
        with patch.dict(os.environ, self.environ), patch.object(admin, 'Store', self.Recording), redirect_stdout(io.StringIO()) as out:
            admin.main(list(argv))
        return out.getvalue()

    def test_the_recording_store_sees_the_plazo_of_a_service_connection(self):
        """Positive control: with the pool of the API the very same recorder reads 100 ms, so the zero below is the absence of the plazo and not a blind spot."""
        store = self.Recording(self.dsn)
        attach_pool(store, Settings('unused', pool_min=1, pool_max=1, statement_timeout_ms=100), 'api')
        self.addCleanup(close_pool, store)
        with store.transaction():
            pass
        self.assertEqual(self.seen, ['100ms'])

    def test_no_admin_command_inherits_the_plazo_of_the_services(self):
        for argv in (('migrate',), ('inspect',), ('content-manifest',), ('backfill-chunks',), ('prune-tables', '--dry-run')):
            with self.subTest(command=argv[0]):
                self.seen.clear()
                self.run_admin(*argv)
                self.assertTrue(self.seen, 'the command opened no transaction: the test would prove nothing')
                self.assertEqual(set(self.seen), {'0'}, 'the command ran under a statement_timeout')

    def test_backup_hands_pg_dump_the_dsn_without_plazos(self):
        self.run_admin('migrate')
        target = Path(tempfile.mkdtemp(prefix='plazo-backup-')) / 'copy.dump'
        captured = {}

        def fake_run(command, env=None, **kwargs):
            captured['text'] = Path(env['PGSERVICEFILE']).read_text(encoding='utf-8')
            Path(command[command.index('--file') + 1]).write_bytes(b'dump')
            return Mock(returncode=0)
        with patch.object(admin.subprocess, 'run', fake_run):
            self.run_admin('backup', '--output', str(target))
        self.assertIn('dbname=' + self.name, captured['text'])
        for forbidden in ('statement_timeout', 'connect_timeout', 'options'):
            self.assertNotIn(forbidden, captured['text'])


class WorkerStatementTimeoutTests(unittest.IsolatedAsyncioTestCase):
    """A 57014 from a query of the WORKER is not an outage: it is repeated within the write budget of `_persist` and, spent, the job fails as `store_error` and goes back to the queue."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.name = 'wplazo_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin_connection:
            admin_connection.execute(f'CREATE DATABASE {self.name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as admin_connection:
                admin_connection.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')
        self.addCleanup(drop)
        self.direct_dsn = make_conninfo(dsn, dbname=self.name)
        with patch.dict(os.environ, {'MEMORY_TEST_DSN': self.direct_dsn}):
            self.direct, self.actor, self.pid = create_core(extraction=True)
        self.jid = self.direct.ingest_event(self.actor, event(self.pid))['jobs'][0]
        self.store = Store(self.direct_dsn)
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=2, statement_timeout_ms=300), 'worker')
        self.addCleanup(close_pool, self.store)

    def row(self):
        with self.direct.transaction() as c:
            return c.execute('SELECT state,attempts,error_code FROM memory.jobs WHERE id=%s', (self.jid,)).fetchone()

    async def test_a_cancelled_query_while_writing_the_outcome_is_retried_and_then_fails_the_job_as_store_error(self):
        cancelled = []

        def slow_complete(job_id, fence, receipt):
            try:
                with self.store.transaction() as c:
                    c.execute('SELECT pg_sleep(30)')  # the plazo of the worker's connection (300 ms here) cancels it in the server
            except Exception as exc:
                cancelled.append(exc)
                raise
        self.store.complete_job = slow_complete
        waiter = Recorder()
        worker = Worker(self.store, worker_settings(), {'extract': Mock(extract=Mock(side_effect=lambda source: asyncio.sleep(0, extraction_receipt())))}, rng=lambda: 1.0, waiter=waiter)
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 60))
        self.assertEqual(len(cancelled), WRITE_RETRY_MAX)  # the write was repeated up to its budget
        self.assertTrue(all(isinstance(exc, pgerrors.QueryCanceled) and exc.sqlstate == '57014' for exc in cancelled))
        self.assertFalse(any(is_store_unavailable(exc) for exc in cancelled))
        self.assertEqual(len(waiter.delays), WRITE_RETRY_MAX - 1)
        self.assertEqual(worker.store_failures, 0)  # never counted as an outage
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('pending', 1, 'store_error'))  # back in the queue with an attempt left



SECRET = 'hunter2-never-in-an-answer'


class StoreFailureClassificationTests(unittest.TestCase):
    """What a client is told when the database does not answer in time (CA-16, CA-19): fixed messages, nothing of the driver, the same everywhere a client can see it."""
    headers = {'Authorization': 'Bearer fixture'}

    def test_the_classifier_names_only_the_two_plazos(self):
        self.assertEqual(public_store_failure(StoreBusy()), ('store_busy', STORE_BUSY_MESSAGE))
        self.assertEqual(public_store_failure(pgerrors.QueryCanceled(SECRET)), ('store_timeout', STORE_TIMEOUT_MESSAGE))
        for other in (StoreUnavailable('OperationalError'), psycopg.OperationalError(SECRET), pgerrors.LockNotAvailable(SECRET), RuntimeError(SECRET), MemoryError('x', 'y')):
            self.assertIsNone(public_store_failure(other), type(other).__name__)
        self.assertTrue(is_statement_timeout(pgerrors.QueryCanceled('x')))
        self.assertFalse(is_statement_timeout(StoreBusy()))
        for message in (STORE_BUSY_MESSAGE, STORE_TIMEOUT_MESSAGE):
            self.assertNotIn('SELECT', message)
            self.assertNotIn('postgres', message.lower())

    def test_the_api_answers_503_with_the_code_of_the_plazo_a_fixed_message_and_the_request_id(self):
        app, store, auth, retrieval = fake_app()
        cases = [(StoreBusy(), 'store_busy', STORE_BUSY_MESSAGE),
                 (pgerrors.QueryCanceled('canceling statement due to statement timeout: SELECT secret FROM ' + SECRET), 'store_timeout', STORE_TIMEOUT_MESSAGE),
                 (StoreUnavailable('OperationalError'), 'service_unavailable', 'Service is temporarily unavailable'),  # an outage keeps its generic answer
                 (RuntimeError(SECRET), 'service_unavailable', 'Service is temporarily unavailable')]
        with TestClient(app, raise_server_exceptions=False) as client:
            for exc, code, message in cases:
                with self.subTest(code=code, exc=type(exc).__name__):
                    store.list_projects.side_effect = exc
                    response = client.get('/v1/projects', headers=self.headers)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()['error'], {'code': code, 'message': message})
                    self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
                    self.assertNotIn(SECRET, response.text)

    def test_the_mounted_mcp_gives_the_fixed_message_of_each_plazo_and_the_generic_one_otherwise(self):
        app, store, auth, retrieval = fake_app()
        cases = [(StoreBusy(), STORE_BUSY_MESSAGE), (pgerrors.QueryCanceled(SECRET), STORE_TIMEOUT_MESSAGE), (StoreUnavailable('OperationalError'), 'Memory service temporarily unavailable'),
                 (RuntimeError(SECRET), 'Memory service temporarily unavailable')]
        with TestClient(app, base_url='http://localhost:8790') as client:
            for exc, message in cases:
                with self.subTest(exc=type(exc).__name__):
                    retrieval.search = AsyncMock(side_effect=exc)
                    response = client.post('/mcp/', headers={**self.headers, 'Accept': 'application/json, text/event-stream'},
                                           json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': 'anything'}}})
                    result = response.json()['result']
                    self.assertTrue(result['isError'])
                    self.assertEqual(result['content'][0]['text'], 'Error executing tool search: ' + message)
                    self.assertNotIn(SECRET, response.text)


class ApiPoolFailureTests(unittest.TestCase):
    """The same answers from a real pool and a real PostgreSQL: an exhausted pool (503 `store_busy`, bounded wait) and a statement cancelled at the plazo (503 `store_timeout`, connection reusable)."""
    headers = {'Authorization': 'Bearer fixture'}

    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.store, self.actor, self.project = create_core()
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=1, pool_timeout=0.3, statement_timeout_ms=300), 'api')
        self.addCleanup(close_pool, self.store)
        auth = Mock()
        auth.authenticate_bearer.return_value = self.actor
        embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True}))
        retrieval = Retrieval(self.store, Settings('unused', request_timeout=5), embeddings)
        self.client = TestClient(create_app(Settings('unused', mount_mcp=False), self.store, auth, retrieval))

    def test_with_the_pool_exhausted_a_request_waits_at_most_the_pool_timeout_and_gets_store_busy(self):
        held, release = threading.Event(), threading.Event()

        def hold():
            with self.store.transaction():
                held.set()
                release.wait(60)
        holder = threading.Thread(target=hold, daemon=True)
        holder.start()
        self.assertTrue(held.wait(30))
        result = {}

        def ask():
            result['response'] = self.client.get('/v1/projects', headers=self.headers)
        asker = threading.Thread(target=ask, daemon=True)
        asker.start()
        asker.join(0.3 + 5)  # MEMORY_POOL_TIMEOUT plus a margin; without the wait of the pool this would last until the holder lets go
        stuck = asker.is_alive()
        release.set()
        holder.join(30)
        asker.join(30)
        self.assertFalse(stuck, 'the request hung on an exhausted pool')
        response = result['response']
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], {'code': 'store_busy', 'message': STORE_BUSY_MESSAGE})
        self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
        self.assertEqual(self.client.get('/v1/projects', headers=self.headers).status_code, 200)  # the pool recovers as soon as the connection is back

    def test_a_statement_cancelled_by_the_plazo_is_503_store_timeout_and_the_next_request_works(self):
        def slow(actor):
            with self.store.transaction() as c:
                c.execute('SELECT pg_sleep(30)')
        with patch.object(self.store, 'list_projects', slow):
            response = self.client.get('/v1/projects', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], {'code': 'store_timeout', 'message': STORE_TIMEOUT_MESSAGE})
        self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
        again = self.client.get('/v1/projects', headers=self.headers)
        self.assertEqual(again.status_code, 200)
        self.assertIsInstance(again.json()['projects'], list)  # the shared test database holds many projects: the answer is a list, not necessarily ours

    def test_a_search_layer_cancelled_by_the_plazo_is_unavailable_and_the_semantic_deadline_still_says_timeout(self):
        def slow(*args, **kwargs):
            with self.store.transaction() as c:
                c.execute('SELECT pg_sleep(30)')
        request = {'project_ids': [self.project], 'q': 'anything', 'layers': ['episodic']}
        with patch.object(self.store, 'search_items', slow):
            response = self.client.post('/v1/search', headers=self.headers, json=request)
        self.assertEqual(response.status_code, 200)  # a layer that failed is marked, the request is not
        self.assertEqual(response.json()['backends']['episodic']['status'], 'unavailable')
        self.assertTrue(response.json()['partial'])
        exceeded = MemoryError('semantic_deadline_exceeded', 'Semantic query exceeded its time budget', 503)
        with patch.object(self.store, 'has_vectors', return_value=True), patch.object(self.store, 'search_vectors', side_effect=exceeded):
            response = self.client.post('/v1/search', headers=self.headers, json=request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['backends']['semantic'], {'status': 'unavailable', 'count': 0, 'reason': 'timeout'})  # as before the pool


class WorkerStoreBusyTests(unittest.IsolatedAsyncioTestCase):
    """For the worker an exhausted pool is an outage (`StoreBusy` is a `StoreUnavailable`): it waits and tries again and never spends the attempt of a job. A statement cancelled by the
    plazo (57014) is NOT one: it is the transient error of `WorkerStatementTimeoutTests`. 503 `store_timeout` exists only in the API (decision of phase 2, kept)."""
    def setUp(self):
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store = Mock()
        self.store.claim_job.return_value = None
        self.receipt = {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        self.provider = Mock(extract=AsyncMock(return_value=self.receipt))

    def worker(self, waiter):
        return Worker(self.store, worker_settings(), {'extract': self.provider}, rng=lambda: 1.0, waiter=waiter)

    async def test_a_claim_that_finds_no_connection_is_an_outage_with_the_backoff_of_one(self):
        waiter = Recorder()
        worker = self.worker(waiter)
        answers = [StoreBusy(), StoreBusy()]

        def claim(*args):
            if answers:
                raise answers.pop(0)
            worker.stopping.set()
            return None
        self.store.claim_job.side_effect = claim
        await asyncio.wait_for(worker.run(), 60)
        self.assertEqual(waiter.delays, [1.0, 2.0, IDLE_SECONDS])  # the growing wait of an outage, then the idle wait of an empty queue
        self.store.fail_job.assert_not_called()
        self.assertEqual(worker.store_failures, 0)

    async def test_a_result_that_finds_no_connection_is_written_when_one_is_free_without_spending_the_attempt(self):
        self.store.claim_job.return_value = self.job
        self.store.renew_lease.return_value = True
        self.store.complete_job.side_effect = [StoreBusy(), True]
        waiter = Recorder()
        worker = self.worker(waiter)
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 60))
        self.assertEqual(self.store.complete_job.call_count, 2)
        self.store.fail_job.assert_not_called()
        self.assertEqual(waiter.delays, [1.0])

    async def test_a_statement_timeout_is_not_an_outage_for_the_worker(self):
        self.store.claim_job.side_effect = pgerrors.QueryCanceled('x')
        worker = self.worker(Recorder())
        with self.assertRaises(pgerrors.QueryCanceled):  # not StoreUnavailable: it is classified by the loop of the worker as a transient database error
            await worker.run_once()
        self.assertEqual(worker.store_failures, 0)


if __name__ == '__main__':
    unittest.main()
