"""Deployment ordering, fail-closed behavior and read-only content fingerprints."""
import contextlib
import importlib.util
import io
import json
import re
import shlex
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from memory_platform.tests.test_admin import workspace

spec = importlib.util.spec_from_file_location('kairos_deploy', Path(__file__).parents[3] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def rehearsal_override(root, project='kairos-rehearsal'):
    return root / '.private' / ('rehearsal-' + project) / 'compose.override.yml'


def arguments(**changes):
    return SimpleNamespace(apply=True, fresh=False, secret_dir=None, verify_key_file=None, **changes)


class DeploymentTests(unittest.TestCase):
    def test_compose_matches_recorded_network_hashes_without_recreating_shared_networks(self):
        import yaml
        networks = yaml.safe_load((Path(__file__).parents[3]/'docker-compose.yml').read_text())['networks']
        recorded = {'webui': 'a34c5a4e713eec0a05343cc7032bc678d660fff906b23d5244b3cc54d450b071',
                    'inference': 'b98bb704e368c5d52ba904a5e3e77ea065bddc46c517dcde08a1e8613eb392c2'}
        for name, wanted in recorded.items():
            desired = dict(networks[name], ipam={})
            self.assertEqual(deploy.native_network_hash(desired), wanted)
            observed = {'Driver': 'bridge', 'Internal': name == 'inference', 'Labels': {'com.docker.compose.config-hash': wanted}}
            deploy.check_network(desired, observed)
            changed = {k:v for k,v in desired.items() if k != 'driver'}
            with self.assertRaises(deploy.DeploymentError):
                deploy.check_network(changed, observed)

    def test_default_is_a_plan_without_engine_network_or_filesystem_mutations(self):
        with patch.object(deploy.subprocess, 'run') as run, patch.object(deploy.Deployment, 'apply') as apply, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(deploy.main([]), 0)
        self.assertEqual(json.loads(output.getvalue())['mode'], 'dry-run')
        run.assert_not_called()
        apply.assert_not_called()

    def test_denied_engine_stops_before_private_files_or_mutations(self):
        with workspace() as root:
            instance = deploy.Deployment(arguments(), root)
            with patch.object(deploy.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='permission denied')) as run, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(deploy.DeploymentError):
                    instance.apply()
            self.assertFalse((root / '.private').exists())
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][:2], ['docker', 'version'])

    def test_existing_volume_with_empty_database_cannot_be_bootstrapped(self):
        with workspace() as root:
            secrets = root / 'private-secrets'
            secrets.mkdir()
            for name in ('postgres_password', 'dsn', 'bootstrap_password'):
                (secrets/name).write_text('synthetic-only', encoding='utf-8')
            instance = deploy.Deployment(SimpleNamespace(fresh=False, secret_dir=str(secrets), verify_key_file=None), root)
            def run(command, **kwargs):
                if command[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'secrets': {'memory_postgres': {'file': str(secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(deploy.VOLUMES)}})
                if command[-1] == 'inspect':
                    return '{"tables":{}}'
                return ''
            with patch.object(instance, 'run', side_effect=run) as calls, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(deploy.DeploymentError):
                instance.apply()
            operations = [call.args[0] for call in calls.call_args_list]
            self.assertFalse(any('migrate' in command or 'bootstrap' in command or 'start' in command for command in operations))
            self.assertFalse(any('--remove-orphans' in command or '-v' in command for command in operations))

    def test_changed_content_prevents_success(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.compare_content({'sha256': 'old'}, {'sha256': 'changed'})
        deploy.compare_content({'sha256': 'same'}, {'sha256': 'same'})

    def test_command_failure_preserves_redacted_diagnostic_for_recovery(self):
        with workspace() as root:
            instance = deploy.Deployment(arguments(), root)
            instance.phase = 'start'
            instance.secret_values = ['synthetic-password-only']
            output = Mock(returncode=1, stdout='', stderr='service failed: host unavailable; password=synthetic-password-only; postgresql://user:another-password@db/test')
            with patch.object(deploy.subprocess, 'run', return_value=output), self.assertRaises(deploy.DeploymentError):
                instance.run(['docker', 'compose', 'up'])
            diagnostic = instance.report['command_failure']
            self.assertIn('host unavailable', diagnostic['details'])
            self.assertNotIn('synthetic-password-only', json.dumps(diagnostic))
            self.assertNotIn('another-password', json.dumps(diagnostic))

    def test_symlink_paths_rejected_before_use(self):
        target = Mock(is_symlink=Mock(return_value=True))
        path = Mock(absolute=Mock(return_value=target))
        target.parents = []
        with self.assertRaises(deploy.DeploymentError):
            deploy.safe_path(path)


if __name__ == '__main__':
    unittest.main()

class BackfillPhaseTests(unittest.TestCase):
    """Decision P-07: the fragments of the existing content are queued at deployment, right after migrate and before the services start."""
    def run_phases(self, backfill_answer=None):
        from memory_platform.tests.test_deploy_isolation import IsolatedDeploymentTests
        helper = IsolatedDeploymentTests('migrate_run')
        return helper.migrate_run(backfill_answer=backfill_answer)

    def test_the_plan_lists_the_backfill_between_bootstrap_and_start(self):
        phases = list(deploy.PHASES)
        self.assertLess(phases.index('migrate'), phases.index('backfill'))
        self.assertEqual(phases[phases.index('bootstrap') + 1:phases.index('bootstrap') + 3], ['backfill', 'start'])
        with patch.object(deploy.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(deploy.main([]), 0)
        self.assertIn('backfill', json.loads(output.getvalue())['phases'])
        run.assert_not_called()  # the simulation only prints the plan

    def test_apply_queues_the_backfill_after_migrate_and_before_start_and_reports_counts_only(self):
        instance, commands = self.run_phases()
        names = [command[-1] for command in commands if 'memory-admin' in command]
        self.assertLess(names.index('migrate'), names.index('backfill-chunks'))
        started = next(n for n, command in enumerate(commands) if 'up' in command and 'ollama' in command)
        backfill = next(n for n, command in enumerate(commands) if command[-1] == 'backfill-chunks')
        self.assertLess(backfill, started)
        self.assertEqual(instance.report['backfill'], {'status': 'backfilled', 'enqueued': 7, 'remaining': 0, 'batches': 1, 'embedding_filled': 0})
        stop = next(n for n, command in enumerate(commands) if 'stop' in command and command[-1] == 'memory-worker')
        self.assertLess(stop, backfill)  # the previous worker never sees the queued jobs
        self.assertEqual(instance.report['phases'][instance.report['phases'].index('bootstrap') + 1], 'backfill')

    def test_fix1_a_running_memory_probe_is_recreated_with_the_new_image_and_one_that_is_not_running_is_not_started(self):
        """The profile `probe` is opt-in and the main `up` does not name it: a loop that was already running would go on with the image of the previous release."""
        from memory_platform.tests.test_deploy_isolation import IsolatedDeploymentTests
        helper = IsolatedDeploymentTests('migrate_run')
        _, without = helper.migrate_run(probe_running=False)
        self.assertFalse([c for c in without if 'memory-probe' in c], 'a service that was not running is not started')
        instance, commands = helper.migrate_run(probe_running=True)
        main_up = next(n for n, command in enumerate(commands) if 'up' in command and 'ollama' in command)
        recreate = [n for n, command in enumerate(commands) if 'up' in command and 'memory-probe' in command]
        self.assertEqual(len(recreate), 1)
        command = commands[recreate[0]]
        self.assertGreater(recreate[0], main_up)
        self.assertTrue({'--profile', 'probe', '--force-recreate', '--no-deps', '-d'} <= set(command), command)
        self.assertEqual(command[-1], 'memory-probe')
        self.assertNotIn('--wait', command)  # its healthcheck has a start period of 120 s: the deployment does not wait for it
        self.assertTrue(instance.report.get('probe_recreated'))
        verify = instance.report['phases'].index('verify')
        self.assertLess(instance.report['phases'].index('start'), verify)

    def test_milestone_b_review_a_running_memory_backup_is_recreated_too_and_the_report_says_so(self):
        """Both services of the `operator` image (`memory-probe`, `memory-backup`) are recreated when they run; `memory-backup` is SIGTERM-safe (the partial copy is dropped, the next cycle redoes it)."""
        from memory_platform.tests.test_deploy_isolation import IsolatedDeploymentTests
        helper = IsolatedDeploymentTests('migrate_run')
        _, without = helper.migrate_run(probe_running=True, backup_running=False)
        self.assertFalse([c for c in without if 'memory-backup' in c], 'a service that was not running is not started')
        instance, commands = helper.migrate_run(probe_running=True, backup_running=True)
        main_up = next(n for n, command in enumerate(commands) if 'up' in command and 'ollama' in command)
        recreate = [n for n, command in enumerate(commands) if 'up' in command and 'memory-backup' in command]
        self.assertEqual(len(recreate), 1)
        command = commands[recreate[0]]
        self.assertGreater(recreate[0], main_up)
        self.assertTrue({'--profile', 'backup', '--force-recreate', '--no-deps', '-d'} <= set(command), command)
        self.assertEqual(command[-1], 'memory-backup')
        self.assertNotIn('--wait', command)
        self.assertTrue(instance.report.get('backup_recreated'))
        self.assertTrue(instance.report.get('probe_recreated'))

    def recreation(self, label, backup_running=True, project='kairos-rehearsal'):
        """The `memory-backup` of an apply whose container was created with the Compose files `label` (a function of the root: `None` leaves the label empty, an Exception makes the question fail)."""
        from memory_platform.tests.test_deploy_isolation import IsolatedDeploymentTests
        instance, commands = IsolatedDeploymentTests('migrate_run').migrate_run(probe_running=False, backup_running=backup_running, project=project, config_files={'memory-backup': label})
        return instance, commands, [c for c in commands if 'up' in c and c[-1] == 'memory-backup']

    def test_milestone_b_review_n1_the_recreation_keeps_the_compose_files_the_container_was_created_with(self):
        """(a) with the rclone override, both `-f` in the order of the label (the container keeps its `egress` network); (b) with only `docker-compose.yml`; the rehearsal override stays in both."""
        for names in (['docker-compose.yml', 'docker-compose.backup-rclone.yml'], ['docker-compose.yml']):
            with self.subTest(names=names):
                instance, _, recreate = self.recreation(lambda root, names=names: ','.join([str(root / name) for name in names] + [str(rehearsal_override(root))]))
                self.assertEqual(len(recreate), 1)
                files = [Path(recreate[0][n + 1]).name for n, part in enumerate(recreate[0]) if part == '-f']
                self.assertEqual(files, names + ['compose.override.yml'], recreate[0])
                self.assertTrue(instance.report.get('backup_recreated'))
                self.assertNotIn('backup_recreate_skipped', instance.report)

    def manual_command(self, label, **options):
        """The `-f` list of the command that is printed for a `memory-backup` that is not recreated, and the whole text of stderr."""
        from memory_platform.tests import test_deploy_isolation as isolation
        helper = isolation.IsolatedDeploymentTests('migrate_run')
        instance, commands = helper.migrate_run(probe_running=False, backup_running=True, config_files={'memory-backup': label}, **options)
        text = helper.stderr.getvalue()
        manual = shlex.split(text.split('it was created with: ', 1)[1].strip().splitlines()[0])
        return instance, commands, text, [manual[n + 1] for n, part in enumerate(manual) if part == '-f']

    def test_milestone_b_review_fix3_r31_the_manual_command_reproduces_the_whole_label_in_its_order(self):
        names = ['docker-compose.yml', 'docker-compose.backup-rclone.yml', 'custom.yml']
        instance, commands, _, files = self.manual_command(lambda root: ','.join(str(root / name) for name in names))
        self.assertEqual([Path(f).name for f in files], names, files)
        self.assertEqual([c for c in commands if 'up' in c and c[-1] == 'memory-backup'], [])
        self.assertTrue(instance.report.get('backup_recreate_skipped'))

    def test_milestone_b_review_fix3_r31_without_a_reliable_label_the_manual_command_says_so_and_invents_no_file(self):
        from memory_platform.tests import test_deploy_isolation as isolation
        for name, label in {'empty': lambda root: '', 'unreadable': lambda root: isolation.deploy.DeploymentError('boom'),
                            'two containers': lambda root: str(root / 'docker-compose.yml') + chr(10) + str(root / 'docker-compose.backup-rclone.yml')}.items():
            with self.subTest(name):
                _, _, text, files = self.manual_command(label)
                self.assertEqual(files, ['<files it was created with>'])
                self.assertIn('could not be known', text)
                self.assertNotIn('docker-compose.yml', text.split('it was created with: ', 1)[1])

    def test_milestone_b_review_fix3_r32_a_rehearsal_container_without_the_rehearsal_override_is_not_recreated(self):
        instance, commands, recreate = self.recreation(lambda root: str(root / 'docker-compose.yml'))
        self.assertEqual(recreate, [])
        self.assertIn('created without the rehearsal override; recreating it would use the installation image and volumes', instance.report.get('backup_recreate_skipped', ''))
        self.assertNotIn('command_failure', instance.report)
        self.assertIn('verify', instance.report['phases'])

    def test_milestone_b_review_fix3_r32_the_manual_command_of_a_rehearsal_container_adds_the_rehearsal_override(self):
        """Following the printed command must never recreate a rehearsal service with the installation image and volumes: it carries the label and then the rehearsal override."""
        _, _, text, files = self.manual_command(lambda root: str(root / 'docker-compose.yml'))
        self.assertEqual([Path(f).name for f in files], ['docker-compose.yml', 'compose.override.yml'], files)
        self.assertIn('rehearsal override', text)

    def test_milestone_b_review_fix3_r33_a_one_off_container_is_left_out_and_identical_labels_count_once_but_different_ones_do_not(self):
        _, commands, recreate = self.recreation(lambda root: chr(10).join([','.join(str(root / n) for n in ('docker-compose.yml', '.private/rehearsal-kairos-rehearsal/compose.override.yml'))] * 2))
        self.assertEqual(len(recreate), 1)
        asked = next(c for c in commands if c[:2] == ['docker', 'ps'] and any('config_files' in part for part in c))
        self.assertIn('label=com.docker.compose.oneoff=False', asked)
        instance, _, recreate = self.recreation(lambda root: str(root / 'docker-compose.yml') + chr(10) + str(root / 'docker-compose.backup-rclone.yml'))
        self.assertEqual(recreate, [])
        self.assertIn('more than one container', instance.report['backup_recreate_skipped'])

    def test_milestone_b_review_fix3_r34_the_question_is_limited_to_the_project(self):
        _, commands, _ = self.recreation(lambda root: '', project='kairos-ops-r34')
        asked = [c for c in commands if c[:2] == ['docker', 'ps'] and any('config_files' in part for part in c)]
        self.assertTrue(asked)
        for command in asked:
            self.assertIn('label=com.docker.compose.project=kairos-ops-r34', command)

    def test_milestone_b_review_fix3_r35_control_characters_of_the_label_never_reach_stderr_or_the_report(self):
        dirty = '/etc/x' + chr(27) + '[2J' + chr(7) + chr(0x9b) + '31m' + chr(0x7f) + '.yml'
        instance, _, text, _ = self.manual_command(lambda root: str(root / 'docker-compose.yml') + ',' + dirty)
        bad = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]')
        self.assertIsNone(bad.search(text), repr(text))
        self.assertIsNone(bad.search(json.dumps(instance.report, ensure_ascii=False)))
        self.assertIn('\\x1b', text)

    def test_milestone_b_review_n1_a_service_made_with_other_files_or_an_unreadable_label_is_not_recreated_and_the_deployment_still_succeeds(self):
        """(c) a file that is not ours, (d) a label that is empty or cannot be read: no `up` for it, `backup_recreate_skipped` in the report, the manual command on stderr, status ok."""
        from memory_platform.tests import test_deploy_isolation as isolation
        IsolatedDeploymentTests = isolation.IsolatedDeploymentTests  # the module of that file has its own copy of the script: its DeploymentError is the one the double raises
        cases = {'foreign file': lambda root: str(root / 'docker-compose.yml') + ',' + str(root / 'docker-compose.other.yml'),
                 'empty label': lambda root: '', 'question fails': lambda root: isolation.deploy.DeploymentError('boom')}
        for name, label in cases.items():
            with self.subTest(name):
                helper_stderr = IsolatedDeploymentTests('migrate_run')
                instance, commands = helper_stderr.migrate_run(probe_running=False, backup_running=True, config_files={'memory-backup': label})
                recreate = [c for c in commands if 'up' in c and c[-1] == 'memory-backup']
                errors = helper_stderr.stderr
                self.assertEqual(recreate, [])
                self.assertTrue(instance.report.get('backup_recreate_skipped'), instance.report)
                self.assertNotIn('backup_recreated', instance.report)
                self.assertNotIn('command_failure', instance.report)
                self.assertIn('--force-recreate', errors.getvalue())
                self.assertIn('memory-backup', errors.getvalue())
                self.assertIn('verify', instance.report['phases'])

    def test_milestone_b_review_n1_a_rehearsal_never_names_the_installed_project_when_it_recreates(self):
        _, commands, recreate = self.recreation(lambda root: str(root / 'docker-compose.yml') + ',' + str(rehearsal_override(root, 'kairos-ops-n1')), project='kairos-ops-n1')
        self.assertEqual(recreate[0][recreate[0].index('-p') + 1], 'kairos-ops-n1')
        self.assertFalse([c for c in commands if 'knowledge-graphs' in ' '.join(c) and 'knowledge-graphs-' in ' '.join(c).replace('knowledge-graphs/', '')])

    def test_the_report_keeps_only_the_known_count_keys(self):
        noisy = json.dumps({'status': 'backfilled', 'enqueued': 1, 'remaining': 0, 'batches': 1, 'embedding_filled': 0, 'dsn': 'postgresql://u:secret@h/db'})
        instance, _ = self.run_phases(noisy)
        self.assertNotIn('secret', json.dumps(instance.report))
        self.assertNotIn('dsn', instance.report['backfill'])

    def test_the_report_carries_pending_failed_and_stale_counts_and_nothing_else(self):
        answer = {'status': 'backfilled', 'enqueued': 2, 'derived': 1, 'failed': 3, 'pending': 4, 'remaining': 5, 'batches': 1, 'embedding_filled': 0, 'stale_marked': 6, 'token': 'x'}
        instance, _ = self.run_phases(json.dumps(answer))
        self.assertEqual(instance.report['backfill'], {key: value for key, value in answer.items() if key != 'token'})
        self.assertEqual((instance.report['backfill']['pending'], instance.report['backfill']['failed']), (4, 3))

    def test_a_failed_backfill_stops_the_deployment_before_the_services_start(self):
        with self.assertRaises(Exception) as raised:  # the helper loads its own copy of the script, hence its own exception class
            self.run_phases('not json')
        self.assertEqual(type(raised.exception).__name__, 'DeploymentError')


class BackupTimeoutTests(unittest.TestCase):
    """O-03 / CA-04: `content-manifest`, `backup` (and `verify-backup`) get `--backup-timeout` (3,600 s by default) instead of the 120 s of `operator()`; the other phases keep theirs."""
    LONG = ('content-manifest', 'backup', 'verify-backup')

    def phases(self, **changes):
        from memory_platform.tests.test_deploy_isolation import IsolatedDeploymentTests
        helper = IsolatedDeploymentTests('migrate_run')
        instance, commands = helper.migrate_run(**changes)
        verbs = []
        for command, timeout in zip(commands, helper.timeouts):
            if 'run' in command and 'memory-admin' in command[command.index('run'):]:  # the service after `run`, not the profile of every command
                verbs.append((next(part for part in command if part in ('inspect', 'content-manifest', 'backup', 'verify-backup', 'migrate', 'bootstrap', 'backfill-chunks')), timeout, command))
        return instance, verbs

    def test_the_default_is_3600_seconds_for_the_long_commands_and_it_is_in_the_report(self):
        instance, verbs = self.phases()
        long_ones = [(verb, timeout) for verb, timeout, _ in verbs if verb in self.LONG]
        self.assertEqual(long_ones, [('content-manifest', 3600), ('backup', 3600), ('verify-backup', 3600), ('content-manifest', 3600), ('content-manifest', 3600)])
        self.assertEqual(deploy.BACKUP_TIMEOUT_SECONDS, 3600)
        self.assertEqual(instance.report['backup_timeout_seconds'], 3600)

    def test_an_explicit_timeout_is_propagated_to_every_long_command(self):
        instance, verbs = self.phases(backup_timeout=7200)
        self.assertEqual({timeout for verb, timeout, _ in verbs if verb in self.LONG}, {7200})
        self.assertEqual(instance.report['backup_timeout_seconds'], 7200)

    def test_the_other_phases_keep_their_own_timeouts(self):
        _, verbs = self.phases(backup_timeout=7200)
        others = {verb: timeout for verb, timeout, _ in verbs if verb not in self.LONG}
        self.assertEqual(others, {'inspect': 120, 'migrate': deploy.MIGRATE_TIMEOUT_SECONDS, 'backfill-chunks': deploy.BACKFILL_TIMEOUT_SECONDS})

    def test_a_long_command_runs_in_a_named_container_that_the_deployment_can_stop(self):
        _, verbs = self.phases()
        for verb, _, command in verbs:
            if verb in self.LONG:
                name = command[command.index('--name') + 1]
                self.assertRegex(name, r'^kairos-deploy-' + verb + r'-[0-9a-f]{10}$')
                self.assertNotIn('knowledge-graphs', name)
                self.assertLess(command.index('--name'), command.index('memory-admin', command.index('run')))
            else:  # fix4 (gap 3): every `compose run` has a name its `reap` can stop, so an interruption never leaves a migration running next to a retry
                name = command[command.index('--name') + 1]
                self.assertRegex(name, r'^kairos-deploy-' + verb + r'-[0-9a-f]{10}$')

    def test_an_invalid_timeout_is_refused_by_the_deployment_and_by_the_command_line(self):
        for bad in (0, -5, True, 86401, '10', 1.5):
            with self.subTest(bad=bad), workspace() as root, self.assertRaises(deploy.DeploymentError):
                deploy.Deployment(arguments(backup_timeout=bad), root)
        with workspace() as root:
            self.assertEqual(deploy.Deployment(arguments(backup_timeout=86400), root).backup_timeout, 86400)
        for argv in (['--backup-timeout', '0'], ['--backup-timeout', '86401'], ['--backup-timeout', 'soon'], ['--apply', '--backup-timeout', '-1']):
            with self.subTest(argv=argv), patch.object(deploy.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                deploy.main(argv)
            self.assertEqual(raised.exception.code, 2)
            run.assert_not_called()

    def test_the_plan_states_the_timeout(self):
        for argv, expected in (([], 3600), (['--backup-timeout', '90'], 90)):
            with patch.object(deploy.subprocess, 'run'), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(deploy.main(argv), 0)
            self.assertEqual(json.loads(output.getvalue())['backup_timeout_seconds'], expected)

    def test_a_command_that_times_out_has_its_container_stopped_and_removed_and_the_error_is_kept(self):
        with workspace() as root:
            instance = deploy.Deployment(arguments(), root)
            calls = []

            def record(command, **kwargs):
                calls.append(command)
                return Mock(returncode=0)
            with patch.object(instance, 'run', side_effect=deploy.DeploymentError('Command unavailable or timed out')) as run, patch.object(deploy.subprocess, 'run', side_effect=record):
                with self.assertRaises(deploy.DeploymentError) as raised:
                    instance.long_operator('backup', '--output', '/backups/x.dump')
            self.assertIn('timed out', str(raised.exception))
            self.assertEqual(run.call_args.kwargs['timeout'], 3600)
            compose = run.call_args.args[0]
            name = compose[compose.index('--name') + 1]
            self.assertEqual(calls, [['docker', 'stop', '--time', '20', name], ['docker', 'rm', '--force', '--volumes', name]])
            self.assertEqual(instance.report['reaped_containers'], [name])

    def test_a_failing_stop_does_not_hide_the_timeout_and_a_command_that_succeeds_is_not_reaped(self):
        with workspace() as root:
            instance = deploy.Deployment(arguments(), root)
            with patch.object(instance, 'run', side_effect=deploy.DeploymentError('timed out')), patch.object(deploy.subprocess, 'run', side_effect=OSError('docker is gone')):
                with self.assertRaises(deploy.DeploymentError):
                    instance.long_operator('content-manifest')
            instance = deploy.Deployment(arguments(), root)
            with patch.object(instance, 'run', return_value='{"sha256": "s"}'), patch.object(deploy.subprocess, 'run') as docker:
                self.assertEqual(instance.long_operator('content-manifest'), {'sha256': 's'})
            docker.assert_not_called()
            self.assertNotIn('reaped_containers', instance.report)


class McpServiceTests(unittest.TestCase):
    """T-40 (CA-09): `memory-mcp` lives on a network of its own with `memory-api` alone: no database, no secrets, no model proxy."""

    @classmethod
    def setUpClass(cls):
        import yaml
        cls.root = Path(__file__).parents[3]
        cls.compose = yaml.safe_load((cls.root / 'docker-compose.yml').read_text(encoding='utf-8'))
        cls.service = cls.compose['services']['memory-mcp']

    def test_the_service_has_no_secrets_no_dsn_and_only_the_api_address(self):
        self.assertNotIn('secrets', self.service)
        environment = self.service['environment']
        self.assertEqual(environment['KAIROS_API_URL'], 'http://memory-api:8790')
        self.assertEqual(sorted(environment), ['KAIROS_ALLOWED_ORIGINS', 'KAIROS_API_TIMEOUT', 'KAIROS_API_URL', 'KAIROS_MAX_BODY_BYTES', 'KAIROS_VALIDATION_THREADS'])  # the whole configuration of the component
        self.assertFalse([key for key in environment if key.startswith('MEMORY_')], 'kairos-mcp takes no MEMORY_* setting')
        self.assertFalse([key for key in environment if 'DSN' in key or 'PASSWORD' in key or 'SECRET' in key])

    def test_the_service_is_on_the_mcp_network_only_and_that_network_is_internal(self):
        networks = self.service['networks']
        self.assertEqual(list(networks), ['mcp'])
        for forbidden in ('memory-data', 'inference', 'egress', 'webui'):
            self.assertNotIn(forbidden, networks)
        self.assertIs(self.compose['networks']['mcp']['internal'], True)

    def test_only_memory_api_shares_the_mcp_network(self):
        members = {name for name, value in self.compose['services'].items() if 'mcp' in (value.get('networks') or [])}
        self.assertEqual(members, {'memory-api', 'memory-mcp', 'memory-web'})  # memory-web routes /mcp to this service (T-52)

    def test_the_image_is_built_from_the_component_alone_and_waits_for_the_api(self):
        self.assertEqual(self.service['image'], 'kairos-mcp:latest')
        self.assertEqual(self.service['build']['context'], './mcp')
        self.assertEqual(self.service['depends_on']['memory-api']['condition'], 'service_healthy')
        self.assertIn('memory', self.service['profiles'])
        self.assertIn('/health/live', json.dumps(self.service['healthcheck']))

    def test_the_deployment_script_builds_starts_and_plans_the_service(self):
        self.assertIn('memory-mcp', deploy.SERVICES)
        with patch.object(deploy.subprocess, 'run'), contextlib.redirect_stdout(io.StringIO()) as output:
            deploy.main([])
        self.assertIn('memory-mcp', json.loads(output.getvalue())['services'])

    def test_a_rehearsal_gets_its_own_image_and_network_for_the_service(self):
        import yaml
        override = yaml.load(deploy.isolation_override('kairos-rehearsal', 18790, 15173).replace('!override', ''), Loader=yaml.SafeLoader)
        self.assertEqual(override['services']['memory-mcp']['image'], 'rehearsal-kairos-rehearsal-mcp:latest')
        self.assertEqual(override['networks']['mcp']['name'], 'kairos-rehearsal_mcp')

    def test_the_new_network_of_an_upgrade_is_created_by_the_start_not_a_missing_infrastructure_error(self):
        # An installation that predates kairos-mcp has no `knowledge-graphs_mcp` network: `up` creates it; any other missing network still stops.
        self.assertEqual(deploy.NEW_NETWORKS, ('mcp',))

    def test_the_diagnosis_knows_the_service_and_its_network(self):
        source = (self.root / 'scripts' / 'diagnose-deployment.py').read_text(encoding='utf-8')
        self.assertIn("'memory-mcp'", source)
        self.assertIn('knowledge-graphs_mcp', source)
