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


def is_store_error(exc):
    """True for an error the database ANSWERED with (any driver error that is not an outage, see `is_store_unavailable`): not the provider's failure either."""
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, psycopg.Error) and not is_store_unavailable(exc)
