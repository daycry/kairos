import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.errors import Unauthorized, NotFound
from memory_platform.tests.chain_harness import ChainMode, chain_variant


class NativeMCPTests(ChainMode, unittest.TestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.authenticate_bearer.return_value = {'id': 'test', 'credential_type': 'bearer'}
        self.auth.authenticate_session.side_effect = Unauthorized()
        self.retrieval = Mock(search=AsyncMock(return_value={'items': [], 'backends': {}, 'partial': False}))
        self.app = create_app(Settings('unused'), store=Mock(), auth=self.auth, retrieval=self.retrieval)

    def test_native_initialize_list_and_search(self):
        with self.open(self.app) as client:
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
        with self.open(self.app) as client:
            response = client.post('/mcp/', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            self.assertEqual(response.status_code, 401)
        self.retrieval.search.assert_not_called()

    def test_tool_scope_denial_is_not_success(self):
        self.retrieval.search.side_effect = NotFound()
        with self.open(self.app) as client:
            response = client.post('/mcp/', headers={'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['foreign'], 'q': 'fixture'}}})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['result']['isError'])


class SearchHitFieldsTests(ChainMode, unittest.TestCase):
    """CA-29 at the tool: `matched_chunk` travels untouched when a hit has it and is absent when it has not."""
    def test_search_passes_matched_chunk_through_and_omits_it_for_other_hits(self):
        auth = Mock()
        auth.authenticate_bearer.return_value = {'id': 'test', 'credential_type': 'bearer'}
        auth.authenticate_session.side_effect = Unauthorized()
        plain = {'ref': 'documental:a:one:1', 'layer': 'documental', 'project_id': 'a', 'item_id': 'one', 'title': 'T', 'excerpt': 'x', 'validation_status': 'validated', 'version': 1}
        chunked = dict(plain, ref='documental:a:two:1', item_id='two', matched_chunk={'ordinal': 4, 'char_start': 5200, 'char_end': 6700})
        retrieval = Mock(search=AsyncMock(return_value={'items': [chunked, plain], 'backends': {}, 'partial': False}))
        app = create_app(Settings('unused'), store=Mock(), auth=auth, retrieval=retrieval)
        with self.open(app) as client:
            headers = {'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}
            client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}})
            call = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': 'fixture'}}})
        self.assertEqual(call.status_code, 200, call.text)
        result = call.json()['result']
        self.assertFalse(result.get('isError'), result)
        content = result.get('structuredContent') or json.loads(result['content'][0]['text'])
        items = content.get('result', content)['items']
        self.assertEqual(items[0]['matched_chunk'], {'ordinal': 4, 'char_start': 5200, 'char_end': 6700})
        self.assertNotIn('matched_chunk', items[1])
        self.assertEqual(items[1]['ref'], 'documental:a:one:1')


class DegradedSemanticToolTests(ChainMode, unittest.TestCase):
    """CA-16 at the tools: `search` and `context` keep answering with lexical hits and carry `degraded` when only the semantic layer fails."""
    def test_search_and_context_tools_report_degraded_with_lexical_hits(self):
        from memory_platform.providers import ProviderError
        from memory_platform.retrieval import Retrieval
        store, auth = Mock(), Mock()
        auth.authenticate_bearer.return_value = {'id': 'test', 'credential_type': 'bearer'}
        auth.authenticate_session.side_effect = Unauthorized()
        store.search_items.return_value = [{'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic',
                                            'title': 'Lexical', 'excerpt': 'x', 'validation_status': 'unknown'}]
        store.search_documents.return_value, store.search_native_facts.return_value, store.has_vectors.return_value = [], [], True
        settings = Settings('unused', request_timeout=5, embedding_query_timeout=0.3)
        app = create_app(settings, store=store, auth=auth, retrieval=Retrieval(store, settings, Mock(embed=AsyncMock(side_effect=ProviderError('http_503')))))
        with self.open(app) as client:
            headers = {'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}
            client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}})
            for number, name in ((2, 'search'), (3, 'context')):
                call = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': number, 'method': 'tools/call', 'params': {'name': name, 'arguments': {'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic']}}})
                self.assertEqual(call.status_code, 200, call.text)
                result = call.json()['result']
                self.assertFalse(result.get('isError'), result)
                content = result.get('structuredContent') or json.loads(result['content'][0]['text'])
                content = content.get('result', content)
                self.assertEqual([item['item_id'] for item in content['items']], ['lex'])
                self.assertEqual(content['backends']['semantic']['status'], 'unavailable')
                self.assertEqual(content['degraded'], {'layer': 'semantic', 'reason': 'provider_error'})

    def test_semantic_budget_ms_is_accepted_by_search_and_context_and_cuts_the_semantic_layer_short(self):
        import time
        from memory_platform.retrieval import Retrieval
        async def stalled(*args, **kwargs):
            await asyncio.sleep(30)
        store, auth = Mock(), Mock()
        auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer'}
        auth.authenticate_session.side_effect = Unauthorized()
        store.search_items.return_value = [{'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic',
                                            'title': 'Lexical', 'excerpt': 'x', 'validation_status': 'unknown'}]
        store.search_documents.return_value, store.search_native_facts.return_value, store.has_vectors.return_value = [], [], True
        settings = Settings('unused', request_timeout=5, embedding_query_timeout=5.0)
        app = create_app(settings, store=store, auth=auth, retrieval=Retrieval(store, settings, Mock(embed=AsyncMock(side_effect=stalled))))
        with self.open(app) as client:
            headers = {'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'}
            client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}}})
            for number, name in ((2, 'search'), (3, 'context')):
                started = time.monotonic()
                call = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': number, 'method': 'tools/call', 'params': {'name': name, 'arguments': {'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic'], 'semantic_budget_ms': 120}}})
                self.assertLessEqual(time.monotonic() - started, 0.12 + 0.5)
                result = call.json()['result']
                self.assertFalse(result.get('isError'), result)
                content = result.get('structuredContent') or json.loads(result['content'][0]['text'])
                content = content.get('result', content)
                self.assertEqual(content['degraded'], {'layer': 'semantic', 'reason': 'timeout'})
                self.assertEqual([item['item_id'] for item in content['items']], ['lex'])
            for bad in (0, 600001, True, '1100'):
                call = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': 'fencing', 'semantic_budget_ms': bad}}})
                result = call.json().get('result', {})
                self.assertTrue(result.get('isError') or 'error' in call.json(), (bad, call.text))

    def test_ca33_degraded_is_an_optional_field_of_the_exported_search_result(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('kairos_export_contracts_degraded', Path(__file__).parents[3] / 'scripts' / 'export-contracts.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        exported = module.contracts()
        schemas = (exported['kairos-mcp.json']['result_schemas']['search'], exported['memory-platform.openapi.json']['components']['schemas']['SearchResult'])
        for schema in schemas:
            self.assertIn('degraded', schema['properties'])
            self.assertNotIn('degraded', schema.get('required', []))
        self.assertEqual(sorted(schemas[0]['$defs']['Degraded']['required']), ['layer', 'reason'])


# Every class above runs a second time through kairos-mcp (T-48, CA-11): the same tests, the same results, the envelope of S-05 aside.
NativeMCPChain = chain_variant(NativeMCPTests)
SearchHitFieldsChain = chain_variant(SearchHitFieldsTests)
DegradedSemanticToolChain = chain_variant(DegradedSemanticToolTests)
