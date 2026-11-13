"""Isolated Compose probe of the Ollama proxy (CA-17, S-09, P-10): `python -m memory_platform.tests.ollama_proxy_probe`.

It starts ONLY the `ollama` proxy service of docker-compose.yml, plus a stub upstream that records every request, in a Compose
project named `kairos-proxy-*` whose networks and volumes are renamed by an override file, then asks the proxy for allowed and
forbidden paths with raw HTTP (no client-side normalisation) and reads what reached the stub. It never touches the deployed
`knowledge-graphs` project, its containers, volumes or networks, and never the Ollama of the host: the upstream is the stub.

The suite does not run it (it needs a Docker daemon, which the test image does not have); `test_ollama_proxy.py` covers the
template, the Compose service and this file's isolation rules without Docker.
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
COMPOSE = ROOT / 'docker-compose.yml'
PREFIX = 'kairos-proxy-'
FORBIDDEN_NAME = re.compile(r'knowledge-graphs', re.IGNORECASE)
STUB_IMAGE = os.environ.get('KAIROS_PROXY_STUB_IMAGE', 'kairos-test:i2p2')  # any local image with python3; nothing is pulled

STUB = r'''
import http.server, json, sys
hits = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def handle_any(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length: self.rfile.read(length)
        if self.path == '/__hits':
            body = json.dumps(hits).encode()
        else:
            hits.append([self.command, self.path, self.headers.get('Host'), self.headers.get('User-Agent') or ''])
            body = json.dumps({'stub': self.path}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = handle_any
http.server.ThreadingHTTPServer(('0.0.0.0', 11434), Handler).serve_forever()
'''

CLIENT = r'''
import http.client, json, sys
host, requests = sys.argv[1], json.loads(sys.argv[2])
out = []
for method, path in requests:
    connection = http.client.HTTPConnection(host, 11434, timeout=10)
    connection.putrequest(method, path, skip_host=False)  # the path goes out exactly as written
    connection.putheader('Content-Length', '2' if method == 'POST' else '0'); connection.endheaders(b'{}' if method == 'POST' else None)
    response = connection.getresponse(); response.read()
    out.append([method, path, response.status])
print(json.dumps(out))
'''


def project_name(name: str) -> str:
    """The only names the probe accepts: a Compose project of its own, never the deployed one."""
    if not name.startswith(PREFIX) or FORBIDDEN_NAME.search(name) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,40}', name):
        raise ValueError('The probe only runs in a Compose project named %s*' % PREFIX)
    return name


def override(project: str, secrets_dir: str, allow_chat: str = '0') -> dict:
    """Compose override: stub upstream, no fixed-name resource of the real project, upstream pointed at the stub."""
    project = project_name(project)
    return {
        'services': {
            'ollama': {'environment': {'OLLAMA_UPSTREAM': 'stub:11434', 'OLLAMA_ALLOW_CHAT': allow_chat}},
            'stub': {'image': STUB_IMAGE, 'entrypoint': ['python', '-c', STUB], 'networks': ['inference'], 'restart': 'no'},
        },
        'networks': {'inference': {'name': project + '_inference'}, 'webui': {'name': project + '_webui'}, 'mcp': {'name': project + '_mcp'}},
        'volumes': {'memory-postgres-data': {'name': project + '_postgres'}, 'memory-backups': {'name': project + '_backups'}},
        'secrets': {name: {'file': secrets_dir + '/' + name} for name in ('postgres_password', 'dsn', 'bootstrap_password')},
    }


class Probe:
    def __init__(self, project: str, workdir: Path):
        self.project, self.workdir = project_name(project), workdir
        secrets = workdir / 'secrets'
        secrets.mkdir()
        for name in ('postgres_password', 'dsn', 'bootstrap_password'):
            (secrets / name).write_text('unused-probe-secret', encoding='utf-8')
        self.secrets = secrets.as_posix()

    def compose(self, *args, allow_chat='0', check=True):
        override_file = self.workdir / 'override.json'  # JSON is valid YAML
        override_file.write_text(json.dumps(override(self.project, self.secrets, allow_chat)), encoding='utf-8')
        env = dict(os.environ, OLLAMA_ALLOW_CHAT=allow_chat, MEMORY_SECRETS_DIR=self.secrets)
        command = ['docker', 'compose', '-p', self.project, '-f', str(COMPOSE), '-f', str(override_file), *args]
        return subprocess.run(command, capture_output=True, text=True, check=check, env=env)

    def names(self):
        """Every resource the project may own, resolved by Compose itself, to prove none belongs to `knowledge-graphs`."""
        config = json.loads(self.compose('config', '--format', 'json').stdout)
        names = [self.project] + [v.get('name', '') for v in config.get('networks', {}).values()] + [v.get('name', '') for v in config.get('volumes', {}).values()]
        for name in names:
            if FORBIDDEN_NAME.search(name):
                raise RuntimeError('Refusing to run: %r belongs to the deployed project' % name)
        return names

    def up(self, allow_chat='0'):
        self.names()
        self.compose('up', '-d', '--force-recreate', '--wait', 'ollama', 'stub', allow_chat=allow_chat)

    def ask(self, requests):
        result = self.compose('exec', '-T', 'stub', 'python', '-c', CLIENT, 'ollama', json.dumps(requests))
        return [tuple(item) for item in json.loads(result.stdout)]

    def hits(self):
        raw = self.compose('exec', '-T', 'stub', 'python', '-c',
                           "import urllib.request,sys;print(urllib.request.urlopen('http://127.0.0.1:11434/__hits').read().decode())").stdout
        # The proxy's own healthcheck (wget) also goes through the proxy to the stub: it is not a request of the probe.
        return [hit for hit in json.loads(raw) if not hit[3].lower().startswith(('wget', 'busybox'))]

    def down(self):
        self.compose('down', '-v', '--remove-orphans', check=False)


# (method, raw path, status through the proxy, reaches the stub with this path or None)
BASE = [
    ('POST', '/api/embed', 200, '/api/embed'),
    ('GET', '/api/version', 200, '/api/version'),
    ('POST', '/api/embed?x=1', 200, '/api/embed?x=1'),
    ('POST', '/api/pull', 403, None), ('DELETE', '/api/delete', 403, None), ('POST', '/api/create', 403, None),
    ('POST', '/api/generate', 403, None), ('POST', '/api/chat', 403, None), ('GET', '/', 403, None), ('GET', '/api/tags', 403, None),
    ('GET', '/api/embed', 403, None), ('POST', '/api/version', 403, None),
    # evasions: none may reach the stub as anything but the allowed constant path
    ('POST', '/API/EMBED', 403, None), ('POST', '/api/embed/', 403, None), ('POST', '//api/embed', 200, '/api/embed'),
    ('POST', '/api/embed/../pull', 403, None), ('POST', '/api/embed%2f..%2fpull', 403, None), ('POST', '/api/%65mbed', 200, '/api/embed'),
    ('POST', '/api/chat/../embed', 200, '/api/embed'), ('POST', '/api/embed/%2e%2e/chat', 403, None), ('POST', '/api/embed;/pull', 403, None),
    ('POST', '/api//pull', 403, None), ('POST', '/api/pull/..;/embed', 403, None),
]
CHAT_ON = [('POST', '/api/chat', 200, '/api/chat'), ('POST', '/api/generate', 403, None), ('POST', '/api/pull', 403, None), ('GET', '/api/chat', 403, None)]


def check(probe: Probe, cases, label):
    seen = len(probe.hits())
    results = probe.ask([[method, path] for method, path, *_ in cases])
    problems = []
    for (method, path, status, _), (_, _, got) in zip(cases, results):
        if got != status:
            problems.append('%s %s: status %s, expected %s' % (method, path, got, status))
    arrived = probe.hits()[seen:]
    expected = [reached for *_, reached in cases if reached]
    if [hit[1] for hit in arrived] != expected:
        problems.append('upstream received %s, expected %s' % ([hit[1] for hit in arrived], expected))
    if {hit[2] for hit in arrived} - {'localhost'}:
        problems.append('unexpected Host upstream: %s' % {hit[2] for hit in arrived})
    print('%s: %d requests, %d reached the stub, %d problems' % (label, len(cases), len(expected), len(problems)))
    for problem in problems:
        print('  PROBLEM', problem)
    return problems


def main():
    project = os.environ.get('KAIROS_PROXY_PROJECT', 'kairos-proxy-t13')
    with tempfile.TemporaryDirectory(prefix='kairos-proxy-') as tmp:
        probe = Probe(project, Path(tmp))
        problems = []
        try:
            probe.up('0')
            problems += check(probe, BASE, 'default (chat off)')
            nginx_test = probe.compose('exec', '-T', 'ollama', 'nginx', '-t')
            print((nginx_test.stdout + nginx_test.stderr).strip().splitlines()[-1])
            user = probe.compose('exec', '-T', 'ollama', 'id', '-u').stdout.strip()
            print('proxy uid:', user)
            if user in ('', '0'):
                problems.append('the proxy runs as root')
            probe.down()
            probe.up('1')
            problems += check(probe, CHAT_ON, 'OLLAMA_ALLOW_CHAT=1')
        finally:
            probe.down()
        print('PROXY_PROBE_RESULT', json.dumps({'project': project, 'problems': problems}))
        return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
