"""C-04 / CA-23 (O-06): one deployment at a time per project. The lock is an operating-system lock (`flock` on POSIX, `msvcrt.locking` on Windows) on `deployment.lock` in the private
directory of the project, held by an open file for the whole deployment; the operating system frees it when the process ends, however it ends, so an owner that is dead never needs
`--break-lock` on this host. A second deployment ends with `deployment_locked` before any phase runs. The JSON in the file (PID, host, start, stamp) is informative: it is written after
the lock is taken and is what the refusal message shows. `--break-lock` is only for a lock whose owner is on ANOTHER host. Fix2 of the review of phase 10 (gaps 3, 4, 5, 8): no window
between two owners (nothing is renamed or linked back), no traceback on Windows, a content that is not an object does not make the lock impossible to take, no file left behind.
Processes here are real (`subprocess`); no test runs Docker: `subprocess.run` is a double that must not be called."""
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
import tempfile
import unittest
from unittest.mock import patch

from memory_platform.tests.test_admin import workspace

SCRIPT = Path(__file__).parents[3] / 'scripts/deploy-memory.py'
spec = importlib.util.spec_from_file_location('kairos_deploy_lock', SCRIPT)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

PROJECT = 'kairos-ops-lk'
ARGV = ['--apply', '--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--secret-dir', 'unused']
OWNER_TIME = '2026-11-17T08:30:00Z'
LOAD = "import importlib.util, sys\nspec = importlib.util.spec_from_file_location('d', sys.argv[1]); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)\n"
HOLDER = LOAD + "lock = d.DeployLock(sys.argv[2], sys.argv[3]); lock.acquire()\nprint('held', flush=True)\nimport time; time.sleep(120)\n"
COMPETE = LOAD + """import os, time
directory, shared = sys.argv[2], sys.argv[3]
lock = d.DeployLock(directory, 'p')
for _ in range(2000):
    try:
        lock.acquire()
        break
    except d.DeploymentLocked:
        time.sleep(0.002)
else:
    sys.exit(3)
try:
    os.close(os.open(os.path.join(shared, 'inside'), os.O_CREAT | os.O_EXCL | os.O_WRONLY))  # two owners at once: the second cannot create it
except FileExistsError:
    sys.exit(4)
counter = os.path.join(shared, 'counter')
value = int(open(counter).read())
time.sleep(0.01)
open(counter, 'w').write(str(value + 1))
os.unlink(os.path.join(shared, 'inside'))
lock.release()
"""


def private_of(root):
    return root / '.private' / ('rehearsal-' + PROJECT)


