"""Native operator safety and full PostgreSQL backup/restore checks."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from memory_platform.admin import main, store_fingerprints, content_manifest
from memory_platform.tests.test_store import create_core, event


@contextlib.contextmanager
def workspace():
    parent = Path(tempfile.gettempdir()).resolve()
    root = parent / ('kairos-admin-test-' + uuid.uuid4().hex)
    root.mkdir(mode=0o777)
    try:
        yield root
    finally:
        if root.resolve().parent != parent or not root.name.startswith('kairos-admin-test-'):
            raise RuntimeError('Unsafe owned test cleanup')
        shutil.rmtree(root)


class OperatorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Mock(dsn='postgresql://fixture@127.0.0.1/fixture', project_maps={})

    def test_inspection_has_no_write_or_provider_side_effect(self):
        store = Mock()
        with patch('memory_platform.admin.Settings.from_env', return_value=self.settings), patch('memory_platform.admin.Store', return_value=store), patch('memory_platform.admin.inspect_store', return_value={'actors': 1}), contextlib.redirect_stdout(io.StringIO()) as output:
            main(['inspect'])
        self.assertEqual(json.loads(output.getvalue()), {'tables': {'actors': 1}})
        store.migrate.assert_not_called()
        store.bootstrap_user.assert_not_called()

    def test_bootstrap_reads_private_file_without_printing_password(self):
        store = Mock()
        store.bootstrap_user.return_value = {'id': 'actor', 'username': 'fixture'}
        with workspace() as root:
            password = root/'password'
            password.write_text('fixture-password-123', encoding='utf-8')
            with patch('memory_platform.admin.Settings.from_env', return_value=self.settings), patch('memory_platform.admin.Store', return_value=store), contextlib.redirect_stdout(io.StringIO()) as output:
                main(['bootstrap', '--username', 'fixture', '--password-file', str(password)])
            self.assertNotIn('fixture-password-123', output.getvalue())
            store.bootstrap_user.assert_called_once_with('fixture', 'fixture-password-123')

    def test_backup_rejects_existing_destination_before_subprocess(self):
        with workspace() as root:
            target = root/'existing.dump'; target.write_bytes(b'original')
            with patch('memory_platform.admin.Settings.from_env', return_value=self.settings), patch('memory_platform.admin.Store'), patch('memory_platform.admin.subprocess.run') as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['backup', '--output', str(target)])
            self.assertEqual(target.read_bytes(), b'original')
            run.assert_not_called()

    def test_restore_rejects_source_database_before_subprocess(self):
        with workspace() as root:
            target = root/'target.dsn'; target.write_text(self.settings.dsn, encoding='utf-8')
            with patch('memory_platform.admin.Settings.from_env', return_value=self.settings), patch('memory_platform.admin.Store'), patch('memory_platform.admin.subprocess.run') as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['restore-check', '--backup', str(root/'unused.dump'), '--target-dsn-file', str(target)])
            run.assert_not_called()


class AdminPostgresTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()

    def test_content_manifest_verifies_exact_hash_tags_and_detects_tampering(self):
        content = 'Fuente: "\u00c1rbol", decisi\u00f3n \U0001f333'
        document = {'document_id': str(uuid.uuid4()), 'version': 1,
                    'title': '\u00cdndice: "\u00c1rbol" \U0001f333', 'content': content,
                    'tags': ['area:despliegue', 'nota:uno,dos', '"\u00c1rbol"'],
                    'source': {'uri': 'fixture://approved', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}}
        self.store.publish_document(self.actor, self.project, document)
        manifest = content_manifest(self.store)
        row = next(d for d in manifest['documents'] if d['id'] == document['document_id'])
        self.assertEqual(row['tags'], document['tags'])
        self.assertEqual(row['title'], document['title'])
        self.assertEqual(row['source_sha256'], document['source']['sha256'])
        self.assertNotIn('content', row)
        self.assertEqual(content_manifest(self.store)['sha256'], manifest['sha256'])
        with self.store.transaction() as c:
            c.execute("UPDATE memory.documents SET body=jsonb_set(body,'{content}','\"tampered\"') WHERE id=%s", (document['document_id'],))
        try:
            with self.assertRaises(RuntimeError):
                content_manifest(self.store)
        finally:
            with self.store.transaction() as c:
                c.execute("UPDATE memory.documents SET body=jsonb_set(body,'{content}',%s::jsonb) WHERE id=%s", (json.dumps(content), document['document_id']))

    def test_pg_dump_restore_preserves_documents_grants_versions_and_tombstones(self):
        if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
            self.skipTest('PostgreSQL client tools are required')
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        self.store.ingest_event(self.actor, event(self.project))
        self.store.create_user(self.actor, {'username': 'grant-' + uuid.uuid4().hex[:14], 'password': 'synthetic-password-only', 'project_ids': [self.project], 'scopes': ['read']})
        content = 'An approved synthetic source.'
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Source', 'content': content, 'tags': ['note:one,two'],
                    'source': {'uri': 'fixture://approved', 'sha256': hashlib.sha256(content.encode()).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['Synthetic approval']}}
        self.store.publish_document(self.actor, self.project, document)
        self.store.publish_document(self.actor, self.project, dict(document, version=2, title='Revised source'))
        self.store.delete_document(self.actor, self.project, document['document_id'], 3)
        values = conninfo_to_dict(self.store.dsn)
        target_name = 'memory_restore_' + uuid.uuid4().hex[:16]
        maintenance = make_conninfo(**dict(values, dbname='postgres'))
        target = make_conninfo(**dict(values, dbname=target_name))
        with psycopg.connect(maintenance, autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target_name)))
        try:
            with workspace() as root:
                target_file = root/'target.dsn'; target_file.write_text(target, encoding='utf-8')
                backup = root/'synthetic.dump'
                with patch.dict(os.environ, {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': ''}), contextlib.redirect_stdout(io.StringIO()):
                    main(['backup', '--output', str(backup)])
                    main(['restore-check', '--backup', str(backup), '--target-dsn-file', str(target_file)])
                from memory_platform.store import Store
                self.assertEqual(store_fingerprints(self.store), store_fingerprints(Store(target)))
        finally:
            if not target_name.startswith('memory_restore_') or len(target_name) != 31:
                raise RuntimeError('Unsafe restore target')
            with psycopg.connect(maintenance, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target_name)))
