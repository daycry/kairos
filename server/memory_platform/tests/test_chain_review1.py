"""The corrections of the phase 5 review (attempt 1) through the real chain: what kairos-mcp answers equals what the internal MCP answers for the same call.

UUIDs in any form, integers written as floats, `.` and `..` in a path argument, an explicit `null`, the envelope of `query_corpus`, the credential check of
`initialize`, and the null that `ChainSession.call` can now send. Each case calls both MCPs over the same state and compares their answers.
"""
import json
import unittest
import uuid
from unittest.mock import patch

from memory_platform.agent_store import AgentStore
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.chain_harness import ChainClient, strip_envelope
from memory_platform.tests.chain_services import ChainSession
from memory_platform.tests.test_store import create_core, event

ACCEPT = 'application/json, text/event-stream'


def data(result):
    structured = result.get('structuredContent')
    if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
        return json.loads(structured['result'])
    return structured if isinstance(structured, dict) else json.loads(result['content'][0]['text'])


class ChainReviewTests(unittest.TestCase):
    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.item = event(self.pid, generate=False, payload={'title': 'Fencing', 'content': 'Use fencing before projection', 'source': {'uri': 'fixture://c'}})
        self.store.ingest_event(self.admin, self.item)
        AgentStore(self.store).build_corpus(self.admin, self.pid, 'c1', query='fencing')
        AgentStore(self.store).prime_corpus(self.admin, self.pid, 'c1')
        self.token = self.store.create_key(self.admin, {'name': 'chain-review', 'project_ids': [self.pid], 'scopes': ['read', 'write']})['token']
        self.app = create_app(Settings('unused'), store=self.store, auth=Auth(self.store))
        self.client = ChainClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, client, method, params=None, token=None):
        return client.post('/mcp/', headers={'Authorization': 'Bearer ' + (token or self.token), 'Accept': ACCEPT},
                           json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    def both(self, name, arguments):
        """`(chain result, internal result)` of the same tool call, each as the `result` object of its answer."""
        calls = [self.post(client, 'tools/call', {'name': name, 'arguments': arguments}) for client in (self.client.chain, self.client.server_mcp)]
        for response in calls:
            self.assertEqual(response.status_code, 200, response.text)
        return calls[0].json()['result'], calls[1].json()['result']

    def same(self, name, arguments):
        chain, internal = self.both(name, arguments)
        self.assertEqual(bool(chain.get('isError')), bool(internal.get('isError')), (chain, internal))
        if chain.get('isError'):
            self.assertEqual(chain['content'][0]['text'], internal['content'][0]['text'])
        else:
            self.assertEqual(strip_envelope(data(chain)), strip_envelope(data(internal)))
        return chain

    def test_a_uuid_in_any_form_finds_the_event_like_the_internal_mcp_does(self):
        eid = self.item['event_id']
        for form in (eid.upper(), eid.replace('-', ''), '{' + eid + '}', 'urn:uuid:' + eid):
            for arguments in ({'event_id': form}, {'event_id': form, 'project_id': self.pid}):
                with self.subTest(form=form, arguments=arguments):
                    chain = self.same('event_status', arguments)
                    self.assertFalse(chain.get('isError'), chain)
                    self.assertNotEqual(data(chain).get('found'), False)
        self.assertEqual(self.client.get('/v1/events/' + eid.upper(), headers={'Authorization': 'Bearer ' + self.token}).status_code, 200)  # any REST client

    def test_documents_by_uuid_in_any_form_are_one_document_for_a_rest_client_too(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        missing = str(uuid.uuid4())
        for form in (missing, missing.upper(), missing.replace('-', ''), '{' + missing + '}'):
            self.assertEqual(self.client.get('/v1/projects/%s/documents/%s' % (self.pid, form), headers=headers).status_code, 404, form)
            self.same('document_status', {'project_id': self.pid, 'document_id': form})

    def test_an_invalid_uuid_has_the_text_of_the_internal_mcp(self):
        for name, arguments in (('event_status', {'event_id': 'not-a-uuid'}), ('event_status', {'event_id': 'x' * 40, 'project_id': self.pid}),
                                ('document_status', {'project_id': self.pid, 'document_id': '123'}),
                                ('revoke_document', {'project_id': self.pid, 'document_id': '', 'version': 1})):
            with self.subTest(name=name, arguments=arguments):
                chain = self.same(name, arguments)
                self.assertTrue(chain['isError'])
                self.assertIn('Input should be a valid UUID', chain['content'][0]['text'])

    def test_integers_in_float_form_are_accepted_like_the_internal_mcp_does(self):
        self.same('document_manifest', {'project_id': self.pid, 'limit': 20.0})
        self.same('observation_search', {'projectId': self.pid, 'query': 'fencing', 'limit': 20.0})
        self.same('rebuild_corpus', {'project': self.pid, 'name': 'c1', 'expected_version': 0.0})
        self.same('rebuild_corpus', {'project': self.pid, 'name': 'c1', 'expected_version': 1.0})
        self.same('get_tool_uses', {'project': self.pid, 'limit': 5.0})

    def test_dot_segments_are_values_not_routes(self):
        for value in ('.', '..'):
            chain = self.same('observation_generation_status', {'jobId': value})
            self.assertTrue(chain['isError'])
            self.assertEqual(chain['content'][0]['text'], 'Error executing tool observation_generation_status: Resource not found')
            self.same('rebuild_corpus', {'project': self.pid, 'name': value})

    def test_query_corpus_carries_the_untrusted_envelope_in_both_mcps(self):
        chain, internal = self.both('query_corpus', {'project': self.pid, 'name': 'c1', 'question': 'fencing'})
        for result in (chain, internal):
            self.assertFalse(result.get('isError'), result)
            self.assertIs(data(result)['untrusted'], True)
        self.assertEqual(data(chain), data(internal))

    def test_initialize_with_a_credential_the_server_does_not_know_is_a_401_in_both(self):
        params = {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'chain', 'version': '1'}}
        for method, arguments in (('initialize', params), ('tools/list', {})):
            with self.subTest(method=method):
                chain = self.post(self.client.chain, method, arguments, token='kairos-not-a-key-' + uuid.uuid4().hex)
                internal = self.post(self.client.server_mcp, method, arguments, token='kairos-not-a-key-' + uuid.uuid4().hex)
                self.assertEqual((chain.status_code, internal.status_code), (401, 401))
                self.assertEqual(chain.json()['error'], internal.json()['error'])
                self.assertEqual(self.post(self.client.chain, method, arguments).status_code, 200)
        bogus = self.post(self.client.chain, 'tools/call', {'name': 'important_workflow', 'arguments': {}}, token='kairos-not-a-key-' + uuid.uuid4().hex)
        self.assertEqual(bogus.status_code, 401)


class ExplicitNullTests(unittest.TestCase):
    """`ChainSession.call` sends what it is given: a `None` is a JSON `null`, and the contract says null is as if the argument were left out."""

    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.item = event(self.pid, generate=False, payload={'title': 'Fencing', 'content': 'Use fencing before projection', 'source': {'uri': 'fixture://n'}})
        self.store.ingest_event(self.admin, self.item)
        AgentStore(self.store).build_corpus(self.admin, self.pid, 'c1', query='fencing')
        self.session = ChainSession(self.store, self.admin)
        self.addCleanup(self.session.close)

    def test_the_session_sends_a_null_it_is_given(self):
        sent = []
        original = self.session.client.chain.post

        def spy(url, **kwargs):
            sent.append(kwargs['json']['params']['arguments'])
            return original(url, **kwargs)
        with patch.object(self.session.client.chain, 'post', spy):
            self.session.call(self.admin, self.pid, 'event_status', event_id=self.item['event_id'], project_id=None)
        self.assertEqual(sent, [{'event_id': self.item['event_id'], 'project_id': None}])

    def test_project_id_null_is_the_event_status_without_a_project(self):
        without = self.session.call(self.admin, self.pid, 'event_status', event_id=self.item['event_id'])
        explicit = self.session.call(self.admin, self.pid, 'event_status', event_id=self.item['event_id'], project_id=None)
        self.assertEqual(explicit, without)
        self.assertEqual(explicit['receipt']['status'], 'accepted')
        self.assertNotIn('found', explicit)

    def test_expected_version_null_is_a_rebuild_over_whatever_version_the_corpus_has(self):
        done = self.session.call(self.admin, self.pid, 'rebuild_corpus', project=self.pid, name='c1', expected_version=None)
        self.assertEqual(done['version'], 1)
        again = self.session.call(self.admin, self.pid, 'rebuild_corpus', project=self.pid, name='c1', force=False, expected_version=None)
        self.assertEqual(again['version'], 1)

    def test_a_null_in_a_work_list_write_is_a_write_without_a_version_check(self):
        first = self.session.call(self.admin, self.pid, 'work_state_write', project=self.pid, list='todo', fields={'task': 'a'}, request_id='r1', expected_version=None)
        second = self.session.call(self.admin, self.pid, 'work_state_write', project=self.pid, list='todo', fields={'task': 'b'}, request_id='r2', expected_version=None)
        self.assertGreater(second['version'], first['version'])


if __name__ == '__main__':
    unittest.main()
