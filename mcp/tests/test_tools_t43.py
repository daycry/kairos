"""T-43 (CA-10, CA-11): the 7 tools of the `extended_tools.py` group: observation writes, tool uses and shared team work."""
import unittest

from kairos_mcp.budget import DETAIL_BYTES, NORMAL_BYTES, TRUNCATION
from support import PROJECT, TOOLS, UUID1, UUID2, Harness
from tool_cases import Case, exercise

P = '/v1/projects/' + PROJECT
GROUP = ['observation_add', 'observation_record_event', 'get_tool_uses', 'team_work_write', 'team_work_read', 'team_brief', 'team_search']
EVENT = {'event_id': UUID1, 'project_id': PROJECT, 'session_id': 's', 'agent_id': 'a', 'event_type': 'note', 'occurred_at': '2026-11-04T10:00:00Z',
         'item_id': UUID2, 'version': 1, 'payload': {'title': 'T', 'content': 'C'}}
REVISION = {**EVENT, 'event_id': '33333333-3333-4333-8333-333333333333', 'version': 2}

CASES = [
    Case('observation_add', {'event': EVENT}, 'POST', '/v1/observations', {'receipt': {'status': 'accepted'}, 'jobs': []}, body=EVENT, status=202),
    Case('observation_record_event', {'event': REVISION}, 'POST', '/v1/observations/events', {'receipt': {'status': 'accepted'}, 'jobs': []}, body=REVISION, status=202),
    Case('get_tool_uses', {'project': PROJECT, 'session_id': 's1', 'tool': 'Read', 'limit': 5, 'cursor': 'c'}, 'GET', '/v1/tool-uses',
         {'items': [], 'has_more': False, 'next_cursor': None},
         query={'project_id': [PROJECT], 'session_id': ['s1'], 'tool': ['Read'], 'limit': ['5'], 'cursor': ['c']}),
    Case('team_work_write', {'project': PROJECT, 'list': 'release', 'fields': {'task': 'Rotate', 'status': 'todo'}, 'request_id': 'r1', 'expected_version': 2},
         'POST', P + '/team-work', {'list': 'release', 'version': 3},
         body={'list': 'release', 'fields': {'task': 'Rotate', 'status': 'todo'}, 'request_id': 'r1', 'expected_version': 2}),
    Case('team_work_read', {'project': PROJECT, 'list': 'release', 'include_closed': True}, 'GET', P + '/team-work', {'lists': []},
         query={'list': ['release'], 'include_closed': ['true']}),
    Case('team_search', {'project': PROJECT, 'query': 'fencing', 'limit': 3}, 'GET', P + '/team-search', {'items': []}, query={'query': ['fencing'], 'limit': ['3']}),
    Case('team_brief', {'project': PROJECT, 'limit': 3}, 'GET', P + '/team-brief', {'items': []}, query={'limit': ['3']}),
]


class GroupTests(unittest.TestCase):
    def test_the_cases_are_exactly_the_7_tools_of_the_group(self):
        self.assertEqual(sorted(case.tool for case in CASES), sorted(GROUP))

    def test_each_tool_translates_succeeds_fails_and_degrades_as_the_internal_mcp_does(self):
        exercise(self, CASES)

    def test_a_false_boolean_query_value_is_sent_as_false_not_dropped(self):
        with Harness({('GET', P + '/team-work'): (200, {'lists': []})}) as harness:
            harness.call('team_work_read', {'project': PROJECT, 'include_closed': False})
            self.assertEqual(harness.stub.requests[0].query, {'include_closed': ['false']})

    def test_the_answers_are_text_json_wrapped_as_result(self):
        with Harness({('GET', P + '/team-brief'): (200, {'items': []})}) as harness:
            result = harness.call('team_brief', {'project': PROJECT})
        self.assertEqual(result.structured, {'result': result.text})


class ByteBudgetTests(unittest.TestCase):
    """Every tool of the group renders at DETAIL_BYTES in the internal MCP (`extended_tools.call`)."""

    def big(self, size):
        return {'items': [{'id': str(number), 'content': 'é' * 100} for number in range(size)]}

    def test_every_listing_tool_of_the_group_has_the_detail_budget(self):
        for tool, arguments, method, route in (('get_tool_uses', {'project': PROJECT}, 'GET', '/v1/tool-uses'),
                                               ('team_work_read', {'project': PROJECT}, 'GET', P + '/team-work'),
                                               ('team_search', {'project': PROJECT}, 'GET', P + '/team-search'),
                                               ('team_brief', {'project': PROJECT}, 'GET', P + '/team-brief')):
            with self.subTest(tool=tool):
                with Harness({(method, route): (200, self.big(1000))}) as harness:  # ~220 KB: over NORMAL, under DETAIL
                    medium = harness.call(tool, arguments)
                self.assertGreater(len(medium.text.encode('utf-8')), NORMAL_BYTES)
                self.assertFalse(medium.text.endswith(TRUNCATION))
                with Harness({(method, route): (200, self.big(5000))}) as harness:
                    cut = harness.call(tool, arguments)
                self.assertLessEqual(len(cut.text.encode('utf-8')), DETAIL_BYTES)
                self.assertTrue(cut.text.endswith(TRUNCATION))


class ContractTests(unittest.TestCase):
    def test_the_writes_keep_their_annotations(self):
        self.assertTrue(TOOLS['observation_record_event']['annotations']['destructiveHint'])
        self.assertFalse(TOOLS['observation_add']['annotations']['readOnlyHint'])


if __name__ == '__main__':
    unittest.main()
