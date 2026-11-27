"""Store mixin: the one door for the changes of access (CA-01, design.md O2, DC-1, DC-10).

Every writer of a change of who may do what that this initiative adds lives here and ends in `_access_changed`, which audits the change and empties the permission cache of
the transaction. `tests/test_auth_cache.py` walks this module: a function that writes `actors`, `project_grants`, `api_keys` or `web_sessions` here and does not end in
`_access_changed` fails there. `admin.py` calls these methods and has no SQL of its own for them (DC-10), so the audit, the closing of sessions and the emptying of the cache
have one implementation.

What decides an access is NOT here: the resolver (`store_auth.py`) reads `is_admin`, `project_grants` and the permissions of a key. A function of this module that has to read one of
those to change an access is declared on `READ_EXCEPTIONS` of that walk, with its reason.
"""
import secrets
from contextlib import nullcontext

from . import limits, passwords
from .auth import KEY_EXPIRY_MAX, lock_attempts, token_hash
from .auth_scope import invalidate_auth
from .errors import Conflict, Forbidden, MemoryError, NotFound
from .store_common import as_dict, canonical, new_id

# `POST /v1/auth/password`: at most this many CORRECT changes per user in the last 15 minutes (fix1 of the review of phase 2, gap 1). The failures have their own limit (10 per user or per IP,
# the one of the login). A person changes a password once; five leave room for a typing mistake that was accepted, a password manager and a second device, and bound what a stolen session
# can make the service derive (two derivations of 128 MB per change) to a handful per quarter of an hour.
PASSWORD_CHANGES_PER_WINDOW = 5
# The count does not read `audit_events` whole (fix2 of the review of phase 2, gap 2: 1 M old rows cost 190 ms per request). There is no index on `happened_at` and the schema is closed (version 13), so it
# is bounded by the primary key: `id` is an identity that the same INSERT assigns together with `happened_at`, so both grow together. LAST_OLD_EVENT is a backward walk of the key that stops at the first row
# older than the window (a few buffers however large the table is) and CHANGES_WAIT reads only the `id` above it, still filtering by `happened_at`. Limit declared in design.md DC-5: the order by `id` is the
# order of the clock only to the microsecond, so a row whose `id` and `happened_at` disagree at the very edge of the window (two sessions inserting in the same microsecond, or a clock stepped back by minutes)
# may be counted or missed by that margin.
LAST_OLD_EVENT = "SELECT id FROM memory.audit_events WHERE happened_at<=clock_timestamp()-interval '15 minutes' ORDER BY id DESC LIMIT 1"
# The seconds until the oldest of the last PASSWORD_CHANGES_PER_WINDOW changes leaves the window (the `Retry-After` of the 429), or no row when there are fewer.
CHANGES_WAIT = ("SELECT ceil(extract(epoch FROM happened_at + interval '15 minutes' - clock_timestamp()))::bigint AS wait FROM memory.audit_events WHERE id>%s AND actor_id=%s "
                "AND action='password.changed' AND happened_at>clock_timestamp()-interval '15 minutes' ORDER BY happened_at DESC OFFSET %s LIMIT 1")


# The advisory lock that serialises every disabling and enabling (T-13): «the last active administrator» is a count over several rows, and two disablings of two different administrators at once
# would each see the other one still active. Under it the count is exact: each statement of READ COMMITTED sees what the previous holder committed.
ADMINS_LOCK = 'access-admins'

# `POST /v1/keys/{id}/rotate` (CA-07, decision 9.1): the old key keeps working this long after the rotation unless the request says otherwise (0 = it stops at once). The
# longest grace a request may ask for is ROTATION_GRACE_MAX (the model refuses more with 422): the point of a rotation is that the old key goes away.
ROTATION_GRACE = 86400
ROTATION_GRACE_MAX = 7 * 86400


def password_changes_left(c, actor):
    """429 `too_many_attempts` (`limits.too_many`, with `Retry-After`) when the user already made `PASSWORD_CHANGES_PER_WINDOW` correct changes in the last 15 minutes (counted in the audit
    events of `password.changed`, bounded by the key: see above)."""
    old = c.execute(LAST_OLD_EVENT).fetchone()
    row = c.execute(CHANGES_WAIT, (old['id'] if old else 0, actor['id'], PASSWORD_CHANGES_PER_WINDOW - 1)).fetchone()
    if row:
        raise limits.too_many('too_many_attempts', row['wait'])


