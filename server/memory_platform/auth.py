"""Primary-database authentication and scoped authorization."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from .errors import Forbidden, MemoryError, NotFound, Unauthorized
from .auth_scope import invalidate_auth, savepoint
from . import observability, passwords
from .passwords import check_login, hash_password, verify_password  # noqa: F401  (re-exported: the callers and tests that import them from here)

SCOPES = frozenset({'read', 'write', 'publish', 'validate', 'admin'})
RECENT_ATTEMPTS = "SELECT count(*) AS n FROM memory.login_attempts WHERE happened_at>clock_timestamp()-interval '15 minutes' AND (username=%s OR client_ip=%s)"
# `last_used_at` of a key (CA-06, DC-7): written by the authentication of the key at most once per LAST_USED_EVERY seconds and key, in a short transaction of its own whose
# `lock_timeout` is LAST_USED_LOCK_TIMEOUT. A row held by another transaction (the `FOR SHARE` of `extended_store.py` and `corpus_answers.py`) makes the write give up, not the
# request: it is tried again on the next request of that key. The statement also skips a row written less than a minute ago (by another process).
LAST_USED_EVERY = 60
LAST_USED_LOCK_TIMEOUT = '50ms'
TOUCH_KEY = "UPDATE memory.api_keys SET last_used_at=clock_timestamp() WHERE id=%s AND (last_used_at IS NULL OR last_used_at<=clock_timestamp()-interval '1 minute')"


def lock_attempts(c, username, client_ip):
    """The advisory locks that serialise the recount and the record of the failures of a user and of an IP: the login and the change of password take them the same way, in a fixed order
    (so two requests never wait for each other in a circle) and for the length of the transaction."""
    for lock in sorted(('login-user:'+username, 'login-ip:'+client_ip)):
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (lock,))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, store, allowed_origins=(), session_ttl=43200, clock=None):
        self.store = store
        self.allowed_origins = frozenset(allowed_origins)
        self.session_ttl = session_ttl
        self.clock = clock or time.monotonic  # injected by the tests of `last_used_at`
        self.last_used = {}  # key id -> clock of the last write of its `last_used_at` by this process

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
        # The last use of the key, at most once a minute per key, in a short transaction of its own (DC-7). It never fails the request: a lock it cannot get within
        # LAST_USED_LOCK_TIMEOUT, or any other failure, leaves it for the next request of the key (the clock of this process is only advanced by a write that got in).
        now, kid = self.clock(), actor['key_id']
        if kid not in self.last_used or now - self.last_used[kid] >= LAST_USED_EVERY:
            try:
                with self.store.transaction() as c:
                    c.execute("SELECT set_config('lock_timeout', %s, true)", (LAST_USED_LOCK_TIMEOUT,))
                    c.execute(TOUCH_KEY, (kid,))
                    invalidate_auth(c)  # nothing was resolved in this transaction; the walk of the writers asks every writer of `api_keys` to end like this
                self.last_used[kid] = now
            except Exception as exc:
                observability.log_failure('key_last_used_deferred', exc, 'warning')  # the type only; the request goes on
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
        # 1) An IP (or a name) blocked by failures is answered 429 before anything else: no slot of the gate, no derivation, nothing written.
        with self.store.transaction() as c:
            if c.execute(RECENT_ATTEMPTS, (username, client_ip)).fetchone()['n'] >= 10:
                raise MemoryError('rate_limited', 'Too many login attempts', 429)
        # 2) One slot per IP and a bounded wait (passwords.LoginGate): full = 503 `login_busy`, which is not a failed attempt, so it is decided before the attempt is recorded.
        with passwords.GATE.hold(client_ip):
            # A separate committed transaction records failures even when authentication raises.
            with self.store.transaction() as c:
                lock_attempts(c, username, client_ip)
                if c.execute(RECENT_ATTEMPTS, (username, client_ip)).fetchone()['n'] >= 10:
                    raise MemoryError('rate_limited', 'Too many login attempts', 429)
                c.execute('INSERT INTO memory.login_attempts(username,client_ip) VALUES(%s,%s)', (username, client_ip))
                row = c.execute('SELECT * FROM memory.actors WHERE username=%s AND NOT disabled', (username,)).fetchone()
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

    def logout(self, token):
        with self.store.transaction() as c:
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
