"""Test helpers of kairos-mcp: a simulated `/v1` server, the application in front of it, and a client that calls tools like an MCP client does."""
import json
from pathlib import Path

from starlette.testclient import TestClient

from stub_api import StubApi

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'contract' / 'kairos-mcp.json').read_text(encoding='utf-8'))
TOOLS = {tool['name']: tool for tool in CONTRACT['tools']}
BASE = 'http://localhost:8791'
TOKEN = 'kairos-synthetic-token-7f3a91c2d0b84e65'
BEARER = 'Bearer ' + TOKEN
HEADERS = {'Accept': 'application/json, text/event-stream', 'Authorization': BEARER}
PROJECT = 'proj-a'
UUID1 = '11111111-1111-4111-8111-111111111111'
UUID2 = '22222222-2222-4222-8222-222222222222'


class Result:
    """What a tool call gave: `error` (isError), the text of the first content block and the structured content."""

    def __init__(self, payload):
        self.raw = payload
        self.error = bool(payload.get('isError'))
        self.text = payload['content'][0]['text']
        self.structured = payload.get('structuredContent')

    def data(self):
        """The JSON the call returned, whatever its shape: the structured object, the text a `-> str` tool wraps in `result`, or the text."""
        structured = self.structured
        if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
            try:
                return json.loads(structured['result'])
            except ValueError:
                return structured['result']
        return structured if isinstance(structured, dict) else json.loads(self.text)


class Harness:
    """A stub `/v1`, the kairos-mcp application pointed at it and a test client; use as a context manager."""

    def __init__(self, routes=None, timeout=5.0, api_url=None, **options):
        from kairos_mcp.app import create_app
        self.stub = StubApi(routes)
        self.timeout, self.api_url, self.options, self.create_app = timeout, api_url, options, create_app
        self.client = None

    def __enter__(self):
        self.stub.__enter__()
        self.client = TestClient(self.create_app(api_url=self.api_url or self.stub.url, timeout=self.timeout, **self.options), base_url=BASE)
        self.client.__enter__()
        return self

    def __exit__(self, *exc):
        self.client.__exit__(*exc)
        self.stub.__exit__(*exc)

    def call(self, name, arguments=None, headers=None):
        response = self.client.post('/mcp/', headers=HEADERS if headers is None else headers, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments or {}}})
        assert response.status_code == 200, (response.status_code, response.text)
        return Result(response.json()['result'])

    def route(self, method, path, reply):
        self.stub.routes[(method, path)] = reply
