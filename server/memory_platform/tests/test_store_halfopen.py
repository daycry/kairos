"""The half-open connection (I3 / CA-16, CA-17, CA-19, CA-34; fix1 of the review of phase 4): a connection that is ALREADY established in the pool and then stops answering WITHOUT closing the
socket (a partition, a frozen host). `FaultProxy.mute()` closes the open connections, so it cannot reproduce it; `FaultProxy.freeze()` keeps them open and silent.

The code under test closes the class with two layers (see `store_pool.py`): TCP keepalives and `tcp_user_timeout` in the connection options (a real network), and a CLIENT-side plazo on every
blocking operation of a pooled connection (a proxy on loopback still answers at TCP level). The plazos of these tests are small (`GUARD`, `CHECK`) and the assertions are bounds on threads that
are always released, never a sleep waiting for a state.

| situation (already open connection, then `freeze()`) | API                                                 | worker                                              |
|-------------------------------------------------------|-----------------------------------------------------|-----------------------------------------------------|
| a statement is in flight                              | 503 service_unavailable within GUARD (+ margin)     | `StoreUnavailable`, never `provider_timeout`        |
| the connection is idle (checked when handed out)      | 503 service_unavailable within wait + CHECK         | the read of the stored vector is an outage          |
| `/health/ready`                                       | 503 not_ready within 3 s (the healthcheck client's) | -                                                   |

After `thaw()` the pool serves again with no connection left checked out and no thread left hanging; the worker stops on `SIGTERM` and closes its pool within a bound."""
import asyncio
import io
import json
import os
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import psycopg
import psycopg.conninfo
from fastapi.testclient import TestClient

from memory_platform import observability
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.errors import StoreBusy, StoreUnavailable, is_store_unavailable
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import CHECK_SECONDS, READY_GUARD, READY_WAIT, StorePool, attach_pool, close_pool, guarded_connection_class, service_conninfo
from memory_platform.tests.fault_proxy import FaultProxy
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.test_store_faults import HEADERS, POOL_WAIT, WorkerFixture, answer_code
from memory_platform.tests.test_worker import long_text
from memory_platform.tests.test_worker_db_down import settings as worker_settings
from memory_platform.worker import Worker

GUARD = 1.0  # client-side plazo of a statement in these tests
CHECK = 0.5  # client-side plazo of the check at hand-out and of the reset
MARGIN = 5.0  # slack added to a bound: a scheduler hiccup is not a hang


def small_plazos(store):
    store.pool.guard_seconds, store.pool.check_seconds = GUARD, CHECK  # the pool has not opened yet: its connections read these when they are made
    return store


class HalfOpenApiTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.direct, self.actor, self.project = create_core()
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.store = Store(self.proxy.dsn())
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=2, pool_timeout=POOL_WAIT, connect_timeout=2, statement_timeout_ms=300), 'api')
        small_plazos(self.store)
        self.addCleanup(close_pool, self.store)
        auth = Mock()
        auth.authenticate_bearer.return_value = self.actor
        retrieval = Retrieval(self.store, Settings('unused', request_timeout=5), Mock(embed=AsyncMock()))
        self.client = TestClient(create_app(Settings('unused', mount_mcp=False), self.store, auth, retrieval), raise_server_exceptions=False)
        self.addCleanup(self.proxy.thaw)  # releases a thread a failed assertion left on a frozen connection

    def read(self):
        return self.client.get('/v1/projects', headers=HEADERS)

    def bounded(self, ask, bound):
        """The answer of `ask()`, which must come within `bound` seconds; the proxy is thawed to release the thread if it did not."""
        result = {}
        thread = threading.Thread(target=lambda: result.update(response=ask(), at=time.monotonic()), daemon=True)
        started = time.monotonic()
        thread.start()
        thread.join(bound)
        stuck = thread.is_alive()
        if stuck:
            self.proxy.thaw()
            thread.join(60)
        self.assertFalse(stuck, 'the request hung on a connection that stopped answering without closing')
        return result['response'], result['at'] - started

    def recovered(self):
        for _ in range(60):
            if self.read().status_code == 200:
                return True
        return False

    def assert_nothing_left_checked_out(self):
        """Every connection the pool may have can be taken at the same time: none was left checked out by a thread that hung (a barrier of `max_size` parties breaks if one is missing).
        The second slot is refilled by the pool on its short backoff, so a few attempts are allowed (as `recovered`), never a sleep."""
        self.assertEqual(self.store.pool.stats()['requests_waiting'], 0)
        size = self.store.pool.max_size

        def attempt():
            barrier, errors = threading.Barrier(size), []

            def take():
                try:
                    with self.store.transaction():
                        barrier.wait(10)
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=take, daemon=True) for _ in range(size)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
            return not errors
        self.assertTrue(any(attempt() for _ in range(40)), 'a connection was left checked out or the pool cannot give its maximum')

    def test_a_statement_in_flight_on_an_established_connection_that_goes_silent_ends_within_the_client_guard_and_the_pool_recovers(self):
        self.assertEqual(self.read().status_code, 200)  # the connection is established and warm

        def hang(*args, **kwargs):
            with self.store.transaction() as c:
                self.proxy.freeze()  # the socket stays open, nothing comes back
                c.execute('SELECT 1')
        with patch.object(self.store, 'list_projects', hang):
            response, elapsed = self.bounded(self.read, GUARD + MARGIN)
        self.assertEqual((response.status_code, answer_code(response)), (503, 'service_unavailable'))  # a database outage, not store_busy or store_timeout
        self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
        self.assertGreaterEqual(elapsed, GUARD * 0.8)  # it WAS the client-side plazo that ended it (the server cannot answer, so there is no 57014)
        self.proxy.thaw()
        self.assertTrue(self.recovered(), 'the API did not recover after the connection came back')
        self.assert_nothing_left_checked_out()

    def test_an_idle_connection_that_went_silent_is_caught_by_the_check_and_the_request_is_bounded(self):
        self.assertEqual(self.read().status_code, 200)
        self.proxy.freeze()
        response, elapsed = self.bounded(self.read, POOL_WAIT + CHECK + MARGIN)
        self.assertEqual((response.status_code, answer_code(response)), (503, 'service_unavailable'))  # the check failed: an outage, not a busy pool
        self.assertLess(elapsed, GUARD - 0.1)  # ended by the SHORT plazo of the check (0.5 s) and not by the statement one (1 s)
        self.assertGreaterEqual(self.proxy.accepted, 1)
        self.proxy.thaw()
        self.assertTrue(self.recovered(), 'the API did not recover after the connection came back')
        self.assert_nothing_left_checked_out()

    def test_many_requests_on_silent_connections_do_not_exhaust_the_pool(self):
        """Without the client plazo, `max` hung requests held every connection for ever (the 10 hung threads of the review)."""
        self.assertEqual(self.read().status_code, 200)
        self.proxy.freeze()
        answers, threads = [], []
        for _ in range(6):  # more requests than connections (max 2)
            thread = threading.Thread(target=lambda: answers.append(self.read().status_code), daemon=True)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join(POOL_WAIT + CHECK + MARGIN + 5)
        stuck = [thread for thread in threads if thread.is_alive()]
        self.proxy.thaw()
        for thread in stuck:
            thread.join(60)
        self.assertEqual(stuck, [], 'a request thread hung on a silent connection')
        self.assertEqual(sorted(set(answers)), [503])
        self.assertTrue(self.recovered())
        self.assert_nothing_left_checked_out()

    def test_ready_is_503_within_the_healthcheck_client_timeout_when_the_database_goes_silent(self):
        self.assertEqual(self.client.get('/health/ready').status_code, 200)
        self.proxy.freeze()
        response, elapsed = self.bounded(lambda: self.client.get('/health/ready'), 3.0)  # the healthcheck of Compose gives up at 3 s
        self.assertEqual((response.status_code, answer_code(response)), (503, 'not_ready'))
        self.assertLess(elapsed, 3.0)
        self.proxy.thaw()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and self.client.get('/health/ready').status_code != 200:
            pass
        self.assertEqual(self.client.get('/health/ready').status_code, 200)

    def test_a_pool_with_every_connection_in_use_is_ready_not_a_dead_database(self):
        """Saturation is not an outage (gap 5): the pool is full, the database answers, `/health/ready` is 200 and the saturation is logged."""
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        self.assertEqual(self.client.get('/health/ready').status_code, 200)
        held, release = threading.Event(), threading.Event()
        holders = []

        def hold():
            with self.store.transaction():
                held.set()
                release.wait(60)
        for _ in range(2):  # max_size = 2: both connections in use
            held.clear()
            thread = threading.Thread(target=hold, daemon=True)
            thread.start()
            holders.append(thread)
            self.assertTrue(held.wait(30))
        self.addCleanup(lambda: [release.set(), *[thread.join(30) for thread in holders]])
        response, elapsed = self.bounded(lambda: self.client.get('/health/ready'), 3.0)
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0)
        self.assertEqual(self.client.get('/v1/projects', headers=HEADERS).status_code, 503)  # the same pool still answers store_busy to a request: it is busy, not ready for more
        self.assertIn('readiness_pool_saturated', [json.loads(line)['event'] for line in stream.getvalue().splitlines() if line.startswith('{')])

    def test_the_search_layers_answer_store_busy_and_not_a_silent_partial_when_the_pool_is_saturated(self):
        """Gap 4: a `StoreBusy` inside a layer is the 503 `store_busy` of the request (as the scope check), never a 200 `partial` that looks like a thin corpus."""
        episodic = {'project_ids': [self.project], 'q': 'anything', 'layers': ['episodic'], 'semantic': False}
        semantic = {'project_ids': [self.project], 'q': 'anything', 'layers': ['episodic'], 'semantic': True}
        with patch.object(self.store, 'search_items', Mock(side_effect=StoreBusy())):
            response = self.client.post('/v1/search', headers=HEADERS, json=episodic)
        self.assertEqual((response.status_code, answer_code(response)), (503, 'store_busy'))
        with patch.object(self.store, 'has_vectors', Mock(side_effect=StoreBusy())):
            response = self.client.post('/v1/search', headers=HEADERS, json=semantic)
        self.assertEqual((response.status_code, answer_code(response)), (503, 'store_busy'))
        with patch.object(self.store, 'search_items', Mock(side_effect=RuntimeError('boom'))):  # any OTHER failure of a layer keeps the documented partial answer
            response = self.client.post('/v1/search', headers=HEADERS, json=episodic)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['partial'])


