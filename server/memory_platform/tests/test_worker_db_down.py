"""The worker with the database gone (I3 / CA-09, CA-10, CA-11): it stays alive, waits with a growing and capped backoff, never turns a database failure into a
failed job, and every wait is driven by the test (injected clock, jitter and waiter), never by real time.

Two kinds of test: the loop and its branches against a mock store (every access of the worker to the database, not only the claim), and the whole path against a
real PostgreSQL behind the `FaultProxy`, in a database of its own so that the queue holds only the job of the test."""
import asyncio
import io
import itertools
import logging
import os
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

import psycopg

from memory_platform import observability
from memory_platform.config import DEFAULT_BACKOFF_MAX, Settings, worker_db_backoff_max
from memory_platform.errors import StoreUnavailable
from memory_platform.store import Store
from memory_platform.tests.fault_proxy import FaultProxy
from memory_platform.tests.test_store import create_core, event, extraction_receipt
from memory_platform.worker import BACKOFF_FIRST, IDLE_SECONDS, Worker, backoff_delay

SECRET = 'hunter2-never-in-a-log'
DOWN = psycopg.OperationalError(f'connection to server at "10.20.30.40", port 5432 failed: password authentication failed password={SECRET}')


def settings(**changes):
    return Settings('unused', **{'lease_seconds': 240, 'max_attempts': 3, 'worker_db_backoff_max': 60.0, **changes})


class Recorder:
    """A waiter that records every wait it is asked for and answers at once; `hook(n, seconds)` runs on the n-th call."""
    def __init__(self, hook=None):
        self.delays, self.hook = [], hook

    async def __call__(self, seconds):
        self.delays.append(seconds)
        if self.hook:
            self.hook(len(self.delays), seconds)


