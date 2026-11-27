"""Explicit process configuration. Importing this module has no side effects."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def secret(name: str, *, required: bool = False) -> str:
    filename = os.environ.get(name + '_FILE')
    value = Path(filename).read_text(encoding='utf-8').strip() if filename else os.environ.get(name, '').strip()
    if required and not value:
        raise ValueError(f'{name}_FILE must identify a configured secret')
    return value


def endpoint(name: str, default: str) -> str:
    value = os.environ.get(name, default).rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f'{name} must be an HTTP(S) endpoint without credentials or query')
    return value


DEFAULT_VECTOR_INDEXES = 'nomic-embed-text:768'
HNSW_MAX_DIMENSIONS = 2000  # pgvector indexes `vector` up to 2,000 dimensions
HNSW_EF_SEARCH = 100  # hnsw.ef_search, per transaction
HNSW_MAX_SCAN_TUPLES = 20000  # hnsw.max_scan_tuples with hnsw.iterative_scan = relaxed_order
EXACT_CANDIDATE_LIMIT = 10000  # exact route: candidates scored per query


def vector_indexes(environ=None) -> tuple:
    """(model, dimensions) pairs that get a partial HNSW index; everything else uses the exact route.

    MEMORY_VECTOR_INDEXES="model:dims,model:dims" (the model name may itself contain ':').
    """
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_VECTOR_INDEXES', DEFAULT_VECTOR_INDEXES)
    result = []
    for entry in (part.strip() for part in raw.split(',')):
        if not entry:
            continue
        model, separator, dims = entry.rpartition(':')
        if not separator or not model.strip() or len(model) > 200 or not dims.isdigit() or not 1 <= int(dims) <= HNSW_MAX_DIMENSIONS:
            raise ValueError(f'MEMORY_VECTOR_INDEXES entries must be model:dimensions with 1..{HNSW_MAX_DIMENSIONS} dimensions')
        pair = (model, int(dims))
        if pair in result:
            raise ValueError('MEMORY_VECTOR_INDEXES contains a duplicate entry')
        result.append(pair)
    return tuple(result)


DEFAULT_EXACT_FALLBACK_MS = 1500


def exact_fallback_ms(environ=None) -> int:
    """Own statement_timeout (ms) of the exact fallback after a short HNSW answer; MEMORY_VECTOR_EXACT_FALLBACK_MS."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_VECTOR_EXACT_FALLBACK_MS', str(DEFAULT_EXACT_FALLBACK_MS)).strip()
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 600000:
        raise ValueError('MEMORY_VECTOR_EXACT_FALLBACK_MS must be a positive integer of milliseconds (1 to 600000)')
    return int(value)


DEFAULT_MIGRATION_MAINTENANCE_WORK_MEM = '256MB'


def migration_maintenance_work_mem(environ=None) -> str:
    """maintenance_work_mem for the migration transaction (HNSW builds); MEMORY_MIGRATION_MAINTENANCE_WORK_MEM."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_MIGRATION_MAINTENANCE_WORK_MEM', DEFAULT_MIGRATION_MAINTENANCE_WORK_MEM).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,5}(kB|MB|GB)', value):
        raise ValueError('MEMORY_MIGRATION_MAINTENANCE_WORK_MEM must be a size such as 256MB')
    return value


DEFAULT_CHUNK_CHARS, DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_MAX, DEFAULT_EMBED_BATCH = 1500, 200, 200, 8
CHUNK_CHARS_RANGE = (200, 6000)  # the provider cuts an input at 8,000 characters: a fragment must never reach it
CHUNK_MAX_LIMIT = 500


def chunk_settings(environ=None) -> tuple:
    """(chunk characters, overlap, maximum fragments); MEMORY_CHUNK_CHARS / MEMORY_CHUNK_OVERLAP / MEMORY_CHUNK_MAX.

    Decision P-07: 1,500 characters with a 200-character overlap. The overlap must stay below half of the fragment.
    """
    environ = os.environ if environ is None else environ

    def read(name, default):
        value = environ.get(name, str(default)).strip()
        if not value.isascii() or not value.isdigit():
            raise ValueError(f'{name} must be a non-negative integer')
        return int(value)
    chars, overlap, maximum = read('MEMORY_CHUNK_CHARS', DEFAULT_CHUNK_CHARS), read('MEMORY_CHUNK_OVERLAP', DEFAULT_CHUNK_OVERLAP), read('MEMORY_CHUNK_MAX', DEFAULT_CHUNK_MAX)
    if not CHUNK_CHARS_RANGE[0] <= chars <= CHUNK_CHARS_RANGE[1]:
        raise ValueError('MEMORY_CHUNK_CHARS must be between %d and %d' % CHUNK_CHARS_RANGE)
    if overlap * 2 >= chars:
        raise ValueError('MEMORY_CHUNK_OVERLAP must be below half of MEMORY_CHUNK_CHARS')
    if not 1 <= maximum <= CHUNK_MAX_LIMIT:
        raise ValueError(f'MEMORY_CHUNK_MAX must be between 1 and {CHUNK_MAX_LIMIT}')
    return chars, overlap, maximum


def embed_batch_size(environ=None) -> int:
    """Fragments sent to /api/embed per request (MEMORY_EMBED_BATCH)."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_EMBED_BATCH', str(DEFAULT_EMBED_BATCH)).strip()
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 64:
        raise ValueError('MEMORY_EMBED_BATCH must be an integer between 1 and 64')
    return int(value)


DEFAULT_EMBED_BATCH_TIMEOUT, DEFAULT_EMBED_JOB_MAX_TIMEOUT = 60.0, 900.0
DEFAULT_BACKOFF_MAX = 60.0


