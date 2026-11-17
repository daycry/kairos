"""C-04 / CA-21, R-01: the heartbeat file of the worker. The loop writes it once per turn, and the lease heartbeat of a running job writes it too, only while
the last access to the database worked; `memory-worker` is `unhealthy` when the file gets old. Time is driven by the test (injected clock and waiter), never waited for."""
import asyncio
import itertools
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import psycopg
import yaml

from memory_platform.config import Settings
from memory_platform.worker import HEARTBEAT_FILE, STORE_OK_MAX_AGE, Worker

ROOT = Path(__file__).resolve().parents[3]
DOWN = psycopg.OperationalError('connection to server at "10.20.30.40", port 5432 failed: Connection refused')


def settings(**changes):
    return Settings('unused', **{'lease_seconds': 240, 'max_attempts': 3, 'worker_db_backoff_max': 60.0, **changes})


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'heartbeat'
        self.clock = Clock()
        self.store = Mock()
        self.store.claim_job.return_value = None

    def worker(self, waiter, heartbeat_file='default', **changes):
        path = self.path if heartbeat_file == 'default' else heartbeat_file
        return Worker(self.store, settings(**changes), {'extract': Mock()}, clock=self.clock, rng=lambda: 1.0, waiter=waiter, heartbeat_file=path)

    def stamp(self):
        return float(self.path.read_text(encoding='utf-8')) if self.path.exists() else None

    async def run_turns(self, turns, step, claims=None):
        """Run the loop for `turns` turns; each wait records the heartbeat file, moves the clock `step` seconds and, after the last turn, stops the worker.
        `claims`: what `claim_job` answers in turn (an exception is raised; after the list, nothing)."""
        seen, holder, count = [], [], itertools.count(1)
        async def waiter(seconds):
            seen.append(self.stamp())
            self.clock.now += step
            if next(count) >= turns:
                holder[0].stopping.set()
        worker = self.worker(waiter)
        holder.append(worker)
        outcomes = iter(claims or [])
        def claim(*args):
            outcome = next(outcomes, None)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        self.store.claim_job.side_effect = claim
        await asyncio.wait_for(worker.run(), 5)
        return seen

    async def test_the_heartbeat_advances_in_every_healthy_turn(self):
        seen = await self.run_turns(4, 7)
        self.assertEqual(seen, [1000.0, 1007.0, 1014.0, 1021.0])

    async def test_it_stops_advancing_when_the_database_has_been_down_longer_than_the_threshold(self):
        self.assertEqual(STORE_OK_MAX_AGE, 120.0)
        seen = await self.run_turns(6, 100, [DOWN]*6)
        # the database never answers: the construction of the worker was its last good access (clock 1000). Turn 1 (age 0) and 2 (age 100) beat; from age 200 on, no.
        self.assertEqual(seen, [1000.0, 1100.0, 1100.0, 1100.0, 1100.0, 1100.0])

    async def test_it_advances_again_when_the_database_answers_again(self):
        seen = await self.run_turns(7, 100, [DOWN, DOWN, DOWN, DOWN, None, None, None])
        self.assertEqual(seen[:4], [1000.0, 1100.0, 1100.0, 1100.0])
        self.assertEqual(seen[5:], [1500.0, 1600.0], 'the claim of turn 5 worked: the heartbeat comes back in the next turns')

    async def test_the_threshold_follows_the_lease_when_the_lease_is_long(self):
        """The renewal of a running job is the access that proves the database lives: it comes every lease/3, so the threshold cannot be below that."""
        worker = self.worker(AsyncMock(), lease_seconds=900)
        self.clock.now += 300
        self.assertTrue(worker.beat(), 'the database answered 300 s ago and the lease renews every 300 s')
        self.clock.now += 100
        self.assertFalse(worker.beat())

    async def test_a_heartbeat_file_that_cannot_be_written_does_not_stop_the_worker(self):
        seen, holder = [], []
        async def waiter(seconds):
            seen.append(seconds)
            if len(seen) >= 3:
                holder[0].stopping.set()
        worker = self.worker(waiter, heartbeat_file=Path(self.directory.name) / 'missing' / 'heartbeat')
        holder.append(worker)
        await asyncio.wait_for(worker.run(), 5)
        self.assertEqual(len(seen), 3)

    async def test_without_a_file_the_worker_writes_nothing(self):
        holder = []
        async def waiter(seconds):
            holder[0].stopping.set()
        worker = self.worker(waiter, heartbeat_file=None)
        holder.append(worker)
        await asyncio.wait_for(worker.run(), 5)
        self.assertFalse(self.path.exists())
        self.assertFalse(worker.beat())

    async def test_a_job_that_takes_long_keeps_the_heartbeat_alive_through_the_renewal_of_its_lease(self):
        job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store.claim_job.return_value = job
        self.store.renew_lease.return_value = True
        stamps = []
        async def tick(seconds):
            self.clock.now += 80
            await asyncio.sleep(0)
        async def slow(source):
            while len(stamps) < 3:  # the job ends only after the renewals of its lease have beaten three times
                await asyncio.sleep(0.01)
            return {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        worker = Worker(self.store, settings(), {'extract': Mock(extract=slow)}, clock=self.clock, rng=lambda: 1.0, waiter=AsyncMock(), heartbeat_wait=tick, heartbeat_file=self.path)
        beat = worker.beat
        def spy():
            written = beat()
            stamps.append(self.stamp())
            return written
        worker.beat = spy
        await asyncio.wait_for(worker.run_once(), 5)
        self.assertEqual(len(set(stamps)), len(stamps), 'every renewal moved the heartbeat on')
        self.assertEqual(stamps, sorted(stamps))


class ComposeHealthcheckTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
        self.service = self.compose['services']['memory-worker']

    def test_the_file_is_on_the_tmpfs_of_a_read_only_service(self):
        self.assertEqual(HEARTBEAT_FILE, '/tmp/kairos-worker-heartbeat')
        self.assertTrue(self.service['read_only'])
        self.assertIn('/tmp', self.service['tmpfs'])

    def test_the_healthcheck_reads_the_age_of_the_file(self):
        check = self.service['healthcheck']
        command = ' '.join(check['test'])
        self.assertIn(HEARTBEAT_FILE, command)
        self.assertIn('st_mtime', command)
        limit = float(re.search(r'<\s*(\d+)', command).group(1))
        self.assertGreater(limit, 60, 'more than the longest wait of the loop between two beats')
        self.assertIn('start_period', check)
        self.assertEqual(check['retries'], 3)
        self.assertEqual(check['interval'], '30s')

    def test_the_documentation_gives_the_time_to_unhealthy(self):
        text = (ROOT / 'docs/operations.md').read_text(encoding='utf-8')
        self.assertIn(HEARTBEAT_FILE, text)
        self.assertIn('interval × retries', text)
