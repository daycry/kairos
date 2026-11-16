"""C-01 / CA-01: every copy has a manifest `<copy>.json`; `admin verify-backup` recomputes the sha256 and refuses anything that is not the file the manifest describes."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch
import uuid

from memory_platform import admin, backup
from memory_platform.admin import main, store_fingerprints
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_store import create_core

PAYLOAD = b'PGDMP' + bytes(range(256)) * 40


def write_copy(root, name='kairos-before-20261116T090000000000Z.dump', payload=PAYLOAD, **changes):
    """A copy and a manifest written here, independently of `backup.py`, the way the tool documents them."""
    copy = root / name
    copy.write_bytes(payload)
    manifest = {'format': 1, 'file': name, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'content_sha256': hashlib.sha256(payload).hexdigest(),
                'content_bytes': len(payload), 'schema_version': 12, 'created_at': '2026-11-16T09:00:00.000000Z', 'encrypted': False,
                'fingerprints': {'actors': {'rows': 1, 'sha256': 'a' * 64}}}
    manifest.update(changes)
    Path(str(copy) + '.json').write_text(json.dumps(manifest), encoding='utf-8')
    return copy


def cli(*argv):
    """(exit text or None, stdout) of the real command line; `Settings.from_env` must not be needed by verify-backup."""
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            main(list(argv))
    except SystemExit as exit_:
        return str(exit_.code), output.getvalue()
    return None, output.getvalue()


class VerifyBackupTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup must not need the database settings')))

    def test_an_intact_copy_verifies_and_the_command_prints_its_facts(self):
        with workspace() as root:
            copy = write_copy(root)
            manifest = backup.verify_backup(copy)
            self.assertEqual((manifest['bytes'], manifest['encrypted']), (len(PAYLOAD), False))
            failure, out = cli('verify-backup', '--backup', str(copy))
            self.assertIsNone(failure)
            report = json.loads(out)
            self.assertEqual((report['status'], report['bytes'], report['sha256'], report['schema_version']), ('verified', len(PAYLOAD), hashlib.sha256(PAYLOAD).hexdigest(), 12))

    def test_one_altered_byte_is_a_checksum_mismatch(self):
        """CA-01: the same size, one byte different."""
        with workspace() as root:
            copy = write_copy(root)
            data = bytearray(copy.read_bytes())
            data[2000] ^= 0x01
            copy.write_bytes(bytes(data))
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            failure, out = cli('verify-backup', '--backup', str(copy))
            self.assertTrue(failure.startswith('backup_checksum_mismatch: '), failure)
            self.assertEqual(out, '')

    def test_a_truncated_copy_says_so(self):
        with workspace() as root:
            copy = write_copy(root)
            copy.write_bytes(PAYLOAD[:-1])
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            self.assertIn('truncated', str(raised.exception))
            copy.write_bytes(PAYLOAD + b'x')  # longer is also a mismatch, and not called truncated
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertNotIn('truncated', str(raised.exception))

    def test_a_copy_without_a_manifest_is_not_a_copy(self):
        with workspace() as root:
            copy = write_copy(root)
            Path(str(copy) + '.json').unlink()
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_missing')
            self.assertTrue(cli('verify-backup', '--backup', str(copy))[0].startswith('backup_manifest_missing: '))
            with self.assertRaises(backup.BackupError) as raised:  # nor is a file that does not exist
                backup.verify_backup(root / 'nothing.dump')
            self.assertEqual(raised.exception.code, 'backup_not_found')

    def test_a_manifest_that_cannot_be_trusted_is_refused_by_shape_without_leaking_paths(self):
        broken = {'not json': None, 'not an object': '[1]', 'format 2': {'format': 2}, 'other file': {'file': 'other.dump'}, 'bad sha': {'sha256': 'xyz'},
                  'bytes as text': {'bytes': '10'}, 'bool as number': {'bytes': True}, 'no fingerprints': {'fingerprints': []}, 'bad time': {'created_at': 'yesterday'},
                  'encrypted as text': {'encrypted': 'false'}, 'negative size': {'bytes': -1}}
        for label, change in broken.items():
            with self.subTest(label), workspace() as root:
                copy = write_copy(root)
                path = Path(str(copy) + '.json')
                if label == 'not json':
                    path.write_text('{ not json', encoding='utf-8')
                elif label == 'not an object':
                    path.write_text('[1]', encoding='utf-8')
                else:
                    copy = write_copy(root, **change)
                with self.assertRaises(backup.BackupError) as raised:
                    backup.verify_backup(copy)
                self.assertEqual(raised.exception.code, 'backup_manifest_invalid')
                self.assertNotIn(str(root), str(raised.exception))
                self.assertNotIn(os.sep + 'kairos-admin-test-', str(raised.exception))

    def test_a_manifest_edited_to_fit_the_wrong_facts_does_not_verify(self):
        with workspace() as root:
            copy = write_copy(root, sha256='0' * 64)
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            copy = write_copy(root, bytes=len(PAYLOAD) + 5)
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            copy = write_copy(root, encrypted=True)  # a plain dump declared as encrypted
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_invalid')
            copy = write_copy(root, payload=b'not a dump at all')  # neither a custom-format dump nor an age file
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_invalid')

    def test_a_symbolic_link_is_not_followed(self):
        with workspace() as root:
            real = write_copy(root, name='kairos-before-20261116T090000000001Z.dump')
            link = root / 'kairos-before-20261116T090000000002Z.dump'
            try:
                link.symlink_to(real)
            except OSError:
                self.skipTest('symbolic links are not available here')
            Path(str(link) + '.json').write_text(Path(str(real) + '.json').read_text(encoding='utf-8').replace(real.name, link.name), encoding='utf-8')
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(link)
            self.assertEqual(raised.exception.code, 'backup_not_found')


class BackupWritesManifestTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': ''}

    def run_backup(self, root, name='kairos-before-20261116T090000000000Z.dump'):
        copy = root / name
        with patch.dict(os.environ, self.environ), contextlib.redirect_stdout(io.StringIO()) as out:
            main(['backup', '--output', str(copy)])
        return copy, json.loads(out.getvalue())

    def test_backup_writes_the_copy_and_its_manifest_with_the_facts_of_one_snapshot(self):
        if not backup.shutil.which('pg_dump'):
            self.skipTest('PostgreSQL client tools are required')
        with workspace() as root:
            copy, report = self.run_backup(root)
            manifest_file = Path(str(copy) + '.json')
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            data = copy.read_bytes()
            self.assertTrue(data.startswith(b'PGDMP'))
            self.assertEqual((manifest['sha256'], manifest['bytes']), (hashlib.sha256(data).hexdigest(), len(data)))
            self.assertEqual((manifest['content_sha256'], manifest['encrypted'], manifest['file'], manifest['format']), (manifest['sha256'], False, copy.name, 1))
            self.assertEqual(manifest['fingerprints'], store_fingerprints(self.store))
            with self.store.transaction() as c:
                self.assertEqual(manifest['schema_version'], c.execute('SELECT max(version) AS v FROM memory.schema_versions').fetchone()['v'])
            self.assertRegex(manifest['created_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$')
            self.assertEqual((report['status'], report['path'], report['bytes'], report['sha256']), ('backed_up', str(copy), len(data), manifest['sha256']))
            if os.name == 'posix':
                self.assertEqual((copy.stat().st_mode & 0o777, manifest_file.stat().st_mode & 0o777), (0o600, 0o600))
            self.assertEqual(sorted(path.name for path in root.iterdir()), sorted([copy.name, manifest_file.name]), 'nothing else is left next to the copy')
            self.assertEqual(backup.verify_backup(copy)['sha256'], manifest['sha256'])
            self.assertIsNone(cli_without_settings('verify-backup', '--backup', str(copy))[0])
            altered = bytearray(data)
            altered[len(altered) // 2] ^= 0xFF
            copy.write_bytes(bytes(altered))
            self.assertTrue(cli_without_settings('verify-backup', '--backup', str(copy))[0].startswith('backup_checksum_mismatch'))

    def test_a_write_during_the_dump_is_in_neither_the_copy_nor_the_manifest(self):
        """The fingerprints and the dump come from one snapshot: a row written between them would make a good copy fail its restore comparison."""
        if not backup.shutil.which('pg_dump') or not backup.shutil.which('pg_restore'):
            self.skipTest('PostgreSQL client tools are required')
        marker = 'LATE-ROW-' + uuid.uuid4().hex
        content = 'written while the dump runs ' + marker
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Late', 'content': content, 'tags': [],
                    'source': {'uri': 'fixture://late', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}}
        before = store_fingerprints(self.store)
        real_run = subprocess.run

        def write_then_dump(command, **kwargs):
            if command[0] == 'pg_dump':
                self.store.publish_document(self.actor, self.project, document)  # another session commits after the snapshot was taken
            return real_run(command, **kwargs)
        with workspace() as root, patch.object(backup.subprocess, 'run', write_then_dump):
            copy, _ = self.run_backup(root)
            manifest = json.loads(Path(str(copy) + '.json').read_text(encoding='utf-8'))
            listing = real_run(['pg_restore', '--file=-', str(copy)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(manifest['fingerprints'], before)
        self.assertNotIn(marker, listing)
        self.assertNotEqual(store_fingerprints(self.store), before, 'positive control: the row was written')

    def test_a_failed_dump_leaves_nothing_that_looks_like_a_copy(self):
        with workspace() as root:
            def failing(command, **kwargs):
                Path(command[command.index('--file') + 1]).write_bytes(b'PGDMP half a dump')  # the dump had started
                raise subprocess.CalledProcessError(1, command)
            with patch.object(admin.subprocess, 'run', failing), patch.dict(os.environ, self.environ), self.assertRaises(subprocess.CalledProcessError):
                main(['backup', '--output', str(root / 'kairos-before-20261116T090000000000Z.dump')])
            self.assertEqual(list(root.iterdir()), [], 'no copy, no manifest and no partial directory is left')

    def test_a_stop_while_dumping_leaves_nothing_and_a_crash_between_the_two_renames_leaves_an_invalid_copy(self):
        with workspace() as root:
            def terminated(command, **kwargs):
                Path(command[command.index('--file') + 1]).write_bytes(b'PGDMP first bytes')
                os.kill(os.getpid(), signal.SIGTERM)  # `docker stop`, or the timeout of the deployment
            before = signal.getsignal(signal.SIGTERM)
            if os.name != 'posix':
                self.skipTest('SIGTERM handling is checked on POSIX')
            with patch.object(admin.subprocess, 'run', terminated), patch.dict(os.environ, self.environ), self.assertRaises(SystemExit):
                main(['backup', '--output', str(root / 'kairos-before-20261116T090000000000Z.dump')])
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(signal.getsignal(signal.SIGTERM), before, 'the handler is only installed while the copy is written')
        with workspace() as root:
            real_replace = os.replace
            calls = []

            def crash_on_manifest(source, target):
                calls.append(Path(target).name)
                if str(target).endswith('.json') and not Path(source).name.startswith('.'):
                    raise OSError('simulated crash before the manifest was published')
                return real_replace(source, target)
            copy = root / 'kairos-before-20261116T090000000001Z.dump'

            def fake_dump(command, **kwargs):
                Path(command[command.index('--file') + 1]).write_bytes(PAYLOAD)
                return Mock(returncode=0)
            with patch.object(admin.subprocess, 'run', fake_dump), patch.object(backup.os, 'replace', crash_on_manifest), patch.dict(os.environ, self.environ), self.assertRaises(OSError):
                main(['backup', '--output', str(copy)])
            self.assertTrue(copy.exists() and not Path(str(copy) + '.json').exists())
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_missing')
            self.assertEqual([path.name for path in root.iterdir()], [copy.name], 'only the unverifiable copy; the partial directory is gone')

    def test_an_existing_copy_or_manifest_or_link_is_never_overwritten(self):
        with workspace() as root:
            copy = root / 'kairos-before-20261116T090000000000Z.dump'
            Path(str(copy) + '.json').write_text('{}', encoding='utf-8')  # an orphan manifest also blocks the name
            with patch.dict(os.environ, self.environ), patch.object(admin.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['backup', '--output', str(copy)])
            run.assert_not_called()
            self.assertEqual(Path(str(copy) + '.json').read_text(encoding='utf-8'), '{}')


def cli_without_settings(*argv):
    with patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup must not need the database settings')):
        return cli(*argv)


if __name__ == '__main__':
    unittest.main()