def worker_db_backoff_max(environ=None) -> float:
    """Longest wait, in seconds, of the worker between two claims while the database does not answer (MEMORY_WORKER_DB_BACKOFF_MAX, 1 to 3600)."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_WORKER_DB_BACKOFF_MAX', str(DEFAULT_BACKOFF_MAX)).strip()
    try:
        value = float(raw)
    except ValueError:
        raise ValueError('MEMORY_WORKER_DB_BACKOFF_MAX must be a number of seconds between 1 and 3600') from None
    if not 1 <= value <= 3600:  # also rejects NaN
        raise ValueError('MEMORY_WORKER_DB_BACKOFF_MAX must be a number of seconds between 1 and 3600')
    return value


def worker_write_retry_seconds(environ=None, lease_seconds=240):
    """Longest the worker keeps repeating the write of the OUTCOME of a job (`complete_job`/`fail_job`) once it failed, counted from the first failure
    (MEMORY_WORKER_WRITE_RETRY_SECONDS, 1 to 86400; default: the lease, MEMORY_LEASE_SECONDS). Past it the worker stops renewing the lease and the job goes
    back to the queue when the lease ends."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_WORKER_WRITE_RETRY_SECONDS', '').strip()
    # The lease fits its range whether or not the budget is set: it is the budget's default, and the heartbeat and every wait of the worker are derived from it.
    if not 1 <= float(lease_seconds) <= 86400:
        raise ValueError('MEMORY_LEASE_SECONDS must be between 1 and 86400 seconds (it is also the default of MEMORY_WORKER_WRITE_RETRY_SECONDS)')
    if not raw:
        return float(lease_seconds)
    try:
        value = float(raw)
    except ValueError:
        raise ValueError('MEMORY_WORKER_WRITE_RETRY_SECONDS must be a number of seconds between 1 and 86400') from None
    if not 1 <= value <= 86400:  # also rejects NaN
        raise ValueError('MEMORY_WORKER_WRITE_RETRY_SECONDS must be a number of seconds between 1 and 86400')
    return value


DEFAULT_POOL_MIN, DEFAULT_POOL_MAX, DEFAULT_POOL_TIMEOUT = 1, 10, 5.0
DEFAULT_LOGIN_CONCURRENCY, LOGIN_CONCURRENCY_LIMIT = 2, 32  # scrypt derivations of the API at once (~128 MB each); 2 fits a 1 GB `memory-api`, see improvement-plan.md, «Valores medidos»


def check_login_concurrency(slots):
    if isinstance(slots, bool) or not isinstance(slots, int) or not 1 <= slots <= LOGIN_CONCURRENCY_LIMIT:
        raise ValueError(f'MEMORY_LOGIN_CONCURRENCY must be a whole number between 1 and {LOGIN_CONCURRENCY_LIMIT}')
    return slots


