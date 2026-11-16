"""C-01 / CA-06: `admin backup-cycle` makes a copy, sends it to a `dir:` or `rclone:` destination, verifies it there and applies the retention of both places;
with the destination out of reach it logs `backup_offsite_failed`, sets its metric to 0, keeps every local copy and sends again at the next cycle."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from memory_platform import admin, backup, config, observability, offsite
from memory_platform.admin import main
from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_backup_manifest import PAYLOAD
from memory_platform.tests.test_backup_prune import copy as plain_copy, names, stamp
from datetime import datetime, timezone

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
AGE_PAYLOAD = b'age-encryption.org/v1\n' + bytes(range(256)) * 2  # what an encrypted copy starts with: the cycle sends nothing else


def seeded_copy(root, day, **options):
    """A valid ENCRYPTED copy of day `day` (what the cycle may send); `plain_copy` is the one it must never send."""
    options.setdefault('encrypted', True)
    return plain_copy(root, day, **options)


def write_copy_at(output, payload, encrypted, recipients=('a' * 64,), created=NOW):
    """The copy and its manifest at `output` (a `.age` name when encrypted), the way `create_backup` leaves them. Returns the report."""
    import hashlib
    output = output.with_name(output.name + '.age') if encrypted and not output.name.endswith('.age') else output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    manifest = {'format': 2, 'file': output.name, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'content_sha256': hashlib.sha256(payload).hexdigest(),
                'content_bytes': len(payload), 'schema_version': 12, 'created_at': created.strftime('%Y-%m-%dT%H:%M:%S.%fZ'), 'encrypted': encrypted, 'fingerprints': {}}
    if encrypted:
        manifest['recipients'] = list(recipients)
    Path(str(output) + '.json').write_text(json.dumps(manifest), encoding='utf-8')
    return {'status': 'backed_up', 'path': str(output), 'bytes': len(payload), 'sha256': manifest['sha256'], 'encrypted': encrypted}


def make_copy_factory(payload=None, encrypted=True):
    """A `make_copy` that writes a complete copy at the name the cycle chose, the way `create_backup` leaves one (encrypted, as the cycle requires, unless asked)."""
    calls = []
    body = payload or (AGE_PAYLOAD if encrypted else PAYLOAD)

    def make_copy(output):
        calls.append(output)
        return write_copy_at(output, body, encrypted)
    make_copy.calls = calls
    return make_copy


def cycle(root_local, destination, **options):
    options.setdefault('keep', 7)
    options.setdefault('remote_keep', 30)
    options.setdefault('now', NOW)
    return offsite.run_cycle(options.pop('make_copy', None) or make_copy_factory(), root_local, destination, **options)


def no_copies(directory):
    """What `directory` holds besides the metrics file (a refused start leaves that file and nothing else)."""
    return [] if not Path(directory).exists() else sorted(p.name for p in Path(directory).iterdir() if p.name != offsite.METRICS_NAME)


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
            self.assertEqual(len([n for n in names(local) if n.endswith('.dump.age')]), 2, 'the local retention keeps the newest 2')
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

    def test_a_plain_copy_of_the_directory_never_reaches_the_destination_and_is_reported(self):
        """CWE-311: the `kairos-before-*` that every deployment writes without recipients (or a copy made by hand) must not leave the server in the clear."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            plain = plain_copy(local, 6, encrypted=False)
            sealed = seeded_copy(local, 5)
            with self.assertLogs('kairos', level='WARNING') as logged:
                report = cycle(local, offsite.DirDestination(remote))
            sent = remote_names(remote)
            self.assertNotIn(plain.name, sent, 'the plain copy stays where it is')
            self.assertNotIn(plain.name + '.json', sent)
            self.assertEqual([n for n in sent if not n.endswith('.json')], sorted([sealed.name, Path(report['path']).name]), 'the encrypted copies do go')
            for name in sent:
                if not name.endswith('.json'):
                    self.assertTrue((remote / name).read_bytes().startswith(backup.AGE_MAGIC), name)
            self.assertEqual(report['offsite']['skipped_plain'], [plain.name])
            self.assertTrue(plain.exists(), 'and it is not deleted locally either')
            self.assertEqual((logged.records[0].kairos_event, logged.records[0].kairos_fields), ('backup_offsite_plain_skipped', {'destination': 'dir', 'count': 1}))
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 1, 'a plain copy that stays home is not a failure of the cycle')

    def test_a_manifest_that_says_encrypted_over_a_file_that_is_not_age_is_not_sent(self):
        import hashlib
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            liar = seeded_copy(local, 6)
            liar.write_bytes(PAYLOAD)  # the manifest still claims `encrypted`, the bytes are a plain dump
            manifest = json.loads(Path(str(liar) + '.json').read_text(encoding='utf-8'))
            manifest.update(sha256=hashlib.sha256(PAYLOAD).hexdigest(), bytes=len(PAYLOAD))
            Path(str(liar) + '.json').write_text(json.dumps(manifest), encoding='utf-8')
            report = cycle(local, offsite.DirDestination(remote))
            self.assertNotIn(liar.name, remote_names(remote))
            self.assertEqual(report['offsite']['skipped_plain'], [liar.name])

    def test_a_plain_copy_made_by_the_cycle_itself_is_refused_before_anything_is_sent(self):
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            with self.assertRaises(backup.BackupError) as raised:
                cycle(local, offsite.DirDestination(remote), make_copy=make_copy_factory(encrypted=False))
            self.assertEqual(raised.exception.code, 'backup_encryption_required')
            self.assertEqual(remote_names(remote), [])
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0)

    def test_a_manifest_cut_short_at_the_destination_is_sent_again_with_its_copy(self):
        """rclone 1.60 writes over the final name: a transfer that stopped leaves a truncated manifest that a cycle used to take for a complete copy."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            first = cycle(local, offsite.DirDestination(remote))
            name = Path(first['path']).name
            good = (remote / (name + '.json')).read_bytes()
            damages = {'truncated': good[:40], 'empty': b'', 'wrong sha256': good.replace(first['sha256'].encode(), b'0' * 64), 'another file': good.replace(name.encode(), b'kairos-cycle-19990101T000000Z.dump.age')}
            later = NOW
            for what, damaged in damages.items():
                self.assertNotEqual(damaged, good, what)
                (remote / (name + '.json')).write_bytes(damaged)
                (remote / name).write_bytes(b'stale bytes ' + what.encode())  # the copy is there too, but not as it should be
                later = later.replace(day=later.day + 1)
                second = cycle(local, offsite.DirDestination(remote), now=later)
                self.assertIn(name, second['offsite']['uploaded'], what)
                self.assertEqual((remote / (name + '.json')).read_bytes(), good, what)
                self.assertEqual((remote / name).read_bytes(), (local / name).read_bytes(), what)
            self.assertNotIn(name, cycle(local, offsite.DirDestination(remote), now=later.replace(day=later.day + 1))['offsite']['uploaded'], 'a complete copy is left alone')

    def test_the_retention_of_the_destination_never_deletes_a_copy_newer_than_the_protected_one(self):
        """Two cycles at once, or a destination shared with another installation, with REMOTE_KEEP=1: the newer copy of the other is not ours to delete."""
        with workspace() as root:
            remote = root / 'remote'
            remote.mkdir()
            for day in (1, 2, 3, 4):
                seeded_copy(remote, day)
            protected = f'kairos-before-{stamp(2)}.dump.age'
            result = offsite.prune_remote(offsite.DirDestination(remote), 1, protected, NOW)
            self.assertEqual(result['deleted'], [f'kairos-before-{stamp(1)}.dump.age'])
            self.assertEqual(sorted(p.name for p in remote.iterdir() if p.name.endswith('.age')), [f'kairos-before-{stamp(d)}.dump.age' for d in (2, 3, 4)])
            self.assertEqual(result['kept'], 3, 'the protected copy and the two newer ones')
            self.assertEqual(len([p for p in remote.iterdir() if p.name.endswith('.json')]), 3, 'no manifest outlives its copy and none is lost')

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
        with contextlib.redirect_stderr(stderr), self.assertLogs('kairos', level='ERROR') as logged:
            offsite.run_loop(one, 90, sleep=sleeps.append, cycles=3, out=outputs.append)
        self.assertEqual([(r.kairos_event, r.kairos_fields) for r in logged.records], [('backup_cycle_failed', {'exc_type': 'RuntimeError'})], 'the structured event carries the type, never the message')
        self.assertNotIn('secret-dsn', ' '.join(observability.JsonFormatter().format(r) for r in logged.records))
        self.assertEqual(sleeps, [90, 90], 'a sleep between cycles, none after the last')
        self.assertEqual(len(outputs), 2)
        self.assertIn('backup_offsite_failed: down', stderr.getvalue())
        self.assertIn('RuntimeError', stderr.getvalue())
        self.assertNotIn('secret-dsn', stderr.getvalue(), 'the message of an unexpected error is never printed')

    def test_a_backup_error_of_a_cycle_is_logged_with_its_code(self):
        def one():
            raise backup.BackupError('backup_dump_unavailable', 'the pg_dump program could not be run')
        with contextlib.redirect_stderr(io.StringIO()), self.assertLogs('kairos', level='ERROR') as logged:
            offsite.run_loop(one, 1, sleep=lambda s: None, cycles=1, out=lambda s: None)
        self.assertEqual([(r.kairos_event, r.kairos_fields) for r in logged.records], [('backup_cycle_failed', {'exc_type': 'BackupError', 'code': 'backup_dump_unavailable'})])

    def test_a_failure_of_the_local_retention_is_logged_as_a_failed_cycle_in_the_loop(self):
        """The copy is at the destination and its report is printed, but the cycle failed: the event is the one the operator alerts on."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            for error in (backup.BackupError('backup_prune_failed', '1 old copy could not be deleted'), PermissionError('secret path')):
                with patch.object(offsite, 'prune_backups', side_effect=error), contextlib.redirect_stderr(io.StringIO()), self.assertLogs('kairos', level='ERROR') as logged:
                    offsite.run_loop(lambda: cycle(local, offsite.DirDestination(remote)), 1, sleep=lambda s: None, cycles=1, out=lambda s: None)
                self.assertEqual([(r.kairos_event, r.kairos_fields) for r in logged.records],
                                 [('backup_cycle_failed', {'exc_type': type(error).__name__, 'code': getattr(error, 'code', 'backup_prune_failed')})])
                self.assertNotIn('secret path', ' '.join(observability.JsonFormatter().format(r) for r in logged.records))

    def test_stop_signals_end_the_loop(self):
        def stop():
            raise SystemExit(143)
        with self.assertRaises(SystemExit):
            offsite.run_loop(stop, 1, sleep=lambda s: None, cycles=3, out=lambda s: None)


