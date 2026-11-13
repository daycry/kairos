"""Early check with real parts (T-39, CA-09): the kairos-mcp CONTAINER, started with `KAIROS_API_URL` alone, answers `/health/live` and
lists its 34 tools, next to a simulated `/v1` server, in an isolated Compose project.

Run from the repository root: `python mcp/tests/smoke_container.py`. It builds the image of `mcp/`, starts `compose.smoke.yml` under its own
project name (`kairos-mcp-smoke`, or `KAIROS_SMOKE_PROJECT`), asks over HTTP and removes what it created (containers, network, volumes, the
image). It never touches a resource of the installed project: the containers named `knowledge-graphs-*` are listed before and after, and a
difference fails the run. Prints `PASS health 200; tools 34` and exits 0.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / 'compose.smoke.yml'
PROJECT = os.environ.get('KAIROS_SMOKE_PROJECT', 'kairos-mcp-smoke')
IMAGE = PROJECT + '-image:smoke'
EXPECTED_TOOLS = 34
CREDENTIAL = 'Bearer smoke-synthetic-token'
READY_SECONDS = 90


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise SystemExit('docker %s failed (%d): %s' % (' '.join(args[:3]), result.returncode, (result.stderr or result.stdout).strip()[-600:]))
    return result


def installed_containers():
    """The containers of the installed project: never created, changed or removed here."""
    return sorted(docker('ps', '-a', '-q', '--filter', 'name=knowledge-graphs-').stdout.split())


def compose(*args, check=True):
    env = {**os.environ, 'KAIROS_SMOKE_IMAGE': IMAGE}
    result = subprocess.run(['docker', 'compose', '-p', PROJECT, '-f', str(COMPOSE), *args], capture_output=True, text=True, encoding='utf-8',
                            errors='replace', env=env)
    if check and result.returncode:
        raise SystemExit('docker compose %s failed (%d): %s' % (args[0], result.returncode, (result.stderr or result.stdout).strip()[-800:]))
    return result


def get(url, headers=None, body=None):
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers or {}, method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read())


def published_port():
    out = compose('port', 'memory-mcp', '8791').stdout.strip()
    match = re.search(r':(\d+)\s*$', out)
    if not match:
        raise SystemExit('the memory-mcp port is not published: ' + out)
    return int(match.group(1))


def wait_live(base):
    deadline = time.monotonic() + READY_SECONDS
    last = None
    while time.monotonic() < deadline:
        try:
            return get(base + '/health/live')
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(1)
    raise SystemExit('memory-mcp did not answer /health/live in %d s: %s' % (READY_SECONDS, last))


def main():
    if not COMPOSE.is_file():
        raise SystemExit('missing ' + str(COMPOSE))
    before = installed_containers()
    try:
        compose('up', '-d', '--build')
        base = 'http://127.0.0.1:%d' % published_port()
        status, body = wait_live(base)
        if (status, body) != (200, {'status': 'live'}):
            raise SystemExit('health answered %r' % ((status, body),))
        _, listing = get(base + '/mcp/', {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json', 'Authorization': CREDENTIAL},
                         {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
        tools = listing['result']['tools']
        if len(tools) != EXPECTED_TOOLS:
            raise SystemExit('tools/list returned %d tools, expected %d' % (len(tools), EXPECTED_TOOLS))
        print('PASS health %d; tools %d' % (status, len(tools)))
    finally:
        compose('down', '-v', '--remove-orphans', check=False)
        docker('rmi', IMAGE, check=False)
        after = installed_containers()
        leftovers = docker('ps', '-a', '-q', '--filter', 'label=com.docker.compose.project=' + PROJECT).stdout.split()
        if after != before or leftovers:
            print('FAIL isolation: installed containers %r -> %r, smoke leftovers %r' % (before, after, leftovers), file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
