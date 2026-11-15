"""CA-14: `admin prune-tables` removes what the retention windows (decision P-03) select, in short batches, and nothing else.

Every date is seeded relative to a fixed `NOW` that the run receives (no real clock), and every test has a database of its own."""
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

from memory_platform import admin
from memory_platform.admin import content_manifest, main, prune_tables, store_fingerprints
from memory_platform.config import RETENTION_DEFAULTS, retention_windows
from memory_platform.store import Store

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
DEFAULTS = {'login_attempts': 30, 'web_sessions': 30, 'audit_events': 365, 'jobs': 90, 'events': None}
VARIABLES = {'login_attempts': 'MEMORY_RETENTION_LOGIN_ATTEMPTS_DAYS', 'web_sessions': 'MEMORY_RETENTION_WEB_SESSIONS_DAYS',
             'audit_events': 'MEMORY_RETENTION_AUDIT_EVENTS_DAYS', 'jobs': 'MEMORY_RETENTION_JOBS_FAILED_DAYS', 'events': 'MEMORY_RETENTION_EVENTS_DAYS'}


def ago(days):
    return NOW - timedelta(days=days)


class WindowTests(unittest.TestCase):
    def test_the_defaults_are_the_ones_of_decision_p03_and_events_has_no_window(self):
        self.assertEqual(retention_windows({}), DEFAULTS)
        self.assertEqual(RETENTION_DEFAULTS, DEFAULTS)

    def test_each_variable_sets_its_own_table_and_blank_means_the_default(self):
        for table, name in VARIABLES.items():
            self.assertEqual(retention_windows({name: ' 7 '})[table], 7, name)
            self.assertEqual({t: d for t, d in retention_windows({name: '12'}).items() if t != table}, {t: d for t, d in DEFAULTS.items() if t != table}, name)
            self.assertEqual(retention_windows({name: ''}), DEFAULTS, name)
            self.assertEqual(retention_windows({name: '   '}), DEFAULTS, name)
            for edge in ('1', '36500'):
                self.assertEqual(retention_windows({name: edge})[table], int(edge))

    def test_a_window_outside_the_range_or_not_an_integer_names_its_variable_and_the_range(self):
        for table, name in VARIABLES.items():
            for bad in ('0', '-1', '-30', 'abc', '1.5', '36501', '1e3', '٣', 'nan', '30d', '999999999999999999999'):
                with self.assertRaises(ValueError, msg=(name, bad)) as caught:
                    retention_windows({name: bad})
                self.assertEqual(str(caught.exception), f'{name} must be an integer number of days between 1 and 36500', (name, bad))