def login_concurrency(environ=None) -> int:
    """The slots of the gate of password derivations (MEMORY_LOGIN_CONCURRENCY): a whole number, 1 to 32, default 2."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_LOGIN_CONCURRENCY', str(DEFAULT_LOGIN_CONCURRENCY))
    if not raw.isascii() or not raw.isdigit():
        raise ValueError(f'MEMORY_LOGIN_CONCURRENCY must be a whole number between 1 and {LOGIN_CONCURRENCY_LIMIT}')
    return check_login_concurrency(int(raw))


# The block of the login by the IP of the client (CA-13, P-05; `limits.py`): MEMORY_LOGIN_MAX_FAILURES failures of one IP within MEMORY_LOGIN_WINDOW seconds answer 429 `rate_limited`.
DEFAULT_LOGIN_MAX_FAILURES, LOGIN_MAX_FAILURES_LIMIT = 10, 1000
DEFAULT_LOGIN_WINDOW, LOGIN_WINDOW_RANGE = 900, (60, 86400)
LOGIN_FAILURES_ERROR = (f'MEMORY_LOGIN_MAX_FAILURES must be a whole number between 1 and {LOGIN_MAX_FAILURES_LIMIT}, and MEMORY_LOGIN_WINDOW a whole number of seconds '
                        f'between {LOGIN_WINDOW_RANGE[0]} and {LOGIN_WINDOW_RANGE[1]}')


def check_login_failures(max_failures, window):
    for value, low, high in ((max_failures, 1, LOGIN_MAX_FAILURES_LIMIT), (window, *LOGIN_WINDOW_RANGE)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(LOGIN_FAILURES_ERROR)
    return max_failures, window


def login_failure_settings(environ=None):
    """(MEMORY_LOGIN_MAX_FAILURES, MEMORY_LOGIN_WINDOW): whole numbers, 1 to 1000 failures (default 10) in 60 to 86400 seconds (default 900, 15 minutes)."""
    environ = os.environ if environ is None else environ
    raw = (environ.get('MEMORY_LOGIN_MAX_FAILURES', str(DEFAULT_LOGIN_MAX_FAILURES)), environ.get('MEMORY_LOGIN_WINDOW', str(DEFAULT_LOGIN_WINDOW)))
    if not all(value.isascii() and value.isdigit() for value in raw):
        raise ValueError(LOGIN_FAILURES_ERROR)
    return check_login_failures(int(raw[0]), int(raw[1]))
POOL_MAX_LIMIT = 100


def check_pool(minimum, maximum, timeout):
    """The sizes and the wait of the connection pool (MEMORY_POOL_MIN / MEMORY_POOL_MAX / MEMORY_POOL_TIMEOUT): whole numbers, 1 <= min <= max <= 100, and a wait of 0.1 to 300 seconds
    (a pool that waits for ever, or not at all, is the hang or the error storm this setting exists to prevent)."""
    if isinstance(minimum, bool) or isinstance(maximum, bool) or not isinstance(minimum, int) or not isinstance(maximum, int) or not 1 <= minimum <= maximum <= POOL_MAX_LIMIT:
        raise ValueError(f'MEMORY_POOL_MIN and MEMORY_POOL_MAX must be whole numbers with 1 <= MEMORY_POOL_MIN <= MEMORY_POOL_MAX <= {POOL_MAX_LIMIT}')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 300:  # also rejects NaN
        raise ValueError('MEMORY_POOL_TIMEOUT must be a number of seconds between 0.1 and 300')


DEFAULT_CONNECT_TIMEOUT = 3  # below the default MEMORY_POOL_TIMEOUT (5 s): a database that does not answer is `service_unavailable` (see `check_timeout_pair`)
CONNECT_TIMEOUT_RANGE = (2, 120)  # libpq never waits less than 2 seconds for a connection: 1 would be read as 2
DEFAULT_STATEMENT_TIMEOUT_MS = {'api': 15000, 'worker': 30000}  # per role; below `request_timeout` (30 s) for the API
STATEMENT_TIMEOUT_RANGE_MS = (100, 3600000)


def check_timeouts(connect, statement):
    """`connect` (MEMORY_CONNECT_TIMEOUT, whole seconds, 2 to 120) and `statement` (MEMORY_STATEMENT_TIMEOUT_MS, whole milliseconds, 100 to 3,600,000, or None for the default of
    the role). Neither can be 0 or unbounded: that is the hang this setting exists to remove."""
    if isinstance(connect, bool) or not isinstance(connect, int) or not CONNECT_TIMEOUT_RANGE[0] <= connect <= CONNECT_TIMEOUT_RANGE[1]:
        raise ValueError('MEMORY_CONNECT_TIMEOUT must be a whole number of seconds between %d and %d' % CONNECT_TIMEOUT_RANGE)
    if statement is not None and (isinstance(statement, bool) or not isinstance(statement, int) or not STATEMENT_TIMEOUT_RANGE_MS[0] <= statement <= STATEMENT_TIMEOUT_RANGE_MS[1]):
        raise ValueError('MEMORY_STATEMENT_TIMEOUT_MS must be a whole number of milliseconds between %d and %d' % STATEMENT_TIMEOUT_RANGE_MS)


POOL_CONNECT_GAP = 1.0  # seconds MEMORY_POOL_TIMEOUT and MEMORY_CONNECT_TIMEOUT must differ by


def check_timeout_pair(connect, pool_timeout):
    """`MEMORY_CONNECT_TIMEOUT` and `MEMORY_POOL_TIMEOUT` must differ by at least a second. With a connect plazo SHORTER than the pool wait a silent database makes the connection fail inside
    the wait (503 `service_unavailable`); with a LONGER one the attempt is still going when the wait ends (503 `store_busy`). Equal or almost equal, which of the two it was would be a race
    between two timers, so that case is refused at the start instead of being answered at random."""
    if abs(float(connect) - float(pool_timeout)) < POOL_CONNECT_GAP:
        raise ValueError('MEMORY_POOL_TIMEOUT and MEMORY_CONNECT_TIMEOUT must differ by at least %d second: when they are close, a database that does not answer is reported as store_busy or '
                         'service_unavailable depending on a race (a connect plazo below the pool wait is an outage; above it, a busy pool)' % POOL_CONNECT_GAP)


DEFAULT_TCP = {'idle': 30, 'interval': 10, 'count': 3, 'user_timeout_ms': 30000}  # TCP keepalives and TCP_USER_TIMEOUT of the service connections: a dead peer is noticed in ~60 s, not in 15 minutes
TCP_RANGES = {'idle': (1, 7200), 'interval': (1, 600), 'count': (1, 20), 'user_timeout_ms': (1000, 3600000)}
TCP_VARIABLES = {'idle': 'MEMORY_TCP_KEEPALIVES_IDLE', 'interval': 'MEMORY_TCP_KEEPALIVES_INTERVAL', 'count': 'MEMORY_TCP_KEEPALIVES_COUNT', 'user_timeout_ms': 'MEMORY_TCP_USER_TIMEOUT_MS'}


def check_tcp(idle, interval, count, user_timeout_ms):
    """Whole numbers inside TCP_RANGES (seconds for idle and interval, a number of probes for count, milliseconds for the user timeout)."""
    for key, value in (('idle', idle), ('interval', interval), ('count', count), ('user_timeout_ms', user_timeout_ms)):
        low, high = TCP_RANGES[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError('%s must be a whole number between %d and %d' % (TCP_VARIABLES[key], low, high))


def tcp_settings(environ=None) -> tuple:
    """(keepalives idle, interval, count, tcp user timeout in ms) of the service connections, from MEMORY_TCP_KEEPALIVES_IDLE / _INTERVAL / _COUNT and MEMORY_TCP_USER_TIMEOUT_MS."""
    environ = os.environ if environ is None else environ
    values = {}
    for key, name in TCP_VARIABLES.items():
        raw = environ.get(name, '').strip()
        if raw and (not raw.isascii() or not raw.isdigit()):
            raise ValueError(f'{name} must be a whole number')
        values[key] = int(raw) if raw else DEFAULT_TCP[key]
    check_tcp(values['idle'], values['interval'], values['count'], values['user_timeout_ms'])
    return values['idle'], values['interval'], values['count'], values['user_timeout_ms']


def connection_timeouts(environ=None) -> tuple:
    """(connect timeout in seconds, statement timeout in milliseconds or None) of the service connections, from MEMORY_CONNECT_TIMEOUT (default 3) and
    MEMORY_STATEMENT_TIMEOUT_MS (unset: 15,000 in the API and 30,000 in the worker; set: that value in both). `admin` never applies them."""
    environ = os.environ if environ is None else environ

    def whole(name, raw):
        raw = raw.strip()
        if not raw.isascii() or not raw.isdigit():
            raise ValueError(f'{name} must be a whole number')
        return int(raw)
    connect = whole('MEMORY_CONNECT_TIMEOUT', environ.get('MEMORY_CONNECT_TIMEOUT', str(DEFAULT_CONNECT_TIMEOUT)))
    raw = environ.get('MEMORY_STATEMENT_TIMEOUT_MS', '').strip()
    statement = whole('MEMORY_STATEMENT_TIMEOUT_MS', raw) if raw else None
    check_timeouts(connect, statement)
    return connect, statement


def service_statement_timeout(settings, role) -> int:
    """Milliseconds of `statement_timeout` for the connections of `role` (`api` or `worker`)."""
    return settings.statement_timeout_ms if settings.statement_timeout_ms is not None else DEFAULT_STATEMENT_TIMEOUT_MS[role]


def pool_settings(environ=None) -> tuple:
    """(minimum, maximum, wait in seconds) of the connection pool of the API and of the worker, from MEMORY_POOL_MIN / MEMORY_POOL_MAX / MEMORY_POOL_TIMEOUT."""
    environ = os.environ if environ is None else environ

    def whole(name, default):
        raw = environ.get(name, str(default)).strip()
        if not raw.isascii() or not raw.isdigit():
            raise ValueError(f'{name} must be a whole number')
        return int(raw)
    minimum, maximum = whole('MEMORY_POOL_MIN', DEFAULT_POOL_MIN), whole('MEMORY_POOL_MAX', DEFAULT_POOL_MAX)
    raw = environ.get('MEMORY_POOL_TIMEOUT', str(DEFAULT_POOL_TIMEOUT)).strip()
    try:
        timeout = float(raw)
    except ValueError:
        raise ValueError('MEMORY_POOL_TIMEOUT must be a number of seconds between 0.1 and 300') from None
    check_pool(minimum, maximum, timeout)
    return minimum, maximum, timeout


# Retention of the tables that only grow (decision P-03): the days after which `admin prune-tables` may delete a row, per table. `events` has NO window by default:
# `event_status`, the activity feed and `get_tool_uses` read it, so deleting from it changes answers clients see (see docs/operations.md).
RETENTION_DEFAULTS = {'login_attempts': 30, 'web_sessions': 30, 'audit_events': 365, 'jobs': 90, 'events': None}
RETENTION_VARIABLES = {'login_attempts': 'MEMORY_RETENTION_LOGIN_ATTEMPTS_DAYS', 'web_sessions': 'MEMORY_RETENTION_WEB_SESSIONS_DAYS',
                       'audit_events': 'MEMORY_RETENTION_AUDIT_EVENTS_DAYS', 'jobs': 'MEMORY_RETENTION_JOBS_FAILED_DAYS', 'events': 'MEMORY_RETENTION_EVENTS_DAYS'}
RETENTION_MAX_DAYS = 36500


def retention_windows(environ=None) -> dict:
    """{table: days or None} from the `MEMORY_RETENTION_*_DAYS` variables: an integer between 1 and 36500; blank or unset is the default of P-03 (None for `events`: never
    pruned). Only `admin prune-tables` reads them, so only it refuses an invalid value."""
    environ = os.environ if environ is None else environ
    windows = {}
    for table, name in RETENTION_VARIABLES.items():
        raw = environ.get(name, '').strip()
        if not raw:
            windows[table] = RETENTION_DEFAULTS[table]
            continue
        if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= RETENTION_MAX_DAYS:
            raise ValueError(f'{name} must be an integer number of days between 1 and {RETENTION_MAX_DAYS}')
        windows[table] = int(raw)
    return windows


BACKUP_KEEP_DEFAULT = 7
BACKUP_KEEP_MAX = 100000


def backup_recipients_file(environ=None):
    """MEMORY_BACKUP_RECIPIENTS_FILE: the file of public `age` recipients the copies are encrypted for; blank or unset is None (no encryption unless it is required)."""
    environ = os.environ if environ is None else environ
    return environ.get('MEMORY_BACKUP_RECIPIENTS_FILE', '').strip() or None


def backup_require_encryption(environ=None) -> bool:
    """MEMORY_BACKUP_REQUIRE_ENCRYPTION: with it on, a copy without recipients fails instead of being written in the clear. Anything that is not a clear yes or no is an
    error (a typo must not turn the requirement off)."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_BACKUP_REQUIRE_ENCRYPTION', '').strip().lower()
    if raw in ('1', 'true', 'yes', 'on'):
        return True
    if raw in ('', '0', 'false', 'no', 'off'):
        return False
    raise ValueError('MEMORY_BACKUP_REQUIRE_ENCRYPTION must be 1/true/yes/on or 0/false/no/off')


