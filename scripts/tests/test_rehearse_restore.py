"""scripts/rehearse-restore.py (C-01, CA-07): the restore rehearsal follows the runbook with doubles for docker; the private key stays out of the project's containers, the restore goes to
a NEW ephemeral PostgreSQL and everything is removed (the key and the temporary directory included, by exact name, and the cleanup goes on after a failing command)."""
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import re
import shutil
import signal
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('kairos_rehearse_restore', ROOT / 'scripts' / 'rehearse-restore.py')
rehearse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearse)

COPY = 'kairos-cycle-20261116T120000123456Z.dump.age'
PAYLOAD = b'age-encryption.org/v1\n' + bytes(range(200))
PLAIN = b'PGDMP' + bytes(range(100))
PUBLIC = 'age1' + 'q' * 58
FOREIGN = 'kairos-ops-b2-restore-pg-0a1b2c3d'  # a container of ANOTHER rehearsal whose project name starts with this one's


def host_of(command, target):
    """The host side of the `-v <host>:<target>[:mode]` that mounts `target`."""
    for position, token in enumerate(command):
        if token == '-v' and re.search(r':' + re.escape(target) + r'(?::\w+)?$', command[position + 1]):
            return Path(re.sub(r':' + re.escape(target) + r'(?::\w+)?$', '', command[position + 1]))
    raise KeyError(target)


class FakeDocker:
    """Answers the commands of the rehearsal the way the real ones would, keeps the containers, networks and volumes it was asked to create (so that what is left can be found), and records them."""

    def __init__(self, rehearsal, **faults):
        self.rehearsal, self.faults, self.commands, self.key_at_cleanup = rehearsal, faults, [], None
        self.state = {'ps': set(faults.get('foreign', ())), 'volume': set(), 'network': set()}
        self.after_down, self.target_dsn, self.restore_command = False, None, None

    def __call__(self, command, timeout=None, environment=None):
        self.commands.append((list(command), dict(environment or {})))
        work = self.rehearsal.work
        text = ' '.join(command)
        if command[:2] == ['docker', 'ps'] or command[:3] in (['docker', 'volume', 'ls'], ['docker', 'network', 'ls']):
            kind = 'ps' if command[1] == 'ps' else command[1]
            wanted = command[command.index('--filter') + 1]
            if wanted.startswith('label='):
                if kind == 'ps' and self.faults.get('existing') and not self.after_down:
                    return 0, 'kairos-ops-b-memory-api-1\n', ''
                return 0, (self.faults.get('left_label', '') if kind == 'ps' and self.after_down else ''), ''
            return 0, ''.join(name + '\n' for name in sorted(self.state[kind]) if re.search(wanted[len('name='):], name)), ''
        if command[:2] == ['docker', 'compose'] and 'down' in command:
            if self.key_at_cleanup is None:
                self.key_at_cleanup = (work / 'keys' / 'identity.txt').exists()
            self.after_down = True
        if command[:3] == ['docker', 'network', 'create']:
            self.state['network'].add(command[-1])
            return 0, '', ''
        if command[:3] == ['docker', 'volume', 'create']:
            self.state['volume'].add(command[-1])
            return 0, '', ''
        if command[:3] in (['docker', 'network', 'rm'], ['docker', 'volume', 'rm']):
            self.state[command[1]].discard(command[-1])
            return 0, '', ''
        if command[:3] == ['docker', 'rm', '--force']:
            if self.faults.get('rm_raises'):
                raise rehearse.RehearsalError('A command could not run or timed out')
            if not self.faults.get('rm_fails'):
                self.state['ps'].discard(command[-1])
            return (1 if self.faults.get('rm_fails') else 0), '', ''
        if command[:2] == ['docker', 'run'] and '-d' in command:
            self.state['ps'].add(command[command.index('--name') + 1])
            self.server = command
            return 0, command[command.index('--name') + 1], ''
        if 'pg_isready' in command:
            return (1 if self.faults.get('never_ready') else 0), '', ''
        if 'psql' in command:
            return 0, '', ''
        if 'deploy-memory.py' in text:
            (work / 'secrets').mkdir(exist_ok=True)
            (work / 'secrets' / 'dsn').write_text('postgresql://memory:pw%2Bx@memory-postgres:5432/agent_memory\n', encoding='utf-8')
            return 0, '', ''
        if 'umask 077' in text and 'age-keygen' in text:
            self.keygen = list(command)
            (host_of(command, '/keys') / 'identity.txt').write_text(f'# created: 2026-11-16T12:00:00Z\n# public key: {PUBLIC}\nAGE-SECRET' + '-KEY-FAKE\n', encoding='utf-8')
            return 0, '', ''
        if 'age-keygen' in command and '-y' in command:
            return 0, PUBLIC + '\n', ''
        if 'shred' in command and command[:2] == ['docker', 'run']:
            if self.faults.get('shred_fails'):
                return 1, '', 'boom'
            (host_of(command, '/keys') / 'identity.txt').unlink()
            return 0, '', ''
        if 'backup-cycle' in command:
            if self.faults.get('sigterm'):
                signal.raise_signal(signal.SIGTERM)
            offsite = Path(environment['MEMORY_BACKUP_OFFSITE_DIR'])
            (offsite / COPY).write_bytes(PAYLOAD)
            sha = hashlib.sha256(PAYLOAD).hexdigest() if not self.faults.get('wrong_sha') else '0' * 64
            (offsite / (COPY + '.json')).write_text(json.dumps({'sha256': sha}), encoding='utf-8')
            offsite_state = {'status': 'failed', 'code': 'backup_offsite_failed'} if self.faults.get('cycle_fails') else {'status': 'verified', 'destination': 'dir'}
            return 0, json.dumps({'status': 'backed_up', 'path': '/backups/' + COPY, 'bytes': len(PAYLOAD), 'encrypted': True, 'offsite': offsite_state}), ''
        if command[:2] == ['docker', 'run'] and 'age' in command and '--decrypt' in command:
            (host_of(command, '/restore') / 'plain.dump').write_bytes(PLAIN)
            return 0, '', ''
        if 'verify-backup' in command:
            content = '--manifest' in command and not self.faults.get('content_wrong')
            return 0, json.dumps({'status': 'verified', 'encrypted': True, 'verified': 'content' if content else 'copy'}), ''
        if 'restore-check' in command:
            self.restore_command = list(command)
            self.target_dsn = (host_of(command, '/restore') / 'target.dsn').read_text(encoding='utf-8').strip()
            status = 'backup_restore_mismatch' if self.faults.get('mismatch') else 'restored_and_content_verified'
            return 0, json.dumps({'status': status, 'tables': {'actors': {'rows': 1, 'sha256': 'a' * 64}}}), ''
        return 0, '', ''


