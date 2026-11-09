"""Native synthesis, temporal facts and validation-authority regressions."""
import unittest
import uuid

from memory_platform.auth import Auth
from memory_platform.errors import Forbidden, MemoryError, NotFound
from memory_platform.tests.test_store import create_core,event,extraction_receipt


class NativeMemoryTests(unittest.TestCase):
    def _running(self,store,jid):
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=7,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(jid,))

    def test_extract_materializes_and_parent_update_invalidates(self):
        store,actor,pid=create_core()
        original=event(pid)
        accepted=store.ingest_event(actor,original)
        self.assertEqual(len(accepted['jobs']),1)
        self._running(store,accepted['jobs'][0])
        receipt=extraction_receipt()
        receipt['payload']['validation_status']='validated'
        self.assertTrue(store.complete_job(accepted['jobs'][0],7,receipt))
        notes=store.list_notes(actor,pid,100)
        derived=next(n for n in notes if n['item_id']!=original['item_id'])
        self.assertEqual(derived['validation_status'],'unverified')
        self.assertEqual(derived['provenance']['parent_item_id'],original['item_id'])
        facts=store.search_native_facts(actor,[pid],'fencing')
        self.assertEqual(len(facts),1)
        self.assertEqual(facts[0]['validity'],'unknown')
        self.assertEqual(store.get_native_fact(actor,pid,derived['item_id'],1,1),facts[0])
        graph=store.graph_data(actor,{'project_ids':[pid],'q':'fencing','limit':100})
        self.assertEqual(len(graph['links']),1)
        self.assertTrue(all(n['project_id']==pid for n in graph['nodes']))
        self.assertTrue(store.timeline(actor,{'project_ids':[pid],'anchor':{'project_id':pid,'item_id':original['item_id'],'version':1}})['items'])
        update=dict(original,event_id=str(uuid.uuid4()),version=2,generate=False)
        store.ingest_event(actor,update)
        with self.assertRaises(NotFound):
            store.get_item(actor,pid,derived['item_id'])
        self.assertEqual(store.search_native_facts(actor,[pid],'fencing'),[])
        with self.assertRaises(NotFound):
            store.get_native_fact(actor,pid,derived['item_id'],1,1)
        self.assertFalse(store.complete_job(accepted['jobs'][0],7,receipt))

    def test_extraction_rejects_invented_quote_atomically(self):
        store,actor,pid=create_core()
        accepted=store.ingest_event(actor,event(pid))
        self._running(store,accepted['jobs'][0])
        receipt=extraction_receipt()
        receipt['payload']['facts'][0]['evidence_quote']='Invented source sentence'
        receipt['payload']['problem']='Invented source sentence'
        with self.assertRaises(MemoryError):
            store.complete_job(accepted['jobs'][0],7,receipt)
        self.assertEqual(len(store.list_notes(actor,pid)),1)
        self.assertEqual(store.get_job(actor,accepted['jobs'][0])['state'],'running')

    def test_write_cannot_mutate_delete_or_supersede_validated_memory(self):
        store,admin,pid=create_core()
        value=event(pid,generate=False,payload={'title':'Validated','content':'Use fencing before projection','validation_status':'validated','evidence':['fixture://review']})
        store.ingest_event(admin,value)
        token=store.create_key(admin,{'name':'writer','project_ids':[pid],'scopes':['read','write']})['token']
        writer=Auth(store).authenticate_bearer(token)
        for change in ({'version':2},{'version':2,'event_type':'delete'}):
            update=dict(value,event_id=str(uuid.uuid4()),payload={'title':'Changed','content':'Changed'},**change)
            with self.assertRaises(Forbidden):
                store.ingest_event(writer,update)
        correction=event(pid,generate=False,event_type='correction',payload={'title':'Unverified correction','content':'Alternative','supersedes':value['item_id']})
        with self.assertRaises(Forbidden):
            store.ingest_event(writer,correction)
        alternative=event(pid,generate=False,payload={'title':'Alternative note','content':'An unverified alternative'})
        store.ingest_event(writer,alternative)
        self.assertEqual(store.get_item(writer,pid,value['item_id'])['validation_status'],'validated')
        self.assertEqual(len(store.list_notes(writer,pid)),2)

    def test_native_facts_source_checks_and_capture_generate_opt_in(self):
        store,actor,pid=create_core()
        value=event(pid,generate=False)
        receipt=store.ingest_event(actor,value)
        self.assertEqual(receipt['jobs'],[])
        omitted=dict(value)
        omitted.pop('generate')
        omitted['payload']=dict(value['payload'],facts=[])
        self.assertEqual(store.ingest_event(actor,omitted),receipt)
        invalid=event(pid,generate=False,payload={'title':'Fact','content':'Actual evidence','facts':[{'subject':'a','predicate':'b','object':'c','evidence_quote':'invented'}]})
        with self.assertRaises(MemoryError):
            store.ingest_event(actor,invalid)
        self.assertEqual(store.search_native_facts(actor,[pid]),[])

    def test_validated_derived_memory_protects_parent_and_csrf_refresh(self):
        store,admin,pid=create_core()
        original=event(pid)
        accepted=store.ingest_event(admin,original)
        self._running(store,accepted['jobs'][0])
        self.assertTrue(store.complete_job(accepted['jobs'][0],7,extraction_receipt()))
        derived=next(n for n in store.list_notes(admin,pid) if n['item_id']!=original['item_id'])
        payload=dict(derived['payload'],validation_status='validated',evidence=['fixture://human-review'])
        store.ingest_event(admin,event(pid,item_id=derived['item_id'],version=2,generate=False,payload=payload))
        writer=Auth(store).authenticate_bearer(store.create_key(admin,{'name':'writer','project_ids':[pid],'scopes':['read','write']})['token'])
        with self.assertRaises(Forbidden):
            store.ingest_event(writer,dict(original,event_id=str(uuid.uuid4()),version=2,generate=False))
        self.assertEqual(store.get_item(admin,pid,original['item_id'])['version'],1)
        username='csrf-'+uuid.uuid4().hex
        store.create_user(admin,{'username':username,'password':'synthetic-password-123','project_ids':[pid],'scopes':['read']})
        auth=Auth(store,['https://memory.example'])
        login=auth.login(username,'synthetic-password-123','fixture-'+uuid.uuid4().hex)
        refreshed=auth.refresh_csrf(login['actor'])
        auth.require_csrf(login['actor'],refreshed,'https://memory.example')
        with self.assertRaises(Forbidden):
            auth.require_csrf(login['actor'],login['csrf_token'],'https://memory.example')
