"""C-04 / CA-23 (O-06): one deployment at a time per project. The lock is a file created exclusively in the private directory of the project (PID, host, time); a second
deployment ends with `deployment_locked` before any phase runs, a lock whose owner is dead is reported and only `--break-lock` removes it (never one whose owner is alive),
and the lock is released on every way out: a phase that fails, an unexpected error, Ctrl-C and SIGTERM. No test here runs Docker: `subprocess` is a double that must not be called."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from memory_platform.tests.test_admin import workspace

spec = importlib.util.spec_from_file_location('kairos_deploy_lock', Path(__file__).parents[3] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

PROJECT = 'kairos-ops-lk'
ARGV = ['--apply', '--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--secret-dir', 'unused']
OWNER_TIME = '2026-11-17T08:30:00Z'


def private_of(root):
    return root / '.private' / ('rehearsal-' + PROJECT)


def write_lock(root, pid=4242, host=None, started=OWNER_TIME, text=None):
    """A lock as another process left it (written by hand: the format is part of what is pinned)."""
    directory = private_of(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'deployment.lock'
    path.write_text(text if text is not None else json.dumps({'pid': pid, 'host': host or socket.gethostname(), 'started_at': started, 'project': PROJECT, 'token': 'other'}), encoding='utf-8')
    return path


def run_main(root, argv=ARGV, **patches):
    """main() of the script in `root`, with every command a double that fails the test if it runs; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with patch.object(deploy.subprocess, 'run', side_effect=AssertionError('no command may run')) as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = deploy.main(argv, root=root)
    return code, out.getvalue(), err.getvalue(), run


class LockedDeploymentTests(unittest.TestCase):
    def test_a_second_deployment_ends_with_deployment_locked_before_any_phase_and_names_the_owner(self):
        with workspace() as root:
            path = write_lock(root)
            before = path.read_text(encoding='utf-8')
            with patch.object(deploy, 'pid_alive', return_value=True), patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')) as apply:
                code, out, err, run = run_main(root)
            self.assertEqual(code, 3)
            self.assertIn('deployment_locked', err)
            self.assertIn('4242', err)
            self.assertIn(OWNER_TIME, err)
            self.assertIn(socket.gethostname(), err)
            apply.assert_not_called()
            run.assert_not_called()
            self.assertEqual(path.read_text(encoding='utf-8'), before, 'the lock of the running deployment is left as it was')
            self.assertFalse((private_of(root) / 'deployment-status.json').exists(), 'the report of the running deployment is not overwritten')

    def test_a_lock_with_a_dead_owner_is_reported_and_kept_without_break_lock(self):
        with workspace() as root:
            path = write_lock(root)
            with patch.object(deploy, 'pid_alive', return_value=False), patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                code, out, err, run = run_main(root)
            self.assertEqual(code, 3)
            self.assertIn('deployment_locked', err)
            self.assertIn('not running', err)
            self.assertIn('--break-lock', err)
            self.assertTrue(path.exists(), 'a stale lock is never broken silently')

    def test_break_lock_removes_a_dead_lock_says_so_and_deploys(self):
        with workspace() as root:
            path = write_lock(root)
            seen = []

            def apply(instance):
                seen.append(path.read_text(encoding='utf-8'))  # while the deployment runs the lock is the new one
            with patch.object(deploy, 'pid_alive', return_value=False), patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=apply):
                code, out, err, run = run_main(root, ARGV + ['--break-lock'])
            self.assertEqual(code, 0)
            self.assertIn('4242', err)
            self.assertIn('lock broken', err)
            self.assertEqual(len(seen), 1)
            self.assertEqual(json.loads(seen[0])['pid'], os.getpid())
            self.assertFalse(path.exists(), 'released at the end')

    def test_break_lock_never_breaks_the_lock_of_a_live_owner(self):
        with workspace() as root:
            path = write_lock(root)
            with patch.object(deploy, 'pid_alive', return_value=True), patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                code, out, err, run = run_main(root, ARGV + ['--break-lock'])
            self.assertEqual(code, 3)
            self.assertIn('still running', err)
            self.assertTrue(path.exists())

    def test_break_lock_breaks_what_it_cannot_check_a_lock_of_another_host_or_one_that_is_unreadable(self):
        for text, host in (('this is not json', None), ('', None), (None, 'some-other-machine')):
            with self.subTest(text=text, host=host), workspace() as root:
                path = write_lock(root, text=text, host=host)
                with patch.object(deploy, 'pid_alive', return_value=True) as alive, patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root)
                self.assertEqual(code, 3, 'without --break-lock it is still a lock')
                self.assertIn('deployment_locked', err)
                alive.assert_not_called() if host else None  # the PID of another machine means nothing here
                self.assertTrue(path.exists())
                with patch.object(deploy, 'pid_alive', return_value=True), patch.object(deploy.Deployment, 'apply', autospec=True):
                    code, out, err, run = run_main(root, ARGV + ['--break-lock'])
                self.assertEqual(code, 0)
                self.assertFalse(path.exists())

    def test_the_dry_run_takes_no_lock_and_writes_nothing(self):
        with workspace() as root:
            code, out, err, run = run_main(root, ['--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173'])
            self.assertEqual(code, 0)
            self.assertFalse((root / '.private').exists())


