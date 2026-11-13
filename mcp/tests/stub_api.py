"""A simulated `/v1` server for the tests of kairos-mcp: a real HTTP server on a loopback port that records every request.

`StubApi` is used in process (`with StubApi() as stub: ...`); `python stub_api.py --port 8790` runs it alone (the container smoke test,
T-39, starts it as the upstream of the real kairos-mcp image). Routes are `(method, path)` pairs mapped to a `(status, body)` pair, to a
`Reply` (status, body, delay, extra headers) or to a callable that receives the recorded request and returns one of those. A path that has
no route answers 404 with the server's own error envelope, so a test that forgot a route fails loudly instead of passing by accident.
"""
from dataclasses import dataclass, field
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit


@dataclass
class Reply:
    status: int = 200
    body: object = None
    delay: float = 0.0
    headers: dict = field(default_factory=dict)
    raw: bytes | None = None  # sent as the body instead of the JSON of `body` (an HTML gateway page, truncated JSON)


@dataclass
class Request:
    method: str
    path: str  # as it came on the wire, query included
    route: str  # the path without the query string
    query: dict  # name -> list of values
    headers: dict  # lower-cased names
    body: object  # parsed JSON, or None


def as_reply(value):
    if isinstance(value, Reply):
        return value
    status, body = value
    return Reply(status, body)


class StubApi:
    def __init__(self, routes=None, port=0, host='127.0.0.1'):
        self.routes = dict(routes or {})
        self.requests = []
        self.connections = 0
        self.lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'  # keep-alive: the client under test must reuse one connection

            def setup(self):
                super().setup()
                with stub.lock:
                    stub.connections += 1

            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get('content-length') or 0)
                raw = self.rfile.read(length) if length else b''
                parts = urlsplit(self.path)
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                request = Request(self.command, self.path, parts.path, parse_qs(parts.query), {k.lower(): v for k, v in self.headers.items()}, body)
                with stub.lock:
                    stub.requests.append(request)
                handler = stub.routes.get((self.command, parts.path))
                if handler is None:
                    reply = Reply(404, {'error': {'code': 'not_found', 'message': 'Resource not found'}})
                else:
                    reply = as_reply(handler(request) if callable(handler) else handler)
                if reply.delay:
                    time.sleep(reply.delay)
                payload = reply.raw if reply.raw is not None else json.dumps(reply.body).encode('utf-8') if reply.body is not None else b''
                self.send_response(reply.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except OSError:
                    pass

            do_GET = do_POST = do_PUT = do_DELETE = handle_any

        class Quiet(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass  # a client that closes its connection while the stub waits is not a failure of the test

        self.server = Quiet((host, port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True)

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.server.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def calls(self, method=None, route=None):
        return [r for r in self.requests if (method is None or r.method == method) and (route is None or r.route == route)]


def standalone(port, host='0.0.0.0'):
    """The upstream of the container smoke test: the project list and one echoing route."""
    stub = StubApi({
        ('GET', '/v1/projects'): (200, {'projects': [{'project_id': 'smoke', 'name': 'Smoke project'}]}),
        ('GET', '/health/live'): (200, {'status': 'live'}),
    }, port=port, host=host)
    print('stub /v1 listening on %d' % port, flush=True)
    stub.server.serve_forever()


if __name__ == '__main__':
    standalone(int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8790)
