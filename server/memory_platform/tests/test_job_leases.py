"""Characterisation of the lease of a job as it behaves today (I3 / CA-34): a `running` job whose lease expired is claimed again and the
claim counts an attempt. Nothing here changes production code: the poisoned-job cap (CA-12) arrives in a later phase and rewrites one test."""
import unittest

from memory_platform.tests.fault_proxy import expire_lease
from memory_platform.tests.test_store import create_core, event, extraction_receipt


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.pid = create_core(extraction=True)
        self.jid = self.store.ingest_event(self.actor, event(self.pid))['jobs'][0]
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at='1990-01-01T00:00:00Z' WHERE id=%s", (self.jid,))

    def claim(self, worker):
        """The next claim of this test's job. Other tests leave jobs in the shared database; claim until ours comes up (it is the first in line)."""
        for _ in range(50):
            job = self.store.claim_job(worker)
            if job is None or job['id'] == self.jid:
                return job
        self.fail('the claims never reached the job of this test')

    def row(self):
        with self.store.transaction() as c:
            return c.execute('SELECT state,attempts,fence,worker_id,lease_until>clock_timestamp() AS leased FROM memory.jobs WHERE id=%s', (self.jid,)).fetchone()

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

    def test_every_expiry_costs_one_more_attempt_and_nothing_stops_it_yet(self):
        """Today a job whose worker always dies is claimed for ever; CA-12 puts a cap here (`attempts_exhausted`)."""
        seen = []
        for number in range(1, 6):
            job = self.claim(f'worker-{number}')
            seen.append((job['attempts'], job['fence']))
            expire_lease(self.store, self.jid)
        self.assertEqual(seen, [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])
        self.assertEqual(self.row()['state'], 'running')  # never failed on its own

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
