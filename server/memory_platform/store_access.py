"""Store mixin: the one door for the changes of access (CA-01, design.md O2, DC-1, DC-10).

Every writer of a change of who may do what that this initiative adds lives here and ends in `_access_changed`, which audits the change and empties the permission cache of
the transaction. `tests/test_auth_cache.py` walks this module: a function that writes `actors`, `project_grants`, `api_keys` or `web_sessions` here and does not end in
`_access_changed` fails there. `admin.py` calls these methods and has no SQL of its own for them (DC-10), so the audit, the closing of sessions and the emptying of the cache
have one implementation.

What decides an access is NOT here: the resolver (`store_auth.py`) reads `is_admin`, `project_grants` and the permissions of a key. A function of this module that has to read one of
those to change an access is declared on `READ_EXCEPTIONS` of that walk, with its reason.
"""
from contextlib import nullcontext

from . import passwords
from .auth import RECENT_ATTEMPTS, lock_attempts
from .auth_scope import invalidate_auth
from .errors import Conflict, Forbidden, MemoryError, NotFound

# `POST /v1/auth/password`: at most this many CORRECT changes per user in the last 15 minutes (fix1 of the review of phase 2, gap 1). The failures have their own limit (10 per user or per IP,
# the one of the login). A person changes a password once; five leave room for a typing mistake that was accepted, a password manager and a second device, and bound what a stolen session
# can make the service derive (two derivations of 128 MB per change) to a handful per quarter of an hour.
PASSWORD_CHANGES_PER_WINDOW = 5
# The count does not read `audit_events` whole (fix2 of the review of phase 2, gap 2: 1 M old rows cost 190 ms per request). There is no index on `happened_at` and the schema is closed (version 13), so it
# is bounded by the primary key: `id` is an identity that the same INSERT assigns together with `happened_at`, so both grow together. LAST_OLD_EVENT is a backward walk of the key that stops at the first row
# older than the window (a few buffers however large the table is) and RECENT_CHANGES counts only the `id` above it, still filtering by `happened_at`. Limit declared in design.md DC-5: the order by `id` is the
# order of the clock only to the microsecond, so a row whose `id` and `happened_at` disagree at the very edge of the window (two sessions inserting in the same microsecond, or a clock stepped back by minutes)
# may be counted or missed by that margin.
LAST_OLD_EVENT = "SELECT id FROM memory.audit_events WHERE happened_at<=clock_timestamp()-interval '15 minutes' ORDER BY id DESC LIMIT 1"
RECENT_CHANGES = "SELECT count(*) AS n FROM memory.audit_events WHERE id>%s AND actor_id=%s AND action='password.changed' AND happened_at>clock_timestamp()-interval '15 minutes'"


def password_changes_left(c, actor):
    """429 `too_many_attempts` when the user already made `PASSWORD_CHANGES_PER_WINDOW` correct changes in the last 15 minutes (counted in the audit events of `password.changed`, bounded by the key: see above)."""
    old = c.execute(LAST_OLD_EVENT).fetchone()
    if c.execute(RECENT_CHANGES, (old['id'] if old else 0, actor['id'])).fetchone()['n'] >= PASSWORD_CHANGES_PER_WINDOW:
        raise MemoryError('too_many_attempts', 'Too many password changes; try again later', 429)


