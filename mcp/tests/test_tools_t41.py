"""T-41 (CA-10, CA-11): the 12 tools of the `mcp.py` group become the `/v1` request their `x-kairos-endpoint` declares."""
import json
import unittest

from kairos_mcp.budget import DETAIL_BYTES, TRUNCATION
from support import BEARER, PROJECT, TOOLS, UUID1, UUID2, Harness
from tool_cases import Case, exercise

P = '/v1/projects/' + PROJECT
EVENT = {'event_id': UUID1, 'project_id': PROJECT, 'session_id': 's', 'agent_id': 'a', 'event_type': 'note', 'occurred_at': '2026-11-04T10:00:00Z',
         'item_id': UUID2, 'version': 1, 'payload': {'title': 'T', 'content': 'C'}}
DOCUMENT = {'document_id': UUID1, 'version': 1, 'title': 'Doc', 'content': 'text', 'source': {'uri': 'fixture://d', 'sha256': 'a' * 64},
            'validation': {'status': 'validated', 'evidence': ['synthetic evidence'], 'validated_by': 'test'}}
GROUP = ['projects', 'remember', 'publish_document', 'document_status', 'document_manifest', 'revoke_document', 'search', 'details',
         'context', 'timeline', 'event_status', 'capture_policy']

CASES = [
    Case('projects', {}, 'GET', '/v1/projects', {'projects': [{'project_id': PROJECT}]}),
    Case('remember', {'event': EVENT}, 'POST', '/v1/events', {'receipt': {'status': 'accepted'}, 'jobs': []}, body=EVENT, status=202),
    Case('publish_document', {'project_id': PROJECT, 'document': DOCUMENT}, 'POST', P + '/documents', {'status': 'accepted'}, body=DOCUMENT, status=202),
    Case('document_status', {'project_id': PROJECT, 'document_id': UUID1}, 'GET', P + '/documents/' + UUID1, {'version': 1, 'jobs': []}),
    Case('document_manifest', {'project_id': PROJECT, 'limit': 5, 'cursor': 'abc'}, 'GET', P + '/manifest', {'items': [], 'next_cursor': None},
         query={'limit': ['5'], 'cursor': ['abc']}),
    Case('revoke_document', {'project_id': PROJECT, 'document_id': UUID1, 'version': 2}, 'DELETE', P + '/documents/' + UUID1, {'status': 'accepted'},
         query={'version': ['2']}, status=202),
    Case('search', {'project_ids': [PROJECT], 'q': 'fencing', 'layers': ['episodic'], 'limit': 7, 'semantic': False, 'semantic_budget_ms': 400},
         'POST', '/v1/search', {'items': [], 'backends': {}, 'partial': False},
         body={'project_ids': [PROJECT], 'q': 'fencing', 'layers': ['episodic'], 'limit': 7, 'semantic': False, 'semantic_budget_ms': 400}),
    Case('details', {'refs': ['episodic:a:b:1'], 'max_chars': 500}, 'POST', '/v1/details', {'items': [], 'truncated': False},
         body={'refs': ['episodic:a:b:1'], 'max_chars': 500}),
    Case('context', {'project_ids': [PROJECT], 'q': 'x', 'match_mode': 'any', 'exclude_categories': ['draft']}, 'POST', '/v1/context',
         {'context': '', 'warnings': []}, body={'project_ids': [PROJECT], 'q': 'x', 'match_mode': 'any', 'exclude_categories': ['draft']}),
    Case('timeline', {'project_ids': [PROJECT], 'anchor_ref': 'episodic:a:b:1', 'limit': 3}, 'POST', '/v1/timeline', {'items': []},
         body={'project_ids': [PROJECT], 'anchor_ref': 'episodic:a:b:1', 'limit': 3}),
    Case('event_status', {'event_id': UUID1, 'project_id': PROJECT}, 'GET', P + '/events/' + UUID1 + '/status',
         {'receipt': {'status': 'accepted', 'jobs': []}, 'jobs': [], 'complete': True}),
    Case('capture_policy', {'project_id': PROJECT}, 'GET', P + '/capture-policy', {'project_id': PROJECT, 'capture_allowed': True}),
]


class GroupTests(unittest.TestCase):
    def test_the_cases_are_exactly_the_12_tools_of_the_group(self):
        self.assertEqual(sorted(case.tool for case in CASES), sorted(GROUP))
        self.assertEqual(len(GROUP), 12)

    def test_each_tool_translates_succeeds_fails_and_degrades_as_the_internal_mcp_does(self):
        exercise(self, CASES)

    def test_a_null_argument_is_as_absent_as_an_omitted_one(self):
        with Harness({('GET', P + '/manifest'): (200, {'items': []})}) as harness:
            result = harness.call('document_manifest', {'project_id': PROJECT, 'cursor': None})
            self.assertFalse(result.error, result.text)
            self.assertEqual(harness.stub.requests[0].query, {})

    def test_a_path_value_is_encoded_in_full_and_the_query_value_is_not_double_encoded(self):
        with Harness({('GET', P + '/manifest'): (200, {'items': []})}) as harness:
            harness.call('document_manifest', {'project_id': PROJECT, 'cursor': 'a b&c=d/é'})
            self.assertEqual(harness.stub.requests[0].query, {'cursor': ['a b&c=d/é']})


