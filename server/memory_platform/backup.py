"""Local copies of the database (C-01): a manifest next to every copy, an integrity check, and (T-36, T-37) encryption and retention.

Encryption (P-01): `age` for the PUBLIC recipients listed in MEMORY_BACKUP_RECIPIENTS_FILE. The server can encrypt but not decrypt: the private key never exists
on the host, in the repository or in an image. The manifest then describes the ciphertext (`sha256`, `bytes`), so a copy is verified without decrypting, and the
plain dump too (`content_sha256`), which is what the restore of a decrypted copy is compared with.

A copy is COMPLETE only when `<copy>` and `<copy>.json` both exist and the manifest describes the file as it is on disk. Both are written to a private
temporary directory next to the destination, hashed there and then renamed into place (the copy first, its manifest last), so a copy that stopped half way
never looks valid: it has no manifest at its final name and `verify-backup` refuses it.

The manifest is a checksum, not a signature: it detects a copy that was corrupted or truncated, not one whose file AND manifest were replaced together by someone
who can write to the directory (it has no MAC). Authenticity is the job of the encryption (only the holder of the private key can produce a ciphertext it opens)
and of keeping the directory out of reach.

With recipients the plain dump never touches the disk: `pg_dump` -> this process (counts and hashes it) -> `age` -> the partial file.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

try:
    import fcntl
except ImportError:  # Windows: no flock; the sweep then goes by age alone
    fcntl = None

MANIFEST_FORMAT = 2  # 2: the fingerprints are additive sums of row hashes (1: sorted-rows sha256, which could not be computed in one pass); a format-1 manifest is refused with its own code
MANIFEST_KEYS = {'format': int, 'file': str, 'sha256': str, 'bytes': int, 'content_sha256': str, 'content_bytes': int, 'schema_version': int,
                 'created_at': str, 'encrypted': bool, 'fingerprints': dict}
PG_DUMP_MAGIC = b'PGDMP'
AGE_MAGIC = b'age-encryption.org/v1'
HASH_BLOCK = 1 << 20
SHA256 = re.compile(r'[0-9a-f]{64}')
AGE_PRIVATE_PREFIX = 'AGE-SECRET' + '-KEY-'  # split so that this source does not trip the repository scan for private keys
COPY_NAME = re.compile(r'kairos-[a-z][a-z0-9]*-\d{8}T\d{6}(?:\d{6})?Z\.dump(?:\.age)?')  # the names this tool gives its copies; nothing else is ever pruned
FUTURE_TOLERANCE_SECONDS = 86400  # a manifest dated further ahead than this is not believed (a decoy would otherwise rank as the newest)
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z')
PARTIAL_PREFIX = '.kairos-partial-'
PARTIAL_MAX_AGE_SECONDS = 3600  # a partial directory untouched for this long belongs to a run that is gone
FINGERPRINT_MASK = (1 << 256) - 1  # the sum of the row hashes wraps at 2^256
LOCK_NAME = 'lock'  # inside a partial directory: the process that is writing the copy holds a flock on it for as long as it runs
FINGERPRINT_ITERSIZE = 200  # rows the server-side cursor brings per round trip


class BackupError(Exception):
    """An error of the copy commands with a stable `code` and a message that never carries a DSN, a password or the path of a key."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sha256_file(path):
    """(hex digest, bytes) of a regular file, read in blocks."""
    digest, size = hashlib.sha256(), 0
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(HASH_BLOCK), b''):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def manifest_path(copy):
    return copy.with_name(copy.name + '.json')


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def write_atomic(path, data, mode=0o600):
    """Write `data` to a hidden temporary file of the same directory and rename it over `path`: a reader sees the old file or the whole new one."""
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def encode_row(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def row_digest(text):
    """The sha256 of one canonically encoded row, as the whole number it spells (big endian)."""
    return int.from_bytes(hashlib.sha256(text.encode('utf-8')).digest(), 'big')


def table_digest(connection, table):
    """(rows, sum) of one table: the number of rows and the SUM, modulo 2^256, of the sha256 of every row's canonical encoding (a sorted-keys JSON line), as 64 hex digits.

    One pass over a server-side cursor, a few rows in memory whatever the table's size. The sum is over a MULTISET: it does not depend on the order the rows come in
    (a restored table is read in another physical order) and an exact duplicate counts as many times as it occurs. It detects a row altered, added or removed by accident;
    it is not a defence against someone who can compute the sum for rows of their choosing (the manifest has no MAC either).
    """
    from psycopg import sql
    query = sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t').format(sql.Identifier(table))
    total, rows = 0, 0
    with connection.cursor(name='kairos_fingerprint') as cursor:
        cursor.itersize = FINGERPRINT_ITERSIZE
        cursor.execute(query)
        for record in cursor:
            total = (total + row_digest(encode_row(record['value']))) & FINGERPRINT_MASK
            rows += 1
    return rows, format(total, '064x')


def table_fingerprints(connection):
    """Rows and additive sha256 sum of every table of the `memory` schema (provenance, grants, jobs, versions and tombstones included), one pass per table, constant memory."""
    result = {}
    tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
    for row in tables:
        rows, total = table_digest(connection, row['table_name'])
        result[row['table_name']] = {'rows': rows, 'sha256': total}
    return result


@contextmanager
def terminate_as_exit():
    """SIGTERM (`docker stop`, the deployment's timeout) raises SystemExit so the `finally` blocks run and no partial file is left behind."""
    def stop(number, frame):
        raise SystemExit(143)
    previous = None
    try:
        previous = signal.signal(signal.SIGTERM, stop)
    except ValueError:  # not the main thread: nothing to install
        pass
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def load_recipients(path):
    """The public recipients of an `age` recipients file (blank lines and `#` comments skipped), as a list of lines.

    `BackupError` `backup_recipients_invalid` for a file that cannot be read, lists no recipient or holds a PRIVATE key (that would put the key on the host,
    which P-01 forbids). The messages name the variable, never the path.
    """
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, ValueError):
        raise BackupError('backup_recipients_invalid', 'MEMORY_BACKUP_RECIPIENTS_FILE cannot be read') from None
    if AGE_PRIVATE_PREFIX in text:
        raise BackupError('backup_recipients_invalid', 'MEMORY_BACKUP_RECIPIENTS_FILE holds a private key; it must list public recipients only (the private key stays off the server)')
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('#')]
    if not lines:
        raise BackupError('backup_recipients_invalid', 'MEMORY_BACKUP_RECIPIENTS_FILE lists no recipient')
    return lines


