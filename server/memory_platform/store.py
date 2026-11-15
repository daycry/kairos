"""Transactional Postgres canon. Connections are short-lived; providers never run here.

Facade: the implementation lives in the store_* domain mixins; helpers are re-exported.
"""
from contextlib import contextmanager

from .errors import StoreUnavailable, is_store_unavailable
from .store_auth import AuthMixin
from .store_common import as_dict, canonical, clean, digest, lexical_query, new_id
from .store_documents import DocumentsMixin
from .store_graph import GraphMixin
from .store_ingest import IngestMixin
from .store_jobs import JobsMixin
from .store_vectors import VectorsMixin

__all__ = ['Store', 'as_dict', 'canonical', 'clean', 'digest', 'lexical_query', 'new_id']


class Store(AuthMixin, IngestMixin, DocumentsMixin, GraphMixin, JobsMixin, VectorsMixin):
    def __init__(self, dsn, project_maps=None, embedding_enabled=False):
        self.dsn = dsn
        self.project_maps = project_maps or {}
        self.embedding_enabled = embedding_enabled

    @contextmanager
    def transaction(self):
        """The one place that opens a connection. A database that does not answer (connect, query or commit) leaves as `StoreUnavailable`
        (see `errors.is_store_unavailable`: connection errors and the shutdown SQLSTATEs only); every other error, including those of the caller's own code
        and the ones the server answered with (a cancelled query, a lock timeout), passes through untouched."""
        import psycopg
        from psycopg.rows import dict_row
        try:
            with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
                with connection.transaction():
                    yield connection
        except Exception as exc:
            if is_store_unavailable(exc) and not isinstance(exc, StoreUnavailable):
                raise StoreUnavailable(type(exc).__name__) from None
            raise
