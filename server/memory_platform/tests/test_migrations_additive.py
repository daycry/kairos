"""CA-34: the migrations only ADD (no DROP, TRUNCATE, DELETE, RENAME, ALTER ... TYPE or SET NOT NULL), and the failed-jobs index of schema version 11 is additive and usable."""
import ast
import contextlib
import os
from pathlib import Path
import re
import unittest
import uuid

from memory_platform.store import Store

PACKAGE = Path(__file__).parents[1]
DESTRUCTIVE = re.compile(r'\b(DROP|TRUNCATE|DELETE|RENAME)\b', re.IGNORECASE)
# Clauses of an `ALTER TABLE` that rewrite or tighten what exists, in ANY position of a multi-clause statement.
ALTER_UNSAFE = re.compile(r'\bALTER\s+(?:COLUMN\s+)?\S+\s+(?:SET\s+DATA\s+)?TYPE\b|\bSET\s+NOT\s+NULL\b', re.IGNORECASE)
# SQL kept in a literal (`EXECUTE 'DROP ...'`, `c.execute('DELETE FROM ...')`) is still SQL.
LITERAL_SQL = re.compile(r'(?:^|;)\s*TRUNCATE\b|\b(?:DROP\s+(?:TABLE|INDEX|COLUMN|SCHEMA|DATABASE|VIEW|CONSTRAINT|TYPE|EXTENSION|TRIGGER|FUNCTION)|DELETE\s+FROM|ALTER\s+TABLE)\b', re.IGNORECASE)
LITERAL = re.compile(r"'((?:[^']|'')*)'")
MIGRATION_SOURCES = ('schema.sql', 'agent_store.py', 'extended_store.py', 'corpus_answers.py', 'store_vectors.py')
# The only DELETEs allowed in the Python modules above: runtime replacement of the rows of ONE corpus (bounded by `corpus_id`), not a migration step.
ALLOWED_DELETES = {'agent_store.py': {'DELETE FROM memory.agent_corpus_entries WHERE corpus_id=%s', 'DELETE FROM memory.agent_corpus_queries WHERE corpus_id=%s'}}


def catalog_snapshot(c):
    """What a database holds, read from the catalog (not from SQL text): columns with type and nullability, indexes with their definition,
    constraints, functions, triggers, extensions and the registered schema versions. `c` is any psycopg connection (tuple or dict rows)."""
    def rows(query):
        return [tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in c.execute(query).fetchall()]
    return {
        'columns': {(t, n): (d, nullable) for t, n, d, nullable in rows("SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema='memory'")},
        'indexes': {(t, n): d for t, n, d in rows("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='memory'")},
        'constraints': {(t, n): k for t, n, k in rows("SELECT conrelid::regclass::text,conname,contype::text FROM pg_constraint WHERE connamespace='memory'::regnamespace")},
        'functions': {n for (n,) in rows("SELECT proname FROM pg_proc WHERE pronamespace='memory'::regnamespace")},
        'triggers': {(t, n) for t, n in rows("SELECT tgrelid::regclass::text,tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid::regclass::text LIKE 'memory.%'")},
        'extensions': {n for (n,) in rows('SELECT extname FROM pg_extension')},
        'versions': {v for (v,) in rows('SELECT version FROM memory.schema_versions')},
    }


def additive_violations(before, after):
    """What a migration took away or changed: empty when `after` only adds to `before` (a column keeps its type and cannot become NOT NULL,
    an index keeps its definition, nothing else disappears)."""
    lost = []
    for key, (data_type, nullable) in before['columns'].items():
        now = after['columns'].get(key)
        if now is None:
            lost.append(('column removed', key))
        elif now[0] != data_type or (nullable == 'YES' and now[1] == 'NO'):
            lost.append(('column changed', key, (data_type, nullable), now))
    for key, definition in before['indexes'].items():
        if after['indexes'].get(key) != definition:
            lost.append(('index removed or redefined', key))
    for kind in ('constraints',):
        lost += [(kind + ' removed', key) for key in before[kind] if after[kind].get(key) != before[kind][key]]
    for kind in ('functions', 'triggers', 'extensions', 'versions'):
        lost += [(kind + ' removed', key) for key in before[kind] - after[kind]]
    return lost


def assert_contiguous_versions(test, c, at_least=11):
    """The registered schema versions are exactly 1..N with N at least `at_least`: a new version may follow, none may be missing or collide."""
    versions = {row[0] if not isinstance(row, dict) else row['version'] for row in c.execute('SELECT version FROM memory.schema_versions').fetchall()}
    test.assertEqual(versions, set(range(1, max(versions) + 1)), 'versions 1..N with no gap')
    test.assertGreaterEqual(max(versions), at_least)


