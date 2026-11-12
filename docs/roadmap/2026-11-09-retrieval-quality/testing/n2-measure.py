"""N2 measure: cost of the /metrics scrape queries on memory.jobs with a synthetic volume, with and without the partial index `memory_jobs_failed_code`.
The queue query reads only the non-terminal states (pending, running, unknown) through memory_job_queue(state, available_at); the failed-by-code query is the only one that
reads the historical `failed` rows (and the one the partial index serves). Also times the non-concurrent CREATE INDEX of schema version 11 on the populated table.
Runs inside the isolated harness container only (own temporary PostgreSQL and database)."""
import json, os, re, time, unittest, uuid
import psycopg
from psycopg.conninfo import make_conninfo
from memory_platform import observability
from memory_platform.store import Store
from memory_platform.tests.retrieval_eval.run import check_dsn, connect_dsn

FAILED = int(os.environ.get('N2_FAILED', '300000'))
SUCCEEDED = int(os.environ.get('N2_SUCCEEDED', '200000'))
PENDING = 50
CODES = ['provider_timeout', 'provider_unavailable', 'provider_rejected', 'embedding_invalid', 'superseded']
QUEUE = "SELECT state, destination, count(*) AS n FROM memory.jobs WHERE state IN ('pending','running','unknown') GROUP BY state, destination"
FAILEDQ = "SELECT destination, error_code, count(*) AS n FROM memory.jobs WHERE state='failed' GROUP BY destination, error_code"


def plan(c, sql):
    text = '\n'.join(r[0] for r in c.execute('EXPLAIN (ANALYZE, BUFFERS) ' + sql).fetchall())
    return {'execution_ms': float(re.search(r'Execution Time: ([\d.]+) ms', text).group(1)), 'plan': [l.strip()[:150] for l in text.split('\n')[:8]],
            'uses_failed_index': 'memory_jobs_failed_code' in text}


class Measure(unittest.TestCase):
    def runTest(self):
        base = os.environ['MEMORY_TEST_DSN']
        check_dsn(os.environ.get('MEMORY_DSN'), base)
        base = connect_dsn(base)
        name = 'n2_' + uuid.uuid4().hex[:10]
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        dsn = make_conninfo(base, dbname=name)
        report = {'failed_rows': FAILED, 'succeeded_rows': SUCCEEDED, 'pending_rows': PENDING, 'postgres': 'isolated container build, own temporary cluster'}
        try:
            store = Store(dsn)
            store.migrate()
            with psycopg.connect(dsn) as c:
                c.execute("INSERT INTO memory.projects(id,title) VALUES('p1','P1')")
                cols = "(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state,error_code)"
                codes = "(ARRAY['" + "','".join(CODES) + f"'])[1 + n % {len(CODES)}]"
                c.execute(f"INSERT INTO memory.jobs{cols} SELECT 'f'||n,'p1','f'||n,1,repeat('a',64),'item',CASE WHEN n%2=0 THEN 'embed' ELSE 'extract' END,'embed','failed',{codes} FROM generate_series(1,{FAILED}) n")
                c.execute(f"INSERT INTO memory.jobs{cols} SELECT 's'||n,'p1','s'||n,1,repeat('a',64),'item','embed','embed','succeeded',NULL FROM generate_series(1,{SUCCEEDED}) n")
                c.execute(f"INSERT INTO memory.jobs{cols} SELECT 'p'||n,'p1','p'||n,1,repeat('a',64),'item','embed','embed','pending',NULL FROM generate_series(1,{PENDING}) n")
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute('VACUUM ANALYZE memory.jobs')
            def stage(label):
                with psycopg.connect(dsn) as c:
                    plan(c, FAILEDQ)  # warm
                    report[label] = {'queue_depth_query': plan(c, QUEUE), 'failed_query': plan(c, FAILEDQ),
                                     'index_bytes': c.execute("SELECT coalesce(pg_relation_size('memory.memory_jobs_failed_code'),0)").fetchone()[0] if c.execute("SELECT to_regclass('memory.memory_jobs_failed_code')").fetchone()[0] else None,
                                     'table_bytes': c.execute("SELECT pg_total_relation_size('memory.jobs')").fetchone()[0]}
                observability.reset_queue_cache()
                started = time.monotonic()
                ok = observability.refresh_queue_depth(store)
                report[label]['refresh_queue_depth_ok'] = ok
                report[label]['refresh_queue_depth_ms'] = round((time.monotonic() - started) * 1000, 1)
                report[label]['scrape_success_gauge'] = observability.REGISTRY.get_sample_value('kairos_jobs_queue_scrape_success')
                report[label]['queue_depth_pending_embed'] = observability.REGISTRY.get_sample_value('kairos_jobs_queue_depth', {'state': 'pending', 'destination': 'embed'})
                report[label]['jobs_failed_provider_timeout_embed'] = observability.REGISTRY.get_sample_value('kairos_jobs_failed', {'destination': 'embed', 'code': 'provider_timeout'})
            stage('with_index')
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute('DROP INDEX memory.memory_jobs_failed_code')  # isolated measurement database only
            stage('without_index')
            # With a 1 ms timeout both reads fail (queue depth -1, scrape_success 0): this run only shows that a timeout keeps the last good values.
            # That each read fails on its own (split transactions) is proven by test_metrics, not by this measurement.
            old = observability.QUEUE_STATEMENT_TIMEOUT_MS
            observability.QUEUE_STATEMENT_TIMEOUT_MS = 1
            try:
                observability.reset_queue_cache()
                observability.QUEUE_DEPTH.labels('pending', 'embed').set(-1)
                ok = observability.refresh_queue_depth(store)
                report['timeout_1ms_without_index'] = {'ok': ok, 'queue_depth_pending_embed': observability.REGISTRY.get_sample_value('kairos_jobs_queue_depth', {'state': 'pending', 'destination': 'embed'}),
                                                        'scrape_success_gauge': observability.REGISTRY.get_sample_value('kairos_jobs_queue_scrape_success')}
            finally:
                observability.QUEUE_STATEMENT_TIMEOUT_MS = old
            # Window of the version 11 block: CREATE INDEX (SHARE lock on memory.jobs, writes wait) on the populated table, as `migrate` runs it, inside a transaction.
            with psycopg.connect(dsn) as c:
                started = time.monotonic()
                c.execute("CREATE INDEX IF NOT EXISTS memory_jobs_failed_code ON memory.jobs(destination, error_code) WHERE state = 'failed'")
                report['create_index_ms'] = round((time.monotonic() - started) * 1000, 1)
        finally:
            with psycopg.connect(base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
        print('N2_RESULT ' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.defaultTestLoader.discover = lambda *a, **k: unittest.TestSuite([Measure()])
    from memory_platform.tests import run_postgres
    run_postgres.main()