class PruneDatabase(unittest.TestCase):
    """A migrated database of its own, seeded with old and recent rows in every pruned table and in the ones that must stay."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'prune_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin_connection:
            admin_connection.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)
        self.store = Store(self.dsn)
        self.store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.seed(c)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin_connection:
            admin_connection.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def seed(self, c):
        c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
        c.execute("INSERT INTO memory.actors(id,username,password_hash) VALUES('a1','u1','x')")
        for index, days in enumerate((31, 400, 30, 29, 1)):  # the one that is exactly 30 days old stays: the window is strict
            c.execute('INSERT INTO memory.login_attempts(username,client_ip,happened_at) VALUES(%s,%s,%s)', (f'old{index}' if days > 30 else f'keep{index}', '10.0.0.1', ago(days)))
        for index, days in enumerate((366, 400, 365, 10)):
            c.execute('INSERT INTO memory.audit_events(action,happened_at) VALUES(%s,%s)', (f'old{index}' if days > 365 else f'keep{index}', ago(days)))
        # name, expired (days ago; negative = still to come), revoked (days ago or None)
        for name, expired, revoked in (('s-expired-old', 31, None), ('s-expired-recent', 29, None), ('s-live', -5, None), ('s-live-revoked-old', -5, 31),
                                       ('s-live-revoked-recent', -5, 29), ('s-expired-long-revoked-today', 40, 1)):
            c.execute('INSERT INTO memory.web_sessions(id,actor_id,token_hash,csrf_hash,expires_at,revoked_at) VALUES(%s,%s,%s,%s,%s,%s)',
                      (name, 'a1', 't-' + name, 'c', ago(expired), None if revoked is None else ago(revoked)))
        # id, state, created (days ago), available (days ago), has a receipt
        for name, state, created, available, receipt in (('f-old', 'failed', 100, 100, False), ('f-old-receipt', 'failed', 100, 100, True), ('f-recent', 'failed', 89, 89, False),
                                                         ('f-retried', 'failed', 100, 10, False), ('f-91', 'failed', 91, 91, False), ('s-old', 'succeeded', 200, 200, True),
                                                         ('p-old', 'pending', 200, 200, False), ('r-old', 'running', 200, 200, False), ('u-old', 'unknown', 200, 200, False)):
            c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,created_at,available_at) "
                      "VALUES(%s,'p1',%s,1,repeat('a',64),'item','embed','upsert',%s,%s,%s)", (name, 'i-' + name, state, ago(created), ago(available)))
            if receipt:
                c.execute("INSERT INTO memory.projection_receipts(job_id,project_id,item_id,version,canonical_hash,destination,receipt) VALUES(%s,'p1',%s,1,repeat('a',64),'embed','{}')", (name, 'i-' + name))
        for name, days in (('e-old', 1000), ('e-recent', 5)):
            c.execute("INSERT INTO memory.events(id,project_id,canonical_hash,body,receipt,created_at) VALUES(%s,'p1',repeat('a',64),'{}','{}',%s)", (name, ago(days)))

    def rows(self, table, column='id'):
        with self.psycopg.connect(self.dsn) as c:
            return {str(row[0]) for row in c.execute(f'SELECT {column} FROM memory.{table}').fetchall()}

    def fingerprint(self):
        with self.psycopg.connect(self.dsn) as c:
            return {table: c.execute(f'SELECT count(*), md5(string_agg(to_jsonb(t)::text, $$,$$ ORDER BY to_jsonb(t)::text)) FROM memory.{table} t').fetchone()
                    for table in ('login_attempts', 'web_sessions', 'audit_events', 'jobs', 'events', 'projection_receipts', 'actors', 'projects')}

    def windows(self, **override):
        return dict(DEFAULTS, **override)


class PruneTests(PruneDatabase):
    def test_a_dry_run_reports_what_each_table_would_lose_and_writes_nothing(self):
        before = self.fingerprint()
        result = prune_tables(self.store, self.windows(), dry_run=True, now=NOW)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual((result['status'], result['dry_run']), ('dry_run', True))
        expected = {'login_attempts': 2, 'web_sessions': 3, 'audit_events': 2, 'jobs': 2}
        self.assertEqual({table: info['would_delete'] for table, info in result['tables'].items() if table in expected}, expected)
        self.assertTrue(all(info['deleted'] == 0 and info['batches'] == 0 for info in result['tables'].values()))
        self.assertEqual(result['tables']['jobs']['window_days'], 90)
        self.assertEqual(result['tables']['jobs']['cutoff'], ago(90).isoformat())

    def test_a_real_run_deletes_exactly_what_the_windows_select_and_a_second_run_finds_nothing(self):
        result = prune_tables(self.store, self.windows(), now=NOW)
        self.assertEqual((result['status'], result['dry_run']), ('pruned', False))
        self.assertEqual({table: result['tables'][table]['deleted'] for table in ('login_attempts', 'web_sessions', 'audit_events', 'jobs')},
                         {'login_attempts': 2, 'web_sessions': 3, 'audit_events': 2, 'jobs': 2})
        self.assertEqual(self.rows('login_attempts', 'username'), {'keep2', 'keep3', 'keep4'})
        self.assertEqual(self.rows('audit_events', 'action'), {'keep2', 'keep3'})
        self.assertEqual(self.rows('web_sessions'), {'s-expired-recent', 's-live', 's-live-revoked-recent'}, 'live sessions and the ones that ended less than the window ago stay')
        self.assertEqual(self.rows('jobs'), {'f-old-receipt', 'f-recent', 'f-retried', 's-old', 'p-old', 'r-old', 'u-old'})
        self.assertEqual(self.rows('events'), {'e-old', 'e-recent'}, 'events has no window by default')
        self.assertEqual(self.rows('projection_receipts', 'job_id'), {'f-old-receipt', 's-old'})
        again = prune_tables(self.store, self.windows(), now=NOW)
        self.assertEqual({table: info['deleted'] for table, info in again['tables'].items()}, {'login_attempts': 0, 'web_sessions': 0, 'audit_events': 0, 'jobs': 0, 'events': 0})

    def test_a_job_with_a_receipt_is_never_deleted_however_old(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("UPDATE memory.jobs SET created_at=%s,available_at=%s WHERE id='f-old-receipt'", (ago(5000), ago(5000)))
        prune_tables(self.store, self.windows(jobs=1), now=NOW)
        self.assertIn('f-old-receipt', self.rows('jobs'))
        self.assertEqual(self.rows('jobs'), {'f-old-receipt', 's-old', 'p-old', 'r-old', 'u-old'}, 'every failed job without a receipt went, no other state')

    def test_events_is_pruned_only_when_its_window_is_set_explicitly(self):
        result = prune_tables(self.store, self.windows(), now=NOW)
        self.assertEqual(result['tables']['events'], {'window_days': None, 'skipped': 'no_window', 'would_delete': 0, 'deleted': 0, 'batches': 0})
        self.assertEqual(self.rows('events'), {'e-old', 'e-recent'})
        result = prune_tables(self.store, self.windows(events=365), now=NOW)
        self.assertEqual(result['tables']['events']['deleted'], 1)
        self.assertEqual(self.rows('events'), {'e-recent'})

    def test_the_tables_option_restricts_the_run(self):
        result = prune_tables(self.store, self.windows(), tables=['audit_events'], now=NOW)
        self.assertEqual(set(result['tables']), {'audit_events'})
        self.assertEqual(len(self.rows('login_attempts')), 5)
        self.assertEqual(len(self.rows('audit_events')), 2)

    def test_batches_have_the_size_asked_and_each_one_is_a_transaction(self):
        with self.psycopg.connect(self.dsn) as c:
            for index in range(7):
                c.execute('INSERT INTO memory.login_attempts(username,client_ip,happened_at) VALUES(%s,%s,%s)', (f'extra{index}', '10.0.0.2', ago(60)))
        opened = []
        real = self.store.transaction

        @contextlib.contextmanager
        def counted():
            opened.append(1)
            with real() as connection:
                yield connection
        self.store.transaction = counted
        result = prune_tables(self.store, self.windows(), tables=['login_attempts'], batch=4, now=NOW)
        self.assertEqual((result['tables']['login_attempts']['deleted'], result['tables']['login_attempts']['batches']), (9, 3))  # 4 + 4 + 1
        self.assertGreaterEqual(len(opened), 3, 'a transaction per batch, not one for the whole run')

    def test_a_failed_batch_rolls_back_whole_and_the_run_can_be_repeated(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute('DELETE FROM memory.audit_events')
            for index in range(10):
                c.execute('INSERT INTO memory.audit_events(action,happened_at) VALUES(%s,%s)', ('poison' if index == 7 else f'a{index}', ago(500)))
            c.execute("CREATE FUNCTION public.refuse_poison() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.action = 'poison' THEN RAISE EXCEPTION 'refused'; END IF; RETURN OLD; END $$")
            c.execute('CREATE TRIGGER refuse_poison BEFORE DELETE ON memory.audit_events FOR EACH ROW EXECUTE FUNCTION public.refuse_poison()')
        with self.assertRaises(self.psycopg.errors.Error):
            prune_tables(self.store, self.windows(), tables=['audit_events'], batch=3, now=NOW)
        self.assertEqual(self.rows('audit_events', 'action'), {'a6', 'poison', 'a8', 'a9'}, 'rows 0-5 went in two committed batches; the batch of 6-8 left nothing half done')
        with self.psycopg.connect(self.dsn) as c:
            c.execute('DROP TRIGGER refuse_poison ON memory.audit_events')
        result = prune_tables(self.store, self.windows(), tables=['audit_events'], batch=3, now=NOW)
        self.assertEqual(result['tables']['audit_events']['deleted'], 4)
        self.assertEqual(self.rows('audit_events'), set())

    def test_two_runs_at_the_same_time_delete_every_row_once(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.login_attempts(username,client_ip,happened_at) SELECT 'bulk'||g,'10.0.0.3',%s FROM generate_series(1,300) g", (ago(90),))
        start, results, errors = threading.Barrier(2), [], []

        def run():
            try:
                start.wait()
                results.append(prune_tables(Store(self.dsn), self.windows(), tables=['login_attempts'], batch=7, now=NOW)['tables']['login_attempts']['deleted'])
            except Exception as error:  # reported below
                errors.append(error)
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sum(results), 302, results)  # 300 + the two old ones of the seed, each deleted by exactly one run
        self.assertEqual(self.rows('login_attempts', 'username'), {'keep2', 'keep3', 'keep4'})

    def test_a_row_another_transaction_holds_is_left_to_it_and_the_run_does_not_wait(self):
        """FOR UPDATE SKIP LOCKED: a run never waits for a lock (no deadlock between two runs either) and takes the rest; the row comes back on the next run."""
        holder = self.psycopg.connect(self.dsn)
        try:
            holder.execute("SELECT id FROM memory.login_attempts WHERE username='old1' FOR UPDATE")
            results = []
            thread = threading.Thread(target=lambda: results.append(prune_tables(Store(self.dsn), self.windows(), tables=['login_attempts'], now=NOW)))
            thread.start()
            thread.join(20)
            waited = thread.is_alive()
            holder.rollback()  # lets a run that waited finish, so the test ends either way
            thread.join(20)
        finally:
            holder.close()
        self.assertFalse(waited, 'the run waited for a row that another transaction holds')
        self.assertEqual(results[0]['tables']['login_attempts']['deleted'], 1)
        self.assertEqual(self.rows('login_attempts', 'username'), {'old1', 'keep2', 'keep3', 'keep4'})
        self.assertEqual(prune_tables(self.store, self.windows(), tables=['login_attempts'], now=NOW)['tables']['login_attempts']['deleted'], 1)
        self.assertEqual(self.rows('login_attempts', 'username'), {'keep2', 'keep3', 'keep4'})

    def test_a_dry_run_runs_read_only_and_issues_no_delete(self):
        statements = []
        real = self.store.transaction

        class Recorder:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, query, *args, **kwargs):
                statements.append(' '.join(str(query).split()))
                return self.connection.execute(query, *args, **kwargs)

        @contextlib.contextmanager
        def recorded():
            with real() as connection:
                yield Recorder(connection)
        self.store.transaction = recorded
        prune_tables(self.store, self.windows(), dry_run=True, now=NOW)
        counts = [s for s in statements if s.startswith('SELECT count(*)')]
        self.assertEqual(len(counts), 4)  # the four tables with a window
        self.assertEqual(statements.count('SET TRANSACTION READ ONLY'), 4, 'every count runs in a READ ONLY transaction')
        self.assertFalse([s for s in statements if s.startswith(('DELETE', 'UPDATE', 'INSERT'))], statements)

    def test_the_batch_size_is_validated(self):
        for bad in (0, -1, 5001, True, 1.5, '10'):
            with self.assertRaises(ValueError, msg=bad):
                prune_tables(self.store, self.windows(), batch=bad, now=NOW)
        self.assertEqual(len(self.rows('login_attempts')), 5)

    def test_an_unknown_table_or_a_missing_window_key_is_refused(self):
        with self.assertRaises(ValueError):
            prune_tables(self.store, self.windows(), tables=['actors'], now=NOW)
        with self.assertRaises(ValueError):
            prune_tables(self.store, {'jobs': 90}, now=NOW)


class InvariantTests(PruneDatabase):
    """Pruning does not change what a client sees: the memory data, the embeddings and the receipts stay exactly as they were (R-04)."""
    PRUNED = {'login_attempts', 'web_sessions', 'audit_events', 'jobs', 'events'}

    def seed_memory_data(self):
        content = 'Contenido de ejemplo'
        body = {'title': 'Doc', 'content': content, 'tags': ['a'], 'source': {'uri': 'fixture://1', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}}
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES('p1','d1',1,repeat('b',64),%s::jsonb)", (json.dumps(body),))
            c.execute("INSERT INTO memory.memory_items(project_id,id,version,canonical_hash,event_type,payload,session_id,agent_id,occurred_at,search_vector) "
                      "VALUES('p1','m1',1,repeat('c',64),'note',%s::jsonb,'s1','ag',%s,to_tsvector('simple','t c'))", (json.dumps({'title': 't', 'content': 'c'}), ago(500)))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES('p1','d1','document',1,repeat('b',64),'nomic-embed-text',%s)", ([0.5, 0.25, 0.125],))
            # The jobs of that document: one that worked (with its receipt) and one that failed long ago.
            for name, state in (('j-d1-ok', 'succeeded'), ('j-d1-failed', 'failed')):
                c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,created_at,available_at) "
                          "VALUES(%s,'p1','d1',1,repeat('b',64),'document','embed',%s,%s,%s,%s)", (name, 'upsert' if state == 'succeeded' else 'delete', state, ago(400), ago(400)))
            c.execute("INSERT INTO memory.projection_receipts(job_id,project_id,item_id,version,canonical_hash,destination,receipt) VALUES('j-d1-ok','p1','d1',1,repeat('b',64),'embed','{\"model\":\"m\"}')")

    def test_the_manifest_the_embeddings_and_the_receipts_are_the_same_after_pruning_with_the_shortest_windows(self):
        self.seed_memory_data()
        manifest, tables = content_manifest(self.store), store_fingerprints(self.store)
        self.assertEqual(len(manifest['documents']), 1)
        self.assertEqual(len(manifest['items']), 1)
        result = prune_tables(self.store, {table: 1 for table in self.PRUNED}, now=NOW)  # every window at its shortest, `events` included
        self.assertGreater(sum(info['deleted'] for info in result['tables'].values()), 0)
        self.assertEqual(content_manifest(self.store), manifest)
        after = store_fingerprints(self.store)
        self.assertEqual({table for table in tables if tables[table] != after[table]}, self.PRUNED, 'nothing outside the five pruned tables changed')
        for table in ('documents', 'memory_items', 'embeddings', 'projection_receipts', 'projects', 'actors', 'item_versions', 'document_versions'):
            self.assertEqual(after[table], tables[table], table)
        self.assertEqual(self.rows('projection_receipts', 'job_id'), {'f-old-receipt', 's-old', 'j-d1-ok'})
        self.assertNotIn('j-d1-failed', self.rows('jobs'))
        self.assertIn('j-d1-ok', self.rows('jobs'))

    def test_a_failed_job_with_a_receipt_survives_and_the_foreign_key_is_what_backs_it(self):
        """The predicate of the run leaves the job out; if it ever did not, the foreign key of `projection_receipts` stops the DELETE (shown here directly)."""
        with self.psycopg.connect(self.dsn) as c:
            with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
                c.execute("DELETE FROM memory.jobs WHERE id='f-old-receipt'")
        for windows in (self.windows(), self.windows(jobs=1), self.windows(jobs=36500)):
            prune_tables(self.store, windows, now=NOW + timedelta(days=40000))  # a clock far in the future makes every job older than any window
            self.assertIn('f-old-receipt', self.rows('jobs'))
            self.assertEqual(self.rows('projection_receipts', 'job_id'), {'f-old-receipt', 's-old'})

    def test_events_is_intact_with_the_default_windows_however_many_times_it_runs(self):
        before = self.fingerprint()['events']
        for _ in range(3):
            prune_tables(self.store, retention_windows({}), now=NOW + timedelta(days=40000))
        self.assertEqual(self.fingerprint()['events'], before)
        self.assertEqual(retention_windows({})['events'], None)


class CommandTests(PruneDatabase):
    def run_main(self, argv, **environ):
        settings = Mock(dsn=self.dsn, project_maps={})
        with patch('memory_platform.admin.Settings.from_env', return_value=settings), patch.dict(os.environ, environ), contextlib.redirect_stdout(io.StringIO()) as output:
            main(argv)
        return json.loads(output.getvalue())

    def test_the_command_prints_the_report_and_dry_run_deletes_nothing(self):
        before = self.fingerprint()
        report = self.run_main(['prune-tables', '--dry-run'])
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual((report['status'], report['dry_run'], report['batch']), ('dry_run', True, 1000))
        self.assertEqual(report['tables']['audit_events']['window_days'], 365)
        self.assertEqual(report['tables']['events']['skipped'], 'no_window')
        self.assertTrue(report['tables']['login_attempts']['would_delete'] >= 0)

    def test_the_command_reads_the_windows_from_the_environment_and_prunes(self):
        report = self.run_main(['prune-tables', '--batch', '10', '--table', 'events'], MEMORY_RETENTION_EVENTS_DAYS='1')
        self.assertEqual((report['status'], report['batch'], set(report['tables'])), ('pruned', 10, {'events'}))
        self.assertEqual(report['tables']['events']['deleted'], 2)
        self.assertEqual(self.rows('events'), set())
        self.assertEqual(len(self.rows('audit_events')), 4, 'only the table asked for')

    def test_an_invalid_window_stops_the_command_with_a_clear_message_before_touching_anything(self):
        before = self.fingerprint()
        for argv, environ, message in ((['prune-tables'], {'MEMORY_RETENTION_AUDIT_EVENTS_DAYS': '0'}, 'MEMORY_RETENTION_AUDIT_EVENTS_DAYS must be an integer number of days between 1 and 36500'),
                                       (['prune-tables', '--dry-run'], {'MEMORY_RETENTION_JOBS_FAILED_DAYS': 'soon'}, 'MEMORY_RETENTION_JOBS_FAILED_DAYS must be an integer number of days between 1 and 36500'),
                                       (['prune-tables', '--batch', '0'], {}, '--batch must be an integer between 1 and 5000'),
                                       (['prune-tables', '--table', 'actors'], {}, "invalid choice: 'actors'")):
            settings = Mock(dsn=self.dsn, project_maps={})
            with patch('memory_platform.admin.Settings.from_env', return_value=settings), patch.dict(os.environ, environ), contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as caught:
                    main(argv)
            self.assertEqual(caught.exception.code, 2, argv)
            self.assertIn(message, error.getvalue())
        self.assertEqual(self.fingerprint(), before)

    def test_the_command_uses_a_direct_connection_without_a_service_statement_timeout(self):
        """`prune-tables` is the long statement of an operator: it connects with the DSN as it is, so the database default applies (`statement_timeout` = 0), never the
        timeout that the API and the worker will get."""
        seen = {}
        real = admin.prune_tables

        def spy(store, windows, **options):
            with store.transaction() as c:
                seen['timeout'] = c.execute('SHOW statement_timeout').fetchone()['statement_timeout']
            seen['dsn'] = store.dsn
            return real(store, windows, **options)
        with patch('memory_platform.admin.prune_tables', spy):
            self.run_main(['prune-tables', '--dry-run'])
        self.assertEqual(seen, {'timeout': '0', 'dsn': self.dsn})


if __name__ == '__main__':
    unittest.main()
