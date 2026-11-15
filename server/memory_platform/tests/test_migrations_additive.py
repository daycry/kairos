"""CA-34: the migrations only ADD (no DROP, TRUNCATE, DELETE, RENAME, ALTER ... TYPE or SET NOT NULL), and the failed-jobs index of schema version 11 is additive and usable."""
import ast
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
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


STRONG = {'ShareLock', 'ShareRowExclusiveLock', 'ExclusiveLock', 'AccessExclusiveLock'}  # every mode that blocks a writer, a reader, or both


def section_tags():
    """The tag of every `DO $tag$ ... $tag$;` block of `schema.sql`, read from the file: a section added by a later version is measured without anybody listing it here."""
    tags = re.findall(r'^DO \$(\w+)\$', (PACKAGE / 'schema.sql').read_text(encoding='utf-8'), re.MULTILINE)
    assert len(tags) == len(set(tags)) and {'pgvector', 'fts', 'chunks', 'failedjobs', 'queueindexes', 'jobqueue'} <= set(tags), tags
    return tags


def schema_section(tag, guarded=True):
    """The `DO $tag$ ... $tag$;` block of `schema.sql` (one schema version), with the `SET LOCAL lock_timeout` that precedes it. `guarded=False` strips its
    `IF EXISTS ... END IF;` early return: the block as it would run without the guard (a positive control for the lock measurement)."""
    text = (PACKAGE / 'schema.sql').read_text(encoding='utf-8')
    block = re.search(r'DO \$%s\$.*?\$%s\$;' % (tag, tag), text, re.DOTALL).group(0)
    if not guarded:
        block = re.sub(r'IF EXISTS .*?END IF;', '', block, count=1, flags=re.DOTALL)
    return "SET LOCAL lock_timeout = '5s';\n" + block


