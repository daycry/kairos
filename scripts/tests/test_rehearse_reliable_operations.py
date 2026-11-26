"""scripts/rehearse-reliable-operations.py (CA-07, CA-37): the closing rehearsal of milestone A, with doubles for docker and for the portal.

The restore steps are the ones of scripts/rehearse-restore.py (its own tests cover them); what is pinned here is what this script adds: the seeded volume of embeddings, the
fingerprint measurement against the backup timeout, the queue that has to survive a stop and start of `memory-postgres`, and that a restart of the worker, a job that fails or a
queue that never empties fail the rehearsal while the cleanup still runs. Nothing here needs Docker or the network.

Stage `rollback` (T-64, CA-24 and the rehearsal case of CA-21) is pinned in `RollbackStageTests` against a double of Docker that keeps the images, the image each container runs and the
health of `memory-worker` on a simulated clock: the tags must exist, the faulty release must really change what runs, the rollback must put the tagged images back without migrating and
with the same content, the worker must turn `unhealthy` within the deadline of its last beat + `interval x retries` and be healthy again once resumed, and the cleanup removes every tag.
"""
import importlib.util
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import Mock, patch
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
            if self.faults.get('drained_just_before_stop') and self.calls['states'] >= 3:
                return 0, 'succeeded|4' + chr(10), ''
            if not self.faults.get('nothing_queued') and self.calls['states'] <= 3:  # the queue_jobs look, the first look before the stop and the last one
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
        password = patch.object(Path, 'read_bytes', return_value=b'bootstrap-password\n')  # bootstrap_password() reads bytes, like password_from_file of the server (fix3)
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

    def test_a_queue_that_drained_between_the_first_look_and_the_stop_proves_nothing(self):
        """The count that counts is the last one before `docker stop`: an earlier one (taken before the worker had drained everything) is not evidence of jobs left while the database was down."""
        rehearsal, docker = self.rehearsal(drained_just_before_stop=True)
        with self.assertRaises(ops.RehearsalError) as raised:
            self.run_steps(rehearsal)
        self.assertIn('queue was empty before the database stopped', str(raised.exception))
        self.assertFalse([c for c in docker.commands if c[:2] == ['docker', 'stop'] and c[-1] == 'memory-postgres-container'])

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
        with patch.object(rehearsal, 'portal', return_value=portal), patch.object(Path, 'read_bytes', return_value=b'x\n'):
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


NAMES = ('api', 'worker', 'mcp', 'web', 'operator')
PROJECT = 'kairos-ops-c'
TAG = '0.4.0-20261103T100000Z'


