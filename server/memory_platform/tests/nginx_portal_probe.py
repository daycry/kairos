"""Isolated probe of the portal's nginx (T-22): `python -m memory_platform.tests.nginx_portal_probe`.

It starts the `web/nginx.conf` of the portal (same pinned image as `web/Dockerfile`) in front of two stubs that echo the request line
they receive (`memory-api:8790` and, since T-52, `memory-mcp:8791`, which is where `/mcp` goes), in a throwaway network, and sends raw HTTP requests (curl `--path-as-is`, no client-side normalisation). It checks what reached
the stub: `/memory-api/` forwards the URI as it came (a corpus name such as `a%2F..%2Fb`, `//` and `..` included, query string included) and
never opens `/metrics`; `/mcp` reaches the kairos-mcp stub and never the API one. It never touches the deployed `knowledge-graphs` project, its containers, volumes or networks, and never the Ollama of
the host. Containers are `--rm` and named with a prefix (`KAIROS_PORTAL_PROBE_PREFIX`, default `kairos-portal-probe-`).

Since T-28 (CA-13, CA-14) the stubs also echo the `X-Forwarded-For` they receive: every route of nginx to the API sends it (the address of the client
appended by `$proxy_add_x_forwarded_for`); `/mcp` does not need it. A second part, `login`, puts the REAL API (`KAIROS_PORTAL_PROBE_API_IMAGE`, the test image with
its PostgreSQL, the code of this checkout mounted read-only) behind the real nginx: the API trusts only the internal network that it shares with nginx
(`MEMORY_TRUSTED_PROXIES` = its subnet) and two client containers on another network log in through nginx. Client A fails ten times, client B enters (200)
and its session keeps B's address, not the one of nginx; the eleventh attempt of A gets 429 with `Retry-After`, also when A writes another address in the header.
`python -m memory_platform.tests.nginx_portal_probe [routes] [login]` (both by default).

The suite does not run it (it needs a Docker daemon, which the test image does not have); `test_nginx_portal.py` checks the same rules in the
configuration text without Docker.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFIX = os.environ.get('KAIROS_PORTAL_PROBE_PREFIX', 'kairos-portal-probe-')
STUB_IMAGE = os.environ.get('KAIROS_PORTAL_PROBE_STUB_IMAGE', 'kairos-test:i2p2')  # any local image with python3; nothing is pulled
API_IMAGE = os.environ.get('KAIROS_PORTAL_PROBE_API_IMAGE', 'kairos-test:i4p5')  # the test target: python with the service's requirements and PostgreSQL; nothing is pulled
STUB = r'''
import http.server, json, sys
NAME, PORT = sys.argv[1], int(sys.argv[2])
class H(http.server.BaseHTTPRequestHandler):
    def do_ANY(self):
        out = json.dumps({'method': self.command, 'target': self.path, 'server': NAME, 'forwarded': self.headers.get('x-forwarded-for')}).encode()
        self.send_response(200); self.send_header('content-length', str(len(out))); self.end_headers(); self.wfile.write(out)
    do_GET = do_POST = do_ANY
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
'''
MCP_PREFIX = '/mcp'  # served by the stub named `mcp`; every other route by the stub named `api`
# (url, the request line the stub must receive, or None when nginx answers 404 itself)
CASES = [
    ('/memory-api/v1/projects/p/corpora/a%2F..%2Fb/query', '/v1/projects/p/corpora/a%2F..%2Fb/query'),
    ('/memory-api/v1/projects/p/corpora/x%2Fy/rebuild?z=1&w=%2F', '/v1/projects/p/corpora/x%2Fy/rebuild?z=1&w=%2F'),
    ('/memory-api/v1/projects/p/corpora/a//b/query', '/v1/projects/p/corpora/a//b/query'),
    ('/memory-api/v1/projects/p/corpora/a/../b/query', '/v1/projects/p/corpora/a/../b/query'),
    ('/memory-api/v1/search', '/v1/search'),
    ('/memory-api/', '/'),
    ('/v1/x%2Fy', '/v1/x%2Fy'),
    ('/mcp/', '/mcp/'),
    ('/mcp', '/mcp'),
    ('/mcp/anything?x=1', '/mcp/anything?x=1'),
    ('/health/ready', '/health/ready'),
    ('/memory-api/metrics', None),
    ('/memory-api//metrics', None),
    ('/memory-api/%2Fmetrics', None),
    ('/memory-api/%6Detrics', None),
    ('/memory-api/x%2F..%2Fmetrics', None),
    ('/memory-api/v1/%2e%2e/metrics', None),
]


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def pinned_image():
    found = re.search(r'^FROM (nginx@sha256:[0-9a-f]{64})', (ROOT / 'web' / 'Dockerfile').read_text(encoding='utf-8'), re.M)
    assert found, 'web/Dockerfile has no pinned nginx image'
    return found.group(1)


def routes():
    network, stub, mcp_stub, web = PREFIX + 'net', PREFIX + 'stub', PREFIX + 'mcp', PREFIX + 'nginx'
    failures = []
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / 'stub.py'
        script.write_text(STUB, encoding='utf-8')
        try:
            docker('network', 'create', network)
            docker('run', '-d', '--rm', '--name', stub, '--network', network, '--network-alias', 'memory-api', '-v', f'{script}:/stub.py:ro', STUB_IMAGE, 'python3', '/stub.py', 'api', '8790')
            docker('run', '-d', '--rm', '--name', mcp_stub, '--network', network, '--network-alias', 'memory-mcp', '-v', f'{script}:/stub.py:ro', STUB_IMAGE, 'python3', '/stub.py', 'mcp', '8791')
            docker('run', '-d', '--rm', '--name', web, '--network', network, '-v', f'{ROOT / "web" / "nginx.conf"}:/etc/nginx/nginx.conf:ro', '--tmpfs', '/tmp', pinned_image())
            for _ in range(30):
                if docker('exec', web, 'curl', '-s', '-o', '/dev/null', 'http://localhost:8080/health/live', check=False).returncode == 0:
                    break
                docker('exec', web, 'sleep', '0.3', check=False)
            for url, expected in CASES:
                run = docker('exec', web, 'curl', '-s', '--path-as-is', '-w', '\n%{http_code}', '-X', 'GET', 'http://localhost:8080' + url, check=False)
                body, _, code = run.stdout.rpartition('\n')
                if expected is None:
                    ok = code == '404' and '"target"' not in body
                else:
                    seen, api = json.loads(body), not url.startswith(MCP_PREFIX)
                    # the header reaches the API with the address of the client (curl runs inside the nginx container: 127.0.0.1); kairos-mcp does not use it
                    ok = code == '200' and seen['target'] == expected and seen['server'] == ('api' if api else 'mcp') and (seen['forwarded'] == '127.0.0.1' or not api)
                print(('ok   ' if ok else 'FAIL ') + url, '->', code, body[:100].replace('\n', ' '))
                if not ok:
                    failures.append(url)
        finally:
            for name in (web, stub, mcp_stub):
                docker('stop', '-t', '1', name, check=False)
            docker('network', 'rm', network, check=False)
    print('PORTAL_PROBE_RESULT', json.dumps({'cases': len(CASES), 'failures': failures}))
    return failures


# The API of the `login` part: a PostgreSQL of its own in the container, the schema, the users `probe-admin` and `ana`, and uvicorn with the options of the service.
# The code of this checkout is mounted at /src and its contracts at /docs/contracts (where the code looks for its schemas: next to `server/`).
API = r'''
import os, subprocess, sys, tempfile
sys.path.insert(0, '/src')
root = tempfile.mkdtemp()
subprocess.run(['initdb', '-D', root + '/data', '-A', 'trust', '--encoding=UTF8', '--no-locale'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['pg_ctl', '-D', root + '/data', '-o', '-h 127.0.0.1 -p 5432 -k ' + root, '-w', 'start', '-l', root + '/log'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['createdb', '-h', '127.0.0.1', '-U', 'postgres', 'probe'], check=True)
import uvicorn
from memory_platform.app import SERVER_OPTIONS, create_app
from memory_platform.config import Settings
from memory_platform.store import Store
dsn = 'postgresql://postgres@127.0.0.1:5432/probe'
store = Store(dsn)
store.migrate()
admin = store.bootstrap_user('probe-admin', 'probe-admin-password-1')
store.create_project(admin, {'id': 'p1', 'title': 'Probe'})
store.create_user(admin, {'username': 'ana', 'password': 'probe-password-123', 'project_ids': ['p1'], 'scopes': ['read']})
settings = Settings(dsn, allowed_origins=('http://probe.invalid',), mount_mcp=False, trusted_proxies=(os.environ['TRUSTED'],))
uvicorn.run(create_app(settings), **SERVER_OPTIONS)
'''
ORIGIN = 'http://probe.invalid'


def login():
    """CA-13 and CA-14 with the real nginx and the real API (module docstring). Returns the names of the checks that failed."""
    back, front = PREFIX + 'back', PREFIX + 'front'
    api, mcp_stub, web, client_a, client_b = PREFIX + 'api', PREFIX + 'mcp2', PREFIX + 'nginx2', PREFIX + 'client-a', PREFIX + 'client-b'
    failures, checks = [], []

    def check(name, ok, detail=''):
        checks.append(name)
        print(('ok   ' if ok else 'FAIL ') + name, detail)
        if not ok:
            failures.append(name)

    def curl(client, *args):
        run = docker('exec', client, 'curl', '-s', '-D', '/dev/stderr', '-w', '\n%{http_code}', *args, check=False)
        body, _, code = run.stdout.rpartition('\n')
        return code, body, run.stderr

    def attempt(client, password, forwarded=None):
        args = ['-X', 'POST', f'http://{web}:8080/v1/auth/login', '-H', 'Origin: ' + ORIGIN, '-H', 'Content-Type: application/json',
                '--data', json.dumps({'username': 'ana', 'password': password})]
        if forwarded:
            args += ['-H', 'X-Forwarded-For: ' + forwarded]
        return curl(client, *args)
    with tempfile.TemporaryDirectory() as directory:
        stub, script = Path(directory) / 'stub.py', Path(directory) / 'api.py'
        stub.write_text(STUB, encoding='utf-8')
        script.write_text(API, encoding='utf-8')
        try:
            docker('network', 'create', back)
            docker('network', 'create', front)
            subnet = json.loads(docker('network', 'inspect', back).stdout)[0]['IPAM']['Config'][0]['Subnet']
            docker('run', '-d', '--rm', '--name', api, '--network', back, '--network-alias', 'memory-api', '-e', 'TRUSTED=' + subnet, '--tmpfs', '/tmp',
                   '-v', f'{ROOT / "server"}:/src:ro', '-v', f'{ROOT / "docs" / "contracts"}:/docs/contracts:ro', '-v', f'{script}:/probe_api.py:ro', '--entrypoint', '/opt/memory-venv/bin/python', API_IMAGE, '/probe_api.py')
            docker('run', '-d', '--rm', '--name', mcp_stub, '--network', back, '--network-alias', 'memory-mcp', '-v', f'{stub}:/stub.py:ro', STUB_IMAGE, 'python3', '/stub.py', 'mcp', '8791')
            ready = False
            for _ in range(120):  # the API creates its database first
                probe = docker('run', '--rm', '--network', back, '--entrypoint', 'curl', pinned_image(), '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://memory-api:8790/health/ready', check=False)
                if probe.stdout == '200':
                    ready = True
                    break
                docker('exec', mcp_stub, 'sleep', '0.5', check=False)
            check('the API answers on the internal network', ready, '' if ready else docker('logs', '--tail', '20', api, check=False).stderr[-600:])
            if not ready:
                return failures
            docker('run', '-d', '--rm', '--name', web, '--network', back, '-v', f'{ROOT / "web" / "nginx.conf"}:/etc/nginx/nginx.conf:ro', '--tmpfs', '/tmp', pinned_image())
            docker('network', 'connect', front, web)
            for client in (client_a, client_b):
                docker('run', '-d', '--rm', '--name', client, '--network', front, '--entrypoint', 'sleep', pinned_image(), '600')
            address = {c: json.loads(docker('inspect', c).stdout)[0]['NetworkSettings']['Networks'][front]['IPAddress'] for c in (client_a, client_b)}
            for _ in range(30):
                if curl(client_b, f'http://{web}:8080/health/live')[0] == '200':
                    break
                docker('exec', client_b, 'sleep', '0.3', check=False)
            codes = [attempt(client_a, 'not-the-password-999')[0] for _ in range(10)]
            check('ten failures of A through nginx are 401', codes == ['401'] * 10, codes)
            code, body, headers = attempt(client_b, 'probe-password-123')
            check('B, from another IP, enters (200)', code == '200', code + ' ' + body[:120])
            cookie = re.search(r'(?im)^set-cookie: *(memory_session=[^;]+)', headers)
            code, body, _ = curl(client_b, '-H', 'Cookie: ' + (cookie.group(1) if cookie else ''), f'http://{web}:8080/v1/auth/sessions')
            seen = [item['client_ip'] for item in json.loads(body)['items']] if code == '200' else body[:120]
            check('the session of B keeps the address of B, not the one of nginx', seen == [address[client_b]], f'{seen} (B {address[client_b]})')
            stored = {table: docker('exec', api, 'psql', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'probe', '-Atc', f'SELECT DISTINCT client_ip FROM memory.{table}', check=False).stdout.split()
                      for table in ('login_attempts', 'web_sessions')}
            check('the API keeps the address of each client, never the one of nginx', stored == {'login_attempts': [address[client_a]], 'web_sessions': [address[client_b]]}, f'{stored} (A {address[client_a]})')
            code, body, headers = attempt(client_a, 'probe-password-123')
            retry = re.search(r'(?im)^retry-after: *(\d+)', headers)
            check('the eleventh of A is 429 with Retry-After', code == '429' and retry is not None and int(retry.group(1)) >= 1, code + ' ' + body[:120])
            code, body, _ = attempt(client_a, 'probe-password-123', forwarded='203.0.113.7')
            check('a header written by A does not dodge the block', code == '429', code)
            code, _, _ = curl(client_b, f'http://{web}:8080/memory-api/metrics')
            check('/metrics is 404 through nginx', code == '404', code)
        finally:
            for name in (client_a, client_b, web, api, mcp_stub):
                docker('stop', '-t', '1', name, check=False)
            for name in (front, back):
                docker('network', 'rm', name, check=False)
    print('PORTAL_LOGIN_PROBE_RESULT', json.dumps({'checks': len(checks), 'failures': failures}))
    return failures


def main(parts=('routes', 'login')):
    assert not re.search('knowledge-graphs', PREFIX, re.I), 'the probe never uses the names of the deployed project'
    failures = []
    for part in parts:
        failures += {'routes': routes, 'login': login}[part]()
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(tuple(sys.argv[1:]) or ('routes', 'login')))