def migration_locks(store):
    """Run `store.migrate()` and return {relation: {lock modes}} held by its transaction when the whole migration is about to COMMIT."""
    held = {}

    class Probe(type(store)):
        @contextlib.contextmanager
        def transaction(self):
            with super().transaction() as c:
                yield c
                for row in c.execute("SELECT relation::regclass::text AS rel, mode FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='relation'").fetchall():
                    held.setdefault(row['rel'], set()).add(row['mode'])

    probe = Probe.__new__(Probe)
    probe.__dict__.update(store.__dict__)
    probe.migrate()
    return held


STRONG = {'ShareLock', 'ShareRowExclusiveLock', 'ExclusiveLock', 'AccessExclusiveLock'}  # every mode that blocks a writer, a reader, or both


def statements(text):
    """The SQL of a file without `--` comments and without string literals (so a column named `deleted` or a quoted word never matches)."""
    text = re.sub(r'--[^\n]*', '', text)
    text = re.sub(r"'(?:[^']|'')*'", "''", text)
    return text


def destructive(sql):
    """What in a piece of SQL (comments and literals already removed) destroys or tightens: DROP/TRUNCATE/DELETE/RENAME anywhere, and the unsafe clauses of any ALTER TABLE."""
    found = [m.group(0) for m in DESTRUCTIVE.finditer(sql)]
    for statement in sql.split(';'):
        if re.search(r'\bALTER\s+TABLE\b', statement, re.IGNORECASE):
            found += [m.group(0) for m in ALTER_UNSAFE.finditer(statement)]
    return found


def sql_findings(text):
    """Findings of a SQL file: the code itself plus every string literal that is SQL (`EXECUTE 'DROP ...'`)."""
    text = re.sub(r'--[^\n]*', '', text)
    found = destructive(statements(text))
    for literal in LITERAL.findall(text):
        literal = literal.replace("''", "'")
        if LITERAL_SQL.search(literal):
            found += destructive(statements(literal))
            found += destructive(re.sub(r"'[^']*'", "''", literal))
    return found


