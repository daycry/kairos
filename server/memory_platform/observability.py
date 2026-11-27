"""Structured JSON logs and Prometheus metrics.

Both use closed vocabularies: a log line only carries the fields of `FIELDS` and a metric label only takes the values listed here
(anything else becomes `other`). Queries, memory content, project ids and credentials never reach either of them; string values are
redacted with the capture rules of `privacy.py` as a second barrier. Failures record the exception TYPE, never its message.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from .privacy import redact_log

LOGGER = logging.getLogger('kairos')
LOGGER.addHandler(logging.NullHandler())  # silent until `configure_logging` runs (tests, imports)
REQUEST_ID = contextvars.ContextVar('kairos_request_id', default=None)
FIELDS = ('request_id', 'layer', 'duration_ms', 'exc_type', 'code', 'status', 'method', 'route', 'destination', 'provider', 'reason', 'outcome', 'caller', 'count', 'stage', 'key_id', 'user_id')
MAX_FIELD = 200
FOREIGN_LOGGERS = ('uvicorn.error',)
QUIET_LOGGERS = ('httpx', 'httpcore')
FOREIGN_FLOOR = logging.INFO  # third-party loggers (mcp, uvicorn, asyncio, psycopg...) never emit below this level, whatever MEMORY_LOG_LEVEL says (CWE-532)
_MARK = '_kairos_json_handler'
_REMOVED = []
_REMOVED_BY = []
_STATE = {}


# --- logs -------------------------------------------------------------------------------------------------------------------------

def _clean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 3) if math.isfinite(value) else None
    if isinstance(value, str):
        return redact_log(value)[:MAX_FIELD]  # redact first: a token cut by the limit would no longer match the rules
    return None


class JsonFormatter(logging.Formatter):
    """One JSON object per line: `ts`, `level`, `event` and the known fields. Records of other loggers (uvicorn, httpx, mcp, psycopg...)
    keep their redacted, truncated text in `msg`, their logger name as `event` and, when they carry an exception, only its type."""

    def format(self, record):
        event = getattr(record, 'kairos_event', None)
        entry = {'ts': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
                 'level': record.levelname.lower(), 'event': event or _clean(record.name) or 'log'}
        fields = getattr(record, 'kairos_fields', None)
        if fields is None:
            try:
                text = record.getMessage()
            except (TypeError, ValueError, KeyError, IndexError):  # a malformed foreign record must never break the logging of the process
                text = '[unreadable log message]'
            entry['msg'] = redact_log(text)[:300]
            fields = {}
            if record.exc_info and record.exc_info[0] is not None:
                fields = {'exc_type': record.exc_info[0].__name__}  # never the message or the traceback: they may carry a DSN or a token
        for name in FIELDS:
            value = _clean(fields.get(name))
            if value is not None:
                entry[name] = value
        return json.dumps(entry, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class ForeignFloor(logging.Filter):
    """Drops the records of loggers that are not `kairos` and are below INFO.

    `MEMORY_LOG_LEVEL=DEBUG` opens the root logger, and at DEBUG third-party libraries dump what they handle (the MCP SDK logs the arguments
    of the tool calls, that is, the queries): the redaction rules would only be a second barrier. Only the `kairos` logger, whose events carry
    a closed vocabulary of fields, may go below INFO."""

    def filter(self, record):
        return record.levelno >= FOREIGN_FLOOR or record.name == 'kairos' or record.name.startswith('kairos.')


def _resolve_level(level):
    name = (level if level is not None else os.environ.get('MEMORY_LOG_LEVEL', 'INFO'))
    resolved = name if isinstance(name, int) else getattr(logging, str(name).strip().upper(), None)
    return resolved if isinstance(resolved, int) else logging.INFO


def _install(stream, level):
    root = logging.getLogger()
    for existing in list(root.handlers):
        if not getattr(existing, _MARK, False):
            root.removeHandler(existing)  # FastMCP installs a text (Rich) handler here: only our JSON one may remain
            _REMOVED.append(existing)
    ours = [h for h in root.handlers if getattr(h, _MARK, False)]
    if ours:
        return ours[0]
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ForeignFloor())
    setattr(handler, _MARK, True)
    root.addHandler(handler)
    return handler


def configure_logging(stream=None, level=None):
    """Make the root logger emit JSON only: one handler, every logger (kairos, uvicorn, httpx, mcp, asyncio, psycopg) propagates to it.

    Idempotent. Level: argument, else MEMORY_LOG_LEVEL, else INFO; it applies to `kairos` only: records of other loggers below INFO are dropped by `ForeignFloor`
    (N1, CWE-532). httpx/httpcore stay at WARNING so that every request is not logged."""
    remove_logging()
    resolved = _resolve_level(level)
    root = logging.getLogger()
    _STATE['root_level'] = root.level
    _STATE['config'] = (stream, resolved)
    handler = _install(stream, resolved)
    root.setLevel(resolved)
    for name in ('kairos',) + FOREIGN_LOGGERS:
        logger = logging.getLogger(name)
        _STATE.setdefault('levels', []).append((logger, logger.level, logger.propagate))
        logger.propagate = True
        logger.setLevel(resolved if name == 'kairos' else logging.NOTSET)
        for existing in list(logger.handlers):
            if not isinstance(existing, logging.NullHandler):
                logger.removeHandler(existing)
                _REMOVED_BY.append((logger, existing))
    for name in QUIET_LOGGERS:
        logger = logging.getLogger(name)
        _STATE['levels'].append((logger, logger.level, logger.propagate))
        logger.setLevel(max(resolved, logging.WARNING))
    return handler


def enforce_logging():
    """Re-assert the JSON-only root after a library has installed its own handler (FastMCP does when it is created). No-op until `configure_logging` ran."""
    config = _STATE.get('config')
    if config:
        _install(*config)


def remove_logging():
    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(existing)
    while _REMOVED:
        root.addHandler(_REMOVED.pop())
    while _REMOVED_BY:
        logger, handler = _REMOVED_BY.pop()
        logger.addHandler(handler)
    for logger, level, propagate in reversed(_STATE.pop('levels', [])):
        logger.setLevel(level)
        logger.propagate = propagate
    if 'root_level' in _STATE:
        root.setLevel(_STATE.pop('root_level'))
    _STATE.pop('config', None)


def log_event(event, level='info', **fields):
    """Record `event` with the known fields only; the request id of the current request is added when there is one."""
    if fields.get('request_id') is None:
        fields.pop('request_id', None)
        current = REQUEST_ID.get()
        if current:
            fields['request_id'] = current
    LOGGER.log(getattr(logging, str(level).upper(), logging.INFO), event, extra={'kairos_event': event, 'kairos_fields': fields})


def log_failure(event, exc, level='error', **fields):
    """Like `log_event` for a caught exception: its type, never its message (it may carry a DSN, a token or the user's text)."""
    log_event(event, level, exc_type=type(exc).__name__, **fields)


def elapsed_ms(started):
    return round((time.monotonic()-started)*1000, 1)


# --- metrics ----------------------------------------------------------------------------------------------------------------------

REGISTRY = CollectorRegistry()
METRICS_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'
LAYERS = ('episodic', 'documental', 'temporal', 'semantic')
PROVIDERS = ('extract', 'embed')
DESTINATIONS = ('extract', 'embed')
STATES = ('pending', 'running', 'succeeded', 'failed', 'unknown')
QUEUE_STATES = ('pending', 'running', 'failed', 'unknown')  # the series of `kairos_jobs_queue_depth`; only the non-terminal ones (`pending`, `running`, `unknown`: the worker retries them) are read by the queue query; `succeeded` and `failed` are terminal and accumulate, so the `failed` series is the sum of the failed-by-code read (partial index)
QUEUE_LIVE_STATES = ('pending', 'running', 'unknown')
CALLERS = ('query', 'worker')
OUTCOMES = ('completed', 'failed', 'lost')
CODES = frozenset({'provider_rate_limited', 'provider_rejected', 'provider_unavailable', 'provider_transport', 'provider_invalid_json',
                   'provider_timeout', 'provider_error', 'extraction_invalid', 'embedding_invalid', 'embedding_empty_input',
                   'embedding_unverified', 'unsupported_destination', 'extraction_disabled'})
JOB_CODES = CODES | {'destination_retired', 'superseded', 'attempts_exhausted', 'store_error'}  # codes written to memory.jobs.error_code by the worker and the store
OTHER = 'other'
QUEUE_CACHE_SECONDS = 10.0  # a loop of scrapes reads the database at most this often
QUEUE_STATEMENT_TIMEOUT_MS = 2000
DUE_AT = "CASE WHEN state='running' THEN lease_until ELSE available_at END"  # when a live job became the worker's to take: a pending/unknown job at `available_at`, a running one when its lease ran out
LIVE_QUEUE_SQL = ("SELECT state, destination, count(*) AS n, COALESCE(max(EXTRACT(EPOCH FROM clock_timestamp()-(%s))) FILTER (WHERE (%s) <= clock_timestamp()), 0) AS oldest "
                  "FROM memory.jobs WHERE state IN ('pending','running','unknown') GROUP BY state, destination") % (DUE_AT, DUE_AT)  # the live rows only, never the terminal bulk
_QUEUE_CACHE = {'at': None, 'ok': False}

LAYER_SECONDS = Histogram('kairos_retrieval_layer_seconds', 'Latency of each retrieval layer of a search', ['layer'], registry=REGISTRY,
                          buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))
