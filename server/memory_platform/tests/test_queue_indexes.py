"""CA-13: the job queue has partial indexes (schema version 12) that a migrated and a new database share, and `claim_job` reads the queue through them."""
import os
from pathlib import Path
import random
import unittest
import uuid

from memory_platform.store import Store
from memory_platform.store_jobs import CLAIM_EXPIRED, CLAIM_WAITING, FAIL_EXHAUSTED, next_claimable
from memory_platform.tests.test_migrations_additive import additive_violations, assert_contiguous_versions, catalog_snapshot

SCHEMA = Path(__file__).parents[1] / 'schema.sql'
VERSION_12 = '-- queue-indexes (schema version 12)'


def schema_before_version_12():
    """`schema.sql` as it stood at version 11: everything before the section of version 12 (the whole text when that section does not exist yet)."""
    return SCHEMA.read_text(encoding='utf-8').split(VERSION_12)[0]


class QueueDatabase(unittest.TestCase):
    """A database of its own per test: the queue holds only what the test seeds."""
    prefix = 'qix_'
    create_options = ''

    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = self.prefix + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name} {self.create_options}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def seed_version_11(self):
        """A database exactly as the previous release leaves it (versions 1 to 11), with a project and jobs in every state."""
        from memory_platform.agent_store import migrate_agent_schema
        from memory_platform.corpus_answers import migrate_corpus_answers
        from memory_platform.extended_store import migrate_extended_schema
        from memory_platform.store_vectors import migrate_vector_indexes
        with self.psycopg.connect(self.dsn) as c:
            c.execute(schema_before_version_12())
            migrate_vector_indexes(c)
            migrate_agent_schema(c)
            migrate_extended_schema(c)
            migrate_corpus_answers(c)
            self.assertEqual({v for (v,) in c.execute('SELECT version FROM memory.schema_versions').fetchall()}, set(range(1, 12)), 'the fixture must be version 11')
            c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
            for index, state in enumerate(('pending', 'running', 'succeeded', 'failed', 'unknown', 'succeeded')):
                c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,attempts,lease_until) "
                          "VALUES(%s,'p1',%s,1,repeat('a',64),'item','embed','upsert',%s,%s,%s)",
                          (f'j{index}', f'i{index}', state, index, '2001-01-01T00:00:00Z' if state == 'running' else None))


