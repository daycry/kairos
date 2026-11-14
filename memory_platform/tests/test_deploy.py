"""Deployment ordering, fail-closed behavior and read-only content fingerprints."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from memory_platform.tests.test_admin import workspace

spec = importlib.util.spec_from_file_location('kairos_deploy', Path(__file__).parents[2] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def arguments(**changes):
    return SimpleNamespace(apply=True, fresh=False, secret_dir=None, verify_key_file=None, **changes)


class DeploymentTests(unittest.TestCase):
    def test_compose_matches_recorded_network_hashes_without_recreating_shared_networks(self):
        import yaml
        networks = yaml.safe_load((Path(__file__).parents[2]/'docker-compose.yml').read_text())['networks']
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