class EventStatusWithoutProjectTests(unittest.TestCase):
    """`event_status` without `project_id` is the composition of the contract: the receipt, then each of its jobs, then the verdict."""

    def routes(self, states, receipt_status='accepted'):
        routes = {('GET', '/v1/events/' + UUID1): (200, {'status': receipt_status, 'jobs': ['j1', 'j2'][:len(states)]})}
        for number, state in enumerate(states, 1):
            routes[('GET', '/v1/jobs/j%d' % number)] = (200, {'id': 'j%d' % number, 'state': state})
        return routes

    def test_the_receipt_and_every_job_are_read_and_the_answer_is_composed(self):
        with Harness(self.routes(['succeeded', 'succeeded'])) as harness:
            result = harness.call('event_status', {'event_id': UUID1})
            self.assertFalse(result.error, result.text)
            data = result.data()
            self.assertEqual([request.route for request in harness.stub.requests], ['/v1/events/' + UUID1, '/v1/jobs/j1', '/v1/jobs/j2'])
            self.assertEqual((data['receipt']['status'], [job['state'] for job in data['jobs']], data['complete']), ('accepted', ['succeeded', 'succeeded'], True))

    def test_one_job_not_succeeded_or_a_superseded_receipt_is_never_complete(self):
        for states, status in ((['succeeded', 'running'], 'accepted'), (['succeeded'], 'superseded')):
            with self.subTest(states=states, status=status), Harness(self.routes(states, status)) as harness:
                self.assertIs(harness.call('event_status', {'event_id': UUID1}).data()['complete'], False)

    def test_a_receipt_without_jobs_is_complete_unless_superseded(self):
        with Harness({('GET', '/v1/events/' + UUID1): (200, {'status': 'accepted', 'jobs': []})}) as harness:
            self.assertIs(harness.call('event_status', {'event_id': UUID1}).data()['complete'], True)

    def test_a_failure_of_the_receipt_or_of_a_job_is_the_failure_of_the_call(self):
        with Harness({('GET', '/v1/events/' + UUID1): (404, {'error': {'code': 'not_found', 'message': 'Resource not found'}})}) as harness:
            result = harness.call('event_status', {'event_id': UUID1})
            self.assertEqual((result.error, result.text), (True, 'Error executing tool event_status: Resource not found'))
        routes = self.routes(['succeeded'])
        routes[('GET', '/v1/jobs/j1')] = (403, {'error': {'code': 'forbidden', 'message': 'Operation not permitted'}})
        with Harness(routes) as harness:
            result = harness.call('event_status', {'event_id': UUID1})
            self.assertEqual(result.text, 'Error executing tool event_status: Operation not permitted')


class BudgetTests(unittest.TestCase):
    """The `mcp.py` group has no byte budget of its own in the internal MCP; kairos-mcp caps each answer at DETAIL_BYTES and says so."""

    def test_an_oversized_answer_is_cut_at_the_byte_budget_with_the_marker(self):
        huge = {'items': [{'excerpt': 'é' * 200}] * 2000}
        with Harness({('POST', '/v1/search'): (200, huge)}) as harness:
            result = harness.call('search', {'project_ids': [PROJECT], 'q': 'x'})
        self.assertFalse(result.error)
        self.assertLessEqual(len(result.text.encode('utf-8')), DETAIL_BYTES)
        self.assertTrue(result.text.endswith(TRUNCATION))
        self.assertIsNone(result.structured)  # a cut object is no longer an object: only the text, with its marker

    def test_an_answer_within_the_budget_is_unchanged_json_text_and_structured_content(self):
        reply = {'items': [{'excerpt': 'é'}], 'backends': {}, 'partial': False}
        with Harness({('POST', '/v1/search'): (200, reply)}) as harness:
            result = harness.call('search', {'project_ids': [PROJECT], 'q': 'x'})
        self.assertEqual(json.loads(result.text)['items'], reply['items'])
        self.assertEqual(plain(result.structured), reply)


def plain(data):
    return {key: value for key, value in data.items() if key not in ('untrusted', 'warning')}


class ContractTests(unittest.TestCase):
    def test_every_tool_of_the_group_declares_a_real_endpoint(self):
        for name in GROUP:
            with self.subTest(tool=name):
                self.assertIn(TOOLS[name]['x-kairos-endpoint']['method'], ('GET', 'POST', 'DELETE'))


if __name__ == '__main__':
    unittest.main()
