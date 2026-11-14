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
from memory_platform.tests.chain_harness import MCP_ROOT  # noqa: F401 (puts `mcp/` on sys.path: kairos-mcp is a separate component, CA-08)
from memory_platform.tests.test_store import create_core, event
from memory_platform.worker import Worker


REQUIRED = {'projects', 'search', 'details', 'context', 'timeline', 'remember', 'event_status',
            'publish_document', 'document_status', 'document_manifest', 'revoke_document'}  # `REQUIRED_TOOLS` of packages/kairos-cli/lib/mcp.mjs


def serve(application):
    """`application` on a loopback socket of its own, in a thread: (server, thread, listener, port)."""
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(application, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError('Isolated server did not start')
    return server, thread, listener, listener.getsockname()[1]


def stop(server, thread, listener):
    server.should_exit = True
    thread.join(timeout=8)
    listener.close()


def stdio_bridge(node_bin, url, key_file, key):
    """`kairos mcp` as a client launches it: JSON-RPC lines on stdin and stdout, against `url` (CA-28). Returns the server info, the tool names and the `projects` answer."""
    child = subprocess.Popen(['node', str(node_bin), 'mcp', '--url', url, '--key-file', str(key_file)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        def ask(identifier, method, params=None):
            child.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params or {}}) + chr(10))
            child.stdin.flush()
            answer = json.loads(child.stdout.readline())
            assert answer.get('id') == identifier and 'result' in answer, 'bridge answer: '+json.dumps(answer)[:400].replace(key, '[REDACTED]')
            return answer['result']
        info = ask(1, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'lifecycle-probe', 'version': '1'}})
        child.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}}) + chr(10))
        tools = ask(2, 'tools/list')['tools']
        projects = ask(3, 'tools/call', {'name': 'projects', 'arguments': {}})
        return info, {tool['name'] for tool in tools}, projects
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        child.stdout.close()
        child.stderr.close()


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
    # The chain of C-07 over real sockets: CLI -> kairos-mcp (`/mcp/`, the route the proxy serves) -> `/v1` of the server -> PostgreSQL. The CLI is given
    # the address of kairos-mcp alone; the internal MCP of the server (`/mcp` of the API) is not in the path.
    import kairos_mcp
    from kairos_mcp.app import create_app as create_kairos_mcp
    api, api_thread, api_listener, api_port = serve(create_app(Settings(os.environ['MEMORY_TEST_DSN']), store=store))
    mcp, mcp_thread, mcp_listener, port = serve(create_kairos_mcp(api_url=f'http://127.0.0.1:{api_port}'))
    try:
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
            # CA-28: the stdio bridge and `kairos doctor` against kairos-mcp, with the installation the lifecycle script made.
            installed = Path(temporary) / 'project é'
            node_bin = next((installed / '.kairos' / 'runtime').glob('*/bin/kairos.mjs'))
            info, names, projects = stdio_bridge(node_bin, f'http://127.0.0.1:{port}', key_file, key)
            assert info['serverInfo']['version'] == kairos_mcp.__version__, 'the bridge reached '+json.dumps(info['serverInfo'])  # FastMCP of the server reports the SDK version
            assert len(names) == 34 and REQUIRED <= names, 'kairos-mcp lists '+str(len(names))+' tools; missing '+str(sorted(REQUIRED-names))
            assert not projects.get('isError') and project in json.dumps(projects), 'projects answers for the project of the key'
            doctor = subprocess.run(['node', str(node_bin), 'doctor', '--root', str(installed), '--online'], capture_output=True, text=True, encoding='utf-8', timeout=40)
            report = json.loads(doctor.stdout or '{}')
            assert doctor.returncode == 0 and report.get('status') == 'ready', 'doctor: '+(doctor.stdout+doctor.stderr).replace(key, '[REDACTED]')[-2000:]
            assert report['network_checked'] and report['missing_tools'] == [] and report['project_authorized'] is True and REQUIRED <= set(report['tools'])
            print('KAIROS_LIFECYCLE_RESULT '+json.dumps({'passed': True, 'database': 'PostgreSQL', 'native_hook_process': True,
                  'authenticated_ipc': True, 'real_mcp': True, 'persisted_events': 1, 'lost_ack_reconciled': True,
                  'provider_calls': measured, 'provider_calls_measured': True, 'embedding_enabled': True,
                  'control_provider_calls': baseline,'real_client_acceptance': False,
                  'kairos_mcp': True, 'bridge_tools': len(names), 'doctor': report['status']}, sort_keys=True), flush=True)
    finally:
        stop(mcp, mcp_thread, mcp_listener)
        stop(api, api_thread, api_listener)
