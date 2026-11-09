import hashlib
import unittest
import uuid

from memory_platform.auth import Auth
from memory_platform.errors import Conflict, MemoryError, NotFound
from memory_platform.tests.test_store import create_core, event


class VersionTests(unittest.TestCase):
    def _document(self,title,content,**fields):
        return dict(document_id=str(uuid.uuid4()),version=1,title=title,content=content,source={'uri':'fixture://canonical','sha256':hashlib.sha256(content.encode()).hexdigest()},validation={'status':'validated','validated_by':'claimed-user','evidence':['fixture://review']},**fields)

    def test_document_source_hash_requires_verbatim_utf8_without_partial_writes(self):
        store,actor,pid=create_core()
        content='\ufeff# Café 東京\r\nContenido aprobado\r\n'
        document=self._document('Unicode source',content)
        invalid=dict(document,source=dict(document['source'],sha256='a'*64))
        before=store.stats(actor,pid)
        with self.assertRaises(MemoryError) as caught:
            store.publish_document(actor,pid,invalid)
        self.assertEqual(caught.exception.code,'source_hash_mismatch')
        self.assertEqual(caught.exception.status_code,422)
        self.assertEqual(store.stats(actor,pid),before)
        with store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.documents WHERE project_id=%s',(pid,)).fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.document_versions WHERE project_id=%s',(pid,)).fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.jobs WHERE project_id=%s',(pid,)).fetchone()['n'],0)
        receipt=store.publish_document(actor,pid,document)
        self.assertEqual(store.publish_document(actor,pid,document),receipt)
        stored=store.get_document(actor,pid,document['document_id'])
        self.assertEqual(stored['content'],content)
        self.assertEqual(stored['source']['sha256'],hashlib.sha256(content.encode('utf-8')).hexdigest())
        normalized=content.lstrip('\ufeff').replace('\r\n','\n')
        altered=dict(document,document_id=str(uuid.uuid4()),source=dict(document['source'],sha256=hashlib.sha256(normalized.encode('utf-8')).hexdigest()))
        with self.assertRaises(MemoryError) as caught:
            store.publish_document(actor,pid,altered)
        self.assertEqual(caught.exception.code,'source_hash_mismatch')
        self.assertEqual(store.stats(actor,pid)['documents'],1)

    def test_canonical_document_search_before_index_and_after_versioned_receipt(self):
        store,actor,pid=create_core()
        store.embedding_enabled=True
        document=self._document('Fencing recipe','Use a monotone lease token',category='operations',tags=['postgres'])
        receipt=store.publish_document(actor,pid,document)
        pending=store.search_documents(actor,[pid],'fencing')
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['index_status'],'pending')
        self.assertEqual(pending[0]['validation_status'],'validated')
        self.assertEqual(pending[0]['source'],document['source'])
        self.assertEqual(pending[0]['ref'],f"documental:{pid}:{document['document_id']}:1")
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=1,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(receipt['jobs'][0],))
        self.assertTrue(store.complete_job(receipt['jobs'][0],1,{'verified':True,'vector':[1.0,0.0],'model':'nomic-embed-text'}))
        self.assertEqual(store.search_documents(actor,[pid],'fencing')[0]['index_status'],'ready')
        updated=dict(document,version=2,title='Revised recipe',content='Use a newer canonical recipe')
        updated['source']=dict(document['source'],sha256=hashlib.sha256(updated['content'].encode('utf-8')).hexdigest())
        store.publish_document(actor,pid,updated)
        self.assertEqual(store.search_documents(actor,[pid],'fencing'),[])
        current=store.search_documents(actor,[pid],'canonical')[0]
        self.assertEqual(current['version'],2)
        self.assertEqual(current['index_status'],'pending')
        store.delete_document(actor,pid,document['document_id'],3)
        self.assertEqual(store.search_documents(actor,[pid],''),[])

    def test_document_search_weighted_filters_acl_and_readonly_no_side_effects(self):
        store,admin,pid=create_core()
        first=self._document('Fencing guide','A lease protocol',category='operations',tags=['postgres'])
        second=self._document('General guide','Fencing appears only in this body',category='notes',tags=['python'])
        store.publish_document(admin,pid,first)
        store.publish_document(admin,pid,second)
        token=store.create_key(admin,{'name':'read-only','project_ids':[pid],'scopes':['read']})['token']
        reader=Auth(store).authenticate_bearer(token)
        before=store.stats(reader,pid)
        hits=store.search_documents(reader,[pid],'fencing',categories=[],tags=[])
        self.assertEqual([h['document_id'] for h in hits],[first['document_id'],second['document_id']])
        self.assertEqual(store.search_documents(reader,[pid],'',categories=['operations'])[0]['document_id'],first['document_id'])
        self.assertEqual(store.search_documents(reader,[pid],'',tags=['python'])[0]['document_id'],second['document_id'])
        self.assertEqual(store.search_documents(reader,[pid],'postgres')[0]['document_id'],first['document_id'])
        self.assertEqual(store.search_documents(reader,[pid],'',categories=['unknown']),[])
        with self.assertRaises(NotFound):
            store.search_documents(reader,[pid,'foreign-project'],'')
        self.assertEqual(store.stats(reader,pid),before)

    def test_document_versioned_canon_and_immediate_tombstone(self):
        store,actor,pid=create_core()
        store.embedding_enabled=True
        document={'document_id':str(uuid.uuid4()),'version':1,'title':'Explicit approved synthetic source','content':'Synthetic content','source':{'uri':'fixture://approved','sha256':hashlib.sha256(b'Synthetic content').hexdigest()},'validation':{'status':'validated','validated_by':'claimed-user','evidence':['fixture://approval']}}
        first=store.publish_document(actor,pid,document)
        self.assertEqual(store.publish_document(actor,pid,document),first)
        self.assertEqual(store.search_documents(actor,[pid],'')[0]['index_status'],'pending')
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=1,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(first['jobs'][0],))
        self.assertTrue(store.complete_job(first['jobs'][0],1,{'verified':True,'vector':[1.0,0.0],'model':'nomic-embed-text'}))
        self.assertEqual(store.search_documents(actor,[pid],'')[0]['index_status'],'ready')
        self.assertEqual(document['validation']['validated_by'],'claimed-user')
        stored=store.get_document(actor,pid,document['document_id'])
        self.assertEqual(stored['validation']['validated_by'],actor['id'])
        self.assertNotEqual(stored['validation']['validated_by'],document['validation']['validated_by'])
        with self.assertRaises(Conflict):
            store.publish_document(actor,pid,dict(document,content='conflict',source=dict(document['source'],sha256=hashlib.sha256(b'conflict').hexdigest())))
        deleted=store.delete_document(actor,pid,document['document_id'],2)
        self.assertEqual(store.search_documents(actor,[pid],''),[])
        self.assertEqual(store.delete_document(actor,pid,document['document_id'],2),deleted)
        with self.assertRaises(NotFound):
            store.get_document(actor,pid,document['document_id'])
        with self.assertRaises(Conflict):
            store.publish_document(actor,pid,dict(document,version=3))

    def test_future_version_rejected_without_partial_jobs(self):
        store,actor,pid=create_core()
        value=event(pid,version=3)
        with self.assertRaises(Conflict):
            store.ingest_event(actor,value)
        with store.transaction() as c:
            self.assertIsNone(c.execute('SELECT id FROM memory.events WHERE id=%s',(value['event_id'],)).fetchone())
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.jobs WHERE item_id=%s',(value['item_id'],)).fetchone()['n'],0)