def stamp(epoch):
    """An instant as the daemon prints it: RFC 3339 with nanoseconds."""
    moment = datetime.fromtimestamp(epoch, timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + f'{moment.microsecond:06d}123Z'


def previous_tags(project=PROJECT):
    return {name: f'rehearsal-{project}-{name}:{TAG}' for name in NAMES}


def second_status():
    return {'status': 'complete', 'images': {'previous': previous_tags(), 'kept': {name: [previous_tags()[name]] for name in NAMES}, 'current': {}}}


def rollback_status(**changes):
    value = {'status': 'rolled_back', 'phases': ['engine', 'configuration', 'rollback', 'verify', 'roundtrip'], 'rollback': {'migrated': False}, 'content_sha256': 's1',
             'images': {'previous': previous_tags(), 'current': {name: f'sha256:old-{name}' for name in NAMES}}, 'roundtrip': {'found_ref': 'ref-1'}}
    value.update(changes)
    return value


class FakeStack:
    """Docker for the rollback stage: the images (`reference -> id`), the image each container runs, the health of `memory-worker` on a simulated clock (`now`, advanced by the
    rehearsal's own sleeps) and the signals sent to it."""
    EPOCH = 1_000_000.0

    def __init__(self, **faults):
        self.faults, self.commands, self.now = faults, [], 0.0
        self.images = {f'rehearsal-{PROJECT}-{name}:{TAG}': f'sha256:old-{name}' for name in NAMES}
        self.images.update({f'rehearsal-{PROJECT}-{name}:latest': f'sha256:new-{name}' for name in NAMES})
        self.running = {'memory-api-container': 'sha256:new-api', 'memory-worker-container': 'sha256:new-worker'}
        self.stopped_at = self.resumed_at = None
        self.signals = []

    def transition_at(self):
        """The simulated instant (on `now`'s clock) of the transition to `unhealthy`: the end of the third failing probe."""
        return self.stopped_at + self.faults.get('deadline_offset', 100) + self.faults.get('unhealthy_after_deadline', 75)

    def health_log(self):
        """`State.Health.Log` as the daemon writes it: the last good probe and the failing ones, each `interval` after the end of the one before, ending at the transition."""
        duration, interval = self.faults.get('probe_seconds', 1.0), 30.0
        if self.faults.get('log'):
            return self.faults['log']
        end, entries = self.EPOCH + self.transition_at(), []
        for code in (1, 1, 1, 0):
            entries.insert(0, {'Start': stamp(end - duration), 'End': stamp(end), 'ExitCode': code, 'Output': ''})
            end -= duration + interval
        return entries

    def advance(self, seconds):
        self.now += seconds

    def health(self):
        if self.stopped_at is not None and self.resumed_at is None:
            if self.faults.get('never_unhealthy'):
                return 'healthy'
            return 'unhealthy' if self.now >= self.stopped_at + self.faults.get('deadline_offset', 100) + self.faults.get('unhealthy_after_deadline', 75) else 'healthy'
        return 'unhealthy' if self.faults.get('stays_unhealthy') and self.resumed_at is not None else 'healthy'

    def __call__(self, command, timeout=None, environment=None):
        self.commands.append(list(command))
        text = ' '.join(command)
        if command[:2] == ['docker', 'compose'] and 'ps' in command and '-q' in command:
            return 0, command[-1] + '-container' + chr(10), ''
        if command[:2] == ['docker', 'compose'] and 'up' in command:
            for name in ('api', 'worker'):
                if f'memory-{name}' in command:
                    self.running[f'memory-{name}-container'] = self.images[f'rehearsal-{PROJECT}-{name}:latest']
            return 0, '', ''
        if command[:2] == ['docker', 'compose'] and 'content-manifest' in command:
            return 0, json.dumps({'sha256': 's1'}), ''
        if command[:3] == ['docker', 'image', 'inspect']:
            found = self.images.get(command[-1]) or (command[-1] if command[-1] in self.images.values() else None)
            return (0, found + chr(10), '') if found else (1, '', 'No such image')
        if command[:3] == ['docker', 'image', 'ls']:
            return 0, ''.join(key + chr(10) for key in self.images if key.startswith(command[3] + ':')), ''
        if command[:3] == ['docker', 'image', 'rm']:
            if command[-1] in self.images:
                del self.images[command[-1]]
            else:
                for key in [k for k, v in self.images.items() if v == command[-1]]:
                    del self.images[key]
            return 0, '', ''
        if command[:2] == ['docker', 'create']:
            self.created = command[-1]
            return 0, 'created' + chr(10), ''
        if command[:2] == ['docker', 'commit']:
            name = command[-1].rsplit(':', 1)[0].rsplit('-', 1)[1]
            self.images[command[-1]] = f'sha256:faulty-{name}'
            return 0, '', ''
        if command[0] == sys.executable and '--rollback' in command:
            if not self.faults.get('not_restored'):
                self.running.update({'memory-api-container': 'sha256:old-api', 'memory-worker-container': 'sha256:old-worker'})
                for name in NAMES:
                    self.images[f'rehearsal-{PROJECT}-{name}:latest'] = f'sha256:old-{name}'
            return 0, '', ''
        if command[:2] == ['docker', 'inspect']:
            if '{{.Image}}' in command:
                return 0, self.running[command[-1]] + chr(10), ''
            if '{{.State.Health.Status}}' in command:
                return 0, self.health() + chr(10), ''
            if '{{json .State.Health.Log}}' in command:
                return 0, json.dumps(self.health_log()), ''
            if '{{json .Config.Healthcheck}}' in command:
                return 0, json.dumps({'Test': ['CMD'], 'Interval': 30_000_000_000, 'Timeout': 5_000_000_000, 'Retries': 3}), ''
        if command[:2] == ['docker', 'exec']:
            if 'time.time()' in text:
                return 0, repr(self.EPOCH + self.now) + chr(10), ''
            if 'kairos-worker-heartbeat' in text:
                return 0, repr(self.EPOCH + self.stopped_at + self.faults.get('deadline_offset', 100)) + chr(10), ''
        if command[:2] == ['docker', 'kill']:
            self.signals.append((command[command.index('--signal') + 1], command[-1]))
            if 'SIGSTOP' in command:
                self.stopped_at = self.now
            else:
                self.resumed_at = self.now
            return 0, '', ''
        return 0, '', ''


class RollbackStageTests(unittest.TestCase):
    def rehearsal(self, **faults):
        stack = FakeStack(**faults)
        rehearsal = ops.OperationsRehearsal(arguments(stage='rollback'), root=ROOT, run=stack)
        rehearsal.sleep = stack.advance
        rehearsal.clock = lambda: stack.now
        rehearsal.work = Path(ROOT / '.private' / 'unit-test-never-written')
        rehearsal.read_status = Mock(side_effect=[second_status(), rollback_status(**faults.get('status', {}))])
        return rehearsal, stack

    def through_rollback(self, rehearsal):
        rehearsal.tagged_images()
        rehearsal.faulty_release()
        rehearsal.rollback_deployment()

    def test_the_stage_is_chosen_with_the_command_line_and_runs_the_two_deployments_the_rollback_and_the_probe_in_that_order(self):
        rehearsal, stack = self.rehearsal()
        self.assertIn('rollback', ops.STAGES)
        names = [getattr(action, '__name__', '') for action in rehearsal.sequence()]
        self.assertEqual(names, ['deploy', 'second_deploy', 'tagged_images', 'faulty_release', 'rollback_deployment', 'worker_unhealthy'])
        stage_all = ops.OperationsRehearsal(arguments(stage='all'), root=ROOT, run=stack)
        names = [getattr(action, '__name__', '') for action in stage_all.sequence()]
        self.assertEqual(names[:1], ['deploy'])
        self.assertEqual(names[-9:-4], ['second_deploy', 'tagged_images', 'faulty_release', 'rollback_deployment', 'worker_unhealthy'])  # the probe steps of T-77 come after
        self.assertEqual([getattr(a, '__name__', '') for a in ops.OperationsRehearsal(arguments(stage='a'), root=ROOT, run=stack).sequence()].count('second_deploy'), 0)
        with patch.object(ops.OperationsRehearsal, 'apply', return_value={'status': 'rollback_ok'}):
            self.assertEqual(ops.main(['--project-name', PROJECT, '--embed-stub', '--stage', 'rollback']), 0)

    def test_the_second_deployment_is_not_fresh_skips_the_slow_backup_restore_and_keeps_the_stub_and_the_round_trip(self):
        rehearsal, stack = self.rehearsal()
        rehearsal.work = Path('/tmp/never')
        rehearsal.second_deploy()
        command = stack.commands[-1]
        self.assertNotIn('--fresh', command)
        for flag in ('--apply', '--no-verify-backup', '--embed-stub', '--roundtrip'):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index('--project-name') + 1], PROJECT)

    def test_the_recorded_tags_must_exist_and_have_the_shape_of_the_deployment(self):
        rehearsal, stack = self.rehearsal()
        rehearsal.tagged_images()
        self.assertEqual(rehearsal.previous_ids, {name: f'sha256:old-{name}' for name in NAMES})
        self.assertEqual(rehearsal.report['tags']['previous'], previous_tags())
        for broken in ({}, {name: tag for name, tag in previous_tags().items() if name != 'web'}, {**previous_tags(), 'api': 'kairos-api:0.4.0-20261103T100000Z'}, {**previous_tags(), 'api': f'rehearsal-{PROJECT}-api:latest'}):
            rehearsal, stack = self.rehearsal()
            rehearsal.read_status = Mock(return_value={'images': {'previous': broken}})
            with self.assertRaises(ops.RehearsalError):
                rehearsal.tagged_images()
        rehearsal, stack = self.rehearsal()
        del stack.images[previous_tags()['worker']]
        with self.assertRaises(ops.RehearsalError) as raised:
            rehearsal.tagged_images()
        self.assertIn('does not exist', str(raised.exception))

    def test_the_faulty_release_really_changes_what_the_containers_run(self):
        rehearsal, stack = self.rehearsal()
        rehearsal.tagged_images()
        rehearsal.faulty_release()
        self.assertEqual(stack.running, {'memory-api-container': 'sha256:faulty-api', 'memory-worker-container': 'sha256:faulty-worker'})
        self.assertEqual(rehearsal.report['faulty_release'], {'api': 'sha256:faulty-api', 'worker': 'sha256:faulty-worker'})
        commit = next(c for c in stack.commands if c[:2] == ['docker', 'commit'])
        self.assertIn('LABEL ' + ops.FAULTY_LABEL, commit)
        up = next(c for c in stack.commands if 'up' in c)
        self.assertIn('--no-build', up)
        self.assertEqual(up[-2:], ['memory-api', 'memory-worker'])

    def test_the_rollback_must_leave_the_containers_on_the_tagged_images_without_migrating_and_with_the_same_content(self):
        rehearsal, stack = self.rehearsal()
        self.through_rollback(rehearsal)
        report = rehearsal.report['rollback']
        self.assertEqual((report['status'], report['migrated'], report['content_equal'], report['search_found_ref']), ('rolled_back', False, True, 'ref-1'))
        self.assertEqual(report['restored_to'], {'api': 'sha256:old-api', 'worker': 'sha256:old-worker'})
        self.assertEqual(report['replaced_faulty'], {'api': 'sha256:faulty-api', 'worker': 'sha256:faulty-worker'})
        deploy = [c for c in stack.commands if c[0] == sys.executable and '--rollback' in c]
        self.assertEqual(len(deploy), 1)
        self.assertNotIn('--fresh', deploy[0])

    def test_a_rollback_that_does_not_do_what_it_says_fails_the_rehearsal(self):
        cases = {'not_restored': ({'not_restored': True}, 'image of its recorded tag'),
                 'status': ({'status': {'status': 'failed'}}, 'did not report a rollback'),
                 'migrated': ({'status': {'rollback': {'migrated': True}}}, 'did not report a rollback'),
                 'phases': ({'status': {'phases': ['engine', 'configuration', 'rollback', 'verify', 'migrate']}}, 'phases it must not'),
                 'content': ({'status': {'content_sha256': 'different'}}, 'content-manifest'),
                 'current': ({'status': {'images': {'current': {name: 'sha256:other' for name in NAMES}, 'previous': previous_tags()}}}, 'recorded current image'),
                 'search': ({'status': {'roundtrip': {}}}, 'found nothing')}
        for label, (faults, message) in cases.items():
            with self.subTest(label):
                rehearsal, stack = self.rehearsal(**faults)
                with self.assertRaises(ops.RehearsalError) as raised:
                    self.through_rollback(rehearsal)
                self.assertIn(message, str(raised.exception))

    def test_the_worker_turns_unhealthy_within_the_deadline_of_its_last_beat_plus_interval_times_retries(self):
        rehearsal, stack = self.rehearsal()
        rehearsal.worker_unhealthy()
        measured = rehearsal.report['worker_unhealthy']
        self.assertTrue(measured['within_bound'] and measured['recovered'])
        self.assertEqual((measured['interval_seconds'], measured['retries']), (30.0, 3), 'the bound uses the healthcheck the container really has')
        self.assertEqual(measured['deadline_after_stop_seconds'], 100.0)
        self.assertEqual(measured['bound_after_stop_seconds'], 194.0, 'deadline of the last beat + 30 x 3 + the durations of the probes (1 s: the last good one and the three failing ones)')
        self.assertGreaterEqual(measured['unhealthy_after_stop_seconds'], 175.0)
        self.assertLessEqual(measured['unhealthy_after_deadline_seconds'], 90)
        self.assertEqual(stack.signals, [('SIGSTOP', 'memory-worker-container'), ('SIGCONT', 'memory-worker-container')])
        self.assertEqual([c for c in stack.commands if c[:2] == ['docker', 'stop'] or c[:2] == ['docker', 'rm']], [], 'the loop is stopped, the container is not')

    def test_a_worker_that_turns_unhealthy_too_late_or_never_fails_the_rehearsal_and_is_resumed_anyway(self):
        for faults, message in (({'unhealthy_after_deadline': 140}, 'later than the deadline'), ({'never_unhealthy': True}, 'turning unhealthy')):
            with self.subTest(faults):
                rehearsal, stack = self.rehearsal(**faults)
                with self.assertRaises(ops.RehearsalError) as raised:
                    rehearsal.worker_unhealthy()
                self.assertIn(message, str(raised.exception))
                self.assertEqual(stack.signals[-1], ('SIGCONT', 'memory-worker-container'))

    def test_fix1_the_bound_is_strict_the_margin_of_the_wait_never_approves_a_late_unhealthy(self):
        """Fix1 (review of phase 10, gap 5): 195 s after the stop is 1 s past the bound of 194 s; the 10 s that the wait allows to still measure it are not part of the verdict."""
        rehearsal, stack = self.rehearsal(unhealthy_after_deadline=95)
        with self.assertRaises(ops.RehearsalError) as raised:
            rehearsal.worker_unhealthy()
        self.assertIn('later than the deadline', str(raised.exception))
        late = rehearsal.report['worker_unhealthy']
        self.assertIs(late['within_bound'], False)
        self.assertGreater(late['late_by_seconds'], 0)
        self.assertEqual(stack.signals[-1], ('SIGCONT', 'memory-worker-container'))

    def test_fix1_the_measurement_reports_its_own_pause_and_how_far_inside_the_bound_it_was(self):
        rehearsal, stack = self.rehearsal()
        rehearsal.worker_unhealthy()
        measured = rehearsal.report['worker_unhealthy']
        self.assertLessEqual(measured['late_by_seconds'], 0)
        self.assertEqual(measured['measurement_pause_seconds'], 3, 'the latency of the measurement is reported apart: the poll that detects it waits this long')
        self.assertLessEqual(measured['unhealthy_after_stop_seconds'], measured['bound_after_stop_seconds'])

    def test_fix2_the_verdict_takes_the_instant_of_the_transition_from_the_health_log_not_the_clock_of_the_poll(self):
        """Fix2 (gap 7): the poll runs every few seconds and its answer comes later still; the instant that counts is the end of the probe that made the container unhealthy."""
        rehearsal, stack = self.rehearsal(unhealthy_after_deadline=93)
        rehearsal.worker_unhealthy()
        measured = rehearsal.report['worker_unhealthy']
        self.assertEqual(measured['unhealthy_after_stop_seconds'], 193.0, 'the transition of the log, not a multiple of the poll pause')
        self.assertEqual(measured['unhealthy_after_deadline_seconds'], 93.0)
        self.assertTrue(measured['within_bound'])
        self.assertEqual(measured['failed_probe_seconds'], [1.0, 1.0, 1.0])
        self.assertEqual(measured['last_ok_probe_seconds'], 1.0)
        self.assertEqual(measured['transition_source'], 'State.Health.Log')

    def test_fix2_probes_that_take_time_widen_the_bound_by_exactly_their_duration(self):
        """Docker waits `interval` AFTER a probe ends: each probe adds its own duration to the time. 4 probes of 10 s make the bound 90 + 40 = 130 s after the deadline."""
        rehearsal, stack = self.rehearsal(probe_seconds=10.0, unhealthy_after_deadline=120)
        rehearsal.worker_unhealthy()
        measured = rehearsal.report['worker_unhealthy']
        self.assertTrue(measured['within_bound'], 'the old bound (deadline + 90 s) would have called this late')
        self.assertEqual(measured['bound_after_stop_seconds'], 100.0 + 90.0 + 40.0)
        rehearsal, stack = self.rehearsal(probe_seconds=10.0, unhealthy_after_deadline=131)
        with self.assertRaises(ops.RehearsalError):
            rehearsal.worker_unhealthy()
        self.assertEqual(rehearsal.report['worker_unhealthy']['late_by_seconds'], 1.0)

    def test_fix2_the_bound_is_deduced_exactly_inside_just_outside_and_with_a_log_that_cannot_prove_it(self):
        interval, retries, deadline = 30.0, 3, 1000.0
        base = 1_000_000.0

        def log(*probes):  # (start, duration, exit code)
            return [{'Start': stamp(base + start), 'End': stamp(base + start + duration), 'ExitCode': code, 'Output': ''} for start, duration, code in probes]

        def verdict(entries):
            return ops.unhealthy_verdict(entries, base + deadline, interval, retries)
        # the last good probe took 2 s, the failing ones 1, 4 and 3 s: bound = deadline + 90 + 2 + (1 + 4 + 3)
        bound = deadline + 90 + 2 + 8
        inside = log((960, 2, 0), (962 + 30, 1, 1), (993 + 30, 4, 1), (1027 + 30, 3, 1))
        result = verdict(inside)
        self.assertEqual((result['unhealthy_at'], result['bound'], result['within_bound']), (base + 1060, base + bound, True))
        self.assertEqual(result['failed_probe_seconds'], [1.0, 4.0, 3.0])
        edge = log((960, 2, 0), (992, 1, 1), (1023, 4, 1), (1057 + 40, 3, 1))
        self.assertEqual(verdict(edge)['unhealthy_at'], base + 1100)
        self.assertTrue(verdict(edge)['within_bound'], 'exactly on the bound is inside')
        outside = log((960, 2, 0), (992, 1, 1), (1023, 4, 1), (1057 + 40.5, 3, 1))
        self.assertFalse(verdict(outside)['within_bound'])
        self.assertAlmostEqual(verdict(outside)['late_by'], 0.5, places=3)
        with self.assertRaises(ops.RehearsalError):  # fewer failing probes than retries: the log does not show the transition
            verdict(log((960, 2, 0), (992, 1, 1), (1023, 4, 1)))
        with self.assertRaises(ops.RehearsalError):
            verdict([])
        self.assertEqual(verdict(log((992, 1, 1), (1023, 4, 1), (1057, 3, 1), (1090, 3, 1)))['last_ok_probe_seconds'], None, 'no good probe in the log: reported, not invented')
        slow = log((960, 2, 0), (992, 1, 1), (1023, 4, 1), (1057, 3, 1), (1090, 3, 1))  # a fourth failing probe after the transition does not move it
        self.assertEqual(verdict(slow)['unhealthy_at'], base + 1060)

    def test_fix2_a_timeout_of_a_probe_counts_as_a_failure_and_a_probe_still_running_is_ignored(self):
        interval, retries, base = 30.0, 3, 1_000_000.0
        entries = [{'Start': stamp(base + 960), 'End': stamp(base + 962), 'ExitCode': 0},
                   {'Start': stamp(base + 992), 'End': stamp(base + 997), 'ExitCode': -1},
                   {'Start': stamp(base + 1027), 'End': stamp(base + 1032), 'ExitCode': 1},
                   {'Start': stamp(base + 1062), 'End': stamp(base + 1067), 'ExitCode': 1},
                   {'Start': stamp(base + 1097), 'End': '0001-01-01T00:00:00Z', 'ExitCode': 0}]
        result = ops.unhealthy_verdict(entries, base + 1000, interval, retries)
        self.assertEqual(result['unhealthy_at'], base + 1067)
        self.assertEqual(result['failed_probe_seconds'], [5.0, 5.0, 5.0])

    def test_fix2_a_time_the_daemon_wrote_that_cannot_be_read_fails_the_rehearsal_with_a_message(self):
        with self.assertRaises(ops.RehearsalError):
            ops.unhealthy_verdict([{'Start': 'yesterday', 'End': 'today', 'ExitCode': 1}] * 4, 0.0, 30.0, 3)

    def test_a_worker_that_does_not_recover_once_resumed_fails_the_rehearsal(self):
        rehearsal, stack = self.rehearsal(stays_unhealthy=True)
        with self.assertRaises(ops.RehearsalError) as raised:
            rehearsal.worker_unhealthy()
        self.assertIn('healthy again', str(raised.exception))

    def test_the_cleanup_removes_every_tag_and_every_faulty_image_by_exact_reference(self):
        rehearsal, stack = self.rehearsal()
        self.through_rollback(rehearsal)
        stack.images['kairos-api:0.4.0-20261103T100000Z'] = 'sha256:installed-api'  # an installed name that must never be touched
        stack.images[f'rehearsal-{PROJECT}-extra:latest'] = 'sha256:extra'
        self.assertEqual(rehearsal.remove_tagged_images(), [])
        self.assertEqual({key for key in stack.images if key.startswith('rehearsal-')}, {f'rehearsal-{PROJECT}-extra:latest'})
        self.assertIn('kairos-api:0.4.0-20261103T100000Z', stack.images)
        removed = [c[-1] for c in stack.commands if c[:3] == ['docker', 'image', 'rm']]
        self.assertTrue(removed and all(r.startswith(f'rehearsal-{PROJECT}-') or r.startswith('sha256:faulty') for r in removed), removed)

    def test_an_image_that_cannot_be_removed_is_reported_by_the_cleanup(self):
        rehearsal, stack = self.rehearsal()
        self.through_rollback(rehearsal)
        real = stack.__call__

        def stubborn(command, timeout=None, environment=None):
            if command[:3] == ['docker', 'image', 'rm'] and command[-1].endswith(TAG):
                stack.commands.append(list(command))
                return 1, '', 'conflict'
            return real(command, timeout, environment)
        rehearsal.run_command = stubborn
        problems = rehearsal.remove_tagged_images()
        self.assertTrue(problems and all(p.startswith('image left in docker: ') for p in problems), problems)

    def test_nothing_the_stage_runs_names_another_project_or_the_host_ollama(self):
        rehearsal, stack = self.rehearsal()
        self.through_rollback(rehearsal)
        rehearsal.worker_unhealthy()
        for command in stack.commands:
            text = ' '.join(command)
            self.assertNotIn('knowledge-graphs-', text)
            self.assertNotIn('knowledge-graphs_', text)
            self.assertNotIn('11434', text)
            if command[:2] == ['docker', 'compose']:
                self.assertEqual(command[command.index('-p') + 1], PROJECT)
            if command[:2] in (['docker', 'kill'], ['docker', 'commit'], ['docker', 'create']):
                self.assertTrue(any(PROJECT in part or part.startswith('sha256:') or part == 'memory-worker-container' for part in command), command)


