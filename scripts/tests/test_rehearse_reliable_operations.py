"""scripts/rehearse-reliable-operations.py (CA-07, CA-37): the closing rehearsal of milestone A, with doubles for docker and for the portal.

The restore steps are the ones of scripts/rehearse-restore.py (its own tests cover them); what is pinned here is what this script adds: the seeded volume of embeddings, the
fingerprint measurement against the backup timeout, the queue that has to survive a stop and start of `memory-postgres`, and that a restart of the worker, a job that fails or a
queue that never empties fail the rehearsal while the cleanup still runs. Nothing here needs Docker or the network.
"""
import importlib.util
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('kairos_rehearse_ops', ROOT / 'scripts' / 'rehearse-reliable-operations.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)

FINGERPRINT = {'rows': 30000, 'table_bytes': 600_000_000, 'embeddings_seconds': 60.0, 'all_tables_seconds': 61.0, 'tables': 30}


def arguments(**changes):
    values = dict(project_name='kairos-ops-c', embed_stub=True, stage='a', seed_rows=30000, queue_jobs=3, api_port=28792, web_port=25175)
    values.update(changes)
    return SimpleNamespace(**values)


class FakePortal:
    def __init__(self, origin):
        self.origin, self.requests = origin, []

    def login(self, password):
        self.requests.append(('login', password))

    def logout(self):
        self.requests.append(('logout',))

    def request(self, path, value=None, method=None, bearer=None, host=None):
        self.requests.append((method or 'POST', path, bearer))
        return {'id': 'key-1', 'token': 'secret-token'} if path == '/v1/keys' and method is None else {}


class FakeDocker:
    """The commands of the new steps, answered the way the real ones would: the jobs, the worker container and the database."""

    def __init__(self, **faults):
        self.faults, self.commands, self.calls = faults, [], {'inspect': 0, 'states': 0}
        self.database_up = True

    def __call__(self, command, timeout=None, environment=None):
        self.commands.append(list(command))
        text = ' '.join(command)
        if command[:2] == ['docker', 'compose'] and 'ps' in command and '-q' in command:
            return 0, command[-1] + '-container' + chr(10), ''
        if command[:2] == ['docker', 'inspect']:
            self.calls['inspect'] += 1
            restarts = self.faults.get('restarts_after', 0) if self.calls['inspect'] > 3 else 0
            started = '2026-11-16T10:00:00Z' if self.calls['inspect'] <= 3 or not self.faults.get('restart_time') else '2026-11-16T10:05:00Z'
            return 0, f'{restarts}|{started}|true\n', ''
        if command[:2] == ['docker', 'stop']:
            self.database_up = self.database_up and command[-1] != 'memory-postgres-container'
            return 0, '', ''
        if command[:2] == ['docker', 'start']:
            self.database_up = self.database_up or command[-1] == 'memory-postgres-container'
            return 0, '', ''
        if 'pg_isready' in command:
            return (0 if self.database_up else 2), '', ''
        if 'INSERT INTO memory.embeddings' in text:
            return 0, '', ''
        if "count(*) FROM memory.embeddings" in text:
            return 0, f"{self.faults.get('seeded', 30000)}\n", ''
        if 'GROUP BY state' in text:
            self.calls['states'] += 1
            if self.faults.get('empty_before_stop') and self.calls['states'] >= 2:
                return 0, 'succeeded|4' + chr(10), ''
            if not self.faults.get('nothing_queued') and self.calls['states'] <= 2:
                return 0, 'pending|3\nsucceeded|1\n', ''
            if self.faults.get('never_drains'):
                return 0, 'pending|2\n', ''
            return 0, 'succeeded|4\n' + (f"failed|{self.faults['failed']}\n" if self.faults.get('failed') else ''), ''
        if '--entrypoint' in command and 'python' in command:
            return 0, 'noise line\n' + json.dumps(FINGERPRINT) + '\n', ''
        return 0, '', ''


class OperationsTests(unittest.TestCase):
    def rehearsal(self, **faults):
        docker = FakeDocker(**faults)
        rehearsal = ops.OperationsRehearsal(arguments(), root=ROOT, run=docker, portal=FakePortal)
        rehearsal.sleep = lambda seconds: None
        ticks = iter(range(0, 10_000, 1))
        rehearsal.clock = lambda: next(ticks)
        rehearsal.work = Path(ROOT / '.private' / 'unit-test-never-written')
        rehearsal.step_names = []
        return rehearsal, docker

    def run_steps(self, rehearsal):
        password = patch.object(Path, 'read_text', return_value='bootstrap-password\n')
        with password:
            rehearsal.seed_embeddings()
            rehearsal.measure_fingerprints()
            rehearsal.queue_jobs()
            rehearsal.database_restart()

    def test_the_rehearsal_only_runs_in_an_isolated_project_with_the_stub(self):
        for bad in ('knowledge-graphs', 'kairos-ops', 'other-ops-c', 'kairos-ops-C'):
            with self.assertRaises(ops.RehearsalError):
                ops.OperationsRehearsal(arguments(project_name=bad))
        with self.assertRaises(ops.RehearsalError):
            ops.OperationsRehearsal(arguments(embed_stub=False))

    def test_a_healthy_restart_reports_the_same_counter_an_empty_queue_and_no_failed_job(self):
        rehearsal, docker = self.rehearsal()
        self.run_steps(rehearsal)
        result = rehearsal.report['worker_survived_db_restart']
        self.assertEqual((result['restarts_before'], result['restarts_after'], result['same_start'], result['failed']), (0, 0, True, 0))
        self.assertGreater(result['pending_at_stop'], 0, 'the database stopped with jobs in the queue')
        order = [c for c in docker.commands if c[:2] in (['docker', 'stop'], ['docker', 'start'])]
        names = [c[-1].replace('-container', '') + ':' + c[1] for c in order]
        self.assertEqual(names, ['memory-worker:stop', 'memory-worker:start', 'memory-postgres:stop', 'memory-postgres:start'])
        self.assertEqual(rehearsal.report['queue']['events'], 3)
        self.assertFalse([c for c in docker.commands if c[:2] == ['docker', 'compose'] and ('start' in c or 'stop' in c)], '`compose start` needs the one-shot memory-migrate that was removed: plain docker is used')

    def test_nothing_the_rehearsal_runs_names_another_project_or_the_host_ollama(self):
        rehearsal, docker = self.rehearsal()
        self.run_steps(rehearsal)
        for command in docker.commands:
            text = ' '.join(command)
            self.assertNotIn('knowledge-graphs-', text)
            self.assertNotIn('11434', text)
            if command[:2] == ['docker', 'compose']:
                self.assertEqual(command[command.index('-p') + 1], 'kairos-ops-c')

    def test_a_worker_that_restarts_fails_the_rehearsal(self):
        for faults in ({'restarts_after': 1}, {'restart_time': True}):
            rehearsal, docker = self.rehearsal(**faults)
            with self.assertRaises(ops.RehearsalError) as raised:
                self.run_steps(rehearsal)
            self.assertIn('memory-worker restarted', str(raised.exception))

    def test_a_job_that_ends_failed_after_the_restart_fails_the_rehearsal(self):
        rehearsal, docker = self.rehearsal(failed=2)
        with self.assertRaises(ops.RehearsalError) as raised:
            self.run_steps(rehearsal)
        self.assertIn('2 job(s) ended failed', str(raised.exception))

    def test_a_queue_that_never_empties_or_was_never_filled_fails_the_rehearsal(self):
        rehearsal, docker = self.rehearsal(never_drains=True)
        with self.assertRaises(ops.RehearsalError) as raised:
            self.run_steps(rehearsal)
        self.assertIn('queue emptying', str(raised.exception))
        rehearsal, docker = self.rehearsal(nothing_queued=True)
        with self.assertRaises(ops.RehearsalError) as raised:
            self.run_steps(rehearsal)
        self.assertIn('No job was queued', str(raised.exception))

    def test_a_queue_that_emptied_before_the_database_stopped_proves_nothing(self):
        rehearsal, docker = self.rehearsal(empty_before_stop=True)
        with self.assertRaises(ops.RehearsalError) as raised:
            self.run_steps(rehearsal)
        self.assertIn('queue was empty before the database stopped', str(raised.exception))
        self.assertFalse([c for c in docker.commands if c[:2] == ['docker', 'stop'] and c[-1] == 'memory-postgres-container'], 'the database was not stopped for nothing')

    def test_the_key_of_the_events_is_revoked_and_the_session_closed_even_when_an_event_fails(self):
        rehearsal, docker = self.rehearsal()
        portal = rehearsal.portal()
        requests = portal.requests

        def failing(path, value=None, method=None, bearer=None, host=None):
            requests.append((method or 'POST', path, bearer))
            if path == '/v1/events':
                raise ops.RehearsalError('the event was refused')
            return {'id': 'key-1', 'token': 'secret-token'} if path == '/v1/keys' and method is None else {}
        portal.request = failing
        with patch.object(rehearsal, 'portal', return_value=portal), patch.object(Path, 'read_text', return_value='x\n'):
            with self.assertRaises(ops.RehearsalError):
                rehearsal.queue_jobs()
        self.assertIn(('DELETE', '/v1/keys/key-1', None), requests)
        self.assertEqual(requests[-1], ('logout',))

    def test_the_seed_is_checked_and_the_fingerprints_are_compared_with_the_backup_timeout(self):
        rehearsal, docker = self.rehearsal(seeded=10)
        with self.assertRaises(ops.RehearsalError):
            rehearsal.seed_embeddings()
        rehearsal, docker = self.rehearsal()
        rehearsal.seed_embeddings()
        rehearsal.measure_fingerprints()
        measured = rehearsal.report['fingerprints']
        self.assertEqual(measured['megabytes_per_second'], 10.0)
        self.assertEqual(measured['seconds_for_5_gb'], round(5 * 1024 ** 3 / 10_000_000))
        self.assertEqual((measured['backup_timeout_seconds'], measured['within_timeout']), (3600, True))
        self.assertEqual(rehearsal.report['seed'], {'embeddings': 30000, 'dims': 768})

    def test_the_sequence_ends_with_the_checks_of_the_closing_and_times_the_copy_and_the_restore(self):
        rehearsal, docker = self.rehearsal()
        names = [getattr(action, '__name__', '') for action in rehearsal.sequence()]
        self.assertEqual(names[:3], ['deploy', 'seed_embeddings', 'make_keys'])
        self.assertEqual(names[-3:], ['measure_fingerprints', 'queue_jobs', 'database_restart'])
        self.assertEqual(names[3], 'cycle')
        self.assertEqual(names[7], 'restore')

    def test_the_command_line_refuses_nonsense_before_anything_runs(self):
        for argv in (['--project-name', 'kairos-ops-c', '--embed-stub', '--seed-rows', '0'], ['--project-name', 'kairos-ops-c', '--embed-stub', '--stage', 'b']):
            with self.assertRaises(SystemExit):
                with patch.object(ops.OperationsRehearsal, 'apply', side_effect=AssertionError('it must not run')):
                    ops.main(argv)
        with patch.object(ops.OperationsRehearsal, 'apply', return_value={'status': 'restored_and_content_verified'}):
            self.assertEqual(ops.main(['--project-name', 'kairos-ops-c', '--embed-stub', '--stage', 'a']), 0)
        self.assertTrue(re.fullmatch(r'kairos-ops-[a-z0-9][a-z0-9-]{0,24}', 'kairos-ops-c'))


if __name__ == '__main__':
    unittest.main()
