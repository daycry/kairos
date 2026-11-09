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


DEFAULT_MIGRATION_MAINTENANCE_WORK_MEM = '256MB'


def migration_maintenance_work_mem(environ=None) -> str:
    """maintenance_work_mem for the migration transaction (HNSW builds); MEMORY_MIGRATION_MAINTENANCE_WORK_MEM."""
    environ = os.environ if environ is None else environ
    value = environ.get('MEMORY_MIGRATION_MAINTENANCE_WORK_MEM', DEFAULT_MIGRATION_MAINTENANCE_WORK_MEM).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,5}(kB|MB|GB)', value):
        raise ValueError('MEMORY_MIGRATION_MAINTENANCE_WORK_MEM must be a size such as 256MB')
    return value


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
        )
