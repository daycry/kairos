"""Transaction guarantees against isolated real Postgres (never a SQLite substitute)."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import unittest

from memory_platform.auth import Auth
from memory_platform.errors import Conflict, Forbidden, NotFound
from memory_platform.store import Store, digest


def create_core():
    dsn = os.getenv('MEMORY_TEST_DSN')
    if not dsn:
        raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
    try:
        import psycopg
    except ImportError:
        raise unittest.SkipTest('psycopg is required for integration tests')
    store = Store(dsn)
    store.migrate()
    # Dedicated fixtures use globally unique names and projects, never truncate shared data.
    suffix = uuid.uuid4().hex[:14]
    with store.transaction() as c:
        from memory_platform.auth import hash_password
        aid = str(uuid.uuid4())
        c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (aid,'test-'+suffix,hash_password('fixture-password-123')))
    actor = {'id':aid,'credential_type':'bootstrap'}
    pid = 'test-'+suffix
    store.create_project(actor, {'id':pid,'title':'Isolated synthetic test'})
    store.set_policy(actor,pid,{'capture_mode':'summary','temporal_projection':True})
    return store, actor, pid


def event(pid, **changes):
    result = {'event_id':str(uuid.uuid4()),'project_id':pid,'session_id':'synthetic-session','agent_id':'fixture','event_type':'note','occurred_at':'2026-11-04T10:00:00Z','item_id':str(uuid.uuid4()),'version':1,'generate':True,'payload':{'title':'Database locking','content':'Use fencing before projection','source':{'uri':'fixture://public'}}}
    result.update(changes)
    return result


def extraction_receipt():
    return {'payload':{'title':'Structured learning','content':'Use fencing before projection','validation_status':'unverified','facts':[{'subject':'projection','predicate':'requires','object':'fencing','evidence_quote':'Use fencing before projection'}]},'model':'synthetic-model','prompt_version':'fixture-v1','status':'extracted'}



class StoreTests(unittest.TestCase):
    def setUp(self):
        self.core = create_core()

    def test_concurrent_duplicate_and_conflict(self):
        store,actor,pid=self.core
        value=event(pid)
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(lambda _:store.ingest_event(actor,value),range(8)))
        assert all(r==receipts[0] for r in receipts)
        with store.transaction() as c:
            assert c.execute('SELECT count(*) AS n FROM memory.events WHERE id=%s',(value['event_id'],)).fetchone()['n']==1
            assert c.execute('SELECT count(*) AS n FROM memory.jobs WHERE item_id=%s',(value['item_id'],)).fetchone()['n']==1
            stored=c.execute('SELECT body,canonical_hash FROM memory.events WHERE id=%s',(value['event_id'],)).fetchone()
            assert digest(stored['body'])==stored['canonical_hash']
        altered=dict(value,payload={'title':'changed','content':'changed'})
        with self.assertRaises(Conflict):
            store.ingest_event(actor,altered)
        normalized=dict(value,occurred_at='2026-11-04T11:00:00+01:00')
        assert store.ingest_event(actor,normalized)==receipts[0]


    def test_version_tombstone_and_stale_completion(self):
        store,actor,pid=self.core
        value=event(pid)
        receipt=store.ingest_event(actor,value)
        # Select our job explicitly so parallel test runs cannot steal another fixture's job.
        with store.transaction() as c:
            job=c.execute("UPDATE memory.jobs SET state='running',fence=1,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s RETURNING *",(receipt['jobs'][0],)).fetchone()
        update=dict(value,event_id=str(uuid.uuid4()),version=2)
        store.ingest_event(actor,update)
        assert not store.complete_job(job['id'],1,{'verified':True})
        deletion=dict(value,event_id=str(uuid.uuid4()),version=3,event_type='delete')
        store.ingest_event(actor,deletion)
        assert store.search_items(actor,[pid],'locking')==[]
        with self.assertRaises(NotFound):
            store.get_item(actor,pid,value['item_id'])
        # Lost response retry does not resurrect a tombstoned current view.
        assert store.ingest_event(actor,value)==receipt
        with self.assertRaises(Conflict):
            store.ingest_event(actor,dict(value,event_id=str(uuid.uuid4()),version=4))


    def test_fencing_and_receipts(self):
        store,actor,pid=self.core
        receipt=store.ingest_event(actor,event(pid))
        jid=receipt['jobs'][0]
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=4,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(jid,))
        assert not store.renew_lease(jid,3)
        assert not store.complete_job(jid,3,{'verified':True})
        assert store.renew_lease(jid,4)
        assert store.complete_job(jid,4,extraction_receipt())
        assert not store.complete_job(jid,4,{'verified':True})
        self.assertEqual(store.get_job(actor, jid)['state'], 'succeeded')
        with store.transaction() as c:
            saved = c.execute('SELECT * FROM memory.projection_receipts WHERE job_id=%s', (jid,)).fetchone()
        self.assertEqual(saved['item_id'], receipt['item_id'])
        self.assertEqual(saved['destination'], 'extract')
        self.assertEqual(saved['receipt']['model'], 'synthetic-model')
        derived = store.get_item(actor, pid, saved['receipt']['derived_item_id'])
        self.assertEqual(derived['validation_status'], 'unverified')
        self.assertEqual(derived['provenance']['parent_hash'], saved['canonical_hash'])


    def test_correction_scope_and_search_priority(self):
        store,actor,pid=self.core
        old=event(pid)
        store.ingest_event(actor,old)
        correction=event(pid,event_type='correction',payload={'title':'Database locking correction','content':'Corrected locks','problem':'database','correction':'Use fencing','evidence':['fixture://evidence'],'validation_status':'validated','supersedes':old['item_id']})
        store.ingest_event(actor,correction)
        results=store.search_items(actor,[pid],'database')
        assert results[0]['item_id']==correction['item_id']
        assert all(r['item_id']!=old['item_id'] for r in results)
        other=pid+'-other'
        store.create_project(actor,{'id':other,'title':'Other'})
        store.set_policy(actor,other,{'capture_mode':'summary','temporal_projection':False})
        with self.assertRaises(Conflict):
            store.ingest_event(actor,event(other,event_type='correction',payload={'title':'Invalid','content':'Cross project','supersedes':old['item_id']}))


    def test_off_default_and_no_key_escalation(self):
        store,actor,pid=self.core
        other=pid+'-off'
        project=store.create_project(actor,{'id':other,'title':'Off','capture_mode':'full'})
        assert project['capture_mode']=='off'
        with self.assertRaises(Forbidden):
            store.ingest_event(actor,event(other))
        key=store.create_key(actor,{'name':'narrow','project_ids':[pid],'scopes':['read','admin']})
        scoped=Auth(store).authenticate_bearer(key['token'])
        with self.assertRaises(NotFound):
            store.create_user(scoped,{'username':'bad-'+uuid.uuid4().hex,'password':'long-enough-password','project_ids':[other],'scopes':['admin']})
        with self.assertRaises(Forbidden):
            store.create_project(scoped,{'id':pid+'-forbidden','title':'No'})
