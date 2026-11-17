"""C-01 / CA-02, CA-08 (part): copies are encrypted with `age` for public-key recipients; the private key never exists on the server side of the test."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from memory_platform import admin, backup, config
from memory_platform.admin import main
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_manifest import cli
from memory_platform.tests.test_store import create_core

ROOT = Path(__file__).resolve().parents[3]
PRIVATE_MARK = 'AGE-SECRET' + '-KEY-'  # split: this very file must not contain the marker it forbids elsewhere
# An age private key: the marker, an optional `PQ-` (the hybrid identity), '1' and a run of bech32 characters (58 in an x25519 key; much longer in a PQ one; a
# key wrapped over several lines still gives a long first run). The tree scan looks for this, not for the bare marker, so the manuals may name the prefix
# (`AGE-SECRET-KEY-…`) when they explain that a recipients file holding one is rejected.
BECH32 = '023456789ACDEFGHJKLMNPQRSTUVWXYZ'
PRIVATE_KEY = re.compile((PRIVATE_MARK + '(?:PQ-)?1[' + BECH32 + ']{20,}').encode())


def new_identity(root, name='key'):
    """(public recipient, path of the private identity) of a fresh age key, generated here and removed with the workspace."""
    identity = root / (name + '.txt')
    result = subprocess.run(['age-keygen', '-o', str(identity)], capture_output=True, text=True, check=True)
    public = re.search(r'(age1[0-9a-z]+)', result.stderr + identity.read_text(encoding='utf-8')).group(1)
    return public, identity


def recipients_file(root, *keys, name='recipients.txt'):
    path = root / name
    path.write_text('# public keys only\n' + '\n'.join(keys) + '\n', encoding='utf-8')
    return path


@unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen') and shutil.which('pg_dump'), 'age and the PostgreSQL client tools are required')
class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        self.marker = 'KAIROS-ROW-MARKER-' + uuid.uuid4().hex
        content = 'A seeded row: ' + self.marker
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Marker', 'content': content, 'tags': [],
                    'source': {'uri': 'fixture://encryption', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}}
        self.store.publish_document(self.actor, self.project, document)
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': '', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': ''}

    def backup(self, destination, **environ):
        with patch.dict(os.environ, dict(self.environ, **environ)), contextlib.redirect_stdout(io.StringIO()) as out:
            main(['backup', '--output', str(destination)])
        return json.loads(out.getvalue())

    def refused(self, destination, **environ):
        """The exit text of a `backup` that is refused, with nothing run and nothing written."""
        with patch.dict(os.environ, dict(self.environ, **environ)), patch.object(backup.subprocess, 'run') as run:
            with self.assertRaises(SystemExit) as raised:
                with contextlib.redirect_stdout(io.StringIO()):
                    main(['backup', '--output', str(destination)])
        run.assert_not_called()
        return str(raised.exception.code)

    def test_the_copy_is_age_ciphertext_and_restores_only_after_decrypting_with_the_private_key(self):
        """CA-02."""
        with workspace() as root:
            public, identity = new_identity(root)
            keys = recipients_file(root, public)
            sink = root / 'out'
            sink.mkdir()
            report = self.backup(sink / 'kairos-before-20261116T090000000000Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(keys))
            copy = Path(report['path'])
            self.assertEqual(copy.name, 'kairos-before-20261116T090000000000Z.dump.age')
            data = copy.read_bytes()
            self.assertFalse(data.startswith(b'PGDMP'))
            self.assertTrue(data.startswith(b'age-encryption.org/v1'))
            self.assertNotIn(self.marker.encode(), data)
            self.assertEqual(sorted(path.name for path in sink.iterdir()), sorted([copy.name, copy.name + '.json']), 'the plain dump is not left behind')
            self.assertNotEqual(subprocess.run(['pg_restore', '-l', str(copy)], capture_output=True).returncode, 0, 'the ciphertext is not a dump')
            plain = root / 'decrypted.dump'
            subprocess.run(['age', '--decrypt', '-i', str(identity), '-o', str(plain), str(copy)], check=True, capture_output=True)
            self.assertTrue(plain.read_bytes().startswith(b'PGDMP'))
            listing = subprocess.run(['pg_restore', '--file=-', str(plain)], capture_output=True, text=True, check=True).stdout
            self.assertIn(self.marker, listing, 'positive control: after decrypting, the seeded row is in the dump')
            manifest = json.loads(Path(str(copy) + '.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['content_sha256'], hashlib.sha256(plain.read_bytes()).hexdigest())
            self.assertEqual(manifest['content_bytes'], plain.stat().st_size)

    def test_the_manifest_marks_encrypted_and_hashes_the_ciphertext_so_it_verifies_without_the_key(self):
        with workspace() as root:
            public, _ = new_identity(root)
            keys = recipients_file(root, public)
            copy = Path(self.backup(root / 'kairos-before-20261116T090000000001Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(keys))['path'])
            manifest = json.loads(Path(str(copy) + '.json').read_text(encoding='utf-8'))
            data = copy.read_bytes()
            self.assertIs(manifest['encrypted'], True)
            self.assertEqual((manifest['sha256'], manifest['bytes']), (hashlib.sha256(data).hexdigest(), len(data)))
            self.assertNotEqual(manifest['sha256'], manifest['content_sha256'])
            self.assertEqual(manifest['recipients'], [hashlib.sha256(public.encode()).hexdigest()])
            self.assertNotIn(public, json.dumps(manifest))  # digests of the recipients only
            with patch.dict(os.environ, {'MEMORY_BACKUP_RECIPIENTS_FILE': ''}):
                self.assertTrue(backup.verify_backup(copy)['encrypted'])  # no key, no recipients file: the ciphertext is enough
            if os.name == 'posix':
                self.assertEqual((copy.stat().st_mode & 0o777, Path(str(copy) + '.json').stat().st_mode & 0o777), (0o600, 0o600))
            altered = bytearray(data)
            altered[100] ^= 0x01
            copy.write_bytes(bytes(altered))
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')

    def test_a_copy_encrypted_for_other_recipients_than_the_configured_ones_is_refused(self):
        with workspace() as root:
            mine, _ = new_identity(root, 'mine')
            other, _ = new_identity(root, 'other')
            copy = Path(self.backup(root / 'kairos-before-20261116T090000000002Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, other)))['path'])
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy, recipients_file=str(recipients_file(root, mine, name='mine.txt')))
            self.assertEqual(raised.exception.code, 'backup_recipients_mismatch')
            self.assertNotIn(str(root), str(raised.exception))
            self.assertEqual(backup.verify_backup(copy, recipients_file=str(recipients_file(root, other, mine, name='both.txt')))['encrypted'], True)  # one of its recipients
            with patch.dict(os.environ, {'MEMORY_BACKUP_RECIPIENTS_FILE': str(recipients_file(root, mine, name='env.txt'))}):
                failure, _ = cli('verify-backup', '--backup', str(copy))
            self.assertTrue(failure.startswith('backup_recipients_mismatch: '), failure)

    def test_with_encryption_required_and_no_recipients_the_copy_fails_naming_the_variable_and_writes_nothing(self):
        """CA-02: nothing in the clear, not even a partial file or the directory."""
        with workspace() as root:
            target = root / 'new-directory' / 'kairos-before-20261116T090000000003Z.dump'
            for blank in ('', '   '):
                text = self.refused(target, MEMORY_BACKUP_REQUIRE_ENCRYPTION='1', MEMORY_BACKUP_RECIPIENTS_FILE=blank)
                self.assertTrue(text.startswith('backup_encryption_required: '), text)
                self.assertIn('MEMORY_BACKUP_RECIPIENTS_FILE', text)
            self.assertEqual(list(root.iterdir()), [])

    def test_without_the_requirement_and_without_recipients_the_copy_is_plain_as_before(self):
        with workspace() as root:
            for value in ('', '0', 'false', 'off', 'no'):
                copy = root / f'kairos-before-2026111609000000{len(value):04d}Z.dump'
                report = self.backup(copy, MEMORY_BACKUP_REQUIRE_ENCRYPTION=value)
                self.assertEqual((report['encrypted'], copy.read_bytes()[:5]), (False, b'PGDMP'))
                self.assertEqual(report['path'], str(copy))

    def test_recipients_that_cannot_be_used_stop_the_copy_before_anything_is_written(self):
        with workspace() as root:
            public, identity = new_identity(root)
            leaking = recipients_file(root, public, identity.read_text(encoding='utf-8').splitlines()[-1], name='with-private.txt')
            empty = root / 'empty.txt'
            empty.write_text('# nothing\n\n', encoding='utf-8')
            cases = {'a private key in the recipients file': (leaking, 'backup_recipients_invalid', 'private key'), 'no recipients': (empty, 'backup_recipients_invalid', 'no recipient'),
                     'a file that is not there': (root / 'missing.txt', 'backup_recipients_invalid', 'cannot be read')}
            for label, (path, code, words) in cases.items():
                for require in ('', '1'):  # a configured file is never skipped, whatever the requirement says
                    with self.subTest(label, require=require):
                        target = root / 'sink' / 'kairos-before-20261116T090000000004Z.dump'
                        text = self.refused(target, MEMORY_BACKUP_RECIPIENTS_FILE=str(path), MEMORY_BACKUP_REQUIRE_ENCRYPTION=require)
                        self.assertTrue(text.startswith(code + ': '), text)
                        self.assertIn(words, text)
                        self.assertIn('MEMORY_BACKUP_RECIPIENTS_FILE', text)
                        self.assertNotIn(str(root), text, 'the path of a key file is not printed')
                        self.assertNotIn(PRIVATE_MARK, text)
                        self.assertFalse((root / 'sink').exists())

    def test_without_the_age_binary_the_copy_is_refused_not_written_in_the_clear(self):
        with workspace() as root:
            public, _ = new_identity(root)
            keys = recipients_file(root, public)
            target = root / 'sink' / 'kairos-before-20261116T090000000005Z.dump'
            with patch.object(backup.shutil, 'which', return_value=None):
                text = self.refused(target, MEMORY_BACKUP_RECIPIENTS_FILE=str(keys))
            self.assertTrue(text.startswith('backup_encryption_unavailable: '), text)
            self.assertFalse((root / 'sink').exists())

    def test_a_failing_age_leaves_no_ciphertext_and_no_plain_dump(self):
        with workspace() as root:
            public, _ = new_identity(root)
            keys = recipients_file(root, public)
            real_popen = subprocess.Popen
            seen = []

            def popen(command, **kwargs):
                if command[0] == 'age':
                    seen.append(command)
                    # a program that had started writing, reads its input to the end and fails printing a detail and a path
                    script = 'printf "age-encryption.org/v1 half" > "$1"; cat > /dev/null; printf "secret detail %s" "$2" >&2; exit 1'
                    return real_popen(['sh', '-c', script, 'age', command[command.index('-o') + 1], str(keys)], **kwargs)
                return real_popen(command, **kwargs)
            sink = root / 'sink'
            sink.mkdir()
            with patch.object(backup.subprocess, 'Popen', popen), patch.dict(os.environ, dict(self.environ, MEMORY_BACKUP_RECIPIENTS_FILE=str(keys))):
                with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(io.StringIO()):
                    main(['backup', '--output', str(sink / 'kairos-before-20261116T090000000006Z.dump')])
            self.assertTrue(seen)
            self.assertTrue(str(raised.exception.code).startswith('backup_encryption_failed: '))
            self.assertNotIn('secret detail', str(raised.exception.code))
            self.assertNotIn(str(root), str(raised.exception.code))
            self.assertEqual(list(sink.iterdir()), [])

    def test_the_plain_dump_does_not_outlive_the_encryption_even_for_the_moments_before_publishing(self):
        with workspace() as root:
            public, _ = new_identity(root)
            seen = []
            real = os.replace

            def watch(source, target):
                if str(target).endswith('.dump.age'):  # the moment the ciphertext is published
                    seen.append(sorted(path.name for path in Path(source).parent.iterdir()))
                return real(source, target)
            with patch.object(backup.os, 'replace', watch):
                self.backup(root / 'kairos-before-20261116T090000000009Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))
            self.assertEqual(len(seen), 1)
            self.assertNotIn('dump', seen[0], 'the plain dump was still on disk when the copy was published')
            self.assertIn('dump.age', seen[0])

    def test_an_existing_ciphertext_blocks_the_name_of_the_plain_one_and_the_other_way_round(self):
        with workspace() as root:
            public, _ = new_identity(root)
            keys = recipients_file(root, public)
            Path(root / 'kairos-before-20261116T090000000007Z.dump.age').write_bytes(b'mine')
            with patch.dict(os.environ, dict(self.environ, MEMORY_BACKUP_RECIPIENTS_FILE=str(keys))), patch.object(backup.subprocess, 'run') as run:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(['backup', '--output', str(root / 'kairos-before-20261116T090000000007Z.dump')])
            run.assert_not_called()
            self.assertEqual(Path(root / 'kairos-before-20261116T090000000007Z.dump.age').read_bytes(), b'mine')

    def test_an_output_that_already_ends_in_age_keeps_its_name(self):
        with workspace() as root:
            public, _ = new_identity(root)
            report = self.backup(root / 'kairos-before-20261116T090000000008Z.dump.age', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))
            self.assertEqual(Path(report['path']).name, 'kairos-before-20261116T090000000008Z.dump.age')


class EncryptionSettingsTests(unittest.TestCase):
    def test_the_requirement_is_read_strictly_and_a_typo_fails_closed(self):
        for raw, expected in (('1', True), ('true', True), ('TRUE', True), ('yes', True), ('on', True), ('', False), ('0', False), ('false', False), ('no', False), ('off', False)):
            self.assertIs(config.backup_require_encryption({'MEMORY_BACKUP_REQUIRE_ENCRYPTION': raw}), expected, raw)
        self.assertIs(config.backup_require_encryption({}), False)
        for raw in ('maybe', '2', 'enable', 'y'):
            with self.assertRaises(ValueError, msg=raw) as raised:
                config.backup_require_encryption({'MEMORY_BACKUP_REQUIRE_ENCRYPTION': raw})
            self.assertIn('MEMORY_BACKUP_REQUIRE_ENCRYPTION', str(raised.exception))

    def test_the_recipients_file_is_blank_or_a_path(self):
        self.assertIsNone(config.backup_recipients_file({}))
        self.assertIsNone(config.backup_recipients_file({'MEMORY_BACKUP_RECIPIENTS_FILE': '  '}))
        self.assertEqual(config.backup_recipients_file({'MEMORY_BACKUP_RECIPIENTS_FILE': ' /run/keys/recipients.txt '}), '/run/keys/recipients.txt')


class NoPrivateKeyTests(unittest.TestCase):
    """CA-08: no private key in the repository or in what the image of the test target carries; `age` is pinned in the two images that run it."""

    def test_the_scan_catches_every_form_of_a_private_key_and_not_the_prose_prefix(self):
        body = (BECH32*3)[:58]
        for sample in (PRIVATE_MARK + '1' + body,                        # x25519
                       PRIVATE_MARK + 'PQ-1' + (BECH32*40)[:1900],       # hybrid post-quantum identity
                       PRIVATE_MARK + '1' + body[:30] + chr(10) + body[30:],  # wrapped: the first line still holds a long run
                       'key = ' + PRIVATE_MARK + '1' + body + chr(10)):
            self.assertTrue(PRIVATE_KEY.search(sample.encode()), sample[:40])
        for prose in (PRIVATE_MARK + '…', PRIVATE_MARK + ' and the public one', PRIVATE_MARK + '1' + body[:10], 'age1' + body.lower()):
            self.assertFalse(PRIVATE_KEY.search(prose.encode()), prose)

    def test_no_file_of_the_tree_holds_an_age_private_key(self):
        found = []
        for base, folders, files in os.walk(ROOT):
            folders[:] = [name for name in folders if name not in ('.git', 'node_modules', '__pycache__', '.private')]
            for name in files:
                path = Path(base) / name
                try:
                    if path.stat().st_size > 5_000_000:
                        continue
                    if PRIVATE_KEY.search(path.read_bytes()):
                        found.append(str(path.relative_to(ROOT)))
                except OSError:
                    continue
        self.assertEqual(found, [])

    def test_the_operator_and_test_images_install_age_at_a_pinned_version(self):
        text = (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text(encoding='utf-8')
        for stage in ('operator', 'test'):
            block = re.search(r'FROM \S+ AS ' + stage + r'\r?\n(.*?)(?=\r?\nFROM |\Z)', text, re.S).group(1)
            self.assertRegex(block, r'\bage=\$\{AGE_VERSION\}', stage)
            self.assertRegex(block, r'ARG AGE_VERSION=\d+\.\d+\.\d+-\S+', stage)
        self.assertNotIn(PRIVATE_MARK, text)


if __name__ == '__main__':
    unittest.main()
