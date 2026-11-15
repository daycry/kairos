"""The lease of a job (I3 / CA-34, CA-12): a `running` job whose lease expired is claimed again and the claim counts an attempt, until the attempts
that `MEMORY_MAX_ATTEMPTS` allows are spent: then the claim that finds it fails it as `attempts_exhausted` (a poisoned job) instead of claiming it, and
`retry_job` brings it back."""
import os
import unittest
import uuid
from unittest.mock import patch

from memory_platform import observability
from memory_platform.config import Settings
from memory_platform.tests.fault_proxy import expire_lease
from memory_platform.tests.test_store import create_core, event, extraction_receipt
from memory_platform.worker import Worker


class LeaseTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        # A database of its own: the queue holds only the job of this test, so a claim can never take (and leave `running`) a job of another test,
        # and the 1990 `available_at` that `expire_lease` writes cannot move ahead of anybody else's job. Dropping it cleans everything this test made.
        self.name = 'lease_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')

        def drop():
            with psycopg.connect(dsn, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

        self.addCleanup(drop)
        with patch.dict(os.environ, {'MEMORY_TEST_DSN': make_conninfo(dsn, dbname=self.name)}):
            self.store, self.actor, self.pid = create_core(extraction=True)
        self.jid = self.store.ingest_event(self.actor, event(self.pid))['jobs'][0]
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at='1990-01-01T00:00:00Z' WHERE id=%s", (self.jid,))

    def claim(self, worker):
        """The next claim: this database holds no other job, so it is this test's job or nothing."""
        job = self.store.claim_job(worker)
        self.assertTrue(job is None or job['id'] == self.jid, job)
        return job

    def row(self):
        with self.store.transaction() as c:
            return c.execute('SELECT state,attempts,fence,worker_id,error_code,lease_until IS NULL AS no_lease,lease_until>clock_timestamp() AS leased FROM memory.jobs WHERE id=%s', (self.jid,)).fetchone()

    def test_a_running_job_with_a_live_lease_is_not_claimed_again(self):
        first = self.claim('worker-a')
        self.assertEqual((first['id'], first['attempts'], first['fence']), (self.jid, 1, 1))
        self.assertIsNone(self.claim('worker-b'))
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['worker_id'], state['leased']), ('running', 1, 'worker-a', True))

    def test_a_running_job_with_an_expired_lease_is_claimed_again_and_counts_an_attempt(self):
        first = self.claim('worker-a')
        self.assertFalse(first['needs_reconciliation'])  # the first claim has nothing to reconcile
        expire_lease(self.store, self.jid)
        recovered = self.claim('replacement')
        self.assertEqual(recovered['id'], self.jid)
        self.assertEqual((recovered['attempts'], recovered['fence'], recovered['worker_id']), (2, first['fence'] + 1, 'replacement'))
        self.assertTrue(recovered['needs_reconciliation'])  # the dead worker may have done part of it
        self.assertEqual(self.row()['state'], 'running')

    def exhaust(self, claims=3):
        """`claims` claims, each of a worker that dies: the lease expires after every one. Returns what the claims saw as (attempts, fence)."""
        seen = []
        for number in range(1, claims + 1):
            job = self.claim(f'worker-{number}')
            seen.append((job['attempts'], job['fence']))
            expire_lease(self.store, self.jid)
        return seen

    def test_every_expiry_costs_one_more_attempt_until_the_cap_and_then_the_job_fails_instead_of_being_claimed(self):
        self.assertEqual(self.exhaust(3), [(1, 1), (2, 2), (3, 3)])  # three attempts are allowed (MEMORY_MAX_ATTEMPTS defaults to 3): all three are claimed
        self.assertIsNone(self.claim('worker-4'))  # the fourth claim does not get it: it finds the job spent
        state = self.row()
        self.assertEqual((state['state'], state['attempts'], state['error_code'], state['no_lease']), ('failed', 3, 'attempts_exhausted', True))  # never claimed a fourth time
        for later in range(3):
            self.assertIsNone(self.claim(f'later-{later}'))  # and it stays out of the queue
        self.assertEqual(self.row()['attempts'], 3)

    def test_the_cap_is_the_configured_max_attempts_not_a_constant(self):
        self.store.max_attempts = 1
        self.assertEqual(self.exhaust(1), [(1, 1)])
        self.assertIsNone(self.claim('worker-2'))
        self.assertEqual((self.row()['state'], self.row()['attempts'], self.row()['error_code']), ('failed', 1, 'attempts_exhausted'))

    def test_a_larger_cap_allows_more_claims(self):
        self.store.max_attempts = 5
        self.assertEqual(self.exhaust(5), [(n, n) for n in range(1, 6)])
        self.assertIsNone(self.claim('worker-6'))
        self.assertEqual((self.row()['state'], self.row()['attempts']), ('failed', 5))

    def test_the_worker_hands_its_max_attempts_to_the_store(self):
        Worker(self.store, Settings('unused', max_attempts=2), {})
        self.assertEqual(self.store.max_attempts, 2)
        self.assertEqual(self.exhaust(2), [(1, 1), (2, 2)])
        self.assertIsNone(self.claim('worker-3'))
        self.assertEqual((self.row()['state'], self.row()['error_code']), ('failed', 'attempts_exhausted'))

    def test_the_claim_that_fails_a_poisoned_job_goes_on_and_returns_the_next_healthy_one_in_the_same_transaction(self):
        self.exhaust(3)
        healthy = self.store.ingest_event(self.actor, event(self.pid))['jobs'][0]
        job = self.store.claim_job('worker-4')
        self.assertEqual((job['id'], job['attempts']), (healthy, 1))  # the healthy job, not nothing and not the poisoned one
        self.assertEqual((self.row()['state'], self.row()['attempts'], self.row()['error_code']), ('failed', 3, 'attempts_exhausted'))
        with self.store.transaction() as c:
            states = {r['id']: r['state'] for r in c.execute('SELECT id,state FROM memory.jobs').fetchall()}
        self.assertEqual(states, {self.jid: 'failed', healthy: 'running'})  # nothing is left in between

    def test_retry_job_brings_an_exhausted_job_back_to_pending_and_it_is_processed(self):
        self.exhaust(3)
        self.assertIsNone(self.claim('worker-4'))
        self.assertEqual(self.store.retry_job(self.actor, self.jid)['state'], 'pending')
        self.assertEqual(self.row()['state'], 'pending')
        job = self.claim('rescuer')
        self.assertEqual((job['id'], job['attempts']), (self.jid, 4))  # a retried job is claimed whatever its attempts: pending is not the poisoned state
        self.assertTrue(self.store.complete_job(job['id'], job['fence'], extraction_receipt()))
        self.assertEqual((self.row()['state'], self.row()['error_code']), ('succeeded', None))

    def test_a_retried_job_whose_worker_dies_again_is_failed_again_at_its_next_expiry(self):
        self.exhaust(3)
        self.assertIsNone(self.claim('worker-4'))
        self.store.retry_job(self.actor, self.jid)
        self.assertEqual(self.claim('rescuer')['attempts'], 4)
        expire_lease(self.store, self.jid)
        self.assertIsNone(self.claim('worker-6'))
        self.assertEqual((self.row()['state'], self.row()['attempts'], self.row()['error_code']), ('failed', 4, 'attempts_exhausted'))

    def test_unknown_jobs_keep_their_reconciliation_whatever_their_attempts(self):
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='unknown',attempts=9 WHERE id=%s", (self.jid,))
        job = self.claim('reconciler')
        self.assertEqual((job['id'], job['attempts'], job['needs_reconciliation']), (self.jid, 10, True))  # reconciled by a worker, not failed by the cap
        self.assertEqual(self.row()['state'], 'running')

    def test_a_running_job_with_a_live_lease_is_not_failed_however_many_attempts_it_has(self):
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET attempts=1 WHERE id=%s", (self.jid,))
        self.store.max_attempts = 1
        job = self.claim('worker-a')  # attempts 2 > the cap, but this is the claim itself: the cap only judges an expired lease
        self.assertEqual(job['attempts'], 2)
        self.assertIsNone(self.claim('worker-b'))
        self.assertEqual((self.row()['state'], self.row()['worker_id'], self.row()['leased']), ('running', 'worker-a', True))

    def test_the_poisoned_job_is_visible_in_kairos_jobs_failed_under_its_own_code(self):
        self.exhaust(3)
        self.assertIsNone(self.claim('worker-4'))
        observability._QUEUE_CACHE.update(at=None, ok=False)
        self.addCleanup(lambda: observability._QUEUE_CACHE.update(at=None, ok=False))
        self.assertTrue(observability.refresh_queue_depth(self.store))
        labels = {'destination': 'extract', 'code': 'attempts_exhausted'}
        self.assertEqual(observability.REGISTRY.get_sample_value('kairos_jobs_failed', labels), 1)
        self.assertEqual(observability.REGISTRY.get_sample_value('kairos_jobs_failed', {'destination': 'extract', 'code': 'other'}), 0)  # not folded into `other`

    def test_the_worker_whose_lease_expired_cannot_complete_the_job_even_with_its_own_fence(self):
        stale = self.claim('worker-a')
        expire_lease(self.store, self.jid)
        self.assertFalse(self.store.renew_lease(self.jid, stale['fence']))
        self.assertFalse(self.store.complete_job(self.jid, stale['fence'], extraction_receipt()))
        self.assertEqual(self.row()['state'], 'running')  # refusing the late worker did not fail the job
        recovered = self.claim('replacement')
        self.assertFalse(self.store.complete_job(self.jid, stale['fence'], extraction_receipt()))
        self.assertTrue(self.store.complete_job(self.jid, recovered['fence'], extraction_receipt()))
        self.assertEqual(self.row()['state'], 'succeeded')

    def test_expire_lease_moves_only_the_lease(self):
        job = self.claim('worker-a')
        before = self.row()
        self.assertTrue(before['leased'])
        expire_lease(self.store, self.jid)
        after = self.row()
        self.assertFalse(after['leased'])
        self.assertEqual({k: after[k] for k in ('state', 'attempts', 'fence', 'worker_id')}, {k: before[k] for k in ('state', 'attempts', 'fence', 'worker_id')})
        self.assertEqual(job['fence'], after['fence'])

    def test_expire_lease_refuses_a_job_that_is_not_running(self):
        with self.assertRaises(AssertionError):
            expire_lease(self.store, self.jid)  # still pending: nothing to expire
        with self.assertRaises(AssertionError):
            expire_lease(self.store, 'no-such-job')


if __name__ == '__main__':
    unittest.main()
