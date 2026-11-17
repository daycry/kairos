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
import sys
import threading
import time
import tracemalloc
import unittest
from unittest.mock import Mock, patch
import uuid

from memory_platform import admin, backup
from memory_platform.admin import main, store_fingerprints
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_encryption import new_identity, recipients_file
from memory_platform.tests.test_backup_manifest import PAYLOAD, cli, write_copy
from memory_platform.tests.test_backup_prune import copy as pruned_copy, names, run_prune, stamp
from memory_platform.tests.test_store import create_core

NEEDS_TOOLS = unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen') and shutil.which('pg_dump') and shutil.which('pg_restore'), 'age and the PostgreSQL client tools are required')


def reference_fingerprints(connection):
    """What a fingerprint must equal, computed the plain way (every table loaded whole): rows and the sum modulo 2**256 of the sha256 of each canonical row."""
    from psycopg import sql
    result = {}
    tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
    for row in tables:
        values = connection.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t').format(sql.Identifier(row['table_name']))).fetchall()
        encoded = [json.dumps(v['value'], sort_keys=True, ensure_ascii=False, default=str) for v in values]
        total = sum(int.from_bytes(hashlib.sha256(text.encode('utf-8')).digest(), 'big') for text in encoded) % (1 << 256)
        result[row['table_name']] = {'rows': len(encoded), 'sha256': format(total, '064x')}
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

    def rows(self, rows, size=40, duplicates=True):
        return [(n % 11 if duplicates else n, ('ñandú-' if n % 3 else 'zeta-') + 'x' * (n % (8 if duplicates else size))) for n in range(rows)]  # with duplicates: 264 different rows, each repeated

    def fill(self, values):
        with self.store.transaction() as c:
            c.execute('TRUNCATE memory.zz_fingerprint_probe')
            for value in values:
                c.execute('INSERT INTO memory.zz_fingerprint_probe VALUES (%s, %s)', value)

    def digest(self):
        with self.store.transaction() as c:
            return backup.table_digest(c, 'zz_fingerprint_probe')

    def test_the_fingerprints_equal_the_reference_with_duplicates_and_unicode_and_the_empty_table_is_zero(self):
        self.fill(self.rows(700))
        with self.store.transaction() as c:
            expected = reference_fingerprints(c)
            self.assertEqual(backup.table_fingerprints(c), expected)  # the whole schema, as the rest of the suite left it
            self.assertEqual(backup.table_digest(c, 'zz_fingerprint_probe'), (700, expected['zz_fingerprint_probe']['sha256']))
        self.fill([])
        self.assertEqual(self.digest(), (0, '0' * 64), 'an empty table')
        self.assertEqual(backup.MANIFEST_FORMAT, 2)

    def test_it_is_a_multiset_sum_the_order_does_not_matter_and_a_duplicate_counts(self):
        values = self.rows(300)
        self.fill(values)
        straight = self.digest()
        self.fill(list(reversed(values)))
        self.assertEqual(self.digest(), straight, 'a reversed insertion order')
        self.fill(sorted(values, key=lambda value: hashlib.sha256(repr(value).encode()).hexdigest()))
        self.assertEqual(self.digest(), straight, 'a permutation')
        self.fill(values + [values[0]])
        self.assertNotEqual(self.digest(), straight, 'one more copy of an existing row changes the number and the sum')
        self.assertEqual(self.digest()[0], 301)
        self.fill(values[1:])
        self.assertNotEqual(self.digest(), straight, 'a row removed')
        self.fill(values[:-1] + [(values[-1][0], values[-1][1] + '!')])
        changed = self.digest()
        self.assertEqual(changed[0], straight[0])
        self.assertNotEqual(changed, straight, 'a row altered keeps the count and changes the sum')
        self.fill(values + [(10_000, 'new')])
        self.assertNotEqual(self.digest(), straight, 'a row added')
        self.fill([(1, 'a'), (1, 'a'), (2, 'b')])  # two equal rows are neither cancelled nor deduplicated
        twice = self.digest()
        self.fill([(1, 'a'), (2, 'b'), (2, 'b')])
        self.assertNotEqual(self.digest(), twice)

    def test_each_table_is_read_exactly_once_however_many_rows_it_has(self):
        import psycopg
        self.fill(self.rows(3000))
        executed = []
        real = psycopg.ServerCursor.execute

        def counting(cursor, query, *args, **kwargs):
            executed.append(query.as_string(None) if hasattr(query, 'as_string') else str(query))
            return real(cursor, query, *args, **kwargs)
        with patch.object(backup, 'FINGERPRINT_ITERSIZE', 7), patch.object(psycopg.ServerCursor, 'execute', counting):
            rows, _ = self.digest()
        self.assertEqual(rows, 3000)
        self.assertEqual(len(executed), 1, 'one pass over the table: 3000 rows at 7 per round trip are one cursor, not one per slice')
        self.assertIn('zz_fingerprint_probe', executed[0])

    def peak(self, rows, function):
        self.fill(self.rows(rows, size=600, duplicates=False))
        with self.store.transaction() as c:
            tracemalloc.start()
            try:
                function(c)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

    def test_the_memory_does_not_grow_with_the_number_of_rows(self):
        streamed = lambda c: backup.table_digest(c, 'zz_fingerprint_probe')
        small, large = self.peak(1000, streamed), self.peak(4000, streamed)
        self.assertLess(large, small * 1.3, (small, large))
        self.assertLess(large, 600_000, 'a table of 2.4 MB of rows is read through a cursor, never held')
        self.assertGreater(self.peak(4000, reference_fingerprints), 3 * large, 'positive control: loading the whole table does hold it')

    def test_a_manifest_of_the_previous_format_has_its_own_clear_error(self):
        with workspace() as root:
            copy = write_copy(root, format=1)
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_format_unsupported')
            self.assertIn('make a new copy', str(raised.exception))
            self.assertNotIn(str(root), str(raised.exception))
            with patch('memory_platform.admin.Settings.from_env', side_effect=AssertionError('verify-backup needs no database')):
                failure, _ = cli('verify-backup', '--backup', str(copy))
            self.assertTrue(failure.startswith('backup_manifest_format_unsupported: '), failure)
            copy = write_copy(root, name='kairos-before-20261116T090000000001Z.dump', format=3)
            with self.assertRaises(backup.BackupError) as raised:
                backup.verify_backup(copy)
            self.assertEqual(raised.exception.code, 'backup_manifest_invalid', 'a newer format is not "old": it is not understood')


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

    def test_an_age_that_dies_without_reading_is_an_encryption_failure_not_a_dump_failure(self):
        """`pg_dump` is left with a closed pipe (EPIPE) and fails too; the cause is `age`, and the code must say so."""
        if os.name != 'posix':
            self.skipTest('a fake age is a shell script')
        with workspace() as root:
            public, _ = new_identity(root)
            real = subprocess.Popen

            def popen(command, **kwargs):
                if command[0] == 'age':
                    return real(['sh', '-c', 'exit 3'], **kwargs)  # exits at once, never reads its input
                return real(command, **kwargs)
            sink = root / 'sink'
            sink.mkdir()
            with patch.object(backup.subprocess, 'Popen', popen), patch.object(backup, 'HASH_BLOCK', 4096), patch.dict(os.environ, dict(self.environ, MEMORY_BACKUP_RECIPIENTS_FILE=str(recipients_file(root, public)))):
                with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(io.StringIO()):
                    main(['backup', '--output', str(sink / 'kairos-before-20261116T090000000019Z.dump')])
            self.assertTrue(str(raised.exception.code).startswith('backup_encryption_failed: '), raised.exception.code)
            self.assertIn('exit 3', str(raised.exception.code))
            self.assertEqual(list(sink.iterdir()), [])

    def test_a_sweep_by_another_process_while_the_copy_is_being_hashed_leaves_its_partial_alone(self):
        """The run holds a flock on its partial for its whole life: however old the mtimes look, the partial of a live run is not swept."""
        if backup.fcntl is None:
            self.skipTest('flock is POSIX')
        with workspace() as root:
            seen = {}
            real = backup.table_fingerprints

            def slow_hashing(connection, *args, **kwargs):  # the hashing phase: nothing is written to the partial for "hours"
                partial = next(root.glob('.kairos-partial-*'))
                long_ago = time.time() - 7200
                for path in (partial / backup.LOCK_NAME, partial):
                    os.utime(path, (long_ago, long_ago))
                seen['swept'] = backup.sweep_partials(root)
                seen['still_there'] = partial.exists()
                return real(connection, *args, **kwargs)
            with patch.object(backup, 'table_fingerprints', slow_hashing), contextlib.redirect_stderr(io.StringIO()):
                report = self.backup(root / 'kairos-before-20261116T090000000020Z.dump')
            self.assertEqual(seen, {'swept': [], 'still_there': True})
            self.assertEqual(report['status'], 'backed_up')
            self.assertEqual([entry.name for entry in root.iterdir() if entry.name.startswith('.kairos-partial-')], [], 'and the finished run removed its own partial')

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

    def test_a_candidate_that_another_prune_deleted_before_its_stat_is_not_a_failure(self):
        with workspace() as root:
            copies = [pruned_copy(root, day) for day in (1, 2, 3)]
            real = Path.stat

            def racing(path, *args, **kwargs):
                if path == copies[0] and sys._getframe(1).f_code.co_name == 'prune_backups':  # the size check of the candidate, not the earlier is_file()
                    raise FileNotFoundError(path)  # deleted between the scan and the stat
                return real(path, *args, **kwargs)
            with patch.object(Path, 'stat', racing):
                report = run_prune(root, 2)
            self.assertEqual(report['deleted'], [], 'it was already gone: nothing for this run to delete, and no error')
            self.assertEqual([entry['name'] for entry in report['kept']], [copies[2].name, copies[1].name])

    def test_a_prune_that_fails_after_a_valid_copy_still_prints_the_report_of_the_copy(self):
        for failure in (OSError('disk gone'), backup.BackupError('backup_prune_failed', '1 old copy could not be deleted')):
            with self.subTest(type(failure).__name__), workspace() as root:
                out = io.StringIO()
                with patch('memory_platform.admin.prune_backups', side_effect=failure), patch('memory_platform.admin.create_backup', return_value={'status': 'backed_up', 'path': str(root / 'x')}), \
                        patch('memory_platform.admin.Settings.from_env', return_value=Mock(dsn='postgresql://u@h/d')), patch('memory_platform.admin.Store'), \
                        patch('memory_platform.admin.pg_environment'), contextlib.redirect_stdout(out):
                    with self.assertRaises(SystemExit) as raised:
                        main(['backup', '--output', str(root / 'kairos-before-20261116T090000000021Z.dump'), '--prune', '--keep', '2'])
                report = json.loads(out.getvalue())
                self.assertEqual((report['status'], report['prune']), ('backed_up', {'status': 'failed', 'code': 'backup_prune_failed'}))
                self.assertTrue(str(raised.exception.code).startswith('backup_prune_failed: '), raised.exception.code)

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


