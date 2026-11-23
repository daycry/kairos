"""Store mixin: the one door for the changes of access (CA-01, design.md O2, DC-1, DC-10).

Every writer of a change of who may do what that this initiative adds lives here and ends in `_access_changed`, which audits the change and empties the permission cache of
the transaction. `tests/test_auth_cache.py` walks this module: a function that writes `actors`, `project_grants`, `api_keys` or `web_sessions` here and does not end in
`_access_changed` fails there. `admin.py` calls these methods and has no SQL of its own for them (DC-10), so the audit, the closing of sessions and the emptying of the cache
have one implementation.

What decides an access is NOT here: the resolver (`store_auth.py`) reads `is_admin`, `project_grants` and the permissions of a key. A function of this module that has to read one of
those to change an access is declared on `READ_EXCEPTIONS` of that walk, with its reason.
"""
from . import passwords
from .auth import RECENT_ATTEMPTS
from .auth_scope import invalidate_auth
from .errors import Conflict, Forbidden, MemoryError, NotFound


class AccessMixin:
    def _access_changed(self, c, actor, action, project_id=None, resource_id=None):
        """The end of every writer of access: the audit event of the change, then the permission cache of this transaction emptied (what was resolved before the change must not outlive it)."""
        self._audit(c, actor, action, project_id, resource_id)
        invalidate_auth(c)

    def change_password(self, actor, current, new, client_ip=''):
        """`POST /v1/auth/password`: with the right current password, replace the hash, close every OTHER session of the user and keep this one and the keys.

        Only a session may do it (a key is a different credential and gets 403). The new password is checked for length before anything is derived. A wrong current password changes nothing and
        is a failed login of `client_ip`: it is recorded (committed, apart from the rest) and an IP already blocked by failures gets 429 before any derivation. The derivations (verify the current,
        hash the new) run outside any transaction and, in the API, inside the slot of `passwords.GATE` that the route holds."""
        with self.transaction() as c:
            self._active(c, actor)  # the credential is alive: a revoked one is 401 before anything else is said about the request
            if actor.get('credential_type') != 'session':
                raise Forbidden('Only a signed-in session may change the password')
            passwords.check_length(new)  # before anything is derived
            if c.execute(RECENT_ATTEMPTS, (actor['username'], client_ip)).fetchone()['n'] >= 10:
                raise MemoryError('rate_limited', 'Too many login attempts', 429)
            stored = c.execute('SELECT password_hash FROM memory.actors WHERE id=%s', (actor['id'],)).fetchone()['password_hash']
        right, _ = passwords.check_login(current, stored)
        if not right:
            with self.transaction() as c:  # committed on its own, before the refusal is raised
                c.execute('INSERT INTO memory.login_attempts(username,client_ip) VALUES(%s,%s)', (actor['username'], client_ip))
            raise MemoryError('invalid_current_password', 'The current password is not correct', 403)
        fresh = passwords.hash_password(new)
        with self.transaction() as c:
            self._active(c, actor)
            # `WHERE password_hash=<the one verified>`: a password changed meanwhile (another request, `admin set-password`) is not overwritten.
            if not c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s AND password_hash=%s', (fresh, actor['id'], stored)).rowcount:
                raise Conflict('The password changed while this request was running')
            c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND id<>%s AND revoked_at IS NULL', (actor['id'], actor['session_id']))
            self._access_changed(c, actor, 'password.changed', resource_id=actor['id'])
        return {'changed': True}

    def set_password(self, username, new):
        """`admin set-password`: the recovery of an account by the operator (no actor, no current password). The user's hash is replaced and EVERY session of the user is closed, the
        current one too: whoever knew the old password may be the one holding a session. Keys stay (they are credentials of their own). The audit event is `password.reset`, with
        no actor (the operator is not an actor of the service) and the user as the resource. Returns what the command may print: the user and how many sessions it closed, never the password or its hash.
        One derivation at the target cost, outside the transaction; `passwords.GATE` is the API's and is not used here."""
        fresh = passwords.hash_password(new)
        with self.transaction() as c:
            row = c.execute('SELECT id FROM memory.actors WHERE username=%s', (username,)).fetchone()
            if not row:
                raise NotFound()
            c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s', (fresh, row['id']))
            closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL', (row['id'],)).rowcount
            self._access_changed(c, {'id': None}, 'password.reset', resource_id=row['id'])
        return {'username': username, 'sessions_revoked': closed}
