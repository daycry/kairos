"""HTTP and MCP exercise the same observation and shared-work transactions."""
import unittest

from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.test_work_gateway import unpack


class ExtendedGatewayTests(unittest.TestCase):
    def test_mcp_http_observation_and_team_retry_share_receipts(self):
        store, actor, project = create_core()
        key = store.create_key(actor, {'name': 'extended-fixture', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
        headers = {'Authorization': 'Bearer '+key, 'Accept': 'application/json, text/event-stream'}
        app = create_app(Settings('unused'), store=store, auth=Auth(store))
        with TestClient(app, base_url='http://localhost:8790') as client:
            def tool(name, arguments):
                response = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
                self.assertEqual(response.status_code, 200)
                return unpack(response.json()['result'])
            data = event(project, generate=False)
            receipt = tool('observation_add', {'event': data})
            self.assertEqual(client.post('/v1/observations', headers=headers, json=data).json(), receipt)
            change = {'list': 'shared', 'fields': {'task': 'Conservar t\u00edtulos, tags', 'status': 'doing'}, 'request_id': 'shared-retry', 'expected_version': 0}
            first = tool('team_work_write', {'project': project, **change})
            response = client.post('/v1/projects/'+project+'/team-work', headers=headers, json=change)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), first)
            result = client.get('/v1/projects/'+project+'/team-work', headers=headers)
            self.assertEqual(result.json()['lists'][0]['state'], first['state'])
            reader = store.create_key(actor, {'name': 'extended-reader', 'project_ids': [project], 'scopes': ['read']})['token']
            read_headers = {**headers, 'Authorization': 'Bearer '+reader}
            self.assertEqual(client.post('/v1/observations', headers=read_headers, json=data).status_code, 403)
            self.assertEqual(client.post('/v1/projects/'+project+'/team-work', headers=read_headers, json={**change, 'request_id': 'denied'}).status_code, 403)
            self.assertEqual(client.get('/v1/projects/'+project+'/team-work', headers=read_headers).status_code, 200)


if __name__ == '__main__':
    unittest.main()
