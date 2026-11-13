"""C-05: the server validates `payload.structured` against the versioned schemas in docs/contracts (CA-20, CA-21)."""
import json
import unittest
from pathlib import Path

from memory_platform import schemas
from memory_platform.errors import MemoryError

SENTINEL = 'SENTINEL-4f9c1e-do-not-echo'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def examples(schema, kind):
    return sorted((schemas.contracts_dir() / 'examples' / schema / kind).glob('*.json'))


class SchemaModuleTests(unittest.TestCase):
    def test_every_valid_example_passes(self):
        for schema in ('observation.v1', 'session-summary.v1'):
            found = examples(schema, 'valid')
            self.assertGreaterEqual(len(found), 3)
            for path in found:
                schemas.validate_structured(load(path))

    def test_every_invalid_example_is_rejected_as_invalid_observation(self):
        for schema in ('observation.v1', 'session-summary.v1'):
            found = examples(schema, 'invalid')
            self.assertGreaterEqual(len(found), 5)
            for path in found:
                with self.assertRaises(MemoryError, msg=f'{schema}/{path.name}') as caught:
                    schemas.validate_structured(load(path))
                self.assertEqual((caught.exception.code, caught.exception.status_code), ('invalid_observation', 422), path.name)

    def test_the_error_carries_the_json_path_and_never_the_content(self):
        base = load(examples('observation.v1', 'valid')[0])
        cases = [
            ({'title': SENTINEL * 20}, '/payload/structured/title'),
            ({'facts': [{'statement': SENTINEL, 'evidence_quote': SENTINEL, 'extra': SENTINEL}]}, '/payload/structured/facts/0'),
            ({SENTINEL: SENTINEL}, '/payload/structured'),
            ({'concepts': SENTINEL}, '/payload/structured/concepts'),
            ({'schema_version': SENTINEL}, '/payload/structured/schema_version'),
            ({'type': SENTINEL}, '/payload/structured/type'),
        ]
        for change, path in cases:
            with self.assertRaises(MemoryError) as caught:
                schemas.validate_structured({**base, **change})
            self.assertIn(path, caught.exception.message)
            self.assertNotIn(SENTINEL, caught.exception.message)
        missing = {key: value for key, value in base.items() if key != 'narrative'}
        with self.assertRaises(MemoryError) as caught:
            schemas.validate_structured(missing)
        self.assertIn('/payload/structured/narrative', caught.exception.message)

    def test_a_document_that_is_not_an_object_is_rejected_without_echo(self):
        for value in ([SENTINEL], SENTINEL, 7, None):
            with self.assertRaises(MemoryError) as caught:
                schemas.validate_structured(value)
            self.assertEqual(caught.exception.code, 'invalid_observation')
            self.assertNotIn(SENTINEL, caught.exception.message)


if __name__ == '__main__':
    unittest.main()