def backup_keep(environ=None) -> int:
    """MEMORY_BACKUP_KEEP: the copies `backup --prune` keeps when `--keep` is not given (default 7); an integer of 1 or more."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_BACKUP_KEEP', '').strip()
    if not raw:
        return BACKUP_KEEP_DEFAULT
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= BACKUP_KEEP_MAX:
        raise ValueError(f'MEMORY_BACKUP_KEEP must be an integer between 1 and {BACKUP_KEEP_MAX}')
    return int(raw)


BACKUP_REMOTE_KEEP_DEFAULT = 30
BACKUP_INTERVAL_DEFAULT = '24h'
BACKUP_INTERVAL_UNITS = {'': 1, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}
BACKUP_INTERVAL_MAX_SECONDS = 30 * 86400


def backup_destination(environ=None):
    """MEMORY_BACKUP_DESTINATION: where `backup-cycle` sends the copies (`dir:<absolute path>` or `rclone:<remote>:<path>`); blank or unset is None (no destination: the cycle refuses to run)."""
    environ = os.environ if environ is None else environ
    return environ.get('MEMORY_BACKUP_DESTINATION', '').strip() or None


def backup_remote_keep(environ=None) -> int:
    """MEMORY_BACKUP_REMOTE_KEEP: the copies `backup-cycle` keeps at the destination (default 30); an integer of 1 or more."""
    environ = os.environ if environ is None else environ
    raw = environ.get('MEMORY_BACKUP_REMOTE_KEEP', '').strip()
    if not raw:
        return BACKUP_REMOTE_KEEP_DEFAULT
    if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= BACKUP_KEEP_MAX:
        raise ValueError(f'MEMORY_BACKUP_REMOTE_KEEP must be an integer between 1 and {BACKUP_KEEP_MAX}')
    return int(raw)


def backup_interval_seconds(environ=None) -> int:
    """MEMORY_BACKUP_INTERVAL: the time between two cycles of `backup-cycle --loop` (default 24h): a whole number with an optional unit s, m, h or d (no unit: seconds), from 1 second to 30 days."""
    environ = os.environ if environ is None else environ
    raw = (environ.get('MEMORY_BACKUP_INTERVAL', '').strip() or BACKUP_INTERVAL_DEFAULT).lower()
    number, unit = raw[:-1] if raw[-1:] in 'smhd' and raw[-1:] else raw, raw[-1:] if raw[-1:] in 'smhd' and raw[-1:] else ''
    if not number.isascii() or not number.isdigit() or not 1 <= int(number) * BACKUP_INTERVAL_UNITS[unit] <= BACKUP_INTERVAL_MAX_SECONDS:
        raise ValueError('MEMORY_BACKUP_INTERVAL must be a duration such as 90s, 30m, 24h or 1d (from 1 second to 30 days)')
    return int(number) * BACKUP_INTERVAL_UNITS[unit]


def max_attempts(environ=None) -> int:
    """MEMORY_MAX_ATTEMPTS: the attempts a job is allowed (also the cap of claims of a job whose lease expires). An integer of 1 or more: with 0 or a negative
    number a job would never run or would be failed as `attempts_exhausted` on its first lost lease."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_MAX_ATTEMPTS', '3').strip()
    if not value.isascii() or not value.isdigit() or int(value) < 1:
        raise ValueError('MEMORY_MAX_ATTEMPTS must be an integer of 1 or more')
    return int(value)


