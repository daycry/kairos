"""Export contracts from native app/tool definitions without contacting services."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def contracts():
    from memory_platform.app import create_app
    from memory_platform.config import Settings
    app = create_app(Settings('unused'))
    from memory_platform.models import SearchResult
    tools = asyncio.run(app.state.mcp.list_tools())
    # Result shape of the search (the hits, with their optional fields such as `matched_chunk`): additive, new keys only. Tool and
    # route definitions are untouched; the OpenAPI schemas are added to `components.schemas` without replacing an existing one.
    result = SearchResult.model_json_schema(ref_template='#/components/schemas/{model}')
    openapi = app.openapi()
    schemas = openapi.setdefault('components', {}).setdefault('schemas', {})
    for name, schema in {**result.pop('$defs', {}), 'SearchResult': result}.items():
        schemas.setdefault(name, schema)
    return {'memory-platform.openapi.json': openapi,
            'kairos-mcp.json': {'name': 'Kairos', 'transport': 'streamable-http',
                                'path': '/mcp/', 'tools': [tool.model_dump(mode='json', exclude_none=True) for tool in tools],
                                'result_schemas': {'search': SearchResult.model_json_schema()}}}


def main():
    destination = ROOT / 'docs/contracts'
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in contracts().items():
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('Native HTTP and MCP contracts exported without connecting to services.')


if __name__ == '__main__':
    main()
