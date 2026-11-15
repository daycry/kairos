"""HTTP/MCP use the same persisted corpus answer and exact request identity."""
import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.chain_harness import ChainMode, chain_variant


class CorpusGatewayTests(ChainMode, unittest.TestCase):
    def test_selection_prime_answer_mcp_retry_reload_and_rebuild(self):
        store, actor, project = create_core()
        source = event(project, generate=False, payload={'title': 'Fencing', 'content': 'Check the fencing token before publication.'})
        store.ingest_event(actor, source)
        key = store.create_key(actor, {'name': 'writer', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
        headers = {'Authorization': 'Bearer '+key, 'Accept': 'application/json, text/event-stream'}
        packets = []
        class Provider:
            async def answer(self, messages, sources, limits):
                packets.append(messages)
                return {'answer': 'Check the fencing token.', 'citations': [{'ref': sources[0]['ref'], 'quote': 'Check the fencing token'}],
                        'input_tokens': 200, 'output_tokens': 100}
        settings = Settings('unused', llm_model='configured-fixture-model', corpus_answer_enabled=True)
        base = '/v1/projects/'+project+'/corpora'
        with patch('memory_platform.corpus_answers.NativeCorpusProvider', return_value=Provider()):
            app = create_app(settings, store=store)
            with self.open(app) as client:
                built = client.post(base, headers=headers, json={'name': 'selected', 'query': 'fencing'})
                self.assertEqual(built.status_code, 200, built.text)
                self.assertEqual(client.get(base, headers=headers).json()['items'][0]['name'], 'selected')
                primed = client.post(base+'/selected/prime', headers=headers, json={'fresh': False}).json()
                intent = {'question': 'fencing', 'request_id': 'same-operation', 'expected_session_id': primed['session_id'], 'expected_generation': primed['version']}
                result = client.post(base+'/selected/answers', headers=headers, json=intent)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['status'], 'completed')
                self.assertEqual(result.json()['model'], 'configured-fixture-model')
                retry = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                    'params': {'name': 'corpus_answer', 'arguments': {'project': project, 'name': 'selected', **intent}}})
                self.assertFalse(retry.json()['result'].get('isError'), retry.text)
                receipt = json.loads(retry.json()['result']['content'][0]['text'])
                self.assertEqual(receipt, result.json())
                self.assertEqual(len(packets), 1)
                reloaded = self.open(create_app(settings, store=store))
                with reloaded:
                    self.assertEqual(reloaded.get(base+'/selected/answers/same-operation', headers=headers).json(), result.json())
                store.ingest_event(actor, event(project, generate=False, payload={'title': 'New fencing', 'content': 'A new fencing source.'}))
                rebuilt = client.post(base+'/selected/rebuild', headers=headers, json={'force': False, 'expected_version': primed['version']})
                self.assertEqual(rebuilt.status_code, 200, rebuilt.text)
                self.assertGreater(rebuilt.json()['version'], primed['version'])
                self.assertEqual(client.get(base+'/selected/answers/same-operation', headers=headers).status_code, 409)
                self.assertEqual(client.post(base+'/selected/rebuild', headers=headers, json={'force': False, 'expected_version': primed['version']}).status_code, 409)
                reader = store.create_key(actor, {'name': 'reader', 'project_ids': [project], 'scopes': ['read']})['token']
                self.assertEqual(client.get(base, headers={'Authorization': 'Bearer '+reader}).status_code, 200)
                self.assertEqual(client.post(base+'/selected/prime', headers={'Authorization': 'Bearer '+reader}, json={'fresh': True}).status_code, 403)

    def test_default_server_refuses_answers_over_http_and_mcp_without_a_provider_call(self):
        store, actor, project = create_core()
        store.ingest_event(actor, event(project, generate=False, payload={'title': 'Fencing', 'content': 'Check the fencing token before publication.'}))
        key = store.create_key(actor, {'name': 'writer', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
        headers = {'Authorization': 'Bearer '+key, 'Accept': 'application/json, text/event-stream'}
        base = '/v1/projects/'+project+'/corpora'
        calls = []
        class Provider:
            async def answer(self, messages, sources, limits):
                calls.append(messages)
        with patch('memory_platform.corpus_answers.NativeCorpusProvider', return_value=Provider()):
            with self.open(create_app(Settings('unused'), store=store)) as client:
                client.post(base, headers=headers, json={'name': 'selected', 'query': 'fencing'})
                primed = client.post(base+'/selected/prime', headers=headers, json={'fresh': False}).json()
                intent = {'question': 'fencing', 'request_id': 'off-operation', 'expected_session_id': primed['session_id'], 'expected_generation': primed['version']}
                refused = client.post(base+'/selected/answers', headers=headers, json=intent)
                self.assertEqual(refused.status_code, 403, refused.text)
                self.assertEqual(refused.json()['error']['code'], 'corpus_answer_disabled')
                listed = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).json()['result']['tools']
                self.assertIn('corpus_answer', [tool['name'] for tool in listed])  # still listed: the 34-tool contract is unchanged
                called = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                    'params': {'name': 'corpus_answer', 'arguments': {'project': project, 'name': 'selected', **intent}}}).json()['result']
                self.assertTrue(called['isError'])
                self.assertIn('corpus_answer_disabled', called['content'][0]['text'])
                status = client.get(base+'/selected/answers/off-operation', headers=headers)
                self.assertEqual(status.status_code, 404)  # nothing was reserved, so there is nothing to read
        self.assertEqual(calls, [])


# Every class above runs a second time through kairos-mcp (T-48, CA-11): the same tests, the same results, the envelope of S-05 aside.
CorpusGatewayChain = chain_variant(CorpusGatewayTests)