class FakeProbeDocker(FakeDocker):
    """`memory-probe` runs and the metrics file, answered the way the real ones would, in the order of the scenario (`runs`: a list of (exit code, report))."""

    def __init__(self, runs, metrics=None, **faults):
        super().__init__(**faults)
        self.runs, self.metrics = list(runs), list(metrics or [])
        self.stopped_when_run = []

    def __call__(self, command, timeout=None, environment=None):
        if 'memory-probe' in command and 'run' in command:
            self.commands.append(list(command))
            self.stopped_when_run.append(any(c[:2] == ['docker', 'stop'] for c in self.commands) and not any(c[:2] == ['docker', 'start'] for c in self.commands))
            code, report = self.runs.pop(0)
            return code, json.dumps(report) + chr(10), ('probe_failed: stage=index code=timeout' + chr(10) if code else '')
        if 'cat' in command and ops.PROBE_METRICS_FILE in command:
            self.commands.append(list(command))
            return 0, self.metrics.pop(0), ''
        if 'probe-provision' in command:
            self.commands.append(list(command))
            return 0, json.dumps({'status': 'provisioned'}) + chr(10), ''
        return super().__call__(command, timeout, environment)


OK = {'status': 'probe_ok', 'kairos_probe_success': 1, 'stages': {'write': 0.2, 'index': 4.0, 'search': 0.5, 'retire': 0.3}, 'total_seconds': 5.0, 'queue': {'oldest_pending_seconds': 0.0, 'threshold_seconds': 900.0, 'stuck': False}}
STOPPED = {'status': 'probe_failed', 'stage': 'index', 'code': 'timeout', 'kairos_probe_success': 0, 'stages': {'write': 0.2, 'index': 29.7, 'retire': 0.4}, 'retired': True,
           'queue': {'oldest_pending_seconds': 31.0, 'threshold_seconds': 10.0, 'stuck': True}}
