"""The corrections of the phase 5 review (attempt 3): an invalid array costs milliseconds wherever the contract puts it, `anyOf` included (CWE-400).

jsonschema 4.26 materializes every error of every `anyOf` branch before it yields the first one, so bounding the consumer with `islice` was not enough:
the arrays inside an `anyOf` (`T | None`) were validated whole. The arrays are found by walking the schemas of the contract, not listed by hand."""
import json
import time
import unittest

import jsonschema

from kairos_mcp.tools import ERROR_LIMIT, Checks
from support import TOOLS, Harness

BUDGET_SECONDS = 1.0  # generous: the cost is a few milliseconds; before the fix it was 14 s for 60 000 elements and 29 s for 120 000
HUGE = 120000  # elements; 240 KB as JSON, under the 256 KiB body limit
BODY_LIMIT = 256 * 1024


def resolved(root, schema):
    """The schema a local `$ref` (`#/$defs/Name`) points to, or the schema itself."""
    while '$ref' in schema:
        target = root
        for part in schema['$ref'].removeprefix('#/').split('/'):
            target = target[part]
        schema = target
    return schema


def array_paths(root, schema, path=(), seen=()):
    """Every place of an input schema where an array is accepted, as `(path, items schema)`: the path is made of property names and `None` (an item),
    walked through `anyOf`, `properties`, `items` and local `$ref`s."""
    if '$ref' in schema:
        if schema['$ref'] in seen:
            return
        seen += (schema['$ref'],)
        schema = resolved(root, schema)
    if schema.get('type') == 'array':
        yield path, resolved(root, schema.get('items', {}))
        if isinstance(schema.get('items'), dict):
            yield from array_paths(root, schema['items'], path + (None,), seen)
    for alternative in schema.get('anyOf', []):
        yield from array_paths(root, alternative, path, seen)
    for key, value in schema.get('properties', {}).items():
        yield from array_paths(root, value, path + (key,), seen)


def with_array(path, elements):
    """Arguments with `elements` at the array `path` (a `None` is an item of the array before it)."""
    value = elements
    for step in reversed(path):
        value = [value] if step is None else {step: value}
    return value


def count_of(element):
    """As many elements as fit the body limit, at most `HUGE` (the smallest elements, `1`, give the 120 000 of the review)."""
    return min(HUGE, (BODY_LIMIT - 1024) // (len(json.dumps(element)) + 1))


def contract_arrays():
    """`(tool, path, an element that array rejects)` for every array of every input schema."""
    found = []
    for name, tool in TOOLS.items():
        root = tool['inputSchema']
        for path, items in array_paths(root, root):
            validator = jsonschema.Draft202012Validator({**items, '$defs': root.get('$defs', {})})
            invalid = next(candidate for candidate in (1, [], {}, 'x', None, True, {'invalid': True}) if not validator.is_valid(candidate))
            found.append((name, path, invalid))
    return sorted(found, key=str)


class EveryArrayOfTheContractTests(unittest.TestCase):
    def test_the_walk_finds_the_arrays_of_anyof_and_the_others(self):
        found = contract_arrays()
        self.assertGreaterEqual(len(found), 15)
        paths = {(name, path) for name, path, _ in found}
        self.assertIn(('search', ('layers',)), paths)
        self.assertIn(('get_observations', ('ids',)), paths)

    def test_every_array_is_refused_in_bounded_time(self):
        for name, path, invalid in contract_arrays():
            with self.subTest(tool=name, path=path):
                arguments = with_array(path, [invalid] * count_of(invalid))
                self.assertLess(len(json.dumps(arguments, separators=(',', ':'))), BODY_LIMIT)
                checks = Checks(name, TOOLS[name]['inputSchema'])
                started = time.perf_counter()
                refusal = checks.refusal(arguments)
                elapsed = time.perf_counter() - started
                self.assertTrue(refusal and refusal.startswith('Input validation error: '), refusal)
                self.assertLess(elapsed, BUDGET_SECONDS, '%s %s took %.2f s' % (name, path, elapsed))

    def test_the_reviewers_request_through_the_server_is_bounded(self):
        arguments = {'q': 'x', 'project_ids': ['p'], 'layers': [1] * HUGE}
        with Harness({}) as harness:
            started = time.perf_counter()
            result = harness.call('search', arguments)
            elapsed = time.perf_counter() - started
        self.assertTrue(result.error)
        self.assertTrue(result.text.startswith('Input validation error: '))
        self.assertLess(elapsed, BUDGET_SECONDS)

    def test_a_few_errors_give_the_text_of_the_sdk_in_every_array_of_the_contract(self):
        for name, path, invalid in contract_arrays():
            for elements in ([invalid] * 3, [], [invalid]):
                with self.subTest(tool=name, path=path, elements=len(elements)):
                    arguments = with_array(path, elements)
                    try:
                        jsonschema.validate(instance=arguments, schema=TOOLS[name]['inputSchema'])
                    except jsonschema.ValidationError as exc:
                        expected = 'Input validation error: ' + exc.message
                    else:
                        expected = None
                    self.assertEqual(Checks(name, TOOLS[name]['inputSchema']).refusal(arguments), expected)

    def test_a_valid_array_inside_an_anyof_is_not_refused(self):
        checks = Checks('search', TOOLS['search']['inputSchema'])
        self.assertIsNone(checks.refusal({'q': 'x', 'project_ids': ['p'], 'layers': ['a', 'b']}))
        self.assertIsNone(checks.refusal({'q': 'x', 'project_ids': ['p'], 'layers': None}))

    def test_a_few_errors_in_scalars_and_objects_keep_the_text_of_the_sdk(self):
        cases = (('search', {'q': 5, 'project_ids': ['p']}), ('search', {'q': 'x', 'project_ids': ['p'], 'layers': 'a'}),
                 ('search', {'q': 'x', 'project_ids': ['p'], 'layers': [9]}), ('search', {'q': 'x', 'project_ids': ['p'], 'limit': 'many'}))
        for name, arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(jsonschema.ValidationError) as expected:
                    jsonschema.validate(instance=arguments, schema=TOOLS[name]['inputSchema'])
                self.assertEqual(Checks(name, TOOLS[name]['inputSchema']).refusal(arguments), 'Input validation error: ' + expected.exception.message)

    def test_many_extra_properties_and_huge_strings_are_refused_in_bounded_time_in_every_tool(self):
        for name, tool in TOOLS.items():
            checks = Checks(name, tool['inputSchema'])
            for label, arguments in (('extra properties', {'k%d' % index: 1 for index in range(15000)}), ('huge key and value', {'k' * 100000: 1, 'q': 'x' * 100000})):
                with self.subTest(tool=name, case=label):
                    started = time.perf_counter()
                    refusal = checks.refusal(arguments)
                    self.assertLess(time.perf_counter() - started, BUDGET_SECONDS)
                    self.assertTrue(refusal is None or refusal.startswith('Input validation error: '))


if __name__ == '__main__':
    unittest.main()