def python_findings(source, allowed=frozenset()):
    """Findings of a Python module: every string constant that holds destructive SQL, except the explicit allow-list (whitespace normalised)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and LITERAL_SQL.search(node.value):
            if ' '.join(node.value.split()) not in allowed:
                found += destructive(re.sub(r"'[^']*'", "''", node.value))
    return found


class StaticTests(unittest.TestCase):
    def test_the_rule_detects_destructive_statements(self):
        for sql in ('DROP TABLE memory.jobs;', 'drop index x;', 'TRUNCATE memory.jobs;', 'DELETE FROM memory.jobs;',
                    'ALTER TABLE memory.jobs ALTER COLUMN state TYPE text;', 'ALTER TABLE memory.jobs ALTER COLUMN state SET DATA TYPE text;',
                    'ALTER TABLE memory.jobs DROP COLUMN priority;', 'ALTER TABLE memory.jobs RENAME TO j;'):
            self.assertTrue(sql_findings(sql), sql)
        for sql in ('ALTER TABLE memory.jobs ADD COLUMN IF NOT EXISTS priority smallint NOT NULL DEFAULT 0;', 'CREATE INDEX IF NOT EXISTS x ON t(a) WHERE NOT deleted;',
                    'deleted boolean NOT NULL DEFAULT false', "SELECT 'the drop and truncate words' -- DROP TABLE",
                    'ALTER TABLE memory.jobs ADD COLUMN a text, ADD COLUMN b integer NOT NULL DEFAULT 0;'):
            self.assertEqual(sql_findings(sql), [], sql)

    def test_gap3_it_detects_what_used_to_slip_through(self):
        """Gap 3: each of these passed the previous rule."""
        for sql in ("DO $x$ BEGIN EXECUTE 'DROP TABLE memory.jobs'; END $x$;", "DO $x$ BEGIN EXECUTE format('DROP INDEX %I', 'a'); END $x$;",
                    "DO $x$ BEGIN EXECUTE 'DELETE FROM memory.jobs'; END $x$;", "DO $x$ BEGIN EXECUTE 'ALTER TABLE memory.jobs ALTER COLUMN state TYPE text'; END $x$;",
                    'ALTER TABLE memory.jobs ADD COLUMN IF NOT EXISTS a text, ALTER COLUMN state TYPE text;',
                    'ALTER TABLE memory.jobs ADD COLUMN IF NOT EXISTS a text,\n    ALTER COLUMN state SET DATA TYPE text;',
                    'ALTER TABLE memory.jobs ADD COLUMN a text, DROP COLUMN priority;', 'ALTER TABLE memory.jobs ADD COLUMN a text, RENAME COLUMN a TO b;',
                    'ALTER TABLE memory.jobs ADD COLUMN a text, ALTER COLUMN state SET NOT NULL;', 'ALTER TABLE memory.jobs ALTER state SET NOT NULL;',
                    'ALTER TABLE memory.jobs\n    ADD COLUMN a text,\n    ALTER COLUMN b SET NOT NULL;'):
            self.assertTrue(sql_findings(sql), sql)
        for source in ("c.execute('DELETE FROM memory.jobs')", 'c.execute("TRUNCATE memory.jobs")', "c.execute('truncate table memory.jobs')",
                       "c.execute('DELETE FROM memory.agent_corpus_entries WHERE corpus_id=%s', (1,))", "c.execute('ALTER TABLE memory.jobs ADD COLUMN a text, ALTER COLUMN b TYPE int')",
                       "c.execute('DROP TABLE x')", "SQL = ('ALTER TABLE memory.jobs '\n       'DROP COLUMN priority')"):
            self.assertTrue(python_findings(source), source)
        for source in ("c.execute('ALTER TABLE memory.jobs ADD COLUMN a text')", "c.execute('SELECT 1')", "'''Rows are truncated, never dropped.'''"):
            self.assertEqual(python_findings(source), [], source)
        allowed = {'DELETE FROM memory.agent_corpus_entries WHERE corpus_id=%s'}
        self.assertEqual(python_findings("c.execute('DELETE FROM  memory.agent_corpus_entries WHERE corpus_id=%s', (1,))", allowed), [])
        self.assertTrue(python_findings("c.execute('DELETE FROM memory.agent_corpus_entries')", allowed))  # the allow-list is the exact bounded statement

    def test_ca34_no_migration_statement_destroys_anything(self):
        for name in MIGRATION_SOURCES:
            text = (PACKAGE / name).read_text(encoding='utf-8')
            found = sql_findings(text) if name.endswith('.sql') else python_findings(text, ALLOWED_DELETES.get(name, frozenset()))
            self.assertEqual(found, [], name)


class VersionRegistrationTests(unittest.TestCase):
    """Behaviour of the registration of versions (it used to be a regular expression over `schema.sql`)."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'ver_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def test_every_version_registers_itself_once_and_a_repeated_migrate_does_not_overwrite_it(self):
        store = Store(self.dsn)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            assert_contiguous_versions(self, c, 11)
            # Move every registration into the past: a migration that rewrote its row (instead of leaving it) would show the present.
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
            before = c.execute('SELECT version,applied_at FROM memory.schema_versions ORDER BY version').fetchall()
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute('SELECT version,applied_at FROM memory.schema_versions ORDER BY version').fetchall(), before)

    def test_a_repeated_migrate_changes_nothing_in_the_catalog(self):
        store = Store(self.dsn)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            first = catalog_snapshot(c)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(catalog_snapshot(c), first)

    def test_the_additive_check_detects_what_a_destructive_migration_would_do(self):
        store = Store(self.dsn)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            before = catalog_snapshot(c)
            c.execute('ALTER TABLE memory.jobs DROP COLUMN priority')
            c.execute('DROP INDEX memory.memory_jobs_failed_code')
            c.execute("DELETE FROM memory.schema_versions WHERE version=11")
            after = catalog_snapshot(c)
        kinds = {item[0] for item in additive_violations(before, after)}
        self.assertEqual(kinds, {'column removed', 'index removed or redefined', 'versions removed'})
        self.assertEqual(additive_violations(before, before), [])


class FailedJobsIndexTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'fji_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def test_version_11_adds_a_partial_index_on_failed_jobs_and_is_idempotent(self):
        store = Store(self.dsn)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            definition = c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='memory' AND indexname='memory_jobs_failed_code'").fetchone()[0]
            self.assertRegex(definition, r"\(destination, error_code\) WHERE \(state = 'failed'")
            self.assertEqual(c.execute('SELECT count(*) FROM memory.schema_versions WHERE version=11').fetchone()[0], 1)
            before = c.execute("SELECT relfilenode::text, oid::text FROM pg_class WHERE relname='memory_jobs_failed_code'").fetchone()
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute("SELECT relfilenode::text, oid::text FROM pg_class WHERE relname='memory_jobs_failed_code'").fetchone(), before)
            self.assertEqual(c.execute('SELECT count(*) FROM memory.schema_versions WHERE version=11').fetchone()[0], 1)

    def test_the_scrape_query_of_failed_jobs_can_use_the_index_and_only_failed_rows_are_indexed(self):
        store = Store(self.dsn)
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
            for index in range(300):
                c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,error_code) "
                          "VALUES(%s,'p1',%s,1,repeat('a',64),'item','embed','embed',%s,%s)", (f'j{index}', f'i{index}', 'failed' if index % 3 == 0 else 'succeeded', 'provider_timeout' if index % 3 == 0 else None))
            c.execute('ANALYZE memory.jobs')
            c.execute('SET LOCAL enable_seqscan = off')
            plan = '\n'.join(row[0] for row in c.execute("EXPLAIN SELECT destination, error_code, count(*) FROM memory.jobs WHERE state='failed' GROUP BY destination, error_code").fetchall())
        self.assertIn('memory_jobs_failed_code', plan)


if __name__ == '__main__':
    unittest.main()
