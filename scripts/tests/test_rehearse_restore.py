"""scripts/rehearse-restore.py (C-01, CA-07): the restore rehearsal follows the runbook with doubles for docker; the private key stays out of the project's containers and everything is removed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('kairos_rehearse_restore', ROOT / 'scripts' / 'rehearse-restore.py')
rehearse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearse)

COPY = 'kairos-cycle-20261116T120000123456Z.dump.age'
PAYLOAD = b'age-encryption.org/v1\n' + bytes(range(200))
PLAIN = b'PGDMP' + bytes(range(100))
PUBLIC = 'age1' + 'q' * 58


def host_of(command, target):
    """The host side of the `-v <host>:<target>[:mode]` that mounts `target`."""
    for position, token in enumerate(command):
        if token == '-v' and re.search(r':' + re.escape(target) + r'(?::\w+)?$', command[position + 1]):
            return Path(re.sub(r':' + re.escape(target) + r'(?::\w+)?$', '', command[position + 1]))
    raise KeyError(target)


class FakeDocker:
    """Answers the commands of the rehearsal the way the real ones would, and records them."""

    def __init__(self, rehearsal, **faults):
        self.rehearsal, self.faults, self.commands, self.key_at_cleanup = rehearsal, faults, [], None
        self.listing = faults.get('listing', '')

    def __call__(self, command, timeout=None, environment=None):
        self.commands.append((list(command), dict(environment or {})))
        work = self.rehearsal.work
        text = ' '.join(command)
        if command[:2] == ['docker', 'ps'] and 'label=' in text and self.faults.get('existing') and 'name=' not in text:
            return 0, 'kairos-ops-b-memory-api-1\n', ''
        if command[:2] == ['docker', 'ps'] and 'name=' in text:
            return 0, self.listing, ''
        if command[:2] == ['docker', 'compose'] and 'down' in command and self.key_at_cleanup is None:
            self.key_at_cleanup = (work / 'keys' / 'identity.txt').exists()
        if 'deploy-memory.py' in text:
            (work / 'secrets').mkdir(exist_ok=True)
            (work / 'secrets' / 'dsn').write_text('postgresql://memory:pw%2Bx@memory-postgres:5432/agent_memory\n', encoding='utf-8')
            return 0, '', ''
        if 'age-keygen' in command:
            (host_of(command, '/keys') / 'identity.txt').write_text(f'# created: 2026-11-16T12:00:00Z\n# public key: {PUBLIC}\nAGE-SECRET' + '-KEY-FAKE\n', encoding='utf-8')
            return 0, '', ''
        if 'backup-cycle' in command:
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

    def test_a_failing_step_still_removes_everything_and_reports_the_failure(self):
        for fault, text in (({'cycle_fails': True}, 'verified, encrypted copy'), ({'wrong_sha': True}, 'sha256 of its manifest'), ({'mismatch': True}, 'restore to the content'), ({'content_wrong': True}, 'content_sha256')):
            self.rehearsal, fake = make(**fault)
            with self.assertRaises(rehearse.RehearsalError) as raised:
                self.rehearsal.apply()
            self.assertIn(text, str(raised.exception))
            self.assertTrue([c for c, e in fake.commands if c[:2] == ['docker', 'compose'] and 'down' in c], 'the project is taken down after a failure')
            self.assertFalse(self.rehearsal.work.exists())
            self.assertIs(fake.key_at_cleanup, False)

    def test_a_cleanup_that_leaves_something_is_a_failure_even_when_the_restore_worked(self):
        self.rehearsal, fake = make(listing='kairos-ops-b-memory-postgres-1\n')
        with self.assertRaises(rehearse.RehearsalError) as raised:
            self.rehearsal.apply()
        self.assertIn('incomplete', str(raised.exception))
        self.assertIn('kairos-ops-b-memory-postgres-1', str(raised.exception))

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
