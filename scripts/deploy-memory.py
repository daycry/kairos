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
DEFAULT_PROJECT = 'knowledge-graphs'
DEFAULT_API_PORT, DEFAULT_WEB_PORT = 8790, 5173
MIGRATE_TIMEOUT_SECONDS = 3600  # the first pgvector migration rewrites and indexes embeddings; the default 120 s would abort it
ISOLATED_PRIVATE_FILES = ('memory-platform.env', 'compose.override.yml', 'deployment-status.json', 'deployment-status.tmp')
VOLUMES = (DEFAULT_PROJECT + '_memory-postgres-data', DEFAULT_PROJECT + '_memory-backups')
SERVICES = ('memory-api', 'memory-worker', 'memory-web')
BACKFILL_TIMEOUT_SECONDS = 1800  # queues jobs in short transactions; the worker does the embedding after `start`
BACKFILL_REPORT_KEYS = ('status', 'reason', 'enqueued', 'derived', 'failed', 'pending', 'remaining', 'batches', 'embedding_filled', 'stale_marked')  # counts only, never anything else
PHASES = ('engine', 'configuration', 'build', 'database', 'inspect', 'backup',
          'migrate', 'bootstrap', 'backfill', 'start', 'verify')


class DeploymentError(Exception):
    pass


def validate_isolation(project, api_port, web_port):
    """The installed project keeps its fixed names and ports; any other project is an isolated rehearsal.

    An isolated project gets its own compose project name, volumes, networks, image tags, ports, private
    directory and secrets, and may not be named like (or inside) the installed project.
    """
    if project == DEFAULT_PROJECT:
        if (api_port, web_port) != (DEFAULT_API_PORT, DEFAULT_WEB_PORT):
            raise DeploymentError('--api-port and --web-port are only for an isolated --project-name')
        return
    if (not re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', project) or len(project) > 40
            or project.startswith(DEFAULT_PROJECT) or DEFAULT_PROJECT.startswith(project)):
        raise DeploymentError('Isolated --project-name must be lowercase letters, digits and hyphens, and distinct from ' + DEFAULT_PROJECT)
    ports = (api_port, web_port)
    if len(set(ports)) != 2 or any(not 1024 <= port <= 65535 or port in (DEFAULT_API_PORT, DEFAULT_WEB_PORT) for port in ports):
        raise DeploymentError('An isolated rehearsal needs two distinct ports in 1024-65535, not ' + f'{DEFAULT_API_PORT} or {DEFAULT_WEB_PORT}')


def isolated_image(project, name):
    # Always under `rehearsal-`: it can never equal an installed tag (kairos-*, knowledge-graphs-*).
    return f'rehearsal-{project}-{name}:latest'


def check_isolation_names(project, compose_text):
    """No generated image tag, volume or network may equal anything docker-compose.yml fixes for the installed project."""
    fixed = set(re.findall(r'^\s+image:\s*(\S+)', compose_text, re.M)) | set(re.findall(r'name:\s*(knowledge-graphs_\S+?)[,}\s]', compose_text))
    generated = {isolated_image(project, name) for name in ('postgres', 'api', 'worker', 'web', 'operator')}
    generated |= {project + suffix for suffix in ('_inference', '_webui', '_memory-postgres-data', '_memory-backups')}
    if fixed & generated:
        raise DeploymentError('A generated rehearsal name collides with an installed one; choose another --project-name')


def project_volumes(project):
    return (project + '_memory-postgres-data', project + '_memory-backups')


