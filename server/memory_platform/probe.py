"""Round-trip probe (C-06, M-06): the whole path of a memory, from `/v1` to the semantic search, with a key that can touch nothing else.

`admin probe-provision` makes the dedicated project `kairos-probe`, a service actor of its own (`kairos-probe`: no password, no web login, no global role) and a key owned by that actor
whose scope is the project alone (read and write). `admin probe` then goes through the public API with that key and nobody else's data: it WRITES one synthetic note with a unique
marker, WAITS for the receipt of its `embed` job (the worker has indexed it), SEARCHES for it with the semantic layer and RETIRES it (a `delete` event, checked by a search).
Every stage is timed with an injected clock, so the tests wait for nothing. A failure (or an interrupt) in any stage ends the run with a closed `stage` and `code`, tries to retire
what was written (inside a budget of its own) and says so; nothing here prints a credential, a response body or an exception message (CWE-150/CWE-532: only status numbers,
exception TYPES and the closed codes below reach the terminal).

What a run leaves behind is bounded: it first retires the active notes an earlier run left (a failed one), runs one at a time (a lock file), and `admin` purges the retired notes of
`kairos-probe` (rows only, and only of that project) so the probe project does not grow.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import threading
import time
import uuid

try:
    import fcntl
except ImportError:  # Windows: the container that runs the probe is Linux; a developer's host runs without the lock
    fcntl = None

from . import observability
from .auth import Auth, token_hash
from .backup import write_atomic
from .errors import Forbidden, NotFound, Unauthorized

PROBE_PROJECT = 'kairos-probe'
PROBE_TITLE = 'Kairos round-trip probe'  # the mark of a project that is the probe's: a project of that id with another title is somebody else's and is never adopted
PROBE_KEY_NAME = 'kairos-probe'
SERVICE_USERNAME = 'kairos-probe'  # the actor that owns the probe key and so signs every audit row of a run (never an administrator)
SERVICE_PASSWORD_HASH = '!service-account'  # not a hash `verify_password` can read: nobody logs in as this actor; it is also the mark of an actor that is ours
SERVICE_GRANTS = ('read', 'write', 'admin')  # `admin` on this one project is the least the permission model lets an actor create and revoke its own keys with (`_delegate`); it is no global role
PROBE_SCOPES = ('read', 'write')  # never publish, validate or admin: the probe writes notes, it cannot publish or delegate
PROBE_POLICY = {'capture_mode': 'summary', 'temporal_projection': False}  # capture off refuses notes; `summary` is the least that accepts them
DEFAULT_TIMEOUT = 120.0
TIMEOUT_RANGE = (1.0, 3600.0)
DEFAULT_URL = 'http://memory-api:8790'
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_KEY_FILE = '/backups/kairos-probe.key'  # the volume of memory-admin: the key never goes in the repository, the image or a log
DEFAULT_METRICS_FILE = '/backups/kairos-probe.prom'
LOCK_SUFFIX = '.lock'  # next to the key file: `kairos-probe.key.lock`, which is no name of a backup copy
CALL_TIMEOUT = 30.0  # the longest one request may take (never more than what is left of the budget)
RETIRE_CALL_TIMEOUT = 10.0  # one retiring request (also after a failure) never waits longer than this
RETIRE_BUDGET = 20.0  # ALL the requests that retire a note (after a failure or at the end) share these seconds, outside the budget of the other stages: a run lasts at most MEMORY_PROBE_TIMEOUT + this
INTERRUPT_RETIRE_BUDGET = 8.0  # the same, after Ctrl-C or SIGTERM: `docker stop` waits 10 s by default, so the retirement and the metrics file must fit in it (the manual gives `stop_grace_period`)
SWEEP_QUERY ='synthetic probe memory'  # what every note of the probe says; the run starts by retiring the active ones an earlier run left
SWEEP_LIMIT = 20
PURGE_AFTER_SECONDS = 600  # a retired note of `kairos-probe` older than this is deleted for good by `admin probe`
PURGE_BATCH = 200
PURGE_BUDGET = 15.0  # ALL the statements of one purge share these seconds (each is limited by what is left); once spent the transaction is rolled back and nothing is deleted
DEFAULT_QUEUE_STUCK_SECONDS = 900.0  # MEMORY_QUEUE_STUCK_SECONDS: a job that has waited longer than this for a worker is a queue that does not drain
PROVISION_LOCK = 688090884127  # advisory lock: two `probe-provision` at once never revoke each other's key
STAGES = observability.PROBE_STAGES
SETUP = 'setup'  # not a stage of the round trip: the configuration of the command (an unreadable key, a bad URL) failed before any request
CODES = ('unreachable', 'unauthorized', 'rejected', 'server_error', 'timeout', 'job_failed', 'no_embed_job', 'not_found', 'no_result', 'semantic_unavailable',
         'still_active', 'bad_answer', 'key_unreadable', 'url_invalid', 'timeout_invalid', 'busy', 'interrupted', 'internal_error')
SAFE_NAME = re.compile(r'[A-Za-z0-9_]{1,60}')
LAST_SUCCESS = re.compile(r'^kairos_probe_last_success_timestamp_seconds\s+([0-9.eE+-]+)\s*$', re.M)


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
    if not token or not token.isascii() or any(character.isspace() or not character.isprintable() for character in token):  # a header carries ASCII only: the transport would fail with a trace
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


def found(items, item_id):
    return isinstance(items, list) and any(isinstance(item, dict) and item.get('item_id') == item_id for item in items)


class Probe:
    """One run of the round trip against `api` (anything with `call(method, path, body, timeout)`); `clock` and `sleep` are injected so a test measures without waiting."""

    def __init__(self, api, *, timeout=DEFAULT_TIMEOUT, poll=DEFAULT_POLL_SECONDS, clock=None, sleep=None, project=PROBE_PROJECT, now=None):
        # Looked up when the Probe is made, not when the module is imported: a test that replaces `time` here sees which clock a run really uses.
        self.api, self.timeout, self.poll, self.clock, self.sleep, self.project = api, timeout, poll, clock or time.monotonic, sleep or time.sleep, project
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.stages = {}
        self.current = 'write'

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

    # -- before the round trip ------------------------------------------------------------------------------------------------------

    def sweep(self, started):
        """Retire the ACTIVE notes of `kairos-probe` an earlier run left (a base that was cut, a kill): a failed run never leaves a permanent trace. Best effort and bounded: at most
        SWEEP_LIMIT notes, one request each of at most RETIRE_CALL_TIMEOUT, and only while more than half of the budget is left. Returns how many were retired."""
        swept = 0
        try:
            if self.remaining(started) <= self.timeout / 2:
                return 0
            status, data = self.call('write', 'POST', '/v1/search', {'project_ids': [self.project], 'q': SWEEP_QUERY, 'limit': SWEEP_LIMIT, 'semantic': False},
                                     min(RETIRE_CALL_TIMEOUT, self.remaining(started)))
            if status != 200 or not isinstance(data, dict) or not isinstance(data.get('items'), list):
                raise StageFailed('write', classify(status) if status != 200 else 'bad_answer', status)
            for item in data['items']:
                if not isinstance(item, dict) or not isinstance(item.get('item_id'), str) or not isinstance(item.get('version'), int) or self.remaining(started) <= self.timeout / 2:
                    continue
                event = self.event('delete', item['item_id'], item['version'] + 1, 'Probe retired', 'retired')
                status, _ = self.call('write', 'POST', '/v1/events', event, min(RETIRE_CALL_TIMEOUT, self.remaining(started)))
                swept += 1 if status in (200, 202) else 0
        except StageFailed as failure:  # the write that follows tells the truth about the server; this is only hygiene
            observability.log_event('probe_sweep_failed', 'warning', stage=SETUP, code=failure.code)
        return swept

    # -- stages ---------------------------------------------------------------------------------------------------------------------

    def write(self, started, state):
        timeout = self.budget('write', started)  # no budget left: nothing is sent and nothing is retired
        state['ambiguous'] = True  # from here on the note may have landed, also when a signal ends the run before the answer: the retirement is tried (harmless when it did not)
        status, data = self.call('write', 'POST', '/v1/events', state['event'], timeout)  # a request that died on the wire (a timeout, a reset) stays ambiguous
        if status not in (200, 202):
            state['ambiguous'] = status >= 500  # a 5xx may have landed before it failed: the retirement tries both versions
            raise StageFailed('write', classify(status), status)
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            state['ambiguous'] = True
            raise StageFailed('write', 'bad_answer', status)
        state['written'], state['ambiguous'] = True, False

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
        """The note of THIS run, found by the semantic path. The query shares no word with the note (the marker is a token of its own): a lexical match is impossible by construction,
        so the note can only come back through the vectors, and `item_id` is this run's (any other note, active or not, is somebody else's). A control search of the same query
        with the semantic layer off must NOT return it: if it does, the two paths cannot be told apart and the run does not call that a semantic hit."""
        body = {'project_ids': [self.project], 'q': state['semantic_query'], 'limit': 5, 'semantic': True}
        status, data = self.call('search', 'POST', '/v1/search', body, self.budget('search', started))
        if status != 200 or not isinstance(data, dict):
            raise StageFailed('search', classify(status) if status != 200 else 'bad_answer', status)
        items, backends = data.get('items'), data.get('backends')
        if not isinstance(items, list) or not isinstance(backends, dict):
            raise StageFailed('search', 'bad_answer', status)
        semantic = backends.get('semantic')
        if not isinstance(semantic, dict) or semantic.get('status') != 'ok':
            raise StageFailed('search', 'semantic_unavailable', status)  # the vector path did not answer
        if not found(items, state['item_id']):
            raise StageFailed('search', 'no_result', status)
        status, data = self.call('search', 'POST', '/v1/search', dict(body, semantic=False), self.budget('search', started))
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise StageFailed('search', classify(status) if status != 200 else 'bad_answer', status)
        if found(data['items'], state['item_id']):
            raise StageFailed('search', 'semantic_unavailable', status)

    def retire(self, started, state, versions=(2,), budget=RETIRE_BUDGET):
        """A `delete` event for the note (version 2, or the versions given), then a lexical search that must not return it. All its requests share `budget` seconds (RETIRE_BUDGET;
        INTERRUPT_RETIRE_BUDGET after a signal; each request at most RETIRE_CALL_TIMEOUT): `started` is the run's and is not used, the retirement runs outside the budget of the stages.
        When no version is accepted, the note carrying the unique marker of THIS run is looked up and retired at the version the server says it has."""
        began = self.clock()

        def left():
            remaining = budget - (self.clock() - began)
            if remaining <= 0:
                raise StageFailed('retire', 'timeout')
            return min(RETIRE_CALL_TIMEOUT, remaining)
        done = False
        for version in versions:
            event = self.event('delete', state['item_id'], version, 'Probe retired', 'retired')
            status, data = self.call('retire', 'POST', '/v1/events', event, left())
            if status in (200, 202):
                done = True
                break
            if status != 409:
                raise StageFailed('retire', classify(status), status)
        query = {'project_ids': [self.project], 'q': state['query'], 'limit': 5, 'semantic': False}  # `q` carries the marker of this run, which no other note has
        if not done:
            status, data = self.call('retire', 'POST', '/v1/search', query, left())
            if status != 200 or not isinstance(data, dict) or not isinstance(data.get('items'), list):
                raise StageFailed('retire', classify(status) if status != 200 else 'bad_answer', status)
            for item in data['items']:
                if isinstance(item, dict) and item.get('item_id') == state['item_id'] and isinstance(item.get('version'), int):
                    status, _ = self.call('retire', 'POST', '/v1/events', self.event('delete', item['item_id'], item['version'] + 1, 'Probe retired', 'retired'), left())
                    done = status in (200, 202)
            if not done:
                raise StageFailed('retire', 'rejected', 409)
        status, data = self.call('retire', 'POST', '/v1/search', query, left())
        if status != 200 or not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise StageFailed('retire', classify(status) if status != 200 else 'bad_answer', status)
        if found(data['items'], state['item_id']):
            raise StageFailed('retire', 'still_active', status)

    # -- the run --------------------------------------------------------------------------------------------------------------------

    def timed(self, stage, function, *arguments, **options):
        began = self.clock()
        self.current = stage
        try:
            function(*arguments, **options)
        finally:
            self.stages[stage] = self.stages.get(stage, 0.0) + max(0.0, self.clock() - began)

    def run(self):
        """Returns the report: `probe_ok` with the seconds of every stage, or `probe_failed` with `stage`, `code`, `retired` (did the attempt to retire what was written work).
        Whatever ends the run (a stage, an unexpected exception, Ctrl-C or SIGTERM) ends in a report with success 0 and the retirement attempted."""
        marker = 'probe-' + uuid.uuid4().hex
        item_id = str(uuid.uuid4())
        state = {'item_id': item_id, 'query': 'synthetic probe ' + marker, 'semantic_query': 'sq' + uuid.uuid4().hex, 'written': False, 'ambiguous': False,
                 'event': self.event('note', item_id, 1, 'Probe ' + marker, 'Synthetic probe memory ' + marker + '. It is written, indexed, found and retired in one run.')}
        started = self.clock()
        self.stages, self.current = {}, 'write'
        swept = 0
        try:
            swept = self.sweep(started)
            for stage in STAGES:
                self.timed(stage, getattr(self, stage), started, state)
        except StageFailed as failure:
            failed_stage = failure.stage
            report = {'status': 'probe_failed', 'stage': failure.stage, 'code': failure.code, 'kairos_probe_success': 0}
            if failure.status is not None:
                report['http_status'] = failure.status
            if failure.error_type:
                report['error_type'] = failure.error_type
        except BaseException as error:  # Ctrl-C and SIGTERM are not `Exception`: they still end with the note retired and the metrics written
            name = type(error).__name__
            failed_stage = self.current
            observability.log_failure('probe_aborted', error, 'error', stage=failed_stage)  # its type only, like every handler of the package (a message may carry a token)
            report = {'status': 'probe_failed', 'stage': failed_stage, 'code': 'internal_error' if isinstance(error, Exception) else 'interrupted', 'kairos_probe_success': 0,
                      'error_type': name if SAFE_NAME.fullmatch(name) else 'Exception'}
        else:
            return self.finish({'status': 'probe_ok', 'kairos_probe_success': 1}, started, item_id, swept)
        report['retired'] = self.clean_up(state, failed_stage, report['code'] == 'interrupted')
        return self.finish(report, started, item_id, swept)

    def clean_up(self, state, failed_stage, interrupted=False):
        """After a failure: retire what was written (or may have been: a write in flight when a signal came). None when nothing was sent; True when the attempt worked; False when it did not
        (or when the retire stage itself is what failed). After a signal the budget is INTERRUPT_RETIRE_BUDGET. Never raises, not even on a second signal, and never hides the failure
        that came first."""
        if not (state['written'] or state['ambiguous']):
            return None
        if failed_stage == 'retire':
            return False
        versions = (2, 1) if state['ambiguous'] and not state['written'] else (2,)  # a write that may not have landed: version 2 if it did, else a tombstone at version 1
        try:
            self.timed('retire', self.retire, self.clock(), state, versions, budget=INTERRUPT_RETIRE_BUDGET if interrupted else RETIRE_BUDGET)
            return True
        except BaseException as error:  # the failure that came first is the one reported (also when a second signal arrives here); this one is logged (its type only) and `retired` says False
            observability.log_failure('probe_retire_failed', error, 'warning', stage='retire')
            return False

    def finish(self, report, started, item_id, swept):
        report['stages'] = {stage: round(seconds, 3) for stage, seconds in self.stages.items()}
        report['total_seconds'] = round(max(0.0, self.clock() - started), 3)
        report['item_id'] = item_id
        report['swept'] = swept
        return report


def run_probe(api, timeout, last_success=None, **options):
    """The report of one run, with the metrics recorded in the probe registry (the caller writes the file)."""
    report = Probe(api, timeout=timeout, **options).run()
    observability.record_probe(report['kairos_probe_success'] == 1, report['stages'], last_success=last_success)
    if report['status'] == 'probe_failed':
        observability.log_event('probe_failed', 'error', stage=report['stage'], code=report['code'])
    return report


def failed_setup(code, last_success=None):
    """The report of a probe that could not start (the key, the URL or the timeout is wrong, another run holds the lock): success 0, no stage ran."""
    observability.record_probe(False, {}, last_success=last_success)
    observability.log_event('probe_failed', 'error', stage=SETUP, code=code)
    return {'status': 'probe_failed', 'stage': SETUP, 'code': code, 'kairos_probe_success': 0, 'stages': {}, 'retired': None}


@contextlib.contextmanager
def terminate_as_interrupt():
    """SIGTERM (`docker stop`, a supervisor) is handled like Ctrl-C for the length of the run, so the note is retired and the metrics are written before the process ends."""
    if not hasattr(signal, 'SIGTERM') or threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def open_lock(paths):
    """The first of `paths` that can be opened for writing (created if missing) WITHOUT following a link (a planted link would lock, and create, a file of somebody else's), or None."""
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    for path in paths:
        try:
            return os.open(path, flags, 0o600)
        except OSError:
            continue
    return None


@contextlib.contextmanager
def run_lock(paths, wait, clock, sleep):
    """One run at a time (an exclusive lock on the first of `paths` that can be opened, released when the process ends whatever way): two runs would sweep and retire each other's note.
    The key file's own directory may be read-only (a key mounted read-only is the right way to mount it), so the lock then goes next to the metrics file; when no path can be opened
    or the file system refuses the lock, the run goes on WITHOUT it and says so (`probe_lock_unavailable`, a warning): a configuration problem, never `internal_error`. Waits up to
    `wait` seconds and then refuses with `busy`. No lock on a host without `fcntl` (Windows)."""
    handle = None if fcntl is None else open_lock([paths] if isinstance(paths, (str, os.PathLike)) else paths)
    locked = False
    try:
        if handle is not None:
            deadline = clock() + wait
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    if clock() >= deadline:
                        raise ProbeError('busy', 'another probe run holds the lock') from None
                    sleep(max(0.0, min(1.0, deadline - clock())))
                except OSError:  # a file system without locks (some network mounts)
                    break
        if fcntl is not None and not locked:
            observability.log_event('probe_lock_unavailable', 'warning', stage=SETUP, code='lock_unavailable')
        yield
    finally:
        if handle is not None:
            os.close(handle)


def previous_success(path):
    """The `kairos_probe_last_success_timestamp_seconds` the last run left in the metrics file (None: no file, or it never succeeded): a failed run keeps it."""
    try:
        match = LAST_SUCCESS.search(Path(path).read_text(encoding='utf-8')) if path else None
        value = float(match.group(1)) if match else None
    except (OSError, ValueError):
        return None
    return value if value and value > 0 else None


def purge_after(store_factory, report):
    """Delete for good the retired notes of `kairos-probe`: this run's (when it retired it) and every one older than PURGE_AFTER_SECONDS. A failure (no database settings, the
    database down, a project that is not the probe's, the budget spent) is logged with its code and does not change the result of the probe. Returns the number of notes purged, or None."""
    try:
        return purge_retired(store_factory(), [report['item_id']] if report.get('item_id') else [])
    except ProbeError as error:  # `project_foreign`, `purge_timeout`: nothing was deleted
        observability.log_failure('probe_purge_failed', error, 'warning', stage='retire', code=error.code)
        return None
    except Exception as error:
        observability.log_failure('probe_purge_failed', error, 'warning', stage='retire')
        return None


def queue_stuck_threshold(environ=None):
    """`MEMORY_QUEUE_STUCK_SECONDS` (default 900): how long the oldest waiting job may wait. A value that is not a positive number is logged and the default applies (a typo never switches the alert off)."""
    environ = os.environ if environ is None else environ
    text = str(environ.get('MEMORY_QUEUE_STUCK_SECONDS', '') or '').strip()
    if not text:
        return DEFAULT_QUEUE_STUCK_SECONDS
    try:
        value = float(text)
    except ValueError:
        value = 0.0
    if not 0 < value < float('inf'):  # also false for nan
        observability.log_event('probe_setting_ignored', 'warning', code='queue_stuck_seconds_invalid')
        return DEFAULT_QUEUE_STUCK_SECONDS
    return value


def queue_check(store_factory, environ=None):
    """The age of the oldest waiting job against the threshold: `{'oldest_pending_seconds', 'threshold_seconds', 'stuck'}`, or None when there is no database to ask or the read failed (the
    probe does not fail for it: the read logs its own cause). A stuck queue is logged as `queue_stuck` (warning). An empty queue is 0 seconds, never stuck."""
    try:
        store = store_factory()
    except Exception as error:  # the purge that shares this factory logs it too: the two checks are separate
        observability.log_failure('probe_queue_failed', error, 'warning', stage=SETUP)
        return None
    threshold = queue_stuck_threshold(environ)
    oldest = observability.oldest_pending_seconds(store)
    if oldest is None:
        return None
    stuck = oldest > threshold
    if stuck:
        observability.log_event('queue_stuck', 'warning', code='queue_stuck')
    return {'oldest_pending_seconds': round(oldest, 1), 'threshold_seconds': threshold, 'stuck': stuck}


def memoized(factory):
    """`factory` called at most once (its result, or its exception, is reused): the queue check and the purge share one database connection of the run."""
    made, failed = [], []

    def once():
        if failed:
            raise failed[0]
        if not made:
            try:
                made.append(factory())
            except Exception as error:
                failed.append(error)
                raise
        return made[0]
    return once


def probe_command(url, key_file, metrics_file, environ=None, api_factory=None, store_factory=None, **options):
    """`admin probe`: settings, one run, the metrics file, the purge. Returns the report (a setting that is wrong is a `probe_failed` at stage `setup`, with success 0 in the file as well).
    Whatever happens inside, the metrics file is written with the result (success 0 for an interrupt or an unexpected error); `metrics_written` says whether it was."""
    try:
        with terminate_as_interrupt():
            report = run_command(url, key_file, metrics_file, environ, api_factory, store_factory, options)
    except BaseException as error:  # an interrupt or an error outside the run itself (the transport): same ending as inside it
        observability.log_failure('probe_aborted', error, 'error', stage=SETUP)
        report = failed_setup('internal_error' if isinstance(error, Exception) else 'interrupted', previous_success(metrics_file))
    if metrics_file and 'metrics_written' not in report:  # a run that held the lock already wrote them inside it
        report['metrics_written'] = write_metrics(metrics_file)
    return report


def lock_paths(key_file, metrics_file):
    """Where the run lock may live: next to the key (as always), else next to the metrics file."""
    return [str(key_file) + LOCK_SUFFIX] + ([str(metrics_file) + LOCK_SUFFIX] if metrics_file else [])


def run_command(url, key_file, metrics_file, environ, api_factory, store_factory, options):
    """One run under the lock. The `last_success` of the metrics file is read INSIDE the lock and the file is written before the lock is released, so a run that waited never
    writes a value older than the one the run before it left. The purge comes after (it needs the database, not the lock) and only when this run knows who owns the project: not after a
    key the server refuses (`unauthorized`) and not after a signal (the container has seconds left)."""
    try:
        timeout, address, token = probe_timeout(environ), probe_url(environ, url), read_key(key_file)
    except ProbeError as error:
        return failed_setup(error.code, previous_success(metrics_file))
    clock, sleep = options.get('clock') or time.monotonic, options.get('sleep') or time.sleep
    began = clock()
    try:
        with run_lock(lock_paths(key_file, metrics_file), timeout / 2, clock, sleep):
            last_success = previous_success(metrics_file)
            api = None
            try:
                api = (api_factory or HttpApi)(address, token)  # looked up now, so a test can replace HttpApi
                report = run_probe(api, max(1.0, timeout - (clock() - began)), last_success=last_success, **options)
            finally:
                close = getattr(api, 'close', None)
                if close:
                    close()
            if metrics_file:
                report['metrics_written'] = write_metrics(metrics_file)
    except ProbeError as error:
        return failed_setup(error.code, previous_success(metrics_file))
    report['queue'] = None
    if store_factory:
        if report.get('code') in ('unauthorized', 'interrupted'):
            report['purged'] = None
        else:
            shared = memoized(store_factory)
            report['queue'] = queue_check(shared, environ)
            report['purged'] = purge_after(shared, report)
    return report


def write_metrics(path):
    """The probe series as a file (a textfile collector reads it). A failure to write it is logged (`probe_metrics_failed`) and returns False: the command then exits non-zero,
    because a monitor that keeps reading the old value is the failure this probe exists to prevent."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, observability.render_probe_metrics(), 0o644)
    except Exception as error:
        observability.log_failure('probe_metrics_failed', error, 'error', stage=SETUP, code='metrics_unwritable')
        return False
    return True


# -- the retired notes, deleted for good (n.o 3 of the review) ----------------------------------------------------------------------

def probe_state(connection, project_id):
    """(service actor row or None, project row or None, foreign?) in one place: the provisioning and the purge ask the same question. A project is FOREIGN when it exists and either has
    another title than PROBE_TITLE or has a grant to an actor other than the service account: it is somebody else's, never adopted and never purged."""
    service = connection.execute('SELECT id,is_admin,disabled,password_hash FROM memory.actors WHERE username=%s', (SERVICE_USERNAME,)).fetchone()
    existing = connection.execute('SELECT title,policy FROM memory.projects WHERE id=%s', (project_id,)).fetchone()
    foreign = bool(existing) and (existing['title'] != PROBE_TITLE or connection.execute(
        'SELECT 1 FROM memory.project_grants WHERE project_id=%s AND actor_id IS DISTINCT FROM %s LIMIT 1', (project_id, service['id'] if service else None)).fetchone() is not None)
    return service, existing, foreign


def purge_retired(store, item_ids=(), *, older_than=PURGE_AFTER_SECONDS, project_id=PROBE_PROJECT, batch=PURGE_BATCH, budget=PURGE_BUDGET, clock=time.monotonic):
    """Delete the ROWS (never a table, a column or a volume) of retired notes of the probe project: the note, its versions, its events, its jobs and receipts, its vectors and fragments.

    Selects the notes of `project_id` (only that project: every statement carries it) that are retired (`deleted`) and either are one of `item_ids` or were retired longer ago than
    `older_than` seconds, and that have no job still waiting or running (a worker may be holding it). At most `batch` notes per call. Returns the number of notes deleted.

    Nothing is deleted from a project that is not the probe's (`project_foreign`, the check of the provisioning). One transaction with ONE budget of `budget` seconds: every
    statement is limited by what is left of it, and when it is spent (`purge_timeout`) the transaction is rolled back, so the whole purge lasts about `budget` seconds."""
    began = clock()
    with store.transaction() as c:
        def step(sql, parameters):
            left = budget - (clock() - began)
            if left <= 0:
                raise ProbeError('purge_timeout', 'the purge used its whole budget')
            c.execute("SET LOCAL statement_timeout = '%dms'" % max(1, int(left * 1000)))
            return c.execute(sql, parameters)
        if probe_state(c, project_id)[2]:
            raise ProbeError('project_foreign', 'a project named kairos-probe exists and is not the probe project: nothing is purged')
        rows = step("SELECT i.id FROM memory.memory_items i WHERE i.project_id=%s AND i.deleted AND (i.id=ANY(%s) OR i.occurred_at < clock_timestamp() - make_interval(secs => %s)) "
                    "AND NOT EXISTS (SELECT 1 FROM memory.jobs j WHERE j.project_id=i.project_id AND j.item_id=i.id AND j.state IN ('pending','running','unknown')) "
                    "ORDER BY i.id LIMIT %s FOR UPDATE OF i SKIP LOCKED", (project_id, list(item_ids), float(older_than), batch)).fetchall()
        ids = [row['id'] for row in rows]
        if not ids:
            return 0
        scope = (project_id, ids)  # every statement below carries the project: no other project's row can match
        step('DELETE FROM memory.projection_receipts WHERE project_id=%s AND item_id=ANY(%s)', scope)  # before `jobs`: the receipt references the job
        step('DELETE FROM memory.embedding_chunks WHERE project_id=%s AND item_id=ANY(%s)', scope)
        step('DELETE FROM memory.embeddings WHERE project_id=%s AND item_id=ANY(%s)', scope)
        step('DELETE FROM memory.jobs WHERE project_id=%s AND item_id=ANY(%s)', scope)
        step('DELETE FROM memory.item_versions WHERE project_id=%s AND item_id=ANY(%s)', scope)
        step("DELETE FROM memory.events WHERE project_id=%s AND body->>'item_id'=ANY(%s)", (project_id, ids))
        step('DELETE FROM memory.memory_items WHERE project_id=%s AND id=ANY(%s)', (project_id, ids))
    return len(ids)


# -- provisioning (T-68) ------------------------------------------------------------------------------------------------------------

def admin_actor(store, username=None):
    """The administrator that acts for the one-off provisioning writes (the project is made by a global administrator: `create_project` asks for one): the `username` given
    (`probe-provision --as`), else the first enabled administrator. It is NOT the owner of the probe key: that is the service actor."""
    with store.transaction() as connection:
        if username:
            row = connection.execute('SELECT id FROM memory.actors WHERE username=%s AND is_admin AND NOT disabled', (username,)).fetchone()
            if not row:
                raise ProbeError('operator_unknown', 'there is no enabled administrator with that username')
        else:
            row = connection.execute('SELECT id FROM memory.actors WHERE is_admin AND NOT disabled ORDER BY username,id LIMIT 1').fetchone()
            if not row:
                raise ProbeError('no_admin', 'there is no administrator: run bootstrap first')
    return {'id': row['id'], 'credential_type': 'bootstrap'}


def valid_key(store, token, project_id, owner_id):
    """The id of the key `token` when the API itself would accept it TODAY, for the service actor `owner_id`, with read and write on exactly this project; else None.

    It goes through the same code as a request (`Auth.authenticate_bearer`, which refuses a revoked or expired key and a disabled owner, then `require_permission`, which refuses an
    owner without the grant), so there is no second copy of the access predicate to drift from it. A wider key, or one owned by anybody else, is never reused."""
    auth = Auth(store)
    try:
        actor = auth.authenticate_bearer(token)
        for permission in PROBE_SCOPES:
            auth.require_permission(actor, project_id, permission)
    except (Unauthorized, Forbidden, NotFound):
        return None
    if actor['id'] != owner_id or list(actor['project_ids']) != [project_id] or sorted(actor['scopes']) != sorted(PROBE_SCOPES):
        return None
    return actor['key_id']


def provision(store, key_file, *, project_id=PROBE_PROJECT, operator=None):
    """Idempotent: the project `kairos-probe` (created if missing, its policy set only when it differs), the service actor that owns the probe key, and a key with read and write on
    the project alone, whose token lives in `key_file` (0600).

    A second run reuses the key in the file when the API still accepts it with that exact reach and that owner; otherwise it makes a new one, writes the file and revokes the older
    probe keys. A project with that id that is not the probe's (another title, or a grant to somebody else), or an actor with that username that is not the service account, is an
    error and is not touched. Serialised by an advisory lock: two runs at once never leave both keys revoked. It writes nothing in any other project and prints no token: the report
    has the key id and the path only. `operator` names the administrator that makes the project (default: the first enabled one)."""
    path = Path(key_file)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProbeError('key_file_unsafe', 'the probe key file must be a regular file, not a link')
    import psycopg
    with store.transaction() as lock:
        try:
            lock.execute("SET LOCAL lock_timeout = '30s'")
            lock.execute('SELECT pg_advisory_xact_lock(%s)', (PROVISION_LOCK,))
        except psycopg.errors.LockNotAvailable:
            raise ProbeError('busy', 'another probe-provision is running') from None
        return provision_locked(store, path, project_id, operator)


def provision_locked(store, path, project_id, operator):
    from .auth_scope import invalidate_auth
    from .store_common import new_id
    with store.transaction() as connection:
        service, existing, foreign = probe_state(connection, project_id)
    if service and (service['is_admin'] or service['password_hash'] != SERVICE_PASSWORD_HASH):
        raise ProbeError('actor_foreign', 'a user named kairos-probe exists and is not the probe service account: rename or remove it')
    if foreign:
        raise ProbeError('project_foreign', 'a project named kairos-probe exists and is not the probe project: rename or remove it')
    if service and service['disabled']:
        raise ProbeError('actor_disabled', 'the probe service account kairos-probe is disabled: enable it or remove it')
    operator_actor = admin_actor(store, operator)  # always: `--as` is validated also when the project exists, and every change below is audited as this administrator
    if existing is None:
        store.create_project(operator_actor, {'id': project_id, 'title': PROBE_TITLE})  # audited by the store as `project.created`
    with store.transaction() as connection:
        if service is None:
            service = connection.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,false) RETURNING id', (new_id(), SERVICE_USERNAME, SERVICE_PASSWORD_HASH)).fetchone()
            store._audit(connection, operator_actor, 'user.created', resource_id=service['id'])  # the same path and action as `create_user` in store_auth
        granted = [permission for permission in SERVICE_GRANTS if connection.execute('INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1',
                                                                                    (service['id'], project_id, permission)).fetchone()]
        for _ in granted:
            store._audit(connection, operator_actor, 'grant.created', project_id, service['id'])
        if granted:
            invalidate_auth(connection)
    actor = {'id': service['id'], 'credential_type': 'bootstrap'}
    if existing is None or existing['policy'] != PROBE_POLICY:
        store.set_policy(actor, project_id, PROBE_POLICY)
    kept, file_token = None, None
    if path.is_file():
        try:
            file_token = path.read_text(encoding='utf-8').strip()
            kept = valid_key(store, file_token, project_id, service['id'])
        except (OSError, ValueError):
            kept = None
    project = 'created' if existing is None else 'present'
    if kept:
        return {'status': 'provisioned', 'project': project, 'key': 'reused', 'key_id': kept, 'key_file': str(path), 'actor': SERVICE_USERNAME}
    created = store.create_key(actor, {'name': PROBE_KEY_NAME, 'project_ids': [project_id], 'scopes': list(PROBE_SCOPES)})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, (created['token'] + '\n').encode('utf-8'), 0o600)
    except BaseException:
        store.revoke_key(actor, created['id'])  # a key nobody can read is not left active
        raise
    with store.transaction() as connection:
        store._audit(connection, operator_actor, 'probe.key_issued', project_id, created['id'])  # who ran the rotation (the key itself is signed by the service account)
        # Only what is the probe's own is rotated: the keys of the service account, and the key the file held (a key of an earlier provisioning, made by an administrator, named like
        # this one and with this reach). Any other key an administrator made with the same name stays active: it is not ours to revoke.
        file_key = connection.execute('SELECT id FROM memory.api_keys WHERE token_hash=%s', (token_hash(file_token),)).fetchone() if file_token else None
        older = [row['id'] for row in connection.execute('SELECT id,actor_id,project_ids FROM memory.api_keys WHERE name=%s AND revoked_at IS NULL AND id<>%s', (PROBE_KEY_NAME, created['id'])).fetchall()
                 if list(row['project_ids']) == [project_id] and (row['actor_id'] == service['id'] or (file_key and row['id'] == file_key['id']))]
    for key_id in older:
        store.revoke_key(actor, key_id)
    return {'status': 'provisioned', 'project': project, 'key': 'created', 'key_id': created['id'], 'key_file': str(path), 'actor': SERVICE_USERNAME}
