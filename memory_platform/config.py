"""Explicit process configuration. Importing this module has no side effects."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
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


@dataclass(frozen=True)
class Settings:
    dsn: str
    allowed_origins: tuple[str, ...] = ('http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8791', 'http://localhost:8791')
    cookie_secure: bool = False
    session_ttl: int = 43200
    project_maps: dict = field(default_factory=dict)
    ollama_url: str = 'http://ollama:11434'
    llm_model: str = 'beam:cloud'
    embedding_model: str = 'nomic-embed-text'
    request_timeout: float = 30.0
    provider_timeout: float = 180.0
    lease_seconds: int = 240
    max_attempts: int = 3
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
        batch_timeout, job_timeout_max = embed_timeouts()
        return cls(
            dsn=secret('MEMORY_DSN', required=True), allowed_origins=origins,
            cookie_secure=secure, session_ttl=int(os.environ.get('MEMORY_SESSION_TTL', '43200')),
            project_maps=maps,
            ollama_url=endpoint('MEMORY_OLLAMA_URL', 'http://ollama:11434'),
            llm_model=os.environ.get('MEMORY_LLM_MODEL', 'beam:cloud'),
            embedding_model=os.environ.get('MEMORY_EMBEDDING_MODEL', 'nomic-embed-text'),
            request_timeout=float(os.environ.get('MEMORY_REQUEST_TIMEOUT', '30')),
            provider_timeout=float(os.environ.get('MEMORY_PROVIDER_TIMEOUT', '180')),
            lease_seconds=int(os.environ.get('MEMORY_LEASE_SECONDS', '240')),
            max_attempts=int(os.environ.get('MEMORY_MAX_ATTEMPTS', '3')),
            max_body_bytes=int(os.environ.get('MEMORY_MAX_BODY_BYTES', '262144')),
            embed_enabled=os.environ.get('MEMORY_EMBED_ENABLED', '1') == '1',
            embedding_query_timeout=float(os.environ.get('MEMORY_EMBED_QUERY_TIMEOUT', '10')),
            embedding_worker_timeout=float(os.environ.get('MEMORY_EMBED_WORKER_TIMEOUT', '120')),
            chunk_chars=chunk_chars, chunk_overlap=chunk_overlap, chunk_max=chunk_max, embedding_batch_size=batch_size,
            embedding_batch_timeout=batch_timeout, embedding_job_timeout_max=job_timeout_max,
        )
