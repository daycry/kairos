"""The host scripts that log in to the portal with `secrets/bootstrap_password` read it with the rule of the server (fix3 of the phase 2 review of access-control, gaps 1 and 2).

`admin bootstrap` creates the administrator from that file with `password_from_file` (`server/memory_platform/admin.py`): exactly the text minus ONE final line break, a file
that is not UTF-8 or that starts with a UTF-8 byte order mark is `password_file_invalid` with no byte of it. The scripts cannot import `memory_platform` (they run on the host), so
each one repeats the rule in a small `bootstrap_password` function; these tests run every case against the three copies AND against `password_from_file` itself, taken from the
source of admin.py, so that a copy that drifts from the server is red. A script that went back to `.read_text().strip()` would log in with a different password than the one
bootstrap created (401 in the round trip, the native acceptance or the rehearsal) whenever the file has spaces at the ends, two line breaks or a carriage return.
"""
import ast
import importlib.util
from pathlib import Path
import re
import shutil
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ('deploy-memory.py', 'accept-native-clients.py', 'rehearse-reliable-operations.py')


def load(filename):
    name = 'kairos_bootstrap_password_' + re.sub(r'\W', '_', filename)
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def server_rule():
    """`password_from_file` of admin.py, compiled alone from its source (admin.py imports the server's dependencies, which the host does not have)."""
    tree = ast.parse((ROOT / 'server' / 'memory_platform' / 'admin.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'password_from_file')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'admin.py', 'exec'), namespace)
    return namespace['password_from_file']


CASES = ((b'  padded password 1  \r\n', '  padded password 1  '), (b'plain-password-123\n', 'plain-password-123'), (b'no-final-break-1234', 'no-final-break-1234'),
         (b'two-breaks-12345\n\n', 'two-breaks-12345\n'), (b'carriage-return-1\r', 'carriage-return-1\r'), (b'tab-at-the-end-123\t\n', 'tab-at-the-end-123\t'),
         (b'\n lead-and-trail \n', '\n lead-and-trail '), (b' no-break-but-spaces ', ' no-break-but-spaces '), (b'no-break-but-a-tab\t', 'no-break-but-a-tab\t'),
('inner﻿mark-12345\n'.encode('utf-8'), 'inner﻿mark-12345'))
INVALID = ((b'secret-\xff\xfe-password-123\n', 'password_file_invalid: the file is not UTF-8 text'),
           (b'\xef\xbb\xbfsecret-bom-password-123\n', 'password_file_invalid: the file starts with a byte order mark; save it as UTF-8 without BOM'))
LEAKS = ('secret', 'password-123', '0xff', '0xfe', 'position', 'codec', '﻿')


class BootstrapPasswordFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readers = {filename: load(filename).bootstrap_password for filename in SCRIPTS}
        cls.readers['admin.py password_from_file'] = server_rule()

    def setUp(self):
        # Synthetic, non-secret fixtures under the repository's ignored cache (as test_accept_native_clients.py does: the Windows owner-only DACL of tempfile is not readable here).
        parent = ROOT / '.cache' / 'bootstrap-password-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = parent / ('kairos-bootstrap-password-' + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)

    def secret(self, raw):
        path = self.directory / 'bootstrap_password'
        path.write_bytes(raw)
        return path

    def test_every_reader_gives_the_password_that_bootstrap_created(self):
        for raw, expected in CASES:
            for reader, function in self.readers.items():
                with self.subTest(reader=reader, raw=raw):
                    self.assertEqual(function(self.secret(raw)), expected)

    def test_a_file_that_is_not_utf8_or_starts_with_a_byte_order_mark_is_a_typed_error_without_a_byte_of_it(self):
        for raw, message in INVALID:
            for reader, function in self.readers.items():
                with self.subTest(reader=reader, raw=raw[:3]):
                    with self.assertRaises(BaseException) as caught:
                        function(self.secret(raw))
                    self.assertEqual(str(caught.exception), message)
                    self.assertIsNone(caught.exception.__cause__)
                    self.assertTrue(caught.exception.__context__ is None or caught.exception.__suppress_context__, 'the decoding error (which names the byte and its position) is not chained')
                    for leaked in LEAKS:
                        self.assertNotIn(leaked, str(caught.exception))

    def test_the_scripts_raise_their_own_error_type(self):
        """The callers catch the error class of their script (DeploymentError, AcceptanceError, RehearsalError), not SystemExit."""
        for filename, error in (('deploy-memory.py', 'DeploymentError'), ('accept-native-clients.py', 'AcceptanceError'), ('rehearse-reliable-operations.py', 'RehearsalError')):
            with self.subTest(script=filename):
                module = load(filename)
                with self.assertRaises(getattr(module, error)):
                    module.bootstrap_password(self.secret(b'\xef\xbb\xbfx\n'))

    def test_no_script_reads_the_bootstrap_password_file_by_hand(self):
        """Every reader of `bootstrap_password` under scripts/ goes through `bootstrap_password(...)`: a `.read_text()` (with or without `.strip()`) on that file is red."""
        offenders = []
        for path in sorted((ROOT / 'scripts').glob('*.py')):
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if "'bootstrap_password')" in line and re.search(r"'bootstrap_password'\)\s*\)?\.read_(text|bytes)\(", line):
                    offenders.append(f'{path.name}:{number}')
        self.assertEqual(offenders, [])
        for filename in SCRIPTS:
            with self.subTest(script=filename):
                calls = [n for n in ast.walk(ast.parse((ROOT / 'scripts' / filename).read_text(encoding='utf-8')))
                         if isinstance(n, ast.Call) and getattr(n.func, 'id', getattr(n.func, 'attr', '')) == 'bootstrap_password']
                self.assertEqual(len(calls), {'deploy-memory.py': 2}.get(filename, 1), 'the round trip and the runtime check in deploy-memory.py; one login in each of the others')


if __name__ == '__main__':
    unittest.main()
