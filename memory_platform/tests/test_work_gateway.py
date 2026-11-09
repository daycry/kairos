"""Actual API and MCP share one durable, private work-state domain."""
import json
import unittest
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.test_store import create_core


def unpack(result):
    if result.get('isError'):
        raise AssertionError(result)
    text = next(v['text'] for v in result['content'] if v['type'] == 'text')
    return json.loads(text)


class WorkGatewayTests(unittest.TestCase):
    def test_mcp_persist_reload_http_retry_and_read_only_denial(self):
        store, admin, project = create_core()
        token = store.create_key(admin, {'name': 'fixture', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
        auth = Auth(store)
        headers = {'Authorization': 'Bearer '+token, 'Accept': 'application/json, text/event-stream'}
        app = create_app(Settings('unused'), store=store, auth=auth)
        change = {'list': 'Revisi\u00f3n: "\u00c1rbol" \U0001f333', 'fields': {'task': 'Conservar tags, con comas', 'status': 'doing'}, 'request_id': 'one-delivery', 'expected_version': 0}
        with TestClient(app, base_url='http://localhost:8790') as client:
            response = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'work_state_write', 'arguments': {'project': project, **change}}})
            self.assertEqual(response.status_code, 200)
            original = unpack(response.json()['result'])
            retry = client.post('/v1/projects/'+project+'/work-state', headers=headers, json=change)
            self.assertEqual(retry.json(), original)
        reloaded = create_app(Settings('unused'), store=store, auth=auth)
        with TestClient(reloaded, base_url='http://localhost:8790') as client:
            result = client.get('/v1/projects/'+project+'/work-state', headers=headers)
            self.assertEqual(result.json()['lists'][0]['list'], change['list'])
            self.assertEqual(result.json()['lists'][0]['state'], original['state'])
            reader = store.create_key(admin, {'name': 'reader', 'project_ids': [project], 'scopes': ['read']})['token']
            read_headers = {**headers, 'Authorization': 'Bearer '+reader}
            self.assertEqual(client.post('/v1/projects/'+project+'/work-state', headers=read_headers, json={**change, 'request_id': 'other'}).status_code, 403)
            self.assertEqual(client.get('/v1/projects/'+project+'/work-state', headers=read_headers).status_code, 200)
            self.assertEqual(client.get('/v1/projects/unknown-project/work-state', headers=read_headers).status_code, 404)
            self.assertEqual(client.post('/v1/projects/'+project+'/work-state', headers=read_headers, json={**change, 'fields': []}).status_code, 422)

    def test_corpus_query_history_requires_write_permission(self):
        from memory_platform.agent_store import AgentStore
        from memory_platform.errors import Forbidden
        store, actor, project = create_core()
        service = AgentStore(store)
        service.build_corpus(actor, project, 'empty')
        service.prime_corpus(actor, project, 'empty')
        reader = Auth(store).authenticate_bearer(store.create_key(actor, {'name': 'reader', 'project_ids': [project], 'scopes': ['read']})['token'])
        with self.assertRaises(Forbidden):
            service.query_corpus(reader, project, 'empty', 'question')
