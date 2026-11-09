"""Surface of Store: names and signatures must not change in the C-02 refactor (CA-05).

Regenerate the snapshot deliberately with:
    python -m memory_platform.tests.test_store_surface --write
"""
import inspect
import json
import sys
import unittest
from pathlib import Path

SNAPSHOT = Path(__file__).with_name('store_surface.json')
HELPERS = ('as_dict', 'canonical', 'digest', 'new_id', 'lexical_query', 'clean')


def surface():
    from memory_platform.store import Store
    methods = {}
    for name in sorted(n for n in dir(Store) if not n.startswith('__') or n == '__init__'):
        value = inspect.getattr_static(Store, name)
        kind = 'staticmethod' if isinstance(value, staticmethod) else 'classmethod' if isinstance(value, classmethod) else 'function' if callable(getattr(Store, name)) else 'attribute'
        methods[name] = {'kind': kind, 'signature': str(inspect.signature(getattr(Store, name))) if kind != 'attribute' else None,
                         'contextmanager': bool(getattr(getattr(Store, name), '__wrapped__', None))}
    return {'methods': methods, 'helpers': list(HELPERS)}


class StoreSurfaceTests(unittest.TestCase):
    def test_names_and_signatures_match_snapshot(self):
        expected = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        actual = surface()
        self.assertEqual(sorted(expected['methods']), sorted(actual['methods']))
        for name, spec in expected['methods'].items():
            self.assertEqual(spec, actual['methods'][name], name)

    def test_reexported_helpers_import_from_store(self):
        from memory_platform import store
        for name in json.loads(SNAPSHOT.read_text(encoding='utf-8'))['helpers']:
            self.assertTrue(callable(getattr(store, name)), name)

    def test_import_line_used_by_importers(self):
        from memory_platform.store import Store, as_dict, canonical, digest, new_id, lexical_query, clean  # noqa: F401


if __name__ == '__main__':
    if '--write' in sys.argv:
        SNAPSHOT.write_text(json.dumps(surface(), indent=2, sort_keys=True) + '\n', encoding='utf-8')
    else:
        unittest.main()
