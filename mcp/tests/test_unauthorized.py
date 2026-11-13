"""A credential that `/v1` refuses is a 401 of the MCP endpoint, as with the internal MCP, and not a successful call carrying an error (T-48, CA-12).

kairos-mcp does not know which tokens are valid: it learns it from the first answer of `/v1`. When that answer is 401 the HTTP response of the MCP request
becomes the 401 the internal MCP gives (same body), so a client re-authenticates instead of reading a tool error; any other refusal stays a tool error.
"""
import unittest

from support import BEARER, HEADERS, PROJECT, UUID1, Harness

UNAUTHORIZED = (401, {'error': {'code': 'unauthorized', 'message': 'Authentication required'}, 'request_id': 'r1'})
BODY = {'error': {'code': 'unauthorized', 'message': 'Authentication required'}, 'request_id': ''}


def rpc(harness, name, arguments=None, headers=None):
    return harness.client.post('/mcp/', headers=headers or HEADERS, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                                          'params': {'name': name, 'arguments': arguments or {}}})


class UpstreamUnauthorizedTests(unittest.TestCase):
    def test_a_401_from_the_api_is_a_401_of_the_endpoint_with_the_body_of_the_internal_mcp(self):
        with Harness({('GET', '/v1/projects'): UNAUTHORIZED}) as harness:
            response = rpc(harness, 'projects')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), BODY)

    def test_a_refusal_that_is_not_a_401_stays_a_tool_error_with_status_200(self):
        with Harness({('GET', '/v1/projects'): (403, {'error': {'code': 'forbidden', 'message': 'Operation not permitted'}})}) as harness:
            response = rpc(harness, 'projects')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['result']['isError'])

    def test_the_decision_belongs_to_its_request_one_401_does_not_poison_the_next_call(self):
        replies = iter([UNAUTHORIZED, (200, {'projects': []})])
        with Harness({('GET', '/v1/projects'): lambda request: next(replies)}) as harness:
            self.assertEqual(rpc(harness, 'projects').status_code, 401)
            second = rpc(harness, 'projects')
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['result'].get('isError'))

    def test_a_401_on_a_later_step_of_a_composition_is_the_401_of_the_endpoint(self):
        routes = {('GET', '/v1/events/' + UUID1): (200, {'status': 'accepted', 'jobs': ['j1']}), ('GET', '/v1/jobs/j1'): UNAUTHORIZED}
        with Harness(routes) as harness:
            response = rpc(harness, 'event_status', {'event_id': UUID1})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), BODY)

    def test_the_credential_the_api_refused_is_never_in_the_answer(self):
        with Harness({('GET', '/v1/projects'): UNAUTHORIZED}) as harness:
            response = rpc(harness, 'projects')
        self.assertNotIn(BEARER.split()[1], response.text)


if __name__ == '__main__':
    unittest.main()
