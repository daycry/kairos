import json
import hashlib
import unittest
import uuid

from memory_platform.auth import Auth
from memory_platform.errors import MemoryError,NotFound
from memory_platform.privacy import has_sensitive,sanitize_payload,strip_private
from memory_platform.tests.test_store import create_core,event,extraction_receipt


class PrivacyUnitTests(unittest.TestCase):
    def test_prefixed_assignments_nested_serialization_and_provider_formats(self):
        secret='V7m9R2t5N8q3C6b1K4w0Z9s2D5h8J6p3'
        texts=['DB_PASSWORD='+secret,'export AWS_SECRET_ACCESS_KEY="'+secret+'"','https://host/?GITHUB_TOKEN='+secret,
               json.dumps({'DB_PASSWORD':secret}),json.dumps({'text':json.dumps({'dbPassword':secret})}),
               'prefix '+json.dumps({'text':json.dumps({'GITHUB_TOKEN':secret})})+' suffix',
               'ghp_'+secret,'xoxb-'+secret,'AIza'+secret,
               '{"APP_\\u0054OKEN":"'+secret+'"}','prefix {"APP_\\u0054OKEN":"'+secret+'"} suffix',
               'APP_PASSWORD=alpha,beta;gamma','PGPASSWORD='+secret,'MYSQL_PWD='+secret,
               *[scheme+'://user:'+secret+'@example.invalid/path' for scheme in ['https','mongodb','mongodb+srv','amqp']],
               json.dumps({'PGPASSWORD':secret,'result':[{'MYSQL_PWD':secret}]}),'https://:'+secret+'@example.invalid/path']
        for text in texts:
            with self.subTest(representation=text[:20]):
                clean,changed=sanitize_payload({'content':text})
                self.assertTrue(changed)
                self.assertNotIn(secret,clean['content'])
                if 'alpha,beta' in text:
                    self.assertNotIn('beta',clean['content']); self.assertNotIn('gamma',clean['content'])
                self.assertFalse(has_sensitive(clean))
                self.assertEqual(sanitize_payload(clean),(clean,False))
        self.assertTrue(has_sensitive({'result':[{'DB_PASSWORD':secret,'dbPassword':secret}]}))
        self.assertFalse(has_sensitive({'content':'https://example.invalid/path user@example.invalid'}))
        self.assertFalse(has_sensitive({'DB_PASSWORD':'REDACTED','GITHUB_TOKEN':'${TOKEN}'}))
        with self.assertRaises(MemoryError):
            sanitize_payload({'content':'safe','source':{'label':'DB_PASSWORD='+secret}})

    def test_private_blocks_are_literal_nested_and_balanced(self):
        self.assertEqual(strip_private('public <PrIvAtE>hidden <private>nested</private></PRIVATE> visible'),('public [PRIVADO] visible',True))
        self.assertEqual(strip_private('<b>Plain HTML</b>'),('<b>Plain HTML</b>',False))
        for text in ('before <private>never save','stray </private>','<private data-x>hidden</private>','<private'):
            with self.subTest(text=text),self.assertRaises(MemoryError):
                strip_private(text)

    def test_recognized_credentials_are_redacted_without_rewriting_placeholders(self):
        samples=['sk-proj-'+'Z'*48,'AKIA'+'Z'*16,'Bearer '+'Z'*42,'Bearer eyJ'+'z'*12+'.'+'q'*16+'.'+'r'*16,'-----BEGIN PRIVATE KEY-----\naGVsbG8=\n-----END PRIVATE KEY-----','password="longSyntheticCredential123"']
        for text in samples:
            with self.subTest(kind=text[:12]):
                payload,changed=sanitize_payload({'title':'Fixture','content':text})
                self.assertTrue(changed)
                self.assertNotIn(text,payload['content'])
                self.assertFalse(has_sensitive(payload))
        for text in ('password="REDACTED"','secret="example-placeholder-value"','nonsecret="ordinary descriptive prose"','<p>My ordinary documentation</p>'):
            self.assertEqual(sanitize_payload({'content':text}),({'content':text},False))

    def test_redaction_is_pure_idempotent_and_drops_removed_fact_quotes(self):
        value={'content':'before <private>hidden</private> after','evidence':['Bearer '+'Q'*48],'facts':[{'subject':'a','predicate':'b','object':'c','evidence_quote':'<private>hidden</private>'}]}
        original=json.dumps(value)
        sanitized,changed=sanitize_payload(value)
        self.assertTrue(changed)
        self.assertEqual(json.dumps(value),original)
        self.assertEqual(sanitized['facts'],[])
        self.assertEqual(sanitize_payload(sanitized),(sanitized,False))
        self.assertTrue(has_sensitive({'validation':{'evidence':['<private>hidden</private>']}}))

    def test_all_fact_text_fields_drop_sensitive_fact_and_source_metadata_rejects(self):
        token='sk-'+'A'*40
        for field in ('subject','predicate','object','evidence_quote'):
            fact={'subject':'service','predicate':'uses','object':'leases','evidence_quote':'Safe public evidence'}
            fact[field]=token
            sanitized,changed=sanitize_payload({'content':'Safe public evidence','facts':[fact]})
            self.assertTrue(changed)
            self.assertEqual(sanitized['facts'],[])
            self.assertNotIn(token,json.dumps(sanitized))
        for source in ({'uri':'https://fixture.invalid/?token='+token},{'uri':'fixture://safe','label':'Bearer '+'Q'*40}):
            with self.assertRaises(MemoryError) as caught:
                sanitize_payload({'content':'Safe','source':source})
            self.assertEqual(caught.exception.code,'sensitive_source_requires_review')
        ordinary={'title':'Plain','content':'<b>public</b>','source':{'uri':'fixture://safe','label':'Public source','sha256':hashlib.sha256(b'<b>public</b>').hexdigest()}}
        self.assertEqual(sanitize_payload(ordinary),(ordinary,False))