class HalfOpenWorkerTests(WorkerFixture, unittest.IsolatedAsyncioTestCase):
    """The worker against a connection that is open and silent (the database, proxy and log fixture of `WorkerFaultTests`)."""
    def setUp(self):
        super().setUp()
        small_plazos(self.store)
        self.addCleanup(self.proxy.thaw)

    async def test_the_stored_vector_read_on_an_open_silent_connection_ends_as_a_database_outage_and_not_as_provider_timeout(self):
        """The half-open version of the debt of phase 2 (T-09, gap 3): the connection of the claim is open and silent when the read of the stored vector needs it."""
        job = {'id': 'synthetic-job', 'fence': 1, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a' * 64, 'policy': {}, 'project_id': self.pid, 'item_id': 'item', 'resource_type': 'document',
               'version': 1, 'payload': {'title': 'Long note', 'content': long_text(6000)}}  # more than one fragment: the stored vector is read first

        def claim(*args):
            with self.store.transaction() as c:
                c.execute('SELECT 1')
            self.proxy.freeze()  # the connection went back to the pool open; from now on nothing comes back through it
            return job
        provider = Mock(embed=AsyncMock(side_effect=AssertionError('the provider must not be reached')), embed_many=AsyncMock(side_effect=AssertionError('the provider must not be reached')))
        self.store.claim_job = claim
        self.store.fail_job = Mock(side_effect=AssertionError('an outage of the database must not fail a job'))
        worker = Worker(self.store, worker_settings(), {'embed': provider})
        try:
            self.assertTrue(await asyncio.wait_for(worker.run_once(), GUARD + MARGIN))
        finally:
            self.proxy.thaw()  # releases the thread if the plazo did not
        provider.embed_many.assert_not_called()
        self.assertEqual(worker.store_failures, 1)
        self.assertEqual([entry['reason'] for entry in self.events('store_unavailable')], ['read'])
        self.assertEqual(self.events('job_failed'), [])  # in particular no `provider_timeout`
        self.assertEqual(self.events('job_completed'), [])

    async def test_the_stored_vector_read_in_flight_on_a_connection_that_goes_silent_is_an_outage_too(self):
        job = {'id': 'synthetic-job', 'fence': 1, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a' * 64, 'policy': {}, 'project_id': self.pid, 'item_id': 'item', 'resource_type': 'document',
               'version': 1, 'payload': {'title': 'Long note', 'content': long_text(6000)}}
        self.store.claim_job = lambda *args: job
        self.store.fail_job = Mock(side_effect=AssertionError('an outage of the database must not fail a job'))

        def silent_read(*args, **kwargs):
            with self.store.transaction() as c:
                self.proxy.freeze()
                c.execute('SELECT 1')  # a statement in flight on an established connection: only the client-side plazo can end it
        worker = Worker(self.store, worker_settings(), {'embed': Mock(embed=AsyncMock(), embed_many=AsyncMock())})
        try:
            with patch('memory_platform.worker.stored_item_vector', silent_read):
                self.assertTrue(await asyncio.wait_for(worker.run_once(), GUARD + MARGIN))
        finally:
            self.proxy.thaw()
        self.assertEqual([entry['reason'] for entry in self.events('store_unavailable')], ['read'])
        self.assertEqual(self.events('job_failed'), [])  # no `provider_timeout`

    async def test_run_ends_after_the_stop_order_and_the_pool_closes_when_a_connection_went_silent_inside_a_claim(self):
        """The shutdown of the review (SIGKILL after the grace period): a claim blocked on a silent connection used to keep `run()` from seeing the stop order."""
        entered = threading.Event()

        def claim(*args):
            with self.store.transaction() as c:
                entered.set()
                self.proxy.freeze()
                c.execute('SELECT 1')
        self.store.claim_job = claim
        worker = Worker(self.store, worker_settings(), {'extract': Mock(extract=AsyncMock())})
        task = asyncio.create_task(worker.run())
        self.assertTrue(await asyncio.to_thread(entered.wait, 30))
        worker.stopping.set()  # SIGTERM while the claim is stuck on the silent connection
        try:
            await asyncio.wait_for(task, GUARD + MARGIN)  # run() ends by itself, once the client plazo freed the thread
        finally:
            self.proxy.thaw()
        self.assertGreaterEqual(worker.store_failures, 1)
        stopping = time.monotonic()
        await asyncio.wait_for(asyncio.to_thread(close_pool, self.store), 10)
        self.assertLess(time.monotonic() - stopping, 5, 'closing the pool of a worker whose connections went silent took too long')


class GuardedConnectionTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.addCleanup(self.proxy.thaw)

    def test_a_guarded_connection_raises_and_closes_when_the_peer_goes_silent_and_a_plain_one_would_not(self):
        connection = guarded_connection_class().connect(self.proxy.dsn(), autocommit=True)
        connection.guard_seconds = 0.5
        self.assertEqual(connection.execute('SELECT 1').fetchone()[0], 1)  # a live server is never cut by the guard
        self.proxy.freeze()
        outcome = {}

        def ask():
            try:
                connection.execute('SELECT 2')
            except Exception as exc:
                outcome['error'] = exc
        thread = threading.Thread(target=ask, daemon=True)
        thread.start()
        thread.join(0.5 + MARGIN)
        stuck = thread.is_alive()
        self.proxy.thaw()  # releases the thread if the guard did not
        thread.join(30)
        self.assertFalse(stuck, 'a guarded connection hung on a silent peer')
        self.assertIsInstance(outcome['error'], psycopg.OperationalError)
        self.assertTrue(connection.closed)  # never used again: the pool replaces it
        self.assertTrue(is_store_unavailable(outcome['error']))  # an outage of the database for the API and the worker
        self.assertNotIn('127.0.0.1', str(outcome['error']))  # fixed message: no host, no port

    def test_the_driver_still_has_the_timeout_this_relies_on(self):
        """If a driver upgrade renames the private exception or drops the `timeout` of `Connection.wait`, this fails before an outage does."""
        import inspect
        self.assertIn('timeout', inspect.signature(psycopg.Connection.wait).parameters)
        self.assertTrue(hasattr(psycopg.errors, '_WaitTimeout'))
        self.assertTrue(issubclass(psycopg.errors._WaitTimeout, psycopg.OperationalError))

    def test_the_service_connections_carry_keepalives_and_tcp_user_timeout(self):
        info = psycopg.conninfo.conninfo_to_dict(service_conninfo('postgresql://u@h/d', 3, 15000, (30, 10, 3, 30000)))
        self.assertEqual({key: info[key] for key in ('keepalives', 'keepalives_idle', 'keepalives_interval', 'keepalives_count', 'tcp_user_timeout')},
                         {'keepalives': '1', 'keepalives_idle': '30', 'keepalives_interval': '10', 'keepalives_count': '3', 'tcp_user_timeout': '30000'})
        store = Store(os.environ['MEMORY_TEST_DSN'])
        attach_pool(store, Settings('unused', keepalives_idle=20, keepalives_interval=5, keepalives_count=4, tcp_user_timeout_ms=45000), 'api')
        self.addCleanup(close_pool, store)
        with store.transaction() as c:  # a connection the pool really made: the options reached libpq
            parameters = c.info.get_parameters()
        self.assertEqual({key: parameters.get(key) for key in ('keepalives', 'keepalives_idle', 'keepalives_interval', 'keepalives_count', 'tcp_user_timeout')},
                         {'keepalives': '1', 'keepalives_idle': '20', 'keepalives_interval': '5', 'keepalives_count': '4', 'tcp_user_timeout': '45000'})
        self.assertGreater(store.pool.guard_seconds, 15.0)  # the API statement plazo plus the margin: the server cancels first when it is alive

    def test_the_default_plazos_of_the_pool_fit_the_healthcheck(self):
        self.assertLess(READY_WAIT + CHECK_SECONDS + READY_GUARD, 3.0)  # the Compose healthcheck client (`urlopen(..., timeout=3)`) must be answered by /health/ready


