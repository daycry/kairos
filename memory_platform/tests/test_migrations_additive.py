"""CA-34: the migrations only ADD (no DROP, TRUNCATE, DELETE, RENAME, ALTER ... TYPE or SET NOT NULL), and the failed-jobs index of schema version 11 is additive and usable."""
import ast
import os
from pathlib import Path
import re
import unittest
import uuid

from memory_platform.store import Store

PACKAGE = Path(__file__).parents[1]
SCHEMA = PACKAGE / 'schema.sql'
DESTRUCTIVE = re.compile(r'\b(DROP|TRUNCATE|DELETE|RENAME)\b', re.IGNORECASE)
# Clauses of an `ALTER TABLE` that rewrite or tighten what exists, in ANY position of a multi-clause statement.
ALTER_UNSAFE = re.compile(r'\bALTER\s+(?:COLUMN\s+)?\S+\s+(?:SET\s+DATA\s+)?TYPE\b|\bSET\s+NOT\s+NULL\b', re.IGNORECASE)
# SQL kept in a literal (`EXECUTE 'DROP ...'`, `c.execute('DELETE FROM ...')`) is still SQL.
LITERAL_SQL = re.compile(r'(?:^|;)\s*TRUNCATE\b|\b(?:DROP\s+(?:TABLE|INDEX|COLUMN|SCHEMA|DATABASE|VIEW|CONSTRAINT|TYPE|EXTENSION|TRIGGER|FUNCTION)|DELETE\s+FROM|ALTER\s+TABLE)\b', re.IGNORECASE)
LITERAL = re.compile(r"'((?:[^']|'')*)'")
MIGRATION_SOURCES = ('schema.sql', 'agent_store.py', 'extended_store.py', 'corpus_answers.py', 'store_vectors.py')
# The only DELETEs allowed in the Python modules above: runtime replacement of the rows of ONE corpus (bounded by `corpus_id`), not a migration step.
ALLOWED_DELETES = {'agent_store.py': {'DELETE FROM memory.agent_corpus_entries WHERE corpus_id=%s', 'DELETE FROM memory.agent_corpus_queries WHERE corpus_id=%s'}}


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

    def test_every_version_block_registers_itself_without_overwriting(self):
        text = statements(SCHEMA.read_text(encoding='utf-8'))
        for version in (8, 9, 10, 11):
            self.assertRegex(text, r'INSERT INTO memory\.schema_versions\(version\) VALUES \(%d\) ON CONFLICT DO NOTHING' % version)


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