def live_sessions(c, actor, user_id):
    """The live sessions of `user_id` (not revoked, not expired) as the two lists show them: creation, expiry, client address and whether it is the caller's; never a token or a hash."""
    rows = c.execute('SELECT id,created_at,expires_at,client_ip FROM memory.web_sessions WHERE actor_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp() ORDER BY created_at,id', (user_id,)).fetchall()
    return [{'id': r['id'], 'created_at': r['created_at'].isoformat() if r['created_at'] else None, 'expires_at': r['expires_at'].isoformat(), 'client_ip': r['client_ip'],
             'current': r['id'] == actor.get('session_id')} for r in rows]


class AccessMixin:
    def _access_changed(self, c, actor, action, project_id=None, resource_id=None):
        """The end of every writer of access: the audit event of the change, then the permission cache of this transaction emptied (what was resolved before the change must not outlive it)."""
        self._audit(c, actor, action, project_id, resource_id)
        invalidate_auth(c)

    def change_password(self, actor, current, new, client_ip='', slot=None):
        """`POST /v1/auth/password`: with the right current password, replace the hash, close every OTHER session of the user and keep this one and the keys.

        Only a session may do it (a key is a different credential and gets 403). The order is DC-5's: first the checks that need no derivation and take no slot (the credential is alive, the new
        password has a valid length, the IP or the user is not blocked by failures: 429 `rate_limited`, the user has not made too many changes: 429 `too_many_attempts`, both from `limits.too_many`
        with `Retry-After`), then the slot of the
        gate (`slot`, a callable that returns a context manager: the route gives `passwords.GATE.hold(ip)`; none in the tests and `admin`), then the derivations: the verification of the current password
        at the cost of ITS hash (a hash of an earlier release costs the cheap check, not a second derivation at the target cost) and the hash of the new one, outside any transaction.
        A wrong current password changes nothing and is a failed login of `client_ip`: it is recorded (committed on its own, under the advisory locks of the login, with the same recount) and
        refused with 403. The last transaction locks the row of the user, checks the session again, recounts the changes and replaces the hash only if it is still the one that was verified."""
        with self.transaction() as c:
            self._active(c, actor)  # the credential is alive: a revoked one is 401 before anything else is said about the request
            if actor.get('credential_type') != 'session':
                raise Forbidden('Only a signed-in session may change the password')
            passwords.check_length(new)  # before anything is derived
            limits.check_user_or_ip(c, actor['username'], client_ip)
            password_changes_left(c, actor)
            stored = c.execute('SELECT password_hash FROM memory.actors WHERE id=%s', (actor['id'],)).fetchone()['password_hash']
        with (slot or nullcontext)():
            right = passwords.verify_password(current, stored)
            fresh = passwords.hash_password(new) if right else None
        if not right:
            with self.transaction() as c:  # committed on its own, before the refusal is raised
                lock_attempts(c, actor['username'], client_ip)
                limits.check_user_or_ip(c, actor['username'], client_ip)  # other failures arrived while this request derived: not one more is written
                c.execute('INSERT INTO memory.login_attempts(username,client_ip) VALUES(%s,%s)', (actor['username'], client_ip))
            raise MemoryError('invalid_current_password', 'The current password is not correct', 403)
        with self.transaction() as c:
            # The row of the user is locked first (`admin set-password`, the login that replaces an old hash and another change take it too): the count of changes is exact for two requests at once, and
            # `WHERE password_hash=<the one verified>` keeps a password changed meanwhile from being overwritten. The session is checked AFTER the lock, with the cache emptied (fix1 of the review of
            # phase 3, gap 2): a disabling, `users/{id}/sessions/revoke` or `revoke-others` that closed it while this derived holds that row until it commits, and then this request is 401, with
            # nothing changed and no event. Only the other LIVE sessions are closed (gap 5): an expired one is already dead.
            c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR NO KEY UPDATE', (actor['id'],))
            invalidate_auth(c)
            self._active(c, actor)
            password_changes_left(c, actor)
            if not c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s AND password_hash=%s', (fresh, actor['id'], stored)).rowcount:
                raise Conflict('The password changed while this request was running')
            c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND id<>%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (actor['id'], actor['session_id']))
            self._access_changed(c, actor, 'password.changed', resource_id=actor['id'])
        return {'changed': True}

    def set_password(self, username, new, revoke_keys=False):
        """`admin set-password`: the recovery of an account by the operator (no actor, no current password). The user's hash is replaced and EVERY session of the user is closed, the
        current one too: whoever knew the old password may be the one holding a session. The API keys of the user stay (they are credentials of their own) unless `revoke_keys`: then
        they are revoked in the same transaction, which is what recovering an account that someone else had access to needs (a key that person made would otherwise keep working).
        The audit event is `password.reset`, with no actor (the operator is not an actor of the service) and the user as the resource, plus `keys.revoked` when keys were revoked.
        Returns what the command may print: the user and how many sessions and keys it closed (the live ones: an expired session is already dead and is not rewritten), never the password or its hash.
        One derivation at the target cost, outside the transaction; `passwords.GATE` is the API's and is not used here."""
        fresh = passwords.hash_password(new)
        with self.transaction() as c:
            row = c.execute('SELECT id FROM memory.actors WHERE username=%s', (username,)).fetchone()
            if not row:
                raise NotFound()
            c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s', (fresh, row['id']))
            closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (row['id'],)).rowcount
            keys = c.execute('UPDATE memory.api_keys SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL', (row['id'],)).rowcount if revoke_keys else 0
            if keys:
                self._audit(c, {'id': None}, 'keys.revoked', resource_id=row['id'])
            self._access_changed(c, {'id': None}, 'password.reset', resource_id=row['id'])
        return {'username': username, 'sessions_revoked': closed, 'keys_revoked': keys}

    def set_user_disabled(self, actor, user_id, disabled):
        """`PATCH /v1/users/{id}` (CA-03): the global administrator disables or enables a user. Disabling closes every session of the user and leaves the keys without value while it lasts
        (`actors.disabled` is checked by every credential); enabling brings back the keys that were not revoked, not the sessions. Never oneself, never the last active administrator (409).
        `disabled` None (a body without a change) is 422 `invalid_user_update`, decided AFTER the caller is authorized: someone who may not do it gets 403 whatever it sends."""
        with self.transaction() as c:
            self._global_admin(c, actor)  # 401/403 before anything is locked
            if disabled is None:
                raise MemoryError('invalid_user_update', 'Nothing to change', 422)
            return self._set_disabled(c, actor, user_id, disabled)

    def operator_set_disabled(self, username, disabled):
        """`admin disable-user`/`enable-user` (DC-10): the same writer, with no request actor (the operator is not an actor of the service, so «never oneself» does not apply; «never the last
        active administrator» does)."""
        with self.transaction() as c:
            row = c.execute('SELECT id FROM memory.actors WHERE username=%s', (username,)).fetchone()
            if not row:
                raise NotFound()
            return self._set_disabled(c, None, row['id'], disabled)

    def _set_disabled(self, c, actor, user_id, disabled):
        """The writer of `disabled`. Order: the advisory lock of every disabling (the count of active administrators is exact under it: nothing else writes `disabled` or `is_admin` at run
        time), then the rows of the target and of the caller under `FOR NO KEY UPDATE` in the order of their ids (fix1 of the review of phase 3, gap 4; the pattern of `replace_grants`), then the
        cache emptied and the credential of the caller checked AGAIN (it may have been disabled, or its session closed, while this waited), then the checks and the writes. The row of the
        user is locked BEFORE the closing of its sessions: a login of the user in progress holds `FOR SHARE` on that row, so the lock waits for it and the closing that follows (a new
        statement) sees the session it opened; a login that comes after sees `disabled` under its own lock and opens none. Only the live sessions are closed (gap 5): an expired one is
        already dead, and `sessions_revoked` counts what `users/{id}/sessions/revoke` counts.
        No wait in a circle: the advisory lock comes first in every disabling and nothing else takes it, and every writer of this module that locks two rows of `actors` takes them in the
        order of their ids."""
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (ADMINS_LOCK,))
        c.execute('SELECT id FROM memory.actors WHERE id=ANY(%s) ORDER BY id FOR NO KEY UPDATE', ([user_id] + ([actor['id']] if actor else []),))
        invalidate_auth(c)
        if actor:
            self._global_admin(c, actor)
        target = c.execute('SELECT id,username,is_admin,disabled FROM memory.actors WHERE id=%s', (user_id,)).fetchone()
        if not target:
            raise NotFound()
        if disabled and actor and user_id == actor['id']:
            raise Conflict('An administrator cannot disable itself')
        if disabled and target['is_admin'] and not target['disabled'] and c.execute('SELECT count(*) AS n FROM memory.actors WHERE is_admin AND NOT disabled').fetchone()['n'] <= 1:
            raise Conflict('The last active administrator cannot be disabled')
        c.execute('UPDATE memory.actors SET disabled=%s WHERE id=%s', (disabled, user_id))
        closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (user_id,)).rowcount if disabled else 0
        self._access_changed(c, actor or {'id': None}, 'user.disabled' if disabled else 'user.enabled', resource_id=user_id)
        return {'id': user_id, 'username': target['username'], 'disabled': disabled, 'sessions_revoked': closed}

    def replace_grants(self, actor, user_id, grants):
        """`PUT /v1/users/{id}/grants` (CA-04): the global administrator replaces the permissions per project of a user, all of them at once. The keys of the user are bounded by them
        (`_require` intersects a key with the grants of its owner), so the next request of a session or a key on a project taken away answers as a project without access. A project that
        does not exist, or one named twice, is 422 `invalid_grants` and nothing changes. The event `grants.replaced` carries the grants before and after: `audit_events` has no column for
        them and version 13 is closed, so they travel as canonical JSON in `resource_id`, as `retention_prune` does (`{"after": ..., "before": ..., "user": <id>}`; format in `docs/operations.md`).
        The caller is authorized BEFORE the grants are judged (fix1 of the review of phase 3, gap 11): someone who may not do it gets 403, not the 422 of a project named twice."""
        with self.transaction() as c:
            self._global_admin(c, actor)  # 401/403 before anything is locked or judged
            wanted = {}
            for grant in grants:
                grant = as_dict(grant)
                if grant['project_id'] in wanted:
                    raise MemoryError('invalid_grants', 'A project is named more than once', 422)
                wanted[grant['project_id']] = sorted(set(grant['permissions']))
            # The rows of the target and of the caller, in the order of their ids: two replacements of one user wait for each other (the second reads the grants the first left), and a
            # disabling of the caller that commits meanwhile is seen by the check that follows the wait.
            rows = c.execute('SELECT id,username FROM memory.actors WHERE id=ANY(%s) ORDER BY id FOR NO KEY UPDATE', ([user_id, actor['id']],)).fetchall()
            invalidate_auth(c)
            self._global_admin(c, actor)
            target = next((r for r in rows if r['id'] == user_id), None)
            if not target:
                raise NotFound()
            known = {r['id'] for r in c.execute('SELECT id FROM memory.projects WHERE id=ANY(%s)', (list(wanted),)).fetchall()}
            if set(wanted) - known:
                raise MemoryError('invalid_grants', 'Unknown project', 422)
            before = {}
            for row in c.execute('SELECT project_id,permission FROM memory.project_grants WHERE actor_id=%s ORDER BY project_id,permission', (user_id,)).fetchall():
                before.setdefault(row['project_id'], []).append(row['permission'])
            c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (user_id,))
            for project, permissions in sorted(wanted.items()):
                for permission in permissions:
                    c.execute('INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,%s)', (user_id, project, permission))
            self._access_changed(c, actor, 'grants.replaced', resource_id=canonical({'user': user_id, 'before': before, 'after': wanted}))
        return {'id': user_id, 'username': target['username'], 'grants': [{'project_id': p, 'permissions': wanted[p]} for p in sorted(wanted)]}

    def list_own_sessions(self, actor):
        """`GET /v1/auth/sessions` (CA-05): the sessions of the user that are still alive, with their creation, expiry, client address and which one is the current; never a token or a hash.
        Only a session may ask (a key is a credential of a machine, not of the person signed in: 403)."""
        with self.transaction() as c:
            self._active(c, actor)
            if actor.get('credential_type') != 'session':
                raise Forbidden('Only a signed-in session may list the sessions')
            return live_sessions(c, actor, actor['id'])

    def list_user_sessions(self, actor, user_id):
        """`GET /v1/users/{id}/sessions` (CA-42; fix1 of the review of phase 3, gap 10): the global administrator with a session lists the live sessions of a user, with the fields of
        `GET /v1/auth/sessions` (`current` is true only for the caller's own session, when it names itself); never a token or a hash. A key or anyone else gets 403 (`_global_admin`), an
        unknown user 404. It reads `web_sessions`, which decides no access: no entry on the closed lists of the guard."""
        with self.transaction() as c:
            self._global_admin(c, actor)
            if not c.execute('SELECT 1 FROM memory.actors WHERE id=%s', (user_id,)).fetchone():
                raise NotFound()
            return live_sessions(c, actor, user_id)

    def revoke_other_sessions(self, actor):
        """`POST /v1/auth/sessions/revoke-others` (CA-05): close every other session of the user and keep this one. The row of the user is locked first (a login in progress holds `FOR SHARE`
        on it: the session it opens is closed here too) and the credential is checked again after the wait."""
        with self.transaction() as c:
            self._active(c, actor)
            if actor.get('credential_type') != 'session':
                raise Forbidden('Only a signed-in session may close the other sessions')
            c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR NO KEY UPDATE', (actor['id'],))
            invalidate_auth(c)
            self._active(c, actor)
            closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND id<>%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (actor['id'], actor['session_id'])).rowcount
            self._access_changed(c, actor, 'sessions.revoked', resource_id=actor['id'])
        return {'revoked': closed}

    def revoke_user_sessions(self, actor, user_id):
        """`POST /v1/users/{id}/sessions/revoke` (CA-05): the global administrator closes every session of a user (the caller's own too when it names itself). Rows of the target and of the caller
        under `FOR NO KEY UPDATE` in the order of their ids, then the credential checked again."""
        with self.transaction() as c:
            self._global_admin(c, actor)
            rows = c.execute('SELECT id FROM memory.actors WHERE id=ANY(%s) ORDER BY id FOR NO KEY UPDATE', ([user_id, actor['id']],)).fetchall()
            invalidate_auth(c)
            self._global_admin(c, actor)
            if user_id not in {r['id'] for r in rows}:
                raise NotFound()
            closed = c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE actor_id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (user_id,)).rowcount
            self._access_changed(c, actor, 'sessions.revoked', resource_id=user_id)
        return {'id': user_id, 'revoked': closed}

    def rotate_key(self, actor, key_id, grace_seconds=None):
        """`POST /v1/keys/{id}/rotate` (CA-07): a new key with the name, projects and permissions of the old one and the SAME owner (`actor_id`: the rotation replaces the key of
        a machine, whichever of the two that may do it asks for it), shown once in this answer. The old key stops at the end of the grace (`grace_seconds`, ROTATION_GRACE by default,
        0 = at once; never later than its own expiry) and keeps the id of its successor in `replaced_by`. The new key expires after the same number of SECONDS the old one was given
        (from now, whatever the time zone of the session; at most KEY_EXPIRY_MAX), or never if the old one never did (P-03): a rotation neither widens nor shortens what the key was
        made for.

        Who may (decision of the user, 2026-11-27; fix1 of the review of phase 4, gap 1): the OWNER of the key or the global administrator (a session or the bootstrap, never a key:
        `_global_admin`), with a credential that may issue the key (`_delegate`: admin and each scope on each project of the key). Anyone else gets the 404 of an unknown key
        (gap 3: no answer tells a key of another user from an invented id); a project administrator who could issue a key like it would otherwise get a token that acts as its owner.

        Order: the credential is alive (401), the key exists (404) and the caller may rotate it (404/403), all WITHOUT a lock (gap 4: a caller that may not rotate the key never waits
        for, nor makes wait, the rows of its owner); then the rows of the caller and of the owner of the key (`FOR SHARE`, in the order of their ids: a disabling, `set-password
        --revoke-keys`, a logout or a revocation that changes them waits for this rotation or makes it wait, never both) and the row of the key (`FOR NO KEY UPDATE`: two rotations of
        one key wait for each other and the second sees `replaced_by`), the cache emptied and the caller authorized AGAIN (401/403/404), and only then the state of the key: revoked,
        expired or already rotated is 409 and nothing is issued. The event `key.rotated` carries `{"key": <old id>, "replaced_by": <new id>}` (canonical JSON in `resource_id`, as
        `grants.replaced`), never the token."""
        grace = ROTATION_GRACE if grace_seconds is None else grace_seconds

        def may_rotate(c, key):
            if key['actor_id'] != actor['id']:
                try:
                    self._global_admin(c, actor)
                except Forbidden:
                    raise NotFound() from None  # the answer of an unknown key
            self._delegate(c, actor, key['project_ids'], key['scopes'])
        with self.transaction() as c:
            self._active(c, actor)  # a dead credential is 401 before anything is said about the key
            found = c.execute('SELECT actor_id,project_ids,scopes FROM memory.api_keys WHERE id=%s', (key_id,)).fetchone()
            if not found:
                raise NotFound()
            may_rotate(c, found)  # before any lock
            c.execute('SELECT id FROM memory.actors WHERE id=ANY(%s) ORDER BY id FOR SHARE', ([actor['id'], found['actor_id']],))
            key = c.execute("SELECT actor_id,name,project_ids,scopes,revoked_at,replaced_by,expires_at IS NOT NULL AND expires_at<=clock_timestamp() AS expired FROM memory.api_keys WHERE id=%s FOR NO KEY UPDATE", (key_id,)).fetchone()
            invalidate_auth(c)
            may_rotate(c, key)  # again, after the waits: authorization before the 422 and the 409s
            if not isinstance(grace, int) or isinstance(grace, bool) or not 0 <= grace <= ROTATION_GRACE_MAX:  # the route's model refuses it first; this is for the other callers
                raise MemoryError('invalid_rotation', 'The grace of a rotation is a whole number of seconds between 0 and %d' % ROTATION_GRACE_MAX, 422)
            if key['revoked_at']:
                raise Conflict('A revoked key cannot be rotated')
            if key['expired']:
                raise Conflict('An expired key cannot be rotated')
            if key['replaced_by']:
                raise Conflict('This key was already rotated')
            token, kid = 'mp_'+secrets.token_urlsafe(48), new_id()
            # The lifetime in seconds (gap 7: `expires_at-created_at` is an interval of days, which a session with summer time adds as calendar days, an hour more or less), and
            # never past KEY_EXPIRY_MAX (gap 5: a key that expires on the last day a key may have is rotated, not a 503)
            new = c.execute("INSERT INTO memory.api_keys(id,actor_id,name,token_hash,prefix,project_ids,scopes,expires_at) SELECT %s,actor_id,name,%s,%s,project_ids,scopes,"
                            "CASE WHEN expires_at IS NULL THEN NULL ELSE LEAST(clock_timestamp()+(extract(epoch FROM expires_at-created_at)*interval '1 second'),%s::timestamptz) END "
                            "FROM memory.api_keys WHERE id=%s RETURNING expires_at",
                            (kid, token_hash(token), token[:10], KEY_EXPIRY_MAX, key_id)).fetchone()
            old = c.execute("UPDATE memory.api_keys SET replaced_by=%s, expires_at=LEAST(COALESCE(expires_at,'infinity'::timestamptz),clock_timestamp()+(%s * interval '1 second')) WHERE id=%s RETURNING expires_at",
                            (kid, grace, key_id)).fetchone()
            self._access_changed(c, actor, 'key.rotated', resource_id=canonical({'key': key_id, 'replaced_by': kid}))
        return {'id': kid, 'name': key['name'], 'token': token, 'project_ids': key['project_ids'], 'scopes': key['scopes'],
                'expires_at': new['expires_at'].isoformat() if new['expires_at'] else None, 'previous_id': key_id, 'previous_expires_at': old['expires_at'].isoformat()}
