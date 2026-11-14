"""CA-06: each of the 34 MCP tools and its `/v1` endpoint return the same content for the same credential and arguments.

A scenario is seeded once in an isolated PostgreSQL (observations, an event with a job, documents, a primed corpus, team and
private work, a tool-use summary, a saved answer). For every tool the test calls the internal MCP endpoint and then the request
that the `x-kairos-endpoint` of the exported contract says that call becomes, with one writer key, and compares what comes back.
The request is NOT written by hand: `translate` is a small generic translator that builds it from the MCP arguments of the case and
from the contract alone (where each argument goes, under which name, the fixed values, the composition of `event_status` without a
project, the read of a missing `expected_version` and its retry). So the contract is only as good as what this test can do with it, which is what a client of `/v1` (kairos-mcp) will have.

The comparison is the content: the MCP byte budget (`render`) and the additive fields of the untrusted-data envelope (S-05, C-03: `untrusted` and `warning`, stripped at the
top level of a reading tool) are the only differences allowed. Operations that write are idempotent by design (a retry returns the same
receipt), so the second call is the endpoint's, over the state the tool left; `reprime_corpus`, which opens a new session each time,
ignores the session fields.

The `CASES` list is checked against the tools the server lists and against the exported contract: a tool without a case, a case without
a tool or a tool whose contract entry does not name every argument fails the run (the removal of an endpoint turns its case red). Each
rule of the contract is exercised by an argument that needs it, and a contract that assigned those arguments by name fails (see
the `test_*` mutation tests of the class).
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest
from urllib.parse import quote
import uuid

from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.extended_store import ExtendedStore
from memory_platform.store import digest
from memory_platform.tests.llm_spy import ChatSpy
from memory_platform.tests.test_store import create_core, event

ORIGIN = 'http://localhost:8790'
EXPORTER = Path(__file__).parents[2] / 'scripts' / 'export-contracts.py'


def untrusted_writes():
    """The tools annotated as a write whose endpoint the contract marks `untrusted` (retrieved content: they carry the S-05 envelope)."""
    return {name for name, rule in declared_endpoints().items() if rule != 'local' and rule.get('untrusted')}


def declared_endpoints():
    """The `x-kairos-endpoint` of every tool of the exported contract (no file read: what the exporter would write)."""
    spec = importlib.util.spec_from_file_location('kairos_export_contracts_parity', EXPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {tool['name']: tool['x-kairos-endpoint'] for tool in module.contracts()['kairos-mcp.json']['tools']}


def drop(value, keys):
    if isinstance(value, dict):
        return {key: drop(item, keys) for key, item in value.items() if key not in keys}
    if isinstance(value, list):
        return [drop(item, keys) for item in value]
    return value


def without_envelope(value):
    """The answer without the two fields of the untrusted-data envelope (S-05), at the top level only."""
    return {key: item for key, item in value.items() if key not in ('untrusted', 'warning')} if isinstance(value, dict) else value


def csv_list(value):
    """`transform: csv-list`: a string is split on commas, trimmed, empties dropped and duplicates removed; a list passes as it is."""
    if isinstance(value, list):
        return value
    return list(dict.fromkeys(part.strip() for part in value.split(',') if part.strip()))


def translate(rule, arguments):
    """One REST request, `(method, path, keywords)`, from an `x-kairos-endpoint` (or one of its `without_project_id` steps) and MCP arguments.

    It reads only the contract: an argument that has no rule is an error (a tool argument the contract forgot), and so is a `{placeholder}`
    left in the path.
    """
    unknown = set(arguments) - set(rule['args'])
    assert not unknown, ('arguments without a rule in the contract', sorted(unknown))
    path, params, fields, whole = rule['path'], {}, {}, None
    for argument, value in arguments.items():
        if value is None:
            continue  # an absent or null argument is omitted: the server applies its default
        where = rule['args'][argument]
        if where.get('transform') == 'csv-list':
            value = csv_list(value)
        if where['in'] == 'path':
            path = path.replace('{' + where['name'] + '}', quote(str(value), safe=''))
        elif where['in'] == 'query':
            params[where['name']] = ('true' if value else 'false') if isinstance(value, bool) else value
        elif 'name' in where:
            fields[where['name']] = value
        else:
            whole = value
    for fixed in rule.get('fixed', []):
        fields[fixed['name']] = fixed['value']
    assert not re.search(r'\{[a-z_]+\}', path), ('unresolved placeholder', path)
    kwargs = {'params': params} if params else {}
    if rule['method'] in ('POST', 'PUT'):
        kwargs['json'] = fields if whole is None else whole  # a POST always carries a JSON object body, `{}` when no field is set
    return rule['method'], path, kwargs


def lookup(value, dotted):
    for key in dotted.split('.'):
        value = value[key]
    return value


def holds(condition, scope):
    """The `complete` rule of `without_project_id`: `path` is / is not a value, or `each` item of a list has `path` equal to `is`."""
    if 'each' in condition:
        return all(lookup(item, condition['path']) == condition['is'] for item in scope[condition['each']])
    value = lookup(scope, condition['path'])
    return value == condition['is'] if 'is' in condition else value != condition['is_not']


def read_missing(rule, arguments, rest):
    """`when_absent`: the values of the arguments the call left out (absent or null), each one read as the contract says. `(values, None)`, or
    `(None, (status, body))` when a read fails, which `on_read_error: answer` makes the answer of the call."""
    values = {}
    for argument, where in rule['args'].items():
        if 'when_absent' in where and arguments.get(argument) is None:
            how = where['when_absent']
            method, path, kwargs = translate(how['read'], {key: value for key, value in arguments.items() if key in how['read']['args']})
            status, read = rest(method, path, **kwargs)
            instead = how.get('send_instead_on_status')
            if instead and status in instead['statuses']:
                values[argument] = instead['value']  # the request goes with a version no corpus has and the server answers in its own order of checks
                continue
            if status >= 400:
                assert how['on_read_error'] == 'answer', how
                return None, (status, read)
            values[argument] = read[how['take']]
    return values, None


def perform(rule, arguments, rest, between=None):
    """What a client of `/v1` does with one call, from the contract alone: an `untranslatable` value goes as `send_instead`; `when_absent`
    values are read and sent (a read that fails with `send_instead_on_status` gives the value that status says); a `retry` status with a value that changed since
    the read sends the request again. `between` is called after each read and before the request (a test hook: the concurrent change). Returns `(status, body)`."""
    for refused in rule.get('untranslatable', []):
        value = arguments.get(refused['argument'])
        if value is not None and value == refused['value'] and type(value) is type(refused['value']):
            arguments = {**arguments, refused['argument']: refused['send_instead']}
            break
    retry = next((where['when_absent'].get('retry') for where in rule['args'].values() if 'when_absent' in where), None)
    sent = last = None
    for _ in range(1 + (retry['max'] if retry else 0)):
        values, failed = read_missing(rule, arguments, rest)
        if failed:
            return failed
        if last is not None and values == sent:
            return last  # nothing changed since the last request: the conflict is real
        sent = values
        if between:
            between()
        method, path, kwargs = translate(rule, {**arguments, **values})
        last = rest(method, path, **kwargs)
        if not values or retry is None or last[0] != retry['on_status']:
            return last
    return last


class Scenario:
    """The seeded project and the credential every case uses."""

    def __init__(self):
        self.store, self.admin, self.pid = create_core()
        self.store.extraction_enabled = True  # the event below then carries an `extract` job to read back (explicit opt-in)
        self.spy = ChatSpy().start()
        auth = Auth(self.store, [ORIGIN])
        settings = Settings(self.store.dsn, allowed_origins=[ORIGIN], ollama_url=self.spy.url)
        self.client = TestClient(create_app(settings, store=self.store, auth=auth), base_url=ORIGIN)
        self.client.__enter__()
        key = self.store.create_key(self.admin, {'name': 'parity writer', 'project_ids': [self.pid], 'scopes': ['read', 'write', 'publish', 'validate']})
        self.headers = {'Authorization': 'Bearer ' + key['token']}
        self.prefix = '/v1/projects/' + self.pid
        # observations (two, lexically distinct) and one event whose job can be read back
        self.obs1 = self.ingest(item_id=str(uuid.uuid4()), occurred_at='2026-11-02T10:00:00Z', generate=False)
        self.obs2 = self.ingest(item_id=str(uuid.uuid4()), occurred_at='2026-11-03T10:00:00Z', generate=False,
                                payload={'title': 'Index choice', 'content': 'Prefer a partial index for archived rows', 'category': 'decision', 'source': {'uri': 'fixture://parity'}})
        self.job_event = self.ingest(item_id=str(uuid.uuid4()), occurred_at='2026-11-04T10:00:00Z', generate=True)
        self.job_id = self.rest('POST', '/v1/events', json=self.job_event)[1]['jobs'][0]
        # a receipt that is `superseded` (the store of this version never writes that status: the receipt is set as the tool reads it)
        self.superseded_event = self.ingest(item_id=str(uuid.uuid4()), occurred_at='2026-11-05T10:00:00Z', generate=False)
        with self.store.transaction() as c:
            c.execute("UPDATE memory.events SET receipt=jsonb_set(receipt,'{status}','\"superseded\"') WHERE id=%s", (self.superseded_event['event_id'],))
        # a PostToolUse summary, so that `get_tool_uses` has content to compare
        payload = {'title': 'Technical tool summary', 'content': json.dumps({'tool': 'Read', 'status': 'success', 'detail': 'private body omitted'}), 'category': 'agent-activity'}
        self.tool_use = event(self.pid, generate=False, payload=payload)
        self.tool_use['capture'] = {'mode': 'summary', 'hook_event': 'PostToolUse', 'fingerprint': digest(
            {'project': self.pid, 'runtime': self.tool_use['agent_id'], 'session': self.tool_use['session_id'], 'event': 'PostToolUse', 'payload': payload})}
        ExtendedStore(self.store).observation_add(self.admin, self.tool_use)
        self.ref = self.search_ref()
        # documents: one to read and one to withdraw
        self.document = self.document_body('Canonical approved fixture')
        self.revocable = self.document_body('A document that will be withdrawn')
        for value in (self.document, self.revocable):
            assert self.rest('POST', self.prefix + '/documents', json=value)[0] == 202
        # primed corpora, private work (one open task and one closed) and shared work
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'c1', 'query': 'fencing'})[0] == 200
        assert self.rest('POST', self.prefix + '/corpora/c1/prime', json={})[0] == 200
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'c-rebuild', 'query': 'index'})[0] == 200  # a filter the other cases never change
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'team/search', 'query': 'fencing'})[0] == 200  # a name with a `/`, sent as `%2F`
        assert self.rest('POST', self.prefix + '/corpora/team%2Fsearch/prime', json={})[0] == 200
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'zz-late', 'query': 'index'})[0] == 200  # sorts after any filler of the 100-corpus test
        for name in ('c-reprime-tool', 'c-reprime-rest'):
            assert self.rest('POST', self.prefix + '/corpora', json={'name': name, 'query': 'fencing'})[0] == 200
            assert self.rest('POST', self.prefix + '/corpora/' + name + '/prime', json={})[0] == 200
        assert self.rest('POST', self.prefix + '/team-work', json={'list': 'release', 'fields': {'task': 'Rotate the fencing token', 'status': 'todo'}, 'request_id': 'seed-team'})[0] == 200
        assert self.rest('POST', self.prefix + '/work-state', json={'list': 'plan', 'fields': {'task': 'Review fencing', 'status': 'doing'}, 'request_id': 'seed-plan'})[0] == 200
        assert self.rest('POST', self.prefix + '/work-state', json={'list': 'plan', 'fields': {'task': 'Ship fencing', 'status': 'done'}, 'request_id': 'seed-closed'})[0] == 200
        self.seed_saved_answer()

    def seed_saved_answer(self):
        """An answer already stored for the primed corpus `c1`, as a completed provider call would leave it (generation is off here: no model is called)."""
        from memory_platform.corpus_answers import migrate_corpus_answers
        with self.store.transaction() as c:
            migrate_corpus_answers(c)
            corpus = c.execute("SELECT * FROM memory.agent_corpora WHERE project_id=%s AND name='c1'", (self.pid,)).fetchone()
            c.execute("""INSERT INTO memory.corpus_answers(corpus_id,project_id,actor_id,request_id,request_hash,session_id,generation,generation_hash,state,question,model,
                         reservation,input_tokens,output_tokens,result,expires_at,finished_at)
                         VALUES(%s,%s,%s,'saved-answer','h',%s,%s,%s,'completed','What is fencing?','fixture-model',9216,10,5,%s::jsonb,clock_timestamp()+interval '1 hour',clock_timestamp())""",
                      (corpus['id'], self.pid, corpus['actor_id'], corpus['session_id'], corpus['version'], corpus['canonical_hash'], json.dumps({'answer': 'Fencing guards a token.', 'citations': []})))

    def close(self):
        self.client.__exit__(None, None, None)
        self.spy.stop()

    def ingest(self, **changes):
        value = event(self.pid, **{'generate': False, 'payload': {'title': 'Fencing note', 'content': 'Use fencing before projection', 'category': 'decision', 'source': {'uri': 'fixture://parity'}}, **changes})
        self.store.ingest_event(self.admin, value)
        return value

    def document_body(self, content):
        return {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Synthetic document', 'content': content,
                'source': {'uri': 'fixture://document/' + uuid.uuid4().hex, 'sha256': hashlib.sha256(content.encode()).hexdigest()},
                'validation': {'status': 'validated', 'evidence': ['synthetic test evidence'], 'validated_by': 'test'}}

    def search_ref(self):
        found = self.rest('POST', '/v1/search', json={'project_ids': [self.pid], 'q': 'fencing', 'layers': ['episodic'], 'semantic': False})[1]
        return found['items'][0]['ref']

    def rest(self, method, path, **kwargs):
        response = self.client.request(method, path, headers=self.headers, **kwargs)
        body = response.json() if response.content else None
        return response.status_code, body

    def acting(self, token):
        """Run a block with another credential (a key of this actor with other scopes, or a key of another actor); `rest` and `tool` both use it."""
        import contextlib

        @contextlib.contextmanager
        def swap():
            saved, self.headers = self.headers, {'Authorization': 'Bearer ' + token}
            try:
                yield
            finally:
                self.headers = saved
        return swap()

    def view(self, status, body):
        return ('error', body['error']['message']) if status >= 400 else ('ok', body)

    def endpoint(self, rule, arguments, between=None):
        """What the contract says a call of the tool becomes, performed: one request, or the composition of `event_status` without a project."""
        if 'without_project_id' in rule and arguments.get('project_id') is None:
            return self.composed(rule['without_project_id'], arguments)
        return self.view(*perform(rule, arguments, self.rest, between))

    def composed(self, rule, arguments):
        method, path, kwargs = translate(rule['receipt'], arguments)
        status, receipt = self.rest(method, path, **kwargs)
        if status >= 400:
            return self.view(status, receipt)
        scope = {'receipt': receipt, 'jobs': []}
        for job_id in lookup(scope, rule['jobs']['for_each']):
            method, path, kwargs = translate(rule['jobs'], {'job_id': job_id})
            status, job = self.rest(method, path, **kwargs)
            if status >= 400:
                return self.view(status, job)
            scope['jobs'].append(job)
        result = {}
        for key, how in rule['result'].items():
            result[key] = scope[how['from']] if 'from' in how else all(holds(condition, scope) for condition in how['all_of'])
        return 'ok', result

    def listing(self):
        if getattr(self, '_listed', None) is None:
            self._listed = self.tool_listing()
        return self._listed

    def tool_listing(self):
        response = self.client.post('/mcp/', headers={**self.headers, 'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        return {tool['name']: tool for tool in response.json()['result']['tools']}

    def tool(self, name, arguments):
        response = self.client.post('/mcp/', headers={**self.headers, 'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
        result = response.json()['result']
        if result.get('isError'):
            return 'error', re.sub(r'^Error executing tool \w+: ', '', result['content'][0]['text'])  # FastMCP's framing, not the service message
        structured = result.get('structuredContent')
        if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
            try:
                return 'ok', json.loads(structured['result'])  # the tools declared `-> str` wrap their JSON text
            except ValueError:
                return 'ok', structured['result']  # `important_workflow` is plain text
        return 'ok', structured if isinstance(structured, dict) else json.loads(result['content'][0]['text'])


def cases(s):
    """The list of `(label, tool, MCP arguments, options)`. Built after the scenario so the ids are real; each tool has at least one case.

    Options: `ignore` (field names that are identity, not content), `rest_arguments` (the arguments of the endpoint call when it must act
    on a twin of what the tool acted on), `error` (both sides refuse), `contains`/`absent` (text that must/must not be in the content),
    `items` (the content has a non-empty list under that key).
    """
    P = s.pid
    remember = event(P, generate=False, item_id=str(uuid.uuid4()))
    added = event(P, generate=False, item_id=str(uuid.uuid4()))
    revision = event(P, generate=False, item_id=added['item_id'], version=2, payload={'title': 'Fencing note', 'content': 'Revised: also take a lease', 'category': 'decision', 'source': {'uri': 'fixture://parity'}})
    ids = [s.obs1['item_id'], s.obs2['item_id']]
    work = {'list': 'release', 'fields': {'task': 'Rotate the fencing token', 'status': 'todo'}, 'request_id': 'seed-team'}
    asked = {'question': 'What is fencing?', 'request_id': 'a1', 'expected_session_id': 'x', 'expected_generation': 1}
    return [
        ('projects', 'projects', {}, {}),
        ('remember', 'remember', {'event': remember}, {}),
        ('capture_policy', 'capture_policy', {'project_id': P}, {}),
        ('event_status', 'event_status', {'event_id': s.job_event['event_id'], 'project_id': P}, {}),
        # without a project the tool reads the receipt and each job and composes the answer; a superseded receipt is never complete
        ('event_status_without_project', 'event_status', {'event_id': s.job_event['event_id']}, {}),
        ('event_status_superseded', 'event_status', {'event_id': s.superseded_event['event_id']}, {'contains': '"complete": false'}),
        ('publish_document', 'publish_document', {'project_id': P, 'document': s.document}, {}),
        ('document_status', 'document_status', {'project_id': P, 'document_id': s.document['document_id']}, {}),
        ('document_manifest', 'document_manifest', {'project_id': P, 'limit': 50}, {}),
        ('revoke_document', 'revoke_document', {'project_id': P, 'document_id': s.revocable['document_id'], 'version': 2}, {}),
        ('search', 'search', {'project_ids': [P], 'q': 'fencing', 'semantic': False}, {}),
        ('details', 'details', {'refs': [s.ref], 'max_chars': 16000}, {}),
        ('context', 'context', {'project_ids': [P], 'q': 'fencing', 'semantic': False}, {}),
        ('timeline', 'timeline', {'project_ids': [P], 'anchor_ref': s.ref}, {}),
        ('work_state_write', 'work_state_write', {'project': P, 'list': 'plan', 'fields': {'task': 'Review fencing', 'status': 'doing'}, 'request_id': 'seed-plan'}, {}),
        # `includeClosed` is `include_closed`: with it the closed task is read, without it it is not
        ('work_state_read', 'work_state_read', {'project': P, 'list': 'plan', 'includeClosed': True}, {'contains': 'Ship fencing'}),
        ('work_state_read_open', 'work_state_read', {'project': P, 'list': 'plan'}, {'absent': 'Ship fencing', 'contains': 'Review fencing'}),
        # `dateStart`/`dateEnd` are `date_start`/`date_end`; `types` is a string of the tool that the endpoint takes as a list
        ('build_corpus', 'build_corpus', {'project': P, 'name': 'c-dates', 'query': 'fencing', 'dateStart': '2026-11-01', 'dateEnd': '2026-11-30'}, {}),
        ('build_corpus_types_text', 'build_corpus', {'project': P, 'name': 'c-types', 'query': 'fencing', 'types': 'decision, ,decision'}, {}),
        ('list_corpora', 'list_corpora', {'project': P}, {}),
        # `expected_version` is optional in the tool, required by the endpoint: the contract says to read the current version when it is left out
        ('rebuild_corpus', 'rebuild_corpus', {'project': P, 'name': 'c-rebuild'}, {}),
        ('rebuild_corpus_guarded', 'rebuild_corpus', {'project': P, 'name': 'c-rebuild', 'expected_version': 1}, {}),
        # an explicit null is as absent as an omitted argument; a name the actor does not have is the tool's NotFound on both sides; 0 is not translatable
        ('rebuild_corpus_null', 'rebuild_corpus', {'project': P, 'name': 'c-rebuild', 'expected_version': None}, {}),
        ('rebuild_corpus_missing', 'rebuild_corpus', {'project': P, 'name': 'no-such-corpus'}, {'error': True, 'contains': 'not found'}),
        ('rebuild_corpus_zero', 'rebuild_corpus', {'project': P, 'name': 'c-rebuild', 'expected_version': 0}, {'error': True, 'contains': 'Corpus version changed'}),
        ('rebuild_corpus_late', 'rebuild_corpus', {'project': P, 'name': 'zz-late'}, {}),
        ('rebuild_corpus_slash', 'rebuild_corpus', {'project': P, 'name': 'team/search'}, {}),
        ('prime_corpus', 'prime_corpus', {'project': P, 'name': 'c1'}, {}),
        # a new session each time: the tool and the endpoint act on twin corpora, and the identity fields (name, id, session) are not content
        ('reprime_corpus', 'reprime_corpus', {'project': P, 'name': 'c-reprime-tool'}, {'rest_arguments': {'project': P, 'name': 'c-reprime-rest'}, 'ignore': {'id', 'name', 'session_id'}}),
        ('query_corpus', 'query_corpus', {'project': P, 'name': 'c1', 'question': 'fencing', 'limit': 5}, {}),
        ('query_corpus_slash', 'query_corpus', {'project': P, 'name': 'team/search', 'question': 'fencing', 'limit': 5}, {}),
        ('get_observations', 'get_observations', {'projectId': P, 'ids': ids}, {}),
        ('observation_search', 'observation_search', {'projectId': P, 'query': 'fencing', 'limit': 5}, {}),
        ('observation_context', 'observation_context', {'projectId': P, 'query': 'index', 'limit': 5}, {}),
        ('observation_generation_status', 'observation_generation_status', {'jobId': s.job_id}, {}),
        ('important_workflow', 'important_workflow', {}, {}),  # local: answered by the MCP itself, no endpoint
        ('observation_add', 'observation_add', {'event': added}, {}),
        ('observation_record_event', 'observation_record_event', {'event': revision}, {}),
        # `project` is the `project_id` of the query here (not of the path); the seeded PostToolUse summary is content
        ('get_tool_uses', 'get_tool_uses', {'project': P, 'limit': 20}, {'items': 'items'}),
        ('get_tool_uses_filtered', 'get_tool_uses', {'project': P, 'tool': 'Read', 'limit': 5}, {'items': 'items'}),
        ('team_work_write', 'team_work_write', {'project': P, **work}, {}),
        ('team_work_read', 'team_work_read', {'project': P, 'list': 'release'}, {}),
        ('team_search', 'team_search', {'project': P, 'query': 'fencing', 'limit': 5}, {}),
        ('team_brief', 'team_brief', {'project': P, 'limit': 5}, {}),
        # generation is off by default: both refuse with the same message and call no model
        ('corpus_answer', 'corpus_answer', {'project': P, 'name': 'c1', **asked}, {'error': True}),
        ('corpus_answer_status', 'corpus_answer_status', {'project': P, 'name': 'c1', 'request_id': 'never-asked'}, {'error': True}),
        ('corpus_answer_status_saved', 'corpus_answer_status', {'project': P, 'name': 'c1', 'request_id': 'saved-answer'}, {'contains': 'Fencing guards a token.'}),
    ]


class ToolEndpointParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = Scenario()
        cls.table = cases(cls.scenario)
        cls.declared = declared_endpoints()

    @classmethod
    def tearDownClass(cls):
        cls.scenario.close()
        assert cls.scenario.spy.chat_calls == [], 'an endpoint or tool reached the language model'

    def check(self, label, rule=None, **override):
        """One case: the tool, and the request its contract entry translates to, compared. `rule` replaces the declared entry and `override` some
        arguments (mutations: a corpus build is not repeatable over a state that changed, so each run gets its own corpus name)."""
        s = self.scenario
        _, name, arguments, options = next(case for case in self.table if case[0] == label)
        arguments = {**arguments, **override}
        rule = self.declared[name] if rule is None else rule
        tool_status, tool_value = s.tool(name, arguments)
        reading = tool_status == 'ok' and isinstance(tool_value, dict) and (s.listing()[name]['annotations']['readOnlyHint'] or name in untrusted_writes())
        if reading:  # S-05: a tool that only reads (or answers retrieved content, `untrusted` in its endpoint) adds `untrusted` and `warning`; the endpoint does not, and what is compared is the rest
            self.assertIs(tool_value.get('untrusted'), True, label)
            self.assertTrue(tool_value.get('warning'), label)
            tool_value = without_envelope(tool_value)
        if rule == 'local':
            self.assertEqual(tool_status, 'ok', tool_value)
            self.assertIsInstance(tool_value, (str, dict))
            return
        endpoint_status, endpoint_value = s.endpoint(rule, options.get('rest_arguments', arguments))
        self.assertEqual(endpoint_status, tool_status, (label, tool_value, endpoint_value))
        self.assertEqual(tool_status, 'error' if options.get('error') else 'ok', (label, tool_value))
        self.assertTrue(tool_value, label)
        ignore = options.get('ignore', set())
        if reading:
            endpoint_value = without_envelope(endpoint_value)  # the endpoint's own `warning` (observation context, team brief) is the same text the tool keeps
        self.assertEqual(drop(endpoint_value, ignore), drop(tool_value, ignore), label)
        text = json.dumps(tool_value, indent=1)
        if 'contains' in options:
            self.assertIn(options['contains'], text, label)
        if 'absent' in options:
            self.assertNotIn(options['absent'], text, label)
        if 'items' in options:
            self.assertTrue(tool_value[options['items']], (label, 'the comparison would be of an empty list'))

    def test_the_table_covers_exactly_the_thirty_four_tools_of_the_server_and_the_contract(self):
        listed = self.scenario.tool_listing()
        self.assertEqual(len(listed), 34)
        self.assertEqual(sorted({case[1] for case in self.table}), sorted(listed))
        self.assertEqual(sorted(self.declared), sorted(listed))
        labels = [case[0] for case in self.table]
        self.assertEqual(len(labels), len(set(labels)))

    def test_the_contract_names_every_argument_of_every_tool_and_what_the_endpoint_reads(self):
        """The contract is enough to translate any call: each input property has a rule, and each rule names a real part of a real operation."""
        listed = self.scenario.tool_listing()
        openapi = self.scenario.client.app.openapi()

        def resolve(schema):
            return openapi['components']['schemas'][schema['$ref'].rsplit('/', 1)[1]] if '$ref' in schema else schema

        def operation(rule):
            found = openapi['paths'].get(rule['path'], {}).get(rule['method'].lower())
            self.assertIsNotNone(found, ('no such operation', rule['method'], rule['path']))
            return found

        for name, rule in self.declared.items():
            if rule == 'local':
                self.assertEqual(name, 'important_workflow')
                continue
            self.assertEqual(set(rule['args']), set(listed[name]['inputSchema'].get('properties', {})), name)
            found = operation(rule)
            placeholders = set(re.findall(r'\{([a-z_]+)\}', rule['path']))
            self.assertEqual({r['name'] for r in rule['args'].values() if r['in'] == 'path'}, placeholders, name)
            query = {r['name'] for r in rule['args'].values() if r['in'] == 'query'}
            self.assertLessEqual(query, {p['name'] for p in found.get('parameters', []) if p['in'] == 'query'}, name)
            body = [r for r in rule['args'].values() if r['in'] == 'body'] + [dict(f) for f in rule.get('fixed', [])]
            if rule['method'] == 'GET' or rule['method'] == 'DELETE':
                self.assertEqual(body, [], name)
            elif body:
                schema = resolve(found['requestBody']['content']['application/json']['schema'])
                named = {r['name'] for r in body if 'name' in r}
                self.assertLessEqual(named, set(schema.get('properties', {})), name)
                self.assertTrue(len(named) == len(body) or len(body) == 1, (name, 'a whole body cannot be mixed with fields'))
            for fixed in rule.get('fixed', []):
                self.assertIn('value', fixed, name)
            for where in rule['args'].values():
                if 'when_absent' in where:
                    read = where['when_absent']['read']
                    self.assertIsNotNone(openapi['paths'].get(read['path'], {}).get(read['method'].lower()), name)
                    self.assertEqual(set(read['args']), {'project', 'name'}, name)
                    self.assertEqual(where['when_absent']['take'], 'version', name)
            if 'without_project_id' in rule:
                step = rule['without_project_id']['receipt']
                self.assertIsNotNone(openapi['paths'].get(step['path'], {}).get(step['method'].lower()), name)
                self.assertIsNotNone(openapi['paths'].get(rule['without_project_id']['jobs']['path'], {}).get('get'), name)
                self.assertEqual(set(rule['without_project_id']['jobs']['args']), {'job_id'}, name)

    def mutated(self, label, edit, fresh=False):
        """A contract that assigns arguments by name, or leaves out a rule, fails the comparison: the cases do not pass by coincidence."""
        name = next(case[1] for case in self.table if case[0] == label)
        rule = copy.deepcopy(self.declared[name])
        edit(rule)
        names = (lambda: {'name': 'c-mut-' + uuid.uuid4().hex[:10]}) if fresh else dict
        self.check(label, **names())  # unchanged, it passes
        with self.assertRaises(AssertionError):
            self.check(label, rule, **names())

    def test_include_closed_by_name_is_ignored_by_the_endpoint(self):
        self.mutated('work_state_read', lambda rule: rule['args']['includeClosed'].update(name='includeClosed'))

    def test_the_date_arguments_by_name_are_refused_by_the_endpoint(self):
        self.mutated('build_corpus', lambda rule: rule['args']['dateStart'].update(name='dateStart'), fresh=True)

    def test_types_as_text_without_the_transform_is_refused_by_the_endpoint(self):
        self.mutated('build_corpus_types_text', lambda rule: rule['args']['types'].pop('transform'), fresh=True)

    def test_the_project_of_get_tool_uses_by_name_is_refused_by_the_endpoint(self):
        self.mutated('get_tool_uses', lambda rule: rule['args']['project'].update({'in': 'query', 'name': 'project'}))

    def test_a_complete_rule_that_forgets_the_superseded_receipt_disagrees_with_the_tool(self):
        self.mutated('event_status_superseded', lambda rule: rule['without_project_id']['result']['complete']['all_of'].pop(0))

    def test_a_rebuild_without_the_version_the_contract_reads_is_refused_by_the_endpoint(self):
        self.mutated('rebuild_corpus', lambda rule: rule['args']['expected_version'].pop('when_absent'))

    def test_a_rebuild_without_the_version_finds_a_corpus_beyond_the_first_hundred_of_the_list(self):
        """The list stops at 100 corpora (sorted by name); the read by name does not. The fillers are inserted directly (the budget is 32) and removed."""
        s = self.scenario
        with s.store.transaction() as c:
            actor = c.execute("SELECT actor_id FROM memory.agent_corpora WHERE project_id=%s AND name='zz-late'", (s.pid,)).fetchone()['actor_id']
            for number in range(105):
                c.execute("INSERT INTO memory.agent_corpora(id,project_id,actor_id,name,description,filters,version,canonical_hash) VALUES(%s,%s,%s,%s,'','{}'::jsonb,1,'x')",
                          ('filler-' + uuid.uuid4().hex, s.pid, actor, 'a-filler-%03d' % number))
        try:
            listed = s.rest('GET', s.prefix + '/corpora')[1]
            self.assertTrue(listed['truncated'])
            self.assertNotIn('zz-late', [item['name'] for item in listed['items']])  # the corpus is NOT in the first page
            self.check('rebuild_corpus_late')
        finally:
            with s.store.transaction() as c:
                c.execute("DELETE FROM memory.agent_corpora WHERE project_id=%s AND name LIKE 'a-filler-%%'", (s.pid,))

    def test_a_missing_name_is_the_tools_not_found_and_the_read_endpoint_validates_the_name_and_the_credential(self):
        s = self.scenario
        status, body = s.rest('GET', s.prefix + '/corpus', params={'name': 'no-such-corpus'})
        self.assertEqual((status, body['error']['code']), (404, 'not_found'))
        self.assertEqual(s.rest('GET', s.prefix + '/corpus', params={'name': 'team/search'})[1]['name'], 'team/search')  # any character, `/` included
        self.assertEqual(s.rest('GET', s.prefix + '/corpus')[0], 422)
        self.assertEqual(s.client.get(s.prefix + '/corpus', params={'name': 'c1'}).status_code, 401)  # no credential
        self.assertEqual(s.client.get('/v1/projects/not-a-project/corpus', params={'name': 'c1'}, headers=s.headers).status_code, 404)
        for bad in ('a\x00b', '   ', 'é' * 150):  # validated like the tool's name: 422, never a 503 from the database
            self.assertEqual(s.rest('GET', s.prefix + '/corpus', params={'name': bad})[0], 422, repr(bad))
        writer = s.store.create_key(s.admin, {'name': 'write only', 'project_ids': [s.pid], 'scopes': ['write']})
        response = s.client.get(s.prefix + '/corpus', params={'name': 'team/search'}, headers={'Authorization': 'Bearer ' + writer['token']})
        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'forbidden'))  # every corpus operation needs read

    def test_a_key_without_write_gets_the_tools_403_for_any_name_not_a_404_from_the_read(self):
        """The read by name asks for `read` only (a read-only key reads its corpus); when it finds nothing the request goes without a version and the
        rebuild endpoint refuses in the order of the tool, write first: a read-only key learns nothing about a name it does not have."""
        s = self.scenario
        rule = self.declared['rebuild_corpus']
        for scopes in (['read'], ['write']):
            token = s.store.create_key(s.admin, {'name': 'scoped-' + '-'.join(scopes), 'project_ids': [s.pid], 'scopes': scopes})['token']
            for name in ('c-rebuild', 'no-such-corpus'):
                for extra in ({}, {'expected_version': 0}):
                    arguments = {'project': s.pid, 'name': name, **extra}
                    with self.subTest(scopes=scopes, name=name, extra=extra), s.acting(token):
                        tool, endpoint = s.tool('rebuild_corpus', arguments), s.endpoint(rule, arguments)
                    self.assertEqual(tool, ('error', 'Operation not permitted'))
                    self.assertEqual(endpoint, tool)

    def test_a_blank_or_invalid_name_is_the_tools_403_for_a_key_without_write_and_its_own_error_otherwise(self):
        """Gap 9 of the phase 5 review: the order of the errors is the tool's for a name the read refuses (422) too."""
        s = self.scenario
        rule = self.declared['rebuild_corpus']
        for scopes in (['read'], ['write'], ['read', 'write']):
            token = s.store.create_key(s.admin, {'name': 'named-' + '-'.join(scopes), 'project_ids': [s.pid], 'scopes': scopes})['token']
            for name in ('   ', 'a\x00b', 'é' * 150):
                for extra in ({}, {'expected_version': 0}, {'expected_version': 2}):
                    arguments = {'project': s.pid, 'name': name, **extra}
                    with self.subTest(scopes=scopes, name=name, extra=extra), s.acting(token):
                        tool, endpoint = s.tool('rebuild_corpus', arguments), s.endpoint(rule, arguments)
                    self.assertEqual(endpoint, tool)
                    if scopes == ['read']:
                        self.assertEqual(tool, ('error', 'Operation not permitted'))

    def test_the_read_by_name_needs_read_only_and_a_key_with_write_alone_is_refused(self):
        """Gap 4 of the phase 5 review: `GET .../corpus` is a read, as the phase 3 left it."""
        s = self.scenario
        for scopes, expected in ((['read'], 200), (['write'], 403), (['read', 'write'], 200)):
            token = s.store.create_key(s.admin, {'name': 'reads-' + '-'.join(scopes), 'project_ids': [s.pid], 'scopes': scopes})['token']
            response = s.client.get(s.prefix + '/corpus', params={'name': 'c-rebuild'}, headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(response.status_code, expected, scopes)

    def test_a_zero_version_is_the_conflict_only_for_a_corpus_the_caller_has_and_otherwise_what_the_tool_says(self):
        s = self.scenario
        rule = self.declared['rebuild_corpus']
        for name, expected in (('c-rebuild', ('error', 'Corpus version changed')), ('no-such-corpus', ('error', 'Resource not found'))):
            arguments = {'project': s.pid, 'name': name, 'expected_version': 0}
            self.assertEqual(s.tool('rebuild_corpus', arguments), expected)
            self.assertEqual(s.endpoint(rule, arguments), expected)

    def test_another_actor_with_read_and_write_cannot_see_nor_rebuild_the_corpora_of_the_first(self):
        """A second real actor on the same project: the read endpoint, the tool and the translation all answer the not-found of the tool for a name that is the first actor's."""
        s = self.scenario
        user = s.store.create_user(s.admin, {'username': 'peer-' + uuid.uuid4().hex[:10], 'password': 'synthetic-password-123', 'project_ids': [s.pid], 'scopes': ['read', 'write']})
        made = s.store.create_key(s.admin, {'name': 'peer key', 'project_ids': [s.pid], 'scopes': ['read', 'write']})  # only an admin delegates a key: hand it to the peer
        with s.store.transaction() as c:
            c.execute('UPDATE memory.api_keys SET actor_id=%s WHERE id=%s', (user['id'], made['id']))
        token = made['token']
        rule = self.declared['rebuild_corpus']
        with s.acting(token):
            status, body = s.rest('GET', s.prefix + '/corpus', params={'name': 'c-rebuild'})
            self.assertEqual((status, body['error']['code']), (404, 'not_found'))
            self.assertEqual(s.rest('GET', s.prefix + '/corpora')[1]['items'], [])  # not in its list either
            for extra in ({}, {'expected_version': 0}, {'expected_version': 1}):
                arguments = {'project': s.pid, 'name': 'c-rebuild', **extra}
                tool, endpoint = s.tool('rebuild_corpus', arguments), s.endpoint(rule, arguments)
                self.assertEqual(tool, ('error', 'Resource not found'), extra)
                self.assertEqual(endpoint, tool, extra)
        self.assertEqual(s.rest('GET', s.prefix + '/corpus', params={'name': 'c-rebuild'})[0], 200)  # the first actor still has it

    def test_a_rebuild_that_lands_between_the_read_and_the_post_is_retried_like_the_tool_that_never_conflicts(self):
        s = self.scenario
        name = 'c-race-' + uuid.uuid4().hex[:8]
        self.assertEqual(s.rest('POST', s.prefix + '/corpora', json={'name': name, 'query': 'index'})[0], 200)
        bumps = []

        def concurrent():  # another rebuild changed the corpus after the read (once)
            if not bumps:
                bumps.append(1)
                with s.store.transaction() as c:
                    c.execute("UPDATE memory.agent_corpora SET version=version+1 WHERE project_id=%s AND name=%s", (s.pid, name))

        rule = self.declared['rebuild_corpus']
        status, value = s.endpoint(rule, {'project': s.pid, 'name': name}, concurrent)
        self.assertEqual((bumps, status, value['version']), ([1], 'ok', 2))
        tool_status, tool_value = s.tool('rebuild_corpus', {'project': s.pid, 'name': name})
        self.assertEqual((tool_status, tool_value), ('ok', value))  # the tool, over the same state, answers the same receipt
        # without the retry rule the same race is the 409 the tool does not have
        bumps.clear()
        without = copy.deepcopy(rule)
        del without['args']['expected_version']['when_absent']['retry']
        self.assertEqual(s.endpoint(without, {'project': s.pid, 'name': name}, concurrent)[0], 'error')

    def test_an_argument_the_contract_forgot_is_an_error(self):
        rule = copy.deepcopy(self.declared['work_state_read'])
        del rule['args']['includeClosed']
        with self.assertRaises(AssertionError):
            self.check('work_state_read', rule)


class RetryRuleTests(unittest.TestCase):
    """The `retry` rule of `rebuild_corpus` over a scripted server (no database): when it sends again, how many times, and when it stops."""

    @classmethod
    def setUpClass(cls):
        cls.rule = declared_endpoints()['rebuild_corpus']

    def run_rule(self, versions, posted, arguments=None):
        reads, posts = [], []

        def rest(method, path, **kwargs):
            if method == 'GET':
                reads.append(path)
                if isinstance(versions, tuple):
                    return versions
                return 200, {'version': versions[min(len(reads), len(versions)) - 1]}
            posts.append(kwargs['json'])
            return posted(len(posts))

        result = perform(self.rule, arguments or {'project': 'p', 'name': 'a/b'}, rest)
        return result, reads, posts

    def test_the_version_read_by_name_is_sent(self):
        result, reads, posts = self.run_rule([4], lambda n: (200, {'version': 4}))
        self.assertEqual((result, posts), ((200, {'version': 4}), [{'expected_version': 4}]))
        self.assertEqual(reads, ['/v1/projects/p/corpus'])

    def test_a_changed_version_is_sent_again_at_most_three_more_times(self):
        result, reads, posts = self.run_rule([1, 2, 3, 4, 5, 6], lambda n: (409, {'error': {'message': 'Corpus version changed'}}))
        self.assertEqual(result[0], 409)
        self.assertEqual([post['expected_version'] for post in posts], [1, 2, 3, 4])
        self.assertEqual(len(reads), 4)

    def test_a_conflict_with_an_unchanged_version_is_the_answer_without_a_second_post(self):
        result, reads, posts = self.run_rule([7], lambda n: (409, {'error': {'message': 'Rebuild would remove more than half the corpus'}}))
        self.assertEqual((result[0], len(posts), len(reads)), (409, 1, 2))

    def test_a_race_that_settles_is_a_success(self):
        result, reads, posts = self.run_rule([1, 2], lambda n: (409, {}) if n == 1 else (200, {'version': 2}))
        self.assertEqual((result, [post['expected_version'] for post in posts]), ((200, {'version': 2}), [1, 2]))

    def test_a_given_version_is_sent_as_it_is_and_zero_goes_as_a_version_no_corpus_has_without_a_read(self):
        result, reads, posts = self.run_rule([9], lambda n: (200, {}), {'project': 'p', 'name': 'c', 'expected_version': 3})
        self.assertEqual((reads, posts), ([], [{'expected_version': 3}]))
        result, reads, posts = self.run_rule([9], lambda n: (409, {'error': {'message': 'Corpus version changed'}}), {'project': 'p', 'name': 'c', 'expected_version': 0})
        self.assertEqual((result[0], reads, posts), (409, [], [{'expected_version': 2147483646}]))  # the endpoint answers in the order of the tool

    def test_a_read_that_finds_no_corpus_or_refuses_the_name_sends_a_version_no_corpus_has(self):
        for status in (404, 422):
            result, reads, posts = self.run_rule((status, {'error': {'code': 'x'}}), lambda n: (403, {'error': {'code': 'forbidden'}}))
            self.assertEqual((result[0], posts), (403, [{'expected_version': 2147483646}]), status)  # the server's own order: a key without write is refused before the name or the corpus
            self.assertEqual(len(reads), 1, status)

    def test_any_other_failed_read_is_the_answer(self):
        for status in (401, 403, 409):
            result, reads, posts = self.run_rule((status, {'error': {'code': 'x'}}), lambda n: (200, {}))
            self.assertEqual((result[0], posts), (status, []), status)


def make_case(label):
    def run(self):
        self.check(label)
    run.__name__ = 'test_parity_' + label
    return run


def _label_names():
    """The labels are fixed text: the methods are generated from them without a database (the table itself needs the ids)."""
    return ('projects', 'remember', 'capture_policy', 'event_status', 'event_status_without_project', 'event_status_superseded', 'publish_document',
            'document_status', 'document_manifest', 'revoke_document', 'search', 'details', 'context', 'timeline', 'work_state_write', 'work_state_read',
            'work_state_read_open', 'build_corpus', 'build_corpus_types_text', 'list_corpora', 'rebuild_corpus', 'rebuild_corpus_guarded',
            'rebuild_corpus_null', 'rebuild_corpus_missing', 'rebuild_corpus_zero', 'rebuild_corpus_late', 'rebuild_corpus_slash', 'prime_corpus', 'reprime_corpus', 'query_corpus', 'query_corpus_slash', 'get_observations',
            'observation_search', 'observation_context', 'observation_generation_status', 'important_workflow', 'observation_add',
            'observation_record_event', 'get_tool_uses', 'get_tool_uses_filtered', 'team_work_write', 'team_work_read', 'team_search', 'team_brief',
            'corpus_answer', 'corpus_answer_status', 'corpus_answer_status_saved')


for _label in _label_names():
    setattr(ToolEndpointParityTests, 'test_parity_' + _label, make_case(_label))


if __name__ == '__main__':
    unittest.main()
