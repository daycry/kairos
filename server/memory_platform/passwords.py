"""Passwords: every scrypt derivation of the service lives here (CA-09, DC-5).

The cost is the one measured in T-01 (`improvement-plan.md`, «Valores medidos»): `n=2^17, r=8, p=1`, about 128 MB and 0.5 to 0.9 s per derivation.
Three rules keep that cost from being a weapon against the service:

* A login makes ONE derivation at the target cost whatever happens (right password, wrong password, unknown or disabled user, an old hash): `check_login`.
* A stored hash whose parameters are ABOVE the target is rejected without deriving it (`verify_password`): nobody can store a hash that costs more than the service pays.
* A hash made with a lower cost (an earlier release) is verified at its own cost and replaced by one at the target cost after the first correct login (`check_login` returns it).

`hashlib.scrypt` releases the GIL (measured in T-01), so a derivation does not stop the other requests of the process; what bounds the memory of the API is the
semaphore of `LoginGate` (below), not this module's functions.
"""
import hashlib
import hmac
import json
import secrets

from .errors import MemoryError

MIN_LENGTH, MAX_LENGTH = 12, 1024
# (n, r, p) measured in T-01. `TARGET` is what the service uses; it is a module attribute only so the test suite can lower it for its hundreds of fixtures
# (`tests/__init__.py`), and `tests/test_passwords.py` runs the real one. `DEFAULT_PARAMS` is never rebound.
DEFAULT_PARAMS = (2 ** 17, 8, 1)
TARGET = DEFAULT_PARAMS
SALT_BYTES = 16
_DUMMY_SALT = bytes(SALT_BYTES)
_DUMMY_DIGEST = bytes(64)


def _maxmem(n, r, p):
    """What OpenSSL needs for these parameters (128*r*(n+2) for the table plus 128*r*p for the blocks) with a megabyte of margin. The default of `hashlib.scrypt` (32 MiB) rejects `n=2^17`."""
    return 128 * r * (n + p + 2) + (1 << 20)


def _derive(password, salt, params):
    """THE derivation: the only call to `hashlib.scrypt` of the service (a test counts the calls here)."""
    n, r, p = params
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=n, r=r, p=p, maxmem=_maxmem(n, r, p))


def _encode(salt, params, digest):
    n, r, p = params
    return json.dumps({'v': 1, 'n': n, 'r': r, 'p': p, 'salt': salt.hex(), 'hash': digest.hex()})


def _parse(encoded):
    """(params, salt, digest) of a stored hash; ValueError, KeyError or TypeError when it is not one of ours or its numbers make no sense."""
    data = json.loads(encoded)
    if not isinstance(data, dict) or data['v'] != 1:
        raise ValueError('hash version')
    params = tuple(data[key] for key in ('n', 'r', 'p'))
    if any(type(value) is not int or value < 1 for value in params) or params[0] < 2 or params[0] & (params[0] - 1):
        raise ValueError('hash parameters')
    return params, bytes.fromhex(data['salt']), bytes.fromhex(data['hash'])


def above_target(params):
    """A stored cost the service would not pay today: any of n, r or p over the target."""
    return any(have > want for have, want in zip(params, TARGET))


def _check_length(password):
    if not isinstance(password, str) or len(password) < MIN_LENGTH or len(password) > MAX_LENGTH:
        raise MemoryError('invalid_password', 'Password must contain 12 to 1024 characters', 422)


def hash_password(password):
    """A new hash at the target cost (one derivation). The length rule of the service is checked here, before deriving."""
    _check_length(password)
    salt = secrets.token_bytes(SALT_BYTES)
    return _encode(salt, TARGET, _derive(password, salt, TARGET))


def verify_password(password, encoded):
    """Whether `password` is the one behind `encoded`. A hash that is not ours, or whose parameters are above the target, is False without deriving anything."""
    try:
        params, salt, expected = _parse(encoded)
    except (ValueError, KeyError, TypeError):
        return False
    if above_target(params):
        return False
    return hmac.compare_digest(_derive(password, salt, params), expected)


def needs_rehash(encoded):
    """True for a readable hash whose parameters are not the target ones (an earlier release's)."""
    try:
        params = _parse(encoded)[0]
    except (ValueError, KeyError, TypeError):
        return False
    return params != TARGET


def dummy_hash():
    """The hash that stands for an unknown or disabled user: the target cost, no password behind it."""
    return _encode(_DUMMY_SALT, TARGET, _DUMMY_DIGEST)


def check_login(password, encoded):
    """(ok, new_hash) for a login attempt, with exactly one derivation at the target cost in every case.

    `encoded` is the stored hash of the user, or None when there is no such enabled user. `new_hash` is a hash at the target cost to store when the password was right and the stored
    one was made with a lower cost; otherwise None. An unreadable stored hash or one above the target costs the same single derivation (against the dummy) and never verifies."""
    try:
        params, salt, expected = _parse(encoded) if encoded is not None else (None, None, None)
    except (ValueError, KeyError, TypeError):
        params = None
    if params is None or above_target(params):
        _derive(password, _DUMMY_SALT, TARGET)
        return False, None
    right = hmac.compare_digest(_derive(password, salt, params), expected)
    if params == TARGET:
        return right, None
    fresh = secrets.token_bytes(SALT_BYTES)  # an old hash: the cheap check above plus one derivation at the target cost, the one that becomes the new hash
    digest = _derive(password, fresh, TARGET)
    return right, _encode(fresh, TARGET, digest) if right else None
