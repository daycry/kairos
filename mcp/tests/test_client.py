"""T-37: the `/v1` client forwards the caller's credential and nothing else, translates refusals and failures, and logs no secret (CA-12)."""
import asyncio
import io
import json
import logging
import time
import unittest

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from stub_api import Reply, StubApi

TOKEN = 'kairos-synthetic-token-7f3a91c2d0b84e65'
BEARER = 'Bearer ' + TOKEN
DOMAIN_404 = (404, {'error': {'code': 'not_found', 'message': 'Resource not found'}, 'request_id': 'r1'})


def run(coroutine):
    return asyncio.run(coroutine)


class RefusalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from kairos_mcp.client import ApiClient
        self.make = ApiClient

    async def call(self, stub, **options):
        client = self.make(stub.url, **options)
        try:
            return await client.send('GET', '/v1/projects', BEARER)
        finally:
            await client.aclose()

    async def test_a_4xx_domain_error_fails_with_the_message_of_the_server(self):
        from kairos_mcp.client import fail
        from kairos_mcp.errors import ToolError
        with StubApi({('GET', '/v1/projects'): (403, {'error': {'code': 'forbidden', 'message': 'Operation not permitted'}})}) as stub:
            status, body = await self.call(stub)
        self.assertEqual(status, 403)
        with self.assertRaises(ToolError) as caught:
            fail(status, body)
        self.assertEqual(str(caught.exception), 'Operation not permitted')
        self.assertIsInstance(caught.exception, ValueError)

    async def test_success_returns_the_parsed_body_untouched(self):
        with StubApi({('GET', '/v1/projects'): (200, {'projects': [{'project_id': 'a'}]})}) as stub:
            self.assertEqual(await self.call(stub), (200, {'projects': [{'project_id': 'a'}]}))

    async def test_a_4xx_without_the_server_envelope_does_not_echo_what_it_said(self):
        from kairos_mcp.client import fail
        from kairos_mcp.errors import UNAVAILABLE, ToolError
        for reply in (Reply(404, raw=b'<html>nginx secret page</html>'), Reply(400, {'detail': 'x'}), Reply(401, None)):
            with self.subTest(reply=reply.status), StubApi({('GET', '/v1/projects'): reply}) as stub:
                status, body = await self.call(stub)
                with self.assertRaises(ToolError) as caught:
                    fail(status, body)
                self.assertEqual(str(caught.exception), UNAVAILABLE)

    async def test_a_5xx_is_the_generic_unavailable_message(self):
        from kairos_mcp.errors import UNAVAILABLE, ToolError
        generic = {'error': {'code': 'service_unavailable', 'message': 'Service is temporarily unavailable'}, 'request_id': 'x'}
        for reply in (Reply(500, None), Reply(502, raw=b'<html>bad gateway</html>'), Reply(503, generic), Reply(500, {'error': {'code': 'service_unavailable', 'message': 'db password is hunter2'}})):
            with self.subTest(status=reply.status), StubApi({('GET', '/v1/projects'): reply}) as stub:
                with self.assertRaises(ToolError) as caught:
                    await self.call(stub)
                self.assertEqual(str(caught.exception), UNAVAILABLE)

    async def test_a_5xx_that_is_a_domain_refusal_keeps_its_message_like_the_internal_mcp(self):
        # `semantic_deadline_exceeded` is a domain error with status 503 (store_vectors.py): the internal MCP shows its message.
        from kairos_mcp.client import fail
        from kairos_mcp.errors import ToolError
        refusal = {'error': {'code': 'semantic_deadline_exceeded', 'message': 'Semantic query exceeded its time budget'}}
        with StubApi({('GET', '/v1/projects'): (503, refusal)}) as stub:
            status, body = await self.call(stub)
        self.assertEqual(status, 503)
        with self.assertRaises(ToolError) as caught:
            fail(status, body)
        self.assertEqual(str(caught.exception), 'Semantic query exceeded its time budget')

    async def test_a_deadline_that_passes_is_the_generic_message_and_bounded(self):
        from kairos_mcp.errors import UNAVAILABLE, ToolError
        with StubApi({('GET', '/v1/projects'): Reply(200, {'projects': []}, delay=3.0)}) as stub:
            started = time.monotonic()
            with self.assertRaises(ToolError) as caught:
                await self.call(stub, timeout=0.3)
            elapsed = time.monotonic() - started
        self.assertEqual(str(caught.exception), UNAVAILABLE)
        self.assertLess(elapsed, 2.0)  # cut at 0.3 s, long before the 3 s the upstream takes

    async def test_a_dropped_connection_is_the_generic_message(self):
        from kairos_mcp.client import ApiClient
        from kairos_mcp.errors import UNAVAILABLE, ToolError
        with StubApi() as stub:
            url = stub.url
        client = ApiClient(url, timeout=1.0)  # the stub is closed: nothing listens
        with self.assertRaises(ToolError) as caught:
            await client.send('GET', '/v1/projects', BEARER)
        self.assertEqual(str(caught.exception), UNAVAILABLE)
        await client.aclose()

    async def test_a_redirect_is_not_followed_so_the_credential_never_leaves(self):
        from kairos_mcp.errors import UNAVAILABLE, ToolError
        routes = {('GET', '/v1/projects'): Reply(302, None, headers={'Location': '/elsewhere'}), ('GET', '/elsewhere'): (200, {'leaked': True})}
        with StubApi(routes) as stub:
            with self.assertRaises(ToolError) as caught:
                await self.call(stub)
            self.assertEqual(str(caught.exception), UNAVAILABLE)
            self.assertEqual(stub.calls(route='/elsewhere'), [])

    async def test_an_answer_over_the_size_bound_is_refused(self):
        import kairos_mcp.client as module
        from kairos_mcp.errors import ToolError
        saved = module.MAX_RESPONSE_BYTES
        module.MAX_RESPONSE_BYTES = 1000
        try:
            with StubApi({('GET', '/v1/projects'): (200, {'text': 'x' * 5000})}) as stub:
                with self.assertRaises(ToolError):
                    await self.call(stub)
        finally:
            module.MAX_RESPONSE_BYTES = saved


class CredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_authorization_header_is_forwarded_as_it_came(self):
        from kairos_mcp.client import ApiClient
        with StubApi({('GET', '/v1/projects'): (200, {'projects': []})}) as stub:
            client = ApiClient(stub.url)
            await client.send('GET', '/v1/projects', 'bEaReR ' + TOKEN)  # the client does not normalise the scheme either
            await client.aclose()
        self.assertEqual(stub.requests[0].headers['authorization'], 'bEaReR ' + TOKEN)

    async def test_each_call_carries_its_own_credential_and_none_is_kept(self):
        from kairos_mcp.client import ApiClient
        with StubApi({('GET', '/v1/projects'): (200, {'projects': []})}) as stub:
            client = ApiClient(stub.url)
            await client.send('GET', '/v1/projects', 'Bearer first-caller')
            await client.send('GET', '/v1/projects', 'Bearer second-caller')
            self.assertNotIn('authorization', {key.lower() for key in client._http.headers})
            await client.aclose()
        self.assertEqual([r.headers['authorization'] for r in stub.requests], ['Bearer first-caller', 'Bearer second-caller'])

    async def test_the_token_never_appears_in_the_logs(self):
        from kairos_mcp.client import ApiClient
        from kairos_mcp.logs import configure_logging
        stream = io.StringIO()
        configure_logging(stream, level=logging.DEBUG)
        capture = io.StringIO()
        handler = logging.StreamHandler(capture)
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)  # every library at its most talkative
        try:
            routes = {('GET', '/v1/projects'): (200, {'projects': []}), ('GET', '/v1/boom'): (500, None), ('GET', '/v1/slow'): Reply(200, {}, delay=1.0)}
            with StubApi(routes) as stub:
                client = ApiClient(stub.url, timeout=0.3)
                await client.send('GET', '/v1/projects', BEARER)
                for path in ('/v1/boom', '/v1/slow'):
                    with self.assertRaises(ValueError):
                        await client.send('GET', path, BEARER)
                await client.aclose()
            with self.assertRaises(ValueError):
                await ApiClient('http://127.0.0.1:9', timeout=0.3).send('GET', '/v1/projects', BEARER)
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        written = stream.getvalue() + capture.getvalue()
        self.assertIn('api_unavailable', stream.getvalue())  # the failures were logged...
        self.assertEqual(written.count(TOKEN), 0)  # ...without the credential
        for line in stream.getvalue().splitlines():
            json.loads(line)  # one JSON object per line


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_reuse_one_persistent_connection(self):
        from kairos_mcp.client import ApiClient
        with StubApi({('GET', '/v1/projects'): (200, {'projects': []})}) as stub:
            client = ApiClient(stub.url)
            for _ in range(5):
                await client.send('GET', '/v1/projects', BEARER)
            await client.aclose()
        self.assertEqual(len(stub.requests), 5)
        self.assertEqual(stub.connections, 1)

    async def test_query_and_json_body_are_sent(self):
        from kairos_mcp.client import ApiClient
        with StubApi({('POST', '/v1/search'): (200, {'items': []})}) as stub:
            client = ApiClient(stub.url)
            await client.send('POST', '/v1/search', BEARER, params={'a': 'b c'}, body={'q': 'x', 'n': 1})
            await client.aclose()
        request = stub.requests[0]
        self.assertEqual(request.query, {'a': ['b c']})
        self.assertEqual(request.body, {'q': 'x', 'n': 1})


