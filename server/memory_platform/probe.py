"""Round-trip probe (C-06, M-06): the whole path of a memory, from `/v1` to the semantic search, with a key that can touch nothing else.

`admin probe-provision` makes the dedicated project `kairos-probe` and a key whose scope is that project alone (read and write). `admin probe` then goes through the
public API with that key and nobody else's data: it WRITES one synthetic note with a unique marker, WAITS for the receipt of its `embed` job (the worker has indexed it),
SEARCHES for it with the semantic layer and RETIRES it (a `delete` event, checked by a search). Every stage is timed with an injected clock, so the tests wait for nothing.
A failure in any stage ends the run with a closed `stage` and `code`, tries to retire what was written and says so; nothing here prints a credential, a response body or an
exception message (CWE-150/CWE-532: only status numbers, exception TYPES and the closed codes below reach the terminal).
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import time
import uuid

from . import observability
from .auth import token_hash
from .backup import write_atomic

PROBE_PROJECT = 'kairos-probe'
PROBE_KEY_NAME = 'kairos-probe'
PROBE_SCOPES = ('read', 'write')  # never publish, validate or admin: the probe writes notes, it cannot publish or delegate
PROBE_POLICY = {'capture_mode': 'summary', 'temporal_projection': False}  # capture off refuses notes; `summary` is the least that accepts them
DEFAULT_TIMEOUT = 120.0
TIMEOUT_RANGE = (1.0, 3600.0)
DEFAULT_URL = 'http://memory-api:8790'
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_KEY_FILE = '/backups/kairos-probe.key'  # the volume of memory-admin: the key never goes in the repository, the image or a log
DEFAULT_METRICS_FILE = '/backups/kairos-probe.prom'
CALL_TIMEOUT = 30.0  # the longest one request may take (never more than what is left of the budget)
RETIRE_CALL_TIMEOUT = 10.0  # retiring (also after a failure) is outside the budget of the other stages, so a note is never left because the wait used it up: one short call each
STAGES = observability.PROBE_STAGES
SETUP = 'setup'  # not a stage of the round trip: the configuration of the command (an unreadable key, a bad URL) failed before any request
CODES = ('unreachable', 'unauthorized', 'rejected', 'server_error', 'timeout', 'job_failed', 'no_embed_job', 'not_found', 'no_result', 'semantic_unavailable',
         'still_active', 'bad_answer', 'key_unreadable', 'url_invalid', 'timeout_invalid')
SAFE_NAME = re.compile(r'[A-Za-z0-9_]{1,60}')


class ProbeError(Exception):
    """A refusal with a closed `code` (provisioning and configuration): the message never carries data of the peer."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


class StageFailed(Exception):
    def __init__(self, stage, code, status=None, error_type=None):
        super().__init__(f'{stage}:{code}')
        self.stage, self.code, self.status, self.error_type = stage, code, status, error_type


def probe_timeout(environ=None):
    """`MEMORY_PROBE_TIMEOUT` seconds (default 120): the whole budget of one run, from the first request to the end of the wait for the index."""
    environ = os.environ if environ is None else environ
    text = str(environ.get('MEMORY_PROBE_TIMEOUT', '') or DEFAULT_TIMEOUT).strip()
    try:
        value = float(text)
    except ValueError:
        raise ProbeError('timeout_invalid', 'MEMORY_PROBE_TIMEOUT must be a number of seconds') from None
    if not TIMEOUT_RANGE[0] <= value <= TIMEOUT_RANGE[1]:  # also false for nan and inf
        raise ProbeError('timeout_invalid', 'MEMORY_PROBE_TIMEOUT must be between %g and %g seconds' % TIMEOUT_RANGE)
    return value


def probe_url(environ=None, override=None):
    """`MEMORY_PROBE_URL` (default http://memory-api:8790): where `/v1` answers, seen from the container that runs the probe."""
    value = (override or (os.environ if environ is None else environ).get('MEMORY_PROBE_URL') or DEFAULT_URL).strip().rstrip('/')
    if not re.fullmatch(r'https?://[A-Za-z0-9._-]+(:[0-9]{1,5})?', value):
        raise ProbeError('url_invalid', 'MEMORY_PROBE_URL must be http(s)://host[:port] with no path, credentials or query')
    return value


def read_key(path):
    """The token of the probe key file, or `key_unreadable` (the path and the reason are not part of the message: they may name an operator's directory)."""
    try:
        token = Path(path).read_text(encoding='utf-8').strip()
    except (OSError, ValueError, TypeError):
        raise ProbeError('key_unreadable', 'the probe key file cannot be read') from None
    if not token or any(character.isspace() for character in token):
        raise ProbeError('key_unreadable', 'the probe key file does not hold one token')
    return token