def embed_timeouts(environ=None) -> tuple:
    """(deadline per batch, global ceiling of one embed job) in seconds; MEMORY_EMBED_BATCH_TIMEOUT / MEMORY_EMBED_JOB_MAX_TIMEOUT."""
    environ = os.environ if environ is None else environ

    def read(name, default, low, high):
        raw = environ.get(name, str(default)).strip()
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f'{name} must be a number of seconds between {low} and {high}') from None
        if not low <= value <= high:  # also rejects NaN
            raise ValueError(f'{name} must be a number of seconds between {low} and {high}')
        return value
    batch = read('MEMORY_EMBED_BATCH_TIMEOUT', DEFAULT_EMBED_BATCH_TIMEOUT, 1, 600)
    ceiling = read('MEMORY_EMBED_JOB_MAX_TIMEOUT', DEFAULT_EMBED_JOB_MAX_TIMEOUT, 1, 3600)
    if ceiling < batch:
        raise ValueError('MEMORY_EMBED_JOB_MAX_TIMEOUT must not be below MEMORY_EMBED_BATCH_TIMEOUT')
    return batch, ceiling


def embedding_job_timeout(settings, inputs: int) -> float:
    """Deadline of one embed job that sends `inputs` texts: one embedding keeps `embedding_worker_timeout`; several get
    `embedding_batch_timeout` for every batch of `embedding_batch_size`, never above the global ceiling (and never below the single-text deadline)."""
    single = getattr(settings, 'embedding_worker_timeout', 120.0)
    if inputs <= 1:
        return single
    size = max(1, int(getattr(settings, 'embedding_batch_size', DEFAULT_EMBED_BATCH)))
    batches = -(-inputs // size)
    ceiling = max(getattr(settings, 'embedding_job_timeout_max', DEFAULT_EMBED_JOB_MAX_TIMEOUT), single)
    return min(ceiling, max(single, batches * getattr(settings, 'embedding_batch_timeout', DEFAULT_EMBED_BATCH_TIMEOUT)))


# Fusion of the retrieval layers (reciprocal rank fusion). The values are the ones chosen with the evaluation gate; see
# memory_platform/tests/retrieval_eval/fusion-tuning.json for the grid and the reason.
DEFAULT_FUSION_K, FUSION_K_RANGE = 60, (1, 1000)
DEFAULT_FUSION_VALIDATED_BONUS, FUSION_BONUS_RANGE = 0.0001, (0.0, 1.0)
FUSION_LAYERS = ('episodic', 'documental', 'temporal', 'semantic')
FUSION_WEIGHT_RANGE = (0.0, 10.0)


def check_fusion(k, bonus, weights) -> None:
    """Validate the fusion parameters (a hit adds `weight / (k + rank)` per layer, and `bonus` once when it is validated)."""
    if isinstance(k, bool) or not isinstance(k, int) or not FUSION_K_RANGE[0] <= k <= FUSION_K_RANGE[1]:
        raise ValueError('MEMORY_FUSION_K must be an integer between %d and %d' % FUSION_K_RANGE)
    if isinstance(bonus, bool) or not isinstance(bonus, (int, float)) or not math.isfinite(bonus) or not FUSION_BONUS_RANGE[0] <= bonus <= FUSION_BONUS_RANGE[1]:
        raise ValueError('MEMORY_FUSION_VALIDATED_BONUS must be a number between %s and %s' % FUSION_BONUS_RANGE)
    if not isinstance(weights, dict):
        raise ValueError('MEMORY_FUSION_WEIGHTS must map layers to weights')
    for layer, weight in weights.items():
        if layer not in FUSION_LAYERS:
            raise ValueError('MEMORY_FUSION_WEIGHTS: unknown layer %r (expected one of %s)' % (layer, ', '.join(FUSION_LAYERS)))
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not FUSION_WEIGHT_RANGE[0] < weight <= FUSION_WEIGHT_RANGE[1]:
            raise ValueError('MEMORY_FUSION_WEIGHTS: the weight of %s must be above %s and at most %s' % ((layer,) + FUSION_WEIGHT_RANGE))


def fusion_from_env(environ=None) -> tuple:
    """(k, validated bonus, weights per layer) from MEMORY_FUSION_K, MEMORY_FUSION_VALIDATED_BONUS and MEMORY_FUSION_WEIGHTS (`layer=weight,...`)."""
    environ = os.environ if environ is None else environ
    raw_k = environ.get('MEMORY_FUSION_K', str(DEFAULT_FUSION_K)).strip()
    raw_bonus = environ.get('MEMORY_FUSION_VALIDATED_BONUS', str(DEFAULT_FUSION_VALIDATED_BONUS)).strip()
    if not raw_k.isascii() or not raw_k.isdigit():
        raise ValueError('MEMORY_FUSION_K must be an integer between %d and %d' % FUSION_K_RANGE)
    try:
        bonus = float(raw_bonus)
    except ValueError:
        raise ValueError('MEMORY_FUSION_VALIDATED_BONUS must be a number between %s and %s' % FUSION_BONUS_RANGE) from None
    weights = {}
    for part in (p for p in environ.get('MEMORY_FUSION_WEIGHTS', '').split(',') if p.strip()):
        layer, separator, value = part.partition('=')
        try:
            if not separator:
                raise ValueError()
            weights[layer.strip()] = float(value)
        except ValueError:
            raise ValueError('MEMORY_FUSION_WEIGHTS must look like layer=weight,layer=weight') from None
    check_fusion(int(raw_k), bonus, weights)
    return int(raw_k), bonus, weights


# Abstention (C-05, M-01): `abstain` answers "nothing relevant" when the best semantic cosine is below the threshold of the embeddings model and no
# lexical layer returned anything (docs/architecture.md, "Abstención: la señal"). Off by default; there is no threshold until it is calibrated (P-04).
ABSTAIN_THRESHOLD_RANGE = (-1.0, 1.0)  # a cosine similarity
ABSTAIN_MODEL_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/@+-]*')  # an Ollama or registry name: never `=`, `;`, spaces or the other characters of a mistyped separator


