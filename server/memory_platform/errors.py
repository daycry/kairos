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


def is_store_unavailable(exc):
    """True when `exc` says the database is unreachable (a `StoreUnavailable`, or the driver's `OperationalError` / `InterfaceError`), False for every
    other error: a provider error, an application error (`MemoryError`), a data error such as a violated constraint. Only the exception itself is
    looked at, never its `__cause__`: a provider failure that happens to wrap something else stays a provider failure."""
    if isinstance(exc, StoreUnavailable):
        return True
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