PROVIDER_ERRORS = Counter('kairos_provider_errors', 'Errors of the extraction and embedding providers, by code', ['provider', 'code'], registry=REGISTRY)
QUEUE_DEPTH = Gauge('kairos_jobs_queue_depth', 'Jobs in memory.jobs by state and destination, read when /metrics is served', ['state', 'destination'], registry=REGISTRY)
QUEUE_SCRAPE_SUCCESS = Gauge('kairos_jobs_queue_scrape_success', '1 when the last read of memory.jobs worked, 0 when it failed (the queue values are then the last good ones)', registry=REGISTRY)
JOBS_FAILED = Gauge('kairos_jobs_failed', 'Jobs of memory.jobs in state failed by destination and error code, read when /metrics is served (covers the worker process)',
                    ['destination', 'code'], registry=REGISTRY)
OLDEST_PENDING = Gauge('kairos_jobs_oldest_pending_seconds', 'Seconds the oldest job of memory.jobs has been waiting for a worker (pending or unknown and due, or running with an expired lease; 0 with an empty queue), read when /metrics is served',
                       registry=REGISTRY)
EMBED_WAIT = Histogram('kairos_embedding_wait_seconds', 'Time spent waiting for the shared embeddings slot, by caller', ['caller'], registry=REGISTRY,
                       buckets=(0.005, 0.05, 0.25, 1, 5, 15, 60, 120))
