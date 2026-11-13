"""Export contracts from native app/tool definitions without contacting services."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

P = '/v1/projects/{project_id}'
C = P + '/corpora'


def path(name):
    return {'in': 'path', 'name': name}


def query(name, **extra):
    return {'in': 'query', 'name': name, **extra}


def body(name=None, **extra):
    """A body field by name; without a name the argument IS the whole JSON body (`remember`'s `event`, `publish_document`'s `document`)."""
    return {'in': 'body', **({'name': name} if name else {}), **extra}


def same(where, *names, **extra):
    """Arguments that keep their name in the request (`limit` is `limit` in the query or in the body)."""
    return {name: {'in': where, 'name': name, **extra} for name in names}


PROJECT = {'project': path('project_id')}
CORPUS = {**PROJECT, 'name': path('name')}
CSV = {'transform': 'csv-list'}
# Where each of the 34 MCP tools lives in the REST API (C-02, CA-04): the `x-kairos-endpoint` key added to every tool of the exported
# contract, so that a client of `/v1` (kairos-mcp) translates a call mechanically and needs no knowledge of the server code. `'local'` is a
# tool answered without the server. NOTHING IS ASSIGNED BY NAME: `args` lists EVERY argument of the tool's input schema and says where it goes
# (`in`: `path`, `query` or `body`) and under which REST name (`name`; `project`, `projectId` and `project_id` are the `{project_id}` of the
# path, `includeClosed` is `include_closed`, `jobId` is `{job_id}`). An `in: body` argument without a `name` is the whole request body. `fixed`
# are values the tool always sends (`reprime_corpus` is `prime` with `fresh: true`). `transform` is a value conversion (`csv-list`: a string
# is split on commas, trimmed, empties dropped and duplicates removed; a list passes as it is). The rules of the translation itself (omitted
# arguments, booleans, a POST always carrying a JSON object, the URL encoding of path values) are in `TRANSLATION`, put once in the contract.
ENDPOINTS = {
    'projects': ('GET', '/v1/projects', {}),
    'remember': ('POST', '/v1/events', {'event': body()}),
    'capture_policy': ('GET', P + '/capture-policy', {'project_id': path('project_id')}),
    # With `project_id` the reconciliation is one call; without it the tool reads the receipt and each of its jobs and composes the answer
    # (`mcp.py`): `without_project_id` says how, with `complete` as the rule the tool applies (a superseded receipt is never complete).
    'event_status': ('GET', P + '/events/{event_id}/status', {'event_id': path('event_id'), 'project_id': path('project_id')},
                     {'without_project_id': {
                         'receipt': {'method': 'GET', 'path': '/v1/events/{event_id}', 'args': {'event_id': path('event_id')}},
                         'jobs': {'for_each': 'receipt.jobs', 'method': 'GET', 'path': '/v1/jobs/{job_id}', 'args': {'job_id': path('job_id')}},
                         'result': {'receipt': {'from': 'receipt'}, 'jobs': {'from': 'jobs'},
                                    'complete': {'all_of': [{'path': 'receipt.status', 'is_not': 'superseded'},
                                                            {'each': 'jobs', 'path': 'state', 'is': 'succeeded'}]}}}}),
    'publish_document': ('POST', P + '/documents', {'project_id': path('project_id'), 'document': body()}),
    'document_status': ('GET', P + '/documents/{document_id}', {'project_id': path('project_id'), 'document_id': path('document_id')}),
    'document_manifest': ('GET', P + '/manifest', {'project_id': path('project_id'), **same('query', 'limit', 'cursor')}),
    'revoke_document': ('DELETE', P + '/documents/{document_id}', {'project_id': path('project_id'), 'document_id': path('document_id'), 'version': query('version')}),
    'search': ('POST', '/v1/search', same('body', 'project_ids', 'q', 'layers', 'limit', 'semantic', 'semantic_budget_ms')),
    'details': ('POST', '/v1/details', same('body', 'refs', 'max_chars')),
    'context': ('POST', '/v1/context', same('body', 'project_ids', 'q', 'layers', 'limit', 'max_chars', 'semantic', 'match_mode', 'exclude_categories', 'semantic_budget_ms')),
    'timeline': ('POST', '/v1/timeline', same('body', 'project_ids', 'anchor_ref', 'before', 'after', 'limit')),
    'work_state_write': ('POST', P + '/work-state', {**PROJECT, **same('body', 'list', 'fields', 'request_id', 'expected_version')}),
    'work_state_read': ('GET', P + '/work-state', {**PROJECT, 'list': query('list'), 'includeClosed': query('include_closed')}),
    'build_corpus': ('POST', C, {**PROJECT, **same('body', 'name', 'description', 'query', 'limit'), **same('body', 'types', 'concepts', 'files', **CSV),
                                 'dateStart': body('date_start'), 'dateEnd': body('date_end')}),
    'list_corpora': ('GET', C, PROJECT),
    # The endpoint requires `expected_version` (>= 1, a field the published schema already marks `required`, which cannot be relaxed
    # additively); the tool makes it optional and, without it, rebuilds whatever version the corpus has (it only takes the row lock). So a call
    # without it (absent or null) reads the corpus by name (`GET .../corpus?name=`, not the list: that one stops at 100) and sends that version:
    # the same guard the endpoint wants, with the version the tool would have compared against. An unknown name is the 404 of the tool: the
    # error of the read is the answer of the call (the read asks for `write` before `read`, as the rebuild does, so a key without write gets the tool's 403). A rebuild that lands between the read and the POST makes the POST answer 409; the tool has
    # no such conflict, so the client reads again and, only if the version changed, sends again (`retry`); an unchanged version means the
    # 409 is real (a rebuild that would remove more than half the corpus without `force`) and it is the answer. `untranslatable`: a value
    # the endpoint cannot receive, answered by the client without sending the request (`after_read`: after the read that checks access and existence).
    'rebuild_corpus': ('POST', C + '/{name}/rebuild', {**CORPUS, **same('body', 'force'), 'expected_version': body('expected_version', when_absent={
        'read': {'method': 'GET', 'path': P + '/corpus', 'args': {'project': path('project_id'), 'name': query('name')}},
        'take': 'version', 'on_read_error': 'answer',
        'retry': {'on_status': 409, 'reread': True, 'only_if_value_changed': True, 'max': 3}})},
        {'untranslatable': [{'argument': 'expected_version', 'value': 0, 'after_read': True,
                             'reason': 'the endpoint refuses a version below 1 with 422, the tool answers a conflict because no corpus has version 0; the '
                                       'read comes first so that a corpus the caller cannot see or does not have is the 403 or 404 the tool gives, not that conflict',
                             'answer': {'status': 409, 'error': {'code': 'conflict', 'message': 'Corpus version changed'}}}]}),
    'prime_corpus': ('POST', C + '/{name}/prime', CORPUS),
    'reprime_corpus': ('POST', C + '/{name}/prime', CORPUS, {'fixed': [{'in': 'body', 'name': 'fresh', 'value': True}]}),
    'query_corpus': ('POST', C + '/{name}/query', {**CORPUS, **same('body', 'question', 'limit')}),
    'get_observations': ('POST', P + '/observations/get', {'projectId': path('project_id'), 'ids': body('ids')}),
    'observation_search': ('GET', P + '/observations/search', {'projectId': path('project_id'), **same('query', 'query', 'limit')}),
    'observation_context': ('GET', P + '/observations/context', {'projectId': path('project_id'), **same('query', 'query', 'limit')}),
    'observation_generation_status': ('GET', '/v1/jobs/{job_id}', {'jobId': path('job_id')}),
    'important_workflow': 'local',
    'observation_add': ('POST', '/v1/observations', {'event': body()}),
    'observation_record_event': ('POST', '/v1/observations/events', {'event': body()}),
    'get_tool_uses': ('GET', '/v1/tool-uses', {'project': query('project_id'), **same('query', 'session_id', 'tool', 'limit', 'cursor')}),
    'team_work_write': ('POST', P + '/team-work', {**PROJECT, **same('body', 'list', 'fields', 'request_id', 'expected_version')}),
    'team_work_read': ('GET', P + '/team-work', {**PROJECT, **same('query', 'list', 'include_closed')}),
    'team_search': ('GET', P + '/team-search', {**PROJECT, **same('query', 'query', 'limit')}),
    'team_brief': ('GET', P + '/team-brief', {**PROJECT, **same('query', 'limit')}),
    'corpus_answer': ('POST', C + '/{name}/answers', {**CORPUS, **same('body', 'question', 'request_id', 'expected_session_id', 'expected_generation')}),
    'corpus_answer_status': ('GET', C + '/{name}/answers/{request_id}', {**CORPUS, 'request_id': path('request_id')}),
}
TRANSLATION = [
    'A tool call becomes one HTTP request to `method` + `path` (the first request; `event_status` without `project_id` follows `without_project_id`).',
    'Each tool argument that is present and not null is placed by its entry in `args`: `in: path` replaces `{name}` in the path with the value URL-encoded in full (a `/` becomes `%2F`), `in: query` adds a query parameter, `in: body` adds a JSON body field; an `in: body` entry without `name` makes the value the whole body.',
    'An absent or null argument is omitted: the server applies its default. A boolean query value is written `true` or `false`; a list query value repeats the parameter.',
    '`transform: csv-list` turns a string into a list (split on commas, trimmed, empties dropped, duplicates removed) and passes a list as it is.',
    '`when_absent` fills an argument that is absent or null (both count as omitted): `read` is one request (same rules, over the arguments of the call that it names in its `args`), `take` is the field of its JSON answer that becomes the argument. `on_read_error: answer` means a read that fails answers the call with that status and error. `retry` (`on_status`, `reread`, `only_if_value_changed`, `max`): if the request carrying a value obtained with `when_absent` answers that status, read again; if the value read differs from the one sent, send the request again with it (at most `max` more times), otherwise the answer is the real one.',
    '`untranslatable` lists argument values that the endpoint cannot receive: the client does not send the request and answers with `answer` (`status` and `error`). With `after_read: true` it first makes the `when_absent` read of the same call, so that the server checks access and existence in the order the tool does (a read that fails answers the call, as in `when_absent`), and answers with `answer` only when the read succeeds.',
    '`without_project_id` (`event_status` without `project_id`) is a composition. Step `receipt` is one request as any entry. Step `jobs` is repeated: `for_each` is a dotted path into the scope (`receipt` is the answer of the first step), each element is the value of the argument its `args` names (`job_id`), and the answers form the list `jobs` (a failed request answers the call). `result` builds the answer: each key is `{from: receipt|jobs}` (that value as it is) or `{all_of: [condition, ...]}`, a boolean true when every condition holds; a condition is `{path, is}` (the value at the dotted `path` of the scope equals `is`), `{path, is_not}` (it differs) or `{each, path, is}` (every item of the list `each` has, at `path`, the value `is`; an empty list holds).',
    '`fixed` entries are always added (`in: body`, `name`, `value`). A POST or PUT always carries a JSON object body, `{}` when no field is set.',
    'The response of the endpoint is the result of the tool; an error status carries `{"error": {"code", "message"}}`.',
]


def endpoint(name):
    value = ENDPOINTS[name]
    if value == 'local':
        return value
    return {'method': value[0], 'path': value[1], 'args': value[2], **(value[3] if len(value) > 3 else {})}


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
                                'path': '/mcp/', 'x-kairos-translation': TRANSLATION, 'tools': [{**tool.model_dump(mode='json', exclude_none=True), 'x-kairos-endpoint': endpoint(tool.name)} for tool in tools],
                                'result_schemas': {'search': SearchResult.model_json_schema()}}}


def main():
    destination = ROOT / 'docs/contracts'
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in contracts().items():
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('Native HTTP and MCP contracts exported without connecting to services.')


if __name__ == '__main__':
    main()
