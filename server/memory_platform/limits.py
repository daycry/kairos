"""Limits of the service (DC-2): the one constructor of every 429, and the block of the login by the IP of the client (CA-12, CA-13, P-05).

Born in milestone A with the login block; milestone B adds here the route classes, the bucket per credential, the daily quota and the streams.

Every 429 of a limit comes out of `too_many`: status 429, a whole number of seconds of at least 1 in `retry_after` (the `Retry-After` header and the `retry_after` of the body,
`app.error`) and a fixed, complete message per code that carries the same number, because `kairos-mcp` drops the headers and passes the message through untouched.

The login is blocked by the IP of the client only, never by the name (P-05: a block by name lets anyone lock `admin` out from outside): `LOGIN.max_failures` failures of
an IP within `LOGIN.window` seconds (MEMORY_LOGIN_MAX_FAILURES, MEMORY_LOGIN_WINDOW; 10 in 15 minutes) answer 429 `rate_limited` until the oldest of the failures that make
the block leaves the window. Only failures are kept in `login_attempts` (`auth.Auth.login`); the failures of a name are published (`login_user_failures`), they block nothing.
"""
import math
from dataclasses import dataclass

from .config import DEFAULT_LOGIN_MAX_FAILURES as DEFAULT_MAX_FAILURES, DEFAULT_LOGIN_WINDOW as DEFAULT_WINDOW, check_login_failures
from .errors import MemoryError

# The fixed message of each code. The number of seconds goes at the end, in the brackets, and is the one of the header.
MESSAGES = {'rate_limited': 'Rate limit exceeded', 'too_many_attempts': 'Too many password changes'}


def too_many(code, retry_after):
    """THE 429 of a limit: `MemoryError` with status 429, `retry_after` rounded up to whole seconds (at least 1) and the fixed message of `code` (KeyError for an unknown one)."""
    message = MESSAGES[code]
    seconds = max(1, math.ceil(retry_after)) if isinstance(retry_after, (int, float)) and math.isfinite(retry_after) else 1
    return MemoryError(code, f'{message} [code={code} retry_after={seconds}]', 429, retry_after=seconds)


@dataclass(frozen=True)
class LoginLimit:
    max_failures: int = DEFAULT_MAX_FAILURES
    window: int = DEFAULT_WINDOW  # seconds


LOGIN = LoginLimit()  # the one of the process; `create_app` sets it from the settings, as it sets the gate of `passwords`


def configure_login(max_failures, window):
    global LOGIN
    LOGIN = LoginLimit(*check_login_failures(max_failures, window))


# The block of an IP, read from the index `login_attempt_ip_time (client_ip, happened_at)` (schema 13): the `max_failures`-th most recent failure of the IP inside the window, if there is
# one, and how many seconds are left until it leaves the window, when the IP is free again. A backward walk of the index that stops after `max_failures` rows.
IP_WAIT = ("SELECT ceil(extract(epoch FROM happened_at + make_interval(secs => %(window)s) - clock_timestamp()))::bigint AS wait FROM memory.login_attempts "
           "WHERE client_ip=%(ip)s AND happened_at > clock_timestamp() - make_interval(secs => %(window)s) ORDER BY happened_at DESC OFFSET %(skip)s LIMIT 1")
# The same for a name (the change of password also counts the failures of its user, DC-5). `login_attempts` has no index on the name: the walk is the one of `login_attempt_time` over the window.
USER_WAIT = ("SELECT ceil(extract(epoch FROM happened_at + make_interval(secs => %(window)s) - clock_timestamp()))::bigint AS wait FROM memory.login_attempts "
             "WHERE username=%(user)s AND happened_at > clock_timestamp() - make_interval(secs => %(window)s) ORDER BY happened_at DESC OFFSET %(skip)s LIMIT 1")
# The failures of a name in the window, for `login_user_failures` (published, never a block).
USER_FAILURES = "SELECT count(*) AS n FROM memory.login_attempts WHERE username=%(user)s AND happened_at > clock_timestamp() - make_interval(secs => %(window)s)"


def _wait(c, sql, **params):
    limit = LOGIN
    row = c.execute(sql, {**params, 'window': limit.window, 'skip': limit.max_failures - 1}).fetchone()
    return int(row['wait']) if row else None


def check_ip(c, client_ip):
    """429 `rate_limited` when the IP already has `max_failures` failures in the window."""
    wait = _wait(c, IP_WAIT, ip=client_ip)
    if wait is not None:
        raise too_many('rate_limited', wait)


def check_user_or_ip(c, username, client_ip):
    """429 `rate_limited` when the user or the IP already has `max_failures` failures in the window (the change of password, DC-5); the plazo is the longer of the two."""
    waits = [w for w in (_wait(c, USER_WAIT, user=username), _wait(c, IP_WAIT, ip=client_ip)) if w is not None]
    if waits:
        raise too_many('rate_limited', max(waits))


def user_failures(c, username):
    return c.execute(USER_FAILURES, {'user': username, 'window': LOGIN.window}).fetchone()['n']
