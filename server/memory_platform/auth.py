"""Primary-database authentication and scoped authorization."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from .errors import Forbidden, MemoryError, NotFound, Unauthorized
from .auth_scope import invalidate_auth, savepoint
from . import limits, observability, passwords
from .store_pool import connection_wait
from .passwords import check_login, hash_password, verify_password  # noqa: F401  (re-exported: the callers and tests that import them from here)

SCOPES = frozenset({'read', 'write', 'publish', 'validate', 'admin'})
# `last_used_at` of a key (CA-06, DC-7): written by the authentication of the key at most once per LAST_USED_EVERY seconds and key, in a short transaction of its own whose
# `lock_timeout` is LAST_USED_LOCK_TIMEOUT and that waits for a connection of the pool at most LAST_USED_POOL_WAIT seconds. A row held by another transaction (the `FOR SHARE` of
# `extended_store.py` and `corpus_answers.py`) or a full pool makes the write give up, not the request. The clock of the process moves BEFORE every attempt (fix1 of the review of
# phase 4, gap 8: requests in between never try again): a minute after a write that got in, LAST_USED_RETRY seconds after one that gave up (fix2, attempt 2, row 2, CWE-778: a
# minute after a failure let whoever holds one write a minute freeze the last use of a stolen key). A write that gives up warns at most once per LAST_USED_WARN_EVERY seconds and key,
# with the id of the key (public; never its token or prefix). The statement also skips a row written less than a minute ago (by another process). `last_used_at` is best effort:
# it may lag the real use by a minute plus the failed attempts; it is not an audit record.
LAST_USED_EVERY = 60
LAST_USED_RETRY = 5
LAST_USED_WARN_EVERY = 60
LAST_USED_LOCK_TIMEOUT = '50ms'
LAST_USED_POOL_WAIT = 0.05
# The latest expiry a key may have (fix1 of the review of phase 4, gap 5). The database stores later ones, but the driver loads a `timestamptz` into a Python datetime, whose last year
# is 9999: a later expiry was a 503 when created and made the key impossible to rotate or list. A day short of the end of 9999 in UTC, so that it loads in any session time zone. A
# creation past it is 422 `invalid_key_expiry`; a rotation gives the new key at most this expiry.
KEY_EXPIRY_MAX = '9999-12-31T00:00:00+00:00'
TOUCH_KEY = "UPDATE memory.api_keys SET last_used_at=clock_timestamp() WHERE id=%s AND (last_used_at IS NULL OR last_used_at<=clock_timestamp()-interval '1 minute')"


def lock_attempts(c, username, client_ip):
    """The advisory locks that serialise the recount and the record of the failures of a user and of an IP: the login and the change of password take them the same way, in a fixed order
    (so two requests never wait for each other in a circle) and for the length of the transaction."""
    for lock in sorted(('login-user:'+username, 'login-ip:'+client_ip)):
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (lock,))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, store, allowed_origins=(), session_ttl=43200, clock=None, record_use=True):
        self.store = store
        self.allowed_origins = frozenset(allowed_origins)
        self.session_ttl = session_ttl
        self.clock = clock or time.monotonic  # injected by the tests of `last_used_at`
        self.next_use = {}  # key id -> clock from which this process may try again to write its `last_used_at`
        self.warned = {}  # key id -> clock of the last `key_last_used_deferred` of the key by this process
        self.record_use = record_use  # False: a check of a key that is not a request (`probe.valid_key`) leaves its last use alone (fix1 of the review of phase 4, gap 9)

    def _actor(self, c, row, credential_type, credential_id=None):
        return self.store._describe(c, row, credential_type, credential_id)  # permissions are resolved in one place (store_auth.py)

    def authenticate_bearer(self, token):
        if not token:
            raise Unauthorized()
        with self.store.transaction() as c:
            row = c.execute('SELECT a.*, k.id AS credential_id FROM memory.api_keys k JOIN memory.actors a ON a.id=k.actor_id WHERE k.token_hash=%s AND k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp()) AND NOT a.disabled', (token_hash(token),)).fetchone()
            if not row:
                raise Unauthorized()
            actor = self._actor(c, row, 'bearer', row['credential_id'])
        # The last use of the key, at most once a minute per key, in a short transaction of its own (DC-7). It never fails the request: a connection it cannot get within
        # LAST_USED_POOL_WAIT, a lock it cannot get within LAST_USED_LOCK_TIMEOUT, or any other failure, leaves it for LAST_USED_RETRY seconds later (the clock moves before the
        # attempt, so the requests that come meanwhile do not try again); a write that got in, for a minute later.
        now, kid = self.clock(), actor['key_id']
        if self.record_use and now >= self.next_use.get(kid, now):
            self.next_use[kid] = now + LAST_USED_RETRY
            try:
                with connection_wait(LAST_USED_POOL_WAIT), self.store.transaction() as c:
                    c.execute("SELECT set_config('lock_timeout', %s, true)", (LAST_USED_LOCK_TIMEOUT,))
                    c.execute(TOUCH_KEY, (kid,))
                    invalidate_auth(c)  # nothing was resolved in this transaction; the walk of the writers asks every writer of `api_keys` to end like this
            except Exception as exc:
                if kid not in self.warned or now - self.warned[kid] >= LAST_USED_WARN_EVERY:
                    self.warned[kid] = now
                    observability.log_failure('key_last_used_deferred', exc, 'warning', key_id=kid)  # the type and the id of the key only; the request goes on
            else:
                self.next_use[kid] = now + LAST_USED_EVERY
        return actor

    def authenticate_session(self, token):
        if not token:
            raise Unauthorized()
        with self.store.transaction() as c:
            row = c.execute('SELECT a.*, s.id AS credential_id FROM memory.web_sessions s JOIN memory.actors a ON a.id=s.actor_id WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() AND NOT a.disabled', (token_hash(token),)).fetchone()
            if not row:
                raise Unauthorized()
            return self._actor(c, row, 'session', row['credential_id'])

    def login(self, username, password, client_ip=''):
        """Open a session (CA-09, CA-12, CA-13, DC-5). Only failures stay in `login_attempts`, and only the IP of the client blocks (`limits.py`; P-05: never the name).

        Order (DC-5): 1) an IP with `limits.LOGIN.max_failures` failures in the window is answered 429 `rate_limited` with `Retry-After`, before anything else (no slot of the gate, no derivation,
        nothing written); 2) the slot of the IP in the gate (full: 503 `login_busy`, not a failure); 3) under the advisory locks of the IP and the name, the IP is counted again and the attempt
        is written BEFORE the derivation, so attempts in flight count (with several processes, twenty attempts of one IP at once never get more than `max_failures` derivations); 4) one derivation;
        5) a right password removes ITS row in the transaction that opens the session (a success neither counts nor clears the failures of its IP); every refusal after 3 keeps it as a failure
        and publishes `login_user_failures` (the count of the name in the window and, for a user that exists, its id; never the name typed nor the password: it blocks nothing)."""
        with self.store.transaction() as c:
            limits.check_ip(c, client_ip)
        with passwords.GATE.hold(client_ip):
            # A separate committed transaction keeps the attempt even when authentication raises.
            with self.store.transaction() as c:
                lock_attempts(c, username, client_ip)
                limits.check_ip(c, client_ip)
                attempt = c.execute('INSERT INTO memory.login_attempts(username,client_ip) VALUES(%s,%s) RETURNING id', (username, client_ip)).fetchone()['id']
                failures = limits.user_failures(c, username)  # read on every attempt, a user that exists or not: the same statements whatever the name
                row = c.execute('SELECT * FROM memory.actors WHERE username=%s AND NOT disabled', (username,)).fetchone()
            user_id = row['id'] if row else None
            try:
                # One derivation at the target cost for every attempt: unknown or disabled user (the dummy hash), wrong password and right password alike (passwords.py).
                right, rehash = check_login(password, row['password_hash'] if row else None)
                if not right or not row:
                    raise Unauthorized()
                session, csrf, sid = secrets.token_urlsafe(48), secrets.token_urlsafe(32), secrets.token_hex(16)
                for retried in (False, True):
                    with self.store.transaction() as c:
                        # Between the verification above and this insert another transaction may have changed the password (`admin set-password`, `POST /v1/auth/password`, another login that replaced an
                        # old hash) or disabled the user. The row is read again under a lock that waits for it, and the session is opened only if the hash is still the verified one and the user is enabled
                        # (no session otherwise: a session born of the old password would outlive the closing of the sessions that change made).
                        # `FOR SHARE` waits for a transaction that changed the row and has not committed; a login that is going to replace an old hash takes `FOR NO KEY UPDATE` instead, because it writes the
                        # row next and two of them must not wait for each other (a share lock that is then upgraded).
                        current = c.execute('SELECT * FROM memory.actors WHERE id=%s FOR NO KEY UPDATE' if rehash else 'SELECT * FROM memory.actors WHERE id=%s FOR SHARE', (row['id'],)).fetchone()
                        if not current or current['disabled']:
                            raise Unauthorized()
                        if current['password_hash'] == row['password_hash']:
                            row = current
                            if rehash:
                                # The hash of an earlier release becomes one at the target cost. `WHERE password_hash=<the one read>`: a password changed meanwhile is not overwritten, and a failed write
                                # (a savepoint, so the transaction goes on) does not stop the login.
                                try:
                                    with savepoint(c):
                                        c.execute('UPDATE memory.actors SET password_hash=%s WHERE id=%s AND password_hash=%s', (rehash, row['id'], row['password_hash']))
                                except Exception as exc:
                                    observability.log_failure('password_rehash_failed', exc, 'warning')  # the type only, never the message; the login goes on
                            saved = c.execute("INSERT INTO memory.web_sessions(id,actor_id,token_hash,csrf_hash,expires_at,client_ip) VALUES(%s,%s,%s,%s,clock_timestamp()+(%s * interval '1 second'),%s) RETURNING expires_at", (sid, row['id'], token_hash(session), token_hash(csrf), self.session_ttl, client_ip)).fetchone()
                            c.execute('DELETE FROM memory.login_attempts WHERE id=%s', (attempt,))  # a success is not a failure: only its own row goes
                            invalidate_auth(c)
                            actor = self._actor(c, row, 'session', sid)
                            return {'actor': actor, 'session_token': session, 'csrf_token': csrf, 'expires_at': saved['expires_at'].isoformat()}
                    # The hash is not the verified one. Most often a second login of the same user replaced an old hash a moment ago, and the password is still right: the transaction above is closed,
                    # the password is verified ONCE against the hash that is there now (one more derivation, inside the same slot of the gate) and the session is tried one more time. If the hash changes
                    # again, or the password does not verify (`set-password`, a change of password), 401 and no session: the old password never opens a session with a new hash.
                    if retried:
                        raise Unauthorized()
                    row = current
                    right, rehash = check_login(password, row['password_hash'])
                    if not right:
                        raise Unauthorized()
            except Unauthorized:
                observability.LOGIN_USER_FAILURES.inc()
                observability.log_event('login_user_failures', 'warning', user_id=user_id, count=failures)
                raise

    def logout(self, token):
        with self.store.transaction() as c:
            # The row of the owner of the session first (T-22; revision of phase 3, attempt 2, gap 1): a `create_key` or `create_user` in progress with this session holds
            # `FOR SHARE` on it, so the logout waits for it; one that comes after waits for the logout and is refused with 401.
            owner = c.execute('SELECT actor_id FROM memory.web_sessions WHERE token_hash=%s', (token_hash(token),)).fetchone()
            if owner:
                c.execute('SELECT 1 FROM memory.actors WHERE id=%s FOR NO KEY UPDATE', (owner['actor_id'],))
            c.execute('UPDATE memory.web_sessions SET revoked_at=clock_timestamp() WHERE token_hash=%s', (token_hash(token),))
            invalidate_auth(c)

    def refresh_csrf(self,actor):
        if actor.get('credential_type')!='session':
            return ''
        token=secrets.token_urlsafe(32)
        with self.store.transaction() as c:
            self.store._active(c,actor)
            c.execute('UPDATE memory.web_sessions SET csrf_hash=%s WHERE id=%s',(token_hash(token),actor['session_id']))
            invalidate_auth(c)
        return token

    def require_csrf(self, actor, token, origin):
        if actor.get('credential_type') != 'session':
            return
        if not origin or origin not in self.allowed_origins or not token:
            raise Forbidden('Invalid origin or CSRF token')
        with self.store.transaction() as c:
            row = c.execute('SELECT csrf_hash FROM memory.web_sessions WHERE id=%s AND revoked_at IS NULL AND expires_at>clock_timestamp()', (actor.get('session_id'),)).fetchone()
        if not row or not hmac.compare_digest(row['csrf_hash'], token_hash(token)):
            raise Forbidden('Invalid origin or CSRF token')

    def require_permission(self, actor, project_id, permission):
        with self.store.transaction() as c:
            return self.store._require(c, actor, project_id, permission)