def check_abstain(thresholds) -> None:
    if not isinstance(thresholds, dict):
        raise ValueError('MEMORY_ABSTAIN_THRESHOLDS must map embedding models to thresholds')
    for model, value in thresholds.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError('MEMORY_ABSTAIN_THRESHOLDS: a model name is empty')
        if not ABSTAIN_MODEL_NAME.fullmatch(model.strip()):
            raise ValueError('MEMORY_ABSTAIN_THRESHOLDS: a model name has characters that do not belong in one (letters, digits and . _ : / @ + -); check the separators: model=threshold,model=threshold')
        if sum(model_key(name) == model_key(model) for name in thresholds if isinstance(name, str)) > 1:
            raise ValueError('MEMORY_ABSTAIN_THRESHOLDS: one model has two thresholds (`name` and `name:latest` are the same model)')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not ABSTAIN_THRESHOLD_RANGE[0] <= value <= ABSTAIN_THRESHOLD_RANGE[1]:
            raise ValueError('MEMORY_ABSTAIN_THRESHOLDS: the threshold of %s must be a number between %s and %s' % ((model,) + ABSTAIN_THRESHOLD_RANGE))


def model_key(model: str) -> str:
    """The model without Ollama's implicit `:latest` tag: `nomic-embed-text` and `nomic-embed-text:latest` are the same model."""
    model = model.strip()
    return model[:-len(':latest')] if model.endswith(':latest') else model


def threshold_for(thresholds, model):
    """The threshold of an embeddings model (`None` when it has none), looking `:latest` up on both sides; any other tag is another model."""
    wanted = model_key(model)
    return next((value for name, value in thresholds.items() if model_key(name) == wanted), None)


def abstain_from_env(environ=None) -> tuple:
    """(default on?, thresholds per model) from MEMORY_ABSTAIN_DEFAULT (`on`/`off`, default `off`) and MEMORY_ABSTAIN_THRESHOLDS (`model=threshold,...`)."""
    environ = os.environ if environ is None else environ
    default = switch_from_env('MEMORY_ABSTAIN_DEFAULT', ('on',), ('off',), 'off', environ)
    thresholds = {}
    for part in (p for p in environ.get('MEMORY_ABSTAIN_THRESHOLDS', '').split(',') if p.strip()):
        model, separator, value = part.rpartition('=')
        model = model.strip()
        try:
            if not separator or not model or model in thresholds:
                raise ValueError()
            thresholds[model] = float(value)
        except ValueError:
            raise ValueError('MEMORY_ABSTAIN_THRESHOLDS must look like model=threshold,model=threshold (one threshold per model)') from None
    check_abstain(thresholds)
    return default, thresholds


