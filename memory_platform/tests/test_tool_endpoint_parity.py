"""CA-06: each of the 34 MCP tools and its `/v1` endpoint return the same content for the same credential and arguments.

A scenario is seeded once in an isolated PostgreSQL (observations, an event with a job, documents, a primed corpus, team and
private work). For every tool the test calls the internal MCP endpoint and then the endpoint the contract declares in
`x-kairos-endpoint`, with one writer key, and compares what comes back. The comparison is the content: the MCP byte budget
(`render`) and the additive fields of the untrusted-data envelope (S-05, C-03) are the only differences allowed, and neither is
produced yet. Operations that write are idempotent by design (a retry returns the same receipt), so the second call is the
endpoint's, over the state the tool left; `reprime_corpus`, which opens a new session each time, ignores the session fields.

The table `CASES` is checked against the tools the server lists and against the exported contract: a tool without a case, a case
without a tool or an endpoint that is not the declared one fails the run (the removal of an endpoint turns its case red).
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest
import uuid

from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.llm_spy import ChatSpy
from memory_platform.tests.test_store import create_core, event

ORIGIN = 'http://localhost:8790'
EXPORTER = Path(__file__).parents[2] / 'scripts' / 'export-contracts.py'


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
        self.ref = self.search_ref()
        # documents: one to read and one to withdraw
        self.document = self.document_body('Canonical approved fixture')
        self.revocable = self.document_body('A document that will be withdrawn')
        for value in (self.document, self.revocable):
            assert self.rest('POST', self.prefix + '/documents', json=value)[0] == 202
        # a primed corpus, private work and shared work
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'c1', 'query': 'fencing'})[0] == 200
        assert self.rest('POST', self.prefix + '/corpora/c1/prime', json={})[0] == 200
        assert self.rest('POST', self.prefix + '/corpora', json={'name': 'c-rebuild', 'query': 'index'})[0] == 200  # a filter the other cases never change
        for name in ('c-reprime-tool', 'c-reprime-rest'):
            assert self.rest('POST', self.prefix + '/corpora', json={'name': name, 'query': 'fencing'})[0] == 200
            assert self.rest('POST', self.prefix + '/corpora/' + name + '/prime', json={})[0] == 200
        assert self.rest('POST', self.prefix + '/team-work', json={'list': 'release', 'fields': {'task': 'Rotate the fencing token', 'status': 'todo'}, 'request_id': 'seed-team'})[0] == 200
        assert self.rest('POST', self.prefix + '/work-state', json={'list': 'plan', 'fields': {'task': 'Review fencing', 'status': 'doing'}, 'request_id': 'seed-plan'})[0] == 200

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
    """tool name -> (MCP arguments, (method, path, request keywords)[, options]). Built after the scenario so the ids are real."""
    P, prefix = s.pid, s.prefix
    remember = event(P, generate=False, item_id=str(uuid.uuid4()))
    added = event(P, generate=False, item_id=str(uuid.uuid4()))
    revision = event(P, generate=False, item_id=added['item_id'], version=2, payload={'title': 'Fencing note', 'content': 'Revised: also take a lease', 'category': 'decision', 'source': {'uri': 'fixture://parity'}})
    ids = [s.obs1['item_id'], s.obs2['item_id']]
    return {
        'projects': ({}, ('GET', '/v1/projects', {})),
        'remember': ({'event': remember}, ('POST', '/v1/events', {'json': remember})),
        'capture_policy': ({'project_id': P}, ('GET', prefix + '/capture-policy', {})),
        'event_status': ({'event_id': s.job_event['event_id'], 'project_id': P}, ('GET', prefix + '/events/' + s.job_event['event_id'] + '/status', {})),
        'publish_document': ({'project_id': P, 'document': s.document}, ('POST', prefix + '/documents', {'json': s.document})),
        'document_status': ({'project_id': P, 'document_id': s.document['document_id']}, ('GET', prefix + '/documents/' + s.document['document_id'], {})),
        'document_manifest': ({'project_id': P, 'limit': 50}, ('GET', prefix + '/manifest', {'params': {'limit': 50}})),
        'revoke_document': ({'project_id': P, 'document_id': s.revocable['document_id'], 'version': 2},
                            ('DELETE', prefix + '/documents/' + s.revocable['document_id'], {'params': {'version': 2}})),
        'search': ({'project_ids': [P], 'q': 'fencing', 'semantic': False}, ('POST', '/v1/search', {'json': {'project_ids': [P], 'q': 'fencing', 'semantic': False}})),
        'details': ({'refs': [s.ref], 'max_chars': 16000}, ('POST', '/v1/details', {'json': {'refs': [s.ref], 'max_chars': 16000}})),
        'context': ({'project_ids': [P], 'q': 'fencing', 'semantic': False}, ('POST', '/v1/context', {'json': {'project_ids': [P], 'q': 'fencing', 'semantic': False}})),
        'timeline': ({'project_ids': [P], 'anchor_ref': s.ref}, ('POST', '/v1/timeline', {'json': {'project_ids': [P], 'anchor_ref': s.ref}})),
        'work_state_write': ({'project': P, 'list': 'plan', 'fields': {'task': 'Review fencing', 'status': 'doing'}, 'request_id': 'seed-plan'},
                             ('POST', prefix + '/work-state', {'json': {'list': 'plan', 'fields': {'task': 'Review fencing', 'status': 'doing'}, 'request_id': 'seed-plan'}})),
        'work_state_read': ({'project': P, 'list': 'plan', 'includeClosed': True}, ('GET', prefix + '/work-state', {'params': {'list': 'plan', 'include_closed': True}})),
        'build_corpus': ({'project': P, 'name': 'c-dates', 'query': 'fencing', 'dateStart': '2026-11-01', 'dateEnd': '2026-11-30'},
                         ('POST', prefix + '/corpora', {'json': {'name': 'c-dates', 'query': 'fencing', 'date_start': '2026-11-01', 'date_end': '2026-11-30'}})),
        'list_corpora': ({'project': P}, ('GET', prefix + '/corpora', {})),
        'rebuild_corpus': ({'project': P, 'name': 'c-rebuild', 'expected_version': 1}, ('POST', prefix + '/corpora/c-rebuild/rebuild', {'json': {'expected_version': 1}})),
        'prime_corpus': ({'project': P, 'name': 'c1'}, ('POST', prefix + '/corpora/c1/prime', {'json': {}})),
        # a new session each time: the tool and the endpoint act on twin corpora, and the identity fields (name, id, session) are not content
        'reprime_corpus': ({'project': P, 'name': 'c-reprime-tool'}, ('POST', prefix + '/corpora/c-reprime-rest/prime', {'json': {'fresh': True}}, {'ignore': {'id', 'name', 'session_id'}})),
        'query_corpus': ({'project': P, 'name': 'c1', 'question': 'fencing', 'limit': 5}, ('POST', prefix + '/corpora/c1/query', {'json': {'question': 'fencing', 'limit': 5}})),
        'get_observations': ({'projectId': P, 'ids': ids}, ('POST', prefix + '/observations/get', {'json': {'ids': ids}})),
        'observation_search': ({'projectId': P, 'query': 'fencing', 'limit': 5}, ('GET', prefix + '/observations/search', {'params': {'query': 'fencing', 'limit': 5}})),
        'observation_context': ({'projectId': P, 'query': 'index', 'limit': 5}, ('GET', prefix + '/observations/context', {'params': {'query': 'index', 'limit': 5}})),
        'observation_generation_status': ({'jobId': s.job_id}, ('GET', '/v1/jobs/' + s.job_id, {})),
        'important_workflow': ({}, None),  # local: answered by the MCP itself, no endpoint
        'observation_add': ({'event': added}, ('POST', '/v1/observations', {'json': added})),
        'observation_record_event': ({'event': revision}, ('POST', '/v1/observations/events', {'json': revision})),
        'get_tool_uses': ({'project': P, 'limit': 20}, ('GET', '/v1/tool-uses', {'params': {'project_id': P, 'limit': 20}})),
        'team_work_write': ({'project': P, 'list': 'release', 'fields': {'task': 'Rotate the fencing token', 'status': 'todo'}, 'request_id': 'seed-team'},
                            ('POST', prefix + '/team-work', {'json': {'list': 'release', 'fields': {'task': 'Rotate the fencing token', 'status': 'todo'}, 'request_id': 'seed-team'}})),
        'team_work_read': ({'project': P, 'list': 'release'}, ('GET', prefix + '/team-work', {'params': {'list': 'release'}})),
        'team_search': ({'project': P, 'query': 'fencing', 'limit': 5}, ('GET', prefix + '/team-search', {'params': {'query': 'fencing', 'limit': 5}})),
        'team_brief': ({'project': P, 'limit': 5}, ('GET', prefix + '/team-brief', {'params': {'limit': 5}})),
        # generation is off by default: both refuse with the same message and call no model
        'corpus_answer': ({'project': P, 'name': 'c1', 'question': 'What is fencing?', 'request_id': 'a1', 'expected_session_id': 'x', 'expected_generation': 1},
                          ('POST', prefix + '/corpora/c1/answers', {'json': {'question': 'What is fencing?', 'request_id': 'a1', 'expected_session_id': 'x', 'expected_generation': 1}})),
        'corpus_answer_status': ({'project': P, 'name': 'c1', 'request_id': 'never-asked'}, ('GET', prefix + '/corpora/c1/answers/never-asked', {})),
    }


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

    def rest_view(self, status, body):
        if status >= 400:
            return 'error', body['error']['message']
        return 'ok', body

    def listed_tools(self):
        response = self.scenario.client.post('/mcp/', headers={**self.scenario.headers, 'Accept': 'application/json, text/event-stream'},
                                             json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        return [tool['name'] for tool in response.json()['result']['tools']]

    def test_the_table_covers_exactly_the_thirty_four_tools_of_the_server_and_the_contract(self):
        listed = self.listed_tools()
        self.assertEqual(len(listed), 34)
        self.assertEqual(sorted(self.table), sorted(listed))
        self.assertEqual(sorted(self.declared), sorted(listed))

    def template(self, path):
        """The case path with its real ids put back as the placeholders of the declared path."""
        s = self.scenario
        for real, placeholder in ((s.pid, '{project_id}'), (s.job_event['event_id'], '{event_id}'), (s.document['document_id'], '{document_id}'),
                                  (s.revocable['document_id'], '{document_id}'), (s.job_id, '{job_id}')):
            path = path.replace(real, placeholder)
        path = re.sub(r'(/corpora/)[^/]+', lambda found: found.group(1) + '{name}', path)
        return re.sub(r'(/answers/)[^/]+$', lambda found: found.group(1) + '{request_id}', path)

    def test_each_case_calls_the_endpoint_the_contract_declares(self):
        for name, (_, request) in self.table.items():
            declared = self.declared[name]
            if request is None:
                self.assertEqual(declared, 'local', name)
                continue
            self.assertEqual((declared['method'], declared['path']), (request[0], self.template(request[1])), name)


REFUSING = {'corpus_answer', 'corpus_answer_status'}


def make_case(name):
    def run(self):
        s = self.scenario
        arguments, request = self.table[name]
        tool_status, tool_value = s.tool(name, arguments)
        if request is None:
            self.assertEqual(tool_status, 'ok', tool_value)
            self.assertIsInstance(tool_value, (str, dict))
            return
        method, path, kwargs, *options = request
        ignore = options[0]['ignore'] if options else set()
        status, body = s.rest(method, path, **kwargs)
        endpoint_status, endpoint_value = self.rest_view(status, body)
        self.assertEqual(endpoint_status, tool_status, (name, tool_value, endpoint_value))
        # only the two answer tools are expected to refuse (generation is off); every other case compares real, non-empty content
        self.assertEqual(tool_status, 'error' if name in REFUSING else 'ok', (name, tool_value))
        self.assertTrue(tool_value, name)
        self.assertEqual(drop(endpoint_value, ignore), drop(tool_value, ignore), name)
        if name == 'event_status':
            # without a project the tool composes the receipt and its jobs: the same two reads over `/v1`
            _, without = s.tool(name, {'event_id': s.job_event['event_id']})
            receipt = s.rest('GET', '/v1/events/' + s.job_event['event_id'])[1]
            jobs = [s.rest('GET', '/v1/jobs/' + job)[1] for job in receipt['jobs']]
            self.assertEqual(without, {'receipt': receipt, 'jobs': jobs, 'complete': all(job['state'] == 'succeeded' for job in jobs)})
    run.__name__ = 'test_parity_' + name
    return run


for _name in ('projects', 'remember', 'capture_policy', 'event_status', 'publish_document', 'document_status', 'document_manifest', 'revoke_document',
              'search', 'details', 'context', 'timeline', 'work_state_write', 'work_state_read', 'build_corpus', 'list_corpora', 'rebuild_corpus',
              'prime_corpus', 'reprime_corpus', 'query_corpus', 'get_observations', 'observation_search', 'observation_context',
              'observation_generation_status', 'important_workflow', 'observation_add', 'observation_record_event', 'get_tool_uses',
              'team_work_write', 'team_work_read', 'team_search', 'team_brief', 'corpus_answer', 'corpus_answer_status'):
    setattr(ToolEndpointParityTests, 'test_parity_' + _name, make_case(_name))


if __name__ == '__main__':
    unittest.main()
