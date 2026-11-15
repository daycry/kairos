"""A bug inside kairos-mcp never reaches the client as its own text: it is the generic unavailable message and a log line without content (T-48)."""
import io
import logging
import unittest
from unittest.mock import patch

from kairos_mcp.errors import UNAVAILABLE
from kairos_mcp.logs import configure_logging
from support import PROJECT, Harness


class UnexpectedFailureTests(unittest.TestCase):
    def test_an_unexpected_exception_is_the_generic_message_and_leaks_nothing(self):
        stream = io.StringIO()
        configure_logging(stream, level=logging.INFO)
        with Harness({}) as harness, patch('kairos_mcp.translate.translate', side_effect=KeyError('INTERNAL-SECRET-DETAIL')):
            result = harness.call('projects')
        self.assertTrue(result.error)
        self.assertEqual(result.text, 'Error executing tool projects: ' + UNAVAILABLE)
        self.assertNotIn('INTERNAL-SECRET-DETAIL', result.text)
        self.assertNotIn('INTERNAL-SECRET-DETAIL', stream.getvalue())
        self.assertIn('tool_failed', stream.getvalue())
        self.assertIn('KeyError', stream.getvalue())

    def test_a_malformed_answer_of_the_api_is_a_failed_call_not_a_success_and_not_a_crash(self):
        # the API answers 200 with a JSON array where an object is expected, and with nothing: the call fails with the generic message
        for body in ([1, 2, 3], None):
            with Harness({('GET', '/v1/projects'): (200, body)}) as harness:
                result = harness.call('projects')
            self.assertTrue(result.error)
            self.assertEqual(result.text, 'Error executing tool projects: ' + UNAVAILABLE)

    def test_a_missing_field_in_a_composed_answer_is_not_a_crash(self):
        # `event_status` without a project reads `receipt.jobs`: a receipt without it must be a failure of the call, not the text of a KeyError
        with Harness({('GET', '/v1/events/11111111-1111-4111-8111-111111111111'): (200, {'status': 'accepted'})}) as harness:
            result = harness.call('event_status', {'event_id': '11111111-1111-4111-8111-111111111111'})
        self.assertTrue(result.error)
        self.assertEqual(result.text, 'Error executing tool event_status: ' + UNAVAILABLE)


if __name__ == '__main__':
    unittest.main()
