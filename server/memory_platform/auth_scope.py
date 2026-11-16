"""The lifetime of the permission cache: one transaction (see the comment below). No imports from the package, so `auth.py`, `store.py` and every store mixin can use it."""
from contextlib import contextmanager

# Permissions resolved ONCE per transaction (I3 / CA-18, B-02). What `_active` (actor and credential) and `_require` (grants of a project) read is kept in a dict that lives on the
# connection from the start of `Store.transaction()` to its COMMIT or ROLLBACK and in no other place: not in the module, not in the store, not in the pool (it is a plain attribute of
# the connection that `auth_scope` sets and unsets around the transaction, so a connection that goes back to the pool carries none). A revocation committed elsewhere is seen by the NEXT
# transaction of any request; within one transaction the answer is the one it started with (the same snapshot every query of the search reads).
# The dict is emptied (`invalidate_auth`) by everything that changes who may do what from inside a transaction (the writers below and in `auth.py`) and by a savepoint that fails
# (`savepoint`): a rolled-back savepoint takes its writes with it, and what was read after them must not outlive them. `tests/test_auth_cache.py` holds each of these.
_CACHE = '_kairos_auth'


@contextmanager
def auth_scope(connection):
    """The lifetime of the cache of one transaction: set when it starts, unset when it ends (committed, rolled back or broken)."""
    setattr(connection, _CACHE, {})
    try:
        yield connection
    finally:
        setattr(connection, _CACHE, None)


def invalidate_auth(c):
    """Forget what this transaction resolved about permissions (call it after any statement that changes actors, credentials, sessions, grants or projects)."""
    cache = getattr(c, _CACHE, None)
    if cache is not None:
        cache.clear()


@contextmanager
def savepoint(c):
    """`c.transaction()` inside a transaction (a savepoint). When it fails and is rolled back the permission cache is dropped: nothing read after its writes may survive them."""
    try:
        with c.transaction():
            yield
    except BaseException:
        invalidate_auth(c)
        raise


def _cached(c, key, load):
    cache = getattr(c, _CACHE, None)
    if cache is None:  # a connection that `Store.transaction()` did not hand out (a test, `admin`): nothing is kept
        return load()
    if key not in cache:
        cache[key] = load()
    return cache[key]


def _identity(actor):
    return (actor['id'], actor.get('credential_type'), actor.get('key_id'), actor.get('session_id'))
