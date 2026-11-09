"""Synthetic-only fixture; PostgreSQL and HTTP are real, no user service configuration."""
import threading
import time
import urllib.request
import uuid
import os
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.store import Store
from memory_platform.tests.test_store import event

BASE = 'http://127.0.0.1:8898'
PASSWORD = 'synthetic-e2e-password-123'

async def synthetic_corpus_answer(self, messages, sources, limits):
    """Deterministic fixture only; no external provider/model request is made."""
    return {'answer': 'Asterion uses the cited safeguard.',
            'citations': [{'ref': sources[0]['ref'], 'quote': sources[0]['content'][:100]}],
            'input_tokens': 200, 'output_tokens': 40}

def start(dsn):
    store = Store(dsn)
    store.migrate()
    admin = store.bootstrap_user('fixture-admin', PASSWORD)
    for pid, title in [('project-a','Proyecto Alfa'),('project-b','Privado Beta'),('capture-off','Captura apagada')]:
        store.create_project(admin, {'id':pid,'title':title})
        if pid != 'capture-off':
            store.set_policy(admin,pid,{'capture_mode':'summary','temporal_projection':True})
    store.create_user(admin,{'username':'alice','password':PASSWORD,'project_ids':['project-a','capture-off'],'scopes':['read','write']})
    store.create_user(admin,{'username':'reader','password':PASSWORD,'project_ids':['project-a'],'scopes':['read']})
    first = event('project-a',generate=False,payload={'title':'Decisión de origen','content':'La proyección requiere fencing.','category':'Arquitectura','tags':['diseño, seguro'],'source':{'uri':'fixture://source-a'},'facts':[{'subject':'proyección','predicate':'requiere','object':'fencing','evidence_quote':'La proyección requiere fencing.'}]})
    store.ingest_event(admin,first)
    store.ingest_event(admin,event('project-b',generate=False,payload={'title':'SECRETO B SINTÉTICO','content':'Contenido B sólo para fixture'}))
    job = store.ingest_event(admin,event('project-a',payload={'title':'Trabajo pendiente real','content':'Uso de leases con fencing','category':'Operación'}))
    with store.transaction() as c:
        c.execute("UPDATE memory.jobs SET state='failed',error_code='synthetic_unavailable' WHERE id=%s",(job['jobs'][0],))
    app = FastAPI()
    class PublicPages(StaticFiles):
        async def get_response(self, path, scope):
            # Static aliases do not wrap private SSE in BaseHTTPMiddleware.
            aliases = {'app': 'portal.html', 'app/': 'portal.html', 'login': 'portal.html', 'docs': 'docs.html', 'docs/': 'docs.html'}
            return await super().get_response(aliases.get(path, path), scope)
    app.mount('/memory-api',create_app(Settings(dsn,allowed_origins=(BASE,),cookie_secure=False),store=store))
    app.mount('/',PublicPages(directory=os.environ.get('KAIROS_E2E_WEB_ROOT', '/web'),html=True))
    server = uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8898,log_level='error'))
    server.fixture_corpus_patch = patch('memory_platform.corpus_answers.NativeCorpusProvider.answer', new=synthetic_corpus_answer)
    server.fixture_corpus_patch.start()
    threading.Thread(target=server.run,daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE+'/memory-api/health/ready',timeout=1)
            break
        except OSError:
            time.sleep(.05)
    else:
        raise RuntimeError('Owned local HTTP fixture did not start')
    return store, admin, server
