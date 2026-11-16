"""Fix 1 of the phase 6 review: the plain dump never touches the disk when the copy is encrypted, a SIGTERM anywhere cleans up, orphan partials are swept, fingerprints take
bounded memory, `content_sha256` ties a decrypted copy to its manifest, and `prune` does not hash what it is about to delete."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import tracemalloc
import unittest
from unittest.mock import patch
import uuid

from memory_platform import admin, backup
from memory_platform.admin import main, store_fingerprints
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_encryption import new_identity, recipients_file
from memory_platform.tests.test_backup_manifest import PAYLOAD, cli, write_copy
from memory_platform.tests.test_backup_prune import copy as pruned_copy, names, run_prune, stamp
from memory_platform.tests.test_store import create_core

NEEDS_TOOLS = unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen') and shutil.which('pg_dump') and shutil.which('pg_restore'), 'age and the PostgreSQL client tools are required')


def legacy_fingerprints(connection):
    """The implementation before fix 1 (every table loaded whole), kept here as the reference the streaming one must equal."""
    from psycopg import sql
    result = {}
    tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
    for row in tables:
        values = connection.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t').format(sql.Identifier(row['table_name']))).fetchall()
        encoded = sorted(json.dumps(v['value'], sort_keys=True, ensure_ascii=False, default=str) for v in values)
        result[row['table_name']] = {'rows': len(encoded), 'sha256': hashlib.sha256('\n'.join(encoded).encode('utf-8')).hexdigest()}
    return result


def plain_dump_files(directory):
    """Names of the files under `directory` that hold (a piece of) a custom-format dump."""
    found = []
    for base, folders, files in os.walk(directory):
        for name in files:
            try:
                if b'PGDMP' in (Path(base) / name).read_bytes():
                    found.append(name)
            except OSError:
                continue
    return found


class Watched:
    """A process of `subprocess.Popen` whose stdin reports every write to `hook` (BufferedWriter cannot be patched in place)."""

    def __init__(self, process, hook):
        self.process = process
        self.stdin = Hooked(process.stdin, hook) if process.stdin else None

    def __getattr__(self, name):
        return getattr(self.process, name)


class Hooked:
    def __init__(self, inner, hook):
        self.inner, self.hook = inner, hook

    def write(self, data):
        self.hook()
        return self.inner.write(data)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def watching_popen(hook, processes, stubborn=False, slow=0):
    """With `stubborn`, `age` is replaced by a program that neither reads its input nor exits when it closes: only killing it ends it. With `slow`, it starts that many seconds late."""
    real = subprocess.Popen

    def popen(command, **kwargs):
        original = command[0]
        if stubborn and original == 'age':
            command = ['sleep', '120']
        elif slow and original == 'age':
            command = ['sh', '-c', f'sleep {slow}; exec "$0" "$@"', *command]
        process = real(command, **kwargs)
        command = [original]
        processes.append((command[0], process))
        return Watched(process, hook) if command[0] == 'age' else process
    return popen


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        with self.store.transaction() as c:
            c.execute('CREATE TABLE memory.zz_fingerprint_probe (n integer, body text)')  # no key: equal rows are possible
        self.addCleanup(self.drop)

    def drop(self):
        with self.store.transaction() as c:
            c.execute('DROP TABLE IF EXISTS memory.zz_fingerprint_probe')

    def fill(self, rows, size=40, duplicates=True):
        with self.store.transaction() as c:
            c.execute('TRUNCATE memory.zz_fingerprint_probe')
            for n in range(rows):
                c.execute('INSERT INTO memory.zz_fingerprint_probe VALUES (%s, %s)', (n % 11 if duplicates else n, ('ñandú-' if n % 3 else 'zeta-') + 'x' * (n % (8 if duplicates else size))))  # with duplicates: 264 different rows, each repeated

    def test_the_streamed_fingerprints_equal_the_old_ones_whatever_the_budget_with_duplicates_and_unicode(self):
        self.fill(700)
        with self.store.transaction() as c:
            expected = legacy_fingerprints(c)
            self.assertEqual(backup.table_fingerprints(c), expected)  # the whole schema, as the rest of the suite left it (a small budget over its tables would re-read them many times)
            for budget in (30_000, 2_000, 1):  # the probe table alone: several passes, many passes and a budget under any row
                self.assertEqual(backup.table_digest(c, 'zz_fingerprint_probe', budget), (expected['zz_fingerprint_probe']['rows'], expected['zz_fingerprint_probe']['sha256']), budget)
        self.assertEqual(expected['zz_fingerprint_probe']['rows'], 700)
        with self.store.transaction() as c:
            c.execute('TRUNCATE memory.zz_fingerprint_probe')
            self.assertEqual(backup.table_digest(c, 'zz_fingerprint_probe', 100), (0, hashlib.sha256(b'').hexdigest()), 'an empty table')
            self.assertEqual(backup.table_digest(c, 'zz_fingerprint_probe'), (0, hashlib.sha256(b'').hexdigest()))

    def test_a_manifest_made_by_the_old_code_still_matches(self):
        """The restore of an old copy compares with the fingerprints of ITS manifest, so the format must not move."""
        self.fill(300)
        with self.store.transaction() as c:
            self.assertEqual(store_fingerprints(self.store), legacy_fingerprints(c))

    def peak(self, rows, budget):
        self.fill(rows, size=600, duplicates=False)
        with self.store.transaction() as c:
            tracemalloc.start()
            try:
                backup.table_digest(c, 'zz_fingerprint_probe', budget)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

    def peak_legacy(self, rows):
        self.fill(rows, size=600, duplicates=False)
        with self.store.transaction() as c:
            tracemalloc.start()
            try:
                legacy_fingerprints(c)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

    def test_the_memory_does_not_grow_with_the_number_of_rows(self):
        small, large = self.peak(1000, 60_000), self.peak(4000, 60_000)
        self.assertLess(large, small * 1.5, (small, large))
        self.assertLess(large, 1_500_000, 'a table of 2.4 MB of rows is held in about the budget, not whole')
        self.assertGreater(self.peak_legacy(4000), 3 * large, 'positive control: the old code did hold the whole table')


@NEEDS_TOOLS
class PlainDumpNeverOnDiskTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        self.marker = 'KAIROS-ROW-MARKER-' + uuid.uuid4().hex
        content = 'A seeded row: ' + self.marker
        self.store.publish_document(self.actor, self.project, {
            'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Marker', 'content': content, 'tags': [],
            'source': {'uri': 'fixture://hardening', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
            'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}})
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': '', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': ''}

    def backup(self, destination, **environ):
        with patch.dict(os.environ, dict(self.environ, **environ)), contextlib.redirect_stdout(io.StringIO()) as out:
            main(['backup', '--output', str(destination)])
        return json.loads(out.getvalue())

    def test_with_recipients_no_file_of_the_directory_holds_the_dump_at_any_moment(self):
        with workspace() as root:
            public, _ = new_identity(root)
            sink = root / 'sink'
            sink.mkdir()
            sightings, processes = [], []
            real_replace = os.replace
            running = threading.Event()
            running.set()

            def look():
                sightings.append(plain_dump_files(sink))

            def replace(source, target):
                look()
                return real_replace(source, target)

            def monitor():  # the whole time, also while a slowed `age` is running
                while running.is_set():
                    look()
                    time.sleep(0.02)
            watcher = threading.Thread(target=monitor)
            watcher.start()
            try:
                with patch.object(backup.subprocess, 'Popen', watching_popen(look, processes, slow=1)), patch.object(backup.os, 'replace', replace):
                    report = self.backup(sink / 'kairos-before-20261116T090000000010Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))
            finally:
                running.clear()
                watcher.join()
            self.assertGreaterEqual(len(sightings), 20, 'the directory was inspected continuously while a slowed age ran, and when the copy was published')
            self.assertEqual([found for found in sightings if found], [])
            self.assertEqual(plain_dump_files(sink), [])
            self.assertEqual({name for name, process in processes}, {'pg_dump', 'age'})
            self.assertTrue(report['encrypted'])

    def test_positive_control_a_plain_copy_does_hold_the_dump_in_its_partial_directory(self):
        with workspace() as root:
            sightings = []
            real_replace = os.replace

            def replace(source, target):
                sightings.append(plain_dump_files(root))
                return real_replace(source, target)
            with patch.object(backup.os, 'replace', replace):
                self.backup(root / 'kairos-before-20261116T090000000011Z.dump')
            self.assertTrue(sightings[0], 'the inspector finds a dump when there is one')

    def test_a_sigterm_while_encrypting_leaves_no_dump_and_no_process(self):
        if os.name != 'posix':
            self.skipTest('SIGTERM handling is checked on POSIX')
        with workspace() as root:
            public, _ = new_identity(root)
            sink = root / 'sink'
            sink.mkdir()
            processes, sent = [], []

            def terminate():
                if not sent:
                    sent.append(True)
                    os.kill(os.getpid(), signal.SIGTERM)  # `docker stop`, or the timeout of the deployment, in the middle of the encryption
            before = signal.getsignal(signal.SIGTERM)
            with patch.object(backup.subprocess, 'Popen', watching_popen(terminate, processes, stubborn=True)), self.assertRaises(SystemExit) as raised:
                self.backup(sink / 'kairos-before-20261116T090000000012Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))
            self.assertEqual(raised.exception.code, 143)
            self.assertEqual(list(sink.iterdir()), [], 'not the dump, not the ciphertext, not the partial directory')
            self.assertEqual(plain_dump_files(sink), [])
            self.assertTrue(sent and processes)
            self.assertTrue(all(process.poll() is not None for name, process in processes), 'pg_dump and age were stopped, even an age that ignores its pipes')
            self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_a_sigterm_after_the_dump_while_the_copy_is_published_still_cleans_up(self):
        """The handler covers the whole of `create_backup`, not only `pg_dump`."""
        if os.name != 'posix':
            self.skipTest('SIGTERM handling is checked on POSIX')
        for stage in ('fsync_path', 'write_atomic'):
            with self.subTest(stage), workspace() as root:
                real = getattr(backup, stage)
                sent = []

                def stop(*args, **kwargs):
                    if not sent:
                        sent.append(True)
                        os.kill(os.getpid(), signal.SIGTERM)
                    return real(*args, **kwargs)
                with patch.object(backup, stage, stop), self.assertRaises(SystemExit) as raised:
                    self.backup(root / 'kairos-before-20261116T090000000013Z.dump')
                self.assertEqual(raised.exception.code, 143)
                self.assertEqual(list(root.iterdir()), [], stage)

    def test_the_copy_and_the_directory_are_flushed_before_and_after_the_renames(self):
        with workspace() as root:
            events = []
            real_replace, real_fsync = os.replace, backup.fsync_path
            with patch.object(backup.os, 'replace', lambda s, t: (events.append(('replace', Path(t).name)), real_replace(s, t))[1]), \
                    patch.object(backup, 'fsync_path', lambda path, directory=False: (events.append(('fsync-directory' if directory else 'fsync', Path(path).name)), real_fsync(path, directory))[1]):
                self.backup(root / 'kairos-before-20261116T090000000014Z.dump')
            copy_name = 'kairos-before-20261116T090000000014Z.dump'
            self.assertLess(events.index(('fsync', 'dump')), events.index(('replace', copy_name)), 'the copy is flushed before it is renamed into place')
            self.assertLess(events.index(('replace', copy_name + '.json')), max(i for i, e in enumerate(events) if e[0] == 'fsync-directory'), 'the directory is flushed after the renames')

    def test_old_orphan_partials_are_swept_by_a_backup_and_reported(self):
        with workspace() as root:
            old = root / '.kairos-partial-old'
            old.mkdir()
            (old / 'dump').write_bytes(b'PGDMP left by a killed run')
            long_ago = old.stat().st_mtime - 7200
            os.utime(old / 'dump', (long_ago, long_ago))
            os.utime(old, (long_ago, long_ago))
            recent = root / '.kairos-partial-recent'
            recent.mkdir()
            (recent / 'dump').write_bytes(b'PGDMP a run in progress')
            with contextlib.redirect_stderr(io.StringIO()) as warnings:
                report = self.backup(root / 'kairos-before-20261116T090000000015Z.dump')
            self.assertEqual(report['swept_partials'], ['.kairos-partial-old'])
            self.assertFalse(old.exists())
            self.assertTrue((recent / 'dump').exists(), 'a run that is still going is not swept')
            self.assertIn('orphan partial', warnings.getvalue())

    def test_a_decrypted_copy_is_verified_and_restored_against_the_content_sha256_of_its_manifest(self):
        with workspace() as root:
            public, identity = new_identity(root)
            copy = Path(self.backup(root / 'kairos-before-20261116T090000000016Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))['path'])
            manifest_file = Path(str(copy) + '.json')
            plain = root / 'decrypted.dump'
            subprocess.run(['age', '--decrypt', '-i', str(identity), '-o', str(plain), str(copy)], check=True, capture_output=True)
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            self.assertEqual(manifest['content_sha256'], hashlib.sha256(plain.read_bytes()).hexdigest())
            self.assertEqual(manifest['content_bytes'], plain.stat().st_size)
            self.assertEqual(backup.verify_backup(plain, manifest_file=manifest_file)['verified'], 'content')
            with patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup needs no database')):
                failure, out = cli('verify-backup', '--backup', str(plain), '--manifest', str(manifest_file))
            self.assertIsNone(failure, failure)
            report = json.loads(out)
            self.assertEqual((report['status'], report['verified'], report['sha256'], report['bytes']), ('verified', 'content', manifest['content_sha256'], manifest['content_bytes']))
            with patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup needs no database')):
                failure, _ = cli('verify-backup', '--backup', str(plain))
            self.assertTrue(failure.startswith('backup_manifest_missing: '), 'without --manifest a loose dump has no manifest to match')
            data = bytearray(plain.read_bytes())
            data[len(data) // 2] ^= 0x01
            plain.write_bytes(bytes(data))
            for call in (lambda: backup.verify_backup(plain, manifest_file=manifest_file),):
                with self.assertRaises(backup.BackupError) as raised:
                    call()
                self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            with patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup needs no database')):
                failure, out = cli('verify-backup', '--backup', str(plain), '--manifest', str(manifest_file))
            self.assertTrue(failure.startswith('backup_checksum_mismatch: ') and out == '', failure)
            plain.write_bytes(bytes(data)[:-1])
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(plain, manifest_file=manifest_file)
            self.assertIn('truncated', str(raised.exception))

    def test_the_ciphertext_checks_still_work_with_an_explicit_manifest(self):
        with workspace() as root:
            public, _ = new_identity(root)
            copy = Path(self.backup(root / 'kairos-before-20261116T090000000017Z.dump', MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))['path'])
            moved = root / 'elsewhere.age'
            moved.write_bytes(copy.read_bytes())
            result = backup.verify_backup(moved, manifest_file=Path(str(copy) + '.json'))
            self.assertEqual(result['verified'], 'copy')

    def test_a_requirement_that_is_not_a_boolean_is_a_stable_code_not_a_traceback(self):
        with workspace() as root:
            with patch.dict(os.environ, dict(self.environ, MEMORY_BACKUP_REQUIRE_ENCRYPTION='maybe')), patch.object(backup.subprocess, 'run') as run, \
                    patch.object(backup.subprocess, 'Popen') as popen:
                with self.assertRaises(SystemExit) as raised:
                    main(['backup', '--output', str(root / 'sink' / 'kairos-before-20261116T090000000018Z.dump')])
            text = str(raised.exception.code)
            self.assertTrue(text.startswith('backup_config_invalid: '), text)
            self.assertIn('MEMORY_BACKUP_REQUIRE_ENCRYPTION', text)
            run.assert_not_called()
            popen.assert_not_called()
            self.assertFalse((root / 'sink').exists())


class PruneEconomyTests(unittest.TestCase):
    def test_only_the_kept_copies_are_hashed_and_the_older_ones_go_unhashed(self):
        with workspace() as root:
            for day in range(1, 8):
                pruned_copy(root, day)
            hashed = []
            real = backup.sha256_file
            with patch.object(backup, 'sha256_file', side_effect=lambda path: (hashed.append(Path(path).name), real(path))[1]):
                report = run_prune(root, 3)
            self.assertEqual(sorted(hashed), sorted(f'kairos-before-{stamp(day)}.dump' for day in (5, 6, 7)), 'the 3 newest are verified and nothing else is read')
            self.assertEqual(len(report['deleted']), 4)
            self.assertEqual(len(names(root)), 6)

    def test_an_older_copy_whose_size_is_not_the_one_of_its_manifest_is_left_alone(self):
        with workspace() as root:
            good = [pruned_copy(root, day) for day in (1, 2, 3, 4)]
            good[0].write_bytes(PAYLOAD[:-1])  # truncated, and the oldest
            report = run_prune(root, 2)
            self.assertEqual(report['deleted'], [good[1].name])
            self.assertTrue(good[0].exists())
            self.assertEqual({entry['name']: entry['code'] for entry in report['skipped']}[good[0].name], 'backup_checksum_mismatch')

    def test_a_copy_that_another_prune_already_deleted_is_not_a_failure(self):
        with workspace() as root:
            copies = [pruned_copy(root, day) for day in (1, 2, 3)]
            real = os.unlink

            def racing(path, *args, **kwargs):
                if Path(path) == copies[0]:
                    real(path)
                    raise FileNotFoundError(path)  # the other run got there first
                return real(path, *args, **kwargs)
            with patch.object(backup.os, 'unlink', racing):
                report = run_prune(root, 2)
            self.assertEqual(report['deleted'], [copies[0].name])
            self.assertFalse(copies[0].exists() or Path(str(copies[0]) + '.json').exists())

    def test_old_orphan_partials_are_swept_and_reported_and_recent_ones_stay(self):
        with workspace() as root:
            pruned_copy(root, 1)
            now = backup.datetime(2026, 11, 20, tzinfo=backup.timezone.utc)
            for name, age in (('.kairos-partial-old', 7200), ('.kairos-partial-new', 60)):
                folder = root / name
                folder.mkdir()
                (folder / 'dump').write_bytes(b'PGDMP half')
                stamp_at = now.timestamp() - age
                os.utime(folder / 'dump', (stamp_at, stamp_at))
                os.utime(folder, (stamp_at, stamp_at))
            (root / '.kairos-partial-file').write_bytes(b'not a directory')
            with contextlib.redirect_stderr(io.StringIO()) as warnings:
                report = run_prune(root, 1)
            self.assertEqual(report['swept_partials'], ['.kairos-partial-old'])
            self.assertFalse((root / '.kairos-partial-old').exists())
            self.assertTrue((root / '.kairos-partial-new' / 'dump').exists() and (root / '.kairos-partial-file').exists())
            self.assertIn('.kairos-partial-old', warnings.getvalue())


if __name__ == '__main__':
    unittest.main()
