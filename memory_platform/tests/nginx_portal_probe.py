"""Isolated probe of the portal's nginx (T-22): `python -m memory_platform.tests.nginx_portal_probe`.

It starts the `memory_platform/nginx.conf` of the portal (same pinned image as `Dockerfile.web`) in front of two stubs that echo the request line
they receive (`memory-api:8790` and, since T-52, `memory-mcp:8791`, which is where `/mcp` goes), in a throwaway network, and sends raw HTTP requests (curl `--path-as-is`, no client-side normalisation). It checks what reached
the stub: `/memory-api/` forwards the URI as it came (a corpus name such as `a%2F..%2Fb`, `//` and `..` included, query string included) and
never opens `/metrics`; `/mcp` reaches the kairos-mcp stub and never the API one. It never touches the deployed `knowledge-graphs` project, its containers, volumes or networks, and never the Ollama of
the host. Containers are `--rm` and named with a prefix (`KAIROS_PORTAL_PROBE_PREFIX`, default `kairos-portal-probe-`).

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

ROOT = Path(__file__).resolve().parents[2]
PREFIX = os.environ.get('KAIROS_PORTAL_PROBE_PREFIX', 'kairos-portal-probe-')
STUB_IMAGE = os.environ.get('KAIROS_PORTAL_PROBE_STUB_IMAGE', 'kairos-test:i2p2')  # any local image with python3; nothing is pulled
STUB = r'''
import http.server, json, sys
NAME, PORT = sys.argv[1], int(sys.argv[2])
class H(http.server.BaseHTTPRequestHandler):
    def do_ANY(self):
        out = json.dumps({'method': self.command, 'target': self.path, 'server': NAME}).encode()
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
    found = re.search(r'^FROM (nginx@sha256:[0-9a-f]{64})', (ROOT / 'memory_platform' / 'Dockerfile.web').read_text(encoding='utf-8'), re.M)
    assert found, 'Dockerfile.web has no pinned nginx image'
    return found.group(1)


def main():
    assert not re.search('knowledge-graphs', PREFIX, re.I), 'the probe never uses the names of the deployed project'
    network, stub, mcp_stub, web = PREFIX + 'net', PREFIX + 'stub', PREFIX + 'mcp', PREFIX + 'nginx'
    failures = []
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / 'stub.py'
        script.write_text(STUB, encoding='utf-8')
        try:
            docker('network', 'create', network)
            docker('run', '-d', '--rm', '--name', stub, '--network', network, '--network-alias', 'memory-api', '-v', f'{script}:/stub.py:ro', STUB_IMAGE, 'python3', '/stub.py', 'api', '8790')
            docker('run', '-d', '--rm', '--name', mcp_stub, '--network', network, '--network-alias', 'memory-mcp', '-v', f'{script}:/stub.py:ro', STUB_IMAGE, 'python3', '/stub.py', 'mcp', '8791')
            docker('run', '-d', '--rm', '--name', web, '--network', network, '-v', f'{ROOT / "memory_platform" / "nginx.conf"}:/etc/nginx/nginx.conf:ro', '--tmpfs', '/tmp', pinned_image())
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
                    ok = code == '200' and json.loads(body)['target'] == expected and json.loads(body)['server'] == ('mcp' if url.startswith(MCP_PREFIX) else 'api')
                print(('ok   ' if ok else 'FAIL ') + url, '->', code, body[:100].replace('\n', ' '))
                if not ok:
                    failures.append(url)
        finally:
            for name in (web, stub, mcp_stub):
                docker('stop', '-t', '1', name, check=False)
            docker('network', 'rm', network, check=False)
    print('PORTAL_PROBE_RESULT', json.dumps({'cases': len(CASES), 'failures': failures}))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
