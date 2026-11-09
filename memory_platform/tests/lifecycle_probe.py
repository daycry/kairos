"""Node native hooks -> private IPC -> real MCP -> isolated PostgreSQL."""
import hashlib
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uvicorn
from unittest.mock import Mock, AsyncMock
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.tests.test_store import create_core, event
from memory_platform.worker import Worker


def run():
    store, actor, project = create_core()
    store.embedding_enabled=True
    store.set_policy(actor, project, {'capture_mode': 'full', 'temporal_projection': False})
    settings=Settings(os.environ['MEMORY_TEST_DSN'],embed_enabled=True)
    providers={'embed':Mock(embed=AsyncMock(return_value={'embedding':[1.0,0.0,0.0],'model':settings.embedding_model})),
               'extract':Mock(extract=AsyncMock())}
    worker=Worker(store,settings,providers)
    seed=event(project,generate=False,payload={'title':'Árbol: "índice" 🌳','content':'Useful correction for Árbol índice','tags':['nota:uno,dos']})
    control=store.ingest_event(actor,seed)
    assert len(control['jobs'])==1 and asyncio.run(worker.run_once())
    assert store.get_job(actor,control['jobs'][0])['state']=='succeeded'
    baseline=providers['embed'].embed.await_count+providers['extract'].extract.await_count
    assert baseline==1
    key = store.create_key(actor, {'name': 'Owned lifecycle probe', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(Settings(os.environ['MEMORY_TEST_DSN']), store=store), log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            raise RuntimeError('Isolated API did not start')
        with tempfile.TemporaryDirectory(prefix='kairos-client-probe-') as temporary:
            key_file = Path(temporary) / 'fixture.key'
            key_file.write_text(key, encoding='utf-8')
            key_file.chmod(0o600)
            env = {**os.environ, 'KAIROS_PROBE_BASE': temporary, 'KAIROS_PROBE_PROJECT': project,
                   'KAIROS_PROBE_URL': f'http://127.0.0.1:{port}'}
            # Child stdout contains counters only; never surface provider bodies
            # or the fixture credential on a failure.
            result = subprocess.run(['node', '/app/client/tests/lifecycle-live.mjs'], env=env,
                                    capture_output=True, text=True, timeout=40)
            if result.returncode:
                raise AssertionError('Native lifecycle probe failed: '+result.stderr.replace(key, '[REDACTED]')[-4000:])
            with store.transaction() as c:
                events = c.execute("SELECT body, receipt FROM memory.events WHERE project_id=%s AND body->>'agent_id'='codex'", (project,)).fetchall()
            assert len(events) == 1, 'Lost acknowledgement must not duplicate ingestion'
            body = events[0]['body']
            assert body['payload']['tags'] == ['runtime:codex', 'capture:full', 'tool:bash']
            assert '\u00c1rbol' in body['payload']['content']
            assert 'PRIVATE-HIDDEN' not in body['payload']['content']
            assert hashlib.sha256(body['payload']['content'].encode()).hexdigest() == body['payload']['source']['sha256']
            saved = store.get_item(actor, project, body['item_id'])
            assert saved['tags'] == body['payload']['tags']
            assert saved['version'] == 1
            assert not asyncio.run(worker.run_once())
            measured=providers['embed'].embed.await_count+providers['extract'].extract.await_count-baseline
            assert measured==0
            print('KAIROS_LIFECYCLE_RESULT '+json.dumps({'passed': True, 'database': 'PostgreSQL', 'native_hook_process': True,
                  'authenticated_ipc': True, 'real_mcp': True, 'persisted_events': 1, 'lost_ack_reconciled': True,
                  'provider_calls': measured, 'provider_calls_measured': True, 'embedding_enabled': True,
                  'control_provider_calls': baseline,'real_client_acceptance': False}, sort_keys=True), flush=True)
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
