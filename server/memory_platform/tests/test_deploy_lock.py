"""C-04 / CA-23 (O-06): one deployment at a time per project. The lock is an operating-system lock (`flock` on POSIX, `msvcrt.locking` on Windows) on `deployment.lock` in the private
directory of the project, held by an open file for the whole deployment; the operating system frees it when the process ends, however it ends, so an owner that is dead never needs
`--break-lock` on this host. A second deployment ends with `deployment_locked` before any phase runs. The JSON in the file (PID, host, start, stamp) is informative: it is written after
the lock is taken and is what the refusal message shows. `--break-lock` is only for a lock whose owner is on ANOTHER host. Fix2 of the review of phase 10 (gaps 3, 4, 5, 8): no window
between two owners (nothing is renamed or linked back), no traceback on Windows, a content that is not an object does not make the lock impossible to take, no file left behind.
Fix3 of the review of phase 10 (gaps 3, 4, 5, 8): the file is opened with `O_NOFOLLOW` (a planted symbolic link is refused), `--break-lock` never deletes or renames a file (it can only take
a lock the system lets it take), a leftover of a deployment that did not end is reported to the next one, and the file is checked to still be the one at the path before and after it is written.
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
lock = d.DeployLock(directory, 'p', break_lock=len(sys.argv) > 4)
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


def can_symlink():
    with tempfile.TemporaryDirectory() as directory:
        try:
            os.symlink(Path(directory, 'target'), Path(directory, 'link'))
        except (OSError, NotImplementedError):
            return False
    return True


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
        try:
            code = deploy.main(argv, root=root)
        except (KeyboardInterrupt, SystemExit) as exc:  # `main` must return a code: an exception that escapes it is a traceback
            code = f'{type(exc).__name__} escaped main()'
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

    def test_fix3_break_lock_never_deletes_a_file_whose_lock_is_held(self):
        """Gaps 3 and 4: a process that is alive here holds the lock and the file says another host does. With or without `--break-lock` the file is left as it is (same file, same content) and
        the holder is not touched: a file is never deleted to get past a lock that is held."""
        with workspace() as root, Holder(private_of(root)) as holder:
            path = private_of(root) / 'deployment.lock'
            path.write_text(json.dumps({'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME, 'project': PROJECT, 'token': 'x'}), encoding='utf-8')
            before, stat = path.read_text(encoding='utf-8'), os.stat(path)
            for flags in ([], ['--break-lock']):
                with self.subTest(flags=flags), patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root, ARGV + flags)
                    self.assertEqual(code, 3)
                    self.assertIn('deployment_locked', err)
                    self.assertIn('some-other-machine', err)
                    self.assertNotIn('Traceback', err)
                    self.assertEqual(path.read_text(encoding='utf-8'), before)
                    self.assertTrue(os.path.samestat(stat, os.stat(path)), 'the very same file')
                    self.assertIsNone(holder.process.poll())
            self.assertEqual(sorted(child.name for child in private_of(root).iterdir()), ['deployment.lock'])

    def test_fix3_a_break_lock_that_read_a_foreign_owner_in_the_window_does_not_delete_the_file_of_the_one_that_just_took_it(self):
        """Gap 3 (reproduced in `kairos-test:i3p10`): A takes the free file of another host; B (`--break-lock`) was refused and read the OLD content before A emptied it. B used to delete A's file and
        take a new one: two owners. Now B only ever fails or takes what the system lets it take."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'deployment.lock')
            path.write_text(json.dumps({'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME, 'project': 'p', 'token': 'old'}), encoding='utf-8')
            first, second = deploy.DeployLock(directory, 'p'), deploy.DeployLock(directory, 'p', break_lock=True)
            first.acquire()
            stat = os.stat(path)
            with patch.object(deploy.DeployLock, 'owner', return_value={'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME}), self.assertRaises(deploy.DeploymentLocked):
                second.acquire()
            self.assertFalse(second.held)
            self.assertTrue(os.path.samestat(stat, os.stat(path)))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['token'], first.token)
            first.release()

    def test_fix3_nothing_is_ever_deleted_or_renamed_to_take_the_lock(self):
        """Gap 4 (CWE-367): with no `unlink` there is no window between checking the file and deleting it."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'deployment.lock')
            path.write_text(json.dumps({'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME, 'project': 'p', 'token': 'old'}), encoding='utf-8')
            stat = os.stat(path)
            forbidden = AssertionError('the lock never deletes or renames a file')
            with patch.object(deploy.os, 'unlink', side_effect=forbidden), patch.object(deploy.os, 'remove', side_effect=forbidden), patch.object(deploy.os, 'rename', side_effect=forbidden), \
                    patch.object(deploy.os, 'replace', side_effect=forbidden), patch.object(Path, 'unlink', side_effect=forbidden):
                lock = deploy.DeployLock(directory, 'p', break_lock=True).acquire()
                lock.release()
            self.assertTrue(os.path.samestat(stat, os.stat(path)))

    def test_fix3_a_free_lock_file_of_another_host_is_taken_and_the_next_deployment_is_told(self):
        """Gap 8: the file still says a deployment of another host started; nothing holds the lock. It is taken (free is free) and the stderr and the report say what it left behind;
        `--break-lock` only names it as a break."""
        for flags, key, word in (([], 'previous_run_interrupted', 'may still be running'), (['--break-lock'], 'lock_broken', 'lock broken')):
            with self.subTest(flags=flags), workspace() as root:
                write_lock(root, pid=4242, host='some-other-machine')
                seen = []
                with patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=lambda instance: seen.append(json.loads(json.dumps(instance.report)))):
                    code, out, err, run = run_main(root, ARGV + flags)
                self.assertEqual(code, 0)
                self.assertIn(word, err)
                self.assertIn('some-other-machine', err)
                self.assertEqual(seen[0][key], {'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME})

    def test_fix3_a_deployment_that_died_is_reported_to_the_next_one_with_its_pid_host_and_start(self):
        with workspace() as root:
            holder = Holder(private_of(root))
            holder.kill()
            seen = []
            with patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=lambda instance: seen.append(json.loads(json.dumps(instance.report)))):
                code, out, err, run = run_main(root)
            self.assertEqual(code, 0)
            left = seen[0]['previous_run_interrupted']
            self.assertEqual((left['pid'], left['host']), (holder.process.pid, socket.gethostname()))
            self.assertRegex(left['started_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
            self.assertIn('did not end', err)
            self.assertIn(str(holder.process.pid), err)
            self.assertNotIn('lock broken', err)

    def test_fix3_a_lock_file_that_is_empty_says_nothing_and_one_that_is_not_json_is_still_a_leftover(self):
        for text, expected in (('', False), ('half a js', True), ('[]', True)):
            with self.subTest(text=text), workspace() as root:
                write_lock(root, text=text)
                seen = []
                with patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=lambda instance: seen.append(json.loads(json.dumps(instance.report)))):
                    code, out, err, run = run_main(root)
                self.assertEqual(code, 0)
                self.assertEqual('previous_run_interrupted' in seen[0], expected)
                self.assertEqual('did not end' in err, expected)

    @unittest.skipUnless(can_symlink(), 'needs permission to create symbolic links')
    def test_fix3_a_symbolic_link_planted_as_the_lock_is_refused_and_its_target_is_never_touched(self):
        """Gap 5 (CWE-59, reproduced in `kairos-test:i3p10`): `O_CREAT` without `O_NOFOLLOW` followed the link, emptied its target and wrote the owner into it."""
        for label, create in (('an existing file', True), ('a dangling link', False)):
            with self.subTest(label), workspace() as root:
                directory = private_of(root)
                directory.mkdir(parents=True)
                victim = root / 'victim.txt'
                if create:
                    victim.write_text('IMPORTANT DATA\n', encoding='utf-8')
                os.symlink(victim, directory / 'deployment.lock')
                with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root)
                self.assertEqual(code, 3)
                self.assertIn('deployment_locked', err)
                self.assertNotIn('Traceback', err)
                self.assertTrue((directory / 'deployment.lock').is_symlink(), 'the link is left as it is')
                if create:
                    self.assertEqual(victim.read_text(encoding='utf-8'), 'IMPORTANT DATA\n')
                else:
                    self.assertFalse(victim.exists(), 'the link was not followed to create its target')
                with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root, ARGV + ['--break-lock'])
                self.assertEqual(code, 3)

    @unittest.skipIf(os.name == 'nt', 'Windows does not delete a file that is open: the window does not exist there')
    def test_fix3_a_file_that_is_replaced_between_the_open_and_the_lock_is_not_the_lock(self):
        """The standard order: open, lock, compare the descriptor with the path, write, compare again. A file that is not the one at the path is dropped and the lock is taken on the new one."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'deployment.lock')
            lock = deploy.DeployLock(directory, 'p')
            real, calls = deploy.DeployLock._lock_file, []

            def swap(descriptor):
                real(descriptor)
                if not calls:  # the first file is replaced right after it is locked (a delete and a create by someone else)
                    calls.append(1)
                    path.unlink()
                    path.write_text('', encoding='utf-8')
            with patch.object(deploy.DeployLock, '_lock_file', staticmethod(swap)):
                lock.acquire()
            try:
                self.assertTrue(lock.held)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['token'], lock.token, 'the owner is written in the file that is at the path')
                self.assertTrue(os.path.samestat(os.fstat(lock.descriptor), os.stat(path)))
            finally:
                lock.release()

    def test_fix2_a_lock_that_cannot_be_taken_for_any_reason_is_deployment_locked_never_a_traceback(self):
        """Gap 4: on Windows renaming or locking a file another process has open raised PermissionError and the exit was 1. Any operating-system error is `deployment_locked` (exit 3)."""
        for label, patched in (('locking fails', patch.object(deploy.DeployLock, '_lock_file', side_effect=PermissionError(13, 'Permission denied'))),
                               ('the file cannot be opened', patch.object(deploy, 'create_without_following', side_effect=PermissionError(13, 'Permission denied')) if os.name == 'nt'
                                else patch.object(deploy.os, 'open', side_effect=PermissionError(13, 'Permission denied'))),
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


class Fix4Tests(unittest.TestCase):
    """Fix4 of the review of phase 10: the message about a leftover says what is known and no more (gap 4), nothing of the lock file reaches the terminal raw (gap 8), and the lock file must be a
    regular file with one link, however it is created (gap 9)."""
    HOSTILE = ('\x1b]0;PWNED\x07', '\x1b[2J\x1b[31mFAKE OK\x1b[0m\r', 'a\nb\x00c', '‮evil', '\x9b31m' + 'x' * 400)

    @staticmethod
    def raw(text):
        """The characters of `text` that a terminal would act on (every one that is not printable, but the line ends the script itself writes)."""
        return sorted({char for char in text if not char.isprintable() and char != '\n'})

    def apply_seeing(self, root, flags=()):
        seen = []
        with patch.object(deploy.Deployment, 'apply', autospec=True, side_effect=lambda instance: seen.append(json.loads(json.dumps(instance.report)))):
            code, out, err, run = run_main(root, ARGV + list(flags))
        return code, err, seen

    def test_a_leftover_of_another_host_says_what_is_known_not_that_the_deployment_was_killed(self):
        with workspace() as root:
            write_lock(root, pid=4242, host='some-other-machine')
            code, err, seen = self.apply_seeing(root)
            self.assertEqual(code, 0)
            self.assertNotIn('killed', err)
            self.assertNotIn('machine was lost', err)
            self.assertNotIn('did not end', err, 'a deployment of another host may be running right now')
            self.assertIn('not held on this machine', err)
            self.assertIn('shared disk', err)
            self.assertIn('may still be running', err)
            self.assertIn('some-other-machine', err)
            self.assertIn('previous_run_interrupted', seen[0], 'the report still records what the file said')

    def test_a_leftover_of_this_host_and_one_that_names_nobody_still_say_that_the_deployment_did_not_end(self):
        for label, text in (('this host', None), ('names nobody', 'half a js')):
            with self.subTest(label), workspace() as root:
                write_lock(root, text=text)
                code, err, seen = self.apply_seeing(root)
                self.assertEqual(code, 0)
                self.assertIn('did not end', err)
                self.assertNotIn('shared disk', err.split('did not end')[0])

    def test_no_data_of_the_lock_file_reaches_stderr_or_the_report_raw(self):
        """`c_inject.py` of the review (CWE-150): the PID, host and start of the file are written by whoever can write the file; an escape sequence in them must not act on the terminal of the operator."""
        for value in self.HOSTILE:
            for field in ('pid', 'host', 'started_at'):
                kwargs = {'pid': 4242, 'host': 'some-other-machine'}
                kwargs[field] = value
                for flags in ((), ('--break-lock',)):
                    with self.subTest(field=field, value=value[:12], flags=flags), workspace() as root:
                        if field == 'started_at':
                            write_lock(root, **{**kwargs, 'started_at': value})
                        else:
                            write_lock(root, **kwargs)
                        code, err, seen = self.apply_seeing(root, flags)
                        self.assertEqual(code, 0)
                        self.assertEqual(self.raw(err), [], repr(err[:200]))
                        left = seen[0].get('lock_broken') or seen[0]['previous_run_interrupted']
                        self.assertEqual(self.raw(json.dumps(left, ensure_ascii=False)), [], repr(left))
                        self.assertLessEqual(len(err), 2000)

    def test_no_data_of_a_held_lock_file_reaches_stderr_raw_in_a_refusal(self):
        with workspace() as root, Holder(private_of(root)):
            path = private_of(root) / 'deployment.lock'
            for value in self.HOSTILE:
                with self.subTest(value=value[:12]):
                    path.write_text(json.dumps({'pid': value, 'host': value, 'started_at': value, 'project': value, 'token': value}), encoding='utf-8')
                    code, out, err, run = run_main(root)
                    self.assertEqual(code, 3)
                    self.assertEqual(self.raw(err), [], repr(err[:200]))

    @unittest.skipUnless(hasattr(os, 'link'), 'needs hard links')
    def test_a_hard_link_planted_as_the_lock_is_refused_and_the_data_it_links_to_is_never_truncated(self):
        """`c_linux.py` of the review (CWE-59): `O_NOFOLLOW` does not cover a hard link, and taking and releasing the lock emptied the file it linked to."""
        with workspace() as root:
            directory = private_of(root)
            directory.mkdir(parents=True)
            victim = root / 'victim.txt'
            victim.write_text('IMPORTANT DATA\n', encoding='utf-8')
            try:
                os.link(victim, directory / 'deployment.lock')
            except OSError as exc:
                self.skipTest(f'no hard links here: {exc}')
            for flags in ((), ('--break-lock',)):
                with patch.object(deploy.Deployment, 'apply', side_effect=AssertionError('no phase may run')):
                    code, out, err, run = run_main(root, ARGV + list(flags))
                self.assertEqual(code, 3)
                self.assertIn('deployment_locked', err)
                self.assertIn('hard link', err)
                self.assertNotIn('Traceback', err)
                self.assertEqual(victim.read_text(encoding='utf-8'), 'IMPORTANT DATA\n')
                self.assertEqual((directory / 'deployment.lock').read_text(encoding='utf-8'), 'IMPORTANT DATA\n', 'the file is left as it was: not written, not emptied')
            with self.assertRaises(deploy.DeploymentLocked):
                deploy.DeployLock(directory, 'p').acquire()
            self.assertEqual(victim.read_text(encoding='utf-8'), 'IMPORTANT DATA\n')

    def test_a_lock_that_is_not_a_regular_file_is_deployment_locked_and_nothing_hangs(self):
        kinds = [('a directory', os.mkdir)] + ([('a named pipe', os.mkfifo)] if hasattr(os, 'mkfifo') else [])
        for label, make in kinds:
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                make(os.path.join(directory, deploy.LOCK_FILE))
                with self.assertRaises(deploy.DeploymentLocked):
                    deploy.DeployLock(directory, 'p').acquire()

    def test_the_opened_file_is_checked_not_the_path_a_reparse_point_or_a_second_link_found_after_the_open_is_refused_without_writing(self):
        """The double of `fstat` (a Windows reparse point cannot be made here without the privilege of linking): whatever the descriptor says, the file is not written."""
        for label, attributes in (('a reparse point', {'st_file_attributes': 0x400}), ('a second link', {'st_nlink': 2}), ('not a regular file', {'st_mode': 0o040000})):
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory, deploy.LOCK_FILE)
                path.write_text('KEEP', encoding='utf-8')
                real = os.stat(path)
                fields = dict(st_mode=real.st_mode, st_nlink=1, st_file_attributes=0)
                fields.update(attributes)
                fake = type('Info', (), {**fields, 'st_ino': real.st_ino, 'st_dev': real.st_dev})()
                with patch.object(deploy.os, 'fstat', return_value=fake), patch.object(deploy.os, 'ftruncate', side_effect=AssertionError('never written')), self.assertRaises(deploy.DeploymentLocked):
                    deploy.DeployLock(directory, 'p').acquire()
                self.assertEqual(path.read_text(encoding='utf-8'), 'KEEP')

    def test_the_windows_creation_asks_for_the_link_itself_and_never_truncates(self):
        """Gap 9 on any platform (the Windows test below needs Windows): `create_without_following` calls `CreateFileW` with OPEN_ALWAYS and `FILE_FLAG_OPEN_REPARSE_POINT` and turns the
        handle into a descriptor; an invalid handle is an error and a failed conversion closes the handle. `kernel32` and `msvcrt` are doubles here."""
        calls, closed = [], []

        class Kernel:
            def __init__(self, handle):
                self.handle = handle

            def CreateFileW(self, *arguments):
                calls.append(arguments)
                return self.handle

            def CloseHandle(self, handle):
                closed.append(handle)

        class Msvcrt:
            def __init__(self, fail=False):
                self.fail = fail

            def open_osfhandle(self, handle, flags):
                if self.fail:
                    raise OSError('no descriptor')
                return ('fd', handle, flags)
        path = Path(tempfile.gettempdir(), 'kairos-not-created.lock')
        with patch.object(deploy, 'windows_kernel', return_value=Kernel(1234)), patch.dict(sys.modules, {'msvcrt': Msvcrt()}):
            self.assertEqual(deploy.create_without_following(path), ('fd', 1234, 0))
        self.assertEqual(calls[0][0], str(path))
        self.assertTrue(calls[0][5] & 0x00200000, 'FILE_FLAG_OPEN_REPARSE_POINT')
        self.assertEqual(calls[0][4], 4, 'OPEN_ALWAYS: it never truncates')
        with patch.object(deploy, 'windows_kernel', return_value=Kernel(1234)), patch.dict(sys.modules, {'msvcrt': Msvcrt(fail=True)}), self.assertRaises(OSError):
            deploy.create_without_following(path)
        self.assertEqual(closed, [1234], 'the handle is closed when it cannot become a descriptor')
        import ctypes
        with patch.object(deploy, 'windows_kernel', return_value=Kernel(ctypes.c_void_p(-1).value)), patch.dict(sys.modules, {'msvcrt': Msvcrt()}), patch.object(ctypes, 'get_last_error', create=True, return_value=5), patch.object(ctypes, 'WinError', create=True, side_effect=lambda code: OSError(code, 'denied')), self.assertRaises(OSError):
            deploy.create_without_following(path)
        self.assertFalse(path.exists(), 'only the double was called')
        if os.name == 'nt':  # and the real call, on the platform that has it (a test of its own would be a skip on Linux, where the suite gate asks for 0 skipped)
            self.windows_real_creation()

    def windows_real_creation(self):
        """A link planted between the `lstat` and the creation must not create or truncate its target: the file is created with `CreateFileW` and `FILE_FLAG_OPEN_REPARSE_POINT` (and
        OPEN_ALWAYS), which opens the link itself if there is one. The call is recorded here; a real link needs a privilege this account does not have."""
        calls = []
        real = deploy.windows_kernel()

        class Spy:
            def __getattr__(self, name):
                return getattr(real, name)

            def CreateFileW(self, *arguments):
                calls.append(arguments)
                return real.CreateFileW(*arguments)
        with tempfile.TemporaryDirectory() as directory, patch.object(deploy, 'windows_kernel', return_value=Spy()):
            lock = deploy.DeployLock(directory, 'p').acquire()
            try:
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0][5] & 0x00200000, 'FILE_FLAG_OPEN_REPARSE_POINT')
                self.assertEqual(calls[0][4], 4, 'OPEN_ALWAYS: it never truncates')
                self.assertTrue(lock.held)
            finally:
                lock.release()


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

    def test_fix3_real_processes_with_break_lock_over_a_stale_file_of_another_host_never_hold_the_lock_together(self):
        """Gaps 3 and 4: eight processes, every one with `--break-lock`, over a stale file that says another host. No window, no two owners, no lost update."""
        with tempfile.TemporaryDirectory() as shared, tempfile.TemporaryDirectory() as directory:
            Path(shared, 'counter').write_text('0', encoding='utf-8')
            Path(directory, 'deployment.lock').write_text(json.dumps({'pid': 4242, 'host': 'some-other-machine', 'started_at': OWNER_TIME, 'project': 'p', 'token': 'old'}), encoding='utf-8')
            children = [subprocess.Popen([sys.executable, '-c', COMPETE, str(SCRIPT), directory, shared, 'break']) for _ in range(8)]
            codes = [child.wait(timeout=120) for child in children]
            self.assertEqual(codes, [0] * 8, 'a 3 is a process that never got the lock, a 4 two owners at once')
            self.assertEqual(Path(shared, 'counter').read_text(encoding='utf-8'), '8')
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

    def test_ctrl_c_releases_the_lock_and_main_ends_with_130(self):
        """Fix3 (gap 2): Ctrl-C is no longer a traceback: the report is saved as `interrupted` (see test_deploy_rollback) and the exit code is the conventional 130."""
        with workspace() as root:
            code, out, err, run = self.deploy_with(root, KeyboardInterrupt())
            self.assertEqual(code, 130)
            self.assertNotIn('Traceback', err)
            self.free(root)

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM'), 'needs signals')
    def test_sigterm_releases_the_lock_ends_with_143_and_puts_the_handlers_back(self):
        with workspace() as root:
            before = signal.getsignal(signal.SIGTERM)
            code, out, err, run = self.deploy_with(root, lambda: signal.raise_signal(signal.SIGTERM))
            self.assertEqual(code, 128 + signal.SIGTERM)
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