class ConfigTests(unittest.TestCase):
    def test_timeout_defaults_to_30_seconds_and_url_is_required(self):
        from kairos_mcp.config import from_env
        config = from_env({'KAIROS_API_URL': 'http://memory-api:8790/'})
        self.assertEqual((config.api_url, config.timeout), ('http://memory-api:8790', 30.0))
        self.assertEqual(from_env({'KAIROS_API_URL': 'http://x', 'KAIROS_API_TIMEOUT': '2.5'}).timeout, 2.5)

    def test_bad_values_name_the_variable(self):
        from kairos_mcp.config import from_env
        for env, name in (({}, 'KAIROS_API_URL'), ({'KAIROS_API_URL': 'memory-api'}, 'KAIROS_API_URL'),
                          ({'KAIROS_API_URL': 'http://x', 'KAIROS_API_TIMEOUT': 'soon'}, 'KAIROS_API_TIMEOUT'),
                          ({'KAIROS_API_URL': 'http://x', 'KAIROS_API_TIMEOUT': '0'}, 'KAIROS_API_TIMEOUT'),
                          ({'KAIROS_API_URL': 'http://x', 'KAIROS_API_TIMEOUT': '-1'}, 'KAIROS_API_TIMEOUT')):
            with self.subTest(env=env), self.assertRaises(ValueError) as caught:
                from_env(env)
            self.assertIn(name, str(caught.exception))


class BearerGateTests(unittest.TestCase):
    """No credential, or a scheme other than Bearer: 401 with today's body and not one call to `/v1` (CA-12)."""

    def gated(self):
        from kairos_mcp.auth import RequireBearer

        async def inner(request):
            return PlainTextResponse('inside')
        return RequireBearer(Starlette(routes=[Route('/mcp/', inner, methods=['GET', 'POST'])]))

    def test_without_authorization_or_with_another_scheme_the_answer_is_401_and_nothing_is_called(self):
        with StubApi() as stub:
            with TestClient(self.gated()) as client:
                for headers in ({}, {'Authorization': ''}, {'Authorization': 'Basic ' + TOKEN}, {'Authorization': 'Token ' + TOKEN},
                                {'Authorization': 'Bearer'}, {'Authorization': 'Bearer '}):
                    with self.subTest(headers=headers):
                        response = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
                        self.assertEqual(response.status_code, 401)
                        self.assertEqual(response.json(), {'error': {'code': 'unauthorized', 'message': 'Authentication required'}, 'request_id': ''})
            self.assertEqual(stub.requests, [])

    def test_a_bearer_credential_reaches_the_application_in_any_case_of_the_scheme(self):
        with TestClient(self.gated()) as client:
            for scheme in ('Bearer', 'bearer', 'BEARER'):
                response = client.post('/mcp/', headers={'Authorization': scheme + ' ' + TOKEN}, json={})
                self.assertEqual((response.status_code, response.text), (200, 'inside'))

    def test_the_credential_of_a_request_is_visible_only_inside_it(self):
        from kairos_mcp.auth import current_authorization
        self.assertIsNone(current_authorization())
        seen = []

        async def inner(request):
            seen.append(current_authorization())
            return PlainTextResponse('ok')
        from kairos_mcp.auth import RequireBearer
        with TestClient(RequireBearer(Starlette(routes=[Route('/mcp/', inner, methods=['POST'])]))) as client:
            client.post('/mcp/', headers={'Authorization': BEARER}, json={})
        self.assertEqual(seen, [BEARER])
        self.assertIsNone(current_authorization())


if __name__ == '__main__':
    unittest.main()
