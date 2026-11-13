"""ASGI application of kairos-mcp: the liveness probe now, the MCP endpoint `/mcp/` as the tools are added."""
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

PORT = 8791


async def live(request):
    return JSONResponse({'status': 'live'})


def create_app(api_url=None, timeout=None):
    """`api_url` and `timeout` default to `KAIROS_API_URL` and `KAIROS_API_TIMEOUT`; liveness never calls the API."""
    app = Starlette(routes=[Route('/health/live', live, methods=['GET'])])
    app.state.api_url = api_url or os.environ.get('KAIROS_API_URL', '')
    return app


def main():
    import uvicorn
    uvicorn.run(create_app(), host='0.0.0.0', port=PORT, log_config=None, access_log=False)


if __name__ == '__main__':
    main()
