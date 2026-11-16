"""The external copy (C-01, P-02): `backup-cycle` makes a copy, verifies it, sends it to a destination, verifies it THERE and applies the retention of both places.

Destinations: `dir:<absolute path>` (a mounted directory) and `rclone:<remote>:<path>` (a remote of the operator's rclone configuration). Both implement the same few
operations (`names`, `put`, `fetch`, `digest`, `delete`) and fail with `OffsiteError`, whose text never carries what the destination or `rclone` printed: it could hold
a URL, a token or a path.

Nothing leaves the server in the clear: only copies whose manifest says `encrypted` AND whose file starts with the `age` header are ever sent; a plain copy that matches the
name of this tool (the `kairos-before-*` of a deployment, one made by hand) is left where it is and reported as `skipped_plain`. The destination should belong to ONE installation:
the retention deletes by the manifests it finds there.

The order is the safety. A copy goes up first and its manifest last (a remote copy without manifest is not complete and is sent again); the sha256 of what the destination
now holds is read back and compared with the manifest BEFORE the manifest goes up and before anything is deleted anywhere. A copy whose bytes differ at the destination is
never completed with its manifest and nothing is deleted, locally or remotely. When the destination cannot be reached nothing local is deleted either (a copy that never
left must not be pruned), the result is logged as `backup_offsite_failed`, `kairos_backup_offsite_success` goes to 0 and the next cycle sends again every copy the destination lacks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from .backup import (AGE_MAGIC, BackupError, COPY_NAME, FUTURE_TOLERANCE_SECONDS, HASH_BLOCK, manifest_path, prune_backups, read_manifest, sha256_file, terminate_as_exit, verify_backup,
                     write_atomic)
from . import observability

UPLOAD_PREFIX = '.kairos-upload-'  # a half-sent file at a `dir:` destination: never at a name that looks like a copy
UPLOAD_MAX_AGE_SECONDS = 3600
RCLONE_TIMEOUT_SECONDS = 6 * 3600  # one transfer; rclone's own --timeout ends a stalled one sooner
RCLONE_SHORT_TIMEOUT_SECONDS = 300  # listing, deleting
RCLONE_FLAGS = ('--contimeout', '30s', '--timeout', '120s', '--retries', '2', '--low-level-retries', '3', '--ask-password=false')
RCLONE_REMOTE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*:[^\x00-\x1f]*')  # `<remote>:<path>`: never a connection string (`:backend:`) and never something that starts like an option
METRICS_NAME = 'kairos-offsite.prom'  # next to the local copies; a textfile collector reads it
CYCLE_KIND = 'cycle'


class OffsiteError(Exception):
    """The destination could not be read or written. The message names the kind of destination and never anything it printed."""


class CycleError(BackupError):
    """A `backup-cycle` that stopped after the local copy existed: `report` says what was done (and is printed by the command).

    Its metric is already written (0 when the copy did not reach the destination, 1 when only the local retention failed): `offsite_recorded` tells the caller not to write it again.
    """
    offsite_recorded = True

    def __init__(self, code, message, report):
        super().__init__(code, message)
        self.report = report


class DirDestination:
    kind = 'dir'

    def __init__(self, path):
        self.root = Path(path)

    def names(self):
        try:
            with os.scandir(self.root) as scan:
                return {entry.name for entry in scan if entry.is_file(follow_symlinks=False)}
        except OSError:
            raise OffsiteError('the dir destination cannot be read') from None

    def sweep(self, now=None):
        """Delete the half-sent files (`.kairos-upload-*`, older than an hour) a killed run left; nothing else is ever deleted here."""
        moment = time.time() if now is None else now
        try:
            with os.scandir(self.root) as scan:
                for entry in scan:
                    if entry.name.startswith(UPLOAD_PREFIX) and entry.is_file(follow_symlinks=False) and moment - entry.stat(follow_symlinks=False).st_mtime > UPLOAD_MAX_AGE_SECONDS:
                        os.unlink(entry.path)
        except OSError:
            pass

    def put(self, source, name):
        """Store what the open file `source` holds (read from where it is) under `name`: the caller checked THAT descriptor, a path is never reopened here."""
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=UPLOAD_PREFIX, dir=self.root)
            try:
                with os.fdopen(descriptor, 'wb') as out:
                    shutil.copyfileobj(source, out, HASH_BLOCK)
                    out.flush()
                    os.fsync(out.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.root / name)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise
        except OSError:
            raise OffsiteError('the dir destination cannot be written') from None

    def fetch(self, name, directory):
        try:
            target = Path(directory) / name
            shutil.copyfile(self.root / name, target)
            return target
        except OSError:
            raise OffsiteError('the dir destination cannot be read') from None

    def digest(self, name):
        path = self.root / name
        try:
            if path.is_symlink():
                raise OSError
            return sha256_file(path)
        except OSError:
            raise OffsiteError('the dir destination cannot be read') from None

    def delete(self, name):
        try:
            (self.root / name).unlink(missing_ok=True)
        except OSError:
            raise OffsiteError('the dir destination cannot be written') from None


class RcloneDestination:
    kind = 'rclone'

    def __init__(self, remote):
        self.remote = remote

    def target(self, name):
        return self.remote + name if self.remote.endswith((':', '/')) else self.remote + '/' + name

    def run(self, *args, timeout=RCLONE_SHORT_TIMEOUT_SECONDS, capture=False, stdin=subprocess.DEVNULL):
        """One `rclone` command: its output is returned only when `capture` (a listing) and its diagnostics are never kept."""
        try:
            result = subprocess.run(['rclone', *RCLONE_FLAGS, *args], stdin=stdin, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=timeout)
        except FileNotFoundError:
            raise OffsiteError('the rclone program is not installed here') from None
        except (OSError, subprocess.SubprocessError):
            raise OffsiteError('the rclone destination cannot be reached (rclone failed to run or timed out)') from None
        if result.returncode:
            raise OffsiteError(f'the rclone destination cannot be reached or written (rclone exit {result.returncode})')
        return result.stdout.decode('utf-8', 'replace') if capture else None

    def names(self):
        return {line for line in self.run('lsf', '--files-only', self.remote, capture=True).splitlines() if line}

    def put(self, source, name):
        """`rclone rcat` of the open file `source` through its descriptor (its stdin): rclone never opens a path the copy could have been swapped at."""
        self.run('rcat', self.target(name), timeout=RCLONE_TIMEOUT_SECONDS, stdin=source)

    def fetch(self, name, directory):
        target = Path(directory) / name
        self.run('copyto', self.target(name), str(target), timeout=RCLONE_TIMEOUT_SECONDS)
        return target

    def digest(self, name):
        """(sha256, bytes) of what the remote holds, by reading it back (`rclone cat`): every backend can do it, a hash listing is not offered by all of them."""
        digest, size = hashlib.sha256(), 0
        try:
            child = subprocess.Popen(['rclone', *RCLONE_FLAGS, 'cat', self.target(name)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise OffsiteError('the rclone program is not installed here') from None
        except OSError:
            raise OffsiteError('the rclone destination cannot be reached (rclone failed to run)') from None
        try:
            for block in iter(lambda: child.stdout.read(HASH_BLOCK), b''):
                digest.update(block)
                size += len(block)
            status = child.wait(timeout=RCLONE_SHORT_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            raise OffsiteError('the rclone destination cannot be read') from None
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child.stdout.close()
        if status:
            raise OffsiteError(f'the rclone destination cannot be read (rclone exit {status})')
        return digest.hexdigest(), size

    def delete(self, name):
        self.run('deletefile', self.target(name))


def parse_destination(spec):
    """The destination of MEMORY_BACKUP_DESTINATION: `dir:<absolute path>` or `rclone:<remote>:<path>`. `BackupError` `backup_destination_invalid` otherwise; the message never echoes the value."""
    text = (spec or '').strip()
    if text.startswith('dir:'):
        path = text[4:]
        if not path or '\x00' in path or not (os.path.isabs(path) or path.startswith('/')):
            raise BackupError('backup_destination_invalid', 'MEMORY_BACKUP_DESTINATION dir: needs an absolute path (dir:/path)')
        return DirDestination(path)
    if text.startswith('rclone:'):
        remote = text[7:]
        if not RCLONE_REMOTE.fullmatch(remote):
            raise BackupError('backup_destination_invalid', 'MEMORY_BACKUP_DESTINATION rclone: needs a remote of the rclone configuration and a path (rclone:<remote>:<path>)')
        return RcloneDestination(remote)
    raise BackupError('backup_destination_invalid', 'MEMORY_BACKUP_DESTINATION must be dir:<absolute path> or rclone:<remote>:<path>' if text else 'MEMORY_BACKUP_DESTINATION is not set')


def cycle_name(now=None):
    """The name a cycle gives its copy: `kairos-cycle-<UTC time to the microsecond>Z.dump` (an encrypted copy gets `.age` from the command)."""
    return f'kairos-{CYCLE_KIND}-{(now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")}.dump'


def has_age_header(path):
    with open(path, 'rb') as handle:
        return handle.read(len(AGE_MAGIC)).startswith(AGE_MAGIC)


def open_regular(path):
    """Open `path` for reading ONCE, never through a link: the descriptor that is checked is the one that is uploaded (CWE-367). `BackupError` `backup_not_found` when it is a link or not a regular file."""
    path = Path(path)
    try:
        if not hasattr(os, 'O_NOFOLLOW') and path.is_symlink():  # a platform without O_NOFOLLOW (the service runs on Linux)
            raise OSError
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    except OSError:
        raise BackupError('backup_not_found', f'The copy {path.name} is not a regular file') from None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise BackupError('backup_not_found', f'The copy {path.name} is not a regular file')
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def open_encrypted_copy(path, manifest):
    """The copy as an open file at its start, after checking ON THAT DESCRIPTOR that it begins with the `age` header and that its sha256 and size are the manifest's.

    Nothing in the clear can be sent through it: a link, a replaced file or a changed one fails here (`backup_not_found`, `backup_encryption_required`, `backup_checksum_mismatch`).
    """
    handle = open_regular(path)
    try:
        if not handle.read(len(AGE_MAGIC)).startswith(AGE_MAGIC):
            raise BackupError('backup_encryption_required', f'The copy {Path(path).name} does not begin with the age header; it was not sent')
        handle.seek(0)
        digest, size = hashlib.sha256(), 0
        for block in iter(lambda: handle.read(HASH_BLOCK), b''):
            digest.update(block)
            size += len(block)
        if digest.hexdigest() != manifest['sha256'] or size != manifest['bytes']:
            raise BackupError('backup_checksum_mismatch', f'The copy {Path(path).name} changed after it was verified; it was not sent')
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


def open_manifest(path, name, manifest):
    """The manifest of `name` as an open file at its start, read once from a descriptor opened without following links; it must say what the verified manifest says (`backup_manifest_invalid` otherwise)."""
    handle = open_regular(path)
    try:
        sent = json.loads(handle.read(16 * HASH_BLOCK + 1).decode('utf-8'))
        if not isinstance(sent, dict) or any(sent.get(key) != manifest[key] for key in ('file', 'sha256', 'bytes', 'created_at')) or sent['file'] != name:
            raise BackupError('backup_manifest_invalid', f'The manifest of {name} changed after it was verified; it was not sent')
        handle.seek(0)
        return handle
    except BaseException as error:
        handle.close()
        if isinstance(error, (ValueError, UnicodeDecodeError)):
            raise BackupError('backup_manifest_invalid', f'The manifest of {name} cannot be read as JSON; it was not sent') from None
        raise


def local_copies(directory, remote_keep, now):
    """The complete, readable ENCRYPTED copies of this tool in `directory` (newest first, at most `remote_keep`), as (created_at, name, manifest), and the names of the plain ones.

    A copy is encrypted only when its manifest says `encrypted` and the file starts with the `age` header; anything else with a valid manifest is plain and is never a candidate.
    """
    limit = (now + timedelta(seconds=FUTURE_TOLERANCE_SECONDS)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    found, plain = [], []
    with os.scandir(directory) as scan:
        names = sorted(entry.name for entry in scan if COPY_NAME.fullmatch(entry.name))
    for name in names:
        path = Path(directory) / name
        try:
            if path.is_symlink() or not path.is_file():
                continue
            manifest = read_manifest(path)
            encrypted = manifest['encrypted'] is True and has_age_header(path)
        except (BackupError, OSError):
            continue
        if manifest['created_at'] <= limit:
            if encrypted:
                found.append((manifest['created_at'], name, manifest))
            else:
                plain.append(name)
    found.sort(key=lambda item: item[:2], reverse=True)
    return found[:remote_keep], sorted(plain)


def remote_is_complete(destination, name, manifest, scratch):
    """The destination holds a manifest of `name` that parses, is this tool's and records the sha256 and size of the local copy (a manifest cut short by a failed transfer does not)."""
    target = Path(scratch) / (name + '.json')
    target.unlink(missing_ok=True)
    try:
        destination.fetch(name + '.json', scratch)
        remote = read_manifest(Path(scratch) / name)
    except (OffsiteError, BackupError, OSError):
        return False
    return remote['sha256'] == manifest['sha256'] and remote['bytes'] == manifest['bytes']


