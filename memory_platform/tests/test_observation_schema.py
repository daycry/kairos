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


def named(schema, name):
    return load(schemas.contracts_dir() / 'examples' / schema / 'valid' / (name + '.json'))


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
        base = named('observation.v1', 'valid-bugfix')
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


class LimitTests(unittest.TestCase):
    """T-33 (CA-20): one case per limit and per kind of error, against the documents in docs/contracts/examples."""

    def base(self, schema='observation.v1'):
        return named(schema, 'valid-bugfix' if schema == 'observation.v1' else 'valid-complete')

    def rejected(self, document, path):
        with self.assertRaises(MemoryError) as caught:
            schemas.validate_structured(document)
        self.assertEqual(caught.exception.code, 'invalid_observation')
        self.assertIn('/payload/structured' + path, caught.exception.message)
        self.assertNotIn(SENTINEL, caught.exception.message)

    def test_every_length_and_count_limit_accepts_the_limit_and_rejects_one_over(self):
        fact = {'statement': 's', 'evidence_quote': 'q'}
        limits = [('title', '/title', 200, lambda n: 't' * n), ('narrative', '/narrative', 20000, lambda n: 'n' * n),
                  ('facts', '/facts', 20, lambda n: [fact] * n),
                  ('concepts', '/concepts', 20, lambda n: [f'c{i}' for i in range(n)]),
                  ('files_read', '/files_read', 50, lambda n: [f'f{i}' for i in range(n)]),
                  ('files_modified', '/files_modified', 50, lambda n: [f'f{i}' for i in range(n)])]
        for key, path, limit, make in limits:
            schemas.validate_structured({**self.base(), key: make(limit)})
            self.rejected({**self.base(), key: make(limit + 1)}, path)
        for key, path, limit in (('statement', '/facts/0/statement', 500), ('evidence_quote', '/facts/0/evidence_quote', 2000)):
            schemas.validate_structured({**self.base(), 'facts': [{**fact, key: 'x' * limit}]})
            self.rejected({**self.base(), 'facts': [{**fact, key: 'x' * (limit + 1)}]}, path)
        schemas.validate_structured({**self.base(), 'concepts': ['c' * 100]})
        self.rejected({**self.base(), 'concepts': ['c' * 101]}, '/concepts/0')
        schemas.validate_structured({**self.base(), 'files_modified': ['f' * 500]})
        self.rejected({**self.base(), 'files_modified': ['f' * 501]}, '/files_modified/0')

    def test_summary_fields_have_their_limit_too(self):
        base = self.base('session-summary.v1')
        for key in ('request', 'investigated', 'learned', 'completed', 'next_steps'):
            schemas.validate_structured({**base, key: 'x' * 4000})
            self.rejected({**base, key: 'x' * 4001}, '/' + key)
            self.rejected({**base, key: ''}, '/' + key)

    def test_lengths_count_characters_not_bytes(self):
        schemas.validate_structured({**self.base(), 'title': '\U0001F99C' * 200})
        self.rejected({**self.base(), 'title': '\U0001F99C' * 201}, '/title')

    def test_each_kind_of_error_is_reported_with_its_rule(self):
        base = self.base()
        fact = {'statement': 's', 'evidence_quote': 'q'}
        kinds = {'required': {k: v for k, v in base.items() if k != 'type'}, 'additionalProperties': {**base, 'x': 1},
                 'type': {**base, 'concepts': 'a'}, 'enum': {**base, 'type': 'other'}, 'const': {**base, 'schema_version': 'observation.v2'},
                 'maxLength': {**base, 'title': 't' * 201}, 'maxItems': {**base, 'facts': [fact] * 21},
                 'minLength': {**base, 'title': ''}, 'uniqueItems': {**base, 'concepts': ['a', 'a']}}
        for rule, document in kinds.items():
            with self.assertRaises(MemoryError) as caught:
                schemas.validate_structured(document)
            self.assertIn(rule, caught.exception.message)

    def test_hostile_nesting_and_size_are_rejected_without_reading_the_content(self):
        deep = current = {}
        for _ in range(5000):
            current['k'] = {}
            current = current['k']
        for document in ({**self.base(), 'title': deep}, {**self.base(), SENTINEL: deep}, {**self.base(), 'facts': [deep]}):
            with self.assertRaises(MemoryError) as caught:
                schemas.validate_structured(document)
            self.assertEqual(caught.exception.code, 'invalid_observation')
            self.assertNotIn(SENTINEL, caught.exception.message)
        wide = {**self.base(), **{f'{SENTINEL}{i}': i for i in range(2000)}}
        self.rejected(wide, '')


if __name__ == '__main__':
    unittest.main()