SUCCESS_1, SUCCESS_0 = 'kairos_probe_success 1.0' + chr(10), 'kairos_probe_success 0.0' + chr(10)


class ProbeStageTests(unittest.TestCase):
    """T-77 (criterion of closing 3): the probe healthy and with `memory-worker` stopped, pinned against a double of Docker (nothing here needs Docker)."""

    def rehearsal(self, runs, metrics, **faults):
        docker = FakeProbeDocker(runs, metrics, **faults)
        rehearsal = ops.OperationsRehearsal(arguments(stage='probe'), root=ROOT, run=docker, portal=FakePortal)
        rehearsal.sleep = lambda seconds: None
        ticks = iter(range(0, 100_000, 1))
        rehearsal.clock = lambda: next(ticks)
        rehearsal.work = Path(ROOT / '.private' / 'unit-test-never-written')
        return rehearsal, docker

    def healthy_stopped_recovered(self):
        return self.rehearsal([(0, OK), (1, STOPPED), (0, OK)], [SUCCESS_1, SUCCESS_0, SUCCESS_1])

    def test_the_stage_is_chosen_with_the_command_line_and_runs_the_deployment_then_the_probe_steps_in_order(self):
        rehearsal, _ = self.healthy_stopped_recovered()
        self.assertIn('probe', ops.STAGES)
        self.assertEqual([getattr(a, '__name__', '') for a in rehearsal.sequence()], ['deploy', 'probe_provision', 'probe_healthy', 'probe_worker_stopped', 'probe_recovered'])
        everything = ops.OperationsRehearsal(arguments(stage='all'), root=ROOT, run=FakeDocker())
        self.assertEqual([getattr(a, '__name__', '') for a in everything.sequence()][-4:], ['probe_provision', 'probe_healthy', 'probe_worker_stopped', 'probe_recovered'])
        with patch.object(ops.OperationsRehearsal, 'apply', return_value={'status': 'probe_rehearsal_ok'}):
            self.assertEqual(ops.main(['--project-name', PROJECT, '--embed-stub', '--stage', 'probe']), 0)

    def test_a_healthy_probe_ends_zero_and_a_stopped_worker_fails_at_index_with_success_zero_and_queue_stuck_and_is_started_again(self):
        rehearsal, docker = self.healthy_stopped_recovered()
        rehearsal.probe_provision()
        rehearsal.probe_healthy()
        rehearsal.probe_worker_stopped()
        rehearsal.probe_recovered()
        self.assertEqual(docker.stopped_when_run, [False, True, False], 'only the second run happens with memory-worker stopped')
        report = rehearsal.report
        self.assertEqual((report['probe_healthy']['exit'], report['probe_healthy']['status']), (0, 'probe_ok'))
        stopped = report['probe_worker_stopped']
        self.assertEqual((stopped['exit'], stopped['status'], stopped['stage'], stopped['code'], stopped['kairos_probe_success']), (1, 'probe_failed', 'index', 'timeout', 0))
        self.assertLessEqual(stopped['seconds_to_failure'], ops.PROBE_TIMEOUT_SECONDS)
        self.assertTrue(stopped['queue']['stuck'])
        self.assertEqual(report['probe_recovered']['status'], 'probe_ok')
        starts = [c for c in docker.commands if c[:2] == ['docker', 'start']]
        self.assertEqual([c[-1] for c in starts], ['memory-worker-container', 'memory-worker-container'][:len(starts)])
        self.assertTrue(starts, 'the worker is started again')

    def test_the_probe_runs_use_the_service_definition_a_short_timeout_and_the_isolated_project_only(self):
        rehearsal, docker = self.healthy_stopped_recovered()
        for step in rehearsal.probe_steps():
            step()
        runs = [c for c in docker.commands if 'memory-probe' in c and 'run' in c]
        self.assertEqual(len(runs), 3)
        for command in runs:
            self.assertEqual(command[command.index('-p') + 1], PROJECT)
            self.assertIn(['--profile', 'probe'], [command[i:i+2] for i in range(len(command) - 1)])  # the `probe` profile
            self.assertEqual(command[-2:], ['memory-probe', 'probe'])
            self.assertIn('MEMORY_PROBE_TIMEOUT=%d' % ops.PROBE_TIMEOUT_SECONDS, command)
        self.assertIn('MEMORY_QUEUE_STUCK_SECONDS=%d' % ops.PROBE_STUCK_SECONDS, runs[1])
        for command in docker.commands:
            text = ' '.join(command)
            self.assertNotIn('knowledge-graphs-', text)
            self.assertNotIn('knowledge-graphs_', text)
            self.assertNotIn('11434', text)

    def test_a_probe_that_does_not_behave_fails_the_rehearsal_and_the_worker_is_started_anyway(self):
        cases = {
            'healthy probe exits non-zero': ([(1, dict(OK))], [SUCCESS_1], 'probe_healthy'),
            'healthy probe leaves success 0': ([(0, dict(OK))], [SUCCESS_0], 'probe_healthy'),
            'healthy probe finds the queue stuck': ([(0, dict(OK, queue={'stuck': True}))], [SUCCESS_1], 'probe_healthy'),
            'healthy probe read no queue': ([(0, dict(OK, queue=None))], [SUCCESS_1], 'probe_healthy'),
        }
        for label, (runs, metrics, step) in cases.items():
            with self.subTest(label):
                rehearsal, _ = self.rehearsal(runs, metrics)
                with self.assertRaises(ops.RehearsalError):
                    getattr(rehearsal, step)()
        stopped_cases = {
            'stopped worker but the probe passes': ([(0, dict(OK))], [SUCCESS_1]),
            'fails at another stage': ([(1, dict(STOPPED, stage='write'))], [SUCCESS_0]),
            'fails with another code': ([(1, dict(STOPPED, code='server_error'))], [SUCCESS_0]),
            'success stays 1 in the file': ([(1, dict(STOPPED))], [SUCCESS_1]),
            'fails later than MEMORY_PROBE_TIMEOUT': ([(1, dict(STOPPED, stages={'write': 1.0, 'index': 45.0}))], [SUCCESS_0]),
            'no queue_stuck': ([(1, dict(STOPPED, queue={'stuck': False}))], [SUCCESS_0]),
            'exit zero with a failed report': ([(0, dict(STOPPED))], [SUCCESS_0]),
        }
        for label, (runs, metrics) in stopped_cases.items():
            with self.subTest(label):
                rehearsal, docker = self.rehearsal(runs, metrics)
                with self.assertRaises(ops.RehearsalError):
                    rehearsal.probe_worker_stopped()
                self.assertTrue([c for c in docker.commands if c[:2] == ['docker', 'start']], 'the worker is started again')

    def test_a_probe_that_does_not_recover_fails_the_rehearsal(self):
        rehearsal, _ = self.rehearsal([(1, dict(STOPPED))], [SUCCESS_0])
        with self.assertRaises(ops.RehearsalError):
            rehearsal.probe_recovered()


if __name__ == '__main__':
    unittest.main()
