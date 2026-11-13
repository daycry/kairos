"""The caller's credential: required as `Authorization: Bearer`, visible only while its request is served, and never stored.

kairos-mcp has no credential of its own and decides no permission. It refuses a request without a Bearer header (401, the body of the
internal MCP, no call to `/v1`) and hands the header to the tool call through a context variable that is reset when the request ends.
The sessions with a cookie and a CSRF token stay in the internal MCP (P-08).
"""
from contextvars import ContextVar

from starlette.responses import JSONResponse

from .errors import unauthorized_body

_authorization = ContextVar('kairos_mcp_authorization', default=None)


def current_authorization():
    """The `Authorization` header of the request being served, or `None` outside of one."""
    return _authorization.get()


def bearer(headers):
    """The header value when it is `Bearer <token>` (the scheme in any case), else `None`."""
    value = headers.get('authorization', '')
    kind, _, token = value.partition(' ')
    return value if kind.lower() == 'bearer' and token.strip() else None


class RequireBearer:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {key.decode('latin-1').lower(): value.decode('latin-1') for key, value in scope['headers']}
        value = bearer(headers)
        if value is None:
            return await JSONResponse(unauthorized_body(), status_code=401)(scope, receive, send)
        token = _authorization.set(value)
        try:
            await self.app(scope, receive, send)
        finally:
            _authorization.reset(token)