class BackoffTests(unittest.TestCase):
    def test_the_wait_doubles_with_every_consecutive_failure_and_stops_at_the_cap(self):
        top = lambda: 1.0
        self.assertEqual([backoff_delay(n, 60, top) for n in range(1, 11)], [1, 2, 4, 8, 16, 32, 60, 60, 60, 60])
        self.assertEqual([backoff_delay(n, 5, top) for n in range(1, 6)], [1, 2, 4, 5, 5])

    def test_it_never_goes_above_the_cap_however_long_the_outage(self):
        for failures in (1, 7, 64, 1000, 10**9):
            for jitter in (0.0, 0.5, 0.999999, 1.0):
                self.assertLessEqual(backoff_delay(failures, 60, lambda: jitter), 60)
        self.assertLessEqual(backoff_delay(1, 0.25, lambda: 1.0), 0.25)  # a cap below the first wait wins over it

    def test_the_jitter_picks_a_point_between_half_the_ceiling_and_the_ceiling(self):
        for failures, ceiling in ((1, 1), (2, 2), (3, 4), (7, 60), (50, 60)):
            low, high = backoff_delay(failures, 60, lambda: 0.0), backoff_delay(failures, 60, lambda: 1.0)
            middle = backoff_delay(failures, 60, lambda: 0.5)
            self.assertEqual((low, high), (ceiling/2, ceiling))
            self.assertTrue(low < middle < high)

    def test_the_default_jitter_is_random_and_stays_inside_its_bounds(self):
        values = {backoff_delay(4, 60) for _ in range(50)}
        self.assertGreater(len(values), 1)
        self.assertTrue(all(BACKOFF_FIRST*8/2 <= value <= BACKOFF_FIRST*8 for value in values))

    def test_the_cap_comes_from_the_environment_with_a_default_of_sixty_seconds_and_is_validated(self):
        self.assertEqual(DEFAULT_BACKOFF_MAX, 60.0)
        self.assertEqual(worker_db_backoff_max({}), 60.0)
        self.assertEqual(worker_db_backoff_max({'MEMORY_WORKER_DB_BACKOFF_MAX': '7.5'}), 7.5)
        for bad in ('0', '-1', 'abc', 'nan', 'inf', '', '99999'):
            with self.assertRaises(ValueError, msg=bad):
                worker_db_backoff_max({'MEMORY_WORKER_DB_BACKOFF_MAX': bad})
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_WORKER_DB_BACKOFF_MAX': '9'}, clear=True):
            self.assertEqual(Settings.from_env().worker_db_backoff_max, 9.0)
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x'}, clear=True):
            self.assertEqual(Settings.from_env().worker_db_backoff_max, 60.0)
        with patch.dict(os.environ, {'MEMORY_DSN': 'postgresql://x', 'MEMORY_WORKER_DB_BACKOFF_MAX': '0'}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


class LoopTests(unittest.IsolatedAsyncioTestCase):
    """`Worker.run()` and `Worker.run_once()` against a mock store: every access to the database is classified."""
    def setUp(self):
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store = Mock()
        self.store.claim_job.return_value = None
        self.receipt = {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        self.provider = Mock(extract=AsyncMock(return_value=self.receipt))

    def worker(self, waiter=None, rng=None, **changes):
        return Worker(self.store, settings(**changes), {'extract': self.provider}, rng=rng or (lambda: 1.0), waiter=waiter)

    def claims(self, outcomes, then_stop):
        """claim_job answers `outcomes` in turn (an exception is raised); the call after the last one asks the worker to stop."""
        calls = itertools.count()
        def claim(*args):
            n = next(calls)
            if n < len(outcomes):
                if isinstance(outcomes[n], BaseException):
                    raise outcomes[n]
                return outcomes[n]
            then_stop()
            return None
        self.store.claim_job.side_effect = claim

    async def test_run_does_not_end_when_the_claim_fails_again_and_again_and_the_waits_grow_to_the_cap(self):
        waiter = Recorder()
        worker = self.worker(waiter)
        self.claims([DOWN]*12, lambda: worker.stopping.set())
        await asyncio.wait_for(worker.run(), 60)
        self.assertEqual(self.store.claim_job.call_count, 13)  # the twelve failures did not end it: it went on to the thirteenth claim
        self.assertEqual(waiter.delays[:12], [1, 2, 4, 8, 16, 32, 60, 60, 60, 60, 60, 60])
        self.assertEqual(waiter.delays[12], IDLE_SECONDS)  # the claim that worked found an empty queue: the ordinary idle wait
        self.assertLessEqual(max(waiter.delays), 60)

    async def test_the_cap_is_the_configured_one(self):
        waiter = Recorder()
        worker = self.worker(waiter, worker_db_backoff_max=3)
        self.claims([DOWN]*5, lambda: worker.stopping.set())
        await asyncio.wait_for(worker.run(), 60)
        self.assertEqual(waiter.delays[:5], [1, 2, 3, 3, 3])

    async def test_one_access_that_works_sets_the_backoff_back_to_the_start(self):
        waiter = Recorder()
        worker = self.worker(waiter, rng=lambda: 0.5)
        self.claims([DOWN, DOWN, DOWN, None, DOWN], lambda: worker.stopping.set())
        await asyncio.wait_for(worker.run(), 60)
        self.assertEqual(waiter.delays[:5], [0.75, 1.5, 3.0, IDLE_SECONDS, 0.75])  # the fifth claim waits like a first failure, not like a fourth

    async def test_the_jitter_comes_from_the_injected_source_so_two_workers_do_not_wait_the_same(self):
        for jitter, expected in ((0.0, [0.5, 1.0, 2.0]), (1.0, [1.0, 2.0, 4.0])):
            self.store.reset_mock()
            waiter = Recorder()
            worker = Worker(self.store, settings(), {'extract': self.provider}, rng=lambda: jitter, waiter=waiter)
            self.claims([DOWN]*3, lambda: worker.stopping.set())
            await asyncio.wait_for(worker.run(), 60)
            self.assertEqual(waiter.delays[:3], expected)

    async def test_run_once_raises_store_unavailable_when_the_claim_fails_and_counts_nothing_as_a_job(self):
        self.store.claim_job.side_effect = DOWN
        worker = self.worker(Recorder())
        with self.assertRaises(StoreUnavailable):
            await worker.run_once()
        self.store.fail_job.assert_not_called()
        self.assertEqual(worker.store_failures, 1)

    async def test_an_error_of_the_loop_that_is_not_the_database_is_logged_apart_and_the_worker_goes_on(self):
        waiter = Recorder()
        worker = self.worker(waiter)
        self.claims([RuntimeError('a bug, not the database'), DOWN], lambda: worker.stopping.set())
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        await asyncio.wait_for(worker.run(), 60)
        events = [line for line in stream.getvalue().splitlines() if line]
        self.assertTrue(any('"event":"worker_loop_error"' in line and '"exc_type":"RuntimeError"' in line for line in events), events)
        self.assertTrue(any('"event":"store_unavailable"' in line and '"reason":"claim"' in line for line in events), events)
        self.assertEqual(waiter.delays[:2], [1, 2])  # both back off: a bug in the loop is not allowed to spin the CPU either

    async def test_store_unavailable_is_logged_with_its_stage_and_count_and_never_with_the_dsn_or_the_password(self):
        waiter = Recorder()
        worker = self.worker(waiter)
        self.claims([DOWN, DOWN, DOWN], lambda: worker.stopping.set())
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        await asyncio.wait_for(worker.run(), 60)
        text = stream.getvalue()
        lines = [line for line in text.splitlines() if '"event":"store_unavailable"' in line]
        self.assertEqual(len(lines), 3)
        for number, line in enumerate(lines, start=1):
            self.assertIn('"reason":"claim"', line)
            self.assertIn(f'"count":{number}', line)
            self.assertIn('"exc_type":"OperationalError"', line)
        for leaked in (SECRET, '10.20.30.40', 'password authentication'):
            self.assertNotIn(leaked, text)

    async def test_last_store_ok_moves_only_with_an_access_that_worked(self):
        now = [100.0]
        worker = Worker(self.store, settings(), {'extract': self.provider}, clock=lambda: now[0], rng=lambda: 1.0, waiter=Recorder())
        self.assertEqual(worker.last_store_ok, 100.0)
        for at, outcome, expected in ((110.0, DOWN, 100.0), (130.0, None, 130.0), (140.0, DOWN, 130.0), (5000.0, DOWN, 130.0)):
            now[0] = at
            self.store.claim_job.side_effect = [outcome] if outcome is not None else None
            self.store.claim_job.return_value = None
            try:
                await worker.run_once()
            except StoreUnavailable:
                pass
            self.assertEqual(worker.last_store_ok, expected, at)  # a long outage does not make it look recent

    async def test_a_stop_ends_the_wait_of_a_backoff_at_once(self):
        with patch('memory_platform.worker.BACKOFF_FIRST', 3600.0):  # a wait that would last an hour if it were not interrupted
            worker = Worker(self.store, settings(worker_db_backoff_max=3600), {'extract': self.provider}, rng=lambda: 1.0)
            loop = asyncio.get_running_loop()
            def claim(*args):
                loop.call_soon_threadsafe(worker.stopping.set)
                raise DOWN
            self.store.claim_job.side_effect = claim
            await asyncio.wait_for(worker.run(), 20)
        self.assertEqual(self.store.claim_job.call_count, 1)

    async def test_the_default_wait_returns_when_the_worker_is_told_to_stop_while_it_waits(self):
        worker = Worker(self.store, settings(), {'extract': self.provider})
        waiting = asyncio.ensure_future(worker._wait(3600))
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())
        worker.stopping.set()
        await asyncio.wait_for(waiting, 20)

    async def test_run_with_a_stop_already_asked_claims_nothing(self):
        worker = self.worker(Recorder())
        worker.stopping.set()
        await asyncio.wait_for(worker.run(), 20)
        self.store.claim_job.assert_not_called()

    async def test_the_heartbeat_keeps_beating_through_a_database_failure_and_the_job_completes(self):
        loop = asyncio.get_running_loop()
        release = asyncio.Event()
        async def extract(source):
            await release.wait()
            return self.receipt
        self.provider.extract.side_effect = extract
        beats = []
        def renew(job_id, fence, lease):
            beats.append(job_id)
            if len(beats) <= 2:
                raise DOWN
            loop.call_soon_threadsafe(release.set)
            return True
        self.store.claim_job.return_value = self.job
        self.store.renew_lease.side_effect = renew
        async def beat(seconds):
            await asyncio.sleep(0)  # the pause of the heartbeat is the test's, not the clock's
        worker = Worker(self.store, settings(), {'extract': self.provider}, rng=lambda: 1.0, waiter=Recorder(), heartbeat_wait=beat)
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))
        self.assertGreaterEqual(len(beats), 3)  # two beats without a database, the third one renewed
        self.store.complete_job.assert_called_once_with('job', 4, self.receipt)  # the job was not given up as lost
        self.store.fail_job.assert_not_called()
        self.assertEqual(stream.getvalue().count('"event":"store_unavailable"'), 2)
        self.assertIn('"reason":"heartbeat"', stream.getvalue())

    async def test_a_heartbeat_that_loses_the_lease_still_ends_the_job_as_lost(self):
        release = asyncio.Event()
        async def extract(source):
            await release.wait()
            return self.receipt
        self.provider.extract.side_effect = extract
        self.store.claim_job.return_value = self.job
        self.store.renew_lease.return_value = False
        async def beat(seconds):
            await asyncio.sleep(0)
        worker = Worker(self.store, settings(), {'extract': self.provider}, rng=lambda: 1.0, waiter=Recorder(), heartbeat_wait=beat)
        real = observability.log_event
        def log_event(name, *args, **fields):
            real(name, *args, **fields)
            if name == 'lease_lost':
                release.set()  # the provider is let go in the same step in which the heartbeat marks the lease as lost: no race
        with patch('memory_platform.worker.observability.log_event', side_effect=log_event):
            await asyncio.wait_for(worker.run_once(), 30)
        self.store.complete_job.assert_not_called()
        self.store.fail_job.assert_not_called()