EMBED_IN_USE = Gauge('kairos_embedding_slots_in_use', 'Embeddings slots held right now, by caller', ['caller'], registry=REGISTRY)
WORKER_JOBS = Counter('kairos_worker_jobs', 'Jobs finished by this process, by destination and outcome', ['destination', 'outcome'], registry=REGISTRY)
# The failed logins (P-05, `auth.Auth.login`): published, never a block. No label (no name, no IP: an unbounded label would be a way to fill the registry); the log line
# `login_user_failures` says which user (its id, when it exists) and how many failures its name has in the window.
LOGIN_USER_FAILURES = Counter('kairos_login_user_failures', 'Failed logins of this process (wrong password, unknown or disabled user); the log line login_user_failures says which user and how many in the window', registry=REGISTRY)
WORKER_JOB_SECONDS = Histogram('kairos_worker_job_seconds', 'Duration of a job in this process, by destination', ['destination'], registry=REGISTRY,
                               buckets=(0.1, 0.5, 1, 5, 15, 60, 180, 600, 1200))
OFFSITE_REGISTRY = CollectorRegistry()  # apart from REGISTRY: memory-api never runs a cycle, so its /metrics must not claim a result (a constant 0 would page someone)
BACKUP_OFFSITE_SUCCESS = Gauge('kairos_backup_offsite_success', '1 when the last `backup-cycle` copy reached its destination and was verified there, 0 when it did not (the copy stays local and the next cycle retries)',
                               registry=OFFSITE_REGISTRY)