@unittest.skipUnless(shutil.which('rclone'), 'rclone is required (the test image installs it)')
class RcloneDestinationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'RCLONE_CONFIG': '', 'RCLONE_LOG_FILE': '', 'RCLONE_LOG_LEVEL': ''}))

    def configure(self, root):
        """A remote of type `local` written here, in a configuration file of the test: no cloud service and no credential."""
        configuration = root / 'rclone.conf'
        configuration.write_text('[vault]\ntype = local\n', encoding='utf-8')
        os.environ['RCLONE_CONFIG'] = str(configuration)
        self.log = root / 'rclone.log'  # what rclone says stays in the test's own directory, never in the product
        os.environ.update(RCLONE_LOG_FILE=str(self.log), RCLONE_LOG_LEVEL='ERROR')

    def tail(self):
        return self.log.read_text(encoding='utf-8', errors='replace')[-800:] if self.log.exists() else ''

    def works_for(self, directory):
        """Positive control: this rclone lists an existing directory of the configured remote, so a failure below is the destination's and not a broken rclone."""
        try:
            listing = offsite.parse_destination(f'rclone:vault:{Path(directory).as_posix()}').names()
        except offsite.OffsiteError:
            probe = subprocess.run(['rclone', 'lsf', '--files-only', f'vault:{Path(directory).as_posix()}'], capture_output=True, text=True)
            umask = os.umask(0)
            os.umask(umask)
            self.fail(f'rclone cannot list {directory} here: exit {probe.returncode}, stderr {probe.stderr[-500:]!r}, config {os.environ.get("RCLONE_CONFIG")} exists={Path(os.environ["RCLONE_CONFIG"]).exists()} '
                      f'cwd={os.getcwd()} which={shutil.which("rclone")} umask={oct(umask)} environment keys={sorted(k for k in os.environ if k.startswith(("RCLONE", "HOME", "TMP", "XDG")))}')
        self.assertIsInstance(listing, set, self.tail())

    def test_a_local_remote_receives_the_copy_verifies_it_and_applies_the_retention(self):
        with workspace() as root:
            self.configure(root)
            local, remote = root / 'local', root / 'remote'
            local.mkdir()
            remote.mkdir()
            for day in (1, 2, 3):
                seeded_copy(remote, day)
            destination = offsite.parse_destination(f'rclone:vault:{remote.as_posix()}')
            try:
                report = cycle(local, destination, remote_keep=2)
            except offsite.CycleError as error:
                self.fail(f'{error}; rclone said: {self.tail()}')
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
            self.works_for(root)
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
            self.works_for(root)
            with self.assertRaises(offsite.CycleError) as raised:
                cycle(local, offsite.parse_destination('rclone:nosuchremote-s3cr3t:bucket'))
            self.assertEqual(raised.exception.code, 'backup_offsite_failed')
            self.assertNotIn('s3cr3t', str(raised.exception))