class QueueIndexMigrationTests(QueueDatabase):
    def indexes(self, c):
        return {name: definition for name, definition in c.execute("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='memory' AND tablename='jobs'").fetchall()}

    def test_a_database_at_version_11_reaches_12_with_both_indexes_and_no_row_or_column_changes(self):
        self.seed_version_11()
        with self.psycopg.connect(self.dsn) as c:
            before = catalog_snapshot(c)
            rows = c.execute('SELECT md5(string_agg(to_jsonb(j)::text, $$,$$ ORDER BY id)), count(*) FROM memory.jobs j').fetchone()
            self.assertNotIn('memory_jobs_claim', self.indexes(c))
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            after = catalog_snapshot(c)
            self.assertEqual(c.execute('SELECT md5(string_agg(to_jsonb(j)::text, $$,$$ ORDER BY id)), count(*) FROM memory.jobs j').fetchone(), rows, 'no job row changed')
            assert_contiguous_versions(self, c, 12)
            self.assertEqual(c.execute('SELECT count(*) FROM memory.schema_versions WHERE version=12').fetchone()[0], 1)
            indexes = self.indexes(c)
        self.assertEqual(additive_violations(before, after), [], 'version 12 only adds')
        self.assertEqual({k: v for k, v in after['columns'].items() if k[0] == 'jobs'}, {k: v for k, v in before['columns'].items() if k[0] == 'jobs'}, 'no column of jobs changed')
        self.assertEqual({k for k in set(after['indexes']) - set(before['indexes']) if k[0] == 'jobs'}, {('jobs', 'memory_jobs_claim'), ('jobs', 'memory_jobs_running_lease')})  # the indexes of other tables are those of later versions (13)
        self.assertIn('memory_job_queue', indexes, 'the index of version 1 stays')
        claim = indexes['memory_jobs_claim']
        self.assertRegex(claim, r"\(priority, available_at, created_at, id\) WHERE")
        self.assertIn("'pending'", claim)
        self.assertIn("'unknown'", claim)
        self.assertNotIn("'running'", claim)
        self.assertRegex(indexes['memory_jobs_running_lease'], r"\(lease_until\) WHERE \(state = 'running'::text\)")

    def test_a_new_database_and_a_migrated_one_have_the_same_catalog(self):
        """Compared from the catalog (columns, indexes, constraints, functions, triggers, extensions, versions), not from the SQL text."""
        self.seed_version_11()
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            migrated = catalog_snapshot(c)
        fresh = QueueIndexMigrationTests('test_a_new_database_and_a_migrated_one_have_the_same_catalog')
        fresh.setUp()
        try:
            Store(fresh.dsn).migrate()
            with fresh.psycopg.connect(fresh.dsn) as c:
                new = catalog_snapshot(c)
        finally:
            fresh.doCleanups()
        self.assertEqual(new, migrated)
        self.assertIn(('jobs', 'memory_jobs_claim'), new['indexes'])

    def test_a_repeated_migrate_does_not_rebuild_the_queue_indexes_nor_register_again(self):
        Store(self.dsn).migrate()
        identity = lambda c: c.execute("SELECT relname,relfilenode::text,oid::text FROM pg_class WHERE relname IN ('memory_jobs_claim','memory_jobs_running_lease') ORDER BY relname").fetchall()
        with self.psycopg.connect(self.dsn) as c:
            first = identity(c)
            self.assertEqual(len(first), 2)
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(identity(c), first)
            self.assertEqual(c.execute("SELECT count(*) FROM memory.schema_versions WHERE version=12 AND applied_at < timestamptz '2002-01-01'").fetchone()[0], 1)

    def test_a_lost_index_is_rebuilt_and_the_registered_version_keeps_its_date(self):
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            c.execute("UPDATE memory.schema_versions SET applied_at=timestamptz '2001-01-01 00:00:00+00'")
            c.execute('DROP INDEX memory.memory_jobs_running_lease')
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.assertIn('memory_jobs_running_lease', self.indexes(c))
            self.assertEqual(c.execute("SELECT count(*) FROM memory.schema_versions WHERE version=12 AND applied_at < timestamptz '2002-01-01'").fetchone()[0], 1)


# The statement the claim used before schema version 12: both sets under one `OR`.
OLD_CLAIM = ("SELECT * FROM memory.jobs WHERE (state IN ('pending','unknown') AND available_at<=clock_timestamp()) OR (state='running' AND lease_until<clock_timestamp()) "
             "ORDER BY priority,available_at,created_at,id FOR UPDATE SKIP LOCKED LIMIT 1")
INSERT_JOB = ("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,attempts,available_at,created_at,lease_until,priority) "
              "VALUES(%s,'p1',%s,1,repeat('a',64),'item','embed','upsert',%s,%s,%s,%s,%s,%s)")


def plan_nodes(c, sql, params=None):
    """Every node of the plan of `sql` (`EXPLAIN (FORMAT JSON)`, nothing is run): [(node type, index name or None)]."""
    found = []

    def walk(node):
        found.append((node['Node Type'], node.get('Index Name')))
        for child in node.get('Plans', []):
            walk(child)
    walk(c.execute('EXPLAIN (FORMAT JSON) ' + sql, params).fetchone()[0][0]['Plan'])
    return found


def kinds(nodes):
    return {kind for kind, _ in nodes}


def indexes(nodes):
    return {name for _, name in nodes if name}


