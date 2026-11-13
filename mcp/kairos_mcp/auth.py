"""The caller's credential: required as `Authorization: Bearer`, visible only while its request is served, and never stored.

kairos-mcp has no credential of its own and decides no permission. It refuses a request without a Bearer header (401, the body of the
internal MCP, no call to `/v1`) and hands the header to the tool call through a context variable that is reset when the request ends.
kairos-mcp learns whether the credential is valid from `/v1`: a 401 there becomes the 401 of the MCP request. The sessions with a cookie and a CSRF token stay in the internal MCP (P-08).
"""
from contextvars import ContextVar

from starlette.responses import JSONResponse

from .errors import unauthorized_body

_authorization = ContextVar('kairos_mcp_authorization', default=None)
_verdict = ContextVar('kairos_mcp_verdict', default=None)  # one dict per request: what `/v1` said about its credential


def current_authorization():
    """The `Authorization` header of the request being served, or `None` outside of one."""
    return _authorization.get()


def credential_refused():
    """`/v1` answered 401 to the credential of the request being served: its MCP response becomes that 401 (see `RequireBearer`)."""
    verdict = _verdict.get()
    if verdict is not None:
        verdict['refused'] = True


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
        token, verdict = _authorization.set(value), {'refused': False}
        marker = _verdict.set(verdict)
        try:
            if scope['method'] != 'POST':
                return await self.app(scope, receive, send)
            # The MCP answer is one JSON message: hold it until the call is over, so that a credential `/v1` refused turns it into the 401 of the internal
            # MCP (same body) instead of a successful HTTP exchange that carries a tool error.
            held = []

            async def hold(message):
                held.append(message)
            await self.app(scope, receive, hold)
            if verdict['refused']:
                return await JSONResponse(unauthorized_body(), status_code=401)(scope, receive, send)
            for message in held:
                await send(message)
        finally:
            _verdict.reset(marker)
            _authorization.reset(token)