class DatabaseDownTests(unittest.IsolatedAsyncioTestCase):
    """A real PostgreSQL behind the `FaultProxy`, in a database of its own: the worker uses the proxy, the test reads the truth directly."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        from psycopg.conninfo import make_conninfo
        self.name = 'down_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

        self.addCleanup(drop)
        self.direct_dsn = make_conninfo(dsn, dbname=self.name)
        with patch.dict(os.environ, {'MEMORY_TEST_DSN': self.direct_dsn}):
            self.direct, self.actor, self.pid = create_core(extraction=True)
        self.jid = self.direct.ingest_event(self.actor, event(self.pid))['jobs'][0]
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.store = Store(self.proxy.dsn(self.direct_dsn))
        self.receipt = extraction_receipt()

    def row(self):
        with self.direct.transaction() as c:
            return c.execute('SELECT state,attempts,error_code FROM memory.jobs WHERE id=%s', (self.jid,)).fetchone()

    def worker(self, extract, cap=60.0, **options):
        return Worker(self.store, settings(worker_db_backoff_max=cap), {'extract': Mock(extract=extract)}, rng=lambda: 1.0, **options)

    async def test_run_survives_a_cut_database_and_processes_the_queue_when_it_returns(self):
        self.proxy.cut()
        waiter = Recorder(lambda n, seconds: self.proxy.restore() if n == 6 else None)

        async def extract(source):
            worker.stopping.set()  # one job is all this test needs
            return self.receipt
        worker = self.worker(extract, cap=8, waiter=waiter)
        await asyncio.wait_for(worker.run(), 120)
        self.assertEqual(waiter.delays, [1, 2, 4, 8, 8, 8])  # six claims against a cut database, growing up to the configured cap
        self.assertGreaterEqual(self.proxy.accepted, 6)  # and each of them really went to the proxy
        self.assertEqual({k: self.row()[k] for k in ('state', 'attempts', 'error_code')}, {'state': 'succeeded', 'attempts': 1, 'error_code': None})
        self.assertEqual(worker.store_failures, 0)


if __name__ == '__main__':
    unittest.main()
