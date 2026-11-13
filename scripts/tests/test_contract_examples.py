"""CA-21: the versioned examples validate as expected with a validator that shares no code with the server.

Only the standard library and `jsonschema` are imported; the server package is deliberately not. The server runs the same
examples through its own module in its own test suite, so a disagreement between the two shows up as a failing test.
"""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[2] / 'docs' / 'contracts'
SCHEMAS = ('observation.v1', 'session-summary.v1')
# Every invalid example carries the kind of defect in its file name; each kind the spec lists must be present.
KINDS = {'missing': 'missing', 'extra': 'extra', 'limit': ('too-long', 'too-many'), 'type': 'wrong-type', 'version': 'unknown-version'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def examples(schema, kind):
    return sorted((CONTRACTS / 'examples' / schema / kind).glob('*.json'))


class ContractExamplesTests(unittest.TestCase):
    def validator(self, schema):
        document = load(CONTRACTS / (schema + '.schema.json'))
        Draft202012Validator.check_schema(document)
        self.assertEqual(document['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        self.assertEqual(document['properties']['schema_version'], {'const': schema})
        return Draft202012Validator(document)

    def test_each_schema_has_enough_examples_of_every_kind(self):
        for schema in SCHEMAS:
            self.assertGreaterEqual(len(examples(schema, 'valid')), 3, schema)
            invalid = [path.name for path in examples(schema, 'invalid')]
            self.assertGreaterEqual(len(invalid), 5, schema)
            for kind, needles in KINDS.items():
                needles = (needles,) if isinstance(needles, str) else needles
                self.assertTrue(any(n in name for name in invalid for n in needles), f'{schema}: no invalid example of kind {kind}')

    def test_the_independent_validator_accepts_the_valid_examples(self):
        for schema in SCHEMAS:
            validator = self.validator(schema)
            for path in examples(schema, 'valid'):
                errors = [e.json_path for e in validator.iter_errors(load(path))]
                self.assertEqual(errors, [], f'{schema}/{path.name}')

    def test_the_independent_validator_rejects_the_invalid_examples(self):
        for schema in SCHEMAS:
            validator = self.validator(schema)
            for path in examples(schema, 'invalid'):
                self.assertTrue(list(validator.iter_errors(load(path))), f'{schema}/{path.name} should be rejected')

    def test_the_limits_are_tight(self):
        # The at-every-limit examples pass and one unit over fails: the limits are the ones the examples exercise.
        for schema in SCHEMAS:
            validator = self.validator(schema)
            top = load(next(p for p in examples(schema, 'valid') if 'at-every-limit' in p.name))
            for key, value in top.items():
                if isinstance(value, str) and key != 'schema_version' and key != 'type':
                    over = {**top, key: value + 'x'}
                    self.assertTrue(list(validator.iter_errors(over)), f'{schema}.{key} accepts one character over its limit')


if __name__ == '__main__':
    unittest.main()