def recipient_digests(recipients):
    """The sha256 of each recipient line, sorted: what a manifest records instead of the keys."""
    return sorted({hashlib.sha256(line.encode('utf-8')).hexdigest() for line in recipients})


def encryption_plan(recipients_file, require):
    """The recipients to encrypt for, or None for a plain copy. A configured file is always used (never skipped); with `require` and no file the copy is refused."""
    if recipients_file:
        recipients = load_recipients(recipients_file)
        if not shutil.which('age'):
            raise BackupError('backup_encryption_unavailable', 'MEMORY_BACKUP_RECIPIENTS_FILE is set but the age program is not installed here; refusing to write a copy in the clear')
        return recipients
    if require:
        raise BackupError('backup_encryption_required', 'MEMORY_BACKUP_REQUIRE_ENCRYPTION is set but MEMORY_BACKUP_RECIPIENTS_FILE names no recipients file; refusing to write a copy in the clear')
    return None


def encrypted_name(output, recipients):
    """The name the copy is published under: `<output>.age` when it is encrypted (unless it already ends in `.age`)."""
    return output.with_name(output.name + '.age') if recipients and not output.name.endswith('.age') else output


def fsync_path(path, directory=False):
    """Flush a file (or, on POSIX, a directory entry) to disk; where the platform cannot do it (a directory on Windows) it is a no-op."""
    try:
        descriptor = os.open(path, os.O_RDONLY | (getattr(os, 'O_DIRECTORY', 0) if directory else 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def hold_partial_lock(partial):
    """Take the exclusive flock of `partial`'s lock file (created here, never through a link) and return its descriptor, or None where flock does not exist.

    The process that writes a copy holds it from the moment its partial directory exists until it is gone, so `sweep_partials` can tell a live run from a dead one
    by trying the same lock: the kernel releases it when the holder exits, however it exits.
    """
    if fcntl is None:
        return None
    descriptor = os.open(Path(partial) / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def try_partial_lock(path):
    """(state, descriptor) of the lock file of the partial directory `path`: 'held' (a live run owns it), 'free' (we now hold it) or 'none' (no readable lock file)."""
    if fcntl is None:
        return 'none', None
    try:
        descriptor = os.open(os.path.join(path, LOCK_NAME), os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:  # missing, or a link (refused by O_NOFOLLOW), or unreadable
        return 'none', None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:  # BlockingIOError: somebody holds it
        os.close(descriptor)
        return 'held', None
    return 'free', descriptor


def sweep_partials(directory, *, now=None, max_age=PARTIAL_MAX_AGE_SECONDS):
    """Delete the `.kairos-partial-*` directories of `directory` that belong to a run that is gone; returns their names.

    A partial whose lock file is held by a live process (`hold_partial_lock`) is NEVER deleted, however old: a run that spends hours hashing or encrypting writes nothing
    into it meanwhile. One whose lock is free, or that has no readable lock file, is deleted only if it was also untouched for more than `max_age` seconds (the newest
    modification time of the directory and of what is inside), which covers a run that has created the directory but not yet taken the lock. A link or a file with
    that name is not one of ours and is left alone. Every swept name is announced on stderr: a leftover means a run ended badly.
    """
    swept = []
    moment = (now or datetime.now(timezone.utc)).timestamp()
    try:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda e: e.name)
    except OSError:
        return swept
    for entry in entries:
        if not entry.name.startswith(PARTIAL_PREFIX):
            continue
        descriptor = None
        try:
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
            state, descriptor = try_partial_lock(entry.path)
            if state == 'held':
                continue
            newest = entry.stat(follow_symlinks=False).st_mtime
            with os.scandir(entry.path) as inside:
                for child in inside:
                    newest = max(newest, child.stat(follow_symlinks=False).st_mtime)
            if moment - newest < max_age:
                continue
            shutil.rmtree(entry.path)
            swept.append(entry.name)
        except OSError:
            continue
        finally:
            if descriptor is not None:
                os.close(descriptor)
    if swept:
        print(f'warning: removed {len(swept)} orphan partial director{"y" if len(swept) == 1 else "ies"} left by a run that ended badly ({", ".join(swept)})', file=sys.stderr)
    return swept


def reap(children):
    """Kill and collect every child process still running; nothing here raises."""
    for child in children:
        try:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=30)
        except (OSError, subprocess.SubprocessError):  # already gone, or it did not die in time: nothing more can be done here
            pass
        for pipe in (child.stdin, child.stdout):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass


def encrypted_dump(environment, snapshot, recipients, target, workdir, children):
    """`pg_dump` -> this process -> `age` -> `target`: the plain dump exists only in the two pipes. Returns (content_sha256, content_bytes).

    The recipients go through a private copy so what was validated is what is used. Every process started is appended to `children`, so a caller that is interrupted
    can kill them. Error messages never carry what the processes print.
    """
    keys = workdir / 'recipients'
    keys.write_text('\n'.join(recipients) + '\n', encoding='utf-8')
    os.chmod(keys, 0o600)
    digest, size = hashlib.sha256(), 0
    with tempfile.TemporaryFile() as diagnostics:  # what the two programs print; never shown, never a pipe that could fill up and block them
        try:
            dump = subprocess.Popen(['pg_dump', '--dbname=service=memory', '--format=custom', '--no-owner', '--snapshot=' + snapshot],
                                    env=environment, stdout=subprocess.PIPE, stderr=diagnostics)
        except OSError:
            raise BackupError('backup_dump_unavailable', 'the pg_dump program could not be run') from None
        children.append(dump)
        try:
            cipher = subprocess.Popen(['age', '--encrypt', '-R', str(keys), '-o', str(target)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=diagnostics)
        except OSError:
            raise BackupError('backup_encryption_unavailable', 'the age program could not be run') from None
        children.append(cipher)
        try:
            for block in iter(lambda: dump.stdout.read(HASH_BLOCK), b''):
                digest.update(block)
                size += len(block)
                cipher.stdin.write(block)
        except BrokenPipeError:  # `age` stopped: its exit status says why, below
            pass
        finally:
            for pipe in (cipher.stdin, dump.stdout):
                try:
                    pipe.close()
                except OSError:
                    pass
        dump_status, cipher_status = dump.wait(), cipher.wait()
    if cipher_status:  # first: when `age` dies early `pg_dump` is left with a closed pipe (EPIPE) and fails too, and the cause is `age`
        raise BackupError('backup_encryption_failed', f'age failed to encrypt the copy (exit {cipher_status})')
    if dump_status:
        raise subprocess.CalledProcessError(dump_status, 'pg_dump')
    return digest.hexdigest(), size


def create_backup(store, output, *, environment, recipients=None):
    """`pg_dump` of the database (encrypted for `recipients`, if given), its manifest, both published atomically. Returns the report of the command.

    The manifest's fingerprints and the dump are taken from ONE exported snapshot, so a database that keeps being written to still yields a manifest the
    restored copy matches exactly. `environment` is the `pg_environment` of the DSN (a service file; the DSN is never an argument).

    A SIGTERM at any point (dump, hash, encryption, renames) stops the children, removes the partial directory and exits 143. With recipients nothing in the
    directory ever holds the plain dump. The `.kairos-partial-*` directories that older runs left behind (SIGKILL, power) are swept first.
    """
    final = output
    manifest_final = manifest_path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    swept = sweep_partials(final.parent)
    children = []
    with terminate_as_exit():
        partial = Path(tempfile.mkdtemp(prefix=PARTIAL_PREFIX, dir=final.parent))  # 0700, never at a name that looks like a copy
        lock = None
        try:
            lock = hold_partial_lock(partial)  # for the whole run: a sweep by another process skips this directory however long the hashing takes
            with store.transaction() as connection:
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                snapshot = connection.execute('SELECT pg_export_snapshot() AS snapshot').fetchone()['snapshot']
                version = connection.execute('SELECT coalesce(max(version), 0) AS version FROM memory.schema_versions').fetchone()['version']
                fingerprints = table_fingerprints(connection)
                if recipients:
                    published = partial / 'dump.age'
                    content_sha, content_bytes = encrypted_dump(environment, snapshot, recipients, published, partial, children)
                else:
                    published = partial / 'dump'
                    subprocess.run(['pg_dump', '--dbname=service=memory', '--format=custom', '--no-owner', '--snapshot=' + snapshot, '--file', str(published)],
                                   env=environment, check=True, capture_output=True)
            sha, size = sha256_file(published)
            if not recipients:
                content_sha, content_bytes = sha, size
            manifest = {'format': MANIFEST_FORMAT, 'file': final.name, 'sha256': sha, 'bytes': size, 'content_sha256': content_sha, 'content_bytes': content_bytes,
                        'schema_version': version, 'created_at': utc_now(), 'encrypted': bool(recipients), 'fingerprints': fingerprints}
            if recipients:
                manifest['recipients'] = recipient_digests(recipients)
            os.chmod(published, 0o600)
            fsync_path(published)
            write_atomic(partial / 'manifest', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'))
            os.replace(published, final)  # the copy first...
            os.replace(partial / 'manifest', manifest_final)  # ...its manifest last: until then the copy has none and is not valid
            fsync_path(final.parent, directory=True)
        finally:
            reap(children)
            shutil.rmtree(partial, ignore_errors=True)
            if lock is not None:
                os.close(lock)
    report = {'status': 'backed_up', 'path': str(final), 'bytes': size, 'sha256': sha, 'encrypted': manifest['encrypted'], 'schema_version': version,
              'created_at': manifest['created_at']}
    if swept:
        report['swept_partials'] = swept
    return report


def check_keep(keep):
    """`--keep` / MEMORY_BACKUP_KEEP: a whole number of 1 or more (a copy is always kept, so 0 would mean "delete the last one")."""
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
        raise BackupError('backup_keep_invalid', '--keep must be a whole number of 1 or more')
    return keep


def prune_backups(directory, keep, *, protect=None, now=None):
    """Delete the copies of `directory` beyond the `keep` newest VERIFIED ones; returns {keep, kept, deleted, skipped, ignored}.

    Only a regular file whose name is exactly one of this tool's (`COPY_NAME`) with a readable manifest is ever a candidate: a decoy, a link, a directory, a copy
    without manifest or with a malformed one, a half-written copy and a manifest dated in the future are skipped and left alone. The candidates are walked from the
    newest to the oldest and each is VERIFIED (sha256 against its manifest) until `keep` valid ones are found: a copy that does not verify is skipped and does not
    count. The older ones are then deleted WITHOUT hashing them again (they are this tool's own copies with a manifest; one whose size differs from its manifest's is
    left alone as truncated). `protect` (the copy just written) is always kept, counts as one of the `keep` and is not hashed again, so a clock that ran ahead
    cannot make the run delete the copy it has just made. Never leaves fewer than `keep` verified copies and never touches the newest one: it deletes oldest first,
    copy before manifest; a copy another run deleted meanwhile is simply gone; a deletion that fails is reported (`backup_prune_failed`) after the others were tried.
    Old `.kairos-partial-*` directories of killed runs are swept first (`swept_partials`). A second run finds nothing to delete.
    """
    keep = check_keep(keep)
    directory = Path(directory)
    now = now or datetime.now(timezone.utc)
    limit = (now + timedelta(seconds=FUTURE_TOLERANCE_SECONDS)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    swept = sweep_partials(directory, now=now)
    candidates, skipped, ignored = [], [], 0
    protect_name = Path(protect).name if protect else None
    with os.scandir(directory) as scan:
        entries = sorted(scan, key=lambda e: e.name)
    for entry in entries:
        if not COPY_NAME.fullmatch(entry.name):
            ignored += 1
            continue
        path = directory / entry.name
        try:
            if path.is_symlink() or not path.is_file():
                raise BackupError('backup_not_found', f'The copy {entry.name} is not a regular file')
            manifest = read_manifest(path)
            if manifest['created_at'] > limit:
                raise BackupError('backup_created_in_the_future', f'The manifest of {entry.name} is dated in the future')
        except BackupError as error:
            skipped.append({'name': entry.name, 'code': error.code})
            continue
        candidates.append((manifest['created_at'], entry.name, manifest))
    candidates.sort(key=lambda item: item[:2], reverse=True)  # newest first
    kept = [item for item in candidates if item[1] == protect_name]
    doomed = []
    for item in candidates:
        created_at, name, manifest = item
        if item in kept:
            continue
        if len(kept) < keep:
            try:
                verify_backup(directory / name)
            except FileNotFoundError:  # another `--prune` deleted it while this one verified it: it is gone and does not count; the next older copy is verified instead
                continue
            except BackupError as error:
                if not os.path.lexists(directory / name):  # the same race, whatever code `verify_backup` gave (not found, manifest missing): the copy is not there any more
                    continue
                skipped.append({'name': name, 'code': error.code})
                continue
            kept.append(item)
        else:
            try:
                size = (directory / name).stat().st_size
            except FileNotFoundError:  # another run deleted it meanwhile: it is gone, which is what was wanted
                continue
            if size != manifest['bytes']:
                skipped.append({'name': name, 'code': 'backup_checksum_mismatch'})
            else:
                doomed.append(item)
    kept.sort(key=lambda item: item[:2], reverse=True)
    deleted, failed = [], []
    for created_at, name, manifest in reversed(doomed):  # oldest first
        try:
            for victim in (directory / name, manifest_path(directory / name)):
                try:
                    os.unlink(victim)
                except FileNotFoundError:  # another run deleted it meanwhile: it is gone, which is what was wanted
                    pass
            deleted.append(name)
        except OSError:
            failed.append(name)
    deleted.reverse()  # newest first, like `kept`
    if failed:
        raise BackupError('backup_prune_failed', f'{len(failed)} old cop{"y" if len(failed) == 1 else "ies"} could not be deleted ({", ".join(failed)}); {len(deleted)} deleted')
    report = {'keep': keep, 'kept': [{'name': name, 'created_at': created_at} for created_at, name, manifest in kept], 'deleted': deleted, 'skipped': skipped, 'ignored': ignored}
    if swept:
        report['swept_partials'] = swept
    return report


def read_manifest(copy, explicit=None):
    """The manifest of `copy` (`<copy>.json`, or the file `explicit`), checked for shape; `BackupError` `backup_manifest_missing` / `backup_manifest_invalid` otherwise.

    An explicit manifest belongs to ANOTHER file than `copy` (the ciphertext, when `copy` is its decrypted dump), so the name inside it is not compared.
    """
    path = Path(explicit) if explicit else manifest_path(copy)
    try:
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError
        if path.stat().st_size > 16 * HASH_BLOCK:
            raise ValueError
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise BackupError('backup_manifest_missing', f'The copy {copy.name} has no manifest ({path.name}); it is not a complete copy') from None
    except (OSError, ValueError):
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} cannot be read as JSON') from None
    if isinstance(manifest, dict) and type(manifest.get('format')) is int and manifest['format'] < MANIFEST_FORMAT:
        raise BackupError('backup_manifest_format_unsupported', f"The manifest {path.name} is format {manifest['format']}; this tool reads format {MANIFEST_FORMAT} (its fingerprints were computed another way): "
                          'make a new copy, copies of the old format cannot be checked against their tables')
    if not isinstance(manifest, dict) or any(type(manifest.get(key)) is not kind for key, kind in MANIFEST_KEYS.items()) or manifest['format'] != MANIFEST_FORMAT:
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} is not a version {MANIFEST_FORMAT} manifest of this tool')
    recipients = manifest.get('recipients')
    if manifest['encrypted'] and (not isinstance(recipients, list) or not recipients or any(not isinstance(r, str) or not SHA256.fullmatch(r) for r in recipients)):
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} of an encrypted copy lists no valid recipients')
    if ((manifest['file'] != copy.name and not explicit) or not SHA256.fullmatch(manifest['sha256']) or not SHA256.fullmatch(manifest['content_sha256'])
            or manifest['bytes'] < 0 or manifest['content_bytes'] < 0 or not TIMESTAMP.fullmatch(manifest['created_at'])):
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} does not describe the file {copy.name}')
    return manifest


def verify_backup(copy, recipients_file=None, manifest_file=None):
    """Recompute the sha256 of the copy as it is on disk and compare it with its manifest. Never decrypts. Returns the manifest plus `verified`: 'copy' or 'content'.

    With `recipients_file` (MEMORY_BACKUP_RECIPIENTS_FILE) an encrypted copy must also have been encrypted for at least one of its recipients (`backup_recipients_mismatch`):
    that is how a copy made for some other key is told. It is the manifest's claim, not a proof (only the private key proves it).

    With `manifest_file` (the manifest of a ciphertext) and a PLAIN dump, the dump is the decrypted copy: its sha256 and size are compared with the manifest's
    `content_sha256` and `content_bytes` (`verified` is 'content'). That is how a copy that was encrypted, decrypted and restored is tied to what the backup recorded.

    `backup_checksum_mismatch` for any difference of content or size (a truncated copy says so); `backup_manifest_*` for a missing or malformed manifest;
    `backup_not_found` for a copy that is not a regular file (a symbolic link is refused).
    """
    copy = Path(copy)
    if copy.is_symlink() or not copy.is_file():
        raise BackupError('backup_not_found', f'The copy {copy.name} is not a regular file')
    manifest = read_manifest(copy, manifest_file)
    with open(copy, 'rb') as handle:
        head = handle.read(len(AGE_MAGIC))
    if manifest_file and manifest['encrypted'] and head.startswith(PG_DUMP_MAGIC):
        sha, size = sha256_file(copy)
        if size != manifest['content_bytes']:
            raise BackupError('backup_checksum_mismatch', f"The decrypted copy {copy.name} has {size} bytes but its manifest says {manifest['content_bytes']}"
                              + (' (truncated)' if size < manifest['content_bytes'] else ''))
        if sha != manifest['content_sha256']:
            raise BackupError('backup_checksum_mismatch', f'The sha256 of the decrypted copy {copy.name} does not match the content_sha256 of its manifest')
        return dict(manifest, verified='content')
    if manifest['encrypted'] != head.startswith(AGE_MAGIC) or (not manifest['encrypted'] and not head.startswith(PG_DUMP_MAGIC)):
        raise BackupError('backup_manifest_invalid', f"The manifest says encrypted={str(manifest['encrypted']).lower()} but the file {copy.name} is not")
    sha, size = sha256_file(copy)
    if size != manifest['bytes']:
        raise BackupError('backup_checksum_mismatch', f"The copy {copy.name} has {size} bytes but its manifest says {manifest['bytes']}"
                          + (' (truncated)' if size < manifest['bytes'] else ''))
    if sha != manifest['sha256']:
        raise BackupError('backup_checksum_mismatch', f'The sha256 of the copy {copy.name} does not match its manifest')
    if manifest['encrypted'] and recipients_file:
        if not set(manifest['recipients']) & set(recipient_digests(load_recipients(recipients_file))):
            raise BackupError('backup_recipients_mismatch', f'The copy {copy.name} was encrypted for other recipients than MEMORY_BACKUP_RECIPIENTS_FILE lists')
    return dict(manifest, verified='copy')
