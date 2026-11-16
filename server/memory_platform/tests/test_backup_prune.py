"""C-01 / CA-03: `backup --prune --keep N` deletes only complete, verified copies of its own name beyond the N newest, and never anything else."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from memory_platform import admin, backup, config
from memory_platform.admin import main
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_manifest import PAYLOAD, write_copy
from memory_platform.tests.test_store import create_core


def stamp(day, suffix='000000'):
    return f'202611{day:02d}T120000{suffix}Z'


def copy(root, day, *, kind='before', encrypted=False, **changes):
    """A valid copy of day `day` of November 2026 (its manifest says so)."""
    name = f'kairos-{kind}-{stamp(day)}.dump' + ('.age' if encrypted else '')
    payload = (b'age-encryption.org/v1\n' + bytes(range(200))) if encrypted else PAYLOAD
    changes.setdefault('created_at', f'2026-11-{day:02d}T12:00:00.000000Z')
    if encrypted:
        changes.update(encrypted=True, recipients=['a' * 64])
    return write_copy(root, name=name, payload=payload, **changes)


def names(root):
    return sorted(path.name for path in root.iterdir())


def run_prune(root, keep, **options):
    return backup.prune_backups(root, keep, now=datetime(2026, 11, 20, tzinfo=timezone.utc), **options)


class PruneTests(unittest.TestCase):
    def test_the_oldest_valid_copies_beyond_the_newest_n_go_with_their_manifests(self):
        with workspace() as root:
            for day in range(1, 7):
                copy(root, day, encrypted=day % 2 == 0)  # plain and encrypted copies are the same kind of thing
            report = run_prune(root, 3)
            self.assertEqual([c['name'] for c in report['kept']], [f'kairos-before-{stamp(d)}.dump' + ('.age' if d % 2 == 0 else '') for d in (6, 5, 4)])
            self.assertEqual(report['deleted'], [f'kairos-before-{stamp(d)}.dump' + ('.age' if d % 2 == 0 else '') for d in (3, 2, 1)])
            self.assertEqual(names(root), sorted(n + ext for n in [f'kairos-before-{stamp(d)}.dump' + ('.age' if d % 2 == 0 else '') for d in (4, 5, 6)] for ext in ('', '.json')))
            self.assertEqual(report['keep'], 3)

    def test_decoys_and_incomplete_or_invalid_copies_are_never_deleted_and_never_counted(self):
        with workspace() as root:
            good = [copy(root, day) for day in (1, 2, 3, 4)]
            decoys = {}
            for name in ('notes.txt', 'kairos-before-20260101T000000000000Z.dump.bak', 'kairos-before-x.dump', 'random.dump', 'kairos-before-20260101T000000000000Z.dump.json.old',
                         'KAIROS-before-20260101T000000000000Z.dump', 'kairos-20260101T000000000000Z.dump', 'xkairos-before-20260101T000000000000Z.dump', 'kairos-before-20260101T000000000000Z.dump~'):
                (root / name).write_bytes(b'precious ' + name.encode())
                decoys[name] = (root / name).read_bytes()
            foreign = [write_copy(root, name=name, created_at='2026-10-01T00:00:00.000000Z') for name in ('precious-20261001.dump', 'my-own-backup.dump', 'kairos-before-20261001.dump', 'kairos-before-20261001T000000Z.dump.old')]  # complete and verified, but not this tool's names
            half = root / f'kairos-before-{stamp(9)}.dump'  # a copy that stopped before its manifest was written
            half.write_bytes(PAYLOAD[:100])
            tampered = copy(root, 10)
            data = bytearray(tampered.read_bytes())
            data[300] ^= 1
            tampered.write_bytes(bytes(data))
            wrong_manifest = copy(root, 11)
            Path(str(wrong_manifest) + '.json').write_text('{"nope": 1}', encoding='utf-8')
            (root / f'kairos-before-{stamp(12)}.dump.json').write_text('{}', encoding='utf-8')  # an orphan manifest
            folder = root / f'kairos-before-{stamp(13)}.dump'
            folder.mkdir()
            (folder / 'inside').write_bytes(b'x')
            (root / '.kairos-partial-abc123').mkdir()
            (root / '.kairos-partial-abc123' / 'dump').write_bytes(b'PGDMP half')
            recent = datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp() - 60  # a run that is still going (older ones are swept: see test_backup_hardening)
            os.utime(root / '.kairos-partial-abc123' / 'dump', (recent, recent))
            os.utime(root / '.kairos-partial-abc123', (recent, recent))
            before = {n: (root / n).read_bytes() for n in names(root) if (root / n).is_file()}
            report = run_prune(root, 2)
            self.assertEqual(report['deleted'], [good[1].name, good[0].name])
            for name in decoys:
                self.assertEqual((root / name).read_bytes(), decoys[name], name)
            for kept in (*foreign, half, tampered, wrong_manifest, folder / 'inside', root / '.kairos-partial-abc123' / 'dump', root / f'kairos-before-{stamp(12)}.dump.json'):
                self.assertTrue(kept.exists(), kept.name)
            self.assertEqual({n for n in before if (root / n).exists()}, set(before) - {good[0].name, good[0].name + '.json', good[1].name, good[1].name + '.json'})
            skipped = {entry['name']: entry['code'] for entry in report['skipped']}
            self.assertEqual(skipped[half.name], 'backup_manifest_missing')
            self.assertEqual(skipped[tampered.name], 'backup_checksum_mismatch')
            self.assertEqual(skipped[wrong_manifest.name], 'backup_manifest_invalid')
            self.assertEqual([c['name'] for c in report['kept']], [good[3].name, good[2].name])

    def test_an_invalid_newest_copy_does_not_push_a_valid_one_out_and_the_last_verified_copy_stays(self):
        with workspace() as root:
            good = [copy(root, day) for day in (1, 2)]
            newest = copy(root, 5)
            data = bytearray(newest.read_bytes())
            data[10] ^= 1
            newest.write_bytes(bytes(data))
            report = run_prune(root, 1)
            self.assertEqual(report['deleted'], [good[0].name])
            self.assertTrue(good[1].exists() and newest.exists())
            self.assertEqual(run_prune(root, 1)['deleted'], [])
            # even when every other copy is broken, the one verified copy is not deleted
            with self.assertRaises(backup.BackupError):
                backup.verify_backup(newest)
            self.assertEqual(backup.verify_backup(good[1])['bytes'], len(PAYLOAD))

    def test_nothing_is_deleted_when_there_are_not_more_than_n_valid_copies_and_a_second_run_does_nothing(self):
        with workspace() as root:
            for day in (1, 2, 3):
                copy(root, day)
            self.assertEqual(run_prune(root, 3)['deleted'], [])
            self.assertEqual(run_prune(root, 10)['deleted'], [])
            self.assertEqual(len(names(root)), 6)
            self.assertEqual(len(run_prune(root, 1)['deleted']), 2)
            self.assertEqual(run_prune(root, 1)['deleted'], [])  # idempotent
            self.assertEqual(len(names(root)), 2)

    def test_a_manifest_dated_in_the_future_does_not_count_as_the_newest(self):
        with workspace() as root:
            good = [copy(root, day) for day in (1, 2)]
            decoy = copy(root, 3, created_at='2099-01-01T00:00:00.000000Z')
            report = run_prune(root, 1)
            self.assertEqual(report['deleted'], [good[0].name])
            self.assertTrue(decoy.exists() and good[1].exists())
            self.assertEqual({entry['name']: entry['code'] for entry in report['skipped']}[decoy.name], 'backup_created_in_the_future')

    def test_symbolic_links_are_neither_followed_nor_counted_nor_deleted(self):
        with workspace() as root:
            real = [copy(root, day) for day in (1, 2, 3)]
            link = root / f'kairos-before-{stamp(4)}.dump'
            try:
                link.symlink_to(real[2])
            except OSError:
                self.skipTest('symbolic links are not available here')
            Path(str(link) + '.json').write_text(Path(str(real[2]) + '.json').read_text(encoding='utf-8').replace(real[2].name, link.name), encoding='utf-8')
            outside = Path(str(root) + '-outside')
            outside.mkdir()
            try:
                (outside / 'victim').write_bytes(b'keep me')
                (root / f'kairos-before-{stamp(5)}.dump').symlink_to(outside / 'victim')
                report = run_prune(root, 1)
                self.assertEqual(report['deleted'], [real[1].name, real[0].name])
                self.assertTrue(link.is_symlink() and (outside / 'victim').exists())
            finally:
                for path in outside.iterdir():
                    path.unlink()
                outside.rmdir()

    def test_a_copy_that_another_prune_deletes_while_this_one_verifies_it_is_gone_and_not_a_failure(self):
        """Two `--prune` at the same time (the scheduled cycle and a manual run): the copy that vanishes under the verification is neither counted nor an error."""
        with workspace() as root:
            for day in (1, 2, 3, 4):
                copy(root, day)
            real = backup.verify_backup

            def vanishing(path, *args, **kwargs):
                if path.name.endswith(stamp(3) + '.dump'):  # the other run deletes it between our `is_file` and our read
                    path.unlink()
                    backup.manifest_path(path).unlink()
                    raise FileNotFoundError(str(path))
                return real(path, *args, **kwargs)
            with patch.object(backup, 'verify_backup', vanishing):
                report = run_prune(root, 2)
            self.assertEqual([c['name'] for c in report['kept']], [f'kairos-before-{stamp(4)}.dump', f'kairos-before-{stamp(2)}.dump'], 'the vanished copy does not count: the next older one is verified instead')
            self.assertEqual(report['deleted'], [f'kairos-before-{stamp(1)}.dump'])
            self.assertEqual(report['skipped'], [])
            self.assertEqual(names(root), sorted(f'kairos-before-{stamp(d)}.dump' + ext for d in (2, 4) for ext in ('', '.json')))

    def test_a_copy_that_is_really_deleted_between_the_listing_and_the_verification_is_gone_not_skipped(self):
        """The real race: the file disappears and the REAL `verify_backup` answers `backup_not_found` (not `FileNotFoundError`); that is a copy that is gone, not one that was skipped."""
        with workspace() as root:
            for day in (1, 2, 3, 4):
                copy(root, day)
            real = backup.verify_backup

            def deleted_then_verified(path, *args, **kwargs):
                if path.name.endswith(stamp(3) + '.dump'):
                    path.unlink()
                    backup.manifest_path(path).unlink()
                return real(path, *args, **kwargs)
            with patch.object(backup, 'verify_backup', deleted_then_verified):
                report = run_prune(root, 2)
            self.assertEqual(report['skipped'], [], 'a vanished copy is not reported as skipped')
            self.assertEqual([c['name'] for c in report['kept']], [f'kairos-before-{stamp(4)}.dump', f'kairos-before-{stamp(2)}.dump'])
            self.assertEqual(report['deleted'], [f'kairos-before-{stamp(1)}.dump'])

    def test_a_copy_that_is_a_link_or_a_directory_at_verification_time_is_still_skipped(self):
        """Positive control of the check above: `backup_not_found` for something that STILL exists is a skip, only a path that is gone counts as vanished."""
        with workspace() as root:
            for day in (1, 2, 3):
                copy(root, day)
            real = backup.verify_backup

            def replaced_by_directory(path, *args, **kwargs):
                if path.name.endswith(stamp(3) + '.dump'):
                    path.unlink()
                    path.mkdir()
                return real(path, *args, **kwargs)
            with patch.object(backup, 'verify_backup', replaced_by_directory):
                report = run_prune(root, 2)
            self.assertEqual(report['skipped'], [{'name': f'kairos-before-{stamp(3)}.dump', 'code': 'backup_not_found'}])

    def test_keep_must_be_a_whole_number_of_one_or_more(self):
        with workspace() as root:
            copy(root, 1)
            for bad in (0, -1, True, False, '3', 1.5, None):
                with self.subTest(bad=bad), self.assertRaises(backup.BackupError) as raised:
                    run_prune(root, bad)
                self.assertEqual(raised.exception.code, 'backup_keep_invalid')
            self.assertEqual(len(names(root)), 2)

    def test_a_failed_deletion_is_reported_and_never_leaves_fewer_than_n_valid_copies(self):
        with workspace() as root:
            for day in (1, 2, 3, 4):
                copy(root, day)
            real = os.unlink

            def stubborn(path, *args, **kwargs):
                if kwargs.get('dir_fd') is None and str(path).endswith(f'{stamp(1)}.dump'):
                    raise PermissionError('read-only')
                return real(path, *args, **kwargs)
            with patch.object(backup.os, 'unlink', stubborn), self.assertRaises(backup.BackupError) as raised:
                run_prune(root, 2)
            self.assertEqual(raised.exception.code, 'backup_prune_failed')
            valid = [n for n in names(root) if n.endswith('.dump') and backup.verify_backup(root / n)]
            self.assertGreaterEqual(len(valid), 2)
            self.assertTrue((root / f'kairos-before-{stamp(4)}.dump').exists() and (root / f'kairos-before-{stamp(3)}.dump').exists())
            self.assertFalse((root / f'kairos-before-{stamp(2)}.dump').exists(), 'the other old copy was still deleted')


class PruneCommandTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': '', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': '', 'MEMORY_BACKUP_KEEP': ''}

        def fake_dump(command, **kwargs):
            Path(command[command.index('--file') + 1]).write_bytes(PAYLOAD)
            return Mock(returncode=0)
        self.fake_dump = fake_dump

    def backup(self, root, day, *argv, **environ):
        output = root / f'kairos-before-{stamp(day, "123456")}.dump'
        with patch.dict(os.environ, dict(self.environ, **environ)), patch.object(admin.subprocess, 'run', self.fake_dump), contextlib.redirect_stdout(io.StringIO()) as out:
            main(['backup', '--output', str(output), *argv])
        return json.loads(out.getvalue())

    def refused(self, root, *argv, **environ):
        with patch.dict(os.environ, dict(self.environ, **environ)), patch.object(admin.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(['backup', '--output', str(root / f'kairos-before-{stamp(9, "123456")}.dump'), *argv])
        run.assert_not_called()
        return str(raised.exception.code)

    def test_the_command_writes_the_new_copy_then_prunes_and_reports_what_it_deleted_and_kept(self):
        with workspace() as root:
            for day in (1, 2, 3):
                copy(root, day)
            report = self.backup(root, 15, '--prune', '--keep', '2')
            self.assertEqual(report['status'], 'backed_up')
            self.assertEqual([c['name'] for c in report['prune']['kept']], [f'kairos-before-{stamp(15, "123456")}.dump', f'kairos-before-{stamp(3)}.dump'])
            self.assertEqual(report['prune']['deleted'], [f'kairos-before-{stamp(2)}.dump', f'kairos-before-{stamp(1)}.dump'])
            self.assertEqual(len([n for n in names(root) if n.endswith('.dump')]), 2)

    def test_without_prune_nothing_is_deleted_and_the_report_has_no_prune_section(self):
        with workspace() as root:
            for day in (1, 2, 3):
                copy(root, day)
            report = self.backup(root, 15)
            self.assertNotIn('prune', report)
            self.assertEqual(len([n for n in names(root) if n.endswith('.dump')]), 4)

    def test_prune_without_keep_uses_memory_backup_keep_and_its_default_is_seven(self):
        self.assertEqual(config.BACKUP_KEEP_DEFAULT, 7)
        self.assertEqual(config.backup_keep({}), 7)
        self.assertEqual(config.backup_keep({'MEMORY_BACKUP_KEEP': ' 3 '}), 3)
        with workspace() as root:
            for day in range(1, 10):
                copy(root, day)
            report = self.backup(root, 15, '--prune')
            self.assertEqual(len(report['prune']['kept']), 7)
            report = self.backup(root, 16, '--prune', MEMORY_BACKUP_KEEP='2')
            self.assertEqual(len(report['prune']['kept']), 2)
            report = self.backup(root, 17, '--prune', '--keep', '5', MEMORY_BACKUP_KEEP='2')  # the option wins
            self.assertEqual(len(report['prune']['kept']), 3)  # only three valid copies are left to keep

    def test_an_invalid_keep_is_refused_before_anything_is_written_or_deleted(self):
        with workspace() as root:
            for day in (1, 2):
                copy(root, day)
            before = names(root)
            for argv in (['--prune', '--keep', '0'], ['--prune', '--keep', '-3'], ['--prune', '--keep', 'many'], ['--prune', '--keep', '1.5'], ['--keep', '2']):
                with self.subTest(argv=argv):
                    text = self.refused(root, *argv)
                    self.assertTrue(text.startswith('backup_keep_invalid: '), text)
                    self.assertIn('--keep', text)
                    self.assertEqual(names(root), before)
            text = self.refused(root, '--prune', MEMORY_BACKUP_KEEP='0')
            self.assertTrue(text.startswith('backup_keep_invalid: '), text)
            self.assertIn('MEMORY_BACKUP_KEEP', text)
            self.assertEqual(names(root), before)

    def test_the_copy_just_written_is_never_pruned_even_when_an_older_copy_claims_a_later_time(self):
        with workspace() as root:
            ahead = copy(root, 15, created_at=(datetime.now(timezone.utc) + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))  # a clock that ran ahead
            report = self.backup(root, 14, '--prune', '--keep', '1')
            new = Path(report['path'])
            self.assertTrue(new.exists() and Path(str(new) + '.json').exists())
            self.assertEqual([c['name'] for c in report['prune']['kept']], [new.name])
            self.assertFalse(ahead.exists())


if __name__ == '__main__':
    unittest.main()
