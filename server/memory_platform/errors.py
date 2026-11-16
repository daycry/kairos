"""Public domain errors; never include provider or database exception text."""


class MemoryError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status_code


class Unauthorized(MemoryError):
    def __init__(self):
        super().__init__('unauthorized', 'Authentication required', 401)


class Forbidden(MemoryError):
    def __init__(self, message='Operation not permitted'):
        super().__init__('forbidden', message, 403)


class NotFound(MemoryError):
    def __init__(self):
        super().__init__('not_found', 'Resource not found', 404)


class Conflict(MemoryError):
    def __init__(self, message='Conflicting event or version'):
        super().__init__('conflict', message, 409)


DomainError = MemoryError


class StoreUnavailable(Exception):
    """The database did not answer: refused or lost connection, a connection closed in the middle of a query or of the commit.

    It is NOT a `MemoryError` on purpose: it carries no public code, and the worker must never turn it into a failure of a job (`fail_job`),
    which is what a provider failure does. The message is fixed and `cause_type` is the class name of the driver error: the driver message may name
    the host, the port or the user, so it is neither kept nor chained (`raise ... from None`)."""

    def __init__(self, cause_type=None):
        super().__init__('Database unavailable')
        self.cause_type = cause_type


class StoreBusy(StoreUnavailable):
    """The pool of connections could not give one within `MEMORY_POOL_TIMEOUT` (all of them in use, or the database is not answering to the new ones).

    It IS a `StoreUnavailable`, so the worker waits and tries again without spending the attempt of a job; the API answers it as 503 `store_busy`.
    Fixed message, no driver text (the DSN is never in it)."""

    def __init__(self, cause_type='PoolTimeout'):
        super().__init__(cause_type)
        self.args = ('Database busy',)


# SQLSTATEs that mean "the server is going away" and nothing else: class 08 (connection exception) and the three shutdown states of class 57.
# Every other OperationalError that carries a SQLSTATE is a problem of ONE statement (57014 query_canceled, 55P03 lock_not_available, 54xxx limits,
# 40001/40P01 serialization and deadlock, 53xxx resources): the database answered, so it is not an outage and must keep its own path.
SHUTDOWN_SQLSTATES = frozenset({'57P01', '57P02', '57P03'})


def _sqlstate(exc):
    state = getattr(exc, 'sqlstate', None)
    if state is None:
        state = getattr(getattr(exc, 'diag', None), 'sqlstate', None)
    return state if isinstance(state, str) else None


def is_store_unavailable(exc):
    """True when `exc` says the database is unreachable: a `StoreUnavailable`, the driver's `InterfaceError` (closed or broken connection object), an
    `OperationalError` WITHOUT a SQLSTATE (the failure to connect, or a connection that broke: the server never said anything) or one whose SQLSTATE
    is of class 08 or is 57P01/57P02/57P03 (admin shutdown, crash shutdown, cannot connect now). False for every other error: a provider error, an
    application error (`MemoryError`), a data error such as a violated constraint, and the OperationalErrors the server DID answer with
    (`QueryCanceled`, `LockNotAvailable`, `ProgramLimitExceeded`, serialization failures...). Only the exception itself is looked at, never its
    `__cause__`: a provider failure that happens to wrap something else stays a provider failure."""
    if isinstance(exc, StoreUnavailable):
        return True
    try:
        import psycopg
    except ImportError:
        return False
    if isinstance(exc, psycopg.InterfaceError):
        return True
    if not isinstance(exc, psycopg.OperationalError):
        return False
    state = _sqlstate(exc)
    return state is None or state.startswith('08') or state in SHUTDOWN_SQLSTATES


TRANSIENT_SQLSTATES = frozenset({'40001', '40P01', '57014', '55P03'})


def is_store_transient(exc):
    """True for an error the database ANSWERED with that is worth repeating a little later: a serialization failure (40001), a deadlock (40P01), a cancelled
    query (57014, `statement_timeout`), a lock that could not be taken (55P03) and any insufficient-resources error (class 53). It is not an outage
    (`is_store_unavailable` is False for it); only the write of the outcome of a job repeats it, within its budget. Anything else (54xxx, a violated
    constraint...) is not transient."""
    try:
        import psycopg
    except ImportError:
        return False
    if not isinstance(exc, psycopg.Error) or is_store_unavailable(exc):
        return False
    state = _sqlstate(exc)
    return state is not None and (state in TRANSIENT_SQLSTATES or state.startswith('53'))


STORE_BUSY_MESSAGE = 'The store is busy; retry shortly'
STORE_TIMEOUT_MESSAGE = 'The store took too long to answer; retry shortly'


def is_statement_timeout(exc):
    """True for the error PostgreSQL answers with when it cancels a statement that ran past `statement_timeout` (SQLSTATE 57014, `QueryCanceled`)."""
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.errors.QueryCanceled)


def public_store_failure(exc):
    """`(code, message)` a client is given (always with status 503) for a failure of the database that is a plazo and not a plain outage, or None: `store_busy` (the pool had no
    connection to give within MEMORY_POOL_TIMEOUT) and `store_timeout` (the database cancelled the statement at its `statement_timeout`). The messages are fixed: nothing of the
    driver, the SQL or the DSN travels (CWE-209). The API, the mounted MCP and, through the API, `kairos-mcp` use it; the WORKER does not: for it the first is an outage
    (`StoreBusy` is a `StoreUnavailable`) and the second a transient error it repeats (`is_store_transient`)."""
    if isinstance(exc, StoreBusy):
        return 'store_busy', STORE_BUSY_MESSAGE
    if is_statement_timeout(exc):
        return 'store_timeout', STORE_TIMEOUT_MESSAGE
    return None


def is_store_error(exc):
    """True for an error the database ANSWERED with (any driver error that is not an outage, see `is_store_unavailable`): not the provider's failure either."""
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.Error) and not is_store_unavailable(exc)
