"""T-51 (CA-27, P-07): the internal MCP is deprecated for one version. Mounted (the default) every response of `/mcp` carries `Deprecation` and `Sunset`
and one `mcp_legacy_used` event without data of the user; with `MEMORY_MOUNT_MCP=0` nothing is mounted and `/mcp` answers 404 at every sub-route."""
import io
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from memory_platform import observability
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.errors import Unauthorized

SECRET = 'legacy-secret-bearer-value'
INIT = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '1'}}}
HEADERS = {'Authorization': 'Bearer ' + SECRET, 'Accept': 'application/json, text/event-stream'}


def build(settings=None):
    auth = Mock()
    auth.authenticate_bearer.return_value = {'id': 'test', 'credential_type': 'bearer'}
    auth.authenticate_session.side_effect = Unauthorized()
    retrieval = Mock(search=AsyncMock(return_value={'items': [], 'backends': {}, 'partial': False}))
    return create_app(settings or Settings('unused'), store=Mock(), auth=auth, retrieval=retrieval)


class LegacyHeadersTests(unittest.TestCase):
    def capture(self):
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        return stream

    def test_default_mounts_and_marks_every_response(self):
        with TestClient(build(), base_url='http://localhost:8790') as client:
            ok = client.post('/mcp/', headers=HEADERS, json=INIT)
            denied = client.post('/mcp/', json=INIT)
            bad = client.post('/mcp/', headers=HEADERS, content=b'{not json')
            other = client.get('/mcp/nowhere', headers=HEADERS)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(denied.status_code, 401)
        for response in (ok, denied, bad, other):
            self.assertEqual(response.headers.get('deprecation'), 'true', response.status_code)
            self.assertIn('0.5.0', response.headers.get('sunset', ''), response.status_code)

    def test_streaming_responses_carry_the_headers(self):
        with TestClient(build(), base_url='http://localhost:8790') as client:
            with client.stream('POST', '/mcp/', headers={**HEADERS, 'Accept': 'text/event-stream, application/json'}, json=INIT) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get('deprecation'), 'true')
                self.assertIn('0.5.0', response.headers.get('sunset', ''))
                response.read()

    def test_the_rest_of_the_api_is_not_marked(self):
        with TestClient(build(), base_url='http://localhost:8790') as client:
            response = client.get('/health/live')
        self.assertNotIn('deprecation', response.headers)
        self.assertNotIn('sunset', response.headers)

    def test_log_event_has_no_credential_arguments_or_content(self):
        stream = self.capture()
        call = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': 'private-question-text'}}}
        with TestClient(build(), base_url='http://localhost:8790') as client:
            client.post('/mcp/', headers=HEADERS, json=INIT)
            client.post('/mcp/', headers=HEADERS, json=call)
        text = stream.getvalue()
        events = [json.loads(line) for line in text.splitlines() if line.strip()]
        legacy = [e for e in events if e.get('event') == 'mcp_legacy_used']
        self.assertEqual(len(legacy), 2, text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('private-question-text', text)
        for entry in legacy:
            self.assertEqual(entry['level'], 'info')
            self.assertEqual(set(entry) - {'ts', 'level', 'event', 'request_id'}, {'method', 'status'}, entry)

    def test_unmounted_is_404_at_every_sub_route_and_never_logs(self):
        stream = self.capture()
        with TestClient(build(Settings('unused', mount_mcp=False)), base_url='http://localhost:8790') as client:
            for path in ('/mcp', '/mcp/', '/mcp/anything', '/mcp/a/b'):
                for method in ('GET', 'POST', 'DELETE'):
                    response = client.request(method, path, headers=HEADERS, json=INIT if method == 'POST' else None)
                    self.assertEqual(response.status_code, 404, (method, path))
                    self.assertNotIn('deprecation', response.headers)
        self.assertNotIn('mcp_legacy_used', stream.getvalue())

    def test_switch_reads_the_environment_and_fails_closed(self):
        base = {'MEMORY_DSN': 'postgresql://x'}
        for value, expected in (({}, True), ({'MEMORY_MOUNT_MCP': '1'}, True), ({'MEMORY_MOUNT_MCP': '0'}, False)):
            with patch.dict(os.environ, {**base, **value}, clear=True):
                self.assertIs(Settings.from_env().mount_mcp, expected, value)
        with patch.dict(os.environ, {**base, 'MEMORY_MOUNT_MCP': 'maybe'}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()