class AccessMixin:
    def _access_changed(self, c, actor, action, project_id=None, resource_id=None):
        """The end of every writer of access: the audit event of the change, then the permission cache of this transaction emptied (what was resolved before the change must not outlive it)."""
        self._audit(c, actor, action, project_id, resource_id)
        invalidate_auth(c)

    def change_password(self, actor, current, new, client_ip='', slot=None):
        """`POST /v1/auth/password`: with the right current password, replace the hash, close every OTHER session of the user and keep this one and the keys.

        Only a session may do it (a key is a different credential and gets 403). The order is DC-5's: first the checks that need no derivation and take no slot (the credential is alive, the new
        password has a valid length, the IP or the user is not blocked by failures: 429 `rate_limited`, the user has not made too many changes: 429 `too_many_attempts`), then the slot of the
        gate (`slot`, a callable that returns a context manager: the route gives `passwords.GATE.hold(ip)`; none in the tests and `admin`), then the derivations: the verification of the current password
        at the cost of ITS hash (a hash of an earlier release costs the cheap check, not a second derivation at the target cost) and the hash of the new one, outside any transaction.
        A wrong current password changes nothing and is a failed login of `client_ip`: it is recorded (committed on its own, under the advisory locks of the login, with the same recount) and
        refused with 403. The last transaction locks the row of the user, recounts the changes and replaces the hash only if it is still the one that was verified."""
        with self.transaction() as c:
            self._active(c, actor)  # the credential is alive: a revoked one is 401 before anything else is said about the request
            if actor.get('credential_type') != 'session':
                raise Forbidden('Only a signed-in session may change the password')
            passwords.check_length(new)  # before anything is derived
            if c.execute(RECENT_ATTEMPTS, (actor['username'], client_ip)).fetchone()['n'] >= 10:
                raise MemoryError('rate_limited', 'Too many login attempts', 429)
            password_changes_left(c, actor)
            stored = c.execute('SELECT password_hash FROM memory.actors WHERE id=%s', (actor['id'],)).fetchone()['password_hash']
        with (slot or nullcontext)():
            right = passwords.verify_password(current, stored)
            fresh = passwords.hash_password(new) if right else None
        if not right:
            with self.transaction() as c:  # committed on its own, before the refusal is raised
                lock_attempts(c, actor['username'], client_ip)
                if c.execute(RECENT_ATTEMPTS, (actor['username'], client_ip)).fetchone()['n'] >= 10:  # other failures arrived while this request derived: not one more is written
                    raise MemoryError('rate_limited', 'Too many login attempts', 429)
                c.execute('INSERT INTO memory.login_attempts(username,client_ip) VALUES(%s,%s)', (actor['username'], client_ip))
            raise MemoryError('invalid_current_password', 'The current password is not correct', 403)
        with self.transaction() as c:
            self._active(c, actor)
            # The row of the user is locked first (`admin set-password`, the login that replaces an old hash and another change take it too): the count of changes is exact for two requests at once, and
            # `WHERE password_hash=<the one verified>` keeps a password changed meanwhile from being overwritten.
            c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR NO KEY UPDATE', (actor['id'],))
            password_changes_left(c, actor)
            if not c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s AND password_hash=%s', (fresh, actor['id'], stored)).rowcount:
                raise Conflict('The password changed while this request was running')
            c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND id<>%s AND revoked_at IS NULL', (actor['id'], actor['session_id']))
            self._access_changed(c, actor, 'password.changed', resource_id=actor['id'])
        return {'changed': True}

    def set_password(self, username, new, revoke_keys=False):
        """`admin set-password`: the recovery of an account by the operator (no actor, no current password). The user's hash is replaced and EVERY session of the user is closed, the
        current one too: whoever knew the old password may be the one holding a session. The API keys of the user stay (they are credentials of their own) unless `revoke_keys`: then
        they are revoked in the same transaction, which is what recovering an account that someone else had access to needs (a key that person made would otherwise keep working).
        The audit event is `password.reset`, with no actor (the operator is not an actor of the service) and the user as the resource, plus `keys.revoked` when keys were revoked.
        Returns what the command may print: the user and how many sessions and keys it closed, never the password or its hash.
        One derivation at the target cost, outside the transaction; `passwords.GATE` is the API's and is not used here."""
        fresh = passwords.hash_password(new)
        with self.transaction() as c:
            row = c.execute('SELECT id FROM memory.actors WHERE username=%s', (username,)).fetchone()
            if not row:
                raise NotFound()
            c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s', (fresh, row['id']))
            closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL', (row['id'],)).rowcount
            keys = c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL', (row['id'],)).rowcount if revoke_keys else 0
            if keys:
                self._audit(c, {'id': None}, 'keys.revoked', resource_id=row['id'])
            self._access_changed(c, {'id': None}, 'password.reset', resource_id=row['id'])
        return {'username': username, 'sessions_revoked': closed, 'keys_revoked': keys}
