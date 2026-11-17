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
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = 'knowledge-graphs'
DEFAULT_API_PORT, DEFAULT_WEB_PORT = 8790, 5173
MIGRATE_TIMEOUT_SECONDS = 3600  # the first pgvector migration rewrites and indexes embeddings; the default 120 s would abort it
BACKUP_TIMEOUT_SECONDS = 3600  # O-03: `content-manifest`, `backup` and `verify-backup` read or dump the whole database; the default 120 s of `operator()` aborts a large one
VERIFY_WAIT_SECONDS = 90  # the ephemeral PostgreSQL of `--verify-backup` must accept connections within this
VERIFY_LABEL = 'com.kairos.verify-backup'
VERIFY_PROJECT_LABEL = 'com.kairos.project'
VERIFY_NAME_PROJECT = 24  # the longest project text in a verify container name: `kairos-verify-pg-<project>-<mark>` is a hostname and must stay within 63 characters
VERIFY_MAINTENANCE_WORK_MEM = '256MB'  # the restore rebuilds the vector indexes: the 64 MB default makes a big one slow enough to exhaust the plazo
BACKUP_TIMEOUT_MAX_SECONDS = 86400  # a timeout is a bound: 0 or "no limit" would let a stuck copy hang the deployment
EXIT_LOCKED, EXIT_NO_PREVIOUS_IMAGES, EXIT_ALREADY_AT_PREVIOUS = 3, 4, 5  # exit codes of `deployment_locked`, `no_previous_images` and `already_at_previous` (documented in docs/operations.md)
LOCK_GRACE_SECONDS = 30  # a lock file that cannot be read and is younger than this may be one that is still being written: --break-lock leaves it
LOCK_FILE = 'deployment.lock'  # in the private directory of the project: created exclusively by the deployment that runs, removed when it ends (T-61, CA-23)
ISOLATED_PRIVATE_FILES = ('memory-platform.env', 'compose.override.yml', 'deployment-status.json', 'deployment-status.tmp', LOCK_FILE)
VOLUMES = (DEFAULT_PROJECT + '_memory-postgres-data', DEFAULT_PROJECT + '_memory-backups')
SERVICES = ('memory-api', 'memory-worker', 'memory-mcp', 'memory-web')
NEW_NETWORKS = ('mcp',)  # networks that an installation made before this release does not have yet: the start creates them, a missing one is not an error
BACKFILL_TIMEOUT_SECONDS = 1800  # queues jobs in short transactions; the worker does the embedding after `start`
BACKFILL_REPORT_KEYS = ('status', 'reason', 'enqueued', 'derived', 'failed', 'pending', 'remaining', 'batches', 'embedding_filled', 'stale_marked')  # counts only, never anything else
STUB_SERVICE, STUB_PORT, STUB_DIMENSIONS = 'embed-stub', 11434, 768  # the simulated embedding provider of an isolated rehearsal (T-71, T-72); 768 = nomic-embed-text, the vector index
REHEARSAL_PROJECT_ID = 'rehearsal'
SPY_QUERY = f"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:{STUB_PORT}/__spy',timeout=5).read().decode())"
IMAGE_NAMES = ('api', 'worker', 'mcp', 'web', 'operator')  # what a deployment tags and a rollback restores; never `postgres`: the server of the data directory is not rolled back (T-62, CA-24)
ROLLBACK_SERVICES = {'api': 'memory-api', 'worker': 'memory-worker', 'mcp': 'memory-mcp', 'web': 'memory-web'}  # the containers a rollback recreates
TAGS_KEPT = 2  # the tagged images of the releases before the current one that are kept per image; the older tags are removed
TAG_MARK = re.compile(r'^[A-Za-z0-9_.]+-(\d{8}T\d{6}Z)$')  # `<version>-<mark>` of a tag this script made
PHASES = ('engine', 'configuration', 'build', 'database', 'inspect', 'backup',
          'migrate', 'bootstrap', 'backfill', 'start', 'verify')
ROLLBACK_PHASES = ('engine', 'configuration', 'rollback', 'verify')  # `--rollback`: no backup, no migrate, no bootstrap, no backfill


class DeploymentError(Exception):
    pass


class NoPreviousImages(DeploymentError):
    """`no_previous_images` (CA-24): `--rollback` has no recorded tags of an earlier release to go back to (or one of them is gone); no service was touched."""
    code = 'no_previous_images'


class AlreadyAtPrevious(DeploymentError):
    """`already_at_previous` (CA-24, fix1): the images `--rollback` would go back to are the ones every service already has in `:latest`; nothing was touched and nothing is reported as rolled back."""
    code = 'already_at_previous'


def release_version(root):
    """The version the tags carry: the one of the components (`client/package.json`), made safe for a Docker tag; `unversioned` without it."""
    try:
        version = json.loads((Path(root) / 'client' / 'package.json').read_text(encoding='utf-8')).get('version')
    except (OSError, ValueError, AttributeError):
        version = None
    return re.sub(r'[^A-Za-z0-9_.]', '_', version)[:40] if isinstance(version, str) and version else 'unversioned'


class DeploymentLocked(DeploymentError):
    """`deployment_locked` (CA-23): another deployment of the project holds the lock, or a lock is left that only `--break-lock` removes. `owner` is what the lock file says (may be empty)."""
    code = 'deployment_locked'

    def __init__(self, message, owner=None):
        super().__init__(message)
        self.owner = owner or {}