def isolation_override(project, api_port, web_port):
    """Compose override that moves one deployment away from every installed name and port."""
    image = lambda name: isolated_image(project, name)
    return f"""# Generated for the isolated project {project}; it replaces every fixed name of docker-compose.yml.
services:
  memory-postgres: {{image: {image('postgres')}}}
  memory-migrate: {{image: {image('api')}}}
  memory-bootstrap: {{image: {image('api')}}}
  memory-files: {{image: {image('api')}}}
  memory-api:
    image: {image('api')}
    ports: !override ['127.0.0.1:{api_port}:8790']
  memory-worker: {{image: {image('worker')}}}
  memory-web:
    image: {image('web')}
    ports: !override ['127.0.0.1:{web_port}:8080']
  memory-admin: {{image: {image('operator')}}}
networks:
  inference: {{name: {project}_inference}}
  webui: {{name: {project}_webui}}
volumes:
  memory-postgres-data: {{name: {project}_memory-postgres-data}}
  memory-backups: {{name: {project}_memory-backups}}
"""


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
        self.project = getattr(args, 'project_name', None) or DEFAULT_PROJECT
        self.api_port = getattr(args, 'api_port', None) or DEFAULT_API_PORT
        self.web_port = getattr(args, 'web_port', None) or DEFAULT_WEB_PORT
        validate_isolation(self.project, self.api_port, self.web_port)
        self.isolated = self.project != DEFAULT_PROJECT
        self.volumes = project_volumes(self.project)
        self.private = safe_path(root / '.private' / ('rehearsal-' + self.project) if self.isolated else root / '.private')
        if self.isolated:
            # An existing directory must be one of ours: never adopt (or write into) somebody else's .private subdirectory.
            if self.private.is_dir() and any(child.name not in ISOLATED_PRIVATE_FILES for child in self.private.iterdir()):
                raise DeploymentError('.private/rehearsal-' + self.project + ' exists and holds files this rehearsal did not create; choose another --project-name')
            # Nothing MEMORY_*/COMPOSE_*/KAIROS* of the caller's shell reaches Compose: the project's own env file decides.
            clean = {k: v for k, v in os.environ.items() if not k.upper().startswith(('MEMORY_', 'COMPOSE_', 'KAIROS'))}
            self.environment = dict(clean, MEMORY_ALLOWED_ORIGINS=f'http://127.0.0.1:{self.web_port},http://localhost:{self.web_port}')
        else:
            self.environment = None
        self.report = {'status': 'pending', 'phases': [], 'backup': None,
                       'data_removed': False, 'capture_policy_changed': False}
        self.compose = ['docker', 'compose', '-p', self.project, '--project-directory', str(root)]
        self.phase = 'engine'
        self.secret_values = []

    def run(self, command, timeout=120):
        try:
            result = subprocess.run(command, cwd=self.root, capture_output=True, env=self.environment,
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

    def operator(self, *args, timeout=120):
        return decode_json(self.run(self.compose + ['run', '--rm', '--no-deps', '-T', 'memory-admin', *args], timeout=timeout))

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
        # An isolated rehearsal never reads the installed project's .env or private configuration.
        config = {} if self.isolated else read_env(self.root / '.env')
        config.update(read_env(self.private / 'memory-platform.env'))
        configured_dir = (None if self.isolated else os.environ.get('MEMORY_SECRETS_DIR')) or config.get('MEMORY_SECRETS_DIR')
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
        if self.isolated:
            # Always an explicit --env-file: without one Compose would load the installed project's root .env.
            env_file = self.private / 'memory-platform.env'
            if not env_file.is_file():
                raise DeploymentError('The rehearsal needs its own ' + str(env_file) + ' (scripts/memory-admin.py prepare --env-output); the installed .env is never used')
            self.compose.extend(['--env-file', str(env_file)])
        else:
            for path in (self.root / '.env', self.private / 'memory-platform.env'):
                if path.is_file():
                    self.compose.extend(['--env-file', str(path)])
        self.compose.extend(['-f', str(self.root / 'docker-compose.yml')])
        if self.isolated:
            self.private.mkdir(parents=True, exist_ok=True)
            check_isolation_names(self.project, (self.root / 'docker-compose.yml').read_text(encoding='utf-8'))
            override = safe_path(self.private / 'compose.override.yml')
            override.write_text(isolation_override(self.project, self.api_port, self.web_port), encoding='utf-8')
            self.compose.extend(['-f', str(override)])
        self.compose.extend(['--profile', 'memory', '--profile', 'memory-admin'])
        self.run(self.compose + ['config', '--quiet'])
        effective = decode_json(self.run(self.compose + ['config', '--format', 'json']))
        if Path(effective['secrets']['memory_postgres']['file']).resolve() != (self.secret_dir / 'postgres_password').resolve():
            raise DeploymentError('Compose resolves a different secret directory')
        if {value.get('name') for value in effective['volumes'].values()} != set(self.volumes):
            raise DeploymentError('Compose resolves different data volumes')
        if not self.args.fresh:
            for volume in self.volumes:
                self.run(['docker', 'volume', 'inspect', '--format', '{{.Name}}', volume])
        existing_networks = set(self.run(['docker', 'network', 'ls', '--filter', 'name='+self.project+'_', '--format', '{{.Name}}']).splitlines())
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
            ids = self.run(['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.project='+self.project,
                            '--filter', 'label=com.docker.compose.service='+service, '--format', '{{.ID}}']).splitlines()
            if len(ids) > 1:
                raise DeploymentError('Multiple containers own the same service; resolve ownership before deployment')
            if ids:
                previous[service] = self.run(['docker', 'inspect', '--format', '{{.Image}}', ids[0]])
        self.report['previous_images'] = previous
        self.step('build')
        self.run(self.compose + ['build', 'memory-postgres', *SERVICES, 'memory-admin'], timeout=1800)
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
        if getattr(self.args, 'stop_services_before_migrate', False):
            # Opt-in: the migration holds ACCESS EXCLUSIVE locks until its COMMIT (docs/operations.md); the services of the
            # previous release would only queue behind them. `start` brings the services back up; if the deployment stops
            # before `start` they stay stopped.
            self.report['services_stopped_before_migrate'] = True  # before the command: a stop that fails half way may have stopped one of them
            self.run(self.compose + ['stop', '--timeout', '30', 'memory-api', 'memory-worker'])
        # The first pgvector migration rewrites embeddings and builds HNSW indexes: no 120 s abort. Recorded in the report.
        self.report['migrate_timeout_seconds'] = MIGRATE_TIMEOUT_SECONDS
        self.operator('migrate', timeout=MIGRATE_TIMEOUT_SECONDS)
        self.step('bootstrap')
        if not existing:
            self.operator('bootstrap')
        after = self.operator('content-manifest')
        if before:
            compare_content(before, after)
        # Decision P-07: fragments for the existing content are queued at deployment. Only `embed` jobs are inserted (no content table is
        # touched, so the manifest checks above and below still hold); the worker started next embeds them, bounded by its own deadline.
        self.step('backfill')
        # The memory-worker of the previous release would complete these jobs with its own `complete_job` (no fragments) and the report would
        # say there is nothing left: it stays stopped until `start` brings the new one up. Always, with or without --stop-services-before-migrate.
        self.report['worker_stopped_before_backfill'] = True  # before the command, for the same reason
        self.run(self.compose + ['stop', '--timeout', '30', 'memory-worker'])
        result = self.operator('backfill-chunks', timeout=BACKFILL_TIMEOUT_SECONDS)
        self.report['backfill'] = {key: result[key] for key in BACKFILL_REPORT_KEYS if key in result}
        self.step('start')
        self.run(self.compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '90',
                                 'ollama', *SERVICES])
        self.step('verify')
        final = self.operator('content-manifest')
        if before:
            compare_content(before, final)
        self.report['verification'] = verify_runtime(final, self.secret_dir,
                                                    self.args.verify_key_file, f'http://127.0.0.1:{self.web_port}')
        self.report.update(status='complete', content_sha256=final['sha256'],
                           documents=len(final['documents']), projects=len(final['projects']))
        self.save_report()
        print('Kairos deployment verified. Report: ' + ('.private/rehearsal-' + self.project + '/' if self.isolated else '.private/') + 'deployment-status.json')


