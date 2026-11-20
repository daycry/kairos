"""The cleanup of `scripts/measure-scrypt.py` removes only the containers it started (names that BEGIN with `kairos-measure-`), never one that merely contains the text."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'measure-scrypt.py'


def load():
    spec = importlib.util.spec_from_file_location('measure_scrypt', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CleanupFilterTests(unittest.TestCase):
    def test_only_names_that_begin_with_the_prefix_are_removed(self):
        names = '\n'.join(['kairos-measure-api', 'kairos-measure-bootstrap-256m', 'knowledge-graphs-kairos-measure-x', 'my-kairos-measure-api', 'knowledge-graphs-memory-api-1', ''])
        self.assertEqual(load().measure_containers(names), ['kairos-measure-api', 'kairos-measure-bootstrap-256m'])

    def test_nothing_listed_removes_nothing(self):
        self.assertEqual(load().measure_containers(''), [])

    def test_the_cleanup_asks_docker_for_names_and_filters_them(self):
        source = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("measure_containers(docker('ps', '-a', '--format', '{{.Names}}'", source)
        self.assertNotIn("'ps', '-aq'", source)


if __name__ == '__main__':
    unittest.main()
