"""Operator commands. Passwords are read from files, never command arguments."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import hashlib

from .config import Settings
from .store import Store






def store_fingerprints(store):
    """Include provenance, grants, jobs, versions and tombstones in restore QA."""
    from psycopg import sql
    result = {}
    with store.transaction() as connection:
        tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
        for row in tables:
            values = connection.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM memory.{} t').format(sql.Identifier(row['table_name']))).fetchall()
            encoded = sorted(json.dumps(v['value'], sort_keys=True, ensure_ascii=False, default=str) for v in values)
            result[row['table_name']] = {'rows': len(encoded), 'sha256': hashlib.sha256('\n'.join(encoded).encode('utf-8')).hexdigest()}
    return result


@contextmanager
def pg_environment(dsn):
    from psycopg.conninfo import conninfo_to_dict
    values = conninfo_to_dict(dsn)
    with tempfile.TemporaryDirectory(prefix='memory-pg-service-') as temporary:
        service = Path(temporary) / 'pg_service.conf'
        if any('\n' in str(v) or '\r' in str(v) for v in values.values()):
            raise ValueError('Invalid PostgreSQL connection parameter')
        service.write_text('[memory]\n' + '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n', encoding='utf-8')
        service.chmod(0o600)
        yield dict(os.environ, PGSERVICEFILE=str(service), PGSERVICE='memory')


def inspect_store(store):
    with store.transaction() as connection:
        tables = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='memory' ORDER BY table_name").fetchall()
        # Identifiers are from our schema inventory, not request input.
        from psycopg import sql
        return {row['table_name']: connection.execute(sql.SQL('SELECT count(*) AS n FROM memory.{}').format(sql.Identifier(row['table_name']))).fetchone()['n'] for row in tables}


def content_manifest(store):
    """Read canonical identities and hashes without document bodies or credentials."""
    with store.transaction() as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        documents = connection.execute('SELECT project_id,id,version,canonical_hash,deleted,body FROM memory.documents ORDER BY project_id,id').fetchall()
        items = connection.execute('SELECT project_id,id,version,canonical_hash,deleted,superseded_by FROM memory.memory_items ORDER BY project_id,id').fetchall()
        projects = connection.execute('SELECT id,title,policy FROM memory.projects ORDER BY id').fetchall()
        result = []
        for document in documents:
            body = document.pop('body')
            source_hash = hashlib.sha256(body.get('content', '').encode('utf-8')).hexdigest()
            expected = body.get('source', {}).get('sha256')
            if source_hash != expected:
                raise RuntimeError('A document source hash does not match its exact UTF-8 content')
            tags = body.get('tags', [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise RuntimeError('Document tags must remain a list of strings')
            result.append(dict(document, source_sha256=source_hash, title=body.get('title'), tags=tags, source=body.get('source', {})))
        manifest = {'projects': projects, 'documents': result, 'items': items}
        encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        return dict(manifest, sha256=hashlib.sha256(encoded.encode('utf-8')).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description='Manage only the isolated memory platform database')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    bootstrap = commands.add_parser('bootstrap')
    bootstrap.add_argument('--username', default='admin')
    bootstrap.add_argument('--password-file', default=os.environ.get('MEMORY_BOOTSTRAP_PASSWORD_FILE'))
    bootstrap.add_argument('--with-projects', action='store_true', help='Create allowlisted project shells; capture stays off')
    commands.add_parser('inspect')
    commands.add_parser('content-manifest')
    backup = commands.add_parser('backup')
    backup.add_argument('--output', required=True)
    restore = commands.add_parser('restore-check')
    restore.add_argument('--backup', required=True)
    restore.add_argument('--target-dsn-file', required=True)
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    store = Store(settings.dsn, project_maps=settings.project_maps, embedding_enabled=True)
    if args.command == 'migrate':
        store.migrate()
        print(json.dumps({'status': 'migrated'}))
    elif args.command == 'bootstrap':
        if not args.password_file:
            parser.error('--password-file or MEMORY_BOOTSTRAP_PASSWORD_FILE is required')
        password = Path(args.password_file).read_text(encoding='utf-8').strip()
        actor = store.bootstrap_user(args.username, password)
        projects = []
        if args.with_projects:
            for project_id in settings.project_maps:
                store.create_project(actor, {'id': project_id, 'title': project_id})
                projects.append(project_id)
        print(json.dumps({'status': 'bootstrapped', 'username': args.username, 'projects': projects, 'capture': 'off'}))
    elif args.command == 'inspect':
        print(json.dumps({'tables': inspect_store(store)}, sort_keys=True))
    elif args.command == 'content-manifest':
        print(json.dumps(content_manifest(store), sort_keys=True, default=str))
    elif args.command == 'backup':
        output = Path(args.output).resolve()
        if output.exists():
            parser.error('Backup destination already exists; choose a new filename')
        output.parent.mkdir(parents=True, exist_ok=True)
        with pg_environment(settings.dsn) as environment:
            subprocess.run(['pg_dump', '--dbname=service=memory', '--format=custom', '--no-owner', '--file', str(output)], env=environment, check=True, capture_output=True)
        output.chmod(0o600)
        print(json.dumps({'status': 'backed_up', 'path': str(output), 'bytes': output.stat().st_size}))
    elif args.command == 'restore-check':
        target = Path(args.target_dsn_file).read_text(encoding='utf-8').strip()
        if target == settings.dsn:
            parser.error('Restore target must be a separate, freshly created memory_restore* database')
        from psycopg.conninfo import conninfo_to_dict
        source_info, target_info = conninfo_to_dict(settings.dsn), conninfo_to_dict(target)
        if target == settings.dsn or not target_info.get('dbname', '').startswith('memory_restore') or (target_info.get('dbname') == source_info.get('dbname') and target_info.get('host') == source_info.get('host')):
            parser.error('Restore target must be a separate, freshly created memory_restore* database')
        restored = Store(target)
        with restored.transaction() as connection:
            if connection.execute("SELECT 1 FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') LIMIT 1").fetchone():
                parser.error('Restore target must be empty; no cleanup or overwrite is performed')
        before = store_fingerprints(store)
        with pg_environment(target) as environment:
            subprocess.run(['pg_restore', '--dbname=service=memory', '--no-owner', '--no-acl', '--exit-on-error', str(Path(args.backup).resolve())], env=environment, check=True, capture_output=True)
        after = store_fingerprints(restored)
        if before != after:
            raise RuntimeError('Restore data fingerprints differ; inspect the isolated restored database')
        print(json.dumps({'status': 'restored_and_content_verified', 'tables': after}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Connection/provider errors may contain passwords or DSNs. Do not print them.
        raise SystemExit(f'Administration failed ({type(exc).__name__}); no credentials are printed.') from None
