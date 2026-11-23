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

from memory_platform import passwords
from memory_platform.admin import backfill_chunks, main, store_fingerprints, content_manifest
from memory_platform.errors import MemoryError
from memory_platform.store_jobs import stored_item_vector
from memory_platform.tests import test_passwords as pw
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


class BackfillChunksTests(unittest.TestCase):
    """`admin backfill-chunks`: queue `embed` jobs for current resources that have no fragments (CA-28), idempotent, resumable, bounded."""
    MODEL = 'nomic-embed-text'

    def setUp(self):
        self.store, self.actor, self.project = create_core()

    LONG = 'palabra ' * 400  # more than one fragment: such a resource needs a job; a short one is completed from its item vector

    def resource(self, kind='document', *, embedded=True, job_state='succeeded', chunks=False, deleted=False, superseded=False, text=None):
        """A resource as the previous release left it: a job and an item-level embedding, no fragments (unless `chunks`)."""
        item_id = str(uuid.uuid4())
        resource_type = 'item' if kind == 'item' else 'document'
        with self.store.transaction() as c:
            if kind == 'document':
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body,deleted) VALUES(%s,%s,1,repeat('a',64),%s::jsonb,%s)",
                          (self.project, item_id, json.dumps({'title': 'T', 'content': self.LONG if text is None else text}), deleted))
            else:
                c.execute("""INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector,deleted,superseded_by)
                             VALUES(%s,%s,1,repeat('a',64),'note',%s::jsonb,'s','a',clock_timestamp(),to_tsvector('simple','x'),%s,%s)""",
                          (self.project, item_id, json.dumps({'title': 'T', 'content': self.LONG if text is None else text}), deleted, 'newer' if superseded else None))
            if job_state:
                c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state) VALUES(%s,%s,%s,1,repeat('a',64),%s,'embed','upsert',%s)",
                          (str(uuid.uuid4()), self.project, item_id, resource_type, job_state))
            if embedded:
                c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,%s,1,repeat('a',64),%s,%s)",
                          (self.project, item_id, resource_type, self.MODEL, [1.0, 0.5]))
            if chunks:
                c.execute("INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding) VALUES(%s,%s,%s,1,repeat('a',64),%s,0,0,10,'[1,0.5]'::vector)",
                          (self.project, item_id, resource_type, self.MODEL))
        return item_id

    def jobs(self, ids):
        with self.store.transaction() as c:
            return {r['item_id']: r for r in c.execute("SELECT * FROM memory.jobs WHERE project_id=%s AND item_id=ANY(%s) AND destination='embed'", (self.project, list(ids))).fetchall()}

    def run_backfill(self, **options):
        return backfill_chunks(self.store, self.MODEL, project=self.project, **options)

    def test_only_current_resources_without_fragments_are_queued_and_a_second_run_queues_none(self):
        """CA-28."""
        wanted = [self.resource('document'), self.resource('item')]
        skipped = {'has fragments': self.resource('document', chunks=True), 'deleted': self.resource('document', deleted=True),
                   'superseded item': self.resource('item', superseded=True),
                   'technical item': self.resource('item', embedded=False, job_state=None),
                   'already queued': self.resource('document', job_state='pending')}
        first = self.run_backfill()
        self.assertEqual((first['enqueued'], first['remaining']), (2, 0))
        queued = self.jobs(wanted)
        self.assertEqual({row['state'] for row in queued.values()}, {'pending'})
        untouched = self.jobs(skipped.values())
        self.assertEqual(untouched[skipped['already queued']]['state'], 'pending')
        self.assertEqual({untouched[skipped[name]]['state'] for name in ('has fragments', 'deleted', 'superseded item')}, {'succeeded'})
        self.assertNotIn(skipped['technical item'], untouched)  # never meant to be embedded: no job, no embedding, none created
        second = self.run_backfill()
        self.assertEqual((second['enqueued'], second['remaining']), (0, 0))
        self.assertEqual({row['id'] for row in self.jobs(wanted).values()}, {row['id'] for row in queued.values()})

    def test_the_run_is_bounded_and_resumable(self):
        resources = [self.resource('document') for _ in range(5)]
        first = self.run_backfill(batch=2, max_jobs=3)
        self.assertEqual((first['enqueued'], first['remaining'], first['batches']), (3, 2, 2))
        self.assertEqual(sum(row['state'] == 'pending' for row in self.jobs(resources).values()), 3)
        second = self.run_backfill(batch=2)
        self.assertEqual((second['enqueued'], second['remaining']), (2, 0))
        self.assertEqual(self.run_backfill()['enqueued'], 0)

    def test_a_failed_job_is_queued_again_with_a_fresh_attempt_budget_and_an_active_one_is_left_alone(self):
        failed, running = self.resource('document', job_state='failed'), self.resource('document', job_state='running')
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET attempts=3,error_code='provider_unavailable' WHERE project_id=%s AND item_id=%s", (self.project, failed))
        before = self.jobs([failed, running])
        self.assertEqual(self.run_backfill()['enqueued'], 0)  # gap 10: a failed job is not queued again on every run...
        self.assertEqual(self.jobs([failed])[failed]['state'], 'failed')
        counted = self.run_backfill()
        self.assertEqual((counted['failed'], counted['remaining']), (1, 0))  # ...it is counted, so nobody reads it as done
        self.assertEqual(self.run_backfill(retry_failed=True)['enqueued'], 1)  # ...until the operator asks
        after = self.jobs([failed, running])
        self.assertEqual((after[failed]['state'], after[failed]['attempts'], after[failed]['error_code']), ('pending', 0, None))
        self.assertEqual(after[failed]['id'], before[failed]['id'])
        self.assertEqual(after[running]['state'], 'running')

    def test_backfill_jobs_are_queued_behind_every_live_write(self):
        """Gap 2: priority 1, also when a finished job is put back in the queue."""
        queued, again = self.resource('document'), self.resource('document', job_state='failed')
        self.assertEqual(self.run_backfill()['enqueued'], 1)
        self.assertEqual(self.run_backfill(retry_failed=True)['enqueued'], 1)
        self.assertEqual({row['priority'] for row in self.jobs([queued, again]).values()}, {1})
        self.assertEqual(self.run_backfill()['pending'], 2)

    def test_a_resource_that_is_one_fragment_with_its_item_vector_needs_no_provider_call(self):
        """Gap 6: its only fragment is the vector the previous worker already computed for exactly that text."""
        short = self.resource('document', text='texto corto')
        shorter_item = self.resource('item', text='nota corta')
        without_vector = self.resource('document', embedded=False, text='sin vector', job_state='succeeded')
        result = self.run_backfill()
        self.assertEqual((result['derived'], result['enqueued']), (2, 1))
        with self.store.transaction() as c:
            rows = c.execute("SELECT item_id,ordinal,char_start,char_end,vector_dims(embedding) AS dims FROM memory.embedding_chunks WHERE project_id=%s ORDER BY item_id", (self.project,)).fetchall()
            flags = {r['item_id']: r['chunked'] for r in c.execute('SELECT item_id,chunked FROM memory.embeddings WHERE project_id=%s', (self.project,)).fetchall()}
        self.assertEqual({r['item_id']: (r['ordinal'], r['char_start'], r['char_end'], r['dims']) for r in rows},
                         {short: (0, 0, len('T\ntexto corto'), 2), shorter_item: (0, 0, len('T\nnota corta'), 2)})
        self.assertTrue(flags[short] and flags[shorter_item])
        self.assertEqual(self.jobs([short])[short]['state'], 'succeeded')  # no new job
        self.assertEqual(self.jobs([without_vector])[without_vector]['state'], 'pending')  # no vector to derive from: the provider is needed
        self.assertEqual(self.run_backfill()['derived'], 0)

    def test_a_resource_with_an_embedding_but_no_job_record_is_queued(self):
        legacy = self.resource('document', job_state=None)
        self.assertEqual(self.run_backfill()['enqueued'], 1)
        self.assertEqual(self.jobs([legacy])[legacy]['state'], 'pending')

    def test_the_other_projects_are_not_touched(self):
        other = 'o-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.actor, {'id': other, 'title': 'Other'})
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,'foreign',1,repeat('a',64),%s::jsonb)", (other, json.dumps({'title': 'T', 'content': 'x'})))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,'foreign','document',1,repeat('a',64),%s,%s)", (other, self.MODEL, [1.0, 0.5]))
        self.resource('document')
        self.assertEqual(self.run_backfill()['enqueued'], 1)
        with self.store.transaction() as c:
            self.assertEqual(c.execute("SELECT count(*) AS n FROM memory.jobs WHERE project_id=%s", (other,)).fetchone()['n'], 0)

    def test_a_completed_job_takes_the_resource_out_of_the_backfill(self):
        item_id = self.resource('document')
        self.assertEqual(self.run_backfill()['enqueued'], 1)
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=9,lease_until=clock_timestamp()+interval '1 minute' WHERE project_id=%s AND item_id=%s", (self.project, item_id))
            job = c.execute("SELECT * FROM memory.jobs WHERE project_id=%s AND item_id=%s", (self.project, item_id)).fetchone()
        self.assertTrue(self.store.complete_job(job['id'], 9, {'vector': [1.0, 0.5], 'model': self.MODEL, 'canonical_hash': job['canonical_hash'], 'verified': True}))
        self.assertEqual(self.run_backfill()['enqueued'], 0)

    def unchunked_rows(self):
        with self.store.transaction() as c:
            return {(r['item_id'], r['version']) for r in c.execute('SELECT item_id,version FROM memory.embeddings WHERE project_id=%s AND NOT chunked', (self.project,)).fetchall()}

    def test_item_vectors_of_non_current_resources_leave_the_unchunked_index_and_none_is_deleted(self):
        """Attempt 2, gap 1: rows of old versions, deleted and superseded resources stay out of `memory_embeddings_unchunked` after the backfill."""
        live = self.resource('document')
        gone, replaced = self.resource('document', deleted=True), self.resource('item', superseded=True)
        old = self.resource('document', chunks=True)
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',0,repeat('b',64),%s,%s)", (self.project, old, self.MODEL, [1.0, 0.5]))
            c.execute('UPDATE memory.embeddings SET chunked=true WHERE project_id=%s AND item_id=%s AND version=1', (self.project, old))
            total = c.execute('SELECT count(*) AS n FROM memory.embeddings WHERE project_id=%s', (self.project,)).fetchone()['n']
        self.assertEqual(self.unchunked_rows(), {(live, 1), (gone, 1), (replaced, 1), (old, 0)})
        result = self.run_backfill(batch=1)  # batch 1: the key order is walked across several transactions
        self.assertEqual(result['stale_marked'], 3)
        self.assertEqual(self.unchunked_rows(), {(live, 1)})  # only live work is left in the partial index
        with self.store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.embeddings WHERE project_id=%s', (self.project,)).fetchone()['n'], total)
        self.assertEqual(self.run_backfill()['stale_marked'], 0)

    def test_completing_a_job_flags_the_item_vectors_of_older_versions(self):
        """Attempt 2, gap 1: a resource updated before its backfill must not leave its old version in the unchunked index."""
        item_id = self.resource('document', job_state='pending')  # no backfill run here: only complete_job may flag the old version
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',0,repeat('b',64),%s,%s)", (self.project, item_id, self.MODEL, [1.0, 0.5]))
        self.assertEqual(self.unchunked_rows(), {(item_id, 0), (item_id, 1)})
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=9,lease_until=clock_timestamp()+interval '1 minute' WHERE project_id=%s AND item_id=%s", (self.project, item_id))
            job = c.execute("SELECT * FROM memory.jobs WHERE project_id=%s AND item_id=%s", (self.project, item_id)).fetchone()
            before = c.execute('SELECT created_at,embedding::text AS e FROM memory.embeddings WHERE project_id=%s AND item_id=%s AND version=1', (self.project, item_id)).fetchone()
        self.assertTrue(self.store.complete_job(job['id'], 9, {'vector': [1.0, 0.5], 'model': self.MODEL, 'canonical_hash': job['canonical_hash'], 'verified': True}))
        self.assertEqual(self.unchunked_rows(), set())
        with self.store.transaction() as c:
            after = c.execute('SELECT created_at,embedding::text AS e FROM memory.embeddings WHERE project_id=%s AND item_id=%s AND version=1', (self.project, item_id)).fetchone()
        self.assertEqual(after, before)  # gap 3: an identical item vector is not rewritten (not even its timestamp)
        self.assertEqual(stored_item_vector(self.store, self.project, item_id, 'document', 1, 'a' * 64, self.MODEL), [1.0, 0.5])
        self.assertIsNone(stored_item_vector(self.store, self.project, item_id, 'document', 1, 'b' * 64, self.MODEL))

    def test_item_vectors_missing_their_pgvector_column_are_filled_in_batches(self):
        item_id = self.resource('document')
        with self.store.transaction() as c:
            c.execute('ALTER TABLE memory.embeddings DISABLE TRIGGER embedding_sync')
            try:
                c.execute('UPDATE memory.embeddings SET embedding=NULL WHERE project_id=%s AND item_id=%s', (self.project, item_id))
            finally:
                c.execute('ALTER TABLE memory.embeddings ENABLE TRIGGER embedding_sync')
        filled = self.run_backfill(batch=1)['embedding_filled']
        self.assertGreaterEqual(filled, 1)  # the whole table is filled: other fixtures of the shared test database may also be pending
        with self.store.transaction() as c:
            self.assertEqual(c.execute('SELECT vector_dims(embedding) AS n FROM memory.embeddings WHERE project_id=%s AND item_id=%s', (self.project, item_id)).fetchone()['n'], 2)
        self.assertEqual(self.run_backfill()['embedding_filled'], 0)

    def test_the_command_prints_counts_only(self):
        settings = Mock(dsn='postgresql://fixture@127.0.0.1/fixture', project_maps={}, embedding_model=self.MODEL)
        store = Mock()
        result = {'enqueued': 3, 'remaining': 0, 'batches': 1, 'embedding_filled': 0}
        with patch('memory_platform.admin.Settings.from_env', return_value=settings), patch('memory_platform.admin.Store', return_value=store), \
                patch('memory_platform.admin.backfill_chunks', return_value=result) as run, contextlib.redirect_stdout(io.StringIO()) as output:
            main(['backfill-chunks', '--batch', '50', '--max-jobs', '1000'])
        self.assertEqual(json.loads(output.getvalue()), dict(result, status='backfilled'))
        run.assert_called_once_with(store, self.MODEL, batch=50, max_jobs=1000, project=None, retry_failed=False)
        self.assertNotIn('postgresql://', output.getvalue())

    def test_the_command_runs_end_to_end_against_the_database_and_a_second_run_queues_none(self):
        item_id = self.resource('document')
        outputs = []
        for _ in range(2):
            with patch.dict(os.environ, {'MEMORY_DSN': self.store.dsn, 'MEMORY_DSN_FILE': ''}), contextlib.redirect_stdout(io.StringIO()) as output:
                main(['backfill-chunks', '--project', self.project, '--batch', '10'])
            outputs.append(json.loads(output.getvalue()))
        self.assertEqual([(o['status'], o['enqueued'], o['remaining']) for o in outputs], [('backfilled', 1, 0), ('backfilled', 0, 0)])
        self.assertEqual(self.jobs([item_id])[item_id]['state'], 'pending')

    def test_a_disabled_embedding_service_queues_nothing_and_says_so(self):
        settings = Mock(dsn='postgresql://fixture@127.0.0.1/fixture', project_maps={}, embedding_model=self.MODEL, embed_enabled=False)
        with patch('memory_platform.admin.Settings.from_env', return_value=settings), patch('memory_platform.admin.Store'),                 patch('memory_platform.admin.backfill_chunks') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            main(['backfill-chunks'])
        run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {'status': 'skipped', 'reason': 'embeddings_disabled', 'enqueued': 0})


