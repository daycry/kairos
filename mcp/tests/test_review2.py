"""The corrections of the phase 5 review (attempt 2): an invalid input costs milliseconds whatever its size, within the body limit."""
import json
import time
import unittest

import jsonschema

from kairos_mcp.tools import Checks
from support import TOOLS, Harness

BUDGET_SECONDS = 1.0  # generous: the cost is a few milliseconds; before the fix it was 11 s for 60 000 elements


def checks_of(name):
    return Checks(name, TOOLS[name]['inputSchema'])


class BoundedValidationTests(unittest.TestCase):
    def test_a_huge_invalid_array_is_refused_in_bounded_time(self):
        checks = checks_of('get_observations')
        started = time.perf_counter()
        refusal = checks.refusal({'projectId': 'demo', 'ids': [1] * 60000})
        elapsed = time.perf_counter() - started
        self.assertTrue(refusal.startswith('Input validation error: '), refusal[:80])
        self.assertLess(elapsed, BUDGET_SECONDS)

    def test_a_body_near_the_limit_is_refused_in_bounded_time_through_the_server(self):
        arguments = {'projectId': 'demo', 'ids': [1] * 120000}
        self.assertLess(len(json.dumps(arguments, separators=(',', ':'))), 256 * 1024)
        with Harness({}) as harness:
            started = time.perf_counter()
            result = harness.call('get_observations', arguments)
            elapsed = time.perf_counter() - started
        self.assertTrue(result.error)
        self.assertTrue(result.text.startswith('Input validation error: '))
        self.assertLess(elapsed, BUDGET_SECONDS)

    def test_the_errors_are_bounded_and_small_inputs_keep_the_sdk_message(self):
        checks = checks_of('get_observations')
        for arguments in ({'projectId': 'demo', 'ids': [1, 2]}, {'projectId': 'demo'}, {'projectId': 'X', 'ids': ['a']}, {'ids': []}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(jsonschema.ValidationError) as expected:
                    jsonschema.validate(instance=arguments, schema=TOOLS['get_observations']['inputSchema'])
                self.assertEqual(checks.refusal(arguments), 'Input validation error: ' + expected.exception.message)


if __name__ == '__main__':
    unittest.main()
