"""Pure file-fixture checks; no Docker, database, credentials or model calls."""
import json
from pathlib import Path
import unittest
import shutil
import uuid
from unittest.mock import patch

import frozen_evidence as evidence


class FrozenEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.product_root = Path(__file__).resolve().parents[4]
        self.fixture_root = (self.product_root/'.pytest_cache/evidence-fixtures').resolve()
        if not self.fixture_root.is_relative_to(self.product_root):
            raise RuntimeError('Fixture directory must remain inside the product workspace')
        self.fixture_root.mkdir(parents=True, exist_ok=True)
        # Python's Windows mode-0700 tempfile ACL can reject the restricted test
        # token; an owned workspace directory uses its inherited permissions.
        self.directory = (self.fixture_root/('kairos-evidence-fixture-'+uuid.uuid4().hex)).resolve()
        self.directory.mkdir()

    def tearDown(self):
        if self.directory.parent != self.fixture_root or not self.directory.name.startswith('kairos-evidence-fixture-'):
            raise RuntimeError('Refusing cleanup outside owned evidence fixture')
        shutil.rmtree(self.directory)

    def source(self, token):
        return {'schema': 1, 'source_sha256': token*64, 'files': {'synthetic.py': 'fixture'}, 'full_backend_suite': True}

    def result(self, token):
        return {'source_sha256': token*64, 'passed': True, 'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0}

    def test_current_running_receipt_precedes_new_manifest_and_history_stays_immutable(self):
        evidence.begin_evidence(self.directory, 'frozen', self.source('a'))
        first = evidence.finish_evidence(self.directory, 'frozen', self.result('a'))
        original_atomic, operations = evidence.atomic, []
        def observed(path, value):
            operations.append((path.name, value.get('status'), value.get('passed')))
            return original_atomic(path, value)
        with patch.object(evidence, 'atomic', side_effect=observed):
            running = evidence.begin_evidence(self.directory, 'frozen', self.source('b'))
        self.assertEqual(operations[0], ('frozen-postgres-result.json', 'running', False))
        self.assertEqual(running['source_sha256'], 'b'*64)
        self.assertFalse(running['passed'])
        saved = [self.directory/name for name in running['historical_pair']]
        self.assertEqual(len(saved), 2)
        saved_bytes = [path.read_bytes() for path in saved]
        self.assertEqual(json.loads(saved_bytes[0]), self.source('a'))
        self.assertEqual(json.loads(saved_bytes[1]), first)
        self.assertIn('history-'+('a'*16), saved[0].name)
        evidence.finish_evidence(self.directory, 'frozen', self.result('b'))
        evidence.begin_evidence(self.directory, 'frozen', self.source('c'))
        self.assertEqual([path.read_bytes() for path in saved], saved_bytes)

    def test_stale_completion_cannot_overwrite_running_source(self):
        evidence.begin_evidence(self.directory, 'frozen', self.source('b'))
        with self.assertRaises(ValueError):
            evidence.finish_evidence(self.directory, 'frozen', self.result('a'))
        active = json.loads((self.directory/'frozen-postgres-result.json').read_text())
        self.assertEqual(active['status'], 'running')
        self.assertFalse(active['passed'])
        evidence.finish_evidence(self.directory, 'frozen', self.result('b'))

    def test_inconsistent_previously_passed_pair_is_not_silently_overwritten(self):
        evidence.atomic(self.directory/'frozen-postgres-source.json', self.source('a'))
        evidence.atomic(self.directory/'frozen-postgres-result.json', self.result('b'))
        with self.assertRaises(ValueError):
            evidence.begin_evidence(self.directory, 'frozen', self.source('c'))
        self.assertEqual(json.loads((self.directory/'frozen-postgres-result.json').read_text()), self.result('b'))

    def test_invalid_historical_hash_cannot_become_a_filesystem_path(self):
        source = dict(self.source('a'), source_sha256='../outside')
        result = dict(self.result('a'), source_sha256='../outside')
        evidence.atomic(self.directory/'frozen-postgres-source.json', source)
        evidence.atomic(self.directory/'frozen-postgres-result.json', result)
        with self.assertRaises(ValueError):
            evidence.begin_evidence(self.directory, 'frozen', self.source('b'))


if __name__ == '__main__':
    unittest.main()