class GraphDataPlazoTests(unittest.TestCase):
    def test_graph_data_through_the_api_pool_finishes_well_within_the_statement_plazo(self):
        """R-02 (gap 11): `graph_data` issues a few statements (each in its own transaction, each bounded by the 15 s of the API); a project of a realistic size finishes far inside it."""
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        direct, actor, project = create_core()
        for number in range(40):
            direct.ingest_event(actor, event(project, payload={'title': 'Fencing note %d' % number, 'content': 'Use fencing before projection %d' % number, 'source': {'uri': 'fixture://public'}}))
        store = Store(os.environ['MEMORY_TEST_DSN'])
        attach_pool(store, Settings('unused'), 'api')  # the defaults of the API: statement_timeout 15,000 ms
        self.addCleanup(close_pool, store)
        statements = []
        real = psycopg.Cursor.execute

        def counting(cursor, query, *args, **kwargs):
            statements.append(1)
            return real(cursor, query, *args, **kwargs)
        started = time.monotonic()
        with patch.object(psycopg.Cursor, 'execute', counting):
            graph = store.graph_data(actor, {'project_ids': [project], 'q': 'fencing', 'limit': 100})
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(graph['stats']['nodes'], 1)
        self.assertLess(elapsed, 15.0 / 3, 'graph_data came close to the 15 s statement plazo of the API')
        self.assertLess(len(statements), 200)  # bounded work: a handful of statements per layer, not one per node


if __name__ == '__main__':
    unittest.main()
