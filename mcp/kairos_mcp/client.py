"""HTTP client of `/v1`: one persistent connection pool, the caller's credential per request (never stored), bounded time and size."""
import asyncio
import json

import httpx

from .errors import UNAVAILABLE, ToolError
from .logs import log_event

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
GENERIC_5XX_CODES = frozenset({'service_unavailable'})


def parse(chunks):
    raw = b''.join(chunks)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def domain_error(body):
    """The server's `{error: {code, message}}` body when it is a domain refusal; `None` for anything else, the generic 5xx included."""
    error = body.get('error') if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get('code'), str) and isinstance(error.get('message'), str) \
            and error['code'] not in GENERIC_5XX_CODES:
        return body
    return None


def fail(status, body):
    """The failure of a refused request: the server's own message, or the generic text when the answer carries none."""
    known = domain_error(body)
    raise ToolError(known['error']['message'] if known else UNAVAILABLE)


class ApiClient:
    def __init__(self, base_url, timeout=30.0, transport=None):
        self.timeout = timeout
        # Redirects are never followed: the credential must not travel to a place `/v1` did not name.
        self._http = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(timeout), transport=transport, follow_redirects=False,
                                       limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=30.0))

    async def aclose(self):
        await self._http.aclose()

    async def send(self, method, path, authorization, params=None, body=None):
        """One request: `(status, parsed JSON or None)` for any answer below 500; `ToolError(UNAVAILABLE)` for a timeout, a dropped
        connection, a redirect, an answer that is too large or a 5xx without a domain refusal. `authorization` is the caller's header,
        forwarded as it came and kept nowhere."""
        headers = {'Authorization': authorization, 'Accept': 'application/json'}
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            async with asyncio.timeout(self.timeout):
                request = self._http.build_request(method, path, params=params, headers=headers, **({'json': body} if body is not None else {}))
                response = await self._http.send(request, stream=True)
                try:
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ValueError('response too large')
                        chunks.append(chunk)
                finally:
                    await response.aclose()
        except (httpx.HTTPError, asyncio.TimeoutError, OSError, ValueError) as exc:
            reason = 'timeout' if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)) else type(exc).__name__
            log_event('api_unavailable', 'warning', method=method, reason=reason, duration_ms=round((loop.time() - started) * 1000, 1))
            raise ToolError(UNAVAILABLE) from None
        status, parsed = response.status_code, parse(chunks)
        if 300 <= status < 400:
            log_event('api_unavailable', 'warning', method=method, status=status, reason='redirect')
            raise ToolError(UNAVAILABLE)
        if status >= 500:
            log_event('api_unavailable', 'warning', method=method, status=status, reason='status')
            # A domain refusal that is a 5xx (`semantic_deadline_exceeded`, 503) keeps its message, as in the internal MCP; the generic
            # envelope of an unhandled failure, a bare 500 or a gateway page does not.
            if domain_error(parsed):
                return status, parsed
            raise ToolError(UNAVAILABLE)
        return status, parsed
