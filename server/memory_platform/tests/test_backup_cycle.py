"""C-01 / CA-06: `admin backup-cycle` makes a copy, sends it to a `dir:` or `rclone:` destination, verifies it there and applies the retention of both places;
with the destination out of reach it logs `backup_offsite_failed`, sets its metric to 0, keeps every local copy and sends again at the next cycle."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from memory_platform import admin, backup, config, observability, offsite
from memory_platform.admin import main
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_manifest import PAYLOAD
from memory_platform.tests.test_backup_prune import copy as seeded_copy, names, stamp
from datetime import datetime, timezone

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def make_copy_factory(payload=PAYLOAD, day=19):
    """A `make_copy` that writes a complete copy at the name the cycle chose, the way `create_backup` leaves one."""
    import hashlib
    calls = []

    def make_copy(output):
        calls.append(output)
        output.write_bytes(payload)
        manifest = {'format': 2, 'file': output.name, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'content_sha256': hashlib.sha256(payload).hexdigest(),
                    'content_bytes': len(payload), 'schema_version': 12, 'created_at': NOW.strftime('%Y-%m-%dT%H:%M:%S.%fZ'), 'encrypted': False, 'fingerprints': {}}
        Path(str(output) + '.json').write_text(json.dumps(manifest), encoding='utf-8')
        return {'status': 'backed_up', 'path': str(output), 'bytes': len(payload), 'sha256': manifest['sha256'], 'encrypted': False}
    make_copy.calls = calls
    return make_copy


def cycle(root_local, destination, **options):
    options.setdefault('keep', 7)
    options.setdefault('remote_keep', 30)
    options.setdefault('now', NOW)
    return offsite.run_cycle(options.pop('make_copy', None) or make_copy_factory(), root_local, destination, **options)


def remote_names(path):
    return sorted(p.name for p in Path(path).iterdir())


class DirDestinationTests(unittest.TestCase):
    def test_the_copy_and_its_manifest_reach_the_directory_and_are_verified_there(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            report = cycle(local, offsite.DirDestination(remote))
            copy = Path(report['path'])
            self.assertEqual(remote_names(remote), sorted([copy.name, copy.name + '.json']))
            self.assertEqual((remote / copy.name).read_bytes(), copy.read_bytes())
            self.assertEqual(report['offsite']['status'], 'verified')
            self.assertEqual(report['offsite']['uploaded'], [copy.name])
            self.assertEqual(report['offsite']['destination'], 'dir')
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 1)
            self.assertNotIn(True, [n.startswith(offsite.UPLOAD_PREFIX) for n in remote_names(remote)], 'no half-sent file stays at the destination')
            self.assertIn('kairos_backup_offsite_success 1.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'))

    def test_the_remote_retention_keeps_the_newest_n_and_the_local_one_applies_too(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            for day in (1, 2, 3, 4):
                seeded_copy(remote, day)  # four older copies already at the destination
            for day in (5, 6, 7):
                seeded_copy(local, day)
            report = cycle(local, offsite.DirDestination(remote), keep=2, remote_keep=3)
            kept_remote = [n for n in remote_names(remote) if not n.endswith('.json')]
            self.assertEqual(len(kept_remote), 3)
            self.assertIn(Path(report['path']).name, kept_remote)
            self.assertEqual(report['offsite']['kept'], 3)
            self.assertEqual(sorted(p.name for p in remote.iterdir() if p.name.endswith('.json')), sorted(n + '.json' for n in kept_remote), 'no manifest outlives its copy')
            self.assertEqual(len([n for n in names(local) if n.endswith('.dump')]), 2, 'the local retention keeps the newest 2')
            self.assertEqual(report['prune']['keep'], 2)

    def test_the_retention_default_of_the_destination_is_thirty_and_it_is_validated(self):
        self.assertEqual(config.backup_remote_keep({}), 30)
        self.assertEqual(config.backup_remote_keep({'MEMORY_BACKUP_REMOTE_KEEP': '5'}), 5)
        for bad in ('0', '-1', 'x', '1.5', '٣'):
            with self.assertRaises(ValueError, msg=bad):
                config.backup_remote_keep({'MEMORY_BACKUP_REMOTE_KEEP': bad})

    def test_the_interval_is_a_duration_with_a_default_of_one_day(self):
        self.assertEqual(config.backup_interval_seconds({}), 86400)
        for text, seconds in (('90s', 90), ('30m', 1800), ('24h', 86400), ('1d', 86400), ('45', 45), (' 2H ', 7200)):
            self.assertEqual(config.backup_interval_seconds({'MEMORY_BACKUP_INTERVAL': text}), seconds, text)
        for bad in ('0', '0s', '31d', 'h', '-5m', '1.5h', 'soon', '٣s'):
            with self.assertRaises(ValueError, msg=bad):
                config.backup_interval_seconds({'MEMORY_BACKUP_INTERVAL': bad})

    def test_destinations_are_parsed_strictly_and_the_message_never_echoes_the_value(self):
        self.assertEqual(offsite.parse_destination('dir:/srv/offsite').kind, 'dir')
        self.assertEqual(offsite.parse_destination('rclone:vault:kairos/prod').kind, 'rclone')
        for bad in ('', None, 'dir:', 'dir:relative/path', 'rclone:', 'rclone:nocolon', 'rclone:-flag:path', 'rclone::s3,env_auth:bucket', 'rclone:x:\npath', 's3://bucket', 'DIR:/x'):
            with self.assertRaises(backup.BackupError, msg=repr(bad)) as raised:
                offsite.parse_destination(bad)
            self.assertEqual(raised.exception.code, 'backup_destination_invalid')
            if bad and bad.strip() not in ('dir:', 'rclone:'):
                self.assertNotIn(bad.strip(), str(raised.exception))

    def test_a_destination_that_is_the_local_directory_is_refused_before_any_copy(self):
        with workspace() as root:
            make_copy = make_copy_factory()
            with self.assertRaises(backup.BackupError) as raised:
                cycle(root, offsite.DirDestination(root), make_copy=make_copy)
            self.assertEqual(raised.exception.code, 'backup_destination_invalid')
            self.assertEqual(make_copy.calls, [])

    def test_a_half_sent_file_of_a_killed_run_is_swept_but_nothing_else(self):
        with workspace() as root:
            old = root / (offsite.UPLOAD_PREFIX + 'old')
            fresh = root / (offsite.UPLOAD_PREFIX + 'fresh')
            other = root / 'notes.txt'
            for path in (old, fresh, other):
                path.write_bytes(b'x')
            os.utime(old, (1, 1))
            offsite.DirDestination(root).sweep()
            self.assertEqual(sorted(p.name for p in root.iterdir()), sorted([fresh.name, other.name]))

    def test_a_second_cycle_sends_only_the_new_copy(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            first = cycle(local, offsite.DirDestination(remote))
            later = datetime(2026, 11, 21, tzinfo=timezone.utc)
            second = cycle(local, offsite.DirDestination(remote), now=later, make_copy=make_copy_factory())
            self.assertEqual(second['offsite']['uploaded'], [Path(second['path']).name])
            self.assertNotEqual(first['path'], second['path'])


class LoopTests(unittest.TestCase):
    def test_the_loop_survives_a_failing_cycle_and_sleeps_the_interval_between_cycles(self):
        outputs, sleeps = [], []
        results = iter([offsite.CycleError('backup_offsite_failed', 'down', {'status': 'backed_up', 'offsite': {'status': 'failed'}}), RuntimeError('database secret-dsn'), {'status': 'backed_up'}])

        def one():
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return result
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            offsite.run_loop(one, 90, sleep=sleeps.append, cycles=3, out=outputs.append)
        self.assertEqual(sleeps, [90, 90], 'a sleep between cycles, none after the last')
        self.assertEqual(len(outputs), 2)
        self.assertIn('backup_offsite_failed: down', stderr.getvalue())
        self.assertIn('RuntimeError', stderr.getvalue())
        self.assertNotIn('secret-dsn', stderr.getvalue(), 'the message of an unexpected error is never printed')

    def test_stop_signals_end_the_loop(self):
        def stop():
            raise SystemExit(143)
        with self.assertRaises(SystemExit):
            offsite.run_loop(stop, 1, sleep=lambda s: None, cycles=3, out=lambda s: None)


@unittest.skipUnless(shutil.which('rclone'), 'rclone is required (the test image installs it)')
class RcloneDestinationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'RCLONE_CONFIG': ''}))

    def configure(self, root):
        """A remote of type `local` written here, in a configuration file of the test: no cloud service and no credential."""
        configuration = root / 'rclone.conf'
        configuration.write_text('[vault]\ntype = local\n', encoding='utf-8')
        os.environ['RCLONE_CONFIG'] = str(configuration)

    def test_a_local_remote_receives_the_copy_verifies_it_and_applies_the_retention(self):
        with workspace() as root:
            self.configure(root)
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            for day in (1, 2, 3):
                seeded_copy(remote, day)
            destination = offsite.parse_destination(f'rclone:vault:{remote.as_posix()}')
            report = cycle(local, destination, remote_keep=2)
            copy = Path(report['path'])
            kept = [n for n in remote_names(remote) if not n.endswith('.json')]
            self.assertEqual(len(kept), 2)
            self.assertIn(copy.name, kept)
            self.assertEqual((remote / copy.name).read_bytes(), copy.read_bytes())
            self.assertTrue((remote / (copy.name + '.json')).is_file())
            self.assertEqual(report['offsite']['destination'], 'rclone')
            self.assertEqual(report['offsite']['status'], 'verified')
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 1)

    def test_a_remote_that_does_not_exist_is_an_offsite_failure_that_names_no_path_or_credential(self):
        with workspace() as root:
            self.configure(root)
            local = root / 'local'
            local.mkdir()
            seeded_copy(local, 5)
            destination = offsite.parse_destination(f'rclone:vault:{(root / "absent").as_posix()}')
            with self.assertRaises(offsite.CycleError) as raised:
                cycle(local, destination)
            self.assertEqual(raised.exception.code, 'backup_offsite_failed')
            self.assertNotIn('absent', str(raised.exception))
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0)

    def test_an_unknown_remote_name_fails_without_echoing_it(self):
        with workspace() as root:
            self.configure(root)
            local = root / 'local'
            local.mkdir()
            with self.assertRaises(offsite.CycleError) as raised:
                cycle(local, offsite.parse_destination('rclone:nosuchremote-s3cr3t:bucket'))
            self.assertEqual(raised.exception.code, 'backup_offsite_failed')
            self.assertNotIn('s3cr3t', str(raised.exception))


class CommandTests(unittest.TestCase):
    """The real command line over a real database (the dump is a double: the cycle's own steps are what is under test)."""

    def setUp(self):
        from memory_platform.tests.test_store import create_core
        self.store, self.actor, self.project = create_core()
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': '', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': '0', 'MEMORY_BACKUP_KEEP': '',
                        'MEMORY_BACKUP_DESTINATION': '', 'MEMORY_BACKUP_REMOTE_KEEP': '', 'MEMORY_BACKUP_INTERVAL': ''}

        def fake_dump(command, **kwargs):
            Path(command[command.index('--file') + 1]).write_bytes(PAYLOAD)
            return Mock(returncode=0)
        self.fake_dump = fake_dump

    def run_command(self, *argv, **environ):
        output, errors = io.StringIO(), io.StringIO()
        failure = None
        with patch.dict(os.environ, dict(self.environ, **environ)), patch.object(admin.subprocess, 'run', self.fake_dump), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                main(['backup-cycle', *argv])
            except SystemExit as exit_:
                failure = str(exit_.code)
        return failure, output.getvalue(), errors.getvalue()

    def test_one_cycle_sends_the_copy_to_the_directory_and_reports_it(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            remote.mkdir()
            failure, out, err = self.run_command('--output-dir', str(local), MEMORY_BACKUP_DESTINATION='dir:' + str(remote))
            self.assertIsNone(failure, err)
            report = json.loads(out)
            self.assertEqual((report['status'], report['offsite']['status'], report['offsite']['destination']), ('backed_up', 'verified', 'dir'))
            copy = Path(report['path'])
            self.assertEqual(copy.parent, local.resolve())
            self.assertEqual((remote / copy.name).read_bytes(), PAYLOAD)
            self.assertTrue((remote / (copy.name + '.json')).is_file())
            self.assertEqual(report['prune']['keep'], 7, 'the local retention is MEMORY_BACKUP_KEEP')

    def test_without_a_destination_or_with_bad_settings_nothing_is_written(self):
        with workspace() as root:
            local = root / 'local'
            for environ, code in (({}, 'backup_destination_invalid'), ({'MEMORY_BACKUP_DESTINATION': 'ftp://x'}, 'backup_destination_invalid'),
                                  ({'MEMORY_BACKUP_DESTINATION': 'dir:' + str(root), 'MEMORY_BACKUP_REMOTE_KEEP': '0'}, 'backup_keep_invalid'),
                                  ({'MEMORY_BACKUP_DESTINATION': 'dir:' + str(root), 'MEMORY_BACKUP_INTERVAL': 'soon'}, 'backup_config_invalid')):
                failure, out, err = self.run_command('--output-dir', str(local), '--loop', **environ)
                self.assertTrue((failure or '').startswith(code + ': '), (environ, failure))
                self.assertEqual(out, '')
            self.assertFalse(local.exists())

    def test_the_cycle_can_end_with_the_retention_of_the_tables(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            remote.mkdir()
            with patch.object(admin, 'prune_tables', return_value={'status': 'pruned', 'tables': {}}) as pruned:
                failure, out, err = self.run_command('--output-dir', str(local), '--prune-tables', MEMORY_BACKUP_DESTINATION='dir:' + str(remote))
            self.assertIsNone(failure, err)
            pruned.assert_called_once()
            self.assertEqual(json.loads(out)['prune_tables'], {'status': 'pruned'})
            with patch.object(admin, 'prune_tables') as pruned:
                self.run_command('--output-dir', str(root / 'local2'), MEMORY_BACKUP_DESTINATION='dir:' + str(remote))
            pruned.assert_not_called()

    def test_the_loop_runs_a_cycle_per_interval(self):
        with workspace() as root:
            remote = root / 'remote'
            remote.mkdir()
            sleeps = []
            with patch.object(offsite.time, 'sleep', sleeps.append), patch.object(admin, 'LOOP_CYCLES', 2):
                failure, out, err = self.run_command('--output-dir', str(root / 'local'), '--loop', MEMORY_BACKUP_DESTINATION='dir:' + str(remote), MEMORY_BACKUP_INTERVAL='90s')
            self.assertIsNone(failure, err)
            self.assertEqual(sleeps, [90])
            self.assertEqual(len([line for line in out.splitlines() if line.startswith('{')]), 2)
            self.assertEqual(len([p for p in remote.iterdir() if p.name.endswith('.dump')]), 2)

