"""Deploy Kairos without importing files, changing capture policy or deleting data.

The default only prints a plan. --apply checks the engine before any local write.
An existing installation must have its original volumes and secret files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VOLUMES = ('knowledge-graphs_memory-postgres-data', 'knowledge-graphs_memory-backups')
SERVICES = ('memory-api', 'memory-worker', 'memory-web')
PHASES = ('engine', 'configuration', 'build', 'database', 'inspect', 'backup',
          'migrate', 'bootstrap', 'start', 'verify')


class DeploymentError(Exception):
    pass


def redact_output(value, known_values=()):
    for secret in sorted((v for v in known_values if v), key=len, reverse=True):
        value = value.replace(secret, '[redacted]')
    value = re.sub(r'(?i)(authorization[=: ]+(?:bearer|basic)\s+)\S+', r'\1[redacted]', value)
    value = re.sub(r'(?i)((?:password|api[_-]?key)[=:]\s*)[^\s,;]+', r'\1[redacted]', value)
    value = re.sub(r'(?i)(postgres(?:ql)?://[^:/\s]+:)[^@\s]+@', r'\1[redacted]@', value)
    return value


def read_env(path):
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() and not key.lstrip().startswith('#'):
            values[key.strip()] = value.strip().strip('\"').strip("'")
    return values


def safe_path(path):
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise DeploymentError('A deployment path traverses a symlink or junction')
    return path


def decode_json(output):
    # Compose diagnostics belong on stderr; require one complete JSON value.
    try:
        return json.loads(output)
    except (TypeError, ValueError):
        raise DeploymentError('The operator returned an invalid JSON result') from None


def compare_content(before, after):
    if before['sha256'] != after['sha256']:
        raise DeploymentError('Canonical content changed during deployment; reconcile before declaring success')


def native_network_hash(config):
    """Compose's recorded layout for this distribution's simple bridge networks.

    Preserve field presence: omitted driver and explicit bridge have different
    persisted hashes even when Docker's effective driver is the same.
    """
    order = ('name', 'driver', 'ipam', 'internal')
    if set(config) - set(order):
        raise DeploymentError('Advanced network configuration requires an explicit migration plan')
    data = {key: config.get(key, {}) for key in order if key in config or key == 'ipam'}
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def check_network(desired, observed):
    expected = native_network_hash(desired)
    actual = (observed.get('Labels') or {}).get('com.docker.compose.config-hash')
    if observed.get('Driver') != desired.get('driver', 'bridge') or bool(observed.get('Internal')) != bool(desired.get('internal')):
        raise DeploymentError('Existing network topology differs; stop before touching services')
    if actual and actual != expected:
        raise DeploymentError('Network '+desired['name']+' definition differs from its recorded configuration; no service was changed')
    return {'name': desired['name'], 'expected_hash': expected, 'recorded_hash': actual}


class Deployment:
    def __init__(self, args, root=ROOT):
        self.args, self.root = args, root
        self.private = safe_path(root / '.private')
        self.report = {'status': 'pending', 'phases': [], 'backup': None,
                       'data_removed': False, 'capture_policy_changed': False}
        self.compose = ['docker', 'compose', '-p', 'knowledge-graphs', '--project-directory', str(root)]
        self.phase = 'engine'
        self.secret_values = []

    def run(self, command, timeout=120):
        try:
            result = subprocess.run(command, cwd=self.root, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise DeploymentError('Command unavailable or timed out; verify its actual state before retrying') from None
        if result.returncode:
            # Retain the reason without exposing configured secrets. Redact
            # before truncating so the cut cannot expose a secret suffix.
            self.report['command_failure'] = {
                'command': [redact_output(v, self.secret_values) for v in command],
                'exit_code': result.returncode,
                'details': redact_output(result.stdout+'\n'+result.stderr, self.secret_values)[-8000:]}
            raise DeploymentError(f'Command failed during {self.phase}.')
        return result.stdout.strip()

    def step(self, name):
        self.phase = name
        self.report['phases'].append(name)
        print(f'Kairos: {name}', flush=True)

    def operator(self, *args):
        return decode_json(self.run(self.compose + ['run', '--rm', '--no-deps', '-T', 'memory-admin', *args]))

    def save_report(self):
        self.private.mkdir(parents=True, exist_ok=True)
        destination = safe_path(self.private / 'deployment-status.json')
        temporary = safe_path(self.private / 'deployment-status.tmp')
        temporary.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')
        temporary.replace(destination)

    def apply(self):
        self.step('engine')
        self.run(['docker', 'version', '--format', '{{.Server.Version}}'])
        self.run(['docker', 'compose', 'version', '--short'])
        # No secret creation, image build or service change precedes this check.
        self.step('configuration')
        config = read_env(self.root / '.env')
        config.update(read_env(self.private / 'memory-platform.env'))
        configured_dir = os.environ.get('MEMORY_SECRETS_DIR') or config.get('MEMORY_SECRETS_DIR')
        if self.args.secret_dir and configured_dir and Path(self.args.secret_dir).resolve() != Path(configured_dir).resolve():
            raise DeploymentError('--secret-dir differs from existing configuration; nothing was replaced')
        secret_dir = self.args.secret_dir or configured_dir
        if not secret_dir:
            raise DeploymentError('Configure MEMORY_SECRETS_DIR or --secret-dir before deployment')
        self.secret_dir = safe_path(Path(secret_dir))
        if self.args.fresh:
            self.run([sys.executable, str(self.root / 'scripts/memory-admin.py'), 'prepare',
                      '--secret-dir', str(self.secret_dir),
                      '--env-output', str(self.private / 'memory-platform.env')])
        for name in ('postgres_password', 'dsn', 'bootstrap_password'):
            path = safe_path(self.secret_dir / name)
            if not path.is_file() or not path.read_text(encoding='utf-8').strip():
                raise DeploymentError('Existing private configuration is incomplete; nothing was replaced')
            self.secret_values.append(path.read_text(encoding='utf-8').strip())
        for path in (self.root / '.env', self.private / 'memory-platform.env'):
            if path.is_file():
                self.compose.extend(['--env-file', str(path)])
        self.compose.extend(['-f', str(self.root / 'docker-compose.yml'),
                             '--profile', 'memory', '--profile', 'memory-admin'])
        self.run(self.compose + ['config', '--quiet'])
        effective = decode_json(self.run(self.compose + ['config', '--format', 'json']))
        if Path(effective['secrets']['memory_postgres']['file']).resolve() != (self.secret_dir / 'postgres_password').resolve():
            raise DeploymentError('Compose resolves a different secret directory')
        if {value.get('name') for value in effective['volumes'].values()} != set(VOLUMES):
            raise DeploymentError('Compose resolves different data volumes')
        if not self.args.fresh:
            for volume in VOLUMES:
                self.run(['docker', 'volume', 'inspect', '--format', '{{.Name}}', volume])
        existing_networks = set(self.run(['docker', 'network', 'ls', '--filter', 'name=knowledge-graphs_', '--format', '{{.Name}}']).splitlines())
        self.report['networks'] = []
        for desired in effective.get('networks', {}).values():
            if desired['name'] not in existing_networks:
                if not self.args.fresh:
                    raise DeploymentError('An expected network is missing; verify infrastructure before deployment')
                continue
            observed = decode_json(self.run(['docker', 'network', 'inspect', '--format', '{{json .}}', desired['name']]))
            self.report['networks'].append(check_network(desired, observed))
        previous = {}
        for service in SERVICES:
            ids = self.run(['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.project=knowledge-graphs',
                            '--filter', 'label=com.docker.compose.service='+service, '--format', '{{.ID}}']).splitlines()
            if len(ids) > 1:
                raise DeploymentError('Multiple containers own the same service; resolve ownership before deployment')
            if ids:
                previous[service] = self.run(['docker', 'inspect', '--format', '{{.Image}}', ids[0]])
        self.report['previous_images'] = previous
        self.step('build')
        self.run(self.compose + ['build', *SERVICES, 'memory-admin'], timeout=1800)
        self.step('database')
        self.run(self.compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '90', 'memory-postgres'])
        self.run(self.compose + ['run', '--rm', '--no-deps', '-T', 'memory-files'])
        self.step('inspect')
        counts = self.operator('inspect')['tables']
        existing = counts.get('actors', 0) > 0
        if not existing and not self.args.fresh:
            raise DeploymentError('Expected the existing database; refusing to bootstrap an empty replacement')
        before = self.operator('content-manifest') if existing else None
        self.step('backup')
        if existing:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            self.report['backup'] = self.operator('backup', '--output', f'/backups/kairos-before-{stamp}.dump')
        self.step('migrate')
        self.operator('migrate')
        self.step('bootstrap')
        if not existing:
            self.operator('bootstrap')
        after = self.operator('content-manifest')
        if before:
            compare_content(before, after)
        self.step('start')
        self.run(self.compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '90',
                                 'ollama', *SERVICES])
        self.step('verify')
        final = self.operator('content-manifest')
        if before:
            compare_content(before, final)
        self.report['verification'] = verify_runtime(final, self.secret_dir,
                                                    self.args.verify_key_file)
        self.report.update(status='complete', content_sha256=final['sha256'],
                           documents=len(final['documents']), projects=len(final['projects']))
        self.save_report()
        print('Kairos deployment verified. Report: .private/deployment-status.json')


def verify_runtime(manifest, secret_dir, key_file=None):
    """Read actual MCP tools, projects and complete paginated document manifests."""
    origin = 'http://127.0.0.1:5173'
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {'Accept': 'application/json, text/event-stream', 'Origin': origin}

    def request(path, value=None):
        data = json.dumps(value).encode() if value is not None else None
        req = urllib.request.Request(origin + path, data=data, headers=dict(headers, **({'Content-Type': 'application/json'} if data else {})))
        try:
            with client.open(req, timeout=15) as response:
                content = response.read(4_194_305)
            if len(content) > 4_194_304:
                raise DeploymentError('Runtime verification exceeded its response limit')
            return json.loads(content)
        except DeploymentError:
            raise
        except Exception:
            raise DeploymentError('Runtime verification failed; check access and service status without resending data') from None

    if key_file:
        key = safe_path(Path(key_file)).read_text(encoding='utf-8').strip()
        headers['Authorization'] = 'Bearer ' + key
    else:
        password = safe_path(secret_dir / 'bootstrap_password').read_text(encoding='utf-8').strip()
        login = request('/v1/auth/login', {'username': 'admin', 'password': password})
        headers['X-CSRF-Token'] = login['csrf_token']
    try:
        serial = 0

        def rpc(method, params):
            nonlocal serial
            serial += 1
            result = request('/mcp/', {'jsonrpc': '2.0', 'id': serial, 'method': method, 'params': params})
            if result.get('error') or 'result' not in result or result['result'].get('isError'):
                raise DeploymentError('MCP verification returned a protocol or tool error')
            return result['result']

        def call(name, arguments):
            result = rpc('tools/call', {'name': name, 'arguments': arguments})
            if 'structuredContent' in result:
                return result['structuredContent']
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    return decode_json(block['text'])
            raise DeploymentError('MCP tool returned no structured result')

        rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'kairos-deploy', 'version': '0.1.0'}})
        tools = rpc('tools/list', {})['tools']
        names = {tool['name'] for tool in tools}
        required = {'projects', 'document_manifest', 'search', 'remember', 'capture_policy', 'event_status',
                    'list_corpora', 'observation_add', 'observation_record_event', 'get_tool_uses',
                    'team_work_write', 'team_work_read', 'team_search', 'team_brief', 'corpus_answer', 'corpus_answer_status'}
        if not required.issubset(names):
            raise DeploymentError('Required native MCP tools are unavailable')
        event_tool = next(tool for tool in tools if tool['name'] == 'event_status')
        if 'project_id' not in event_tool.get('inputSchema', {}).get('properties', {}):
            raise DeploymentError('Native MCP capture reconciliation contract is unavailable')
        remember_tool=next(tool for tool in tools if tool['name']=='remember')
        context_tool=next(tool for tool in tools if tool['name']=='context')
        if 'AutomaticCapture' not in remember_tool.get('inputSchema',{}).get('$defs',{}) or 'match_mode' not in context_tool.get('inputSchema',{}).get('properties',{}):
            raise DeploymentError('Automatic capture fingerprint or context filter contract is unavailable')
        projects = call('projects', {})['projects']
        if {p['id'] for p in projects} != {p['id'] for p in manifest['projects']}:
            raise DeploymentError('Verification identity cannot read every configured project')
        actual = {}
        for project in projects:
            cursor, seen = None, set()
            for _ in range(1000):
                arguments = {'project_id': project['id'], 'limit': 100}
                if cursor:
                    arguments['cursor'] = cursor
                page = call('document_manifest', arguments)
                for row in page['items']:
                    identity = (project['id'], row['document_id'])
                    if identity in actual:
                        raise DeploymentError('MCP pagination duplicated a document')
                    actual[identity] = (row['version'], row['source_sha256'], row['deleted'])
                if not page['has_more']:
                    break
                cursor = page.get('next_cursor')
                if not cursor or cursor in seen:
                    raise DeploymentError('MCP pagination failed to advance')
                seen.add(cursor)
            else:
                raise DeploymentError('MCP verification exceeded its page limit')
        expected = {(d['project_id'], d['id']): (d['version'], d['source_sha256'], d['deleted'])
                    for d in manifest['documents']}
        if actual != expected:
            raise DeploymentError('Runtime document identities, hashes or versions differ')
        return {'transport': 'MCP HTTP', 'tools': sorted(names),
                'projects': len(projects), 'documents_verified': len(actual)}
    finally:
        if not key_file:
            request('/v1/auth/logout', {})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--fresh', action='store_true', help='Allow first installation; never replace existing secrets')
    parser.add_argument('--secret-dir', help='Existing private secret directory outside the repository')
    parser.add_argument('--verify-key-file', help='Optional existing read key for all projects, if the admin password was changed')
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({'mode': 'dry-run', 'phases': PHASES, 'fresh': args.fresh,
                          'volumes': VOLUMES, 'models': 'preserve configuration',
                          'data_removed': False}, indent=2))
        return 0
    deployment = Deployment(args)
    try:
        deployment.apply()
    except Exception as exc:
        deployment.report.update(status='failed', failed_phase=deployment.phase,
                                 error_code=type(exc).__name__,
                                 message=str(exc) if isinstance(exc, DeploymentError) else 'Unexpected failure; inspect the local phase without sharing credentials')
        if deployment.phase != 'engine':
            deployment.save_report()
        reason = str(exc) if isinstance(exc, DeploymentError) else 'Unexpected failure.'
        print(f'Kairos stopped during {deployment.phase}. {reason} No later phase was run. '
              'Inspect the current state before retrying; credentials are not printed.', file=sys.stderr)
        if deployment.report.get('command_failure'):
            print(deployment.report['command_failure']['details'], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
