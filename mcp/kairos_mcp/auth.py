"""The caller's credential: required as `Authorization: Bearer`, visible only while its request is served, and never stored.

kairos-mcp has no credential of its own and decides no permission. It refuses a request without a Bearer header (401, the body of the
internal MCP, no call to `/v1`) and hands the header to the tool call through a context variable that is reset when the request ends.
kairos-mcp learns whether the credential is valid from `/v1`: a 401 there becomes the 401 of the MCP request. The sessions with a cookie and a CSRF token stay in the internal MCP (P-08).
"""
import json
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


def needs_check(raw):
    """Whether a JSON-RPC body is something other than a tool call (`initialize`, `tools/list`, `ping`, a notification, a batch carrying any of them):
    a tool call finds out about its credential from the `/v1` request it makes, the rest would otherwise answer to any `Bearer`."""
    try:
        message = json.loads(raw)
    except ValueError:
        return False  # not JSON: the MCP layer refuses it as it does for any caller
    messages = message if isinstance(message, list) else [message]
    return any(not isinstance(item, dict) or item.get('method') != 'tools/call' for item in messages)


class RequireBearer:
    """`verify(authorization)` is an async check against the API (a cheap `/v1` read) that is false only when the API refuses the credential."""

    def __init__(self, app, verify=None):
        self.app, self.verify = app, verify

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
            if self.verify is not None:
                body = bytearray()  # the body is already bounded (`BodyLimit` is in front); it is read here and handed to the application again
                while True:
                    event = await receive()
                    if event['type'] == 'http.disconnect':
                        return
                    body.extend(event.get('body', b''))
                    if not event.get('more_body'):
                        break
                if needs_check(bytes(body)) and not await self.verify(value):
                    return await JSONResponse(unauthorized_body(), status_code=401)(scope, receive, send)
                given = False

                async def receive(replayed=receive):  # the application reads the same body, then whatever the server sends next
                    nonlocal given
                    if not given:
                        given = True
                        return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                    return await replayed()
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
