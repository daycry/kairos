"""An isolated rehearsal (--project-name) can never reach the installed project's names, volumes or ports."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_platform.tests.test_admin import workspace

spec = importlib.util.spec_from_file_location('kairos_deploy_isolation', Path(__file__).parents[3] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

COMPOSE = Path(__file__).parents[3] / 'docker-compose.yml'


def arguments(**changes):
    values = dict(apply=True, fresh=False, secret_dir=None, verify_key_file=None)
    values.update(changes)
    return SimpleNamespace(**values)


class IsolationValidationTests(unittest.TestCase):
    def test_default_project_keeps_its_names_and_rejects_rehearsal_ports(self):
        deploy.validate_isolation('knowledge-graphs', 8790, 5173)
        self.assertEqual(deploy.project_volumes('knowledge-graphs'), deploy.VOLUMES)
        with self.assertRaises(deploy.DeploymentError):
            deploy.validate_isolation('knowledge-graphs', 18790, 15173)

    def test_isolated_names_and_ports_are_checked(self):
        deploy.validate_isolation('kairos-rehearsal', 18790, 15173)
        for name in ('knowledge-graphs-two', 'knowledge', 'Kairos', 'kairos_rehearsal', '-x', 'a' * 41, ''):
            with self.assertRaises(deploy.DeploymentError, msg=name):
                deploy.validate_isolation(name, 18790, 15173)
        for ports in ((8790, 15173), (18790, 5173), (18790, 18790), (80, 15173), (18790, 70000)):
            with self.assertRaises(deploy.DeploymentError, msg=str(ports)):
                deploy.validate_isolation('kairos-rehearsal', *ports)

    def test_override_replaces_every_fixed_name_port_and_installed_image_of_the_compose_file(self):
        import yaml
        base = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))
        text = deploy.isolation_override('kairos-rehearsal', 18790, 15173)
        override = yaml.load(text.replace('!override', ''), Loader=yaml.SafeLoader)
        self.assertNotIn('knowledge-graphs', text)
        for kind in ('networks', 'volumes'):
            for key, value in (base.get(kind) or {}).items():
                if isinstance(value, dict) and str(value.get('name', '')).startswith('knowledge-graphs'):
                    self.assertTrue(override[kind][key]['name'].startswith('kairos-rehearsal_'), (kind, key))
        for service, value in base['services'].items():
            if str(value.get('image', '')).startswith('kairos-'):
                self.assertTrue(override['services'][service]['image'].startswith('rehearsal-kairos-rehearsal-'), service)
            if value.get('ports'):
                self.assertEqual(len(override['services'][service]['ports']), len(value['ports']), service)
        self.assertEqual(override['services']['memory-api']['ports'], ['127.0.0.1:18790:8790'])
        self.assertEqual(override['services']['memory-web']['ports'], ['127.0.0.1:15173:8080'])
        self.assertEqual(base['services']['memory-postgres']['build']['target'], 'postgres-pgvector')


class IsolatedDeploymentTests(unittest.TestCase):
    def secrets(self, root):
        (root / 'docker-compose.yml').write_text(COMPOSE.read_text(encoding='utf-8'), encoding='utf-8')
        folder = root / 'rehearsal-secrets'
        folder.mkdir()
        for name in ('postgres_password', 'dsn', 'bootstrap_password'):
            (folder / name).write_text('synthetic-only', encoding='utf-8')
        return folder

    def test_isolated_run_uses_only_its_own_project_files_names_and_environment(self):
        with workspace() as root:
            (root / '.env').write_text('MEMORY_SECRETS_DIR=/installed/secrets\n', encoding='utf-8')
            (root / '.private').mkdir()
            (root / '.private' / 'memory-platform.env').write_text('MEMORY_SECRETS_DIR=/installed/secrets\n', encoding='utf-8')
            secrets = self.secrets(root)
            own = root / '.private' / 'rehearsal-kairos-rehearsal'
            own.mkdir()
            (own / 'memory-platform.env').write_text('MEMORY_SECRETS_DIR=' + secrets.as_posix() + '\n', encoding='utf-8')
            instance = deploy.Deployment(arguments(secret_dir=str(secrets), project_name='kairos-rehearsal', api_port=18790, web_port=15173), root)
            self.assertEqual(instance.private, own)
            self.assertEqual(instance.environment['MEMORY_ALLOWED_ORIGINS'], 'http://127.0.0.1:15173,http://localhost:15173')

            def run(command, **kwargs):
                if command[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'secrets': {'memory_postgres': {'file': str(secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(instance.volumes)}})
                if command[-1] == 'inspect':
                    return '{"tables":{}}'
                return ''
            with patch.object(instance, 'run', side_effect=run) as calls, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(deploy.DeploymentError):
                instance.apply()
            commands = [call.args[0] for call in calls.call_args_list]
            joined = '\n'.join(' '.join(command) for command in commands)
            self.assertNotIn('knowledge-graphs', joined)
            self.assertNotIn(str(root / '.env'), joined)
            self.assertNotIn(str(root / '.private' / 'memory-platform.env'), joined)
            compose = next(command for command in commands if command[:2] == ['docker', 'compose'] and '-p' in command)
            self.assertEqual(compose[2:4], ['-p', 'kairos-rehearsal'])
            override = own / 'compose.override.yml'
            self.assertEqual(compose.count('--env-file'), 1)
            self.assertEqual(compose[compose.index('--env-file') + 1], str(own / 'memory-platform.env'))
            self.assertIn(str(override), compose)
            self.assertIn('kairos-rehearsal_memory-postgres-data', joined)
            self.assertIn('memory-postgres', next(c for c in commands if 'build' in c))
            self.assertFalse((root / '.private' / 'deployment-status.json').exists())

    def test_default_run_is_unchanged_and_passes_no_environment_override(self):
        with workspace() as root:
            instance = deploy.Deployment(arguments(), root)
            self.assertEqual((instance.project, instance.private, instance.volumes, instance.environment), ('knowledge-graphs', root / '.private', deploy.VOLUMES, None))
            self.assertEqual(instance.compose[:4], ['docker', 'compose', '-p', 'knowledge-graphs'])
            with patch.object(deploy.subprocess, 'run') as run:
                run.return_value = SimpleNamespace(returncode=0, stdout='ok\n', stderr='')
                instance.run(['docker', 'version'])
            self.assertIsNone(run.call_args.kwargs['env'])

    def test_build_phase_includes_the_postgres_image(self):
        source = (Path(__file__).parents[3] / 'scripts/deploy-memory.py').read_text(encoding='utf-8')
        self.assertRegex(source, re.compile(r"\['build', 'memory-postgres', \*SERVICES, 'memory-admin'\]"))

    def isolated(self, root, project='kairos-rehearsal', with_env=True):
        secrets = self.secrets(root)
        own = root / '.private' / ('rehearsal-' + project)
        own.mkdir(parents=True)
        if with_env:
            (own / 'memory-platform.env').write_text('MEMORY_SECRETS_DIR=' + secrets.as_posix() + '\n', encoding='utf-8')
        return deploy.Deployment(arguments(secret_dir=str(secrets), project_name=project, api_port=18790, web_port=15173), root), secrets

    def test_project_named_kairos_cannot_produce_installed_image_tags(self):
        import yaml
        text = deploy.isolation_override('kairos', 18790, 15173)
        override = yaml.load(text.replace('!override', ''), Loader=yaml.SafeLoader)
        base = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))
        installed = {value['image'] for value in base['services'].values() if 'image' in value}
        generated = {value['image'] for value in override['services'].values()}
        self.assertFalse(installed & generated)
        self.assertTrue(all(tag.startswith('rehearsal-kairos-') for tag in generated))
        deploy.validate_isolation('kairos', 18790, 15173)
        deploy.check_isolation_names('kairos', COMPOSE.read_text(encoding='utf-8'))

    def test_a_colliding_generated_name_is_refused(self):
        forced = COMPOSE.read_text(encoding='utf-8') + '\n  x:\n    image: rehearsal-clash-api:latest\n'
        with self.assertRaises(deploy.DeploymentError):
            deploy.check_isolation_names('clash', forced)

    def test_existing_private_subdirectory_of_somebody_else_is_never_adopted(self):
        with workspace() as root:
            stray = root / '.private' / 'rehearsal-clash'
            stray.mkdir(parents=True)
            (stray / 'notes.txt').write_text('not ours', encoding='utf-8')
            with self.assertRaises(deploy.DeploymentError):
                deploy.Deployment(arguments(project_name='clash', api_port=18790, web_port=15173), root)
            (stray / 'notes.txt').unlink()
            (stray / 'compose.override.yml').write_text('x', encoding='utf-8')
            deploy.Deployment(arguments(project_name='clash', api_port=18790, web_port=15173), root)

    def test_isolated_environment_drops_memory_compose_and_kairos_variables(self):
        with workspace() as root, patch.dict('os.environ', {'MEMORY_SECRETS_DIR': '/installed/secrets', 'MEMORY_DSN_FILE': '/x', 'COMPOSE_FILE': 'other.yml', 'KAIROS_X': '1', 'PATH_KEEP': 'yes'}):
            instance, _ = self.isolated(root)
            for name in ('MEMORY_SECRETS_DIR', 'MEMORY_DSN_FILE', 'COMPOSE_FILE', 'KAIROS_X'):
                self.assertNotIn(name, instance.environment)
            self.assertEqual(instance.environment['PATH_KEEP'], 'yes')
            self.assertIn('MEMORY_ALLOWED_ORIGINS', instance.environment)

    def test_isolated_run_needs_its_own_env_file_before_any_compose_call(self):
        with workspace() as root, patch.dict('os.environ', {'MEMORY_SECRETS_DIR': '/installed/secrets'}):
            instance, secrets = self.isolated(root, with_env=False)
            commands = []
            with patch.object(instance, 'run', side_effect=lambda command, **kw: commands.append(command) or ''), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(deploy.DeploymentError) as raised:
                instance.apply()
            self.assertIn('needs its own', str(raised.exception))
            self.assertFalse(any('config' in command for command in commands))

    def migrate_run(self, backfill_answer=None, fail_stop=False, fail_when=None, verify_answer=None, restore_answer=None, expect_failure=False, **changes):
        """Run the isolated apply() with a fake runner; returns (instance, ordered compose/operator commands)."""
        with workspace() as root:
            secrets = self.secrets(root)
            own = root / '.private' / 'rehearsal-kairos-rehearsal'
            own.mkdir(parents=True)
            (own / 'memory-platform.env').write_text('MEMORY_SECRETS_DIR=' + secrets.as_posix() + '\n', encoding='utf-8')
            instance = deploy.Deployment(arguments(secret_dir=str(secrets), project_name='kairos-rehearsal', api_port=18790, web_port=15173, **changes), root)
            commands = []
            self.timeouts = []  # the timeout of each call of `commands`, in step
            answers = {'inspect': '{"tables":{"actors":1}}', 'content-manifest': '{"sha256":"s","documents":[],"projects":[]}',
                       'backup': '{"status":"backed_up","path":"/backups/kairos-before-20261116T090000000000Z.dump","bytes":1}', 'migrate': '{"status":"migrated"}',
                       'verify-backup': verify_answer or '{"status":"verified","encrypted":false,"bytes":1}',
                       'backfill-chunks': backfill_answer or '{"status":"backfilled","enqueued":7,"remaining":0,"batches":1,"embedding_filled":0}'}

            def run(command, **kwargs):
                commands.append(command)
                self.timeouts.append(kwargs.get('timeout'))
                if fail_stop and 'stop' in command:
                    raise RuntimeError('stop failed')
                if fail_when and fail_when(command):
                    raise deploy.DeploymentError('simulated failure')
                if any('restore-check' in part for part in command):
                    return restore_answer or '{"status":"restored_and_content_verified","tables":{"actors":{"rows":1,"sha256":"a"}}}'
                if command[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'secrets': {'memory_postgres': {'file': str(secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(instance.volumes)}})
                if 'memory-admin' in command and command[-1] in answers or 'backup' in command or 'verify-backup' in command:
                    return answers[next(part for part in command if part in answers)]
                return ''
            sleeps = []

            def sleep_guard(seconds):
                sleeps.append(seconds)
                if len(sleeps) > 200:
                    raise AssertionError('a wait that never ends')
            with patch.object(instance, 'run', side_effect=run), patch.object(deploy, 'verify_runtime', return_value={}), patch.object(deploy.time, 'sleep', side_effect=sleep_guard), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if fail_stop:
                    with self.assertRaises(RuntimeError):
                        instance.apply()
                elif fail_when or expect_failure:
                    with self.assertRaises(deploy.DeploymentError):
                        instance.apply()
                else:
                    instance.apply()
            return instance, commands

    def test_services_are_left_running_during_migrate_by_default(self):
        instance, commands = self.migrate_run()
        stops = [n for n, command in enumerate(commands) if 'stop' in command]
        migrate = next(n for n, command in enumerate(commands) if 'memory-admin' in command and command[-1] == 'migrate')
        backfill = next(n for n, command in enumerate(commands) if 'memory-admin' in command and command[-1] == 'backfill-chunks')
        # Nothing stops before migrate; only the memory-worker stops, after migrate and right before the backfill (gap 4).
        self.assertEqual(len(stops), 1)
        self.assertTrue(migrate < stops[0] < backfill)
        self.assertEqual(commands[stops[0]][-1:], ['memory-worker'])
        self.assertNotIn('services_stopped_before_migrate', instance.report)
        self.assertTrue(instance.report['worker_stopped_before_backfill'])

    def test_opt_in_stops_api_and_worker_right_before_migrate(self):
        instance, commands = self.migrate_run(stop_services_before_migrate=True)
        stops = [n for n, command in enumerate(commands) if 'stop' in command]
        migrate = next(n for n, command in enumerate(commands) if 'memory-admin' in command and command[-1] == 'migrate')
        self.assertEqual(len(stops), 2)  # api + worker before migrate, the worker again right before the backfill
        self.assertLess(stops[0], migrate)
        self.assertEqual(commands[stops[0]][-2:], ['memory-api', 'memory-worker'])
        self.assertTrue(instance.report['services_stopped_before_migrate'])

    def test_a_failure_after_stopping_the_services_says_they_are_still_stopped(self):
        self.assertEqual(deploy.failure_hints({}, 'migrate'), [])
        self.assertEqual(deploy.failure_hints({'services_stopped_before_migrate': True}, 'start'), [])
        hints = deploy.failure_hints({'worker_stopped_before_backfill': True}, 'backfill')
        self.assertEqual(len(hints), 1)
        self.assertIn('memory-worker was stopped before the backfill', hints[0])
        self.assertEqual(deploy.failure_hints({'worker_stopped_before_backfill': True}, 'migrate'), [])
        for phase in ('migrate', 'bootstrap'):
            hints = deploy.failure_hints({'services_stopped_before_migrate': True}, phase)
            self.assertEqual(len(hints), 1)
            self.assertIn('still stopped', hints[0])

    def test_a_backfill_failure_with_both_stops_names_the_api_too_and_a_failed_stop_is_still_reported(self):
        both = {'services_stopped_before_migrate': True, 'worker_stopped_before_backfill': True}
        hints = deploy.failure_hints(both, 'backfill')
        self.assertEqual(len(hints), 1)
        self.assertIn('memory-api', hints[0])
        self.assertEqual(len(deploy.failure_hints({'services_stopped_before_migrate': True}, 'backfill')), 1)
        self.assertEqual(len(deploy.failure_hints({'worker_stopped_before_backfill': True}, 'start')), 1)
        instance, _ = self.migrate_run(fail_stop=True, stop_services_before_migrate=True)  # the stop itself fails: it may have stopped one of them
        self.assertTrue(instance.report['services_stopped_before_migrate'])
        self.assertTrue(deploy.failure_hints(instance.report, 'migrate'))

    def test_migrate_phase_has_its_own_long_timeout_recorded_in_the_report(self):
        with workspace() as root:
            instance, secrets = self.isolated(root)
            instance.verify_backup = False  # this test is about the migrate timeout; the verify phase has its own tests
            timeouts = {}
            answers = {'inspect': '{"tables":{"actors":1}}', 'content-manifest': '{"sha256":"s","documents":[],"projects":[]}',
                       'backup': '{"status":"backed_up"}', 'migrate': '{"status":"migrated"}',
                       'backfill-chunks': '{"status":"backfilled","enqueued":0,"remaining":0,"batches":0,"embedding_filled":0}'}

            def run(command, **kwargs):
                if command[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'secrets': {'memory_postgres': {'file': str(secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(instance.volumes)}})
                if 'memory-admin' in command and command[-1] in answers or 'backup' in command:
                    verb = next(part for part in command if part in answers)
                    timeouts[verb] = kwargs.get('timeout')
                    return answers[verb]
                return ''
            with patch.object(instance, 'run', side_effect=run), patch.object(deploy, 'verify_runtime', return_value={}), contextlib.redirect_stdout(io.StringIO()):
                instance.apply()
            self.assertEqual(timeouts['migrate'], deploy.MIGRATE_TIMEOUT_SECONDS)
            self.assertGreaterEqual(deploy.MIGRATE_TIMEOUT_SECONDS, 1800)
            self.assertEqual(instance.report['migrate_timeout_seconds'], deploy.MIGRATE_TIMEOUT_SECONDS)
            saved = json.loads((instance.private / 'deployment-status.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['migrate_timeout_seconds'], deploy.MIGRATE_TIMEOUT_SECONDS)


def label(command):
    """What a recorded command of the apply() double is, for the order assertions of the verify phase."""
    if 'run' in command and 'memory-admin' in command[command.index('run'):]:
        return 'operator:' + command[-1] if command[-1] in ('migrate', 'inspect', 'content-manifest') else 'operator:' + next((p for p in command if p in ('backup', 'verify-backup', 'backfill-chunks', 'bootstrap')), '?')
    if command[:3] == ['docker', 'network', 'create']:
        return 'network-create'
    if command[:3] == ['docker', 'network', 'rm']:
        return 'network-rm'
    if command[:3] == ['docker', 'run', '--detach']:
        return 'database-start'
    if command[:2] == ['docker', 'exec'] and 'pg_isready' in command:
        return 'database-ready'
    if command[:2] == ['docker', 'exec'] and 'psql' in command:
        return 'create-database'
    if command[:3] == ['docker', 'run', '--rm'] and '--entrypoint' in command:
        return 'restore'
    if command[:3] == ['docker', 'rm', '--force']:
        return 'remove:' + command[-1].split('-')[2]
    return 'other'


class VerifyBackupPhaseTests(unittest.TestCase):
    """O-02 / CA-05: the copy made before `migrate` is restored in an ephemeral, isolated PostgreSQL and compared with its manifest; a difference stops the deployment before `migrate`."""

    def run_phases(self, **changes):
        helper = IsolatedDeploymentTests('migrate_run')
        instance, commands = helper.migrate_run(**changes)
        return instance, commands, [label(command) for command in commands]

    def positions(self, labels, *wanted):
        found = []
        for name in wanted:
            found.append(next(n for n, value in enumerate(labels) if value == name or value.startswith(name)))
        return found

    def test_the_sequence_is_copy_verify_ephemeral_restore_compare_remove_then_migrate(self):
        instance, commands, labels = self.run_phases()
        order = self.positions(labels, 'operator:backup', 'operator:verify-backup', 'network-create', 'database-start', 'database-ready', 'create-database', 'restore', 'remove:op', 'remove:pg', 'network-rm', 'operator:migrate')
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(set(order)), len(order))
        report = instance.report['verify_backup']
        self.assertEqual((report['status'], report['cleanup']), ('verified', 'complete'))
        self.assertRegex(report['database'], r'^memory_restore_[0-9a-f]{12}$')
        self.assertGreaterEqual(report['duration_seconds'], 0)
        self.assertEqual(report['tables'], 1)
        self.assertEqual(instance.report['phases'][instance.report['phases'].index('backup') + 1:instance.report['phases'].index('backup') + 3], ['verify_backup', 'migrate'])

    def test_the_ephemeral_resources_are_isolated_named_apart_and_never_the_projects(self):
        instance, commands, labels = self.run_phases(backup_timeout=7200)
        verify = [command for command, name in zip(commands, labels) if name in ('network-create', 'database-start', 'database-ready', 'create-database', 'restore') or name.startswith('remove:') or name == 'network-rm']
        joined = '\n'.join(' '.join(command) for command in verify)
        self.assertNotIn('knowledge-graphs', joined)
        self.assertNotIn('--publish', joined)
        self.assertNotIn(' -p ', joined)
        self.assertNotIn('compose', joined)
        network = commands[labels.index('network-create')]
        self.assertIn('--internal', network)
        start = commands[labels.index('database-start')]
        self.assertEqual(start[start.index('--network') + 1], network[-1])
        self.assertEqual(start[-1], 'rehearsal-kairos-rehearsal-postgres:latest')
        self.assertIn('no-new-privileges:true', start)
        restore = commands[labels.index('restore')]
        self.assertEqual(restore[restore.index('--network') + 1], network[-1])
        self.assertIn(f'{instance.volumes[1]}:/backups:ro', restore)  # the project's backups, read only
        self.assertIn('rehearsal-kairos-rehearsal-operator:latest', restore)
        self.assertIn('--from-manifest', restore[-1])
        target = next(part for part in restore if part.startswith('TARGET_DSN='))
        self.assertEqual(target, f"TARGET_DSN=postgresql://postgres@{start[start.index('--name') + 1]}:5432/{instance.report['verify_backup']['database']}")
        self.assertIn('MEMORY_DSN=postgresql://unused@127.0.0.1:1/unused', restore)  # the live database is not even named
        for name in (start[start.index('--name') + 1], restore[restore.index('--name') + 1], network[-1]):
            self.assertRegex(name, r'^kairos-verify-(pg-|op-)?[0-9a-f]{12}$')

    def test_the_verify_and_restore_commands_get_the_backup_timeout(self):
        helper = IsolatedDeploymentTests('migrate_run')
        instance, commands = helper.migrate_run(backup_timeout=7200)
        by_label = {label(command): timeout for command, timeout in zip(commands, helper.timeouts)}
        self.assertEqual((by_label['operator:verify-backup'], by_label['restore']), (7200, 7200))
        verify = next(command for command in commands if label(command) == 'operator:verify-backup')
        self.assertIn('--name', verify)

    def test_a_difference_stops_the_deployment_before_migrate_and_everything_ephemeral_is_removed(self):
        instance, commands, labels = self.run_phases(fail_when=lambda command: label(command) == 'restore')
        self.assertNotIn('operator:migrate', labels)
        self.assertFalse(any(name in ('operator:backfill-chunks', 'operator:bootstrap') for name in labels))
        for name in ('remove:op', 'remove:pg', 'network-rm'):
            self.assertIn(name, labels)
        report = instance.report
        self.assertEqual(report['verify_backup']['status'], 'failed')
        self.assertIn('duration_seconds', report['verify_backup'])
        self.assertEqual(report['verify_backup']['cleanup'], 'complete')
        self.assertNotIn('migrate', report['phases'])

    def test_whichever_step_fails_the_containers_and_the_network_are_removed_and_migrate_never_runs(self):
        for step in ('network-create', 'database-start', 'create-database', 'restore'):
            with self.subTest(step=step):
                instance, commands, labels = self.run_phases(fail_when=lambda command, step=step: label(command) == step)
                self.assertNotIn('operator:migrate', labels)
                for name in ('remove:op', 'remove:pg', 'network-rm'):
                    self.assertIn(name, labels, step)
                self.assertEqual(instance.report['verify_backup']['status'], 'failed')

    def test_an_ephemeral_database_that_never_answers_is_a_failure_after_the_wait_and_is_removed(self):
        ticks = iter(range(0, 10000, 40))
        with patch.object(deploy.time, 'monotonic', side_effect=lambda: next(ticks)):
            instance, commands, labels = self.run_phases(fail_when=lambda command: label(command) == 'database-ready')
        self.assertNotIn('operator:migrate', labels)
        self.assertNotIn('restore', labels)
        self.assertIn('network-rm', labels)
        self.assertEqual(instance.report['verify_backup']['status'], 'failed')

    def test_a_failing_cleanup_does_not_hide_the_real_error_and_is_reported(self):
        instance, commands, labels = self.run_phases(fail_when=lambda command: label(command) in ('restore', 'network-rm'))
        self.assertEqual(instance.report['verify_backup']['status'], 'failed')
        self.assertTrue(instance.report['verify_backup']['cleanup'].startswith('incomplete: remove kairos-verify-'))
        self.assertNotIn('operator:migrate', labels)
        self.assertNotIn('command_failure', instance.report, 'a clean-up failure is not the failure of the deployment')

    def test_an_encrypted_copy_is_checked_without_decrypting_and_nothing_is_started(self):
        instance, commands, labels = self.run_phases(verify_answer='{"status":"verified","encrypted":true}')
        self.assertFalse([name for name in labels if name in ('network-create', 'database-start', 'restore')])
        self.assertEqual(instance.report['verify_backup']['status'], 'integrity_only')
        self.assertEqual(instance.report['verify_backup']['restore'], 'skipped')
        self.assertIn('operator:migrate', labels)

    def test_an_answer_that_is_not_a_verified_restore_is_a_failure_too(self):
        instance, commands, labels = self.run_phases(restore_answer='{"status":"restored","tables":{}}', expect_failure=True)
        self.assertNotIn('operator:migrate', labels)
        self.assertEqual(instance.report['verify_backup']['status'], 'failed')
        self.assertIn('network-rm', labels)

    def test_a_verify_answer_that_is_not_verified_stops_before_anything_is_started(self):
        instance, commands, labels = self.run_phases(verify_answer='{"status":"unverified","encrypted":false}', expect_failure=True)
        self.assertFalse([name for name in labels if name in ('network-create', 'database-start', 'restore')])
        self.assertNotIn('operator:migrate', labels)
        self.assertEqual(instance.report['verify_backup']['status'], 'failed')

    def test_a_copy_that_does_not_verify_stops_before_anything_is_started(self):
        instance, commands, labels = self.run_phases(fail_when=lambda command: label(command) == 'operator:verify-backup')
        self.assertFalse([name for name in labels if name in ('network-create', 'database-start', 'restore')])
        self.assertNotIn('operator:migrate', labels)
        self.assertEqual(instance.report['verify_backup']['status'], 'failed')

    def test_it_can_be_switched_off_and_the_default_depends_on_the_project(self):
        instance, commands, labels = self.run_phases(verify_backup=False)
        self.assertNotIn('verify_backup', instance.report)
        self.assertNotIn('operator:verify-backup', labels)
        self.assertNotIn('verify_backup', instance.report['phases'])
        self.assertIn('operator:migrate', labels)
        with workspace() as root:
            self.assertIs(deploy.Deployment(arguments(), root).verify_backup, False)  # the installed project: opt-in
            self.assertIs(deploy.Deployment(arguments(verify_backup=True), root).verify_backup, True)
            self.assertIs(deploy.Deployment(arguments(project_name='kairos-rehearsal', api_port=18790, web_port=15173), root).verify_backup, True)  # a rehearsal: on
            self.assertIs(deploy.Deployment(arguments(project_name='kairos-rehearsal', api_port=18790, web_port=15173, verify_backup=False), root).verify_backup, False)

    def test_the_plan_lists_the_phase_between_backup_and_migrate_only_when_it_will_run(self):
        base = ['--project-name', 'kairos-rehearsal', '--api-port', '18790', '--web-port', '15173']
        for argv, expected in ((base, True), (base + ['--no-verify-backup'], False), (['--verify-backup'], True), ([], False)):
            with patch.object(deploy.subprocess, 'run'), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(deploy.main(argv), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan['verify_backup'], expected, argv)
            self.assertEqual('verify_backup' in plan['phases'], expected, argv)
            if expected:
                phases = plan['phases']
                self.assertEqual(phases[phases.index('backup') + 1:phases.index('backup') + 3], ['verify_backup', 'migrate'])

    def test_a_fresh_installation_has_no_previous_copy_and_nothing_to_verify(self):
        with workspace() as root:
            instance, secrets = IsolatedDeploymentTests('migrate_run').isolated(root)
            instance.args.fresh = True
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                if command[-3:] == ['config', '--format', 'json']:
                    return json.dumps({'secrets': {'memory_postgres': {'file': str(secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(instance.volumes)}})
                if command[-1] == 'inspect':
                    return '{"tables":{}}'
                if command[-1] == 'content-manifest':
                    return '{"sha256":"s","documents":[],"projects":[]}'
                if command[-1] in ('migrate', 'bootstrap'):
                    return '{"status":"ok"}'
                if command[-1] == 'backfill-chunks':
                    return '{"status":"backfilled","enqueued":0,"remaining":0,"batches":0,"embedding_filled":0}'
                return ''
            with patch.object(instance, 'run', side_effect=run), patch.object(deploy, 'verify_runtime', return_value={}), contextlib.redirect_stdout(io.StringIO()):
                instance.apply()
            self.assertNotIn('verify_backup', instance.report)
            self.assertFalse([label(command) for command in commands if label(command) in ('network-create', 'database-start', 'operator:verify-backup')])