PROBE_REGISTRY = CollectorRegistry()  # apart too: only `admin probe` sets these, and it writes them to a file (no process of the service serves them)
PROBE_STAGES = ('write', 'index', 'search', 'retire')
PROBE_SUCCESS = Gauge('kairos_probe_success', '1 when the last `admin probe` wrote, indexed, found and retired its synthetic memory, 0 when any stage failed', registry=PROBE_REGISTRY)
PROBE_STAGE_SECONDS = Gauge('kairos_probe_stage_seconds', 'Seconds each stage of the last `admin probe` took (a stage that did not run has no series)', ['stage'], registry=PROBE_REGISTRY)
PROBE_LAST_RUN = Gauge('kairos_probe_last_run_timestamp_seconds', 'Unix time at which the last `admin probe` finished, whatever its result', registry=PROBE_REGISTRY)
PROBE_LAST_SUCCESS = Gauge('kairos_probe_last_success_timestamp_seconds', 'Unix time at which the last `admin probe` that succeeded finished (0: none yet); a failed run keeps the value of the file it read', registry=PROBE_REGISTRY)
BACKUP_OFFSITE_LAST_RUN = Gauge('kairos_backup_offsite_last_run_timestamp_seconds', 'Unix time at which the last `backup-cycle` finished its offsite stage, whatever its result', registry=OFFSITE_REGISTRY)


def closed(value, allowed):
    """`value` when it belongs to the closed set, otherwise `other`: a label can never carry free text."""
    return value if isinstance(value, str) and value in allowed else OTHER


def observe_layer(layer, seconds):
    LAYER_SECONDS.labels(closed(layer, LAYERS)).observe(max(0.0, seconds))


def record_layer(layer, seconds, status=None):
    """One executed retrieval layer: metric and log line (`duration_ms`, `layer`, the request id of the current request)."""
    observe_layer(layer, seconds)
    log_event('retrieval_layer', layer=closed(layer, LAYERS), duration_ms=round(seconds*1000, 1), status=status)


def count_provider_error(provider, code):
    PROVIDER_ERRORS.labels(closed(provider, PROVIDERS), closed(code, CODES)).inc()


def record_job(destination, seconds, outcome):
    destination = closed(destination, DESTINATIONS)
    WORKER_JOBS.labels(destination, closed(outcome, OUTCOMES)).inc()
    WORKER_JOB_SECONDS.labels(destination).observe(max(0.0, seconds))


async def acquire_embedding_slot(semaphore, caller):
    """Take the shared embeddings slot, measuring the wait even when the caller gives up (cancelled/timed out) while waiting."""
    caller = closed(caller, CALLERS)
    started = time.monotonic()
    try:
        await semaphore.acquire()
    finally:
        EMBED_WAIT.labels(caller).observe(time.monotonic()-started)
    EMBED_IN_USE.labels(caller).inc()
    return caller


def release_embedding_slot(semaphore, caller):
    EMBED_IN_USE.labels(caller).dec()
    semaphore.release()


@contextlib.asynccontextmanager
async def embedding_slot(semaphore, caller):
    held = await acquire_embedding_slot(semaphore, caller)
    try:
        yield
    finally:
        release_embedding_slot(semaphore, held)


def reset_queue_cache():
    _QUEUE_CACHE['at'] = None


def _read(store, sql, event):
    """Rows of one scrape query in its OWN transaction and short `statement_timeout`, or None (logged, never raised) when it failed:
    a slow or failing query cannot take the other one down with it."""
    try:
        with store.transaction() as connection:
            connection.execute('SET LOCAL statement_timeout = %d' % int(QUEUE_STATEMENT_TIMEOUT_MS))
            return connection.execute(sql).fetchall()
    except Exception as exc:
        log_failure(event, exc, 'warning')
        return None


def oldest_of(rows):
    """The largest `oldest` of the rows of `LIVE_QUEUE_SQL` (0.0 for no rows, a missing or a malformed age): an empty queue is never stuck."""
    oldest = 0.0
    for row in rows:
        try:
            oldest = max(oldest, float(row.get('oldest') or 0))
        except (TypeError, ValueError, AttributeError):
            continue
    return oldest


def oldest_pending_seconds(store):
    """How long the oldest waiting job has waited, in seconds (0.0: none), or None (logged, never raised) when the read failed: the probe compares it with MEMORY_QUEUE_STUCK_SECONDS."""
    rows = _read(store, LIVE_QUEUE_SQL, 'queue_age_unavailable')
    return None if rows is None else oldest_of(rows)


