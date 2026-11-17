"""C-04 / CA-21, R-01: the heartbeat file of the worker. It holds the DEADLINE (epoch seconds) by which the next beat is due. The loop writes it once per turn
(now + the longest wait of a turn + a margin) and the lease heartbeat of a running job writes it too (now + the renewal period lease/3 + a margin), both only
while the last access to the database worked and never before the first one; `memory-worker` is `unhealthy` once the deadline has passed, whatever the lease is.
Time is driven by the test (injected clock and waiter), never waited for."""
import asyncio
import itertools
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import psycopg
import yaml

from memory_platform.config import Settings
from memory_platform.worker import HEARTBEAT_FILE, HEARTBEAT_MARGIN, STORE_OK_MAX_AGE, Worker

ROOT = Path(__file__).resolve().parents[3]
TURN = 60.0 + HEARTBEAT_MARGIN  # the longest wait of a turn (`worker_db_backoff_max` of these tests) plus the margin
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

    async def test_the_file_holds_the_deadline_of_the_next_beat_and_advances_in_every_healthy_turn(self):
        seen = await self.run_turns(4, 7)
        # turn 1 beats before any access to the database: nothing is written; from turn 2 on the file says "the next beat is due at now + TURN"
        self.assertEqual(seen, [None, 1007.0+TURN, 1014.0+TURN, 1021.0+TURN])

    async def test_it_never_beats_before_the_first_access_to_the_database_that_works(self):
        """A worker that starts with the database down has no access that worked: the construction of the worker is not one."""
        self.assertIsNone(self.worker(AsyncMock()).last_store_ok)
        seen = await self.run_turns(5, 100, [DOWN]*5)
        self.assertEqual(seen, [None]*5)

    async def test_it_stops_advancing_when_the_database_has_been_down_longer_than_the_threshold(self):
        self.assertEqual(STORE_OK_MAX_AGE, 120.0)
        seen = await self.run_turns(6, 100, [None]+[DOWN]*5)
        # the claim of turn 1 worked (clock 1000), none after that. Turn 2 (age 100) beats; from age 200 on, no: the deadline stays the one of turn 2 and passes.
        last = 1100.0+TURN
        self.assertEqual(seen, [None, last, last, last, last, last])
        self.assertLessEqual(last, 1000.0+STORE_OK_MAX_AGE+TURN, 'the last deadline is at most the last good access + the age limit + one turn')

    async def test_it_advances_again_when_the_database_answers_again(self):
        seen = await self.run_turns(7, 100, [None, DOWN, DOWN, DOWN, None, None, None])
        self.assertEqual(seen[:4], [None, 1100.0+TURN, 1100.0+TURN, 1100.0+TURN])
        self.assertEqual(seen[5:], [1500.0+TURN, 1600.0+TURN], 'the claim of turn 5 worked: the heartbeat comes back in the next turns')

    async def test_a_long_lease_keeps_the_worker_healthy_during_a_long_job_and_the_deadline_lapses_without_the_database(self):
        """The renewal comes every lease/3 (300 s here): its deadline is that period plus the margin, so a probe never sees it lapse while renewals work."""
        job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store.claim_job.return_value = job
        self.store.renew_lease.return_value = True
        beats = []
        async def tick(seconds):
            self.clock.now += 300  # lease/3
            await asyncio.sleep(0)
        async def slow(source):
            while len(beats) < 4:  # the job ends only after the renewals of its lease have beaten four times
                await asyncio.sleep(0.01)
            return {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        worker = Worker(self.store, settings(lease_seconds=900), {'extract': Mock(extract=slow)}, clock=self.clock, rng=lambda: 1.0, waiter=AsyncMock(),
                        heartbeat_wait=tick, heartbeat_file=self.path)
        beat = worker.beat
        def spy(*args, **kwargs):
            written = beat(*args, **kwargs)
            beats.append((self.clock.now, self.stamp()))
            return written
        worker.beat = spy
        await asyncio.wait_for(worker.run_once(), 5)
        self.assertGreaterEqual(len(beats), 4)
        for (at, deadline), (next_at, _) in zip(beats, beats[1:]):
            self.assertEqual(deadline, at+300+HEARTBEAT_MARGIN)
            self.assertLess(next_at, deadline, 'the next renewal arrives before the deadline of this one: a probe never finds it passed')
        # the database goes away after the last renewal: no beat can be written any more, so the deadline lapses at most renewal period + margin after it
        last_at, last_deadline = beats[-1]
        self.clock.now = worker.last_store_ok+STORE_OK_MAX_AGE+1
        self.assertFalse(worker.beat())
        self.assertEqual(self.stamp(), last_deadline)
        self.assertLessEqual(last_deadline-last_at, 900/3+HEARTBEAT_MARGIN)

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


class ComposeHealthcheckTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
        self.service = self.compose['services']['memory-worker']
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'heartbeat'

    def probe(self):
        """Run the python of the Compose healthcheck (exec form, no shell) against a temp file in place of the container's path; its exit code is the verdict."""
        test = self.service['healthcheck']['test']
        self.assertEqual(test[:3], ['CMD', 'python', '-c'], 'exec form: no shell interpolation')
        code = test[3]
        self.assertIn(HEARTBEAT_FILE, code)
        return subprocess.run([sys.executable, '-I', '-c', code.replace(HEARTBEAT_FILE, str(self.path).replace(chr(92), '/'))], capture_output=True, timeout=30).returncode

    def test_the_file_is_on_the_tmpfs_of_a_read_only_service(self):
        self.assertEqual(HEARTBEAT_FILE, '/tmp/kairos-worker-heartbeat')
        self.assertTrue(self.service['read_only'])
        self.assertIn('/tmp', self.service['tmpfs'])

    def test_the_healthcheck_compares_the_deadline_of_the_file_with_the_clock_and_not_its_age(self):
        check = self.service['healthcheck']
        self.assertNotIn('st_mtime', ' '.join(check['test']))
        self.assertIn('start_period', check)
        self.assertEqual(check['retries'], 3)
        self.assertEqual(check['interval'], '30s')

    def test_the_probe_is_healthy_before_the_deadline_and_unhealthy_after_it_or_without_a_readable_one(self):
        self.assertEqual(self.probe(), 1, 'no file: unhealthy')
        self.path.write_text(f'{time.time()+600:.3f}\n', encoding='utf-8')
        self.assertEqual(self.probe(), 0, 'deadline in the future, however old the file is')
        self.path.write_text(f'{time.time()-1:.3f}\n', encoding='utf-8')
        self.assertEqual(self.probe(), 1, 'deadline passed')
        self.path.write_text('not a number\n', encoding='utf-8')
        self.assertEqual(self.probe(), 1)
        self.path.write_text('', encoding='utf-8')
        self.assertEqual(self.probe(), 1)

    def test_what_the_worker_writes_is_what_the_probe_reads(self):
        worker = Worker(Mock(), settings(lease_seconds=900), {'extract': Mock()}, heartbeat_file=self.path)  # real clocks
        self.assertFalse(worker.beat(), 'no access to the database yet: no file')
        self.assertEqual(self.probe(), 1)
        worker.last_store_ok = worker.clock()
        self.assertTrue(worker.beat(300))
        self.assertEqual(self.probe(), 0)
        self.assertAlmostEqual(float(self.path.read_text(encoding='utf-8'))-time.time(), 300+HEARTBEAT_MARGIN, delta=5)

    def test_the_documentation_gives_the_time_to_unhealthy_from_the_deadline(self):
        text = (ROOT / 'docs/operations.md').read_text(encoding='utf-8')
        self.assertIn(HEARTBEAT_FILE, text)
        self.assertIn('plazo del último latido', text)
        self.assertIn('interval × retries', text)
        self.assertNotIn('270 s', text)
