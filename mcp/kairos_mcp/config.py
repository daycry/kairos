"""Settings from the environment: `KAIROS_API_URL` (required), `KAIROS_API_TIMEOUT` (seconds, default 30), `KAIROS_ALLOWED_ORIGINS` and `KAIROS_MAX_BODY_BYTES`."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BODY_BYTES = 262144  # the server's own default (MEMORY_MAX_BODY_BYTES)
MAX_BODY_BYTES_CEILING = 16 * 1024 * 1024


@dataclass(frozen=True)
class Config:
    api_url: str
    timeout: float = DEFAULT_TIMEOUT
    allowed_origins: tuple = ()
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES


def parse_timeout(value):
    if value is None or str(value).strip() == '':
        return DEFAULT_TIMEOUT
    try:
        timeout = float(value)
    except ValueError:
        raise ValueError('KAIROS_API_TIMEOUT must be a number of seconds') from None
    if not 0 < timeout <= 600:
        raise ValueError('KAIROS_API_TIMEOUT must be above 0 and at most 600 seconds')
    return timeout


def parse_max_body_bytes(value):
    if value is None or str(value).strip() == '':
        return DEFAULT_MAX_BODY_BYTES
    try:
        size = int(value)
    except ValueError:
        raise ValueError('KAIROS_MAX_BODY_BYTES must be a whole number of bytes') from None
    if not 0 < size <= MAX_BODY_BYTES_CEILING:
        raise ValueError('KAIROS_MAX_BODY_BYTES must be above 0 and at most %d' % MAX_BODY_BYTES_CEILING)
    return size


def parse_api_url(value):
    url = (value or '').strip().rstrip('/')
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('KAIROS_API_URL is required and must be an http(s) URL, for example http://memory-api:8790')
    return url


def from_env(env=None):
    env = os.environ if env is None else env
    origins = tuple(value.strip() for value in env.get('KAIROS_ALLOWED_ORIGINS', '').split(',') if value.strip())
    return Config(parse_api_url(env.get('KAIROS_API_URL')), parse_timeout(env.get('KAIROS_API_TIMEOUT')), origins,
                  parse_max_body_bytes(env.get('KAIROS_MAX_BODY_BYTES')))
