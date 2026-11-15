"""ASGI application of kairos-mcp: `/health/live` and the MCP endpoint `/mcp/` (streamable HTTP, stateless, JSON responses)."""
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from . import contract as contract_module
from .auth import RequireBearer
from .client import ApiClient
from .errors import ToolError
from .config import DEFAULT_MAX_BODY_BYTES, DEFAULT_TIMEOUT, DEFAULT_VALIDATION_THREADS, from_env, parse_api_url
from .limits import BodyLimit
from .logs import configure_logging
from .tools import build_server

PORT = 8791
SERVICE_HOST = 'memory-mcp'  # the name of this service on the Compose network: the proxy and the stack reach it by that name


async def live(request):
    return JSONResponse({'status': 'live'})


def security(allowed_origins):
    """DNS-rebinding protection as the internal MCP has it: loopback, the hostnames of the allowed origins and this service's own name."""
    hosts = ['localhost:*', '127.0.0.1:*', '[::1]:*', SERVICE_HOST, SERVICE_HOST + ':*']
    for origin in allowed_origins:
        hostname = urlsplit(origin).hostname
        if hostname:
            hosts.extend([hostname, hostname + ':*'])
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=list(dict.fromkeys(hosts)), allowed_origins=list(allowed_origins))


def create_app(api_url=None, timeout=None, allowed_origins=(), transport=None, contract=None, max_body_bytes=DEFAULT_MAX_BODY_BYTES, validation_threads=DEFAULT_VALIDATION_THREADS):
    """`transport` replaces the network (an ASGI transport onto the server in the in-process chain tests); the credential is never configured here."""
    from .translate import Executor
    api_url = parse_api_url(api_url)
    client = ApiClient(api_url, DEFAULT_TIMEOUT if timeout is None else timeout, transport=transport)
    contract = contract or contract_module.load()
    executor = Executor(contract, client)
    server = build_server(contract, executor.execute, validation_threads)
    manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True, security_settings=security(allowed_origins))

    async def mcp_endpoint(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    async def verify(authorization):
        """The credential is refused only when `/v1` says so: an API that cannot answer is a failure of the calls, not a reason to refuse the request."""
        try:
            status, _ = await client.send('GET', '/v1/auth/me', authorization)
        except ToolError:
            return True
        return status != 401

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield
        await client.aclose()

    app = Starlette(routes=[Route('/health/live', live, methods=['GET']), Mount('/mcp', app=RequireBearer(mcp_endpoint, verify))], lifespan=lifespan)
    app.add_middleware(BodyLimit, maximum=max_body_bytes)
    app.state.api_url, app.state.client = api_url, client
    return app


def main():
    import uvicorn
    configure_logging()
    config = from_env()
    uvicorn.run(create_app(config.api_url, config.timeout, config.allowed_origins, max_body_bytes=config.max_body_bytes, validation_threads=config.validation_threads), host='0.0.0.0', port=PORT, log_config=None, access_log=False)


if __name__ == '__main__':
    main()
