"""Connection pool of the two services (the API and the worker). `admin` never uses it: its commands connect directly, with no pool and no plazo of their own.

`Store.transaction()` is still the one place that gives a connection (`store.py`): it takes it from `store.pool` when there is one and opens a direct one when there
is not (every test and every `admin` command). The pool lives in an attribute of the instance, not in a method of `Store`, because the surface of `Store` is frozen
(`tests/store_surface.json`).

What the pool guarantees, and `tests/test_store_pool.py` / `tests/test_store_faults.py` hold it:
* the sizes (`MEMORY_POOL_MIN`/`MEMORY_POOL_MAX`) and the wait (`MEMORY_POOL_TIMEOUT`) are validated in `config.py`; a transaction that finds no connection within the wait
  raises `StoreBusy` (503 `store_busy` in the API), or `StoreUnavailable` when the pool could not connect since the last connection it gave (the database is down);
* a connection is checked when it is handed out (`ConnectionPool.check_connection`): one that broke while idle is discarded and replaced, never given to a request;
* a connection that comes back is reset (`RESET ALL`) before it is given back: the code only sets transaction-local settings (`set_config(..., true)`, `SET LOCAL`), so this is
  the net under it, and one request can never see what another one set in the session. It is done here, in the request, and not with the `reset=` callback of the pool: that one
  runs in a worker thread AFTER the connection is returned, so the next request would find none ready and the pool would open another one (measured: connections that never stop);
* the pool is opened on the first use, without waiting (a service that starts with the database down must still start) and closed with `close_pool` on shutdown.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading

from .errors import StoreBusy, StoreUnavailable
from .observability import log_failure


def service_conninfo(dsn, connect_timeout=None, statement_timeout_ms=None):
    """The DSN of the service connections: `connect_timeout` (seconds) and `statement_timeout` (milliseconds, a startup option, so it is the default of every session of the
    pool) added over whatever the DSN already says (its own `options` are kept, ours go last and win). With neither it is the DSN itself."""
    if connect_timeout is None and statement_timeout_ms is None:
        return dsn
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    extra = {}
    if connect_timeout is not None:
        extra['connect_timeout'] = int(connect_timeout)
    if statement_timeout_ms is not None:
        existing = conninfo_to_dict(dsn).get('options', '')
        extra['options'] = (existing + ' ' if existing else '') + '-c statement_timeout=%d' % int(statement_timeout_ms)
    return make_conninfo(dsn, **extra)


def reset_session(connection):
    """What a connection goes through before it goes back to the pool: any session setting a request made is dropped (the startup `statement_timeout` returns to its value)."""
    connection.autocommit = True
    try:
        connection.execute('RESET ALL')
    finally:
        connection.autocommit = False


class StorePool:
    def __init__(self, dsn, *, min_size, max_size, timeout, connect_timeout=None, statement_timeout_ms=None, name='kairos'):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        self.timeout, self.name = timeout, name
        self._pool = ConnectionPool(service_conninfo(dsn, connect_timeout, statement_timeout_ms), min_size=min_size, max_size=max_size, timeout=timeout, open=False,
                                    kwargs={'row_factory': dict_row}, check=ConnectionPool.check_connection, name=name)
        self._lock = threading.Lock()
        self._opened = self.closed = False
        self._errors_at_ok = 0  # `connections_errors` of the pool when it last gave a connection: more at a timeout means the database did not let it connect

    def _open(self):
        if not self._opened:
            with self._lock:
                if self.closed:
                    raise StoreUnavailable('PoolClosed')
                if not self._opened:
                    self._pool.open(wait=False)  # no connection is awaited: a database that is down must not stop the service from starting
                    self._opened = True
        return self._pool

    @contextmanager
    def connection(self):
        """A connection for one transaction: committed (or rolled back, when the body raised) and given back when the block ends, whatever happens in it."""
        from psycopg_pool import PoolClosed, PoolTimeout
        pool = self._open()
        try:
            connection = pool.getconn()
        except PoolTimeout:
            raise (StoreUnavailable('PoolTimeout') if pool.get_stats().get('connections_errors', 0) > self._errors_at_ok else StoreBusy()) from None
        except PoolClosed:
            raise StoreUnavailable('PoolClosed') from None
        try:
            self._errors_at_ok = pool.get_stats().get('connections_errors', 0)
            with connection:
                yield connection
        finally:
            try:
                if not connection.closed and not connection.broken:
                    reset_session(connection)
            except Exception as exc:
                log_failure('pool_reset_failed', exc, 'warning')  # the type only, never the message
                connection.close()  # one that cannot be reset is not given to anybody: the pool replaces it
            pool.putconn(connection)

    def wait(self, timeout=30.0):
        """Block until the pool holds `min_size` connections (tests and the measurement use it to start warm; the services never wait for it)."""
        self._open().wait(timeout)

    def stats(self):
        return self._pool.get_stats()

    def close(self):
        """Close the pool and its connections (idempotent); a transaction that starts afterwards finds `StoreUnavailable`."""
        with self._lock:
            already, self.closed = self.closed, True
        if not already and self._opened:
            self._pool.close(timeout=5.0)


def attach_pool(store, settings, role):
    """Give `store` a pool built from `settings` (`pool_min`, `pool_max`, `pool_timeout`); `role` names it in the logs of the pool (`api` or `worker`)."""
    store.pool = StorePool(store.dsn, min_size=settings.pool_min, max_size=settings.pool_max, timeout=settings.pool_timeout, name='kairos-' + role)
    return store.pool


def close_pool(store):
    """Close the pool of `store` if it has one (every shutdown path calls this; a store without a pool is left alone)."""
    pool = getattr(store, 'pool', None)
    if pool is not None:
        pool.close()
