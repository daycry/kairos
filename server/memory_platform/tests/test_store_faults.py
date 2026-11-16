"""The whole class of database faults against the new data paths of the API and the worker (I3 / CA-16, CA-17, CA-19, CA-34): a database that is cut, mute or slow, in the read, write
and search routes and in every access of the worker. A real PostgreSQL behind the `FaultProxy`, a real pool and the real plazos; the tests that observe time are bounds ("answered within the
pool wait plus a margin") on threads that are always released, never a sleep waiting for a state.

What each route answers (API; every 503 carries `request_id`, a fixed message and nothing of the driver):

| route                     | cut (refused/closed)               | mute (accepts, never answers; cold pool) | slow (statement past the plazo)      |
|---------------------------|------------------------------------|-------------------------------|-------------------------------------------------|
| read   GET /v1/projects   | 503 service_unavailable            | 503 store_busy                | 503 store_timeout                               |
| write  POST /v1/projects  | 503 service_unavailable            | 503 store_busy                | 503 store_timeout                               |
| search POST /v1/search    | 503 service_unavailable (scope)    | 503 store_busy (scope)        | 200, the slow layer `unavailable`, `partial`    |
| ready  GET /health/ready  | 503 not_ready                      | 503 not_ready                 | (a one-row read: not slow-able)                 |

Mute with a cold pool is `store_busy` and not `service_unavailable` because a connection attempt that has not failed yet is not an error: the pool simply had nothing to give within MEMORY_POOL_TIMEOUT (the connect plazo is longer than the wait in these tests; with the defaults it is shorter, see `ConnectAndWaitTests`). A connection that was already in the pool and dies is an outage (`service_unavailable`).
The worker treats `store_busy` as an outage (it waits and tries again without spending the attempt) and a cancelled statement (57014) as a transient error of the database."""
import asyncio
import io
import json
import os
import threading
import time
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

import psycopg
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from memory_platform import observability
from memory_platform.app import create_app
from memory_platform.config import Settings, worker_write_retry_seconds
from memory_platform.errors import StoreUnavailable
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import attach_pool, close_pool
from memory_platform.tests.fault_proxy import FaultProxy
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.test_worker import long_text
from memory_platform.tests.test_worker_db_down import DOWN, Recorder, settings as worker_settings
from memory_platform.worker import Abandoned, Worker

POOL_WAIT = 0.5  # MEMORY_POOL_TIMEOUT of these tests
HEADERS = {'Authorization': 'Bearer fixture'}


def service_store(proxy):
    store = Store(proxy.dsn())
    attach_pool(store, Settings('unused', pool_min=1, pool_max=2, pool_timeout=POOL_WAIT, connect_timeout=2, statement_timeout_ms=300), 'api')
    return store


def answer_code(response):
    return (response.json().get('error') or {}).get('code')


class ApiFaultTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.direct, self.actor, self.project = create_core()
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.store = service_store(self.proxy)
        self.addCleanup(close_pool, self.store)
        self.client = self.client_for(self.store)
        self.routes = self.routes_of(self.client)

    def client_for(self, store):
        auth = Mock()
        auth.authenticate_bearer.return_value = self.actor
        retrieval = Retrieval(store, Settings('unused', request_timeout=5), Mock(embed=AsyncMock()))
        return TestClient(create_app(Settings('unused', mount_mcp=False), store, auth, retrieval), raise_server_exceptions=False)  # the generic 503 is answered, then raised to the server

    def routes_of(self, client):
        return {
            'read': lambda: client.get('/v1/projects', headers=HEADERS),
            'write': lambda: client.post('/v1/projects', headers=HEADERS, json={'id': 'fault-' + uuid.uuid4().hex[:12], 'title': 'Fault'}),
            'search': lambda: client.post('/v1/search', headers=HEADERS, json={'project_ids': [self.project], 'q': 'anything', 'layers': ['episodic'], 'semantic': False}),
            'ready': lambda: client.get('/health/ready'),
        }

    def bounded(self, ask):
        """The answer of `ask()`, which must come within the pool wait plus a margin; the proxy is restored to release the thread if it did not."""
        result = {}
        thread = threading.Thread(target=lambda: result.update(response=ask()), daemon=True)
        thread.start()
        thread.join(POOL_WAIT + 5)
        stuck = thread.is_alive()
        if stuck:
            self.proxy.restore()
            thread.join(30)
        self.assertFalse(stuck, 'the request hung beyond the pool wait')
        return result['response']

    def recovered(self):
        """True once a request works again (the pool retries its connection on a short backoff: a few requests, never a restart)."""
        for _ in range(40):
            if self.client.get('/v1/projects', headers=HEADERS).status_code == 200:
                return True
        return False

    def warm(self):
        self.assertEqual(self.client.get('/v1/projects', headers=HEADERS).status_code, 200)

    def test_a_cut_database_gives_service_unavailable_on_every_route_and_the_api_recovers(self):
        expected = {'read': (503, 'service_unavailable'), 'write': (503, 'service_unavailable'), 'search': (503, 'service_unavailable'), 'ready': (503, 'not_ready')}
        for route, ask in self.routes.items():
            with self.subTest(route=route):
                self.warm()
                self.proxy.cut()
                response = self.bounded(ask)
                self.assertEqual((response.status_code, answer_code(response)), expected[route])
                self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
                self.proxy.restore()
                self.assertTrue(self.recovered(), 'the API did not recover after the database came back')

    def test_a_mute_database_gives_service_unavailable_within_the_pool_wait_and_the_api_recovers(self):
        """A database that is mute BEFORE the pool made a connection: its first attempt has neither worked nor failed within the wait (connect plazo 2 s > wait 0.5 s). The pool still has free
        slots, so nobody is using them up: it is `service_unavailable` on every route (T-30: `store_busy` is only for a pool with EVERY connection in use, which no timer decides).
        One fresh pool per route (a pool that already holds a connection that dies is the next test)."""
        expected = {'read': (503, 'service_unavailable'), 'write': (503, 'service_unavailable'), 'search': (503, 'service_unavailable'), 'ready': (503, 'not_ready')}
        for route in expected:
            with self.subTest(route=route):
                self.proxy.mute()
                store = service_store(self.proxy)
                self.addCleanup(close_pool, store)
                response = self.bounded(self.routes_of(self.client_for(store))[route])
                self.assertEqual((response.status_code, answer_code(response)), expected[route])
                self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
                self.proxy.restore()
                self.assertTrue(self.recovered(), 'the API did not recover after the database came back')

    def test_a_connection_of_the_pool_that_dies_when_the_database_goes_mute_is_an_outage_on_every_route(self):
        """The pool already held a connection and the mute closed it: the check at hand-out failed, which is evidence of an outage (fix1, gap 3): `service_unavailable`, not a busy pool."""
        expected = {'read': (503, 'service_unavailable'), 'write': (503, 'service_unavailable'), 'search': (503, 'service_unavailable'), 'ready': (503, 'not_ready')}
        for route, ask in self.routes.items():
            with self.subTest(route=route):
                self.warm()
                self.proxy.mute()
                response = self.bounded(ask)
                self.assertEqual((response.status_code, answer_code(response)), expected[route])
                self.proxy.restore()
                self.assertTrue(self.recovered(), 'the API did not recover after the database came back')

    def test_a_slow_database_gives_store_timeout_on_read_and_write_and_a_partial_search(self):
        def sleeper(*args, **kwargs):
            with self.store.transaction() as c:
                c.execute('SELECT pg_sleep(10)')  # past the 300 ms plazo of these tests: the SERVER cancels it
        for route, method in (('read', 'list_projects'), ('write', 'create_project')):
            with self.subTest(route=route), patch.object(self.store, method, sleeper):
                response = self.routes[route]()
                self.assertEqual((response.status_code, answer_code(response)), (503, 'store_timeout'))
                self.assertEqual(response.json()['request_id'], response.headers['X-Request-ID'])
        with self.subTest(route='search'), patch.object(self.store, 'search_items', sleeper):
            response = self.routes['search']()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['backends']['episodic']['status'], 'unavailable')
            self.assertTrue(response.json()['partial'])
        self.assertTrue(self.recovered())

    def test_a_connection_that_died_while_idle_is_replaced_before_it_reaches_a_request(self):
        # The pool checks what it hands out and a dead connection costs one backoff of its check loop (about a second) before the replacement is used: the default wait of 5 s is
        # used here, the 0.5 s of the other tests would give up first.
        store = Store(self.proxy.dsn())
        attach_pool(store, Settings('unused', pool_min=1, pool_max=2, pool_timeout=5.0, connect_timeout=2), 'api')
        self.addCleanup(close_pool, store)
        auth = Mock()
        auth.authenticate_bearer.return_value = self.actor
        client = TestClient(create_app(Settings('unused', mount_mcp=False), store, auth), raise_server_exceptions=False)
        self.assertEqual(client.get('/v1/projects', headers=HEADERS).status_code, 200)
        self.proxy.cut()  # every idle connection of the pool is closed by the "server"...
        self.proxy.restore()  # ...and the database is back at once: the very next request must work, not fail on a dead connection
        self.assertEqual(client.get('/v1/projects', headers=HEADERS).status_code, 200)

    def test_a_connection_cut_in_the_middle_of_a_query_does_not_go_back_to_the_pool_broken(self):
        store = Store(self.proxy.dsn())
        attach_pool(store, Settings('unused', pool_min=1, pool_max=1, pool_timeout=POOL_WAIT * 4, connect_timeout=3), 'api')
        self.addCleanup(close_pool, store)

        def pid():
            with store.transaction() as c:
                return c.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
        first = pid()
        running, outcome = threading.Event(), {}

        def long_query():
            try:
                with store.transaction() as c:
                    running.set()
                    c.execute('SELECT pg_sleep(30)')
            except Exception as exc:
                outcome['error'] = exc
        thread = threading.Thread(target=long_query, daemon=True)
        thread.start()
        self.assertTrue(running.wait(30))
        self.proxy.cut()  # the server is gone while the statement runs
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome['error'], StoreUnavailable)
        self.proxy.restore()
        for _ in range(40):
            try:
                second = pid()
                break
            except StoreUnavailable:
                continue
        else:
            self.fail('the pool did not recover')
        self.assertNotEqual(second, first, 'the connection that lost its server was given to the next transaction')
        self.assertEqual(pid(), second)  # and the replacement is a healthy, reusable one


