"""The MCP endpoint of kairos-mcp bounds the request body like the server does (T-48): a body over the limit is a 413 before anything is parsed or called."""
import unittest

from support import BASE, HEADERS, Harness, PROJECT, UUID1


class BodyLimitTests(unittest.TestCase):
    def post(self, harness, size, headers=None):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': [PROJECT], 'q': 'x' * size}}}
        return harness.client.post('/mcp/', headers=headers or HEADERS, json=body)

    def test_a_body_over_the_limit_is_a_413_with_the_servers_error_and_no_call_to_the_api(self):
        with Harness({}, max_body_bytes=2048) as harness:
            response = self.post(harness, 5000)
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()['error'], {'code': 'body_too_large', 'message': 'Request body exceeds limit'})
            self.assertEqual(harness.stub.requests, [])

    def test_a_body_within_the_limit_is_served(self):
        with Harness({('POST', '/v1/search'): (200, {'items': []})}, max_body_bytes=2048) as harness:
            self.assertEqual(self.post(harness, 100).status_code, 200)
            self.assertEqual(len(harness.stub.requests), 1)

    def test_a_chunked_body_is_counted_while_it_arrives_not_trusted_from_its_header(self):
        def chunks():
            for _ in range(10):
                yield b'x' * 1000
        with Harness({}, max_body_bytes=2048) as harness:
            response = harness.client.post('/mcp/', headers={**HEADERS, 'Content-Type': 'application/json'}, content=chunks())
            self.assertEqual(response.status_code, 413)

    def test_the_default_limit_is_the_servers_262144_bytes(self):
        from kairos_mcp.config import DEFAULT_MAX_BODY_BYTES, from_env
        self.assertEqual(DEFAULT_MAX_BODY_BYTES, 262144)
        self.assertEqual(from_env({'KAIROS_API_URL': 'http://x'}).max_body_bytes, 262144)
        self.assertEqual(from_env({'KAIROS_API_URL': 'http://x', 'KAIROS_MAX_BODY_BYTES': '1000'}).max_body_bytes, 1000)
        for bad in ('0', '-5', 'lots', '999999999999'):
            with self.subTest(value=bad), self.assertRaises(ValueError) as caught:
                from_env({'KAIROS_API_URL': 'http://x', 'KAIROS_MAX_BODY_BYTES': bad})
            self.assertIn('KAIROS_MAX_BODY_BYTES', str(caught.exception))

    def test_the_liveness_probe_is_not_affected(self):
        with Harness({}, max_body_bytes=16) as harness:
            self.assertEqual(harness.client.get('/health/live').status_code, 200)


if __name__ == '__main__':
    unittest.main()
