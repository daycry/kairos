"""Independent review scenarios, with production embedding scheduling enabled."""
import asyncio
import hashlib
import json
import threading
import unittest
from unittest.mock import AsyncMock, Mock
from memory_platform import models as m
from memory_platform.config import Settings
from memory_platform.errors import Forbidden, MemoryError
from memory_platform.mcp import AuthenticatedMCP
from memory_platform.retrieval import Retrieval
from memory_platform.store import digest
from memory_platform.tests.test_store import create_core, event
from memory_platform.worker import Worker


class ActivityIndexRegression(unittest.TestCase):
    def test_large_project_cursor_feed_uses_project_indexes(self):
        store,actor,pid=create_core()
        with store.transaction() as c:
            c.execute("""INSERT INTO memory.events(id,project_id,canonical_hash,body,receipt,created_at)
                SELECT md5(%s||n)::uuid::text,%s,repeat('a',64),'{}','{}',
                timestamptz '2026-01-01'+n*interval '1 second' FROM generate_series(1,100000) n""",(pid,pid))
            c.execute('ANALYZE memory.events')
            reports=[]
            for name,query,args,index in [
                ('activity','SELECT id,created_at FROM memory.events WHERE project_id=%s AND (created_at,id)>(%s::timestamptz,%s) ORDER BY created_at,id LIMIT 51',(pid,'2026-01-01 12:00:00+00',''), 'memory_events_activity'),
                ('history','SELECT id,body,created_at FROM memory.events WHERE project_id=%s AND id>%s ORDER BY id LIMIT 20',(pid,'8'), 'memory_events_history')]:
                row=c.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query,args).fetchone()
                plan=row['QUERY PLAN'][0]
                self.assertIn(index,json.dumps(plan))
                reports.append({'query':name,'execution_ms':plan['Execution Time'],'index':index})
        print('KAIROS_QUERY_PLAN_RESULT '+json.dumps({'events':100000,'queries':reports,'synthetic':True}),flush=True)


def automatic(pid, mode='summary', content=None):
    value=event(pid,generate=False,agent_id='codex')
    value['payload']={'title':'read: completed','content':json.dumps(content or {'tool':'read','status':'completed'},ensure_ascii=False),
                      'category':'agent-activity','tags':['runtime:codex','capture:'+mode],
                      'source':{'uri':'agent://codex/synthetic'},'validation_status':'observed'}
    fingerprint=digest({'project':pid,'runtime':'codex','session':value['session_id'],'event':'PostToolUse','payload':value['payload']})
    value['capture']={'mode':mode,'hook_event':'PostToolUse','fingerprint':fingerprint}
    return value


class ReviewPostgresTests(unittest.TestCase):
    def test_technical_capture_has_no_provider_work_with_embeddings_enabled_and_manual_control_does(self):
        store,actor,pid=create_core(); store.embedding_enabled=True
        received=store.ingest_event(actor,automatic(pid))
        self.assertEqual(received['jobs'],[])
        # The shared test database contains jobs of other fixtures. Assert this
        # project's queue directly; the dedicated lifecycle harness instruments
        # provider calls in a fresh database without consuming other fixtures.
        with store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.jobs WHERE project_id=%s',(pid,)).fetchone()['n'],0)
        control=store.ingest_event(actor,event(pid,generate=False))
        self.assertEqual(len(control['jobs']),1)
        self.assertEqual(store.get_job(actor,control['jobs'][0])['destination'],'embed')

    def test_live_policy_ceiling_fingerprint_and_exact_retry(self):
        store,actor,pid=create_core()
        value=automatic(pid,'full',{'tool':'read','input':{'file':'fixture'},'result':'public data'})
        with self.assertRaises(Forbidden): store.ingest_event(actor,value)
        store.set_policy(actor,pid,{'capture_mode':'full','temporal_projection':False})
        receipt=store.ingest_event(actor,m.Event.model_validate(value))
        self.assertEqual(receipt['capture_hash'],value['capture']['fingerprint'])
        store.set_policy(actor,pid,{'capture_mode':'off','temporal_projection':False})
        self.assertEqual(store.ingest_event(actor,value),receipt)
        with self.assertRaises(MemoryError): store.ingest_event(actor,automatic(pid,'summary',{'tool':'read','input':'not summary metadata'}))

    def test_prefixed_secrets_never_reach_current_or_immutable_event_bodies(self):
        store,actor,pid=create_core(); secret='V7m9R2t5N8q3C6b1K4w0Z9s2D5h8J6p3'
        value=event(pid,generate=False,payload={'title':'Safe','content':json.dumps({'text':json.dumps({'DB_PASSWORD':secret})}),'tags':['nota:uno,dos']})
        receipt=store.ingest_event(actor,value); self.assertTrue(receipt['redacted'])
        self.assertNotIn(secret,json.dumps(store.get_item(actor,pid,value['item_id'])))
        with store.transaction() as c:
            for table,column in [('events','body'),('item_versions','body'),('memory_items','payload')]:
                rows=c.execute(f'SELECT {column} FROM memory.{table} WHERE project_id=%s',(pid,)).fetchall()
                self.assertNotIn(secret,json.dumps(rows))

    def test_any_context_finds_partial_terms_and_excludes_technical_noise_before_limit(self):
        store,actor,pid=create_core()
        useful=event(pid,generate=False,payload={'title':'Proyección: "Árbol" 🌳','content':'Use fencing before projection','tags':['nota:uno,dos']})
        store.ingest_event(actor,useful)
        for _ in range(8): store.ingest_event(actor,automatic(pid))
        query='necesito revisar errores de deployment projection y workers desconocidos'
        self.assertEqual(store.search_items(actor,[pid],query),[])
        retrieval=Retrieval(store,Settings('unused'))
        context=asyncio.run(retrieval.context(actor,m.Context(project_ids=[pid],q=query,semantic=False,match_mode='any',exclude_categories=['agent-activity'],limit=5)))
        self.assertEqual([row['item_id'] for row in context['items']],[useful['item_id']])
        self.assertIn('Árbol',context['context'])
        self.assertEqual(context['items'][0]['tags'],['nota:uno,dos'])
        with self.assertRaises(MemoryError): store.search_items(actor,[pid],query,match_mode='invalid')


class MiddlewareConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_authentication_does_not_block_an_independent_coroutine(self):
        entered,release=threading.Event(),threading.Event()
        class Auth:
            def authenticate_bearer(self,token):
                entered.set(); release.wait(1); return {'id':'fixture'}
        async def app(scope,receive,send): pass
        async def receive(): return {'type':'http.request','body':b''}
        async def send(message): pass
        middleware=AuthenticatedMCP(app,Auth())
        scope={'type':'http','method':'GET','path':'/mcp/','headers':[(b'authorization',b'Bearer synthetic')]}
        task=asyncio.create_task(middleware(scope,receive,send))
        try:
            await asyncio.sleep(0.05)
            self.assertTrue(entered.is_set()); self.assertFalse(task.done())
        finally:
            release.set(); await task

    async def test_worker_retains_domain_error_code_without_retrying_deterministic_failure(self):
        job={'id':'job','fence':1,'destination':'extract','attempts':1,'payload':{'content':'public source'}}
        store=Mock(claim_job=Mock(return_value=job))
        store.complete_job.side_effect=MemoryError('invalid_evidence','Untrusted detail')
        provider=Mock(extract=AsyncMock(return_value={'payload':{}}))
        await Worker(store,Settings('unused'),{'extract':provider}).run_once()
        self.assertEqual(store.fail_job.call_args.args,('job',1,'invalid_evidence'))