class WorkerFixture:
    """The database of its own behind the proxy, the pool and the log of the worker tests (shared with `test_store_halfopen.py`)."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.name = 'wfault_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')
        self.addCleanup(drop)
        self.direct_dsn = make_conninfo(dsn, dbname=self.name)
        with patch.dict(os.environ, {'MEMORY_TEST_DSN': self.direct_dsn}):
            self.direct, self.actor, self.pid = create_core(extraction=True)
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.store = Store(self.proxy.dsn(self.direct_dsn))
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=2, pool_timeout=1.0, connect_timeout=2, statement_timeout_ms=30000), 'worker')
        self.addCleanup(close_pool, self.store)
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        self.stream = stream

    def events(self, name=None):
        entries = [json.loads(line) for line in self.stream.getvalue().splitlines() if line.startswith('{')]
        return [entry for entry in entries if name is None or entry['event'] == name]


class WorkerFaultTests(WorkerFixture, unittest.IsolatedAsyncioTestCase):
    """The accesses of the worker against a real database behind the proxy, in a database of its own."""
    async def test_a_claim_against_a_mute_server_fails_within_the_plazo_and_the_worker_stops_without_needing_a_kill(self):
        """Debt of phase 2 (T-08, gap 4): with no plazo a claim hung about two minutes and the stop ended in SIGKILL."""
        ingested = self.direct.ingest_event(self.actor, event(self.pid))['jobs'][0]
        self.proxy.mute()
        worker = Worker(self.store, worker_settings(), {'extract': Mock(extract=AsyncMock())})  # the real, stop-aware wait between claims
        task = asyncio.create_task(worker.run())
        started = time.monotonic()
        while worker.store_failures < 1 and time.monotonic() - started < 30:
            await asyncio.sleep(0.02)
        self.assertGreaterEqual(worker.store_failures, 1, 'a claim against a mute server never gave up')
        self.assertGreaterEqual(self.proxy.accepted, 1)  # and it really went to the mute proxy
        worker.stopping.set()  # SIGTERM
        await asyncio.wait_for(task, 5)  # run() ends by itself: nothing is left for a kill to do
        stopping = time.monotonic()
        await asyncio.wait_for(asyncio.to_thread(close_pool, self.store), 10)
        self.assertLess(time.monotonic() - stopping, 5, 'closing the pool of a worker whose database is mute took too long')
        with self.direct.transaction() as c:  # the job was never touched
            self.assertEqual(c.execute('SELECT state,attempts FROM memory.jobs WHERE id=%s', (ingested,)).fetchone(), {'state': 'pending', 'attempts': 0})
        self.assertTrue(any(entry.get('reason') == 'claim' for entry in self.events('store_unavailable')))

    async def test_the_stored_vector_read_against_a_mute_server_ends_as_a_database_outage_and_not_as_provider_timeout(self):
        """Debt of phase 2 (T-09, gap 3): the read of the stored vector (stage `read`) used to end as `provider_timeout` when the database stopped answering."""
        job = {'id': 'synthetic-job', 'fence': 1, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a' * 64, 'policy': {}, 'project_id': self.pid, 'item_id': 'item', 'resource_type': 'document',
               'version': 1, 'payload': {'title': 'Long note', 'content': long_text(6000)}}  # more than one fragment: the stored vector is read first

        def claim(*args):
            self.proxy.mute()  # the claim worked; the database stops answering before the read
            return job
        provider = Mock(embed=AsyncMock(side_effect=AssertionError('the provider must not be reached')), embed_many=AsyncMock(side_effect=AssertionError('the provider must not be reached')))
        self.store.claim_job = claim
        self.store.fail_job = Mock(side_effect=AssertionError('an outage of the database must not fail a job'))
        worker = Worker(self.store, worker_settings(), {'embed': provider})
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))
        provider.embed_many.assert_not_called()
        self.assertEqual(worker.store_failures, 1)
        self.assertEqual([entry['reason'] for entry in self.events('store_unavailable')], ['read'])
        self.assertEqual([entry for entry in self.events('job_failed')], [])  # in particular no `provider_timeout`
        self.assertEqual(self.events('job_completed'), [])


class PersistWithTheHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    """Debt of phase 2 (review 3, n.o 3-5): `_persist` asks the database whether a write that failed ambiguously landed also when the HEARTBEAT is the one that saw the lease go, and the
    paths of `_persist` and `job_outcome` are exercised with the heartbeat active."""
    def setUp(self):
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store = Mock()
        self.store.claim_job.return_value = self.job
        self.store.renew_lease.return_value = True
        self.receipt = {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        self.provider = Mock(extract=AsyncMock(return_value=self.receipt))
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        self.stream = stream

    def events(self, name):
        return [entry for entry in (json.loads(line) for line in self.stream.getvalue().splitlines() if line.startswith('{')) if entry['event'] == name]

    def worker(self, waiter=None, heartbeat_wait=None):
        return Worker(self.store, worker_settings(), {'extract': self.provider}, rng=lambda: 1.0, waiter=waiter or Recorder(), heartbeat_wait=heartbeat_wait)

    async def persist(self, worker, lost):
        return await worker._persist(self.job, [worker.clock() + 240], lost, 'extract', 'complete', self.store.complete_job, self.receipt)

    async def test_a_lease_the_heartbeat_lost_is_not_given_up_when_the_write_had_landed(self):
        self.store.complete_job.side_effect = DOWN  # the COMMIT whose answer was lost
        lost = asyncio.Event()
        lost.set()  # the heartbeat already saw the lease go
        worker = self.worker()
        with patch('memory_platform.worker.job_outcome', return_value={'state': 'succeeded', 'error_code': None}) as outcome:
            self.assertIs(await self.persist(worker, lost), True)
        outcome.assert_called_once()
        self.assertEqual(self.events('job_write_abandoned'), [])

    async def test_a_lease_the_heartbeat_lost_is_given_up_when_the_job_is_not_as_this_write_leaves_it(self):
        self.store.complete_job.side_effect = DOWN
        lost = asyncio.Event()
        lost.set()
        worker = self.worker()
        with patch('memory_platform.worker.job_outcome', return_value={'state': 'running', 'error_code': None}):
            with self.assertRaises(Abandoned) as raised:
                await self.persist(worker, lost)
        self.assertEqual(raised.exception.reason, 'lease_lost')
        self.assertEqual([entry['reason'] for entry in self.events('job_write_abandoned')], ['complete:lease_lost'])

    async def test_when_job_outcome_itself_fails_the_write_is_not_proven_and_the_lease_is_given_up(self):
        self.store.complete_job.side_effect = DOWN
        lost = asyncio.Event()
        lost.set()
        worker = self.worker()
        for failure in (DOWN, RuntimeError('a bug reading the job')):
            with self.subTest(failure=type(failure).__name__), patch('memory_platform.worker.job_outcome', side_effect=failure):
                self.stream.truncate(0)
                self.stream.seek(0)
                with self.assertRaises(Abandoned):
                    await self.persist(worker, lost)
                self.assertEqual(len(self.events('job_outcome_unread')), 1)  # logged, never trusted
                self.assertEqual([entry['reason'] for entry in self.events('job_write_abandoned')], ['complete:lease_lost'])

    async def test_the_heartbeat_that_sees_the_lease_go_while_the_write_waits_does_not_lose_a_write_that_landed(self):
        """End to end through `run_once`: the first write fails ambiguously, the heartbeat then finds the lease gone, the job is already `succeeded`: it counts as completed."""
        beat, renewed = asyncio.Event(), threading.Event()

        async def heartbeat_wait(seconds):
            await beat.wait()  # the heartbeat beats only once the write is waiting

        def renew(*args):
            renewed.set()
            return False  # the fence moved: the write that "failed" is the one that landed
        self.store.renew_lease.side_effect = renew
        self.store.complete_job.side_effect = DOWN

        async def waiter(seconds):
            beat.set()
            while not renewed.is_set():
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.05)  # the coroutine of the heartbeat takes the answer and marks the lease lost
        worker = self.worker(waiter=waiter, heartbeat_wait=heartbeat_wait)
        with patch('memory_platform.worker.job_outcome', return_value={'state': 'succeeded', 'error_code': None}), patch.object(observability, 'record_job') as record:
            self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))
        self.assertEqual(self.store.complete_job.call_count, 1)
        self.assertEqual(self.events('job_write_abandoned'), [])
        self.assertEqual(len(self.events('job_completed')), 1)
        self.store.fail_job.assert_not_called()
        record.assert_called_once()
        self.assertEqual(record.call_args.args[2], 'completed')  # fix1 (gap 2): the log and the metric say the same, `completed`, and not `lost`

    async def test_with_the_heartbeat_beating_all_along_the_write_is_repeated_and_lands(self):
        """The heartbeat and `_persist` both renew the lease while the database is down: the write ends up written once it answers, with no attempt spent."""
        gate = asyncio.Event()
        beats = []

        async def heartbeat_wait(seconds):
            beats.append(seconds)
            if len(beats) > 30:
                await gate.wait()  # enough beats: the rest of the test is not a busy loop
            await asyncio.sleep(0)
        self.store.complete_job.side_effect = [DOWN, DOWN, True]
        worker = self.worker(heartbeat_wait=heartbeat_wait)
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))
        self.assertEqual(self.store.complete_job.call_count, 3)
        self.assertGreaterEqual(self.store.renew_lease.call_count, 2)  # renewed between failures (by the write and by the heartbeat), never let to expire
        self.store.fail_job.assert_not_called()
        self.assertEqual(self.events('job_write_abandoned'), [])
        self.assertEqual(len(self.events('job_completed')), 1)


class WriteRetryDefaultTests(unittest.TestCase):
    """Debt of phase 2 (review 3, n.o 5): the default of MEMORY_WORKER_WRITE_RETRY_SECONDS is the lease and is validated against the same range as an explicit value."""
    def test_the_default_that_comes_from_the_lease_is_checked_against_its_range(self):
        self.assertEqual(worker_write_retry_seconds({}, 240), 240.0)
        self.assertEqual(worker_write_retry_seconds({}, 1), 1.0)
        self.assertEqual(worker_write_retry_seconds({}, 86400), 86400.0)
        for lease in (0, -5, 86401, float('nan')):
            with self.subTest(lease=lease), self.assertRaisesRegex(ValueError, 'MEMORY_LEASE_SECONDS must be between 1 and 86400'):
                worker_write_retry_seconds({}, lease)
            with self.subTest(lease=lease, explicit=True), self.assertRaisesRegex(ValueError, 'MEMORY_LEASE_SECONDS must be between 1 and 86400'):
                worker_write_retry_seconds({'MEMORY_WORKER_WRITE_RETRY_SECONDS': '30'}, lease)  # fix1 (gap 10): the lease is validated also when the budget is set
        self.assertEqual(worker_write_retry_seconds({'MEMORY_WORKER_WRITE_RETRY_SECONDS': '30'}, 240), 30.0)

    def test_a_lease_out_of_range_stops_the_start_of_every_process_that_reads_the_settings(self):
        for lease in ('0', '86401'):
            with self.subTest(lease=lease), patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_LEASE_SECONDS': lease}, clear=True):
                with self.assertRaisesRegex(ValueError, 'MEMORY_LEASE_SECONDS'):
                    Settings.from_env()
            with self.subTest(lease=lease, explicit=True), patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_LEASE_SECONDS': lease, 'MEMORY_WORKER_WRITE_RETRY_SECONDS': '30'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'MEMORY_LEASE_SECONDS'):
                    Settings.from_env()
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_LEASE_SECONDS': '300'}, clear=True):
            self.assertEqual(Settings.from_env().worker_write_retry_seconds, 300.0)


if __name__ == '__main__':
    unittest.main()
