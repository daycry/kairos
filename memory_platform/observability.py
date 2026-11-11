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
FIELDS = ('request_id', 'layer', 'duration_ms', 'exc_type', 'code', 'status', 'method', 'route', 'destination', 'provider', 'reason', 'outcome', 'caller', 'count')
MAX_FIELD = 200
FOREIGN_LOGGERS = ('uvicorn.error',)
QUIET_LOGGERS = ('httpx', 'httpcore')
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
    setattr(handler, _MARK, True)
    root.addHandler(handler)
    return handler


def configure_logging(stream=None, level=None):
    """Make the root logger emit JSON only: one handler, every logger (kairos, uvicorn, httpx, mcp, asyncio, psycopg) propagates to it.

    Idempotent. Level: argument, else MEMORY_LOG_LEVEL, else INFO. httpx/httpcore stay at WARNING so that every request is not logged."""
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
QUEUE_STATES = ('pending', 'running', 'failed', 'unknown')  # `succeeded` is the terminal bulk of the table: never counted at scrape time
CALLERS = ('query', 'worker')
OUTCOMES = ('completed', 'failed', 'lost')
CODES = frozenset({'provider_rate_limited', 'provider_rejected', 'provider_unavailable', 'provider_transport', 'provider_invalid_json',
                   'provider_timeout', 'provider_error', 'extraction_invalid', 'embedding_invalid', 'embedding_empty_input',
                   'embedding_unverified', 'unsupported_destination'})
JOB_CODES = CODES | {'destination_retired', 'superseded'}  # codes written to memory.jobs.error_code by the worker and the store
OTHER = 'other'
QUEUE_CACHE_SECONDS = 10.0  # a loop of scrapes reads the database at most this often
QUEUE_STATEMENT_TIMEOUT_MS = 2000
_QUEUE_CACHE = {'at': None, 'ok': False}

LAYER_SECONDS = Histogram('kairos_retrieval_layer_seconds', 'Latency of each retrieval layer of a search', ['layer'], registry=REGISTRY,
                          buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30))
PROVIDER_ERRORS = Counter('kairos_provider_errors', 'Errors of the extraction and embedding providers, by code', ['provider', 'code'], registry=REGISTRY)
QUEUE_DEPTH = Gauge('kairos_jobs_queue_depth', 'Jobs in memory.jobs by state and destination, read when /metrics is served', ['state', 'destination'], registry=REGISTRY)
QUEUE_SCRAPE_SUCCESS = Gauge('kairos_jobs_queue_scrape_success', '1 when the last read of memory.jobs worked, 0 when it failed (the queue values are then the last good ones)', registry=REGISTRY)
JOBS_FAILED = Gauge('kairos_jobs_failed', 'Jobs of memory.jobs in state failed by destination and error code, read when /metrics is served (covers the worker process)',
                    ['destination', 'code'], registry=REGISTRY)
EMBED_WAIT = Histogram('kairos_embedding_wait_seconds', 'Time spent waiting for the shared embeddings slot, by caller', ['caller'], registry=REGISTRY,
                       buckets=(0.005, 0.05, 0.25, 1, 5, 15, 60, 120))
EMBED_IN_USE = Gauge('kairos_embedding_slots_in_use', 'Embeddings slots held right now, by caller', ['caller'], registry=REGISTRY)
WORKER_JOBS = Counter('kairos_worker_jobs', 'Jobs finished by this process, by destination and outcome', ['destination', 'outcome'], registry=REGISTRY)
WORKER_JOB_SECONDS = Histogram('kairos_worker_job_seconds', 'Duration of a job in this process, by destination', ['destination'], registry=REGISTRY,
                               buckets=(0.1, 0.5, 1, 5, 15, 60, 180, 600, 1200))


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


def refresh_queue_depth(store):
    """Set `kairos_jobs_queue_depth` and `kairos_jobs_failed` from memory.jobs as they are now, at most every QUEUE_CACHE_SECONDS.

    Only non-terminal states are counted (index `memory_job_queue(state, available_at)`), under a short `statement_timeout`. A database failure
    leaves the previous values, sets `kairos_jobs_queue_scrape_success` to 0 and is logged, never raised; the failed read is cached too."""
    now = time.monotonic()
    if _QUEUE_CACHE['at'] is not None and now-_QUEUE_CACHE['at'] < QUEUE_CACHE_SECONDS:
        return _QUEUE_CACHE['ok']
    _QUEUE_CACHE['at'], _QUEUE_CACHE['ok'] = now, False
    try:
        with store.transaction() as connection:
            connection.execute('SET LOCAL statement_timeout = %d' % int(QUEUE_STATEMENT_TIMEOUT_MS))
            rows = connection.execute("SELECT state, destination, count(*) AS n FROM memory.jobs WHERE state IN ('pending','running','failed','unknown') GROUP BY state, destination").fetchall()
            failed = connection.execute("SELECT destination, error_code, count(*) AS n FROM memory.jobs WHERE state='failed' GROUP BY destination, error_code").fetchall()
    except Exception as exc:
        QUEUE_SCRAPE_SUCCESS.set(0)
        log_failure('metrics_queue_unavailable', exc, 'warning')
        return False
    counts = {(state, destination): 0 for state in QUEUE_STATES for destination in DESTINATIONS}
    counts[(OTHER, OTHER)] = 0
    for row in rows:
        key = (closed(row['state'], QUEUE_STATES), closed(row['destination'], DESTINATIONS))
        if OTHER in key:
            key = (OTHER, OTHER)
        counts[key] = counts.get(key, 0)+int(row['n'])
    for (state, destination), value in counts.items():
        QUEUE_DEPTH.labels(state, destination).set(value)
    by_code = {(destination, code): 0 for destination in DESTINATIONS+(OTHER,) for code in tuple(sorted(JOB_CODES))+(OTHER,)}
    for row in failed:
        key = (closed(row['destination'], DESTINATIONS), closed(row['error_code'], JOB_CODES))
        by_code[key] = by_code.get(key, 0)+int(row['n'])
    for (destination, code), value in by_code.items():
        JOBS_FAILED.labels(destination, code).set(value)
    QUEUE_SCRAPE_SUCCESS.set(1)
    _QUEUE_CACHE['ok'] = True
    return True


def render_metrics():
    return generate_latest(REGISTRY)
