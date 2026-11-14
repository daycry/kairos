"""The chain kairos-mcp -> server, in process (T-47, CA-11): kairos-mcp is mounted in front of the server application over an ASGI transport.

No socket is opened: kairos-mcp's HTTP client is an `httpx.ASGITransport` whose application is the server's, so every tool call of a test becomes the
real `/v1` request of the contract, authenticated, authorized and stored by the real server over the isolated PostgreSQL of the test target. The harness
is on this side of the repository on purpose: `mcp/` must not import the server (CA-08), the tests of the server may import `mcp/` (they run in an image
that has it at `/app/mcp`).

`ChainClient` looks like the test client of the server application, but a request to `/mcp/` is served by kairos-mcp and everything else goes straight to
the server. `ChainMode` is the mixin of the tests that run twice: `self.open(app)` gives a plain client of the internal MCP, or a `ChainClient` when the
class says `mode = 'chain'` (`chain_variant` builds that class from the original; the tests are not copied).
"""
import asyncio
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

MCP_ROOT = Path(__file__).resolve().parents[3] / 'mcp'
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

ENVELOPE = ('untrusted', 'warning')  # the fields kairos-mcp and the internal MCP add to a reading tool (S-05)
BASE = 'http://localhost:8790'


def strip_envelope(value):
    """The answer of a tool without the two fields of the untrusted-data envelope, at the top level only."""
    return {key: item for key, item in value.items() if key not in ENVELOPE} if isinstance(value, dict) else value


class RecordingTransport(httpx.AsyncBaseTransport):
    """The ASGI transport onto the server, with a record of every request kairos-mcp sends and an optional hook that runs after the server has answered it
    (a concurrent change landing between two requests of one tool call). The hook is called with the request and the response."""

    def __init__(self, app, after=None):
        self.inner = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        self.requests, self.after = [], after

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        self.requests.append((request.method, request.url.raw_path.decode('ascii'), response.status_code))
        if self.after:
            await asyncio.to_thread(self.after, request, response)
        return response

    async def aclose(self):
        await self.inner.aclose()


def chain_app(server_app, timeout=30.0, transport=None, **options):
    """kairos-mcp over `server_app`: its `/v1` calls never leave the process. Unhandled errors of the server become its 503, as over a network."""
    from kairos_mcp.app import create_app
    # An installation gives both the same limit (`MEMORY_MAX_BODY_BYTES` and `KAIROS_MAX_BODY_BYTES`): the chain does too, so an oversized body is the 413 of either.
    options.setdefault('max_body_bytes', getattr(getattr(server_app.state, 'settings', None), 'max_body_bytes', 262144))
    return create_app(api_url='http://server.invalid', timeout=timeout, transport=transport or httpx.ASGITransport(app=server_app, raise_app_exceptions=False), **options)


class ChainClient:
    """`/mcp/` through kairos-mcp, everything else (and `server_mcp`, the server's own MCP) on the server application."""

    def __init__(self, server_app, base_url=BASE, timeout=30.0, **options):
        self.api = self.server_mcp = TestClient(server_app, base_url=base_url)
        self.chain = TestClient(chain_app(server_app, timeout, **options), base_url=base_url)
        self.app = server_app

    def __enter__(self):
        self.api.__enter__()
        self.chain.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            self.chain.__exit__(*exc)
        finally:
            self.api.__exit__(*exc)

    def request(self, method, url, **kwargs):
        return (self.chain if url.split('?')[0].rstrip('/') == '/mcp' else self.api).request(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def put(self, url, **kwargs):
        return self.request('PUT', url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request('DELETE', url, **kwargs)

    def __getattr__(self, name):
        return getattr(self.api, name)


def open_client(app, mode='internal', base_url=BASE, **options):
    return ChainClient(app, base_url=base_url, **options) if mode == 'chain' else TestClient(app, base_url=base_url)


class ChainMode:
    """Mixin: `self.open(app)` is a client of the internal MCP, or of the chain when the class sets `mode = 'chain'`."""
    mode = 'internal'

    def open(self, app, base_url=BASE, **options):
        return open_client(app, self.mode, base_url, **options)


def chain_variant(cls):
    """The same tests, run through kairos-mcp: a subclass of `cls` whose `mode` is `chain` (no test is copied, none is skipped)."""
    return type(cls.__name__.replace('Tests', '') + 'ChainTests', (cls,), {'mode': 'chain', '__module__': cls.__module__,
                                                                             '__doc__': 'The tests of ' + cls.__name__ + ' through kairos-mcp.'})