METRICS_MODES = ('off', 'internal', 'admin')


def metrics_mode_from_env(environ=None) -> str:
    """Exposure of `GET /metrics` (MEMORY_METRICS, decision P-05): `off` (no route), `internal` (default: only requests that did not come through a proxy) or `admin` (administrator credential)."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_METRICS', 'internal').strip().lower()
    if value not in METRICS_MODES:
        raise ValueError('MEMORY_METRICS must be one of: ' + ', '.join(METRICS_MODES))
    return value


def switch_from_env(name: str, on: tuple[str, ...], off: tuple[str, ...], default: str, environ=None) -> bool:
    """A server-side switch that fails closed at startup: an unknown value is an error, never a silent `on` or `off`."""
    environ = os.environ if environ is None else environ
    value = environ.get(name, default).strip().lower()
    if value not in on + off:
        raise ValueError(name + ' must be one of: ' + ', '.join(on + off))
    return value in on


@dataclass(frozen=True)
class Settings:
    dsn: str
    allowed_origins: tuple[str, ...] = ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8791', 'http://localhost:8791')
    cookie_secure: bool = False
    session_ttl: int = 43200
    project_maps: dict = field(default_factory=dict)
    ollama_url: str = 'http://ollama:11434'
    llm_model: str = ''
    extract_enabled: bool = False
    corpus_answer_enabled: bool = False
    embedding_model: str = 'nomic-embed-text'
    request_timeout: float = 30.0
    provider_timeout: float = 180.0
    lease_seconds: int = 240
    max_attempts: int = 3
    worker_db_backoff_max: float = DEFAULT_BACKOFF_MAX  # MEMORY_WORKER_DB_BACKOFF_MAX
    worker_write_retry_seconds: float | None = None  # MEMORY_WORKER_WRITE_RETRY_SECONDS; None = the lease (`lease_seconds`)
    max_body_bytes: int = 262144
    embed_enabled: bool = True
    embedding_query_timeout: float = 10.0
    embedding_worker_timeout: float = 120.0
    chunk_chars: int = DEFAULT_CHUNK_CHARS
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    chunk_max: int = DEFAULT_CHUNK_MAX
    embedding_batch_size: int = DEFAULT_EMBED_BATCH
    embedding_batch_timeout: float = DEFAULT_EMBED_BATCH_TIMEOUT
    embedding_job_timeout_max: float = DEFAULT_EMBED_JOB_MAX_TIMEOUT
    fusion_k: int = DEFAULT_FUSION_K
    fusion_validated_bonus: float = DEFAULT_FUSION_VALIDATED_BONUS
    fusion_weights: dict = field(default_factory=dict)
    abstain_default: bool = False  # MEMORY_ABSTAIN_DEFAULT: abstention when the request does not say
    abstain_thresholds: dict = field(default_factory=dict)  # MEMORY_ABSTAIN_THRESHOLDS: embeddings model -> cosine threshold
    pool_min: int = DEFAULT_POOL_MIN  # MEMORY_POOL_MIN: connections the pool of the API / of the worker keeps open
    pool_max: int = DEFAULT_POOL_MAX  # MEMORY_POOL_MAX
    pool_timeout: float = DEFAULT_POOL_TIMEOUT  # MEMORY_POOL_TIMEOUT: seconds a transaction waits for a connection before 503 `store_busy`
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT  # MEMORY_CONNECT_TIMEOUT: seconds a service connection may take to be made
    statement_timeout_ms: int | None = None  # MEMORY_STATEMENT_TIMEOUT_MS; None = the default of the role (API 15,000, worker 30,000); `admin` ignores it
    keepalives_idle: int = DEFAULT_TCP['idle']  # MEMORY_TCP_KEEPALIVES_IDLE (s): TCP keepalives of the service connections (a peer that vanished is noticed)
    keepalives_interval: int = DEFAULT_TCP['interval']  # MEMORY_TCP_KEEPALIVES_INTERVAL (s)
    keepalives_count: int = DEFAULT_TCP['count']  # MEMORY_TCP_KEEPALIVES_COUNT
    tcp_user_timeout_ms: int = DEFAULT_TCP['user_timeout_ms']  # MEMORY_TCP_USER_TIMEOUT_MS: how long sent data may stay unacknowledged before the connection is dropped
    metrics_mode: str = 'internal'
    mount_mcp: bool = True  # MEMORY_MOUNT_MCP: the internal MCP at `/mcp`, deprecated since 0.4.0 and removed in 0.5.0 (P-07)
    login_concurrency: int = DEFAULT_LOGIN_CONCURRENCY  # MEMORY_LOGIN_CONCURRENCY: password derivations of the API at once (passwords.LoginGate)
    login_max_failures: int = DEFAULT_LOGIN_MAX_FAILURES  # MEMORY_LOGIN_MAX_FAILURES: failures of one client IP that block its logins (limits.py)
    login_window: int = DEFAULT_LOGIN_WINDOW  # MEMORY_LOGIN_WINDOW: seconds those failures count

    def __post_init__(self):
        if self.metrics_mode not in METRICS_MODES:
            raise ValueError('metrics_mode must be one of: ' + ', '.join(METRICS_MODES))
        check_fusion(self.fusion_k, self.fusion_validated_bonus, self.fusion_weights)
        check_abstain(self.abstain_thresholds)
        check_pool(self.pool_min, self.pool_max, self.pool_timeout)
        check_timeouts(self.connect_timeout, self.statement_timeout_ms)
        check_timeout_pair(self.connect_timeout, self.pool_timeout)
        check_tcp(self.keepalives_idle, self.keepalives_interval, self.keepalives_count, self.tcp_user_timeout_ms)
        check_login_concurrency(self.login_concurrency)
        check_login_failures(self.login_max_failures, self.login_window)

    @classmethod
    def from_env(cls):
        maps_file = os.environ.get('MEMORY_PROJECT_MAP_FILE')
        maps = json.loads(Path(maps_file).read_text(encoding='utf-8')) if maps_file else {}
        if not isinstance(maps, dict) or any(not isinstance(v, dict) for v in maps.values()):
            raise ValueError('MEMORY_PROJECT_MAP_FILE must contain a project mapping object')
        origins = tuple(v.strip() for v in os.environ.get('MEMORY_ALLOWED_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8791,http://localhost:8791').split(',') if v.strip())
        if not origins:
            raise ValueError('MEMORY_ALLOWED_ORIGINS must declare portal origins')
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError('MEMORY_ALLOWED_ORIGINS contains an invalid origin')
        secure = os.environ.get('MEMORY_COOKIE_SECURE', '0') == '1'
        if any(urlsplit(v).hostname not in ('localhost', '127.0.0.1', '::1', 'testserver') for v in origins) and (not secure or any(urlsplit(v).scheme != 'https' for v in origins)):
            raise ValueError('Remote portal origins require HTTPS and MEMORY_COOKIE_SECURE=1')
        exact_fallback_ms()  # fail at startup, not on the first short semantic answer
        chunk_chars, chunk_overlap, chunk_max = chunk_settings()
        batch_size = embed_batch_size()
        pool_min, pool_max, pool_timeout = pool_settings()
        connect_timeout, statement_timeout = connection_timeouts()
        check_timeout_pair(connect_timeout, pool_timeout)
        keepalives_idle, keepalives_interval, keepalives_count, tcp_user_timeout_ms = tcp_settings()
        batch_timeout, job_timeout_max = embed_timeouts()
        fusion_k, fusion_bonus, fusion_weights = fusion_from_env()
        abstain_default, abstain_thresholds = abstain_from_env()
        metrics_mode = metrics_mode_from_env()
        login_max_failures, login_window = login_failure_settings()
        extract_enabled = switch_from_env('MEMORY_EXTRACT_ENABLED', ('1',), ('0',), '0')
        corpus_answer_enabled = switch_from_env('MEMORY_CORPUS_ANSWER', ('on',), ('off',), 'off')
        mount_mcp = switch_from_env('MEMORY_MOUNT_MCP', ('1',), ('0',), '1')
        llm_model = os.environ.get('MEMORY_LLM_MODEL', '').strip()
        if (extract_enabled or corpus_answer_enabled) and not llm_model:
            raise ValueError('MEMORY_LLM_MODEL must name a model when MEMORY_EXTRACT_ENABLED=1 or MEMORY_CORPUS_ANSWER=on')
        return cls(
            dsn=secret('MEMORY_DSN', required=True), allowed_origins=origins,
            cookie_secure=secure, session_ttl=int(os.environ.get('MEMORY_SESSION_TTL', '43200')),
            project_maps=maps,
            ollama_url=endpoint('MEMORY_OLLAMA_URL', 'http://ollama:11434'),
            llm_model=llm_model, extract_enabled=extract_enabled, corpus_answer_enabled=corpus_answer_enabled,
            embedding_model=os.environ.get('MEMORY_EMBEDDING_MODEL', 'nomic-embed-text'),
            request_timeout=float(os.environ.get('MEMORY_REQUEST_TIMEOUT', '30')),
            provider_timeout=float(os.environ.get('MEMORY_PROVIDER_TIMEOUT', '180')),
            lease_seconds=int(os.environ.get('MEMORY_LEASE_SECONDS', '240')),
            max_attempts=max_attempts(),
            worker_db_backoff_max=worker_db_backoff_max(),
            worker_write_retry_seconds=worker_write_retry_seconds(None, int(os.environ.get('MEMORY_LEASE_SECONDS', '240'))),
            max_body_bytes=int(os.environ.get('MEMORY_MAX_BODY_BYTES', '262144')),
            embed_enabled=os.environ.get('MEMORY_EMBED_ENABLED', '1') == '1',
            embedding_query_timeout=float(os.environ.get('MEMORY_EMBED_QUERY_TIMEOUT', '10')),
            embedding_worker_timeout=float(os.environ.get('MEMORY_EMBED_WORKER_TIMEOUT', '120')),
            chunk_chars=chunk_chars, chunk_overlap=chunk_overlap, chunk_max=chunk_max, embedding_batch_size=batch_size,
            embedding_batch_timeout=batch_timeout, embedding_job_timeout_max=job_timeout_max,
            fusion_k=fusion_k, fusion_validated_bonus=fusion_bonus, fusion_weights=fusion_weights,
            abstain_default=abstain_default, abstain_thresholds=abstain_thresholds,
            pool_min=pool_min, pool_max=pool_max, pool_timeout=pool_timeout, connect_timeout=connect_timeout, statement_timeout_ms=statement_timeout,
            keepalives_idle=keepalives_idle, keepalives_interval=keepalives_interval, keepalives_count=keepalives_count, tcp_user_timeout_ms=tcp_user_timeout_ms,
            metrics_mode=metrics_mode, mount_mcp=mount_mcp, login_concurrency=login_concurrency(),
            login_max_failures=login_max_failures, login_window=login_window,
        )