class HttpApi:
    """`/v1` over HTTP with the probe key. `call` returns (status, JSON object or None); a transport error propagates (the probe records its TYPE only)."""

    def __init__(self, url, token):
        import httpx
        # No redirects and no proxy variables: the bearer token goes only to the configured URL.
        self.client = httpx.Client(base_url=url, headers={'Authorization': 'Bearer ' + token}, follow_redirects=False, trust_env=False, timeout=CALL_TIMEOUT)

    def call(self, method, path, body=None, timeout=None):
        response = self.client.request(method, path, json=body, timeout=timeout or CALL_TIMEOUT)
        try:
            data = response.json()
        except ValueError:
            data = None
        return response.status_code, data if isinstance(data, dict) else None

    def close(self):
        self.client.close()


def classify(status):
    return 'unauthorized' if status in (401, 403) else 'server_error' if status >= 500 or status in (429,) else 'rejected'


class Probe:
    """One run of the round trip against `api` (anything with `call(method, path, body, timeout)`); `clock` and `sleep` are injected so a test measures without waiting."""

    def __init__(self, api, *, timeout=DEFAULT_TIMEOUT, poll=DEFAULT_POLL_SECONDS, clock=None, sleep=None, project=PROBE_PROJECT, now=None):
        # Looked up when the Probe is made, not when the module is imported: a test that replaces `time` here sees which clock a run really uses.
        self.api, self.timeout, self.poll, self.clock, self.sleep, self.project = api, timeout, poll, clock or time.monotonic, sleep or time.sleep, project
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.stages = {}

    # -- requests -------------------------------------------------------------------------------------------------------------------

    def event(self, event_type, item_id, version, title, content):
        return {'event_id': str(uuid.uuid4()), 'project_id': self.project, 'session_id': 'kairos-probe', 'agent_id': 'kairos-probe', 'event_type': event_type,
                'occurred_at': self.now().strftime('%Y-%m-%dT%H:%M:%SZ'), 'item_id': item_id, 'version': version, 'generate': False,
                'payload': {'title': title, 'content': content, 'source': {'uri': 'fixture://kairos-probe'}}}

    def call(self, stage, method, path, body=None, timeout=None):
        """One request of `stage`: (status, data); a transport failure is `unreachable` and carries only the exception type."""
        try:
            return self.api.call(method, path, body, timeout)
        except Exception as error:
            name = type(error).__name__
            raise StageFailed(stage, 'unreachable', error_type=name if SAFE_NAME.fullmatch(name) else 'Exception') from None

    def remaining(self, started):
        return self.timeout - (self.clock() - started)

    def budget(self, stage, started):
        left = self.remaining(started)
        if left <= 0:
            raise StageFailed(stage, 'timeout')
        return min(CALL_TIMEOUT, left)

    # -- stages ---------------------------------------------------------------------------------------------------------------------

    def write(self, started, state):
        try:
            status, data = self.call('write', 'POST', '/v1/events', state['event'], self.budget('write', started))
        except StageFailed as failure:
            state['ambiguous'] = failure.code == 'unreachable'  # a request that died on the wire (a timeout, a reset) may have landed; one refused before it was sent is retired in vain, harmlessly
            raise
        if status not in (200, 202):
            state['ambiguous'] = status >= 500  # a 5xx may have landed before it failed: the retirement tries both versions
            raise StageFailed('write', classify(status), status)
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            state['ambiguous'] = True
            raise StageFailed('write', 'bad_answer', status)
        state['written'] = True

    def index(self, started, state):
        path = '/v1/projects/%s/events/%s/status' % (self.project, state['event']['event_id'])
        while True:
            status, data = self.call('index', 'GET', path, None, self.budget('index', started))
            if status != 200 or not isinstance(data, dict):
                raise StageFailed('index', classify(status) if status != 200 else 'bad_answer', status)
            if data.get('found') is False:
                raise StageFailed('index', 'not_found', status)
            jobs = [job for job in data.get('jobs') or [] if isinstance(job, dict) and job.get('destination') == 'embed']
            if not jobs:
                raise StageFailed('index', 'no_embed_job', status)  # embeddings are off in this server: nothing will ever index the note
            if any(job.get('state') == 'failed' for job in jobs):
                raise StageFailed('index', 'job_failed', status)
            if all(job.get('state') == 'succeeded' for job in jobs):
                return
            left = self.remaining(started)
            if left <= 0:
                raise StageFailed('index', 'timeout')
            self.sleep(min(self.poll, left))

    def search(self, started, state):
        body = {'project_ids': [self.project], 'q': state['query'], 'limit': 5, 'semantic': True}
        status, data = self.call('search', 'POST', '/v1/search', body, self.budget('search', started))
        if status != 200 or not isinstance(data, dict):
            raise StageFailed('search', classify(status) if status != 200 else 'bad_answer', status)
        items = data.get('items')
        backends = data.get('backends')
        if not isinstance(items, list) or not isinstance(backends, dict):
            raise StageFailed('search', 'bad_answer', status)
        if not any(isinstance(item, dict) and item.get('item_id') == state['item_id'] for item in items):
            raise StageFailed('search', 'no_result', status)
        semantic = backends.get('semantic')
        if not isinstance(semantic, dict) or semantic.get('status') != 'ok' or not semantic.get('count'):
            raise StageFailed('search', 'semantic_unavailable', status)  # found by the lexical layer alone: the vector path did not answer

    def retire(self, started, state, versions=(2,)):
        """A `delete` event for the note (version 2, or the versions given), then a lexical search that must not return it."""
        done = False
        for version in versions:
            event = self.event('delete', state['item_id'], version, 'Probe retired', 'retired')
            status, data = self.call('retire', 'POST', '/v1/events', event, RETIRE_CALL_TIMEOUT)
            if status in (200, 202):
                done = True
                break
            if status != 409:
                raise StageFailed('retire', classify(status), status)
        if not done:
            raise StageFailed('retire', 'rejected', 409)
        status, data = self.call('retire', 'POST', '/v1/search', {'project_ids': [self.project], 'q': state['query'], 'limit': 5, 'semantic': False},
                                 RETIRE_CALL_TIMEOUT)
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise StageFailed('retire', classify(status) if status != 200 else 'bad_answer', status)
        if any(isinstance(item, dict) and item.get('item_id') == state['item_id'] for item in data['items']):
            raise StageFailed('retire', 'still_active', status)

    # -- the run --------------------------------------------------------------------------------------------------------------------

    def timed(self, stage, function, *arguments, **options):
        began = self.clock()
        try:
            function(*arguments, **options)
        finally:
            self.stages[stage] = self.stages.get(stage, 0.0) + max(0.0, self.clock() - began)

    def run(self):
        """Returns the report: `probe_ok` with the seconds of every stage, or `probe_failed` with `stage`, `code`, `retired` (did the attempt to retire what was written work)."""
        marker = 'probe-' + uuid.uuid4().hex
        item_id = str(uuid.uuid4())
        state = {'item_id': item_id, 'query': 'synthetic probe ' + marker, 'written': False, 'ambiguous': False,
                 'event': self.event('note', item_id, 1, 'Probe ' + marker, 'Synthetic probe memory ' + marker + '. It is written, indexed, found and retired in one run.')}
        started = self.clock()
        self.stages = {}
        try:
            for stage in STAGES:
                self.timed(stage, getattr(self, stage), started, state)
        except StageFailed as failure:
            report = {'status': 'probe_failed', 'stage': failure.stage, 'code': failure.code, 'kairos_probe_success': 0}
            if failure.status is not None:
                report['http_status'] = failure.status
            if failure.error_type:
                report['error_type'] = failure.error_type
            report['retired'] = self.clean_up(state, failure.stage)
            return self.finish(report, started)
        return self.finish({'status': 'probe_ok', 'kairos_probe_success': 1}, started)

    def clean_up(self, state, failed_stage):
        """After a failure: retire what was written. None when nothing was written; True when the attempt worked; False when it did not (or when the retire stage itself is what failed).
        Never raises and never hides the failure that came first."""
        if not (state['written'] or state['ambiguous']):
            return None
        if failed_stage == 'retire':
            return False
        versions = (2, 1) if state['ambiguous'] and not state['written'] else (2,)  # a write that may not have landed: version 2 if it did, else a tombstone at version 1
        try:
            self.timed('retire', self.retire, self.clock(), state, versions)
            return True
        except Exception as error:  # the failure that came first is the one reported; this one is logged (its type only) and `retired` says False
            observability.log_failure('probe_retire_failed', error, 'warning', stage='retire')
            return False

    def finish(self, report, started):
        report['stages'] = {stage: round(seconds, 3) for stage, seconds in self.stages.items()}
        report['total_seconds'] = round(max(0.0, self.clock() - started), 3)
        return report