def write_lock(root, pid=4242, host=None, text=None, **extra):
    """The content of a lock file as a process left it (written by hand: the format is part of what is pinned). Nothing holds an operating-system lock on it."""
    directory = private_of(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'deployment.lock'
    path.write_text(text if text is not None else json.dumps({'pid': pid, 'host': host or socket.gethostname(), 'started_at': OWNER_TIME, 'project': PROJECT, 'token': 'other', **extra}), encoding='utf-8')
    return path


def run_main(root, argv=ARGV):
    """main() of the script in `root`, with every command a double that fails the test if it runs; returns (exit code, stdout, stderr, the double)."""
    out, err = io.StringIO(), io.StringIO()
    with patch.object(deploy.subprocess, 'run', side_effect=AssertionError('no command may run')) as run, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = deploy.main(argv, root=root)
    return code, out.getvalue(), err.getvalue(), run


class Holder:
    """A real process that takes the lock of `directory` and keeps it until it is killed."""

    def __init__(self, directory, project=PROJECT):
        self.process = subprocess.Popen([sys.executable, '-c', HOLDER, str(SCRIPT), str(directory), project], stdout=subprocess.PIPE, text=True)
        if self.process.stdout.readline().strip() != 'held':
            self.process.kill()
            raise AssertionError('the holder did not take the lock')

    def kill(self):
        self.process.kill()
        self.process.wait()
        self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.process.poll() is None:
            self.kill()


class LockedDeploymentTests(unittest.TestCase):
    def test_a_second_deployment_ends_with_deployment_locked_before_any_phase_and_names_the_owner(self):
        with workspace() as root, Holder(private_of(root)) as holder:
            path = private_of(root) / 'deployment.lock'
            before = path.read_text(encoding='utf-8')
            with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')) as apply:
                code, out, err, run = run_main(root)
            self.assertEqual(code, 3)
            self.assertIn('deployment_locked', err)
            self.assertIn(str(holder.process.pid), err)
            self.assertIn(socket.gethostname(), err)
            self.assertRegex(err, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
            apply.assert_not_called()
            run.assert_not_called()
            self.assertEqual(path.read_text(encoding='utf-8'), before, 'the lock of the running deployment is left as it was')
            self.assertFalse((private_of(root) / 'deployment-status.json').exists(), 'the report of the running deployment is not overwritten')

    def test_break_lock_never_breaks_the_lock_of_a_live_owner_of_this_host(self):
        with workspace() as root, Holder(private_of(root)) as holder:
            path = private_of(root) / 'deployment.lock'
            before = path.read_text(encoding='utf-8')
            with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                code, out, err, run = run_main(root, ARGV + ['--break-lock'])
            self.assertEqual(code, 3)
            self.assertIn('still running', err)
            self.assertIn('wait', err)
            self.assertEqual(path.read_text(encoding='utf-8'), before)
            self.assertIsNone(holder.process.poll(), 'the holder was not touched')

    def test_fix2_an_owner_that_died_needs_no_break_lock_the_next_deployment_takes_the_lock(self):
        """Fix2 (gaps 3, 8): the operating system frees the lock when its process ends (a SIGKILL included): nothing has to be broken, renamed or put back."""
        with workspace() as root:
            holder = Holder(private_of(root))
            holder.kill()
            path = private_of(root) / 'deployment.lock'
            self.assertIn(str(holder.process.pid), path.read_text(encoding='utf-8'), 'the dead owner left its information behind')
            seen = []

            def apply(instance):
                seen.append(json.loads(path.read_text(encoding='utf-8')))
            with patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=apply):
                code, out, err, run = run_main(root)
            self.assertEqual(code, 0)
            self.assertEqual(seen[0]['pid'], os.getpid(), 'the information is the new owner\'s')
            self.assertNotIn('lock broken', err)
            self.assertEqual(sorted(child.name for child in private_of(root).iterdir()), ['deployment.lock'], 'no other file is ever left by the lock')

    def test_a_lock_file_that_nobody_holds_is_taken_whatever_it_says(self):
        """A lock file of an earlier version, of a deployment that was killed, with a host or a PID that means nothing, or with content that is not an object (gap 5): free is free."""
        for label, text in (('an older lock', json.dumps({'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': OWNER_TIME, 'token': 'x'})), ('null', 'null'), ('a list', '[]'), ('a number', '7'),
                            ('a string', '"x"'), ('empty', ''), ('not json', 'half a js'), ('another host', json.dumps({'pid': 4242, 'host': 'some-other-machine', 'token': 'x'})),
                            ('bytes that are not UTF-8', None)):
            with self.subTest(label), workspace() as root:
                path = write_lock(root, text=text) if text is not None else write_lock(root, text='')
                if text is None:
                    path.write_bytes(b'\xff\xfe\x00garbage')
                with patch.object(deploy.Deployment, 'apply', autospec=True):
                    code, out, err, run = run_main(root)
                self.assertEqual(code, 0)
                self.assertNotIn('lock broken', err)

    def test_the_content_of_a_lock_that_is_held_and_unreadable_is_a_refusal_with_a_message_not_a_traceback(self):
        for text in ('null', '[]', '', '{"pid": "x", "host": 3}'):
            with self.subTest(text=text), workspace() as root, Holder(private_of(root)) as holder:
                path = private_of(root) / 'deployment.lock'
                path.write_text(text, encoding='utf-8')
                with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root, ARGV + ['--break-lock'])
                self.assertEqual(code, 3)
                self.assertIn('deployment_locked', err)
                self.assertNotIn('Traceback', err)

    def test_fix2_break_lock_is_only_for_a_lock_written_by_another_host(self):
        """The one case a PID cannot answer: the file says another host holds it (a private directory on a shared disk). Without the flag it is `deployment_locked`; with it the file is replaced."""
        with workspace() as root, Holder(private_of(root)) as holder:
            path = private_of(root) / 'deployment.lock'
            path.write_text(json.dumps({'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME, 'project': PROJECT, 'token': 'x'}), encoding='utf-8')
            with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                code, out, err, run = run_main(root)
            self.assertEqual(code, 3)
            self.assertIn('some-other-machine', err)
            self.assertIn('--break-lock', err)
            self.assertTrue(path.exists())
            with patch.object(deploy.Deployment, 'apply', autospec=True):
                code, out, err, run = run_main(root, ARGV + ['--break-lock'])
            if os.name == 'nt':  # a file that another process has open cannot be deleted there: the refusal says so and nothing is broken
                self.assertEqual(code, 3)
                self.assertIn('deployment_locked', err)
                self.assertNotIn('Traceback', err)
            else:
                self.assertEqual(code, 0)
                self.assertIn('lock broken', err)
                self.assertIn('some-other-machine', err)
            self.assertEqual(sorted(child.name for child in private_of(root).iterdir()), ['deployment.lock'])

    def test_fix2_a_lock_that_cannot_be_taken_for_any_reason_is_deployment_locked_never_a_traceback(self):
        """Gap 4: on Windows renaming or locking a file another process has open raised PermissionError and the exit was 1. Any operating-system error is `deployment_locked` (exit 3)."""
        for label, patched in (('locking fails', patch.object(deploy.DeployLock, '_lock_file', side_effect=PermissionError(13, 'Permission denied'))),
                               ('the file cannot be opened', patch.object(deploy.os, 'open', side_effect=PermissionError(13, 'Permission denied'))),
                               ('no locks on this filesystem', patch.object(deploy.DeployLock, '_lock_file', side_effect=OSError(37, 'No locks available')))):
            with self.subTest(label), workspace() as root, patched:
                with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root)
                self.assertEqual(code, 3)
                self.assertIn('deployment_locked', err)
                self.assertNotIn('Traceback', err)

    def test_the_dry_run_takes_no_lock_and_writes_nothing(self):
        with workspace() as root:
            code, out, err, run = run_main(root, ['--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173'])
            self.assertEqual(code, 0)
            self.assertFalse((root / '.private').exists())


class CompetitionTests(unittest.TestCase):
    def test_fix2_real_processes_competing_never_hold_the_lock_together(self):
        """The window of the rename+link scheme (gap 3, `race3.py`, CWE-367): eight processes each take the lock, enter a section that fails if another one is inside, and leave."""
        with tempfile.TemporaryDirectory() as shared, tempfile.TemporaryDirectory() as directory:
            Path(shared, 'counter').write_text('0', encoding='utf-8')
            children = [subprocess.Popen([sys.executable, '-c', COMPETE, str(SCRIPT), directory, shared]) for _ in range(8)]
            codes = [child.wait(timeout=120) for child in children]
            self.assertEqual(codes, [0] * 8, 'a 3 is a process that never got the lock, a 4 two owners at once')
            self.assertEqual(Path(shared, 'counter').read_text(encoding='utf-8'), '8', 'every section ran alone: no update was lost')
            self.assertEqual(sorted(child.name for child in Path(directory).iterdir()), ['deployment.lock'])

    def test_fix2_two_break_lock_and_a_plain_deployment_on_one_stale_lock_leave_exactly_one_owner(self):
        """`repro_lock2.py` cases 2 and 3 and `race3.py`: three deployments (two with --break-lock) find the same stale file; the first takes it and the other two are refused, with its content intact."""
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'deployment.lock').write_text(json.dumps({'pid': 999999, 'host': 'other-host', 'started_at': 'x', 'project': 'p', 'token': 'old'}), encoding='utf-8')
            first, second, third = (deploy.DeployLock(directory, 'p', break_lock=flag) for flag in (True, True, False))
            first.acquire()
            for other in (second, third):
                with self.assertRaises(deploy.DeploymentLocked):
                    other.acquire()
                self.assertFalse(other.held)
            self.assertEqual(json.loads(Path(directory, 'deployment.lock').read_text(encoding='utf-8'))['token'], first.token)
            self.assertEqual(sorted(child.name for child in Path(directory).iterdir()), ['deployment.lock'])
            first.release()
            third.acquire()  # released: the next one takes it
            third.release()

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
            first.release()  # releasing twice is harmless
            deploy.DeployLock(directory, PROJECT).acquire().release()  # and it is free


class ReleaseTests(unittest.TestCase):
    def deploy_with(self, root, effect):
        with patch.object(deploy.Deployment, 'apply', side_effect=effect):
            return run_main(root)

    def free(self, root):
        """The lock is free (it can be taken) and the file says nothing of the deployment that ended."""
        path = private_of(root) / 'deployment.lock'
        again = deploy.DeployLock(private_of(root), PROJECT)
        again.acquire()
        again.release()
        self.assertEqual(path.read_text(encoding='utf-8'), '', 'a deployment that ended leaves no owner in the file')
        self.assertEqual(sorted(child.name for child in private_of(root).iterdir() if child.name.startswith('deployment.lock')), ['deployment.lock'])

    def test_the_lock_is_held_while_the_deployment_runs_with_pid_host_time_and_stamp(self):
        with workspace() as root:
            seen = []
            lock = private_of(root) / 'deployment.lock'

            def apply():
                seen.append(json.loads(lock.read_text(encoding='utf-8')))
                with self.assertRaises(deploy.DeploymentLocked):
                    deploy.DeployLock(private_of(root), PROJECT).acquire()
            code, out, err, run = self.deploy_with(root, apply)
            self.assertEqual(code, 0)
            self.assertEqual((seen[0]['pid'], seen[0]['host'], seen[0]['project']), (os.getpid(), socket.gethostname(), PROJECT))
            self.assertRegex(seen[0]['started_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
            self.assertEqual(seen[0]['stamp'], deploy.process_stamp(os.getpid()))
            self.free(root)

    def test_a_phase_that_fails_or_an_unexpected_error_releases_the_lock(self):
        for error, code in ((deploy.DeploymentError('a phase failed'), 1), (RuntimeError('unexpected'), 1)):
            with self.subTest(error=type(error).__name__), workspace() as root:
                result = self.deploy_with(root, error)
                self.assertEqual(result[0], code)
                self.free(root)

    def test_ctrl_c_releases_the_lock_and_propagates(self):
        with workspace() as root:
            with self.assertRaises(KeyboardInterrupt):
                self.deploy_with(root, KeyboardInterrupt())
            self.free(root)

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM'), 'needs signals')
    def test_sigterm_releases_the_lock_and_puts_the_handlers_back(self):
        with workspace() as root:
            before = signal.getsignal(signal.SIGTERM)
            with self.assertRaises(SystemExit) as raised:
                self.deploy_with(root, lambda: signal.raise_signal(signal.SIGTERM))
            self.assertEqual(raised.exception.code, 128 + signal.SIGTERM)
            self.free(root)
            self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_the_lock_is_not_inherited_by_the_commands_a_deployment_runs(self):
        """A `docker` child that kept the descriptor would hold the lock after the deployment ended."""
        with workspace() as root:
            lock = deploy.DeployLock(private_of(root), PROJECT)
            lock.acquire()
            try:
                child = subprocess.run([sys.executable, '-c', 'import time; time.sleep(0.2)'], timeout=30)
                self.assertEqual(child.returncode, 0)
            finally:
                lock.release()
            deploy.DeployLock(private_of(root), PROJECT).acquire().release()

    def test_the_lock_file_does_not_make_the_private_directory_foreign(self):
        with workspace() as root:
            write_lock(root)
            deploy.Deployment(type('A', (), {'fresh': False, 'secret_dir': None, 'verify_key_file': None, 'project_name': PROJECT, 'api_port': 18790, 'web_port': 15173})(), root)
            self.assertIn(deploy.LOCK_FILE, deploy.ISOLATED_PRIVATE_FILES)


class StampTests(unittest.TestCase):
    def test_the_stamp_of_a_process_is_stable_and_absent_for_a_dead_one(self):
        stamp = deploy.process_stamp(os.getpid())
        if sys.platform.startswith('linux') or os.name == 'nt':
            self.assertTrue(stamp)
        self.assertEqual(stamp, deploy.process_stamp(os.getpid()))
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        self.assertIsNone(deploy.process_stamp(child.pid))
        self.assertIsNone(deploy.process_stamp(0))


if __name__ == '__main__':
    unittest.main()