class SetPasswordTests(pw.Fixture):
    """CA-02 (T-10): `admin set-password --username --password-file` on the writer of the store (DC-10): new password, every session of the user closed, audited, nothing printed."""
    NEW = 'replacement-password-789'

    def run_command(self, username='ana', password=None, extra=()):
        settings = Mock(dsn=self.dsn, project_maps={})
        with workspace() as root:
            secret = root / 'password'
            secret.write_text((self.NEW if password is None else password) + '\n', encoding='utf-8')
            out, err = io.StringIO(), io.StringIO()
            with patch('memory_platform.admin.Settings.from_env', return_value=settings), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    main(['set-password', '--username', username, '--password-file', str(secret), *extra])
                    status = 0
                except SystemExit as exit:
                    status = exit.code
        return status, out.getvalue(), err.getvalue()

    def sessions(self):
        from memory_platform.auth import Auth
        auth = Auth(self.store, ['https://memory.example'])
        return [auth.login('ana', pw.PASSWORD, '192.0.2.%d' % n) for n in (10, 11)]

    def test_it_sets_the_password_closes_every_session_and_audits(self):
        first, second = self.sessions()
        status, out, err = self.run_command()
        self.assertEqual(status, 0, err)
        self.assertEqual(json.loads(out)['status'], 'password_set')
        self.assertEqual(json.loads(out)['sessions_revoked'], 2)
        for session in (first, second):
            with self.assertRaises(MemoryError) as raised:
                self.auth.authenticate_session(session['session_token'])
            self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(MemoryError):
            self.auth.login('ana', pw.PASSWORD, '192.0.2.12')
        self.assertEqual(self.auth.login('ana', self.NEW, '192.0.2.12')['actor']['username'], 'ana')
        with self.psycopg.connect(self.dsn) as c:
            events = c.execute("SELECT action,resource_id FROM memory.audit_events WHERE action LIKE 'password.%' ORDER BY id").fetchall()
            ana = c.execute("SELECT id FROM memory.actors WHERE username='ana'").fetchone()[0]
        self.assertEqual(events, [('password.reset', ana)])

    def test_neither_the_output_nor_the_logs_nor_the_events_hold_the_password_or_its_hash(self):
        self.sessions()
        with self.assertNoLogs(level='DEBUG'):
            status, out, err = self.run_command()
        self.assertEqual(status, 0, err)
        with self.psycopg.connect(self.dsn) as c:
            stored = c.execute("SELECT password_hash FROM memory.actors WHERE username='ana'").fetchone()[0]
            events = json.dumps(c.execute('SELECT * FROM memory.audit_events').fetchall(), default=str)
        salt, digest = json.loads(stored)['salt'], json.loads(stored)['hash']
        for text in (out, err, events):
            for secret in (self.NEW, stored, salt, digest):
                self.assertNotIn(secret, text)

    def test_a_short_password_or_an_unknown_user_changes_nothing(self):
        before = self.stored_hash()
        for username, password in (('ana', 'short'), ('nobody', self.NEW)):
            status, out, err = self.run_command(username, password)
            self.assertNotEqual(status, 0)
        self.assertEqual(self.stored_hash(), before)
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.20')['actor']['username'], 'ana')

    def test_the_command_derives_once_at_the_target_cost_and_uses_no_gate(self):
        with pw.Derivations() as spy, patch.object(passwords, 'GATE', None):  # the API's gate is not the operator's: a None gate would break any use of it
            self.assertEqual(self.run_command()[0], 0)
        self.assertEqual(spy.calls, [passwords.TARGET])

    def test_admin_py_has_no_sql_of_its_own_for_it(self):
        import ast
        source = (Path(__file__).parents[1] / 'admin.py').read_text(encoding='utf-8')
        branch = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.If) and 'set-password' in ast.dump(node.test))
        body = [node for statement in branch.body for node in ast.walk(statement)]  # the `elif` chain hangs the next commands from `orelse`: only this one's own statements
        for node in body:
            self.assertFalse(isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'execute', 'the branch of set-password runs SQL itself')
            self.assertFalse(isinstance(node, ast.Constant) and isinstance(node.value, str) and 'memory.' in node.value, 'the branch of set-password names a table')
        self.assertTrue(any(isinstance(n, ast.Attribute) and n.attr == 'set_password' for n in body), 'it calls the writer of the store')
