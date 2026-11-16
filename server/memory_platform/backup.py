"""Local copies of the database (C-01): a manifest next to every copy, an integrity check, and (T-36, T-37) encryption and retention.

A copy is COMPLETE only when `<copy>` and `<copy>.json` both exist and the manifest describes the file as it is on disk. Both are written to a private
temporary directory next to the destination, hashed there and then renamed into place (the copy first, its manifest last), so a copy that stopped half way
never looks valid: it has no manifest at its final name and `verify-backup` refuses it.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

MANIFEST_FORMAT = 1
MANIFEST_KEYS = {'format': int, 'file': str, 'sha256': str, 'bytes': int, 'content_sha256': str, 'content_bytes': int, 'schema_version': int,
                 'created_at': str, 'encrypted': bool, 'fingerprints': dict}
PG_DUMP_MAGIC = b'PGDMP'
AGE_MAGIC = b'age-encryption.org/v1'
HASH_BLOCK = 1 << 20
SHA256 = re.compile(r'[0-9a-f]{64}')
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z')


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


def table_fingerprints(connection):
    """Rows and sha256 of every table of the `memory` schema (provenance, grants, jobs, versions and tombstones included)."""
    from psycopg import sql
    result = {}
    tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
    for row in tables:
        values = connection.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t').format(sql.Identifier(row['table_name']))).fetchall()
        encoded = sorted(json.dumps(v['value'], sort_keys=True, ensure_ascii=False, default=str) for v in values)
        result[row['table_name']] = {'rows': len(encoded), 'sha256': hashlib.sha256('\n'.join(encoded).encode('utf-8')).hexdigest()}
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


def create_backup(store, output, *, environment):
    """`pg_dump` of the database, its manifest, both published atomically. Returns the report of the command.

    The manifest's fingerprints and the dump are taken from ONE exported snapshot, so a database that keeps being written to still yields a manifest the
    restored copy matches exactly. `environment` is the `pg_environment` of the DSN (a service file; the DSN is never an argument).
    """
    final = output
    manifest_final = manifest_path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(prefix='.kairos-partial-', dir=final.parent))  # 0700, never at a name that looks like a copy
    try:
        with terminate_as_exit(), store.transaction() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            snapshot = connection.execute('SELECT pg_export_snapshot() AS snapshot').fetchone()['snapshot']
            version = connection.execute('SELECT coalesce(max(version), 0) AS version FROM memory.schema_versions').fetchone()['version']
            fingerprints = table_fingerprints(connection)
            dump = partial / 'dump'
            subprocess.run(['pg_dump', '--dbname=service=memory', '--format=custom', '--no-owner', '--snapshot=' + snapshot, '--file', str(dump)],
                           env=environment, check=True, capture_output=True)
        content_sha, content_bytes = sha256_file(dump)
        published = dump
        sha, size = content_sha, content_bytes
        manifest = {'format': MANIFEST_FORMAT, 'file': final.name, 'sha256': sha, 'bytes': size, 'content_sha256': content_sha, 'content_bytes': content_bytes,
                    'schema_version': version, 'created_at': utc_now(), 'encrypted': False, 'fingerprints': fingerprints}
        os.chmod(published, 0o600)
        write_atomic(partial / 'manifest', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'))
        os.replace(published, final)  # the copy first...
        os.replace(partial / 'manifest', manifest_final)  # ...its manifest last: until then the copy has none and is not valid
    finally:
        shutil.rmtree(partial, ignore_errors=True)
    return {'status': 'backed_up', 'path': str(final), 'bytes': size, 'sha256': sha, 'encrypted': manifest['encrypted'], 'schema_version': version,
            'created_at': manifest['created_at']}


def read_manifest(copy):
    """The manifest of `copy`, checked for shape; `BackupError` `backup_manifest_missing` / `backup_manifest_invalid` otherwise."""
    path = manifest_path(copy)
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
    if not isinstance(manifest, dict) or any(type(manifest.get(key)) is not kind for key, kind in MANIFEST_KEYS.items()) or manifest['format'] != MANIFEST_FORMAT:
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} is not a version {MANIFEST_FORMAT} manifest of this tool')
    if (manifest['file'] != copy.name or not SHA256.fullmatch(manifest['sha256']) or not SHA256.fullmatch(manifest['content_sha256'])
            or manifest['bytes'] < 0 or manifest['content_bytes'] < 0 or not TIMESTAMP.fullmatch(manifest['created_at'])):
        raise BackupError('backup_manifest_invalid', f'The manifest {path.name} does not describe the file {copy.name}')
    return manifest


def verify_backup(copy):
    """Recompute the sha256 of the copy as it is on disk and compare it with its manifest. Never decrypts. Returns the manifest.

    `backup_checksum_mismatch` for any difference of content or size (a truncated copy says so); `backup_manifest_*` for a missing or malformed manifest;
    `backup_not_found` for a copy that is not a regular file (a symbolic link is refused).
    """
    copy = Path(copy)
    if copy.is_symlink() or not copy.is_file():
        raise BackupError('backup_not_found', f'The copy {copy.name} is not a regular file')
    manifest = read_manifest(copy)
    with open(copy, 'rb') as handle:
        head = handle.read(len(AGE_MAGIC))
    if manifest['encrypted'] != head.startswith(AGE_MAGIC) or (not manifest['encrypted'] and not head.startswith(PG_DUMP_MAGIC)):
        raise BackupError('backup_manifest_invalid', f"The manifest says encrypted={str(manifest['encrypted']).lower()} but the file {copy.name} is not")
    sha, size = sha256_file(copy)
    if size != manifest['bytes']:
        raise BackupError('backup_checksum_mismatch', f"The copy {copy.name} has {size} bytes but its manifest says {manifest['bytes']}"
                          + (' (truncated)' if size < manifest['bytes'] else ''))
    if sha != manifest['sha256']:
        raise BackupError('backup_checksum_mismatch', f'The sha256 of the copy {copy.name} does not match its manifest')
    return manifest
