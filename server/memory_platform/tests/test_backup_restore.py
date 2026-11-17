"""C-01 / CA-05 (operator side): `restore-check --from-manifest` restores a verified copy into an empty memory_restore_* database and compares the tables with the manifest,
without ever reading the live database."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from memory_platform import admin, backup
from memory_platform.admin import main, store_fingerprints
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_store import create_core


@unittest.skipUnless(shutil.which('pg_dump') and shutil.which('pg_restore'), 'PostgreSQL client tools are required')
class RestoreFromManifestTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        self.store, self.actor, self.project = create_core()
        content = 'A synthetic source for the restore comparison.'
        self.store.publish_document(self.actor, self.project, {
            'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Source', 'content': content, 'tags': [],
            'source': {'uri': 'fixture://restore', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
            'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}})
        values = conninfo_to_dict(self.store.dsn)
        self.name = 'memory_restore_' + uuid.uuid4().hex[:16]
        maintenance = make_conninfo(**dict(values, dbname='postgres'))
        self.target = make_conninfo(**dict(values, dbname=self.name))
        with psycopg.connect(maintenance, autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.name)))

        def drop():
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(self.name)))
        self.addCleanup(drop)
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': '', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': ''}

    def run_command(self, *argv):
        output = io.StringIO()
        with patch.dict(os.environ, self.environ), contextlib.redirect_stdout(output):
            try:
                main(list(argv))
            except SystemExit as exit_:
                return str(exit_.code), output.getvalue()
        return None, output.getvalue()

    def make_copy(self, root):
        copy = root / 'kairos-before-20261116T090000000000Z.dump'
        failure, _ = self.run_command('backup', '--output', str(copy))
        self.assertIsNone(failure)
        target_file = root / 'target.dsn'
        target_file.write_text(self.target, encoding='utf-8')
        return copy, target_file

    def test_a_verified_copy_restores_and_matches_its_manifest_without_reading_the_live_database(self):
        with workspace() as root:
            copy, target_file = self.make_copy(root)
            with self.store.transaction() as c:  # the live database moves on after the copy: the manifest, not the live state, is what the restore must match
                c.execute("INSERT INTO memory.audit_events(action,resource_id) VALUES('after_the_copy','x')")
            calls = []
            real = admin.store_fingerprints
            with patch.object(admin, 'store_fingerprints', side_effect=lambda store: calls.append(store.dsn) or real(store)):
                failure, out = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file), '--from-manifest')
            self.assertIsNone(failure, failure)
            report = json.loads(out)
            self.assertEqual(report['status'], 'restored_and_content_verified')
            self.assertEqual(calls, [admin.guarded_dsn(self.target)], 'only the restored database was read (with the connect timeout and keepalives every admin connection carries)')
            manifest = json.loads(Path(str(copy) + '.json').read_text(encoding='utf-8'))
            self.assertEqual(report['tables'], manifest['fingerprints'])

    def test_a_copy_that_does_not_verify_is_not_restored(self):
        with workspace() as root:
            copy, target_file = self.make_copy(root)
            data = bytearray(copy.read_bytes())
            data[len(data) // 2] ^= 0xFF
            copy.write_bytes(bytes(data))
            with patch.object(admin.subprocess, 'run') as run:
                failure, out = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file), '--from-manifest')
            self.assertTrue(failure.startswith('backup_checksum_mismatch: '), failure)
            run.assert_not_called()
            self.assertEqual(out, '')

    def test_a_difference_between_the_restored_tables_and_the_manifest_names_the_tables(self):
        with workspace() as root:
            copy, target_file = self.make_copy(root)
            path = Path(str(copy) + '.json')
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['fingerprints']['documents']['sha256'] = '0' * 64  # a manifest that does not describe the dump (the file itself is untouched)
            path.write_text(json.dumps(manifest), encoding='utf-8')
            failure, out = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file), '--from-manifest')
            self.assertTrue(failure.startswith('backup_restore_mismatch: '), failure)
            self.assertIn('documents', failure)
            self.assertNotIn('postgresql://', failure)
            self.assertEqual(out, '')

    def test_an_encrypted_copy_cannot_be_restored_here_and_says_why(self):
        with workspace() as root:
            copy, target_file = self.make_copy(root)
            encrypted = root / 'kairos-before-20261116T090000000001Z.dump.age'
            payload = b'age-encryption.org/v1\n' + bytes(range(100))
            encrypted.write_bytes(payload)
            manifest = json.loads(Path(str(copy) + '.json').read_text(encoding='utf-8'))
            manifest.update(file=encrypted.name, sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload), encrypted=True, recipients=['a' * 64])
            Path(str(encrypted) + '.json').write_text(json.dumps(manifest), encoding='utf-8')
            with patch.object(admin.subprocess, 'run') as run:
                failure, _ = self.run_command('restore-check', '--backup', str(encrypted), '--target-dsn-file', str(target_file), '--from-manifest')
            self.assertTrue(failure.startswith('backup_encrypted: '), failure)
            run.assert_not_called()

    def test_the_target_safeguards_still_apply_in_this_mode(self):
        with workspace() as root:
            copy, _ = self.make_copy(root)
            live = root / 'live.dsn'
            live.write_text(self.store.dsn, encoding='utf-8')
            with patch.object(admin.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                failure, _ = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(live), '--from-manifest')
            self.assertEqual(failure, '2')  # parser.error: the live database is not a restore target
            run.assert_not_called()
            # and a restore target that is not empty is refused too: restore once, then again
            target_file = root / 'target.dsn'
            target_file.write_text(self.target, encoding='utf-8')
            self.assertIsNone(self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file), '--from-manifest')[0])
            with patch.object(admin.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                failure, _ = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file), '--from-manifest')
            self.assertEqual(failure, '2')
            run.assert_not_called()

    def test_the_comparison_with_the_live_database_is_still_the_default(self):
        with workspace() as root:
            copy, target_file = self.make_copy(root)
            failure, out = self.run_command('restore-check', '--backup', str(copy), '--target-dsn-file', str(target_file))
            self.assertIsNone(failure, failure)
            self.assertEqual(json.loads(out)['tables'], store_fingerprints(self.store))

    def encrypted_copy(self, root):
        """(ciphertext, manifest, decrypted dump, target file): the copy as the server makes it and as the operator decrypts it with a key the server never had."""
        import subprocess
        from memory_platform.tests.test_backup_encryption import new_identity, recipients_file
        public, identity = new_identity(root)
        self.environ = dict(self.environ, MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))
        failure, out = self.run_command('backup', '--output', str(root / 'kairos-before-20261116T090000000002Z.dump'))
        self.assertIsNone(failure, failure)
        ciphertext = Path(json.loads(out)['path'])
        plain = root / 'decrypted.dump'
        subprocess.run(['age', '--decrypt', '-i', str(identity), '-o', str(plain), str(ciphertext)], check=True, capture_output=True)
        target_file = root / 'target.dsn'
        target_file.write_text(self.target, encoding='utf-8')
        return ciphertext, Path(str(ciphertext) + '.json'), plain, target_file

    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'), 'age is required')
    def test_a_decrypted_copy_restores_against_the_manifest_of_its_ciphertext(self):
        """The runbook: decrypt with the private key, then `restore-check --from-manifest <manifest of the .age>`: the dump is compared with content_sha256 first."""
        with workspace() as root:
            ciphertext, manifest_file, plain, target_file = self.encrypted_copy(root)
            failure, out = self.run_command('restore-check', '--backup', str(plain), '--target-dsn-file', str(target_file), '--from-manifest', str(manifest_file))
            self.assertIsNone(failure, failure)
            report = json.loads(out)
            self.assertEqual(report['status'], 'restored_and_content_verified')
            self.assertEqual(report['tables'], json.loads(manifest_file.read_text(encoding='utf-8'))['fingerprints'])

    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'), 'age is required')
    def test_a_decrypted_copy_with_one_altered_byte_is_refused_before_restoring(self):
        with workspace() as root:
            ciphertext, manifest_file, plain, target_file = self.encrypted_copy(root)
            data = bytearray(plain.read_bytes())
            data[len(data) // 2] ^= 0x01
            plain.write_bytes(bytes(data))
            with patch.object(admin.subprocess, 'run') as run:
                failure, out = self.run_command('restore-check', '--backup', str(plain), '--target-dsn-file', str(target_file), '--from-manifest', str(manifest_file))
            self.assertTrue(failure.startswith('backup_checksum_mismatch: '), failure)
            run.assert_not_called()
            self.assertEqual(out, '')

    @unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'), 'age is required')
    def test_the_ciphertext_is_still_refused_even_with_an_explicit_manifest(self):
        with workspace() as root:
            ciphertext, manifest_file, plain, target_file = self.encrypted_copy(root)
            with patch.object(admin.subprocess, 'run') as run:
                failure, _ = self.run_command('restore-check', '--backup', str(ciphertext), '--target-dsn-file', str(target_file), '--from-manifest', str(manifest_file))
            self.assertTrue(failure.startswith('backup_encrypted: '), failure)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
