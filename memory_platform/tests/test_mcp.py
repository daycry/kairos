import unittest
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.errors import Unauthorized, NotFound


class NativeMCPTests(unittest.TestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.authenticate_bearer.return_value = {'id': 'test', 'credential_type': 'bearer'}
        self.auth.authenticate_session.side_effect = Unauthorized()
        self.retrieval = Mock(search=AsyncMock(return_value={'items': [], 'backends': {}, 'partial': False}))
        self.app = create_app(Settings('unused'), store=Mock(), auth=self.auth, retrieval=self.retrieval)

    def test_native_initialize_list_and_search(self):
        with TestClient(self.app, base_url='http://localhost:8790') as client:
            headers = {'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}
            response = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn('serverInfo', response.json()['result'])
            listed = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
            self.assertEqual({v['name'] for v in listed.json()['result']['tools']}, {
                'search', 'details', 'context', 'timeline', 'projects', 'remember', 'event_status',
                'publish_document', 'document_status', 'document_manifest', 'revoke_document',
                'work_state_write', 'work_state_read', 'build_corpus', 'prime_corpus',
                'query_corpus', 'rebuild_corpus', 'reprime_corpus', 'get_observations',
                'observation_search', 'observation_context', 'observation_generation_status',
                'important_workflow', 'capture_policy', 'list_corpora',
                'observation_add', 'observation_record_event', 'get_tool_uses',
                'team_work_write', 'team_work_read', 'team_search', 'team_brief',
                'corpus_answer', 'corpus_answer_status'})
            search = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': 'fixture'}}})
            self.assertEqual(search.status_code, 200, search.text)
            self.assertFalse(search.json()['result'].get('isError'))
        self.retrieval.search.assert_awaited_once()

    def test_missing_auth_cannot_discover_or_invoke(self):
        with TestClient(self.app, base_url='http://localhost:8790') as client:
            response = client.post('/mcp/', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            self.assertEqual(response.status_code, 401)
        self.retrieval.search.assert_not_called()

    def test_tool_scope_denial_is_not_success(self):
        self.retrieval.search.side_effect = NotFound()
        with TestClient(self.app, base_url='http://localhost:8790') as client:
            response = client.post('/mcp/', headers={'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['foreign'], 'q': 'fixture'}}})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['result']['isError'])