class CommandTests(unittest.TestCase):
    """The real command line over a real database (the dump and `age` are doubles: the cycle's own steps are what is under test; the real pair is the rehearsal's and test_backup_encryption's)."""

    def setUp(self):
        from memory_platform.tests.test_store import create_core
        self.store, self.actor, self.project = create_core()
        folder = Path(tempfile.mkdtemp(prefix='kairos-cycle-recipients-'))
        self.addCleanup(shutil.rmtree, folder, True)
        self.recipients = folder / 'recipients.txt'
        self.recipients.write_text('# public recipient\nage1' + 'q' * 58 + '\n', encoding='utf-8')
        self.environ = {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': '', 'MEMORY_BACKUP_RECIPIENTS_FILE': str(self.recipients), 'MEMORY_BACKUP_REQUIRE_ENCRYPTION': '0', 'MEMORY_BACKUP_KEEP': '',
                        'MEMORY_BACKUP_DESTINATION': '', 'MEMORY_BACKUP_REMOTE_KEEP': '', 'MEMORY_BACKUP_INTERVAL': ''}
        self.created = []

        def fake_create(store, output, *, environment, recipients=None):
            self.created.append((output, recipients))
            return write_copy_at(output, AGE_PAYLOAD if recipients else PAYLOAD, bool(recipients), backup.recipient_digests(recipients or []), datetime.now(timezone.utc))
        self.fake_create = fake_create

    def run_command(self, *argv, **environ):
        output, errors = io.StringIO(), io.StringIO()
        failure = None
        with (patch.dict(os.environ, dict(self.environ, **environ)), patch.object(admin, 'create_backup', self.fake_create), patch.object(backup.shutil, 'which', lambda name, *a, **k: '/usr/bin/' + name),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
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
            self.assertTrue(copy.name.endswith('.dump.age'), 'the cycle encrypts for the recipients')
            self.assertEqual(self.created[0][1], ['age1' + 'q' * 58])
            self.assertEqual((remote / copy.name).read_bytes(), AGE_PAYLOAD)
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
            self.assertEqual(no_copies(local), [])
            self.assertEqual(self.created, [])

    def test_a_refused_start_zeroes_the_metric_so_a_restarting_service_never_keeps_a_stale_one(self):
        """The validation of the settings fails before any cycle (no recipients, an unreadable file, a bad destination): with `restart: unless-stopped` the `.prom` would stay at 1 for ever."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            remote.mkdir()
            local.mkdir()
            for environ in ({'MEMORY_BACKUP_RECIPIENTS_FILE': ''}, {'MEMORY_BACKUP_RECIPIENTS_FILE': str(root / 'missing.txt')}, {'MEMORY_BACKUP_DESTINATION': 'ftp://x'}, {'MEMORY_BACKUP_REMOTE_KEEP': '0'}):
                observability.record_offsite(True)
                (local / offsite.METRICS_NAME).write_text('kairos_backup_offsite_success 1.0\n', encoding='utf-8')
                failure, out, err = self.run_command('--output-dir', str(local), **dict({'MEMORY_BACKUP_DESTINATION': 'dir:' + str(remote)}, **environ))
                self.assertTrue(failure, environ)
                self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0, environ)
                self.assertIn('kairos_backup_offsite_success 0.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'), environ)
            self.assertEqual(no_copies(local), [])

    def test_a_destination_without_recipients_is_refused_whatever_the_encryption_requirement_says_and_nothing_is_written_or_sent(self):
        """The external copy in the clear is not an option: MEMORY_BACKUP_REQUIRE_ENCRYPTION=0 (or unset) does not open it."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            remote.mkdir()
            for require in ('0', '1', '', 'off'):
                for loop in ((), ('--loop',)):
                    with patch.object(admin, 'LOOP_CYCLES', 1), patch.object(offsite.time, 'sleep', lambda seconds: None):  # a refusal that did not happen must not loop for ever
                        failure, out, err = self.run_command('--output-dir', str(local), *loop, MEMORY_BACKUP_DESTINATION='dir:' + str(remote), MEMORY_BACKUP_RECIPIENTS_FILE='',
                                                             MEMORY_BACKUP_REQUIRE_ENCRYPTION=require)
                    self.assertTrue((failure or '').startswith('backup_encryption_required: '), (require, loop, failure))
                    self.assertEqual(out, '')
            self.assertEqual(no_copies(local), [], 'no copy was made')
            self.assertEqual(self.created, [])
            self.assertEqual(remote_names(remote), [], 'and nothing was sent')

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
            self.assertEqual(len([p for p in remote.iterdir() if p.name.endswith('.dump.age')]), 2)

    def test_a_cycle_that_fails_before_the_copy_is_made_still_zeroes_the_metric(self):
        """The recipients file that stops being usable between two cycles: the failure is of the encryption stage, before `run_cycle`; the metric and the `.prom` file say 0."""
        with workspace() as root:
            local, remote = root / 'local', root / 'remote'
            remote.mkdir()
            real = admin.encryption_plan
            calls = []

            def breaks_on_the_third_call(*args):
                calls.append(1)
                if len(calls) >= 3:
                    raise backup.BackupError('backup_recipients_invalid', 'MEMORY_BACKUP_RECIPIENTS_FILE cannot be read')
                return real(*args)
            with patch.object(offsite.time, 'sleep', lambda s: None), patch.object(admin, 'LOOP_CYCLES', 2), patch.object(admin, 'encryption_plan', breaks_on_the_third_call):
                failure, out, err = self.run_command('--output-dir', str(local), '--loop', MEMORY_BACKUP_DESTINATION='dir:' + str(remote))
            self.assertIsNone(failure, err)
            self.assertIn('backup_recipients_invalid', err)
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0)
            self.assertIn('kairos_backup_offsite_success 0.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'))


