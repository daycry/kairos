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
from memory_platform.errors import MemoryError, StoreUnavailable
from memory_platform.providers import ProviderError
from memory_platform.store import Store
from memory_platform.tests.fault_proxy import FaultProxy, expire_lease
from memory_platform.tests.test_store import create_core, event, extraction_receipt
from memory_platform.tests.test_worker import long_text
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

    # --- what happens to the job when the database goes while it runs (CA-09, CA-11) -------------------------------------------------

    # The outcome of a job is never lost to a database that does not answer: `complete_job` and `fail_job` are repeated in place, with the claim's
    # backoff, and the lease is renewed once the database answers (a decision of review 1 of phase 2; CA-09, CA-11).

    def clocked(self, hook=None, lease=240, **changes):
        """A worker whose clock only moves when a wait is asked for (`step` seconds per wait): the lease runs out by the test's clock, never the real one."""
        now = [1000.0]
        def on_wait(n, seconds):
            now[0] += step[0]
            if hook:
                hook(n, seconds)
        step = [1.0]
        waiter = Recorder(on_wait)
        worker = Worker(self.store, settings(lease_seconds=lease, **changes), {'extract': self.provider}, clock=lambda: now[0], rng=lambda: 1.0, waiter=waiter)
        return worker, waiter, step

    def capture_log(self):
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        return stream

    async def test_a_database_failure_while_completing_is_repeated_in_place_with_the_same_result(self):
        self.store.claim_job.return_value = self.job
        self.store.complete_job.side_effect = [DOWN, DOWN, True]
        worker, waiter, _ = self.clocked()
        stream = self.capture_log()
        self.assertTrue(await worker.run_once())
        self.assertEqual(self.store.complete_job.call_count, 3)  # the result was kept and written again, not lost
        self.assertTrue(all(call.args == ('job', 4, self.receipt) for call in self.store.complete_job.call_args_list))
        self.assertEqual(waiter.delays, [1, 1])  # the claim's backoff (a renewal that works starts it over, as any access that works does)
        self.assertEqual(self.store.renew_lease.call_count, 2)  # the lease is renewed each time the database answers again, before writing
        self.store.fail_job.assert_not_called()  # not failed, no `provider_error`
        self.assertEqual(worker.store_failures, 0)  # the write worked at last
        self.assertIn('"event":"job_completed"', stream.getvalue())
        self.assertEqual(stream.getvalue().count('"event":"store_unavailable"'), 2)
        self.assertNotIn('job_write_abandoned', stream.getvalue())

    async def test_a_database_failure_in_fail_job_is_repeated_in_place_in_every_branch_of_the_provider_failure(self):
        errors = {'retryable provider error': (ProviderError('provider_unavailable', retryable=True), 'provider_unavailable'),
                  'provider error': (ProviderError('provider_rejected'), 'provider_rejected'),
                  'provider timeout': (TimeoutError(), 'provider_timeout'), 'domain error': (MemoryError('invalid_embedding', 'x', 422), 'invalid_embedding'),
                  'unexpected error': (RuntimeError('boom'), 'provider_error')}
        for name, (error, code) in errors.items():
            with self.subTest(name):
                self.store.reset_mock()
                self.store.claim_job.return_value = self.job
                self.store.fail_job.side_effect = [DOWN, DOWN, True]
                self.provider.extract.side_effect = error
                worker, waiter, _ = self.clocked()
                self.assertTrue(await worker.run_once())
                self.assertEqual(self.store.fail_job.call_count, 3)  # it tried, the database did not answer, and the failure was written again
                self.assertEqual({call.args[:3] for call in self.store.fail_job.call_args_list}, {('job', 4, code)})  # always the provider's own code
                self.assertEqual(len({call.args for call in self.store.fail_job.call_args_list}), 1)
                self.store.complete_job.assert_not_called()
                self.assertEqual(self.store.renew_lease.call_count, 2)
                self.assertEqual(worker.store_failures, 0)

    async def test_a_failure_that_is_the_databases_but_not_an_outage_is_failed_with_its_own_code_not_provider_error(self):
        from psycopg import errors
        for exc in (errors.QueryCanceled('canceling statement due to statement timeout'), errors.LockNotAvailable('lock timeout'), errors.SerializationFailure('x')):
            with self.subTest(type(exc).__name__):
                self.store.reset_mock()
                self.store.claim_job.return_value = self.job
                self.store.complete_job.side_effect = exc
                worker, waiter, _ = self.clocked()
                self.assertTrue(await worker.run_once())
                self.store.fail_job.assert_called_once()
                self.assertEqual(self.store.fail_job.call_args.args[:3], ('job', 4, 'store_error'))  # distinguishable from a provider failure
                self.assertEqual(waiter.delays, [])  # and not waited for as if the database were gone
                self.assertEqual(worker.store_failures, 0)

    async def test_when_the_lease_runs_out_before_the_database_returns_the_worker_gives_up_and_says_so(self):
        self.store.claim_job.return_value = self.job
        self.store.complete_job.side_effect = DOWN
        self.store.renew_lease.side_effect = DOWN
        worker, waiter, step = self.clocked(lease=240)
        step[0] = 100.0  # every wait moves the clock 100 s: the third one is past the 240 s lease
        stream = self.capture_log()
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))  # it returns: no hang
        self.assertEqual(self.store.complete_job.call_count, 1)  # the database never answered: one attempt, the waits did the rest
        self.assertEqual(len(waiter.delays), 3)
        self.store.fail_job.assert_not_called()
        lines = [line for line in stream.getvalue().splitlines() if '"event":"job_write_abandoned"' in line]
        self.assertEqual(len(lines), 1, stream.getvalue())
        for field in ('"reason":"complete:lease_expired"', '"destination":"extract"'):
            self.assertIn(field, lines[0])
        self.assertNotIn('"event":"job_completed"', stream.getvalue())

    async def test_when_the_database_returns_but_the_lease_is_no_longer_ours_the_worker_gives_up_without_writing(self):
        for stage, setup in (('complete', lambda: setattr(self.store.complete_job, 'side_effect', [DOWN, True])),
                             ('fail', lambda: (setattr(self.store.fail_job, 'side_effect', [DOWN, True]), setattr(self.provider.extract, 'side_effect', ProviderError('provider_rejected'))))):
            with self.subTest(stage):
                self.store.reset_mock()
                self.store.claim_job.return_value = self.job
                setup()
                self.store.renew_lease.return_value = False  # the database answers: the lease expired meanwhile
                worker, waiter, _ = self.clocked()
                stream = self.capture_log()
                self.assertTrue(await worker.run_once())
                self.assertEqual(self.store.complete_job.call_count + self.store.fail_job.call_count, 1)  # nothing written after the lease was lost
                self.assertIn('"reason":"%s:lease_lost"' % stage, stream.getvalue())
                self.assertNotIn('"event":"job_completed"', stream.getvalue())
                observability.remove_logging()

    async def test_a_complete_that_answers_false_is_not_counted_as_completed_in_the_log_or_the_metric(self):
        self.store.claim_job.return_value = self.job
        self.store.complete_job.return_value = False  # the fence moved: somebody else owns the job
        worker, _, _ = self.clocked()
        stream = self.capture_log()
        before = observability.REGISTRY.get_sample_value('kairos_worker_jobs_total', {'destination': 'extract', 'outcome': 'completed'}) or 0
        lost_before = observability.REGISTRY.get_sample_value('kairos_worker_jobs_total', {'destination': 'extract', 'outcome': 'lost'}) or 0
        self.assertTrue(await worker.run_once())
        self.assertNotIn('"event":"job_completed"', stream.getvalue())
        self.assertIn('"reason":"complete:fence"', stream.getvalue())
        self.assertEqual(observability.REGISTRY.get_sample_value('kairos_worker_jobs_total', {'destination': 'extract', 'outcome': 'completed'}) or 0, before)
        self.assertEqual(observability.REGISTRY.get_sample_value('kairos_worker_jobs_total', {'destination': 'extract', 'outcome': 'lost'}) or 0, lost_before+1)

    async def test_a_stop_ends_the_wait_to_write_again_and_the_worker_gives_up_the_job(self):
        with patch('memory_platform.worker.BACKOFF_FIRST', 3600.0):  # a wait that would last an hour if a stop did not interrupt it
            worker = Worker(self.store, settings(worker_db_backoff_max=3600), {'extract': self.provider}, rng=lambda: 1.0)
            loop = asyncio.get_running_loop()
            self.store.claim_job.return_value = self.job
            def complete(*args):
                loop.call_soon_threadsafe(worker.stopping.set)
                raise DOWN
            self.store.complete_job.side_effect = complete
            stream = self.capture_log()
            self.assertTrue(await asyncio.wait_for(worker.run_once(), 20))
        self.assertEqual(self.store.complete_job.call_count, 1)
        self.assertIn('"reason":"complete:stopping"', stream.getvalue())
        self.store.fail_job.assert_not_called()

    async def test_the_renewal_of_the_lease_waits_for_the_database_too(self):
        self.store.claim_job.return_value = self.job
        self.store.complete_job.side_effect = [DOWN, True]
        self.store.renew_lease.side_effect = [DOWN, True]  # the database answers the write's retry only after a second wait
        worker, waiter, _ = self.clocked()
        self.assertTrue(await worker.run_once())
        self.assertEqual(waiter.delays[:2], [1, 2])  # two waits: one for the write, one for the renewal
        self.assertEqual(self.store.complete_job.call_count, 2)
        self.assertEqual(self.store.renew_lease.call_count, 2)

    async def test_the_provider_failure_policy_is_the_one_it_always_was_when_the_database_answers(self):
        self.store.claim_job.return_value = self.job
        self.provider.extract.side_effect = ProviderError('provider_unavailable', retryable=True)
        await self.worker(Recorder()).run_once()
        args = self.store.fail_job.call_args.args
        self.assertEqual(args[:3], ('job', 4, 'provider_unavailable'))
        self.assertIsNotNone(args[3])  # retryable and attempts < max_attempts: it is scheduled again
        self.assertEqual(args[4:], (False,))
        self.store.fail_job.reset_mock()
        self.job['attempts'] = 3
        await self.worker(Recorder()).run_once()
        self.assertIsNone(self.store.fail_job.call_args.args[3])  # attempts exhausted: no more retries (worker.py policy, unchanged)

    async def test_a_database_failure_reading_the_stored_vector_is_not_a_provider_failure(self):
        job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a'*64, 'policy': {}, 'project_id': 'p', 'item_id': 'i',
               'resource_type': 'document', 'version': 1, 'payload': {'title': 'Long note', 'content': long_text(20000)}}
        self.store.claim_job.return_value = job
        embed_many = AsyncMock(side_effect=AssertionError('the provider must not be called when the stored vector could not be read'))
        provider = Mock(embed=AsyncMock(), embed_many=embed_many)
        worker = Worker(self.store, settings(), {'embed': provider}, rng=lambda: 1.0, waiter=Recorder())
        with patch('memory_platform.worker.stored_item_vector', side_effect=DOWN):
            self.assertTrue(await worker.run_once())
        self.store.fail_job.assert_not_called()
        self.store.complete_job.assert_not_called()

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

    def at_attempt(self, attempts):
        """The job as its `attempts`-th claim will find it: the claim of the test is that attempt."""
        with self.direct.transaction() as c:
            c.execute('UPDATE memory.jobs SET attempts=%s WHERE id=%s', (attempts-1, self.jid))

    async def test_a_cut_during_complete_job_in_the_last_attempt_still_completes_the_job_with_its_result(self):
        """(a) MEMORY_MAX_ATTEMPTS=3, the job in its 3rd attempt, the database goes after the provider answered and returns before the lease ends."""
        self.at_attempt(3)
        waiter = Recorder(lambda n, seconds: self.proxy.restore())

        async def extract(source):
            self.proxy.cut()  # the database goes away after the claim and before the receipt is stored
            return self.receipt
        worker = self.worker(extract, waiter=waiter)
        self.assertTrue(await worker.run_once())
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('succeeded', 3, None))  # the result is there; never `attempts_exhausted`
        with self.direct.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.projection_receipts WHERE job_id=%s', (self.jid,)).fetchone()['n'], 1)
        self.assertEqual(len(waiter.delays), 1)
        self.assertEqual(worker.store_failures, 0)
        # and the next claim finds nothing to take (the job is not `running` any more): it is not exhausted by a later claim
        self.assertFalse(await worker.run_once())
        self.assertEqual(self.row()['state'], 'succeeded')

    async def test_a_cut_during_fail_job_in_the_last_attempt_still_records_the_provider_code(self):
        """(b) The same for the failure: a retryable provider error in the last attempt keeps its `provider_*` code, not `attempts_exhausted`."""
        self.at_attempt(3)
        waiter = Recorder(lambda n, seconds: self.proxy.restore())

        async def extract(source):
            self.proxy.cut()
            raise ProviderError('provider_unavailable', retryable=True)
        worker = self.worker(extract, waiter=waiter)
        self.assertTrue(await worker.run_once())
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('failed', 3, 'provider_unavailable'))  # no retry left, the code survives
        self.assertEqual(len(waiter.delays), 1)

    async def test_a_cut_during_fail_job_before_the_last_attempt_records_the_failure_and_schedules_the_retry(self):
        waiter = Recorder(lambda n, seconds: self.proxy.restore())

        async def extract(source):
            self.proxy.cut()
            raise ProviderError('provider_unavailable', retryable=True)
        worker = self.worker(extract, waiter=waiter)
        self.assertTrue(await worker.run_once())
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('pending', 1, 'provider_unavailable'))  # a retry, as when the database answers

    async def test_when_the_database_does_not_return_before_the_lease_ends_the_worker_gives_up_and_a_later_claim_costs_one_attempt(self):
        """(c) The database stays cut for longer than the lease: the worker abandons without hanging and says so; the job is claimed again, one attempt per claim."""
        now = [5000.0]
        waiter = Recorder(lambda n, seconds: now.__setitem__(0, now[0]+100.0))  # three waits and the 240 s lease is over; the proxy stays cut

        async def extract(source):
            self.proxy.cut()
            return self.receipt
        worker = self.worker(extract, waiter=waiter, clock=lambda: now[0])
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        self.assertTrue(await asyncio.wait_for(worker.run_once(), 60))
        self.assertIn('"event":"job_write_abandoned"', stream.getvalue())
        self.assertIn('"reason":"complete:lease_expired"', stream.getvalue())
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('running', 1, None))  # the claim is the only attempt it cost
        self.proxy.restore()
        expire_lease(self.direct, self.jid)

        async def again(source):
            return self.receipt
        retry = self.worker(again, waiter=Recorder())
        self.assertTrue(await retry.run_once())
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('succeeded', 2, None))  # the second attempt is the second claim, nothing else

    async def test_a_stop_while_the_database_is_cut_gives_the_job_up_at_once(self):
        """(d) The stop interrupts the wait to write again (no hour-long sleep, no hang)."""
        async def extract(source):
            self.proxy.cut()
            worker.stopping.set()
            return self.receipt
        with patch('memory_platform.worker.BACKOFF_FIRST', 3600.0):
            worker = Worker(self.store, settings(worker_db_backoff_max=3600), {'extract': Mock(extract=extract)}, rng=lambda: 1.0)
            self.assertTrue(await asyncio.wait_for(worker.run_once(), 30))
        self.assertEqual({k: self.row()[k] for k in ('state', 'attempts')}, {'state': 'running', 'attempts': 1})

    async def test_a_provider_failure_then_a_cut_while_completing_then_success_charges_one_attempt_per_claim(self):
        """A provider failure in the first claim, a cut in the second (written in place), success: `attempts` is 2, one per claim."""
        outcomes = iter(['provider', 'database'])

        async def extract(source):
            if next(outcomes) == 'provider':
                raise ProviderError('provider_unavailable', retryable=True)
            self.proxy.cut()
            return self.receipt
        worker = self.worker(extract, waiter=Recorder(lambda n, seconds: self.proxy.restore()))
        await worker.run_once()
        self.assertEqual((self.row()['state'], self.row()['attempts']), ('pending', 1))
        with self.direct.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at=clock_timestamp() WHERE id=%s", (self.jid,))
        await worker.run_once()  # the database goes away while completing and is back before the lease ends
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code']), ('succeeded', 2, None))


if __name__ == '__main__':
    unittest.main()