def verify_runtime(manifest, secret_dir, key_file=None, origin='http://127.0.0.1:5173'):
    """Read actual MCP tools, projects and complete paginated document manifests."""
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


def failure_hints(report, phase):
    """Extra stderr lines for a failed deployment that leaves something in a state the operator must act on."""
    hints = []
    if report.get('services_stopped_before_migrate') and phase in ('migrate', 'bootstrap', 'backfill'):
        hints.append('memory-api and memory-worker were stopped before migrate and are still stopped; a failed migration is '
                     'rolled back. Start them again (docker compose ... start memory-api memory-worker) or retry.')
    if report.get('worker_stopped_before_backfill') and phase in ('backfill', 'start', 'verify') and not hints:  # the hint above already covers the worker
        hints.append('memory-worker was stopped before the backfill (the previous release would complete its jobs without fragments) and may still be '
                     'stopped; start it again (docker compose ... up -d memory-worker) or retry the deployment. Queued jobs stay pending meanwhile.')
    return hints


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--fresh', action='store_true', help='Allow first installation; never replace existing secrets')
    parser.add_argument('--secret-dir', help='Existing private secret directory outside the repository')
    parser.add_argument('--verify-key-file', help='Optional existing read key for all projects, if the admin password was changed')
    parser.add_argument('--project-name', default=DEFAULT_PROJECT,
                        help='Isolated rehearsal: own compose project, volumes, networks, image tags, ports and private directory (never the installed project)')
    parser.add_argument('--api-port', type=int, default=DEFAULT_API_PORT, help='Isolated rehearsal only: host port of the API')
    parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT, help='Isolated rehearsal only: host port of the portal')
    parser.add_argument('--stop-services-before-migrate', action='store_true',
                        help='Stop memory-api and memory-worker before the migrate phase (they are started again by the start phase); default: leave them running')
    args = parser.parse_args(argv)
    if not args.apply:
        try:
            validate_isolation(args.project_name, args.api_port, args.web_port)
        except DeploymentError as exc:
            parser.error(str(exc))
        print(json.dumps({'mode': 'dry-run', 'phases': PHASES, 'fresh': args.fresh, 'project': args.project_name,
                          'volumes': project_volumes(args.project_name), 'models': 'preserve configuration',
                          'data_removed': False}, indent=2))
        return 0
    try:
        deployment = Deployment(args)
    except DeploymentError as exc:
        parser.error(str(exc))
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
        for hint in failure_hints(deployment.report, deployment.phase):
            print(hint, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
