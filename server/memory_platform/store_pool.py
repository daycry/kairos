"""Connection pool of the two services (the API and the worker). `admin` never uses it: its commands connect directly, with no pool and no plazo of their own.

`Store.transaction()` is still the one place that gives a connection (`store.py`): it takes it from `store.pool` when there is one and opens a direct one when there
is not (every test and every `admin` command). The pool lives in an attribute of the instance, not in a method of `Store`, because the surface of `Store` is frozen
(`tests/store_surface.json`).

What the pool guarantees, and `tests/test_store_pool.py` / `tests/test_store_faults.py` hold it:
* the sizes (`MEMORY_POOL_MIN`/`MEMORY_POOL_MAX`) and the wait (`MEMORY_POOL_TIMEOUT`) are validated in `config.py`; a transaction that finds no connection within the wait
  raises `StoreBusy` (503 `store_busy` in the API) when the pool has recorded NO connection fault since the last connection it gave (no connect error, no failed check): the database
  answered every time it was asked, so the pool is busy or still growing under load (the free slots that are becoming connections, the one that is being handed over to a waiter);
  `StoreUnavailable` (503 `service_unavailable`, the database does not answer) ONLY when a connect error or a failed check IS on record since then. Neither depends on how many
  connections are in use at that instant, which is a race with the connection coming back, nor on a timer;
* a connection is checked when it is handed out (`ConnectionPool.check_connection`): one that broke while idle is discarded and replaced, never given to a request;
* a connection that comes back is reset (`RESET ALL`) before it is given back: the code only sets transaction-local settings (`set_config(..., true)`, `SET LOCAL`), so this is
  the net under it, and one request can never see what another one set in the session. It is done here, in the request, and not with the `reset=` callback of the pool: that one
  runs in a worker thread AFTER the connection is returned, so the next request would find none ready and the pool would open another one (measured: connections that never stop);
* a connection that is ALREADY established and then stops answering without closing (a partition, a frozen host: the half-open case) cannot hang a thread. Two layers, because each one alone is not enough:
  the connections carry TCP keepalives and `tcp_user_timeout` (`service_conninfo`; the kernel drops a peer that vanished in about a minute, but not on loopback or in a proxy that still
  answers at TCP level), and every blocking operation on a pooled connection (the check at hand-out, each statement, the commit, the `RESET`) runs under a CLIENT-side plazo
  (`GuardedConnection.wait`, the `timeout` that psycopg's own wait takes): `statement_timeout` plus a margin for statements (the server cancels first when it is alive), a short
  `check_seconds` for the check, the reset and `/health/ready`. When it runs out the connection is closed, the operation raises `OperationalError` (a database outage for
  `errors.is_store_unavailable`, never a provider failure) and the pool replaces it. No watchdog thread, no socket tricks: it is the library's own mechanism, found by reading
  `Connection.wait` of psycopg 3.3 (the alternative, `shutdown()` of the descriptor from a timer thread, needs a thread per pool and races with the close);
* the pool is opened on the first use, without waiting (a service that starts with the database down must still start) and closed with `close_pool` on shutdown.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading

from .config import service_statement_timeout
from .errors import StoreBusy, StoreUnavailable
from .observability import log_failure

GUARD_MARGIN_SECONDS = 5.0  # added to the longest statement_timeout in force: the server answers its own cancellation within it when it is alive
CHECK_SECONDS = 1.0  # client-side plazo of the check at hand-out and of the RESET (a one-packet round trip): a request never waits for a half-open connection longer than this
READY_WAIT = 0.5  # seconds `/health/ready` waits for a connection (the healthcheck client gives up at 3 s: this, the check and its query add up to 2.5)
READY_GUARD = 1.0  # client-side plazo of the one-row query of `/health/ready`
RECONNECT_TIMEOUT = 10.0  # seconds a pool keeps retrying one connection (the pool default is 300): the waits of its backoff (1, 2, 4... s) are cut at this, so once the database is back a
# request never waits behind a retry scheduled minutes ahead; a slot that gives up is made again by the next request that finds the pool empty


def service_conninfo(dsn, connect_timeout=None, statement_timeout_ms=None, tcp=None):
    """The DSN of the service connections: `connect_timeout` (seconds), `statement_timeout` (milliseconds, a startup option, so it is the default of every session of the
    pool) and `tcp` (`(idle, interval, count, user_timeout_ms)`: `keepalives=1`, `keepalives_idle`, `keepalives_interval`, `keepalives_count`, `tcp_user_timeout`) added over whatever the
    DSN already says (its own `options` are kept, ours go last and win). With none of them it is the DSN itself."""
    if connect_timeout is None and statement_timeout_ms is None and tcp is None:
        return dsn
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    extra = {}
    if tcp is not None:
        extra.update(keepalives=1, keepalives_idle=int(tcp[0]), keepalives_interval=int(tcp[1]), keepalives_count=int(tcp[2]), tcp_user_timeout=int(tcp[3]))
    if connect_timeout is not None:
        extra['connect_timeout'] = int(connect_timeout)
    if statement_timeout_ms is not None:
        existing = conninfo_to_dict(dsn).get('options', '')
        extra['options'] = (existing + ' ' if existing else '') + '-c statement_timeout=%d' % int(statement_timeout_ms)
    return make_conninfo(dsn, **extra)


_GUARDED = None


def guarded_connection_class():
    """`psycopg.Connection` whose every blocking wait (statement, commit, rollback, check) has a client-side plazo, `guard_seconds` (None: no plazo, as a plain connection). Built on the first
    use so that importing this module does not import the driver."""
    global _GUARDED
    if _GUARDED is None:
        import psycopg
        from psycopg import errors as pg_errors
        wait_timeout = pg_errors._WaitTimeout  # what `Connection.wait(..., timeout=)` raises; a test fails if a driver upgrade renames it

        class GuardedConnection(psycopg.Connection):
            guard_seconds = None

            def wait(self, gen, *args, **kwargs):
                if self.guard_seconds is not None and kwargs.get('timeout') is None and len(args) < 2:
                    kwargs['timeout'] = self.guard_seconds
                try:
                    return super().wait(gen, *args, **kwargs)
                except wait_timeout:
                    try:
                        self.close()  # the state of the server side is unknown: this connection is never used again
                    except Exception as exc:
                        log_failure('pool_guard_close_failed', exc, 'warning')  # the type only
                    raise psycopg.OperationalError('the connection did not answer within its client-side plazo') from None
        _GUARDED = GuardedConnection
    return _GUARDED


def reset_session(connection):
    """What a connection goes through before it goes back to the pool: any session setting a request made is dropped (the startup `statement_timeout` returns to its value)."""
    connection.autocommit = True
    try:
        connection.execute('RESET ALL')
    finally:
        connection.autocommit = False


class StorePool:
    def __init__(self, dsn, *, min_size, max_size, timeout, connect_timeout=None, statement_timeout_ms=None, name='kairos', tcp=None, guard_seconds=None, check_seconds=CHECK_SECONDS):
        # Nothing is parsed or connected here: the DSN is read when the pool is first used (a `Settings('unused')` app, the contract exporter and most tests never serve).
        self.timeout, self.name, self.max_size = timeout, name, max_size
        self.guard_seconds, self.check_seconds = guard_seconds, check_seconds
        self._parameters = dict(dsn=dsn, min_size=min_size, max_size=max_size, timeout=timeout, connect_timeout=connect_timeout, statement_timeout_ms=statement_timeout_ms, tcp=tcp)
        self._pool = None
        self._lock = threading.Lock()
        self._opened = self.closed = False
        self._in_use = 0  # connections handed out and not yet given back (the pool's own `pool_size` also counts the attempts that are still connecting, so it cannot tell a full pool)
        self._failed_checks = 0  # checks at hand-out that failed (a dead or half-open connection): counted with the connect errors below
        self._faults_at_ok = 0  # connect errors + failed checks when the pool last gave a connection: more at a timeout means the database does not answer

    def _open(self):
        if not self._opened:
            with self._lock:
                if self.closed:
                    raise StoreUnavailable('PoolClosed')
                if not self._opened:
                    from psycopg.rows import dict_row
                    from psycopg_pool import ConnectionPool
                    values = self._parameters
                    def configure(connection):
                        connection.guard_seconds = self.guard_seconds
                    pool = ConnectionPool(service_conninfo(values['dsn'], values['connect_timeout'], values['statement_timeout_ms'], values['tcp']), min_size=values['min_size'], max_size=values['max_size'],
                                          timeout=values['timeout'], open=False, kwargs={'row_factory': dict_row}, connection_class=guarded_connection_class(), configure=configure,
                                          check=self._check, reconnect_timeout=RECONNECT_TIMEOUT, name=self.name)
                    pool.open(wait=False)  # no connection is awaited: a database that is down must not stop the service from starting
                    self._pool, self._opened = pool, True
        return self._pool

    def _check(self, connection):
        """The check at hand-out, under its own short client-side plazo; a failure is counted (it is evidence of an outage at the timeout) and the pool discards the connection."""
        from psycopg_pool import ConnectionPool
        previous, connection.guard_seconds = connection.guard_seconds, self.check_seconds
        try:
            ConnectionPool.check_connection(connection)
        except Exception:
            with self._lock:
                self._failed_checks += 1
            raise
        finally:
            connection.guard_seconds = previous

    def _faults(self, pool):
        return pool.get_stats().get('connections_errors', 0) + self._failed_checks

    def saturated(self):
        """True when every connection the pool may have is handed out and in use (the database is not the problem: the service is busy)."""
        with self._lock:
            return self._in_use >= self.max_size

    @contextmanager
    def connection(self, wait=None, guard=None):
        """A connection for one transaction: committed (or rolled back, when the body raised) and given back when the block ends, whatever happens in it. `wait` and `guard` override, for this
        one transaction, the wait for a connection and the client-side plazo of its statements (`/health/ready` uses short ones)."""
        from psycopg_pool import PoolClosed, PoolTimeout
        pool = self._open()
        try:
            connection = pool.getconn(timeout=wait)
        except PoolTimeout:
            # no timer and no look at `_in_use` (a race with a connection coming back or being handed over): only a fault on record says the database does not answer
            raise (StoreUnavailable('PoolTimeout') if self._faults(pool) > self._faults_at_ok else StoreBusy()) from None
        except PoolClosed:
            raise StoreUnavailable('PoolClosed') from None
        with self._lock:
            self._in_use += 1
        try:
            self._faults_at_ok = self._faults(pool)
            connection.guard_seconds = guard if guard is not None else self.guard_seconds
            with connection:
                yield connection
        finally:
            try:
                if not connection.closed and not connection.broken:
                    connection.guard_seconds = self.check_seconds
                    reset_session(connection)
            except Exception as exc:
                log_failure('pool_reset_failed', exc, 'warning')  # the type only, never the message
                connection.close()  # one that cannot be reset is not given to anybody: the pool replaces it
            try:
                pool.putconn(connection)
            finally:
                with self._lock:
                    self._in_use -= 1  # AFTER the connection is back: between the two a waiter would see a pool that is neither full nor able to give it (`/health/ready` answered 503)

    def wait(self, timeout=30.0):
        """Block until the pool holds `min_size` connections (tests and the measurement use it to start warm; the services never wait for it)."""
        self._open().wait(timeout)

    def stats(self):
        return self._open().get_stats()

    def close(self):
        """Close the pool and its connections (idempotent); a transaction that starts afterwards finds `StoreUnavailable`."""
        with self._lock:
            already, self.closed = self.closed, True
        if not already and self._opened:
            self._pool.close(timeout=2.0)  # a thread stuck in a connect (libpq cannot be interrupted) is a daemon: the process still exits


def client_guard_seconds(statement_timeout_ms):
    """Client-side plazo of a statement: the longest `statement_timeout` any statement may run under (the session one, or the exact-fallback one when it is longer: it is set per statement
    with `set_config`) plus `GUARD_MARGIN_SECONDS`. The server cancels first when it is alive; this one only fires when it is not."""
    from .config import DEFAULT_EXACT_FALLBACK_MS, exact_fallback_ms
    try:
        fallback = exact_fallback_ms()
    except ValueError:
        fallback = DEFAULT_EXACT_FALLBACK_MS
    return max(statement_timeout_ms, fallback) / 1000.0 + GUARD_MARGIN_SECONDS


def attach_pool(store, settings, role):
    """Give `store` a pool built from `settings` (`pool_min`, `pool_max`, `pool_timeout`, `connect_timeout`, `statement_timeout_ms`, the TCP options); `role` (`api` or `worker`) names the pool and
    picks the default `statement_timeout`. Every connection of the pool is made with those plazos as options of the connection, so they are the default of each of its sessions."""
    statement = service_statement_timeout(settings, role)
    store.pool = StorePool(store.dsn, min_size=settings.pool_min, max_size=settings.pool_max, timeout=settings.pool_timeout, connect_timeout=settings.connect_timeout,
                           statement_timeout_ms=statement, name='kairos-' + role, guard_seconds=client_guard_seconds(statement),
                           tcp=(settings.keepalives_idle, settings.keepalives_interval, settings.keepalives_count, settings.tcp_user_timeout_ms))
    return store.pool


def ready_probe(store):
    """What `/health/ready` runs: a one-row read on its own short plazos, `'ready'` when it worked and `'saturated'` when the pool had no free connection within `READY_WAIT` and
    no connection fault is on record (the same rule as `StorePool.connection`: a busy service is not a dead database, the healthcheck must not take it out). Anything else (a database that does not answer, a pool that cannot connect,
    a connection that stopped answering) raises. A store without a pool (or a test double) just reads."""
    pool = getattr(store, 'pool', None)
    if not isinstance(pool, StorePool):
        with store.transaction() as c:
            c.execute('SELECT version FROM memory.schema_versions LIMIT 1')
        return 'ready'
    try:
        with pool.connection(wait=READY_WAIT, guard=READY_GUARD) as c:
            c.execute('SELECT version FROM memory.schema_versions LIMIT 1')
    except StoreBusy:
        return 'saturated'  # `StoreBusy` is decided at the timeout itself, from the faults on record: asking again afterwards would race with a connection coming back
    return 'ready'



def close_pool(store):
    """Close the pool of `store` if it has one (every shutdown path calls this; a store without a pool is left alone)."""
    pool = getattr(store, 'pool', None)
    if pool is not None:
        pool.close()