def section_table_locks(psycopg, dsn, tag, guarded=True):
    """Run ONE section of `schema.sql` alone, on a database that is already migrated, and return {table: {lock modes}} held by its transaction before the COMMIT.
    Only tables are watched (an index is locked as a consequence of locking its table), every table of the schema `memory`: `documents`, `memory_items`, `embeddings`, `jobs`..."""
    with psycopg.connect(dsn) as c:
        c.execute(schema_section(tag, guarded))
        held = {}
        for name, mode in c.execute("SELECT r.relname, l.mode FROM pg_locks l JOIN pg_class r ON r.oid=l.relation WHERE l.pid=pg_backend_pid() AND l.locktype='relation' "
                                    "AND r.relnamespace='memory'::regnamespace AND r.relkind IN ('r','p')").fetchall():
            held.setdefault(name, set()).add(mode)
    return held


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


    def test_a_delete_in_any_migration_source_is_found_and_retention_is_not_a_migration_step(self):
        """Mutants over the real text of every migration source: one `DELETE` appended (a statement in `schema.sql`, a statement string in each Python module) must be found,
        so the rule cannot pass by looking at the wrong thing. The retention code (`admin prune-tables`) lives outside `MIGRATION_SOURCES` and nothing there refers to it."""
        for name in MIGRATION_SOURCES:
            text = (PACKAGE / name).read_text(encoding='utf-8')
            allowed = ALLOWED_DELETES.get(name, frozenset())
            if name.endswith('.sql'):
                self.assertEqual(sql_findings(text), [], name)
                self.assertTrue(sql_findings(text + "\nDELETE FROM memory.jobs WHERE state = 'failed';\n"), name)
                self.assertTrue(sql_findings(text + "\nDO $x$ BEGIN EXECUTE 'DELETE FROM memory.jobs'; END $x$;\n"), name)
            else:
                self.assertEqual(python_findings(text, allowed), [], name)
                self.assertTrue(python_findings(text + "\nc.execute('DELETE FROM memory.jobs WHERE state=%s', ('failed',))\n", allowed), name)
                self.assertTrue(python_findings(text + "\nc.execute('DELETE FROM memory.agent_corpus_entries')\n", allowed), name)  # the allow-list is the exact bounded statement
            self.assertNotIn('prune', text.lower(), name)
        # `Store.migrate()` itself (store_auth.py) is the entry of every migration: it never calls the retention code either.
        entry = (PACKAGE / 'store_auth.py').read_text(encoding='utf-8').lower()
        self.assertTrue('def migrate' in entry and 'prune' not in entry and 'retention' not in entry)
        self.assertNotIn('admin.py', MIGRATION_SOURCES)
        self.assertIn('DELETE FROM memory.', (PACKAGE / 'admin.py').read_text(encoding='utf-8'))  # the delete lives there, outside the migration sources

    def test_every_registration_of_a_version_leaves_an_existing_one_alone(self):
        """Versions 8 to 12 register themselves inside `DO` blocks after a `RETURN` that a migrated database never passes, so no behavioural test reaches them
        on a repeated migrate: the statement itself is checked, in every migration source (a bare INSERT would collide, a DO UPDATE would rewrite the date)."""
        registered = set()
        for name in MIGRATION_SOURCES:
            text = statements((PACKAGE / name).read_text(encoding='utf-8')) if name.endswith('.sql') else '\n'.join(
                node.value for node in ast.walk(ast.parse((PACKAGE / name).read_text(encoding='utf-8'))) if isinstance(node, ast.Constant) and isinstance(node.value, str))
            for statement in re.findall(r'INSERT\s+INTO\s+memory\.schema_versions\b[^;]*;', text, re.IGNORECASE):
                self.assertRegex(statement, r'(?i)\bON\s+CONFLICT\s*(\(\s*version\s*\))?\s+DO\s+NOTHING\s*;$', statement)
                registered.add(int(re.search(r'VALUES\s*\(\s*(\d+)\s*\)', statement, re.IGNORECASE).group(1)))
        self.assertTrue(set(range(1, 13)) <= registered, registered)


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
            assert_contiguous_versions(self, c, 12)
            # Move every registration into the past: a migration that rewrote its row (instead of leaving it) would show the present.
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
            before = c.execute('SELECT version,applied_at FROM memory.schema_versions ORDER BY version').fetchall()
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute('SELECT version,applied_at FROM memory.schema_versions ORDER BY version').fetchall(), before)

    def test_the_registrations_behind_the_guards_run_again_without_overwriting_one_that_exists(self):
        """Versions 8-10 are registered again when their row is gone (the block runs from the top); versions 11 and 12 are registered with their row ALREADY there when
        an index of theirs is missing: that is the only route that reaches an INSERT of a version with a conflict, and it must neither fail nor move the date."""
        store = Store(self.dsn)
        store.migrate()
        past = "timestamptz '2001-01-01 00:00:00+00'"
        with self.psycopg.connect(self.dsn) as c:
            c.execute(f'UPDATE memory.schema_versions SET applied_at={past}')
            c.execute('DELETE FROM memory.schema_versions WHERE version IN (8,9,10)')
            c.execute('DROP INDEX memory.memory_jobs_failed_code')
            c.execute('DROP INDEX memory.memory_jobs_claim')
        store.migrate()
        with self.psycopg.connect(self.dsn) as c:
            assert_contiguous_versions(self, c, 12)
            rows = dict(c.execute(f'SELECT version,applied_at > {past} FROM memory.schema_versions').fetchall())
            self.assertEqual({v: rows[v] for v in (8, 9, 10)}, {8: True, 9: True, 10: True}, 'a deleted registration is written again')
            self.assertEqual({v: rows[v] for v in (1, 5, 11, 12)}, {1: False, 5: False, 11: False, 12: False}, 'a registration that existed keeps its date')
            for index in ('memory_jobs_failed_code', 'memory_jobs_claim'):
                self.assertIsNotNone(c.execute("SELECT to_regclass(%s)", ('memory.' + index,)).fetchone()[0])

    def test_every_section_is_a_no_op_on_a_migrated_database_and_the_measure_sees_it_when_it_is_not(self):
        """Behind its guard a section takes no strong lock on any table (the earlier `ADD COLUMN IF NOT EXISTS` of versions 2 and 3 live outside the sections and are not
        measured here). Control: the same sections without their guard DO, so the measurement can fail."""
        Store(self.dsn).migrate()
        for tag in section_tags():  # every section of schema.sql, as the file has them
            held = section_table_locks(self.psycopg, self.dsn, tag)
            self.assertEqual({table: modes & STRONG for table, modes in held.items() if modes & STRONG}, {}, tag)
            unguarded = section_table_locks(self.psycopg, self.dsn, tag, guarded=False)
            self.assertTrue(any(modes & STRONG for modes in unguarded.values()), (tag, 'the measure must see the lock of the section without its guard', unguarded))
        for tag, table in (('pgvector', 'embeddings'), ('fts', 'documents'), ('fts', 'memory_items'), ('chunks', 'jobs')):
            self.assertIn('AccessExclusiveLock', section_table_locks(self.psycopg, self.dsn, tag, guarded=False).get(table, set()), (tag, table))
        for tag in ('jobqueue', 'failedjobs', 'queueindexes'):  # a CREATE INDEX of a table that exists blocks its writers (SHARE), `IF NOT EXISTS` or not
            self.assertIn('ShareLock', section_table_locks(self.psycopg, self.dsn, tag, guarded=False).get('jobs', set()), tag)

    def test_a_repeated_run_of_the_whole_schema_takes_no_strong_lock_on_jobs(self):
        """The manual promises that a repeated `admin migrate` does not block the writers of `memory.jobs`: the whole file, run again as `Store.migrate()` runs it (one
        transaction), holds no SHARE or stronger lock on that table before the COMMIT. `CREATE INDEX IF NOT EXISTS memory_job_queue` used to take SHARE on it."""
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            c.execute((PACKAGE / 'schema.sql').read_text(encoding='utf-8'))
            held = {row[0] for row in c.execute("SELECT l.mode FROM pg_locks l JOIN pg_class r ON r.oid=l.relation WHERE l.pid=pg_backend_pid() AND l.locktype='relation' "
                                                "AND r.relname='jobs' AND r.relnamespace='memory'::regnamespace").fetchall()}
        self.assertEqual(held & STRONG, set(), held)

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