ROOTS = []


def make(**faults):
    args = SimpleNamespace(project_name='kairos-ops-b', embed_stub=True, api_port=28792, web_port=25175)
    ROOTS.append(Path(tempfile.mkdtemp(prefix='kairos-rehearse-test-')))
    rehearsal = rehearse.Rehearsal(args, root=ROOTS[-1])
    fake = FakeDocker(rehearsal, **faults)
    rehearsal.run_command = fake
    rehearsal.sleep = lambda seconds: None
    return rehearsal, fake


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.rehearsal = None
        self.addCleanup(lambda: [shutil.rmtree(root, ignore_errors=True) for root in ROOTS])
        self.addCleanup(lambda: self.rehearsal and self.rehearsal.work and shutil.rmtree(self.rehearsal.work, ignore_errors=True))

    def test_the_rehearsal_follows_the_runbook_in_order_and_ends_with_the_verified_restore(self):
        self.rehearsal, fake = make()
        result = self.rehearsal.apply()
        self.assertEqual(result['status'], 'restored_and_content_verified')
        self.assertEqual(result['steps'], ['deploy', 'keys', 'cycle', 'download', 'verify', 'decrypt', 'restore'])
        self.assertEqual(result['cleanup'], 'complete')
        self.assertEqual(result['cycle']['copy'], COPY)
        self.assertEqual(result['restore']['tables'], 1)
        flat = [' '.join(command) for command, environment in fake.commands]
        order = [next(n for n, line in enumerate(flat) if marker in line) for marker in ('deploy-memory.py', 'age-keygen', 'backup-cycle', '--decrypt', 'restore-check')]
        self.assertEqual(order, sorted(order))
        self.assertFalse(self.rehearsal.work.exists(), 'the temporary directory (key, copy, secrets) is gone')
        self.assertEqual(fake.state, {'ps': set(), 'volume': set(), 'network': set()}, 'nothing of the rehearsal is left in docker')

    def test_the_private_key_never_reaches_a_container_of_the_project_and_the_tools_have_no_network(self):
        self.rehearsal, fake = make()
        self.rehearsal.apply()
        work = str(self.rehearsal.work)
        for command, environment in fake.commands:
            flat = ' '.join(command)
            if command[:2] == ['docker', 'compose']:
                self.assertNotIn(work + '/keys', flat.replace('\\', '/'), flat)
                self.assertNotIn('identity', flat)
                self.assertNotIn('/keys', flat)
                self.assertNotIn(str(Path(work) / 'keys'), flat)
                self.assertNotIn('/keys', ' '.join(environment.values()))
            if '/keys' in flat:
                self.assertEqual(command[:2], ['docker', 'run'], flat)
                self.assertIn('none', command[command.index('--network') + 1], 'the containers that hold the key have no network')
        self.assertTrue([c for c, e in fake.commands if '/keys' in ' '.join(c)], 'positive control: the tools do mount it')
        services = {c[c.index('memory-backup') + 1] for c, e in fake.commands if 'memory-backup' in c}
        self.assertEqual(services, {'backup-cycle'})
        cycle_environment = next(e for c, e in fake.commands if 'backup-cycle' in c)
        self.assertEqual(cycle_environment['MEMORY_BACKUP_DESTINATION'], 'dir:/offsite')
        self.assertTrue(cycle_environment['MEMORY_BACKUP_CONFIG_DIR'].endswith('config'))

    def test_the_key_is_destroyed_before_the_project_is_taken_down_and_nothing_names_the_installed_project(self):
        self.rehearsal, fake = make()
        self.rehearsal.apply()
        self.assertIs(fake.key_at_cleanup, False)
        for command, environment in fake.commands:
            self.assertNotRegex(' '.join(command), r'knowledge-graphs[-_]', 'no resource of the installed project is named')
            self.assertEqual([v for k, v in environment.items() if k.startswith('MEMORY_BACKUP') and 'knowledge-graphs' in v], [])
        self.assertTrue(all('kairos-ops-b' in ' '.join(c) for c, e in fake.commands if c[:3] in (['docker', 'volume', 'rm'], ['docker', 'network', 'rm'])))

    def test_the_restore_goes_to_a_new_ephemeral_postgres_and_never_to_the_cluster_of_the_source(self):
        """CA-07: an empty database of a NEW cluster, not of the one that made the copy."""
        self.rehearsal, fake = make()
        self.rehearsal.apply()
        flat = [' '.join(command) for command, environment in fake.commands]
        self.assertFalse([line for line in flat if 'memory-postgres' in line and ('exec' in line or 'psql' in line)], 'no command is run in the memory-postgres of the isolated project')
        started = fake.server
        name, network = started[started.index('--name') + 1], started[started.index('--network') + 1]
        self.assertRegex(name, r'^kairos-ops-b-restore-pg-[0-9a-f]{8}$')
        self.assertRegex(network, r'^kairos-ops-b-restore-net-[0-9a-f]{8}$')
        self.assertEqual(started[-1], 'rehearsal-kairos-ops-b-postgres:latest', 'the kairos-postgres image of the isolated project')
        self.assertNotIn('-p', started, 'no published port')
        self.assertNotIn('--publish', started)
        create = next(c for c, e in fake.commands if c[:3] == ['docker', 'network', 'create'])
        self.assertIn('--internal', create)
        self.assertEqual(fake.target_dsn.split('@')[1].split(':')[0], name, 'the target DSN names the ephemeral server')
        self.assertRegex(fake.target_dsn, r'/memory_restore_[0-9a-f]{12}$')
        self.assertNotIn('memory-postgres', fake.target_dsn)
        self.assertEqual(fake.restore_command[fake.restore_command.index('--network') + 1], network, 'the restore runs on the network of the ephemeral server')
        self.assertTrue(any(c[:2] == ['docker', 'exec'] and c[2] == name and 'CREATE DATABASE' in ' '.join(c) for c, e in fake.commands))
        self.assertFalse([c for c, e in fake.commands if c[:2] == ['docker', 'compose'] and ('exec' in c or 'restore-check' in c)], 'no compose exec/run for the restore')
        ready = flat.index(next(line for line in flat if 'pg_isready' in line))
        self.assertLess(ready, next(n for n, line in enumerate(flat) if 'CREATE DATABASE' in line), 'the server is awaited before the database is created')
        self.assertEqual(fake.state, {'ps': set(), 'volume': set(), 'network': set()})

    def test_a_server_that_never_becomes_ready_fails_the_step_and_is_still_removed(self):
        self.rehearsal, fake = make(never_ready=True)
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('did not become ready', str(raised.exception))
        self.assertEqual(fake.state, {'ps': set(), 'volume': set(), 'network': set()}, 'its container, network and volume are removed by name')

    def test_the_key_is_created_inside_its_container_with_a_restrictive_umask_and_the_host_never_changes_its_mode(self):
        modes = []
        real_chmod = os.chmod
        self.rehearsal, fake = make()
        with patch.object(rehearse.os, 'chmod', lambda path, mode, *a, **k: (modes.append(str(path)), real_chmod(path, mode, *a, **k))[1]):
            self.rehearsal.apply()
        self.assertIn('umask 077 && exec age-keygen -o /keys/identity.txt', ' '.join(fake.keygen))
        self.assertFalse([path for path in modes if path.endswith('identity.txt')], 'no chmod of a file that belongs to another uid')
        self.assertTrue(modes, 'positive control: the rehearsal does chmod its own directories')
        self.assertFalse([c for c, e in fake.commands if c[:2] != ['docker', 'run'] and 'identity.txt' in ' '.join(c)])

    def test_a_failing_step_still_removes_everything_and_reports_the_failure(self):
        for fault, text in (({'cycle_fails': True}, 'verified, encrypted copy'), ({'wrong_sha': True}, 'sha256 of its manifest'), ({'mismatch': True}, 'restore to the content'), ({'content_wrong': True}, 'content_sha256')):
            self.rehearsal, fake = make(**fault)
            with self.assertRaises(rehearse.RehearsalError) as raised:
                self.rehearsal.apply()
            self.assertIn(text, str(raised.exception))
            self.assertTrue([c for c, e in fake.commands if c[:2] == ['docker', 'compose'] and 'down' in c], 'the project is taken down after a failure')
            self.assertFalse(self.rehearsal.work.exists())
            self.assertIs(fake.key_at_cleanup, False)
            self.assertEqual(fake.state, {'ps': set(), 'volume': set(), 'network': set()})

    def test_a_sigterm_runs_the_cleanup_destroys_the_key_and_ends_with_the_signal_exit_status(self):
        before = signal.getsignal(signal.SIGTERM)
        self.rehearsal, fake = make(sigterm=True)
        with self.assertRaises(SystemExit) as raised:
            self.rehearsal.apply()
        self.assertEqual(raised.exception.code, 128 + signal.SIGTERM)
        self.assertIs(fake.key_at_cleanup, False, 'the key was shredded before the project came down')
        self.assertTrue([c for c, e in fake.commands if c[:2] == ['docker', 'compose'] and 'down' in c])
        self.assertFalse(self.rehearsal.work.exists())
        self.assertEqual(fake.state, {'ps': set(), 'volume': set(), 'network': set()})
        self.assertIs(signal.getsignal(signal.SIGTERM), before, 'the handler of the caller is put back')

    def test_a_cleanup_that_leaves_something_is_a_failure_even_when_the_restore_worked(self):
        self.rehearsal, fake = make(left_label='kairos-ops-b-memory-postgres-1\n')
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('incomplete', str(raised.exception))
        self.assertIn('kairos-ops-b-memory-postgres-1', str(raised.exception))

    def test_a_container_that_cannot_be_removed_is_reported_by_its_exact_name(self):
        self.rehearsal, fake = make(rm_fails=True)
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('incomplete', str(raised.exception))
        self.assertRegex(str(raised.exception), r'left in docker: kairos-ops-b-restore-pg-[0-9a-f]{8}')

    def test_a_command_that_fails_in_the_cleanup_does_not_stop_the_rest_and_the_original_failure_survives(self):
        self.rehearsal, fake = make(mismatch=True, rm_raises=True)
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('restore to the content', str(raised.exception), 'the failure that came first is the one raised')
        flat = [' '.join(c) for c, e in fake.commands]
        rm = max(n for n, line in enumerate(flat) if line.startswith('docker rm --force'))
        for later in ('docker compose', 'docker network rm', 'docker volume rm', 'docker image rm'):
            self.assertTrue([n for n, line in enumerate(flat) if line.startswith(later) and n > rm], f'{later} still ran after the command that failed')
        self.assertFalse(self.rehearsal.work.exists())
        self.assertIsNotNone(fake.key_at_cleanup)

    def test_a_key_that_cannot_be_destroyed_or_a_directory_that_stays_is_reported_never_swallowed(self):
        self.rehearsal, fake = make(shred_fails=True)
        with patch.object(rehearse.os, 'unlink', side_effect=PermissionError('not yours')):
            with self.assertRaises(rehearse.RehearsalError) as raised:
                self.rehearsal.apply()
        self.assertIn('incomplete', str(raised.exception))
        self.assertIn('private key', str(raised.exception))
        self.assertIn('PermissionError', str(raised.exception))
        leftover = self.rehearsal.work
        self.addCleanup(lambda: shutil.rmtree(leftover, ignore_errors=True))
        self.rehearsal, fake = make(shred_fails=True)
        with patch.object(rehearse.os, 'unlink', lambda path, *a, **k: None):  # the file is overwritten but a remove that does nothing leaves it there
            with self.assertRaises(rehearse.RehearsalError) as raised:
                self.rehearsal.apply()
        self.assertIn('the private key file is still there', str(raised.exception))
        leftover = self.rehearsal.work
        self.addCleanup(lambda: shutil.rmtree(leftover, ignore_errors=True))
        self.rehearsal, fake = make()
        with patch.object(rehearse.shutil, 'rmtree', side_effect=OSError('busy')):
            with self.assertRaises(rehearse.RehearsalError) as raised:
                self.rehearsal.apply()
        self.assertIn('incomplete', str(raised.exception))
        self.assertIn('temporary directory', str(raised.exception))
        self.assertIn('is still there', str(raised.exception))

    def test_every_docker_filter_by_name_is_anchored_and_the_resources_of_a_project_with_a_longer_name_are_not_touched(self):
        self.rehearsal, fake = make(foreign=(FOREIGN,))
        result = self.rehearsal.apply()
        self.assertEqual(result['cleanup'], 'complete')
        self.assertIn(FOREIGN, fake.state['ps'], 'a container of kairos-ops-b2 is not ours')
        named = [token for c, e in fake.commands for token in c if token.startswith('name=')]
        self.assertTrue(named, 'positive control: the final check filters by name')
        for token in named:
            self.assertRegex(token, r'^name=\^[A-Za-z0-9_.-]+\$$', token)
        self.assertFalse([c for c, e in fake.commands if c[:3] == ['docker', 'rm', '--force'] and FOREIGN in c])

    def test_an_existing_project_is_refused_before_anything_is_deployed(self):
        self.rehearsal, fake = make(existing=True)
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('already has containers', str(raised.exception))
        self.assertFalse([c for c, e in fake.commands if any('deploy-memory.py' in t for t in c)])

    def test_only_kairos_ops_projects_and_the_embedding_stub_are_accepted(self):
        for name in ('knowledge-graphs', 'knowledge-graphs-two', 'kairos-ops', 'kairos-ops-', 'kairos-ops-B', 'kairos-rehearsal', '', 'kairos-ops-' + 'x' * 30, 'kairos-ops-a b'):
            with self.assertRaises(rehearse.RehearsalError, msg=name):
                rehearse.Rehearsal(SimpleNamespace(project_name=name, embed_stub=True, api_port=1, web_port=2))
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.Rehearsal(SimpleNamespace(project_name='kairos-ops-b', embed_stub=False, api_port=1, web_port=2))
        rehearse.Rehearsal(SimpleNamespace(project_name='kairos-ops-b', embed_stub=True, api_port=1, web_port=2))


class RunbookTests(unittest.TestCase):
    """Every step of the runbook in docs/operations.md is a command the rehearsal runs."""

    def test_the_runbook_names_the_commands_the_rehearsal_runs(self):
        text = (ROOT / 'docs' / 'operations.md').read_text(encoding='utf-8')
        section = text.split('## Restaurar desde la copia externa', 1)[1].split('\n## ', 1)[0]
        for fragment in ('verify-backup', 'age --decrypt', '--manifest', 'restore-check', '--from-manifest', 'memory_restore_', 'restored_and_content_verified', 'rehearse-restore.py'):
            self.assertIn(fragment, section)
        script = (ROOT / 'scripts' / 'rehearse-restore.py').read_text(encoding='utf-8')
        for fragment in ("'verify-backup'", "'--decrypt'", "'--manifest'", "'restore-check'", "'--from-manifest'", "'memory_restore_'"):
            self.assertIn(fragment.strip("'"), script)