HOLDER = """
import fcntl, os, sys
descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(descriptor, fcntl.LOCK_EX)
sys.stdout.write('locked\\n')
sys.stdout.flush()
sys.stdin.readline()
"""


@unittest.skipIf(backup.fcntl is None, 'flock is POSIX')
class SweepLockTests(unittest.TestCase):
    def partial(self, root, name, hours=2):
        folder = root / name
        folder.mkdir()
        (folder / 'dump').write_bytes(b'PGDMP half')
        stamp_at = time.time() - hours * 3600
        for path in (folder / 'dump', folder):
            os.utime(path, (stamp_at, stamp_at))
        return folder

    def test_a_partial_whose_lock_another_process_holds_is_never_swept_even_when_old_and_a_free_old_one_is(self):
        with workspace() as root:
            held = self.partial(root, '.kairos-partial-held')
            free = self.partial(root, '.kairos-partial-free')
            (free / backup.LOCK_NAME).write_bytes(b'')  # a lock file nobody holds: its owner is gone
            stamp_at = time.time() - 7200
            os.utime(free / backup.LOCK_NAME, (stamp_at, stamp_at))
            os.utime(free, (stamp_at, stamp_at))
            holder = subprocess.Popen([sys.executable, '-c', HOLDER, str(held / backup.LOCK_NAME)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), 'locked')
                os.utime(held / backup.LOCK_NAME, (stamp_at, stamp_at))
                os.utime(held, (stamp_at, stamp_at))
                with contextlib.redirect_stderr(io.StringIO()):
                    swept = backup.sweep_partials(root)
                self.assertEqual(swept, ['.kairos-partial-free'])
                self.assertTrue((held / 'dump').exists(), 'two hours old by mtime and still the partial of a live process')
                self.assertFalse(free.exists())
            finally:
                holder.stdin.write('\n')
                holder.stdin.close()
                holder.wait(timeout=30)
                holder.stdout.close()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(backup.sweep_partials(root), ['.kairos-partial-held'], 'once its holder is gone the lock is free and it is old: swept')

    def test_a_free_lock_does_not_make_a_recent_partial_sweepable_and_a_lock_link_is_not_followed(self):
        with workspace() as root:
            recent = self.partial(root, '.kairos-partial-recent', hours=0)
            (recent / backup.LOCK_NAME).write_bytes(b'')
            target = root / 'elsewhere'
            target.write_bytes(b'x')
            linked = self.partial(root, '.kairos-partial-linked')
            os.symlink(target, linked / backup.LOCK_NAME)
            stamp_at = time.time() - 7200
            os.utime(linked / backup.LOCK_NAME, (stamp_at, stamp_at), follow_symlinks=False)
            os.utime(linked, (stamp_at, stamp_at))
            with contextlib.redirect_stderr(io.StringIO()):
                swept = backup.sweep_partials(root)
            self.assertEqual(swept, ['.kairos-partial-linked'], 'a link in place of the lock file is no lock: by age alone, and never opened')
            self.assertTrue(recent.exists(), 'a run that made the directory a moment ago and has not locked it yet is not swept')
            self.assertEqual(target.read_bytes(), b'x')


if __name__ == '__main__':
    unittest.main()
