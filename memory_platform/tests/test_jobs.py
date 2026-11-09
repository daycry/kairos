import unittest
from concurrent.futures import ThreadPoolExecutor

from memory_platform.tests.test_store import create_core, event, extraction_receipt


class JobTests(unittest.TestCase):
    def test_skip_locked_and_expired_lease_recovery(self):
        store,actor,pid=create_core()
        accepted=store.ingest_event(actor,event(pid))
        jid=accepted['jobs'][0]
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at='2000-01-01T00:00:00Z' WHERE id=%s",(jid,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims=list(pool.map(lambda w:store.claim_job(w),['worker-a','worker-b']))
        ours=[j for j in claims if j and j['id']==jid]
        self.assertEqual(len(ours),1)
        first=ours[0]
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET lease_until=clock_timestamp()-interval '1 second',available_at='1999-01-01T00:00:00Z' WHERE id=%s",(jid,))
        recovered=store.claim_job('replacement-worker')
        self.assertEqual(recovered['id'],jid)
        self.assertGreater(recovered['fence'],first['fence'])
        self.assertTrue(recovered['needs_reconciliation'])
        self.assertFalse(store.complete_job(jid,first['fence'],{'verified':True}))
        self.assertTrue(store.complete_job(jid,recovered['fence'],extraction_receipt()))
        self.assertEqual(store.retry_job(actor,jid)['state'],'succeeded')

    def test_unknown_is_reconciled_and_errors_redacted(self):
        store,actor,pid=create_core()
        accepted=store.ingest_event(actor,event(pid))
        jid=accepted['jobs'][0]
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at='1900-01-01T00:00:00Z' WHERE id=%s",(jid,))
        job=store.claim_job('uncertain-worker')
        self.assertEqual(job['id'],jid)
        self.assertTrue(store.fail_job(jid,job['fence'],'http://secret.invalid/?token=private',unknown=True))
        self.assertEqual(store.retry_job(actor,jid)['state'],'unknown')
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at='1900-01-01T00:00:00Z' WHERE id=%s",(jid,))
        recovered=store.claim_job('reconciler')
        self.assertEqual(recovered['id'],jid)
        self.assertTrue(recovered['needs_reconciliation'])
        with store.transaction() as c:
            row=c.execute('SELECT error_code FROM memory.jobs WHERE id=%s',(jid,)).fetchone()
        self.assertEqual(row['error_code'],'provider_error')