def run_probe(api, timeout, **options):
    """The report of one run, with the metrics recorded in the probe registry (the caller writes the file)."""
    report = Probe(api, timeout=timeout, **options).run()
    observability.record_probe(report['kairos_probe_success'] == 1, report['stages'])
    if report['status'] == 'probe_failed':
        observability.log_event('probe_failed', 'error', stage=report['stage'], code=report['code'])
    return report


def failed_setup(code):
    """The report of a probe that could not start (the key, the URL or the timeout is wrong): success 0, no stage ran."""
    observability.record_probe(False, {})
    observability.log_event('probe_failed', 'error', stage=SETUP, code=code)
    return {'status': 'probe_failed', 'stage': SETUP, 'code': code, 'kairos_probe_success': 0, 'stages': {}, 'retired': None}


def probe_command(url, key_file, metrics_file, environ=None, api_factory=None, **options):
    """`admin probe`: settings, one run, the metrics file. Returns the report (a setting that is wrong is a `probe_failed` at stage `setup`, with success 0 in the file as well)."""
    try:
        timeout, address, token = probe_timeout(environ), probe_url(environ, url), read_key(key_file)
    except ProbeError as error:
        report = failed_setup(error.code)
    else:
        api = (api_factory or HttpApi)(address, token)  # looked up now, so a test can replace HttpApi
        try:
            report = run_probe(api, timeout, **options)
        finally:
            close = getattr(api, 'close', None)
            if close:
                close()
    if metrics_file:
        write_metrics(metrics_file)
    return report