def refresh_queue_depth(store):
    """Set `kairos_jobs_queue_depth` and `kairos_jobs_failed` from memory.jobs as they are now, at most every QUEUE_CACHE_SECONDS.

    Two independent reads, each in its own transaction under a short `statement_timeout`: the counts of the non-terminal states (`pending`, `running`, `unknown`; never the
    terminal rows `succeeded` or `failed`: index `memory_job_queue(state, available_at)`) and the failed jobs by destination and code (partial index `memory_jobs_failed_code`, version 11),
    whose total by destination is also the `failed` series of `kairos_jobs_queue_depth`.
    A read that fails leaves the previous values of ITS series and is logged; the other series is still refreshed. Either failure sets
    `kairos_jobs_queue_scrape_success` to 0 and makes the call return False; nothing is ever raised. The failed read is cached too."""
    now = time.monotonic()
    if _QUEUE_CACHE['at'] is not None and now-_QUEUE_CACHE['at'] < QUEUE_CACHE_SECONDS:
        return _QUEUE_CACHE['ok']
    _QUEUE_CACHE['at'], _QUEUE_CACHE['ok'] = now, False
    rows = _read(store, LIVE_QUEUE_SQL, 'metrics_queue_unavailable')
    failed = _read(store, "SELECT destination, error_code, count(*) AS n FROM memory.jobs WHERE state='failed' GROUP BY destination, error_code", 'metrics_failed_unavailable')
    if rows is not None:
        counts = {(state, destination): 0 for state in QUEUE_STATES for destination in DESTINATIONS}
        counts[(OTHER, OTHER)] = 0
        for row in rows:
            key = (closed(row['state'], QUEUE_LIVE_STATES), closed(row['destination'], DESTINATIONS))
            if OTHER in key:
                key = (OTHER, OTHER)
            counts[key] = counts.get(key, 0)+int(row['n'])
        for (state, destination), value in counts.items():
            if state != 'failed':
                QUEUE_DEPTH.labels(state, destination).set(value)
        OLDEST_PENDING.set(oldest_of(rows))
    if failed is not None:
        failed_depth = {destination: 0 for destination in DESTINATIONS+(OTHER,)}  # `other` lives in `kairos_jobs_failed`; the queue series `other` is for the live read
        by_code = {(destination, code): 0 for destination in DESTINATIONS+(OTHER,) for code in tuple(sorted(JOB_CODES))+(OTHER,)}
        for row in failed:
            key = (closed(row['destination'], DESTINATIONS), closed(row['error_code'], JOB_CODES))
            by_code[key] = by_code.get(key, 0)+int(row['n'])
            failed_depth[key[0]] += int(row['n'])
        for (destination, code), value in by_code.items():
            JOBS_FAILED.labels(destination, code).set(value)
        for destination in DESTINATIONS:
            QUEUE_DEPTH.labels('failed', destination).set(failed_depth[destination])
    ok = rows is not None and failed is not None
    QUEUE_SCRAPE_SUCCESS.set(1 if ok else 0)
    _QUEUE_CACHE['ok'] = ok
    return ok


def record_offsite(ok, now=None):
    """The result of the offsite stage of one `backup-cycle`: `kairos_backup_offsite_success` 1 or 0 and the time it finished."""
    BACKUP_OFFSITE_SUCCESS.set(1 if ok else 0)
    BACKUP_OFFSITE_LAST_RUN.set(time.time() if now is None else now)


def record_probe(ok, stages, now=None, last_success=None):
    """The result of one `admin probe`: `kairos_probe_success` 1 or 0, the seconds of every stage that ran (`stages` {stage: seconds}), the time it finished and, when it succeeded,
    the time of the last success (a failure keeps `last_success`, the value the previous run left in the metrics file, when there is one)."""
    PROBE_SUCCESS.set(1 if ok else 0)
    PROBE_STAGE_SECONDS.clear()
    for stage, seconds in stages.items():
        PROBE_STAGE_SECONDS.labels(closed(stage, PROBE_STAGES)).set(max(0.0, float(seconds)))
    finished = time.time() if now is None else now
    PROBE_LAST_RUN.set(finished)
    if ok:
        PROBE_LAST_SUCCESS.set(finished)
    elif last_success is not None:
        PROBE_LAST_SUCCESS.set(last_success)


def render_probe_metrics():
    """Only the four probe series, in the text exposition format (`admin probe --metrics-file` writes them; a textfile collector reads them)."""
    return generate_latest(PROBE_REGISTRY)


def render_offsite_metrics():
    """Only the two offsite series, in the text exposition format: `backup-cycle` writes them to a file (a textfile collector reads them; no process of the service serves HTTP)."""
    return generate_latest(OFFSITE_REGISTRY)


def render_metrics():
    return generate_latest(REGISTRY)
