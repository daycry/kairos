"""Export contracts from native app/tool definitions without contacting services."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

P = '/v1/projects/{project_id}'
C = P + '/corpora'
# Where each of the 34 MCP tools lives in the REST API (C-02, CA-04): the `x-kairos-endpoint` key added to every tool of the exported
# contract, so that a client of `/v1` (kairos-mcp) needs no knowledge of the server code. `'local'` is a tool answered without the server.
# The tool arguments map onto the path parameters by meaning (`project`, `projectId` and `project_id` are the project), onto the body
# or the query by name; a tool that is a variant of its endpoint says so in the entry (`reprime_corpus` is `prime` with `fresh`).
ENDPOINTS = {
    'projects': ('GET', '/v1/projects'),
    'remember': ('POST', '/v1/events'),
    'capture_policy': ('GET', P + '/capture-policy'),
    # With `project_id` the reconciliation is one call; without it the receipt (`GET /v1/events/{event_id}`) and each of its jobs.
    'event_status': ('GET', P + '/events/{event_id}/status',
                     {'without_project_id': {'method': 'GET', 'path': '/v1/events/{event_id}',
                                             'jobs': {'method': 'GET', 'path': '/v1/jobs/{job_id}'}}}),
    'publish_document': ('POST', P + '/documents'),
    'document_status': ('GET', P + '/documents/{document_id}'),
    'document_manifest': ('GET', P + '/manifest'),
    'revoke_document': ('DELETE', P + '/documents/{document_id}'),
    'search': ('POST', '/v1/search'),
    'details': ('POST', '/v1/details'),
    'context': ('POST', '/v1/context'),
    'timeline': ('POST', '/v1/timeline'),
    'work_state_write': ('POST', P + '/work-state'),
    'work_state_read': ('GET', P + '/work-state'),
    'build_corpus': ('POST', C),
    'list_corpora': ('GET', C),
    'rebuild_corpus': ('POST', C + '/{name}/rebuild'),
    'prime_corpus': ('POST', C + '/{name}/prime'),
    'reprime_corpus': ('POST', C + '/{name}/prime', {'body': {'fresh': True}}),
    'query_corpus': ('POST', C + '/{name}/query'),
    'get_observations': ('POST', P + '/observations/get'),
    'observation_search': ('GET', P + '/observations/search'),
    'observation_context': ('GET', P + '/observations/context'),
    'observation_generation_status': ('GET', '/v1/jobs/{job_id}'),
    'important_workflow': 'local',
    'observation_add': ('POST', '/v1/observations'),
    'observation_record_event': ('POST', '/v1/observations/events'),
    'get_tool_uses': ('GET', '/v1/tool-uses'),
    'team_work_write': ('POST', P + '/team-work'),
    'team_work_read': ('GET', P + '/team-work'),
    'team_search': ('GET', P + '/team-search'),
    'team_brief': ('GET', P + '/team-brief'),
    'corpus_answer': ('POST', C + '/{name}/answers'),
    'corpus_answer_status': ('GET', C + '/{name}/answers/{request_id}'),
}


def endpoint(name):
    value = ENDPOINTS[name]
    if value == 'local':
        return value
    return {'method': value[0], 'path': value[1], **(value[2] if len(value) > 2 else {})}


def contracts():
    from memory_platform.app import create_app
    from memory_platform.config import Settings
    app = create_app(Settings('unused'))
    from memory_platform.models import SearchResult
    tools = asyncio.run(app.state.mcp.list_tools())
    if sorted(tool.name for tool in tools) != sorted(ENDPOINTS):
        raise SystemExit('ENDPOINTS and the MCP tools differ: ' + ', '.join(sorted(set(tool.name for tool in tools) ^ set(ENDPOINTS))))
    # Result shape of the search (the hits, with their optional fields such as `matched_chunk`): additive, new keys only. Tool and
    # route definitions are untouched; the OpenAPI schemas are added to `components.schemas` without replacing an existing one.
    result = SearchResult.model_json_schema(ref_template='#/components/schemas/{model}')
    openapi = app.openapi()
    schemas = openapi.setdefault('components', {}).setdefault('schemas', {})
    for name, schema in {**result.pop('$defs', {}), 'SearchResult': result}.items():
        schemas.setdefault(name, schema)
    return {'memory-platform.openapi.json': openapi,
            'kairos-mcp.json': {'name': 'Kairos', 'transport': 'streamable-http',
                                'path': '/mcp/', 'tools': [{**tool.model_dump(mode='json', exclude_none=True), 'x-kairos-endpoint': endpoint(tool.name)} for tool in tools],
                                'result_schemas': {'search': SearchResult.model_json_schema()}}}


def main():
    destination = ROOT / 'docs/contracts'
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in contracts().items():
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('Native HTTP and MCP contracts exported without connecting to services.')


if __name__ == '__main__':
    main()