class PrivacyPostgresTests(unittest.TestCase):
    def test_sensitive_fact_fields_drop_and_sensitive_identifiers_or_source_never_persist(self):
        store,actor,pid=create_core()
        token='sk-'+'A'*40
        value=event(pid,generate=False,payload={'title':'Safe note','content':'Safe public evidence','facts':[{'subject':'service','predicate':'uses','object':token,'evidence_quote':'Safe public evidence'}]})
        receipt=store.ingest_event(actor,value)
        self.assertTrue(receipt['redacted'])
        self.assertEqual(store.get_item(actor,pid,value['item_id'])['facts'],[])
        bad_sources=[{'uri':'https://fixture.invalid/?api_key='+token},{'uri':'fixture://safe','label':'Bearer '+'Q'*40}]
        for source in bad_sources:
            with self.assertRaises(MemoryError) as caught:
                store.ingest_event(actor,event(pid,generate=False,payload={'title':'Safe','content':'Safe public evidence','source':source}))
            self.assertEqual(caught.exception.code,'sensitive_source_requires_review')
        for field in ('session_id','agent_id'):
            for sensitive in (token,'<private>synthetic-identity-secret</private>'):
                with self.assertRaises(MemoryError) as caught:
                    store.ingest_event(actor,event(pid,generate=False,**{field:sensitive}))
                self.assertEqual(caught.exception.code,'sensitive_source_requires_review')
        with store.transaction() as c:
            events=c.execute('SELECT body,receipt FROM memory.events WHERE project_id=%s',(pid,)).fetchall()
            versions=c.execute('SELECT body FROM memory.item_versions WHERE project_id=%s',(pid,)).fetchall()
            items=c.execute('SELECT payload FROM memory.memory_items WHERE project_id=%s',(pid,)).fetchall()
            receipts=c.execute('SELECT receipt FROM memory.projection_receipts WHERE project_id=%s',(pid,)).fetchall()
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['body']['session_id'],value['session_id'])
        self.assertEqual(events[0]['body']['agent_id'],value['agent_id'])
        persisted=json.dumps([events,versions,items,receipts],default=str)
        for private in (token,'Q'*40,'synthetic-identity-secret'):
            self.assertNotIn(private,persisted)

    def test_activity_resume_includes_derived_learning_once_and_is_project_scoped(self):
        store,actor,pid=create_core()
        receipt=store.ingest_event(actor,event(pid))
        initial=store.list_activity(actor,pid,limit=1)
        self.assertEqual(len(initial['items']),1)
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=9,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s",(receipt['jobs'][0],))
        extracted=extraction_receipt()
        extracted['payload']['content']+=' <private>model-generated-private</private>'
        self.assertTrue(store.complete_job(receipt['jobs'][0],9,extracted))
        generated=store.list_activity(actor,pid,initial['next_cursor'],limit=1)
        self.assertEqual(len(generated['items']),1)
        self.assertEqual(generated['items'][0]['event_type'],'learning')
        self.assertEqual(store.get_event_receipt(actor,generated['items'][0]['event_id'])['status'],'accepted')
        self.assertFalse(store.complete_job(receipt['jobs'][0],9,extraction_receipt()))
        self.assertEqual(store.list_activity(actor,pid,generated['next_cursor'])['items'],[])
        self.assertTrue(store.list_activity(actor,pid,limit=1)['has_more'])
        all_items=store.list_activity(actor,pid,limit=100)['items']
        self.assertEqual(len(all_items),2)
        with store.transaction() as c:
            persisted=c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s',(receipt['jobs'][0],)).fetchone()['receipt']
        self.assertNotIn('model-generated-private',json.dumps(persisted))
        self.assertTrue(all(set(item)=={'id','event_id','project_id','event_type','ref','created_at','cursor'} for item in all_items))
        other=pid+'-foreign'
        store.create_project(actor,{'id':other,'title':'Foreign'})
        reader=Auth(store).authenticate_bearer(store.create_key(actor,{'name':'read','project_ids':[pid],'scopes':['read']})['token'])
        with self.assertRaises(NotFound):
            store.list_activity(reader,other,generated['next_cursor'])

    def test_capture_redacts_before_canon_jobs_history_and_activity(self):
        store,actor,pid=create_core()
        private='synthetic-private-'+uuid.uuid4().hex
        key='sk-proj-'+uuid.uuid4().hex+uuid.uuid4().hex
        value=event(pid,payload={'title':'Safe title','content':f'public <private>{private}</private> token {key}','problem':'Issue','correction':'Keep privacy','evidence':['fixture://safe']})
        first=store.ingest_event(actor,value)
        self.assertTrue(first['redacted'])
        self.assertEqual(store.ingest_event(actor,value),first)
        replaced=dict(value,payload=dict(value['payload'],content=value['payload']['content'].replace(key,'sk-proj-'+'A'*64)))
        self.assertEqual(store.ingest_event(actor,replaced),first)
        with store.transaction() as c:
            data={
                'events':c.execute('SELECT body,receipt FROM memory.events WHERE project_id=%s',(pid,)).fetchall(),
                'versions':c.execute('SELECT body FROM memory.item_versions WHERE project_id=%s',(pid,)).fetchall(),
                'items':c.execute('SELECT payload FROM memory.memory_items WHERE project_id=%s',(pid,)).fetchall(),
                'audit':c.execute('SELECT * FROM memory.audit_events WHERE project_id=%s',(pid,)).fetchall(),
            }
        persisted=json.dumps(data,default=str)
        self.assertNotIn(private,persisted)
        self.assertNotIn(key,persisted)
        self.assertIn('[PRIVADO]',persisted)
        self.assertIn('[REDACTADO]',persisted)
        activity=store.list_activity(actor,pid,limit=1)
        self.assertEqual(len(activity['items']),1)
        self.assertFalse(any(key in activity['items'][0] for key in ('title','body','content','session_id','agent_id')))
        self.assertEqual(store.list_activity(actor,pid,activity['next_cursor'])['items'],[])
        other=pid+'-other'
        store.create_project(actor,{'id':other,'title':'Other'})
        with self.assertRaises(MemoryError):
            store.list_activity(actor,other,activity['next_cursor'])

    def test_validated_and_approved_sources_require_review_without_mutation(self):
        store,actor,pid=create_core()
        value=event(pid,generate=False,payload={'title':'Source','content':'<private>sensitive original</private>','validation_status':'validated','evidence':['fixture://review']})
        with self.assertRaises(MemoryError) as caught:
            store.ingest_event(actor,value)
        self.assertEqual(caught.exception.code,'sensitive_source_requires_review')
        content='password="sensitiveCredential123"'
        document={'document_id':str(uuid.uuid4()),'version':1,'title':'Approved source','content':content,'source':{'uri':'fixture://approved','sha256':hashlib.sha256(content.encode('utf-8')).hexdigest()},'validation':{'status':'validated','validated_by':'claim','evidence':['fixture://review']}}
        original=json.dumps(document)
        with self.assertRaises(MemoryError) as caught:
            store.publish_document(actor,pid,document)
        self.assertEqual(caught.exception.code,'sensitive_source_requires_review')
        self.assertEqual(json.dumps(document),original)
        with store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.events WHERE project_id=%s',(pid,)).fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.documents WHERE project_id=%s',(pid,)).fetchone()['n'],0)