def upload(destination, directory, current, remote_keep, recipients_file, now):
    """Send `current` and every other recent ENCRYPTED local copy the destination lacks (newest first); each one is read back and compared with its manifest before its manifest goes up.

    Returns {uploaded, skipped, skipped_plain}. `current` was verified by the caller. An older copy that no longer verifies locally is skipped (and said so), never sent; a plain copy is
    never sent (`skipped_plain`). A copy already at the destination is left alone only when its remote manifest parses and records the sha256 and size of the local copy; otherwise copy and
    manifest are sent again. A copy that differs at the destination raises `backup_checksum_mismatch` with its manifest NOT sent and nothing deleted.
    """
    remote = destination.names()
    uploaded, skipped = [], []
    copies, plain = local_copies(directory, remote_keep, now)
    with tempfile.TemporaryDirectory(prefix='kairos-offsite-') as scratch:
        for created_at, name, manifest in copies:
            if name in remote and name + '.json' in remote and remote_is_complete(destination, name, manifest, scratch):
                continue
            path = Path(directory) / name
            if name != current:
                try:
                    verify_backup(path, recipients_file)
                except BackupError as error:
                    skipped.append({'name': name, 'code': error.code})
                    continue
            try:
                handle = open_encrypted_copy(path, manifest)  # the header and the sha256 are checked on the descriptor that is uploaded
            except BackupError as error:
                skipped.append({'name': name, 'code': error.code})
                continue
            with handle:
                destination.put(handle, name)
            sha, size = destination.digest(name)
            if sha != manifest['sha256'] or size != manifest['bytes']:
                raise BackupError('backup_checksum_mismatch', f'The copy {name} differs at the {destination.kind} destination from its manifest; its manifest was not sent and nothing was deleted')
            try:
                handle = open_manifest(manifest_path(path), name, manifest)
            except BackupError as error:  # the copy is up without its manifest: it is not complete there and the next cycle sends it again
                skipped.append({'name': name, 'code': error.code})
                continue
            with handle:
                destination.put(handle, name + '.json')
            uploaded.append(name)
    return {'uploaded': uploaded, 'skipped': skipped, 'skipped_plain': plain}