class ReleaseTests(unittest.TestCase):
    def deploy_with(self, root, effect):
        with patch.object(deploy.Deployment, 'apply', side_effect=effect):
            return run_main(root)

    def test_the_lock_exists_while_the_deployment_runs_with_pid_host_and_time(self):
        with workspace() as root:
            seen = []
            lock = private_of(root) / 'deployment.lock'
            code, out, err, run = self.deploy_with(root, lambda: seen.append(json.loads(lock.read_text(encoding='utf-8'))))
            self.assertEqual(code, 0)
            self.assertEqual((seen[0]['pid'], seen[0]['host'], seen[0]['project']), (os.getpid(), socket.gethostname(), PROJECT))
            self.assertRegex(seen[0]['started_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
            self.assertFalse(lock.exists())

    def test_a_phase_that_fails_or_an_unexpected_error_releases_the_lock(self):
        for error, code in ((deploy.DeploymentError('a phase failed'), 1), (RuntimeError('unexpected'), 1)):
            with self.subTest(error=type(error).__name__), workspace() as root:
                result = self.deploy_with(root, error)
                self.assertEqual(result[0], code)
                self.assertFalse((private_of(root) / 'deployment.lock').exists())

    def test_ctrl_c_releases_the_lock_and_propagates(self):
        with workspace() as root:
            with self.assertRaises(KeyboardInterrupt):
                self.deploy_with(root, KeyboardInterrupt())
            self.assertFalse((private_of(root) / 'deployment.lock').exists())

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM'), 'needs signals')
    def test_sigterm_releases_the_lock_and_puts_the_handlers_back(self):
        with workspace() as root:
            before = signal.getsignal(signal.SIGTERM)
            with self.assertRaises(SystemExit) as raised:
                self.deploy_with(root, lambda: signal.raise_signal(signal.SIGTERM))
            self.assertEqual(raised.exception.code, 128 + signal.SIGTERM)
            self.assertFalse((private_of(root) / 'deployment.lock').exists())
            self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_a_deployment_never_removes_a_lock_that_is_no_longer_its_own(self):
        with workspace() as root:
            lock = private_of(root) / 'deployment.lock'

            def other_takes_over():
                lock.write_text(json.dumps({'pid': 9, 'host': 'h', 'started_at': OWNER_TIME, 'project': PROJECT, 'token': 'someone-else'}), encoding='utf-8')
            self.deploy_with(root, other_takes_over)
            self.assertTrue(lock.exists())
            self.assertEqual(json.loads(lock.read_text(encoding='utf-8'))['token'], 'someone-else')

    def test_two_locks_in_one_process_exclude_each_other(self):
        with workspace() as root:
            directory = private_of(root)
            first = deploy.DeployLock(directory, PROJECT)
            first.acquire()
            try:
                with self.assertRaises(deploy.DeploymentLocked) as raised:
                    deploy.DeployLock(directory, PROJECT).acquire()
                self.assertEqual(raised.exception.code, 'deployment_locked')
                self.assertEqual(raised.exception.owner['pid'], os.getpid())
            finally:
                first.release()
            self.assertFalse((directory / 'deployment.lock').exists())
            first.release()  # releasing twice is harmless

    def test_the_lock_file_does_not_make_the_private_directory_foreign(self):
        with workspace() as root:
            write_lock(root)
            deploy.Deployment(type('A', (), {'fresh': False, 'secret_dir': None, 'verify_key_file': None, 'project_name': PROJECT, 'api_port': 18790, 'web_port': 15173})(), root)


class AliveTests(unittest.TestCase):
    def test_this_process_is_alive_and_a_finished_one_is_not(self):
        self.assertTrue(deploy.pid_alive(os.getpid()))
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        self.assertFalse(deploy.pid_alive(child.pid))
        self.assertFalse(deploy.pid_alive(0))
        self.assertFalse(deploy.pid_alive(-3))


if __name__ == '__main__':
    unittest.main()