def pid_alive(pid):
    """Whether a process with this PID exists on this machine. `os.kill(pid, 0)` is the POSIX probe; on Windows it would TERMINATE the process, so the process table is asked instead."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def process_stamp(pid):
    """An identifier of THE process instance behind a PID (fix1, review of phase 10): PIDs are reused, above all after a restart. Linux: the boot id and the start time of the process
    (`/proc`); Windows: its creation time. None if the process does not exist or the platform gives no reliable value (then the PID alone decides)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        kernel.GetProcessTimes.argtypes = (ctypes.c_void_p,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            created, finished, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            code = ctypes.c_ulong()
            kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # an exited process whose handle is still open is not one
                return None
            if not kernel.GetProcessTimes(handle, created, finished, kernel_time, user_time):
                return None
            return f'nt:{(created.dwHighDateTime << 32) | created.dwLowDateTime}'
        finally:
            kernel.CloseHandle(handle)
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
        fields = Path(f'/proc/{pid}/stat').read_text(encoding='utf-8', errors='replace').rsplit(')', 1)[1].split()
        return f'{boot}:{fields[19]}'  # field 22 of /proc/<pid>/stat: the start time, in ticks since boot
    except (OSError, IndexError):
        return None


class DeployLock:
    """One deployment at a time per project (CA-23): `deployment.lock` in the private directory, created exclusively (`O_EXCL`) with the PID, host, start time, a token and the `stamp`.

    A lock that exists makes `acquire` raise `DeploymentLocked` and run nothing. If its owner is on this host and dead, the message says so; it is still not removed: only
    `break_lock` does it, and never for an owner that is alive here. A lock of another host or one that cannot be read cannot be checked: `break_lock` removes it (an unreadable
    one only after LOCK_GRACE_SECONDS: a deployment may still be writing it). The owner is the PID AND its `stamp` (`process_stamp`): a PID that another process holds now is dead
    for this purpose. Breaking is atomic: the lock is renamed to a name of its own and removed only if it still is the one that was read; otherwise it is put back (fix1).
    The lock is removed by `release` only while the file still carries this deployment's token (one that somebody else took over is not ours to delete).
    """

    def __init__(self, directory, project, break_lock=False):
        self.path = Path(directory) / LOCK_FILE
        self.project, self.break_lock = project, break_lock
        self.token = uuid.uuid4().hex
        self.held = False
        self.broken = None  # the owner of the lock this one replaced

    def owner(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def describe(self, owner):
        pid, host, started = owner.get('pid'), owner.get('host'), owner.get('started_at')
        if not owner:
            return 'a lock file exists and cannot be read'
        return f'started by PID {pid} on {host} at {started}'

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in (1, 2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                owner = self.owner()
                if attempt == 2 or not self.break_lock or not self.breakable(owner) or not self.take_over(owner):
                    raise DeploymentLocked(self.refusal(owner), owner) from None
                self.broken = owner
                continue
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump({'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                           'project': self.project, 'token': self.token, 'stamp': process_stamp(os.getpid())}, handle)
            self.held = True
            return self
        raise DeploymentLocked('the lock could not be taken')  # pragma: no cover (the loop always returns or raises)

    def take_over(self, owner):
        """Remove the lock whose content was `owner`, atomically: rename it to a name of its own and check what was renamed. True if it was that lock (or it was already gone);
        False, with the lock put back, if it was another one (somebody else broke the first and took the lock meanwhile)."""
        grabbed = self.path.with_name(f'{LOCK_FILE}.{uuid.uuid4().hex}.broken')
        try:
            os.rename(self.path, grabbed)
        except FileNotFoundError:
            return True
        try:
            try:
                value = json.loads(grabbed.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                value = {}
            if value == owner:
                return True
            try:
                os.link(grabbed, self.path)  # the lock that was not the one read: back where it was (fails if a newer one is there: that one wins)
            except OSError:
                pass
            return False
        finally:
            grabbed.unlink(missing_ok=True)

    def local(self, owner):
        return bool(owner) and owner.get('host') == socket.gethostname() and isinstance(owner.get('pid'), int)

    def running(self, owner):
        """The owner is a process of this host that is alive AND is the one that took the lock (same `stamp`; a lock without one, made by an earlier version, is judged by the PID)."""
        if not (self.local(owner) and pid_alive(owner['pid'])):
            return False
        stamp = owner.get('stamp')
        return not (isinstance(stamp, str) and process_stamp(owner['pid']) not in (None, stamp))

    def recent_unreadable(self, owner):
        if owner:
            return False
        try:
            return time.time() - self.path.stat().st_mtime < LOCK_GRACE_SECONDS
        except OSError:
            return False

    def breakable(self, owner):
        return not self.running(owner) and not self.recent_unreadable(owner)

    def refusal(self, owner):
        head = f'the project {self.project} is locked by a deployment {self.describe(owner)} (lock file {self.path}); no phase was run.'
        if self.local(owner):
            if self.running(owner):
                return head + (' That deployment is still running here' + ('; --break-lock does not break the lock of a process that is alive: wait for it to end. '
                               f"If PID {owner['pid']} is not a deployment (a lock of an older version, after a restart), delete the lock file by hand." if self.break_lock else '.'))
            return head + f" The owner process (PID {owner['pid']}) is not running: if that deployment was killed, check the state of the services and remove the lock with --break-lock."
        if owner:
            return head + ' That host is not this one, so its process cannot be checked here; if it is gone, remove the lock with --break-lock.'
        if self.recent_unreadable(owner):
            return head + f' It was written a moment ago (less than {LOCK_GRACE_SECONDS} s): a deployment may still be writing it; try again in a moment.'
        return head + ' If no deployment is running, remove the lock with --break-lock.'

    def release(self):
        if not self.held:
            return
        self.held = False
        if self.owner().get('token') == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
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


def check_backup_timeout(value):
    """`--backup-timeout` in seconds: None is the default; otherwise a whole number between 1 and a day (never 0 or unbounded)."""
    if value is None:
        return BACKUP_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= BACKUP_TIMEOUT_MAX_SECONDS:
        raise DeploymentError(f'--backup-timeout must be a whole number of seconds between 1 and {BACKUP_TIMEOUT_MAX_SECONDS}')
    return value


def verify_name_part(project):
    """The project as it appears in the names of the ephemeral verification objects: whole if short, else its start plus a short hash of the whole (names stay unique per project)."""
    if len(project) <= VERIFY_NAME_PROJECT:
        return project
    return project[:VERIFY_NAME_PROJECT - 9] + '-' + hashlib.sha256(project.encode('utf-8')).hexdigest()[:8]


def isolated_image(project, name):
    # Always under `rehearsal-`: it can never equal an installed tag (kairos-*, knowledge-graphs-*).
    return f'rehearsal-{project}-{name}:latest'


def check_isolation_names(project, compose_text):
    """No generated image tag, volume or network may equal anything docker-compose.yml fixes for the installed project."""
    fixed = set(re.findall(r'^\s+image:\s*(\S+)', compose_text, re.M)) | set(re.findall(r'name:\s*(knowledge-graphs_\S+?)[,}\s]', compose_text))
    generated = {isolated_image(project, name) for name in ('postgres', 'api', 'worker', 'web', 'operator', 'mcp')}
    generated |= {project + suffix for suffix in ('_inference', '_webui', '_mcp', '_memory-postgres-data', '_memory-backups')}
    if fixed & generated:
        raise DeploymentError('A generated rehearsal name collides with an installed one; choose another --project-name')


def project_volumes(project):
    return (project + '_memory-postgres-data', project + '_memory-backups')


def embed_stub_services(project):
    """Services of the simulated embedding provider: the `api` image running `memory_platform.tests.llm_spy` on the networks the proxy `ollama` uses.

    `ollama` (the allow-list proxy) forwards to it instead of the Ollama of the host, and `/api/chat` is let through the proxy (`OLLAMA_ALLOW_CHAT=1`, set by
    the deployment) so that a language-model call would reach the stub, be refused with a 500 and be counted instead of being hidden by the proxy's own 403.
    """
    return f"""  {STUB_SERVICE}:
    image: {isolated_image(project, 'api')}
    pull_policy: never
    entrypoint: [python, -m, memory_platform.tests.llm_spy, --serve, '0.0.0.0:{STUB_PORT}', --dimensions, '{STUB_DIMENSIONS}']
    user: '10001:10001'
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    networks: [inference, egress]
    healthcheck:
      test: [CMD, python, -c, "import urllib.request;urllib.request.urlopen('http://127.0.0.1:{STUB_PORT}/api/version',timeout=4)"]
      interval: 5s
      timeout: 6s
      retries: 12
  ollama:
    depends_on:
      {STUB_SERVICE}: {{condition: service_healthy}}
"""


def isolation_override(project, api_port, web_port, embed_stub=False):
    """Compose override that moves one deployment away from every installed name and port."""
    image = lambda name: isolated_image(project, name)
    stub = embed_stub_services(project) if embed_stub else ''
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
  memory-mcp: {{image: {image('mcp')}}}
  memory-web:
    image: {image('web')}
    ports: !override ['127.0.0.1:{web_port}:8080']
  memory-admin: {{image: {image('operator')}}}
  memory-backup: {{image: {image('operator')}}}
{stub}networks:
  inference: {{name: {project}_inference}}
  webui: {{name: {project}_webui}}
  mcp: {{name: {project}_mcp}}
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
        self.embed_stub = bool(getattr(args, 'embed_stub', False))
        self.roundtrip = bool(getattr(args, 'roundtrip', False))
        if (self.embed_stub or self.roundtrip) and not self.isolated:
            raise DeploymentError('--embed-stub and --roundtrip are only for an isolated --project-name: the installed project keeps its own embedding provider')
        if self.roundtrip and not self.embed_stub:
            raise DeploymentError('--roundtrip needs --embed-stub: the rehearsal must prove that no language model was asked for')
        self.backup_timeout = check_backup_timeout(getattr(args, 'backup_timeout', None))
        requested = getattr(args, 'verify_backup', None)
        self.verify_backup = self.isolated if requested is None else bool(requested)  # on by default in a rehearsal, opt-in for the installed project
        self.volumes = project_volumes(self.project)
        self.private = safe_path(root / '.private' / ('rehearsal-' + self.project) if self.isolated else root / '.private')
        if self.isolated:
            # An existing directory must be one of ours: never adopt (or write into) somebody else's .private subdirectory.
            if self.private.is_dir() and any(child.name not in ISOLATED_PRIVATE_FILES for child in self.private.iterdir()):
                raise DeploymentError('.private/rehearsal-' + self.project + ' exists and holds files this rehearsal did not create; choose another --project-name')
            # Nothing MEMORY_*/COMPOSE_*/KAIROS* of the caller's shell reaches Compose: the project's own env file decides.
            clean = {k: v for k, v in os.environ.items() if not k.upper().startswith(('MEMORY_', 'COMPOSE_', 'KAIROS'))}
            self.environment = dict(clean, MEMORY_ALLOWED_ORIGINS=f'http://127.0.0.1:{self.web_port},http://localhost:{self.web_port}')
            if self.embed_stub:
                # Never the Ollama of the host: the proxy of the project points at the stub of the project, and lets chat through so the stub can count it.
                self.environment.update(OLLAMA_UPSTREAM=f'{STUB_SERVICE}:{STUB_PORT}', OLLAMA_ALLOW_CHAT='1')
        else:
            self.environment = None
        self.report = {'status': 'pending', 'phases': [], 'backup': None,
                       'data_removed': False, 'capture_policy_changed': False}
        self.compose = ['docker', 'compose', '-p', self.project, '--project-directory', str(root)]
        self.phase = 'engine'
        self.secret_values = []
        recorded = self.load_status().get('images')  # the tags of the earlier releases outlive a deployment that stops before it tags again: a rollback still finds them
        if recorded:
            self.report['images'] = recorded

    def run(self, command, timeout=120, extra_env=None):
        """Run `command`; `extra_env` adds variables to ITS environment only (a secret that a `-e NAME` of docker takes from there, never from the argument list)."""
        environment = self.environment if not extra_env else dict(os.environ if self.environment is None else self.environment, **extra_env)
        try:
            result = subprocess.run(command, cwd=self.root, capture_output=True, env=environment,
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

    def operator(self, *args, timeout=120, name=None):
        """One `memory-admin` command. A command with a `name` runs in a container of that name, which is stopped and removed if the command fails or times out: the client that
        `subprocess` kills at the timeout is not the container, and a dump that kept running would leave a copy half written (the SIGTERM of `docker stop` makes the dump clean up)."""
        command = self.compose + ['run', '--rm', '--no-deps', '-T'] + (['--name', name] if name else []) + ['memory-admin', *args]
        try:
            return decode_json(self.run(command, timeout=timeout))
        except BaseException:
            if name:
                self.reap(name)
            raise

    def reap(self, name):
        """Stop (SIGTERM first, so the command removes what it had half written) and remove the container `name`; nothing here may hide the error that is propagating."""
        for command, wait in ((['docker', 'stop', '--time', '20', name], 60), (['docker', 'rm', '--force', '--volumes', name], 60)):
            try:
                subprocess.run(command, capture_output=True, env=self.environment, timeout=wait)
            except Exception:
                pass
        self.report.setdefault('reaped_containers', []).append(name)

    def image(self, name):
        """The image of a service of this project: the rehearsal's own tag, or the one docker-compose.yml fixes for the installed project."""
        return isolated_image(self.project, name) if self.isolated else f'kairos-{name}:latest'

    def image_repo(self, name):
        """The repository of that image without its tag: the tags `<version>-<mark>` live under it. An isolated project is always under `rehearsal-<project>-`, so it can never equal an installed name."""
        return self.image(name).rsplit(':', 1)[0]

    def probe(self, command, timeout=60):
        """The output of a read-only command, or None if it failed; a failure never becomes `command_failure` of the report nor replaces the error being raised."""
        kept = self.report.get('command_failure')
        try:
            return self.run(command, timeout=timeout) or None
        except DeploymentError:
            return None
        finally:
            if kept is None:
                self.report.pop('command_failure', None)
            else:
                self.report['command_failure'] = kept

    def load_status(self):
        try:
            value = json.loads(safe_path(self.private / 'deployment-status.json').read_text(encoding='utf-8'))
        except (OSError, ValueError, DeploymentError):
            return {}
        return value if isinstance(value, dict) else {}

    def tags_of(self, name):
        """The tags `<version>-<mark>` of this image, newest mark first."""
        listed = self.probe(['docker', 'image', 'ls', self.image_repo(name), '--format', '{{.Tag}}']) or ''
        found = [(match.group(1), tag) for tag in listed.split() for match in [TAG_MARK.match(tag)] if match]
        return [tag for _, tag in sorted(found, reverse=True)]

    def image_to_tag(self, name, status):
        """The id of the image that is IN USE for `name`, or None. A service is in use by its CONTAINER (`previous_images`, read in `apply` before anything changes): `:latest` may already be
        the release of a deployment that failed after its build and never ran (fix1, review of phase 10). A service without a container is not tagged (a first installation, or one that
        never had it). `operator` has no long-running container (`memory-admin` runs one command and goes): its `:latest` is used only if the last deployment ended well (or there is no
        record), otherwise it is not tagged, and a rollback leaves it where it is (the operator of the newer release works on the migrated database)."""
        service = ROLLBACK_SERVICES.get(name)
        if service:
            served = (self.report.get('previous_images') or {}).get(service)
            return served if isinstance(served, str) and served else None
        if status in (None, 'complete', 'rolled_back'):
            return self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', self.image(name)])
        return None

    def tag_previous_images(self):
        """T-62 (CA-24, O-06): before the build replaces `:latest`, the images in use are tagged `<repository>:<version>-<mark>` so that `--rollback` has something to go back to.

        The images in use are those of the containers (`image_to_tag`), not `:latest`. The tags of the TAGS_KEPT newest marks stay per image and the older ones are removed (only the tag:
        an image a container uses is never deleted). An image that is the same as the newest tag is not tagged again (a deployment that stopped and is retried does not use up the kept
        tags on one release). The version in the tag is the one of the deployment that BUILT that image when the record of the last deployment says so (`current` and `current_versions`);
        an image that cannot be traced to it gets the version of the code that tags it, which may be newer than the image (the mark is the reliable order). The report records `previous`
        (the tags of this deployment), `kept`, and, after the build, `current` (the image ids now in `:latest`) and `current_versions`. `current` is NOT tagged: it gets its tag
        when the next deployment tags it as `previous`.
        """
        version, mark = release_version(self.root), datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        status = self.load_status().get('status')
        recorded = self.report.get('images') if isinstance(self.report.get('images'), dict) else {}
        built_ids, built_versions = recorded.get('current'), recorded.get('current_versions')
        built_ids, built_versions = built_ids if isinstance(built_ids, dict) else {}, built_versions if isinstance(built_versions, dict) else {}
        previous, kept = {}, {}
        for name in IMAGE_NAMES:
            image_id = self.image_to_tag(name, status)
            if not image_id:
                continue  # a first deployment, or an installation that predates this image: nothing to go back to
            tag_version = built_versions.get(name) if built_ids.get(name) == image_id else None
            if not (isinstance(tag_version, str) and re.fullmatch(r'[A-Za-z0-9_.]+', tag_version)):
                tag_version = version
            newest = (self.tags_of(name) or [None])[0]
            if newest and self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', f'{self.image_repo(name)}:{newest}']) == image_id:
                previous[name] = f'{self.image_repo(name)}:{newest}'
            else:
                previous[name] = f'{self.image_repo(name)}:{tag_version}-{mark}'
                self.run(['docker', 'tag', image_id, previous[name]])
            kept[name] = []
            for number, tag in enumerate(self.tags_of(name)):
                if number < TAGS_KEPT:
                    kept[name].append(f'{self.image_repo(name)}:{tag}')
                else:
                    self.quietly(['docker', 'image', 'rm', f'{self.image_repo(name)}:{tag}'])
        self.report['images'] = {'version': version, 'mark': mark, 'previous': previous, 'kept': kept, 'current': {}, 'current_versions': {}}

    def record_current_images(self):
        images = self.report.setdefault('images', {'previous': {}})
        current, versions = images.setdefault('current', {}), images.setdefault('current_versions', {})
        for name in IMAGE_NAMES:
            image_id = self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', self.image(name)])
            if image_id:
                current[name], versions[name] = image_id, release_version(self.root)

    def quietly(self, command, timeout=60):
        """Run a clean-up or probe command: True if it succeeded (or what it removes was not there), False if not; a failure never becomes `command_failure` of the report nor replaces the error being raised."""
        kept = self.report.get('command_failure')
        try:
            self.run(command, timeout=timeout)
            return True
        except DeploymentError:
            details = (self.report.get('command_failure') or {}).get('details', '').lower()
            return 'no such' in details or 'not found' in details  # removing what is not there is not a failure
        finally:
            if kept is None:
                self.report.pop('command_failure', None)
            else:
                self.report['command_failure'] = kept

    def verify_backup_phase(self, copy):
        """CA-05 (O-02): the copy just made is checked and, if it is not encrypted, restored into an EPHEMERAL PostgreSQL before `migrate`.

        The sha256 against the manifest first (`verify-backup`). Then, on a network of its own (internal: no route out, no published port), a container of the project's postgres image
        with a database `memory_restore_<mark>`, where a throw-away operator container restores the copy (read-only mount of the project's backups volume) and compares the tables
        with the manifest (`restore-check --from-manifest`: the live database is not read, let alone written). Whatever was created is removed, and the report keeps the result and
        the duration. An encrypted copy is verified without decrypting (its key is never on this host) and reported as `integrity_only`.
        Nothing here uses the project's own database. Names and labels carry the project and the mark (`kairos-verify-<project>-<mark>`).

        The ephemeral PostgreSQL holds the restored data in the clear, so it gets a password drawn for this run (given to docker through the environment, never in an argument or
        in the report), no capability, no privilege escalation and the unprivileged `postgres` user; its only door is the internal network.
        """
        started = time.monotonic()
        mark = uuid.uuid4().hex[:12]
        result = self.report['verify_backup'] = {'status': 'running', 'backup': copy.get('path')}
        tag = f'{verify_name_part(self.project)}-{mark}'  # the labels carry the whole project; only the names (a hostname among them) are shortened
        net, database_container, restore_container = f'kairos-verify-{tag}', f'kairos-verify-pg-{tag}', f'kairos-verify-op-{tag}'
        database = 'memory_restore_' + mark
        labels = ['--label', f'{VERIFY_LABEL}={mark}', '--label', f'{VERIFY_PROJECT_LABEL}={self.project}']
        password = secrets.token_urlsafe(24)
        self.secret_values.append(password)
        secret_env = {'POSTGRES_PASSWORD': password, 'PGPASSWORD': password, 'TARGET_PASSWORD': password}
        created = []  # (name, remover) of everything this phase created, in order: only that is removed and only that can be reported as left over
        try:
            integrity = self.long_operator('verify-backup', '--backup', copy['path'])
            if integrity.get('status') != 'verified':
                raise DeploymentError('The copy was not verified against its manifest')
            if integrity.get('encrypted'):
                result.update(status='integrity_only', restore='skipped', reason='encrypted copy: it is verified without decrypting; its private key is never on this host')
                return
            result['database'] = database
            self.run(['docker', 'network', 'create', '--internal', *labels, net])
            created.append((net, ['docker', 'network', 'rm', net]))
            created.append((database_container, ['docker', 'rm', '--force', '--volumes', database_container]))  # registered first: a start that failed half way may have made it
            self.run(['docker', 'run', '--detach', '--name', database_container, '--network', net, *labels, '--init', '--user', 'postgres', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges:true', '-e', 'POSTGRES_PASSWORD', self.image('postgres'), '-c', f'maintenance_work_mem={VERIFY_MAINTENANCE_WORK_MEM}'],
                     timeout=120, extra_env=secret_env)
            deadline = time.monotonic() + VERIFY_WAIT_SECONDS
            while not self.quietly(['docker', 'exec', database_container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], timeout=15):
                if time.monotonic() > deadline:
                    raise DeploymentError(f'The ephemeral PostgreSQL did not accept connections in {VERIFY_WAIT_SECONDS} s')
                time.sleep(2)
            self.run(['docker', 'exec', '-e', 'PGPASSWORD', database_container, 'psql', '-h', '127.0.0.1', '-U', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', f'CREATE DATABASE {database}'],
                     extra_env=secret_env)
            created.append((restore_container, ['docker', 'rm', '--force', '--volumes', restore_container]))
            command = ['docker', 'run', '--rm', '--name', restore_container, '--network', net, *labels, '--init', '--entrypoint', 'sh', '-v', f'{self.volumes[1]}:/backups:ro',
                       '-e', 'MEMORY_DSN=postgresql://unused@127.0.0.1:1/unused', '-e', f'TARGET_HOST={database_container}', '-e', f'TARGET_DATABASE={database}', '-e', 'TARGET_PASSWORD',
                       '-e', 'BACKUP=' + copy['path'], self.image('operator'), '-c',
                       'printf "postgresql://postgres:%s@%s:5432/%s" "$TARGET_PASSWORD" "$TARGET_HOST" "$TARGET_DATABASE" > /tmp/target.dsn '
                       '&& exec python -m memory_platform.admin restore-check --backup "$BACKUP" --target-dsn-file /tmp/target.dsn --from-manifest']
            restored = decode_json(self.run(command, timeout=self.backup_timeout, extra_env=secret_env))
            if restored.get('status') != 'restored_and_content_verified':
                raise DeploymentError('The copy did not restore to the content its manifest records')
            result.update(status='verified', tables=len(restored.get('tables', {})))
        except BaseException:
            result['status'] = 'failed'
            raise
        finally:
            result['duration_seconds'] = round(time.monotonic() - started, 2)
            if created:
                gone = [(name, self.quietly(command)) for name, command in reversed(created)]  # the container that uses the network goes before the network
                result['cleanup'] = 'complete' if all(ok for name, ok in gone) else 'incomplete: remove ' + ', '.join(name for name, ok in gone if not ok) + ' by hand'
                if not all(ok for name, ok in gone):
                    print('WARNING: ' + result['cleanup'], file=sys.stderr)
            elif result.get('database'):
                result['cleanup'] = 'complete'  # nothing had been created yet, so nothing is left

    def long_operator(self, verb, *args):
        """A command that reads or dumps the whole database: the `--backup-timeout`, in a container that is reaped on failure."""
        return self.operator(verb, *args, timeout=self.backup_timeout, name=f'kairos-deploy-{verb}-{uuid.uuid4().hex[:10]}')

    def spy_report(self):
        report = decode_json(self.run(self.compose + ['exec', '-T', STUB_SERVICE, 'python', '-c', SPY_QUERY]))
        if set(report) != {'chat_calls', 'embed_calls', 'requests'}:
            raise DeploymentError('The embedding stub returned an unexpected report')
        return report

    def check_no_language_model(self):
        """The oracle of CA-18 over the running stack: whatever the services did, the stub saw no `/api/chat` or `/api/generate` call."""
        report = self.spy_report()
        if report['chat_calls']:
            raise DeploymentError(f"The server asked a language model {report['chat_calls']} time(s); there must be none")
        print(f"PASS no language model: chat calls {report['chat_calls']}; embed calls {report['embed_calls']}", flush=True)
        return report

    def run_roundtrip(self):
        """CLI -> memory-web (`/mcp/`) -> kairos-mcp -> `/v1` -> PostgreSQL, then the worker and the stub: write one observation and find it by search (T-72, CA-31)."""
        password = safe_path(self.secret_dir / 'bootstrap_password').read_text(encoding='utf-8').strip()
        origin = f'http://127.0.0.1:{self.web_port}'
        before = self.spy_report()
        result = roundtrip(origin, password, self.private, self.root, warnings=self.report.setdefault('warnings', []))
        after = self.spy_report()
        if after['chat_calls']:
            raise DeploymentError(f"The server asked a language model {after['chat_calls']} time(s) during the round trip; there must be none")
        if after['embed_calls'] <= before['embed_calls']:
            raise DeploymentError('The worker never asked the simulated provider for the vector of the observation')
        result.update(chat_calls=after['chat_calls'], embed_calls=after['embed_calls'])
        print('PASS roundtrip: ' + json.dumps(result, sort_keys=True), flush=True)
        return result

    def save_report(self):
        self.private.mkdir(parents=True, exist_ok=True)
        destination = safe_path(self.private / 'deployment-status.json')
        temporary = safe_path(self.private / 'deployment-status.tmp')
        temporary.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')
        temporary.replace(destination)

    def prepare(self):
        """The `configuration` phase, shared by `apply` and `rollback`: the project's own configuration, secrets and compose files, and what Compose resolves from them."""
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
            override.write_text(isolation_override(self.project, self.api_port, self.web_port, self.embed_stub), encoding='utf-8')
            self.compose.extend(['-f', str(override)])
        self.compose.extend(['--profile', 'memory', '--profile', 'memory-admin'])
        self.run(self.compose + ['config', '--quiet'])
        effective = decode_json(self.run(self.compose + ['config', '--format', 'json']))
        if Path(effective['secrets']['memory_postgres']['file']).resolve() != (self.secret_dir / 'postgres_password').resolve():
            raise DeploymentError('Compose resolves a different secret directory')
        if {value.get('name') for value in effective['volumes'].values()} != set(self.volumes):
            raise DeploymentError('Compose resolves different data volumes')
        return effective

    def invalid_previous(self, previous):
        """What is wrong with `images.previous`: a key that is not one of IMAGE_NAMES (never `postgres`), or a tag that is not exactly `<image_repo(key)>:<version>-<mark>`."""
        problems = []
        for name, tag in previous.items():
            if name not in IMAGE_NAMES:
                problems.append(f'unknown image {str(name)[:40]!r}')
            elif not (isinstance(tag, str) and re.fullmatch(re.escape(self.image_repo(name)) + r':[A-Za-z0-9_.]+-\d{8}T\d{6}Z', tag)):
                problems.append(f'{name}: {str(tag)[:80]!r}')
        return problems

    def rollback(self):
        """`--rollback` (T-63, CA-24, O-06): the services go back to the images tagged by the previous deployment, WITHOUT migrating: no backup, no `migrate`, no bootstrap, no backfill, no data touched.

        It relies on the migrations being additive (the code of the previous release works on the migrated database: docs/operations.md). Without recorded tags (or if one is gone) it ends with
        `no_previous_images` before any service, image or volume is touched. The images are put back in `:latest` and only the services of the four tagged images are recreated, with
        `--no-deps --no-build`; the content manifest is read before and after and must be equal; the runtime check (and the round trip with `--roundtrip`) closes it.
        """
        recorded = self.report.get('images')
        previous = recorded.get('previous') if isinstance(recorded, dict) else None
        if not isinstance(previous, dict) or not previous:
            raise NoPreviousImages('no previous images are recorded for this project (deployment-status.json has no tags of an earlier release): there is nothing to go back to; no service was changed')
        invalid = self.invalid_previous(previous)
        if invalid:  # the file is data on disk: only `<repository of that image>:<version>-<mark>` of the images of a deployment is ever retagged to :latest
            raise NoPreviousImages('the recorded previous images are not tags this script makes (' + '; '.join(invalid) + '): refusing to use them; no service was changed')
        self.report['phases'] = []
        self.step('engine')
        self.run(['docker', 'version', '--format', '{{.Server.Version}}'])
        self.run(['docker', 'compose', 'version', '--short'])
        self.prepare()
        self.step('rollback')
        target = {name: self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag]) for name, tag in previous.items()}
        gone = [previous[name] for name, image_id in target.items() if not image_id]
        if gone:
            raise NoPreviousImages('the recorded images are no longer here: ' + ', '.join(gone) + '; no service was changed')
        running = {name: self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', self.image(name)]) for name in previous}
        if running == target:  # what a rollback would put in :latest is already there: it would only report a rollback that did not happen (fix1)
            raise AlreadyAtPrevious('the images of the previous deployment (' + ', '.join(previous.values()) + ') are already the ones in use: there is nothing to go back to; no service was changed')
        before = self.long_operator('content-manifest')
        self.report['rollback'] = {'from': running, 'to': dict(previous), 'migrated': False}
        for name, tag in previous.items():
            self.run(['docker', 'tag', tag, self.image(name)])
        services = [ROLLBACK_SERVICES[name] for name in ROLLBACK_SERVICES if name in previous]
        if services:
            self.run(self.compose + ['up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '90', *services])
        self.step('verify')
        final = self.long_operator('content-manifest')
        compare_content(before, final)
        self.report['verification'] = verify_runtime(final, self.secret_dir, self.args.verify_key_file, f'http://127.0.0.1:{self.web_port}', self.report.setdefault('warnings', []))
        if self.roundtrip:
            self.step('roundtrip')
            self.report['roundtrip'] = self.run_roundtrip()
        if self.embed_stub:
            self.report['model_calls'] = self.check_no_language_model()
        self.report['images']['current'] = {name: self.probe(['docker', 'image', 'inspect', '--format', '{{.Id}}', self.image(name)]) for name in previous}
        self.report['images']['current_versions'] = {name: tag.rsplit(':', 1)[1].rsplit('-', 1)[0] for name, tag in previous.items()}
        self.report.update(status='rolled_back', content_sha256=final['sha256'], documents=len(final['documents']), projects=len(final['projects']))
        self.save_report()
        print('Kairos rolled back to the images ' + ', '.join(previous.values()) + '; nothing was migrated. ' + verified_message(self.report['verification']) + ' Report: '
              + ('.private/rehearsal-' + self.project + '/' if self.isolated else '.private/') + 'deployment-status.json')

    def apply(self):
        self.step('engine')
        self.run(['docker', 'version', '--format', '{{.Server.Version}}'])
        self.run(['docker', 'compose', 'version', '--short'])
        # No secret creation, image build or service change precedes this check.
        effective = self.prepare()
        if not self.args.fresh:
            for volume in self.volumes:
                self.run(['docker', 'volume', 'inspect', '--format', '{{.Name}}', volume])
        existing_networks = set(self.run(['docker', 'network', 'ls', '--filter', 'name='+self.project+'_', '--format', '{{.Name}}']).splitlines())
        self.report['networks'] = []
        for desired in effective.get('networks', {}).values():
            if desired['name'] not in existing_networks:
                if not self.args.fresh and desired['name'] not in {self.project + '_' + name for name in NEW_NETWORKS}:
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
        self.tag_previous_images()
        self.run(self.compose + ['build', 'memory-postgres', *SERVICES, 'memory-admin'], timeout=1800)
        self.record_current_images()
        self.step('database')
        self.run(self.compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '90', 'memory-postgres'])
        self.run(self.compose + ['run', '--rm', '--no-deps', '-T', 'memory-files'])
        self.step('inspect')
        counts = self.operator('inspect')['tables']
        existing = counts.get('actors', 0) > 0
        if not existing and not self.args.fresh:
            raise DeploymentError('Expected the existing database; refusing to bootstrap an empty replacement')
        self.report['backup_timeout_seconds'] = self.backup_timeout
        before = self.long_operator('content-manifest') if existing else None
        self.step('backup')
        if existing:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            self.report['backup'] = self.long_operator('backup', '--output', f'/backups/kairos-before-{stamp}.dump')
            if self.verify_backup:
                self.step('verify_backup')
                self.verify_backup_phase(self.report['backup'])
                print(f"PASS verify-backup: {self.report['verify_backup']['status']} in {self.report['verify_backup']['duration_seconds']} s", flush=True)
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
        after = self.long_operator('content-manifest')
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
                                 *((STUB_SERVICE,) if self.embed_stub else ()), 'ollama', *SERVICES])
        self.step('verify')
        final = self.long_operator('content-manifest')
        if before:
            compare_content(before, final)
        self.report['verification'] = verify_runtime(final, self.secret_dir,
                                                    self.args.verify_key_file, f'http://127.0.0.1:{self.web_port}',
                                                    self.report.setdefault('warnings', []))
        if self.roundtrip:
            self.step('roundtrip')
            self.report['roundtrip'] = self.run_roundtrip()
        if self.embed_stub:
            self.report['model_calls'] = self.check_no_language_model()
        self.report.update(status='complete', content_sha256=final['sha256'],
                           documents=len(final['documents']), projects=len(final['projects']))
        self.save_report()
        print(verified_message(self.report['verification']) + ' Report: ' + ('.private/rehearsal-' + self.project + '/' if self.isolated else '.private/') + 'deployment-status.json')


class Portal:
    """The web entry as a browser or a client uses it: HTTP to the published port, a session cookie with its CSRF token, or a Bearer for `/mcp/`."""

    def __init__(self, origin):
        self.origin = origin
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.headers = {'Accept': 'application/json, text/event-stream', 'Origin': origin}

    def exchange(self, path, value=None, method=None, bearer=None, host=None):
        """(status, body) of one request; an HTTP error status is an answer here, not an exception."""
        data = json.dumps(value).encode() if value is not None else None
        headers = dict(self.headers, **({'Content-Type': 'application/json'} if data else {}))
        if bearer:
            headers['Authorization'] = 'Bearer ' + bearer
        if host:
            headers['Host'] = host
        request = urllib.request.Request(self.origin + path, data=data, headers=headers, method=method)
        try:
            with self.client.open(request, timeout=15) as response:
                status, content = response.status, response.read(4_194_305)
        except urllib.error.HTTPError as error:
            status, content = error.code, error.read(4_194_305)
        if len(content) > 4_194_304:
            raise DeploymentError('Runtime verification exceeded its response limit')
        return status, content

    def request(self, path, value=None, method=None, bearer=None, host=None):
        try:
            status, content = self.exchange(path, value, method, bearer, host)
            if status >= 400:
                raise ValueError(status)
            return json.loads(content) if content else {}
        except DeploymentError:
            raise
        except Exception:
            raise DeploymentError('Runtime verification failed; check access and service status without resending data') from None

    def login(self, password):
        self.headers['X-CSRF-Token'] = self.request('/v1/auth/login', {'username': 'admin', 'password': password})['csrf_token']

    def logout(self):
        self.request('/v1/auth/logout', {})


def verified_message(verification):
    """Console line of a finished deployment: a skipped `/mcp/` check is said, not hidden behind a plain success."""
    if not verification.get('mcp_checked', True):
        return 'Kairos deployment verified; /mcp not checked: the installation has no projects.'
    if verification.get('projects_not_checked'):
        return f"Kairos deployment verified; /mcp not checked for {verification['projects_not_checked']} projects (a temporary key names at most {MAX_KEY_PROJECTS})."
    return 'Kairos deployment verified.'


MAX_KEY_PROJECTS = 100  # `KeyInput.project_ids` of the server


def revoke_key(portal, key_id, name, warnings):
    """Revoke a temporary key without hiding the error that is already propagating: a failure is a warning (report and stderr) with the way to revoke it by hand. Never the token."""
    try:
        portal.request('/v1/keys/' + key_id, method='DELETE')
    except Exception:
        warning = {'code': 'temporary_key_not_revoked', 'key_id': key_id, 'key_name': name,
                   'action': f'The temporary key {name} (id {key_id}) is still active; revoke it by hand: DELETE /v1/keys/{key_id} with an admin session, or the portal key list.'}
        if warnings is not None:
            warnings.append(warning)
        print('WARNING: ' + warning['action'], file=sys.stderr)
        return warning
    return None


def verify_runtime(manifest, secret_dir, key_file=None, origin='http://127.0.0.1:5173', warnings=None):
    """Read actual MCP tools, projects and complete paginated document manifests.

    `/mcp/` of the web entry is kairos-mcp, which takes a Bearer and never the portal cookie: with a session login the check first creates a read key
    for the projects of the manifest (at most 100, what a key can name; the rest is reported as not checked) and revokes it at the end, also when the check fails.
    """
    portal = Portal(origin)
    request = portal.request
    bearer, temporary_key, key_name, granted, result = None, None, None, None, None
    if key_file:
        bearer = safe_path(Path(key_file)).read_text(encoding='utf-8').strip()
    else:
        portal.login(safe_path(secret_dir / 'bootstrap_password').read_text(encoding='utf-8').strip())
        if not manifest['projects']:
            # A key needs at least one project to be granted on, and an installation without projects has nothing to read: the `/mcp/` check is not possible (and is reported as such).
            portal.logout()
            return {'transport': 'MCP HTTP', 'tools': [], 'projects': 0, 'documents_verified': 0, 'mcp_checked': False, 'reason': 'the installation has no project to authorize a key on'}
    try:
        if not key_file:
            granted = sorted(p['id'] for p in manifest['projects'])[:MAX_KEY_PROJECTS]
            key_name = 'deployment-verify-' + uuid.uuid4().hex[:8]
            created = request('/v1/keys', {'name': key_name, 'project_ids': granted, 'scopes': ['read']})
            temporary_key = created['id']  # before the token: from here on the key has to be revoked
            bearer = created['token']
        serial = 0

        def rpc(method, params):
            nonlocal serial
            serial += 1
            result = request('/mcp/', {'jsonrpc': '2.0', 'id': serial, 'method': method, 'params': params}, bearer=bearer)
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
        expected_ids = {p['id'] for p in manifest['projects']} if granted is None else set(granted)
        if {p['id'] for p in projects} != expected_ids:
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
                    for d in manifest['documents'] if granted is None or d['project_id'] in expected_ids}
        if actual != expected:
            raise DeploymentError('Runtime document identities, hashes or versions differ')
        result = {'transport': 'MCP HTTP', 'tools': sorted(names),
                  'projects': len(projects), 'documents_verified': len(actual)}
        if granted is not None and len(manifest['projects']) > len(granted):
            result['projects_not_checked'] = len(manifest['projects']) - len(granted)  # a key names at most 100 projects
        return result
    finally:
        failing = sys.exc_info()[0] is not None  # an error is propagating: it is the one to keep
        if not key_file:
            try:
                if temporary_key:
                    revocation = revoke_key(portal, temporary_key, key_name, warnings)
                    if revocation and result is not None:
                        result['temporary_key_not_revoked'] = revocation
            finally:
                try:
                    portal.logout()
                except Exception:
                    if not failing:
                        raise


class CliBridge:
    """`kairos mcp --url <web entry> --key-file <file>` as an MCP client launches it: JSON-RPC lines on stdin and stdout (the CLI of `client/`)."""

    def __init__(self, root, origin, key_file):
        import queue
        import shutil
        import threading
        node = shutil.which('node')
        if not node:
            raise DeploymentError('The round trip needs Node.js to run the CLI of client/')
        self.child = subprocess.Popen([node, str(root / 'client' / 'bin' / 'kairos.mjs'), 'mcp', '--url', origin, '--key-file', str(key_file)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', cwd=root)
        self.lines, self.serial = queue.Queue(), 0
        threading.Thread(target=lambda: [self.lines.put(line) for line in self.child.stdout], daemon=True).start()

    def send(self, method, params=None, notification=False):
        import queue
        self.serial += 1
        message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notification:
            message['id'] = self.serial
        self.child.stdin.write(json.dumps(message) + '\n')
        self.child.stdin.flush()
        if notification:
            return None
        try:
            answer = json.loads(self.lines.get(timeout=60))
        except queue.Empty:
            raise DeploymentError('The CLI bridge did not answer ' + method + ' in 60 s') from None
        if answer.get('id') != self.serial or 'result' not in answer:
            raise DeploymentError('The CLI bridge answered ' + method + ' with an error')
        return answer['result']

    def tool(self, name, arguments):
        result = self.send('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise DeploymentError('The tool ' + name + ' returned an error')
        if 'structuredContent' in result:
            return result['structuredContent']
        return decode_json(next(block['text'] for block in result['content'] if block.get('type') == 'text'))

    def close(self):
        try:
            self.child.stdin.close()
            self.child.wait(timeout=10)
        except Exception:
            self.child.kill()
            self.child.wait()
        self.child.stdout.close()


def roundtrip(origin, password, private, root, wait_seconds=90, warnings=None):
    """The three components end to end through the web entry (T-72, CA-31): the CLI talks to `/mcp/` of nginx, which is kairos-mcp, which calls `/v1`.

    A project and a read/write key are created through the portal; the CLI bridge writes one observation with `remember` and searches for it until the worker
    has indexed it. `allowed_hosts` parity: nginx forwards the `Host` it received, so kairos-mcp must accept the host names of the published origins and refuse any other.
    """
    portal = Portal(origin)
    portal.login(password)
    key_id = key_file = bridge = None
    try:
        if REHEARSAL_PROJECT_ID not in {project['id'] for project in portal.request('/v1/projects')['projects']}:  # a retry of a failed rehearsal finds it
            portal.request('/v1/projects', {'id': REHEARSAL_PROJECT_ID, 'title': 'Three-component rehearsal'})
        portal.request('/v1/projects/' + REHEARSAL_PROJECT_ID + '/policy', {'capture_mode': 'full', 'temporal_projection': False}, method='PUT')  # capture is off by default
        created = portal.request('/v1/keys', {'name': 'rehearsal-roundtrip', 'project_ids': [REHEARSAL_PROJECT_ID], 'scopes': ['read', 'write']})
        key_id, token = created['id'], created['token']
        private.mkdir(parents=True, exist_ok=True)
        key_file = safe_path(private / 'roundtrip.key')
        key_file.write_text(token + '\n', encoding='utf-8')
        if os.name != 'nt':
            key_file.chmod(0o600)
        host = origin.split('//', 1)[1]
        listing = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}}
        hosts = {}
        for name, value in (('ip', host), ('localhost', 'localhost:' + host.rsplit(':', 1)[1]), ('foreign', 'evil.example')):
            status, _ = portal.exchange('/mcp/', listing, bearer=token, host=value)
            hosts[name] = status
        if hosts['ip'] != 200 or hosts['localhost'] != 200 or hosts['foreign'] not in (400, 403, 421):
            raise DeploymentError('allowed_hosts of kairos-mcp does not match the Host that nginx forwards: ' + json.dumps(hosts, sort_keys=True))
        bridge = CliBridge(root, origin, key_file)
        info = bridge.send('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'kairos-rehearsal', 'version': '1'}})
        bridge.send('notifications/initialized', notification=True)
        tools = {tool['name'] for tool in bridge.send('tools/list')['tools']}
        if len(tools) != 34 or not {'remember', 'search', 'event_status'} <= tools:
            raise DeploymentError(f'kairos-mcp listed {len(tools)} tools through nginx; expected 34')
        marker = 'rehearsal-' + uuid.uuid4().hex
        item_id = str(uuid.uuid4())
        event = {'event_id': str(uuid.uuid4()), 'project_id': REHEARSAL_PROJECT_ID, 'session_id': 'rehearsal-session', 'agent_id': 'kairos-rehearsal', 'event_type': 'note',
                 'occurred_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'item_id': item_id, 'version': 1, 'generate': False,
                 'payload': {'title': 'Rehearsal observation ' + marker, 'content': 'The observation ' + marker + ' was written through kairos-mcp and the web entry.',
                             'source': {'uri': 'fixture://rehearsal'}}}
        receipt = bridge.tool('remember', {'event': event})
        deadline, found = time.monotonic() + wait_seconds, None
        while time.monotonic() < deadline and not found:
            hits = bridge.tool('search', {'project_ids': [REHEARSAL_PROJECT_ID], 'q': marker, 'limit': 5})
            found = next((hit for hit in hits.get('items', []) if hit.get('item_id') == item_id), None)
            if not found:
                time.sleep(2)
        if not found:
            raise DeploymentError(f'The observation written through kairos-mcp was not found by search in {wait_seconds} s')
        return {'server': info.get('serverInfo', {}).get('name'), 'tools': len(tools), 'hosts': hosts, 'receipt': sorted(receipt) if isinstance(receipt, dict) else None,
                'found_ref': found.get('ref'), 'found_layer': found.get('layer')}
    finally:
        failing = sys.exc_info()[0] is not None
        try:
            if bridge:
                bridge.close()
        finally:
            try:
                if key_id:
                    revoke_key(portal, key_id, 'rehearsal-roundtrip', warnings)
            finally:
                if key_file and key_file.exists():
                    key_file.unlink()
                try:
                    portal.logout()
                except Exception:
                    if not failing:
                        raise


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


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Print the plan only (the default; it cannot be combined with --apply)')
    parser.add_argument('--fresh', action='store_true', help='Allow first installation; never replace existing secrets')
    parser.add_argument('--secret-dir', help='Existing private secret directory outside the repository')
    parser.add_argument('--verify-key-file', help='Optional existing read key for all projects, if the admin password was changed')
    parser.add_argument('--project-name', default=DEFAULT_PROJECT,
                        help='Isolated rehearsal: own compose project, volumes, networks, image tags, ports and private directory (never the installed project)')
    parser.add_argument('--api-port', type=int, default=DEFAULT_API_PORT, help='Isolated rehearsal only: host port of the API')
    parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT, help='Isolated rehearsal only: host port of the portal')
    parser.add_argument('--embed-stub', action='store_true',
                        help='Isolated rehearsal only: a simulated embedding provider instead of the Ollama of the host; it also counts any language-model call (must be 0)')
    parser.add_argument('--roundtrip', action='store_true',
                        help='Isolated rehearsal only (needs --embed-stub): the CLI writes an observation through memory-web -> kairos-mcp -> /v1 and finds it by search')
    parser.add_argument('--backup-timeout', type=int, default=None,
                        help=f'Seconds the content-manifest, backup and verify-backup commands may take (1..{BACKUP_TIMEOUT_MAX_SECONDS}, default {BACKUP_TIMEOUT_SECONDS}); '
                             'the container of a command that exceeds it is stopped and removed')
    parser.add_argument('--verify-backup', action=argparse.BooleanOptionalAction, default=None,
                        help='Restore the copy made before migrating into an ephemeral, isolated PostgreSQL and compare it with its manifest; migrate does not run if it differs. '
                             'Default: on for an isolated --project-name, off for the installed project')
    parser.add_argument('--stop-services-before-migrate', action='store_true',
                        help='Stop memory-api and memory-worker before the migrate phase (they are started again by the start phase); default: leave them running')
    parser.add_argument('--rollback', action='store_true',
                        help='Go back to the images tagged by the previous deployment (kairos-*:<version>-<mark>) WITHOUT migrating; no_previous_images if there are none, already_at_previous if they are the ones in use. '
                             'Not for --fresh, --stop-services-before-migrate or --verify-backup')
    parser.add_argument('--break-lock', action='store_true',
                        help='Remove the lock file of a deployment whose process is gone (deployment_locked); it never breaks the lock of a process that is still running here')
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error('--dry-run and --apply exclude each other')
    if args.rollback and (args.fresh or args.stop_services_before_migrate or args.verify_backup is not None):
        parser.error('--rollback goes back to the previous images without migrating: it takes no --fresh, --stop-services-before-migrate or --verify-backup')
    if not args.apply:
        try:
            validate_isolation(args.project_name, args.api_port, args.web_port)
            check_backup_timeout(args.backup_timeout)
            if (args.embed_stub or args.roundtrip) and args.project_name == DEFAULT_PROJECT:
                raise DeploymentError('--embed-stub and --roundtrip are only for an isolated --project-name')
            if args.roundtrip and not args.embed_stub:
                raise DeploymentError('--roundtrip needs --embed-stub')
        except DeploymentError as exc:
            parser.error(str(exc))
        verifying = args.verify_backup if args.verify_backup is not None else args.project_name != DEFAULT_PROJECT
        if args.rollback:
            print(json.dumps({'mode': 'dry-run', 'phases': ROLLBACK_PHASES + (('roundtrip',) if args.roundtrip else ()), 'rollback': True, 'services': [ROLLBACK_SERVICES[n] for n in ROLLBACK_SERVICES],
                              'project': args.project_name, 'migrate': False, 'data_removed': False}, indent=2))
            return 0
        phases = PHASES[:PHASES.index('backup') + 1] + (('verify_backup',) if verifying else ()) + PHASES[PHASES.index('backup') + 1:] + (('roundtrip',) if args.roundtrip else ())
        print(json.dumps({'mode': 'dry-run', 'phases': phases, 'services': SERVICES + ((STUB_SERVICE,) if args.embed_stub else ()), 'fresh': args.fresh, 'project': args.project_name,
                          'backup_timeout_seconds': check_backup_timeout(args.backup_timeout), 'verify_backup': verifying, 'volumes': project_volumes(args.project_name), 'models': 'simulated embedding provider; no language model' if args.embed_stub else 'preserve configuration',
                          'data_removed': False}, indent=2))
        return 0
    try:
        deployment = Deployment(args, root)
    except DeploymentError as exc:
        parser.error(str(exc))
    lock = DeployLock(deployment.private, deployment.project, break_lock=args.break_lock)
    try:
        lock.acquire()
    except DeploymentLocked as exc:  # before any phase and without touching the report of the deployment that holds the lock
        print(f'{exc.code}: {exc}', file=sys.stderr)
        return EXIT_LOCKED
    put_back = install_signal_handlers()
    try:
        if lock.broken is not None:
            deployment.report['lock_broken'] = {key: lock.broken.get(key) for key in ('pid', 'host', 'started_at')}
            print(f'WARNING: lock broken: it was held by a deployment {lock.describe(lock.broken)}.', file=sys.stderr)
        try:
            deployment.rollback() if args.rollback else deployment.apply()
        except (NoPreviousImages, AlreadyAtPrevious) as exc:  # nothing was touched, and the report (with the tags) is left as it is
            print(f'{exc.code}: {exc}', file=sys.stderr)
            return EXIT_NO_PREVIOUS_IMAGES if isinstance(exc, NoPreviousImages) else EXIT_ALREADY_AT_PREVIOUS
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
    finally:  # a phase that fails, an unexpected error, Ctrl-C and SIGTERM all release the lock
        try:
            lock.release()
        finally:
            put_back()


def install_signal_handlers():
    """SIGTERM and SIGHUP end the deployment like an exception, so that the lock is released on the way out; returns the function that puts the old handlers back."""
    def stop(signum, frame):
        raise SystemExit(128 + signum)
    previous = {}
    for name in ('SIGTERM', 'SIGHUP'):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            previous[number] = signal.signal(number, stop)
        except (ValueError, OSError):  # not the main thread: the caller owns the signals
            pass

    def put_back():
        for number, handler in previous.items():
            signal.signal(number, handler)
    return put_back


if __name__ == '__main__':
    raise SystemExit(main())