class CorruptingDestination(offsite.DirDestination):
    """A destination that stores the copy with one byte changed (a bad disk, a bad network): the copy and its size look right, its sha256 does not."""

    def put(self, source, name):
        super().put(source, name)
        if not name.endswith('.json'):
            data = bytearray((self.root / name).read_bytes())
            data[300] ^= 0x01
            (self.root / name).write_bytes(bytes(data))


class OffsiteFailureTests(unittest.TestCase):
    def seeded(self, root, local_days=(5, 6, 7), remote_days=(1, 2, 3)):
        local, remote = root / 'local', root / 'remote'
        local.mkdir()
        remote.mkdir()
        for day in local_days:
            seeded_copy(local, day)
        for day in remote_days:
            seeded_copy(remote, day)
        return local, remote

    def test_an_unreachable_destination_is_logged_zeroes_the_metric_keeps_every_local_copy_and_the_next_cycle_sends_again(self):
        with workspace() as root:
            local, remote = self.seeded(root, remote_days=())
            before = names(local)
            absent = offsite.DirDestination(root / 'absent')
            with self.assertLogs('kairos', level='ERROR') as logged:
                with self.assertRaises(offsite.CycleError) as raised:
                    cycle(local, absent, keep=1)
            self.assertEqual(raised.exception.code, 'backup_offsite_failed')
            record = logged.records[0]
            self.assertEqual((record.kairos_event, record.kairos_fields), ('backup_offsite_failed', {'destination': 'dir', 'code': 'backup_offsite_failed'}))
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0)
            self.assertIn('kairos_backup_offsite_success 0.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'))
            failed_copy = Path(raised.exception.report['path']).name
            self.assertEqual(raised.exception.report['offsite'], {'destination': 'dir', 'status': 'failed', 'code': 'backup_offsite_failed'})
            self.assertNotIn('prune', raised.exception.report, 'nothing local is pruned when the copy did not leave')
            self.assertEqual(sorted(n for n in names(local) if n.endswith(('.age', '.json'))), sorted(before + [failed_copy, failed_copy + '.json']), 'every local copy is intact, with keep=1')
            later = datetime(2026, 11, 21, tzinfo=timezone.utc)
            report = cycle(local, offsite.DirDestination(remote), now=later, make_copy=make_copy_factory())
            self.assertIn(failed_copy, report['offsite']['uploaded'], 'the copy of the failed cycle is sent by the next one')
            self.assertIn(Path(report['path']).name, report['offsite']['uploaded'])
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 1)
            self.assertIn('kairos_backup_offsite_success 1.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'))

    def test_a_cycle_that_fails_at_any_stage_zeroes_the_metric_stamps_the_time_and_rewrites_the_file(self):
        """After a good cycle (metric 1) a failure of the database, pg_dump, the encryption, the local check or the destination must not leave the 1 standing (alerts read it)."""
        honest = make_copy_factory()

        def damaged(output):
            report = honest(output)
            data = bytearray(Path(report['path']).read_bytes())
            data[300] ^= 0x01
            Path(report['path']).write_bytes(bytes(data))
            return report
        stages = {'database down': Mock(side_effect=RuntimeError('connection refused')), 'pg_dump': Mock(side_effect=subprocess.CalledProcessError(1, 'pg_dump')),
                  'encryption': Mock(side_effect=backup.BackupError('backup_encryption_failed', 'age failed')), 'local verification': damaged, 'plain copy': make_copy_factory(encrypted=False)}
        for stage, failing in stages.items():
            with self.subTest(stage), workspace() as root:
                local, remote = root / 'local', root / 'remote'
                local.mkdir()
                remote.mkdir()
                cycle(local, offsite.DirDestination(remote))
                self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 1)
                self.assertIn('kairos_backup_offsite_success 1.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'))
                before = time.time()
                with self.assertRaises(Exception) as raised:
                    cycle(local, offsite.DirDestination(remote), now=datetime(2026, 11, 21, tzinfo=timezone.utc), make_copy=failing)
                self.assertIs(raised.exception.offsite_recorded, True)
                self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0, stage)
                self.assertGreaterEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_last_run_timestamp_seconds'), before, stage)
                self.assertIn('kairos_backup_offsite_success 0.0', (local / offsite.METRICS_NAME).read_text(encoding='utf-8'), stage)

    def test_a_copy_that_differs_at_the_destination_is_not_completed_and_nothing_is_deleted_anywhere(self):
        with workspace() as root:
            local, remote = self.seeded(root)
            local_before, remote_before = names(local), remote_names(remote)
            with self.assertLogs('kairos', level='ERROR') as logged:
                with self.assertRaises(offsite.CycleError) as raised:
                    cycle(local, CorruptingDestination(remote), keep=1, remote_keep=1)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            self.assertEqual(logged.records[0].kairos_fields['code'], 'backup_checksum_mismatch')
            new = Path(raised.exception.report['path']).name
            self.assertFalse((remote / (new + '.json')).exists(), 'a copy that does not match never gets its manifest at the destination')
            self.assertTrue(set(remote_before) <= set(remote_names(remote)), 'nothing was deleted at the destination, with remote_keep=1')
            self.assertTrue(set(local_before) <= set(names(local)), 'nothing was deleted locally, with keep=1')
            self.assertEqual(observability.OFFSITE_REGISTRY.get_sample_value('kairos_backup_offsite_success'), 0)

    def test_a_local_copy_that_no_longer_matches_its_manifest_is_never_sent_and_nothing_is_deleted(self):
        with workspace() as root:
            local, remote = self.seeded(root)
            local_before, remote_before = names(local), remote_names(remote)
            honest = make_copy_factory()

            def damaged(output):
                report = honest(output)
                data = bytearray(Path(report['path']).read_bytes())
                data[300] ^= 0x01
                Path(report['path']).write_bytes(bytes(data))
                return report
            with self.assertRaises(backup.BackupError) as raised:
                cycle(local, offsite.DirDestination(remote), keep=1, remote_keep=1, make_copy=damaged)
            self.assertEqual(raised.exception.code, 'backup_checksum_mismatch')
            self.assertEqual(remote_names(remote), remote_before, 'nothing was sent and nothing was deleted at the destination')
            self.assertTrue(set(local_before) <= set(names(local)))

    def test_a_copy_swapped_for_a_link_between_the_check_and_the_upload_sends_no_bytes_in_the_clear(self):
        """CWE-367: the header and the sha256 are checked on the descriptor that is then uploaded, opened without following links."""
        with workspace() as root:
            local, remote = self.seeded(root, local_days=(5, 6), remote_days=())
            secret = root / 'plain.dump'
            secret.write_bytes(b'PGDMP in the clear ' * 100)
            real = offsite.verify_backup

            def swapping(path, *args, **kwargs):
                result = real(path, *args, **kwargs)
                if path.name.endswith(stamp(5) + '.dump.age'):
                    path.unlink()
                    try:
                        os.symlink(secret, path)
                    except (OSError, NotImplementedError):
                        self.skipTest('symbolic links are not available here')
                return result
            with patch.object(offsite, 'verify_backup', swapping):
                report = cycle(local, offsite.DirDestination(remote), keep=7)
            for path in remote.iterdir():
                self.assertNotIn(b'in the clear', path.read_bytes(), path.name)
            self.assertIn(f'kairos-before-{stamp(5)}.dump.age', [item['name'] for item in report['offsite']['skipped']])
            self.assertNotIn(f'kairos-before-{stamp(5)}.dump.age', remote_names(remote))

    def test_a_copy_replaced_by_one_in_the_clear_is_not_sent_either(self):
        """The same window without a link: a regular file in the clear at the name of the copy fails the header and the sha256 of the descriptor."""
        with workspace() as root:
            local, remote = self.seeded(root, local_days=(5, 6), remote_days=())
            real = offsite.verify_backup

            def replacing(path, *args, **kwargs):
                result = real(path, *args, **kwargs)
                if path.name.endswith(stamp(5) + '.dump.age'):
                    path.write_bytes(b'PGDMP in the clear ' * 100)
                return result
            with patch.object(offsite, 'verify_backup', replacing):
                report = cycle(local, offsite.DirDestination(remote), keep=7)
            for path in remote.iterdir():
                self.assertNotIn(b'in the clear', path.read_bytes(), path.name)
            self.assertIn(f'kairos-before-{stamp(5)}.dump.age', [item['name'] for item in report['offsite']['skipped']])

    def test_a_copy_changed_after_the_check_is_not_sent_even_with_the_age_header(self):
        """The sha256 of the descriptor is part of the check: bytes other than the manifest's never leave, whatever they start with."""
        with workspace() as root:
            local, remote = self.seeded(root, local_days=(5, 6), remote_days=())
            real = offsite.verify_backup

            def changing(path, *args, **kwargs):
                result = real(path, *args, **kwargs)
                if path.name.endswith(stamp(5) + '.dump.age'):
                    path.write_bytes(AGE_PAYLOAD + b'one more block of something else')
                return result
            with patch.object(offsite, 'verify_backup', changing):
                report = cycle(local, offsite.DirDestination(remote), keep=7)
            self.assertEqual([item for item in report['offsite']['skipped'] if item['name'].endswith(stamp(5) + '.dump.age')],
                             [{'name': f'kairos-before-{stamp(5)}.dump.age', 'code': 'backup_checksum_mismatch'}])
            self.assertNotIn(f'kairos-before-{stamp(5)}.dump.age', remote_names(remote), 'it was not even put at the destination')

    def test_an_older_local_copy_that_no_longer_verifies_is_skipped_and_never_sent(self):
        with workspace() as root:
            local, remote = self.seeded(root, remote_days=())
            damaged = next(p for p in local.iterdir() if p.name.endswith(stamp(7) + '.dump.age'))
            damaged.write_bytes(damaged.read_bytes()[:-1])
            report = cycle(local, offsite.DirDestination(remote))
            self.assertIn({'name': damaged.name, 'code': 'backup_checksum_mismatch'}, report['offsite']['skipped'])
            self.assertFalse((remote / damaged.name).exists())

    def test_what_the_destination_or_rclone_prints_never_reaches_the_report_the_log_or_the_error(self):
        secret = 'hunter2-s3cr3t'
        with workspace() as root:
            local = root / 'local'
            local.mkdir()
            destination = offsite.parse_destination(f'rclone:vault:{secret}-bucket/path')
            failures = [subprocess.CompletedProcess([], 3, stdout=(secret + '\n').encode(), stderr=secret.encode()), subprocess.TimeoutExpired(['rclone', secret], 10), OSError(secret)]
            for failure in failures:
                side_effect = [failure] if isinstance(failure, Exception) else [failure]
                with patch.dict(os.environ, {'RCLONE_CONFIG_VAULT_PASS': secret}), patch.object(offsite.subprocess, 'run', side_effect=side_effect):
                    with self.assertLogs('kairos', level='ERROR') as logged:
                        with self.assertRaises(offsite.CycleError) as raised:
                            cycle(local, destination, make_copy=make_copy_factory())
                everything = ' '.join([str(raised.exception), json.dumps(raised.exception.report), *(observability.JsonFormatter().format(r) for r in logged.records)])
                self.assertNotIn(secret, everything)
                self.assertNotIn('bucket', everything, 'not even the path of the remote')
                self.assertEqual(raised.exception.code, 'backup_offsite_failed')
                for leftover in local.iterdir():
                    leftover.unlink()

    def test_rclone_is_started_without_a_shell_and_the_names_come_from_the_tool(self):
        calls, stdins = [], []
        destination = offsite.parse_destination('rclone:vault:folder')

        def run(command, **kw):
            calls.append(command)
            stdins.append(kw['stdin'])
            return subprocess.CompletedProcess(command, 0, stdout=b'a.dump\n\nb.json\n', stderr=b'')
        source = io.BytesIO(b'age-encryption.org/v1\n')
        with patch.object(offsite.subprocess, 'run', side_effect=run):
            self.assertEqual(destination.names(), {'a.dump', 'b.json'})
            destination.put(source, 'kairos-cycle-20261120T000000000000Z.dump')
            destination.delete('kairos-cycle-20261120T000000000000Z.dump')
        self.assertEqual([c[0] for c in calls], ['rclone'] * 3)
        self.assertEqual([c[len(offsite.RCLONE_FLAGS) + 1] for c in calls], ['lsf', 'rcat', 'deletefile'])
        self.assertIs(stdins[1], source, 'the upload reads the descriptor that was checked, rclone never opens a path')
        self.assertEqual(stdins[0], subprocess.DEVNULL)
        self.assertEqual(calls[1][-1], 'vault:folder/kairos-cycle-20261120T000000000000Z.dump')
        self.assertEqual(offsite.RcloneDestination('vault:').target('x'), 'vault:x')