def prune_remote(destination, keep, protect, now):
    """Delete from the destination the copies beyond the `keep` newest (by the `created_at` of their manifests); `protect` (verified at the destination a moment ago) is always kept.

    Only names of this tool with a manifest that reads are candidates; anything else is left alone. A copy NEWER than `protect` is never deleted (another installation or a concurrent
    cycle sent it: the destination is meant to be exclusive, but a newer copy is not ours to judge) and counts among the kept. Oldest first, the copy before its manifest.
    Returns {kept, deleted, skipped}.
    """
    limit = (now + timedelta(seconds=FUTURE_TOLERANCE_SECONDS)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    names = destination.names()
    candidates, skipped = [], []
    with tempfile.TemporaryDirectory(prefix='kairos-offsite-') as scratch:
        for name in sorted(n for n in names if COPY_NAME.fullmatch(n) and n + '.json' in names):
            try:
                destination.fetch(name + '.json', scratch)
                manifest = read_manifest(Path(scratch) / name)
                if manifest['created_at'] > limit:
                    raise BackupError('backup_created_in_the_future', f'The manifest of {name} is dated in the future')
            except BackupError as error:
                skipped.append({'name': name, 'code': error.code})
                continue
            candidates.append((manifest['created_at'], name))
    candidates.sort(reverse=True)
    if protect not in {name for created_at, name in candidates}:
        raise BackupError('backup_offsite_failed', f'The copy just sent is not complete at the {destination.kind} destination; nothing was deleted there')
    protected = next(item for item in candidates if item[1] == protect)
    kept = [item for item in candidates if item >= protected]  # the protected copy and everything newer than it
    doomed = []
    for item in candidates:
        if item >= protected:
            continue
        if len(kept) < keep:
            kept.append(item)
        else:
            doomed.append(item)
    deleted = []
    for created_at, name in reversed(doomed):
        destination.delete(name)
        destination.delete(name + '.json')
        deleted.append(name)
    return {'kept': len(kept), 'deleted': sorted(deleted, reverse=True), 'skipped': skipped}


def write_metrics(directory):
    """The two offsite series as a file next to the copies; a failure to write it is not a failure of the cycle."""
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        write_atomic(Path(directory) / METRICS_NAME, observability.render_offsite_metrics(), 0o644)
    except OSError:
        pass


def record_failure(directory, error=None):
    """A cycle that failed at any stage: `kairos_backup_offsite_success` 0, the time of the attempt, the `.prom` file rewritten. `error` is marked so that nobody records it twice."""
    observability.record_offsite(False)
    write_metrics(directory)
    if error is not None:
        error.offsite_recorded = True


def run_cycle(make_copy, directory, destination, *, keep, remote_keep, recipients_file=None, now=None):
    """One cycle: local copy -> verify -> send -> verify there -> remote retention -> local retention. Returns the report; raises `CycleError` (with the report) when it stopped.

    `make_copy(output)` writes the copy and its manifest (`create_backup`) and returns its report; `output` is the plain name, the copy may get `.age`. A copy that does not verify
    locally raises its own code and is never sent. A failure of the offsite stage logs `backup_offsite_failed`, sets the metric to 0 and keeps every local copy.
    """
    directory = Path(directory)
    now = now or datetime.now(timezone.utc)
    with terminate_as_exit():
        try:
            if isinstance(destination, DirDestination) and destination.root.resolve() == directory.resolve():
                raise BackupError('backup_destination_invalid', 'MEMORY_BACKUP_DESTINATION is the directory of the local copies; the external copy must be somewhere else')
            report = make_copy(directory / cycle_name(now))
            copy = Path(report['path'])
            if verify_backup(copy, recipients_file)['encrypted'] is not True:
                raise BackupError('backup_encryption_required', f'The copy {copy.name} is not encrypted; the external destination only receives encrypted copies and nothing was sent')
        except Exception as error:  # the cycle failed before the offsite stage (the database, pg_dump, the encryption, the local check): the metric says so too
            record_failure(directory, error)
            raise
        if isinstance(destination, DirDestination):
            destination.sweep()
        try:
            offsite = upload(destination, directory, copy.name, remote_keep, recipients_file, now)
            remote = prune_remote(destination, remote_keep, copy.name, now)
            offsite.update(destination=destination.kind, kept=remote['kept'], deleted=remote['deleted'], remote_skipped=remote['skipped'])
        except (OffsiteError, BackupError) as error:
            code = error.code if isinstance(error, BackupError) else 'backup_offsite_failed'
            observability.log_event('backup_offsite_failed', 'error', destination=destination.kind, code=code)
            record_failure(directory)
            report['offsite'] = {'destination': destination.kind, 'status': 'failed', 'code': code}
            raise CycleError(code, str(error) if isinstance(error, BackupError) else f'the {destination.kind} destination failed ({error}); the copy is kept locally and the next cycle sends it again', report) from None
        except Exception as error:  # anything else of the offsite stage (the local listing): the copy did not leave, the metric says so
            record_failure(directory, error)
            raise
        if offsite['skipped_plain']:
            observability.log_event('backup_offsite_plain_skipped', 'warning', destination=destination.kind, count=len(offsite['skipped_plain']))
        observability.record_offsite(True)
        write_metrics(directory)
        report['offsite'] = dict(offsite, status='verified')
        try:
            report['prune'] = prune_backups(directory, keep, protect=copy, now=now)
        except (BackupError, OSError) as error:  # the copy exists and is at the destination: its report is printed whatever stopped the local retention
            code = error.code if isinstance(error, BackupError) else 'backup_prune_failed'
            observability.log_event('backup_cycle_failed', 'error', exc_type=type(error).__name__, code=code)  # the report is printed, but the cycle failed: the event of every other failed cycle
            report['prune'] = {'status': 'failed', 'code': code}
            raise CycleError(code, str(error) if isinstance(error, BackupError) else f'the local retention failed ({type(error).__name__})', report) from None
    return report


def run_loop(cycle, interval, *, sleep=None, cycles=None, out=print):
    """`cycle()` every `interval` seconds, for ever (or `cycles` times): a cycle that fails is reported (its code, never a message that could carry a secret) and the next one retries.

    Only SystemExit and KeyboardInterrupt (a stop of the service) end the loop.
    """
    done = 0
    while cycles is None or done < cycles:
        done += 1
        try:
            out(json.dumps(cycle(), sort_keys=True))
        except CycleError as error:
            out(json.dumps(error.report, sort_keys=True))
            print(f'{error.code}: {error}', file=sys.stderr, flush=True)
        except BackupError as error:
            observability.log_event('backup_cycle_failed', 'error', exc_type=type(error).__name__, code=error.code)
            print(f'{error.code}: {error}', file=sys.stderr, flush=True)
        except Exception as error:
            observability.log_failure('backup_cycle_failed', error)
            print(f'backup_cycle_failed: the cycle failed ({type(error).__name__}); the next one retries', file=sys.stderr, flush=True)
        if cycles is None or done < cycles:
            (sleep or time.sleep)(interval)
