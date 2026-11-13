"""A bound on the request body: the server's own (`BodyLimit` of the server, 262144 bytes) so that the MCP endpoint is as hard to flood as `/v1`.

The body is counted while it arrives (a chunked body has no honest Content-Length) and an excess is a 413 with the server's error, before anything is
parsed, authenticated or sent to `/v1`.
"""
from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            incoming = event.get('body', b'')
            if len(body) + len(incoming) > self.maximum:
                response = JSONResponse({'error': {'code': 'body_too_large', 'message': 'Request body exceeds limit'}, 'request_id': ''}, status_code=413)
                return await response(scope, receive, send)
            body.extend(incoming)
            if not event.get('more_body'):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)