class QueuePlanTests(QueueDatabase):
    """CA-13: with 10,000 finished jobs in the table, the claim reads the live part of the queue through the partial indexes."""
    TERMINAL, WAITING = 10000, 2000

    def seed(self, c):
        c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
        c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,attempts,available_at,created_at,priority) "
                  "SELECT 't'||g,'p1','ti'||g,1,repeat('a',64),'item','embed','upsert',CASE WHEN g%%5=0 THEN 'failed' ELSE 'succeeded' END,1,"
                  "timestamptz '2020-01-01'+g*interval '1 minute',timestamptz '2020-01-01'+g*interval '1 minute',0 FROM generate_series(1,%s) g", (self.TERMINAL,))
        c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,attempts,available_at,created_at,priority) "
                  "SELECT 'w'||g,'p1','wi'||g,1,repeat('a',64),'item','embed','upsert',CASE WHEN g%%7=0 THEN 'unknown' ELSE 'pending' END,0,"
                  "timestamptz '2021-01-01'+g*interval '1 second',timestamptz '2021-01-01'+g*interval '1 second',g%%2 FROM generate_series(1,%s) g", (self.WAITING,))
        for index in range(40):
            c.execute(INSERT_JOB, (f'r{index}', f'ri{index}', 'running', 1 + index % 4, '2021-01-01T00:00:00Z', '2021-01-01T00:00:00Z',
                                   '2000-01-01T00:00:00Z' if index % 2 else '2999-01-01T00:00:00Z', 0))
        c.execute('ANALYZE memory.jobs')
        self.assertEqual(c.execute("SELECT count(*) FROM memory.jobs WHERE state IN ('succeeded','failed')").fetchone()[0], self.TERMINAL)

    def test_the_waiting_probe_reads_the_claim_index_in_order_and_never_sorts_the_backlog(self):
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn) as c:
            self.seed(c)
            nodes = plan_nodes(c, CLAIM_WAITING)
            self.assertIn(('Index Scan', 'memory_jobs_claim'), nodes, nodes)
            self.assertFalse({'Seq Scan', 'Sort', 'Bitmap Heap Scan'} & kinds(nodes), nodes)
            # Controls: the measure can fail. The statement it replaced sorts the live rows, and without the index the probe is no longer the ordered index read.
            old = plan_nodes(c, OLD_CLAIM)
            self.assertTrue({'Seq Scan', 'Sort'} & kinds(old), old)
            c.execute('DROP INDEX memory.memory_jobs_claim')
            without = plan_nodes(c, CLAIM_WAITING)
            self.assertNotIn('memory_jobs_claim', indexes(without))
            self.assertTrue({'Seq Scan', 'Sort'} & kinds(without), without)

    def test_the_expired_probe_and_the_exhausted_statement_use_an_index_and_the_lease_index_is_usable(self):
        Store(self.dsn).migrate()
        statements = ((CLAIM_EXPIRED, None), (FAIL_EXHAUSTED, (3,)))
        with self.psycopg.connect(self.dsn) as c:
            self.seed(c)
            for sql, params in statements:
                nodes = plan_nodes(c, sql, params)
                self.assertNotIn('Seq Scan', kinds(nodes), (sql, nodes))
                self.assertTrue(indexes(nodes) & {'memory_jobs_running_lease', 'memory_job_queue'}, (sql, nodes))
            # With the index of version 1 out of the way the planner takes the lease index: it can serve both statements.
            c.execute('DROP INDEX memory.memory_job_queue')
            for sql, params in statements:
                nodes = plan_nodes(c, sql, params)
                self.assertIn('memory_jobs_running_lease', indexes(nodes), (sql, nodes))
                self.assertNotIn('Seq Scan', kinds(nodes), (sql, nodes))
            # Control: with neither index both statements read the whole table.
            c.execute('DROP INDEX memory.memory_jobs_running_lease')
            for sql, params in statements:
                self.assertIn('Seq Scan', kinds(plan_nodes(c, sql, params)), sql)


