"""T-47 (CA-11): the chain kairos-mcp -> server runs in process over an isolated PostgreSQL, with the credentials the tests already use.

Smoke case of the chain: `projects`, `remember` and `search` through kairos-mcp (which only speaks `/v1`) give what the internal MCP gives for the same
call, envelope aside. The harness lives here, on the server side of the repository (`chain_harness.py`), so that `mcp/` imports nothing of the server.
"""
import json
from pathlib import Path
import unittest

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.chain_harness import ChainClient, strip_envelope
from memory_platform.tests.test_store import create_core, event

ORIGIN = 'http://localhost:8790'
ROOT = Path(__file__).resolve().parents[3]


def parsed(result):
    """The data of a tool result as a client reads it: the structured object, or the JSON text a `-> str` tool wraps in `result`."""
    structured = result.get('structuredContent')
    if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
        return json.loads(structured['result'])
    return structured if isinstance(structured, dict) else json.loads(result['content'][0]['text'])


class ChainSmokeTests(unittest.TestCase):
    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        key = self.store.create_key(self.admin, {'name': 'chain', 'project_ids': [self.pid], 'scopes': ['read', 'write']})['token']
        self.headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json, text/event-stream'}
        self.app = create_app(Settings('unused', allowed_origins=[ORIGIN]), store=self.store, auth=Auth(self.store, [ORIGIN]))

    def call(self, client, name, arguments=None, headers=None):
        response = client.post('/mcp/', headers=headers or self.headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                                              'params': {'name': name, 'arguments': arguments or {}}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['result']

    def test_projects_remember_and_search_through_the_chain_equal_the_internal_mcp(self):
        item = event(self.pid, generate=False, payload={'title': 'Chain note', 'content': 'The chain carries the fencing token', 'source': {'uri': 'fixture://chain'}})
        with ChainClient(self.app, base_url=ORIGIN) as client:
            via_chain = self.call(client, 'projects')
            self.assertFalse(via_chain.get('isError'), via_chain)
            projects = parsed(via_chain)
            self.assertIn(self.pid, [project['id'] for project in projects['projects']])
            self.assertIs(projects['untrusted'], True)
            remembered = self.call(client, 'remember', {'event': item})
            self.assertFalse(remembered.get('isError'), remembered)
            self.assertEqual(parsed(remembered)['status'], 'accepted')
            arguments = {'project_ids': [self.pid], 'q': 'fencing', 'layers': ['episodic'], 'semantic': False}
            found = self.call(client, 'search', arguments)
            self.assertFalse(found.get('isError'), found)
            self.assertEqual([hit['item_id'] for hit in parsed(found)['items']], [item['item_id']])
            direct = self.call(client.server_mcp, 'search', arguments)  # the same call on the server's own MCP
            self.assertEqual(strip_envelope(parsed(found)), strip_envelope(parsed(direct)))

    def test_a_key_without_access_fails_with_the_message_of_the_internal_mcp(self):
        outsider = self.store.create_key(self.admin, {'name': 'reader', 'project_ids': [self.pid], 'scopes': ['read']})['token']
        headers = {**self.headers, 'Authorization': 'Bearer ' + outsider}
        item = event(self.pid, generate=False)
        with ChainClient(self.app, base_url=ORIGIN) as client:
            chain = self.call(client, 'remember', {'event': item}, headers)
            direct = self.call(client.server_mcp, 'remember', {'event': item}, headers)
        self.assertTrue(chain['isError'] and direct['isError'])
        self.assertEqual(chain['content'][0]['text'], direct['content'][0]['text'])

    def test_without_a_credential_the_chain_answers_401_without_reaching_the_server(self):
        with ChainClient(self.app, base_url=ORIGIN) as client:
            response = client.post('/mcp/', headers={'Accept': self.headers['Accept']}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'unauthorized')


class ComponentIsolationTests(unittest.TestCase):
    """CA-08 from the server side: the component's sources never import the server package (a split string: this file may name it)."""

    def test_mcp_sources_do_not_name_the_server_package(self):
        package = 'memory' + '_platform'
        found = [str(path.relative_to(ROOT)) for path in (ROOT / 'mcp').rglob('*.py') if package in path.read_text(encoding='utf-8')]
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
