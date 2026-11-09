"""Native semantic indexing: real Postgres arrays, current versions and project ACL."""
import math
import hashlib
import unittest
import uuid
import tracemalloc

from memory_platform.auth import Auth
from memory_platform.errors import MemoryError,NotFound
from memory_platform.store import Store
from memory_platform.tests.test_store import create_core,event,extraction_receipt

MODEL='nomic-embed-text'


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        base,self.actor,self.pid=create_core()
        self.store=Store(base.dsn,embedding_enabled=True)

    def _job(self,receipt,destination='embed'):
        with self.store.transaction() as c:
            job=c.execute('SELECT * FROM memory.jobs WHERE id=ANY(%s) AND destination=%s',(receipt['jobs'],destination)).fetchone()
            c.execute("UPDATE memory.jobs SET state='running',fence=5,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(job['id'],))
        return job

    def _complete(self,job,vector=None):
        return self.store.complete_job(job['id'],5,{'vector':vector or [1.0,0.0],'model':MODEL,'canonical_hash':job['canonical_hash'],'verified':True})

    def test_semantic_scan_streams_vectors_and_fetches_only_winning_payloads(self):
        # Deliberately larger than the cursor batch: old fetchall retained all
        # 1,500 payloads plus 768-dimensional Python vectors at once.
        with self.store.transaction() as c:
            c.execute("""INSERT INTO memory.documents(project_id,id,version,canonical_hash,body)
                SELECT %s,'stream-'||n,1,repeat('a',64),jsonb_build_object(
                    'title','Stream '||n,'content',repeat('x',10000),'tags',jsonb_build_array('área:uno,dos'))
                FROM generate_series(1,1500) n""",(self.pid,))
            c.execute("""INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector)
                SELECT project_id,id,'document',version,canonical_hash,%s,array_fill(1.0::float8,ARRAY[768])
                FROM memory.documents WHERE project_id=%s""",(MODEL,self.pid))
        tracemalloc.start()
        try:
            found=self.store.search_vectors(self.actor,[self.pid],[1.0]*768,MODEL,limit=5)
            _,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(found),5)
        self.assertEqual(found[0]['item_id'],'stream-1')
        self.assertEqual(found[0]['tags'],['área:uno,dos'])
        self.assertLess(peak,20*1024*1024)
        print(f'SEMANTIC_MEMORY_RESULT candidates=1500 dimensions=768 payload_chars=10000 peak_bytes={peak}',flush=True)

    def test_document_native_indexing_readiness_and_receipt_redaction(self):
        content='Synthetic vector indexed knowledge'
        document={'document_id':str(uuid.uuid4()),'version':1,'title':'Semantic fixture','content':content,'category':'operations','tags':['postgres'],'source':{'uri':'fixture://semantic','sha256':hashlib.sha256(content.encode('utf-8')).hexdigest()},'validation':{'status':'validated','validated_by':'claim','evidence':['fixture://review']}}
        receipt=self.store.publish_document(self.actor,self.pid,document)
        self.assertEqual(len(receipt['jobs']),1)
        self.assertEqual(self.store.search_documents(self.actor,[self.pid],'semantic')[0]['index_status'],'pending')
        job=self._job(receipt)
        self.assertFalse(self.store.has_vectors(self.actor,[self.pid],MODEL))
        self.assertTrue(self._complete(job))
        hit=self.store.search_vectors(self.actor,[self.pid],[1,0],MODEL,categories=['operations'],tags=['postgres'])[0]
        self.assertEqual(hit['ref'],f"documental:{self.pid}:{document['document_id']}:1")
        self.assertAlmostEqual(hit['score'],1.0)
        self.assertEqual(hit['candidate_limit'],10000)
        self.assertFalse(hit['candidates_truncated'])
        self.assertTrue(self.store.has_vectors(self.actor,[self.pid],MODEL))
        self.assertEqual(self.store.search_documents(self.actor,[self.pid],'semantic')[0]['index_status'],'ready')
        with self.store.transaction() as c:
            stored=c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s',(job['id'],)).fetchone()['receipt']
        self.assertEqual(set(stored),{'model','dimensions','hash','status','verified'})
        self.assertNotIn('vector',stored)
        self.store.delete_document(self.actor,self.pid,document['document_id'],2)
        self.assertFalse(self.store.has_vectors(self.actor,[self.pid],MODEL))
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[1,0],MODEL),[])

    def test_invalid_vectors_are_atomic_and_completion_is_fenced_idempotent(self):
        accepted=self.store.ingest_event(self.actor,event(self.pid,generate=False))
        job=self._job(accepted)
        for vector in ([math.nan,0],[math.inf,0],[-math.inf,0],[0,0],[],[1]*4097,[True,0]):
            with self.subTest(vector_type=str(vector[:2])):
                with self.assertRaises(MemoryError):
                    self.store.complete_job(job['id'],5,{'model':MODEL,'vector':vector})
        with self.store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.embeddings WHERE project_id=%s',(self.pid,)).fetchone()['n'],0)
        self.assertFalse(self.store.complete_job(job['id'],4,{'model':MODEL,'vector':[1,0]}))
        self.assertTrue(self._complete(job))
        self.assertFalse(self._complete(job))
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[0,0],MODEL),[])
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[1,0,0],MODEL),[])
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[1,0],'other-model'),[])
        self.assertFalse(self.store.has_vectors(self.actor,[self.pid],'other-model'))

    def test_project_isolation_and_stale_versions_never_reappear(self):
        original=event(self.pid,generate=False)
        self.assertTrue(self._complete(self._job(self.store.ingest_event(self.actor,original))))
        reader=Auth(self.store).authenticate_bearer(self.store.create_key(self.actor,{'name':'reader','project_ids':[self.pid],'scopes':['read']})['token'])
        self.assertEqual(len(self.store.search_vectors(reader,[self.pid],[1,0],MODEL)),1)
        with self.assertRaises(NotFound):
            self.store.search_vectors(reader,[self.pid,'foreign-project'],[1,0],MODEL)
        with self.assertRaises(NotFound):
            self.store.has_vectors(reader,['foreign-project'],MODEL)
        update=dict(original,event_id=str(uuid.uuid4()),version=2)
        pending=self._job(self.store.ingest_event(self.actor,update))
        self.assertEqual(self.store.search_vectors(reader,[self.pid],[1,0],MODEL),[])
        deletion=dict(original,event_id=str(uuid.uuid4()),version=3,event_type='delete')
        self.store.ingest_event(self.actor,deletion)
        self.assertFalse(self._complete(pending))
        self.assertEqual(self.store.search_vectors(reader,[self.pid],[1,0],MODEL),[])

    def test_derived_learning_is_embedded_once_and_tracks_parent_lineage(self):
        original=event(self.pid,generate=True)
        accepted=self.store.ingest_event(self.actor,original)
        self.assertEqual(self.store.ingest_event(self.actor,original),accepted)
        self.assertEqual(len(accepted['jobs']),2)
        extraction=self._job(accepted,'extract')
        self.assertTrue(self.store.complete_job(extraction['id'],5,extraction_receipt()))
        derived=next(note for note in self.store.list_notes(self.actor,self.pid) if note['item_id']!=original['item_id'])
        with self.store.transaction() as c:
            jobs=c.execute("SELECT id FROM memory.jobs WHERE project_id=%s AND item_id=%s AND destination='embed'",(self.pid,derived['item_id'])).fetchall()
        self.assertEqual(len(jobs),1)
        childjob=self._job({'jobs':[job['id'] for job in jobs]})
        self.assertTrue(self._complete(childjob))
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[1,0],MODEL)[0]['item_id'],derived['item_id'])
        self.store.ingest_event(self.actor,dict(original,event_id=str(uuid.uuid4()),version=2,generate=False))
        self.assertEqual(self.store.search_vectors(self.actor,[self.pid],[1,0],MODEL),[])
        self.assertFalse(self.store.has_vectors(self.actor,[self.pid],MODEL))
