"""T-44 (CA-10, CA-11, P-04): `corpus_answer` and `corpus_answer_status`, and with them the 34 tools of the contract are all served."""
import unittest

from kairos_mcp.budget import DETAIL_BYTES, OUTPUT, TRUNCATION
from support import CONTRACT, PROJECT, TOOLS, Harness
from tool_cases import Case, exercise

P = '/v1/projects/' + PROJECT
ASKED = {'project': PROJECT, 'name': 'team/c1', 'question': 'What is fencing?', 'request_id': 'a1', 'expected_session_id': 'sess', 'expected_generation': 2}
DISABLED = (403, {'error': {'code': 'corpus_answer_disabled',
                            'message': 'corpus_answer_disabled: generated answers are off on this server (MEMORY_CORPUS_ANSWER=off)'}})

CASES = [
    Case('corpus_answer', ASKED, 'POST', P + '/corpora/team%2Fc1/answers', {'answer': 'Fencing guards a token.', 'citations': []},
         body={'question': 'What is fencing?', 'request_id': 'a1', 'expected_session_id': 'sess', 'expected_generation': 2}),
    Case('corpus_answer_status', {'project': PROJECT, 'name': 'team/c1', 'request_id': 'a1'}, 'GET', P + '/corpora/team%2Fc1/answers/a1',
         {'state': 'completed', 'answer': 'Fencing guards a token.'}),
]


class GroupTests(unittest.TestCase):
    def test_each_tool_translates_succeeds_fails_and_degrades_as_the_internal_mcp_does(self):
        exercise(self, CASES)

    def test_the_error_of_a_server_with_generated_answers_off_reaches_the_client_with_its_message(self):
        with Harness({('POST', P + '/corpora/team%2Fc1/answers'): DISABLED}) as harness:
            result = harness.call('corpus_answer', ASKED)
        self.assertTrue(result.error)
        self.assertEqual(result.text, 'Error executing tool corpus_answer: corpus_answer_disabled: generated answers are off on this server (MEMORY_CORPUS_ANSWER=off)')

    def test_the_status_of_a_stored_answer_is_readable_while_generation_is_off(self):
        with Harness({('GET', P + '/corpora/c1/answers/a1'): (200, {'state': 'completed', 'answer': 'saved'})}) as harness:
            result = harness.call('corpus_answer_status', {'project': PROJECT, 'name': 'c1', 'request_id': 'a1'})
        self.assertEqual(result.data()['answer'], 'saved')

    def test_the_status_has_the_detail_budget(self):
        huge = {'answer': 'é' * 400000}
        with Harness({('GET', P + '/corpora/c1/answers/a1'): (200, huge)}) as harness:
            result = harness.call('corpus_answer_status', {'project': PROJECT, 'name': 'c1', 'request_id': 'a1'})
        self.assertLessEqual(len(result.text.encode('utf-8')), DETAIL_BYTES)
        self.assertTrue(result.text.endswith(TRUNCATION))

    def test_the_generator_is_open_world_and_the_status_reads_only(self):
        self.assertTrue(TOOLS['corpus_answer']['annotations']['openWorldHint'])
        self.assertTrue(TOOLS['corpus_answer_status']['annotations']['readOnlyHint'])


class AllThirtyFourTests(unittest.TestCase):
    def test_every_tool_of_the_contract_is_served_and_nothing_else(self):
        names = [tool['name'] for tool in CONTRACT['tools']]
        self.assertEqual(len(names), 34)
        self.assertEqual(sorted(OUTPUT), sorted(names))

    def test_every_served_tool_has_a_declared_endpoint_or_is_local(self):
        for tool in CONTRACT['tools']:
            endpoint = tool['x-kairos-endpoint']
            self.assertTrue(endpoint == 'local' or endpoint['method'] in ('GET', 'POST', 'DELETE'), tool['name'])


if __name__ == '__main__':
    unittest.main()