def write_metrics(path):
    """The probe series as a file (a textfile collector reads it); a failure to write it is not a failure of the probe."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, observability.render_probe_metrics(), 0o644)
    except OSError:
        return False
    return True


# -- provisioning (T-68) ------------------------------------------------------------------------------------------------------------

def admin_actor(store):
    """The operator that `admin` acts as: the first enabled administrator (the database credentials the command already holds are the authority)."""
    with store.transaction() as connection:
        row = connection.execute('SELECT id FROM memory.actors WHERE is_admin AND NOT disabled ORDER BY username,id LIMIT 1').fetchone()
    if not row:
        raise ProbeError('no_admin', 'there is no administrator: run bootstrap first')
    return {'id': row['id'], 'credential_type': 'bootstrap'}


def valid_key(store, token, project_id):
    """The id of the active key whose token is `token` AND whose reach is exactly this project with read and write, or None (a wider key is never reused)."""
    with store.transaction() as connection:
        row = connection.execute('SELECT id,project_ids,scopes FROM memory.api_keys WHERE token_hash=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())',
                                 (token_hash(token),)).fetchone()
    if row and list(row['project_ids']) == [project_id] and sorted(row['scopes']) == sorted(PROBE_SCOPES):
        return row['id']
    return None


def provision(store, key_file, *, project_id=PROBE_PROJECT):
    """Idempotent: the project `kairos-probe` (created if missing, its policy set only when it differs) and a key with read and write on it alone, whose token lives in `key_file` (0600).

    A second run reuses the key in the file when the database still accepts it with that exact reach; otherwise it makes a new one, writes the file and revokes the older probe
    keys. It writes nothing in any other project and prints no token: the report has the key id and the path only."""
    path = Path(key_file)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProbeError('key_file_unsafe', 'the probe key file must be a regular file, not a link')
    actor = admin_actor(store)
    with store.transaction() as connection:
        existing = connection.execute('SELECT policy FROM memory.projects WHERE id=%s', (project_id,)).fetchone()
    if existing is None:
        store.create_project(actor, {'id': project_id, 'title': 'Kairos round-trip probe'})
        store.set_policy(actor, project_id, PROBE_POLICY)
    elif existing['policy'] != PROBE_POLICY:
        store.set_policy(actor, project_id, PROBE_POLICY)
    kept = None
    if path.is_file():
        try:
            kept = valid_key(store, path.read_text(encoding='utf-8').strip(), project_id)
        except (OSError, ValueError):
            kept = None
    if kept:
        return {'status': 'provisioned', 'project': 'created' if existing is None else 'present', 'key': 'reused', 'key_id': kept, 'key_file': str(path)}
    created = store.create_key(actor, {'name': PROBE_KEY_NAME, 'project_ids': [project_id], 'scopes': list(PROBE_SCOPES)})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, (created['token'] + '\n').encode('utf-8'), 0o600)
    except BaseException:
        store.revoke_key(actor, created['id'])  # a key nobody can read is not left active
        raise
    with store.transaction() as connection:
        older = [row['id'] for row in connection.execute('SELECT id,project_ids FROM memory.api_keys WHERE name=%s AND revoked_at IS NULL AND id<>%s', (PROBE_KEY_NAME, created['id'])).fetchall()
                 if list(row['project_ids']) == [project_id]]
    for key_id in older:
        store.revoke_key(actor, key_id)
    return {'status': 'provisioned', 'project': 'created' if existing is None else 'present', 'key': 'created', 'key_id': created['id'], 'key_file': str(path)}