class VectorIndexGuardTests(unittest.TestCase):
    """`migrate_vector_indexes` (Python, not a section of `schema.sql`) skips an HNSW index that already exists BEFORE it asks for the table lock: a repeated
    `admin migrate` neither rebuilds an HNSW index nor blocks the writers of `embeddings` and `embedding_chunks`."""
    ENV = {'MEMORY_VECTOR_INDEXES': 'alpha-model:3,nomic-embed-text:768'}

    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'hnsw_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def vector_index_locks(self):
        """Run ONLY `migrate_vector_indexes` on the migrated database and return {table: strong lock modes} held before the COMMIT."""
        from memory_platform.store_vectors import migrate_vector_indexes
        with self.psycopg.connect(self.dsn) as c:
            migrate_vector_indexes(c)
            held = {}
            for name, mode in c.execute("SELECT r.relname, l.mode FROM pg_locks l JOIN pg_class r ON r.oid=l.relation WHERE l.pid=pg_backend_pid() AND l.locktype='relation' "
                                        "AND r.relnamespace='memory'::regnamespace AND r.relkind IN ('r','p')").fetchall():
                if mode in STRONG:
                    held.setdefault(name, set()).add(mode)
        return held

    def hnsw_identity(self):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute("SELECT relname,relfilenode::text,oid::text FROM pg_class WHERE relnamespace='memory'::regnamespace AND relname LIKE '%hnsw%' ORDER BY relname").fetchall()

    def test_a_repeated_migrate_takes_no_strong_lock_and_rebuilds_no_hnsw_index(self):
        with patch.dict(os.environ, self.ENV):
            Store(self.dsn).migrate()
            first = self.hnsw_identity()
            self.assertEqual(len(first), 4, first)  # two models x (embeddings, embedding_chunks)
            Store(self.dsn).migrate()
            self.assertEqual(self.hnsw_identity(), first, 'no HNSW index was rebuilt')
            self.assertEqual(self.vector_index_locks(), {}, 'the guard asks for no table lock')

    def test_the_measure_sees_the_lock_when_an_index_is_missing_and_only_that_one_is_built(self):
        """Control: with one index gone the same call takes SHARE on its table (the measure can fail) and builds that index alone."""
        with patch.dict(os.environ, self.ENV):
            Store(self.dsn).migrate()
            first = self.hnsw_identity()
            with self.psycopg.connect(self.dsn) as c:
                lost = c.execute("SELECT indexname FROM pg_indexes WHERE schemaname='memory' AND tablename='embedding_chunks' AND indexname LIKE 'memory_chunk_hnsw_%' ORDER BY 1 LIMIT 1").fetchone()[0]
                c.execute(f'DROP INDEX memory.{lost}')
            held = self.vector_index_locks()
            self.assertIn('ShareLock', held.get('embedding_chunks', set()))
            self.assertNotIn('embeddings', held, 'the indexes that exist do not lock their table')
            after = {row[0]: row[1:] for row in self.hnsw_identity()}
            self.assertEqual(set(after), {row[0] for row in first})
            self.assertEqual({k: v for k, v in after.items() if k != lost}, {row[0]: row[1:] for row in first if row[0] != lost}, 'the others were not rebuilt')


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