class ClaimOrder:
    """The two probes pick exactly what one ordered query over both sets picks, ties on (priority, available_at, created_at) included."""
    ELIGIBLE = "(state IN ('pending','unknown') AND available_at<=clock_timestamp()) OR (state='running' AND lease_until<clock_timestamp())"
    TIE_GROUP = (('tie-B', 'pending', None), ('tie-a', 'running', '2000-01-01T00:00:00Z'), ('tie-C', 'unknown', None), ('tie-b', 'running', '2000-01-01T00:00:00Z'))
    FIRST_FOUR = ()

    def seed_mixed_queue(self, c):
        generator = random.Random(20261115)
        c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
        days = ['2021-01-0%dT00:00:00Z' % day for day in range(1, 5)]
        names = [letter + str(number) for letter in 'aBcDeFgH' for number in range(1, 8)]
        generator.shuffle(names)
        for index, name in enumerate(names):
            kind = ('pending', 'unknown', 'expired', 'live', 'failed', 'succeeded', 'future')[index % 7]
            state = {'expired': 'running', 'live': 'running', 'future': 'pending'}.get(kind, kind)
            lease = {'expired': '2000-01-01T00:00:00Z', 'live': '2999-01-01T00:00:00Z'}.get(kind)
            available = '2999-01-01T00:00:00Z' if kind == 'future' else generator.choice(days)
            c.execute(INSERT_JOB, (name, 'item-' + name, state, 1 if state == 'running' else 0, available, generator.choice(days[:2]), lease, generator.choice((0, 0, 1))))
        # An explicit tie: same priority, available_at and created_at (the earliest of the queue), waiting jobs and expired leases, with ids that a collation orders its own way.
        for name, state, lease in self.TIE_GROUP:
            c.execute(INSERT_JOB, (name, 'item-' + name, state, 1 if state == 'running' else 0, '2020-06-01T00:00:00Z', '2020-06-01T00:00:00Z', lease, 0))

    def test_the_two_probes_claim_in_the_same_order_as_one_ordered_query(self):
        Store(self.dsn).migrate()
        with self.psycopg.connect(self.dsn, row_factory=self.psycopg.rows.dict_row) as c:  # dict rows, as the store's own connections
            self.seed_mixed_queue(c)
            reference = [row['id'] for row in c.execute(f'SELECT id FROM memory.jobs WHERE {self.ELIGIBLE} ORDER BY priority,available_at,created_at,id').fetchall()]
            self.assertGreater(len(reference), 20)
            claimed = []
            while True:
                row = next_claimable(c)
                if not row:
                    break
                claimed.append(row['id'])
                c.execute("UPDATE memory.jobs SET state='succeeded',lease_until=NULL WHERE id=%s", (row['id'],))
            self.assertEqual(claimed, reference)
            self.assertEqual(claimed[:4], list(self.FIRST_FOUR))
            self.after_equivalence(claimed)

    def after_equivalence(self, claimed):
        pass


class ClaimOrderTests(ClaimOrder, QueueDatabase):
    """The default collation of the test server (C: byte order, uppercase first)."""
    FIRST_FOUR = ('tie-B', 'tie-C', 'tie-a', 'tie-b')


class IcuClaimOrderTests(ClaimOrder, QueueDatabase):
    """An ICU database, where 'a' sorts before 'B' and Python's `<` says the opposite: the tie between a waiting job and an expired lease follows the database."""
    create_options = "TEMPLATE template0 ENCODING 'UTF8' LOCALE_PROVIDER icu ICU_LOCALE 'en-US' LOCALE 'C'"
    prefix = 'icu_'
    FIRST_FOUR = ('tie-a', 'tie-b', 'tie-B', 'tie-C')

    def after_equivalence(self, claimed):
        self.assertNotEqual(claimed[:4], sorted(claimed[:4]), 'the database order differs from the one of Python, so the test can tell them apart')


if __name__ == '__main__':
    unittest.main()
