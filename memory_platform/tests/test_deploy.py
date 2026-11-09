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
