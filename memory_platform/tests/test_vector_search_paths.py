"""search_vectors on pgvector: HNSW route, exact route, deadlines, truncation flag and double write."""
from contextlib import contextmanager
import hashlib
import math
import os
import random
import time
import unittest
import uuid
from unittest.mock import patch

from memory_platform.errors import MemoryError
from memory_platform.store import Store
from memory_platform import store_vectors

MODEL = 'nomic-embed-text'


def vectors(count, dims, seed):
    generator = random.Random(seed)
    return [[generator.gauss(0, 1) for _ in range(dims)] for _ in range(count)]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class Spy:
    """Connection proxy that records SQL and delegates."""
    def __init__(self, connection, statements):
        self.connection, self.statements = connection, statements

    def execute(self, query, params=None, **kwargs):
        self.statements.append((str(query), params))
        return self.connection.execute(query, params, **kwargs)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class VectorSearchPathTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        from memory_platform.auth import hash_password
        # Own database: the shared test database holds thousands of unrelated (even identical) 768-d vectors.
        name = 'vec_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {name}')
        self.addCleanup(self.drop_database, dsn, name)
        self.store = Store(make_conninfo(dsn, dbname=name), embedding_enabled=True)
        self.store.migrate()
        self.pid = 'p-' + uuid.uuid4().hex[:10]
        with self.store.transaction() as c:
            aid = str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (aid, 'u-' + aid[:8], hash_password('fixture-password-123')))
        self.actor = {'id': aid, 'credential_type': 'bootstrap'}
        self.store.create_project(self.actor, {'id': self.pid, 'title': 'Isolated vector test'})
        self.store.set_policy(self.actor, self.pid, {'capture_mode': 'summary', 'temporal_projection': True})

    @staticmethod
    def drop_database(dsn, name):
        import psycopg
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')

    def add(self, vectors_, model=MODEL, prefix='doc', project=None):
        project = project or self.pid
        with self.store.transaction() as c:
            for number, vector in enumerate(vectors_):
                ident = f'{prefix}-{number:04d}'
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,1,repeat('a',64),jsonb_build_object('title',%s::text,'content','x','category','ops','tags',jsonb_build_array('t')))", (project, ident, ident))
                c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',1,repeat('a',64),%s,%s)", (project, ident, model, vector))

    def routes(self):
        """Patches observing which ranking route runs (call-through)."""
        return patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact), patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann)

    def spied_transaction(self, statements):
        original = self.store.transaction

        @contextmanager
        def spied():
            with original() as connection:
                yield Spy(connection, statements)
        return patch.object(self.store, 'transaction', spied)

    def test_indexed_model_and_dimension_use_the_hnsw_route_and_match_the_exact_cosine(self):
        corpus = vectors(80, 768, 1)
        self.add(corpus)
        query = [x + 0.3 * y for x, y in zip(corpus[3], vectors(1, 768, 2)[0])]  # clearly closest to doc-0003
        exact, ann = self.routes()
        with exact as exact_spy, ann as ann_spy:
            found = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=10)
        self.assertEqual((ann_spy.call_count, exact_spy.call_count), (1, 0))
        expected = [f'doc-{i:04d}' for i in sorted(range(80), key=lambda i: -cosine(query, corpus[i]))[:10]]
        # HNSW is approximate: the top hit must be exact and the top 10 must overlap almost fully (recall@10 over
        # 2,000 rows is asserted in test_vector_index).
        self.assertEqual(found[0]['item_id'], expected[0])
        self.assertGreaterEqual(len({hit['item_id'] for hit in found} & set(expected)), 9)
        for hit in found:
            self.assertAlmostEqual(hit['score'], cosine(query, corpus[int(hit['item_id'][4:])]), places=5)
            self.assertEqual(hit['candidate_limit'], 20000)
            self.assertFalse(hit['candidates_truncated'])

    def test_short_hnsw_answer_over_a_small_population_is_recomputed_exactly(self):
        corpus = vectors(40, 768, 7)
        self.add(corpus)
        with self.store.transaction() as c:
            c.execute("UPDATE memory.documents SET body=jsonb_set(body,'{tags}','[\"rare\"]') WHERE id IN ('doc-0005','doc-0017','doc-0033')")
        query = vectors(1, 768, 8)[0]
        exact, ann = self.routes()
        with exact as exact_spy, ann as ann_spy:
            found = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=10, tags=['rare'])
        self.assertEqual((ann_spy.call_count, exact_spy.call_count), (1, 1))
        expected = [f'doc-{i:04d}' for i in sorted((5, 17, 33), key=lambda i: -cosine(query, corpus[i]))]
        self.assertEqual([hit['item_id'] for hit in found], expected)
        self.assertEqual(found[0]['candidate_limit'], 10000)

    def test_other_dimension_or_model_uses_the_exact_route(self):
        self.add([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], prefix='two')
        self.add(vectors(5, 768, 3), model='other-model', prefix='other')
        exact, ann = self.routes()
        with exact as exact_spy, ann as ann_spy:
            two = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], MODEL)
            other = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 3)[0], 'other-model', limit=1)
        self.assertEqual((ann_spy.call_count, exact_spy.call_count), (0, 2))
        self.assertEqual([hit['item_id'] for hit in two], ['two-0000', 'two-0002', 'two-0001'])
        self.assertEqual(other[0]['item_id'], 'other-0000')
        self.assertEqual(two[0]['candidate_limit'], 10000)

    def test_exact_route_matches_the_previous_python_ranking_including_ties(self):
        points = [[1.0, 0.0], [2.0, 0.0], [0.0, 3.0], [1.0, 1.0], [-1.0, 0.0]]
        self.add(points)
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], MODEL, limit=10)
        previous = sorted(range(5), key=lambda i: (-max(-1.0, min(1.0, cosine([1.0, 0.0], points[i]))), 'documental', f'doc-{i:04d}'))
        self.assertEqual([hit['item_id'] for hit in found], [f'doc-{i:04d}' for i in previous])

    def test_exact_route_flags_truncation_beyond_ten_thousand_candidates(self):
        with self.store.transaction() as c:
            c.execute("""INSERT INTO memory.documents(project_id,id,version,canonical_hash,body)
                SELECT %s,'bulk-'||lpad(n::text,6,'0'),1,repeat('b',64),jsonb_build_object('title','Bulk '||n,'content','x') FROM generate_series(1,10050) n""", (self.pid,))
            c.execute("""INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector)
                SELECT project_id,id,'document',version,canonical_hash,%s,ARRAY[1.0::float8,(length(id)%%7)::float8+1] FROM memory.documents WHERE project_id=%s""", (MODEL, self.pid))
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.5], MODEL, limit=5)
        self.assertEqual(len(found), 5)
        self.assertTrue(all(hit['candidates_truncated'] and hit['candidate_limit'] == 10000 for hit in found))

    def test_expired_deadline_and_short_deadline_timeout(self):
        self.add([[1.0, 0.0]])
        with self.assertRaises(MemoryError) as raised:
            self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], MODEL, deadline=0.0)
        self.assertEqual((raised.exception.code, raised.exception.status), ('semantic_deadline_exceeded', 503))
        statements = []
        with self.spied_transaction(statements):
            self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], MODEL, deadline=time.monotonic() + 2.5)
        timeouts = [int(params[0]) for query, params in statements if 'statement_timeout' in query]
        # Re-armed before each statement with what is left, never the whole budget again.
        self.assertGreaterEqual(len(timeouts), 3)
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertTrue(all(1 <= value <= 2500 for value in timeouts))

    def test_hnsw_parameters_are_set_per_transaction_for_the_indexed_route_only(self):
        self.add(vectors(3, 768, 4))
        statements = []
        with self.spied_transaction(statements):
            self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 5)[0], MODEL)
        settings = {params[0]: params[1] for query, params in statements if 'set_config' in query and params and str(params[0]).startswith('hnsw.')}
        self.assertEqual(settings, {'hnsw.iterative_scan': 'relaxed_order', 'hnsw.max_scan_tuples': '20000', 'hnsw.ef_search': '100'})
        statements.clear()
        with self.spied_transaction(statements):
            self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], MODEL)
        self.assertFalse([1 for query, _ in statements if 'hnsw.' in query or 'hnsw.' in str(_)])

    def test_complete_job_writes_vector_and_embedding_in_one_statement(self):
        content = 'Synthetic vector double write'
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Double write', 'content': content, 'category': 'operations', 'tags': ['postgres'],
                    'source': {'uri': 'fixture://double-write', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'claim', 'evidence': ['fixture://review']}}
        self.store.publish_document(self.actor, self.pid, document)
        with self.store.transaction() as c:
            job = c.execute("SELECT * FROM memory.jobs WHERE project_id=%s AND destination='embed'", (self.pid,)).fetchone()
            c.execute("UPDATE memory.jobs SET state='running',fence=5,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (job['id'],))
        statements = []
        with self.spied_transaction(statements):
            vector = vectors(1, 768, 6)[0]
            self.assertTrue(self.store.complete_job(job['id'], 5, {'vector': vector, 'model': MODEL, 'canonical_hash': job['canonical_hash'], 'verified': True}))
        inserts = [query for query, _ in statements if 'INSERT INTO memory.embeddings' in query]
        self.assertEqual(len(inserts), 1)
        self.assertRegex(inserts[0], r'\(project_id,item_id,resource_type,version,canonical_hash,model,vector,embedding\)')
        with self.store.transaction() as c:
            row = c.execute('SELECT dims,vector_dims(embedding) AS embedded,array_length(vector,1) AS length FROM memory.embeddings WHERE project_id=%s', (self.pid,)).fetchone()
        self.assertEqual((row['dims'], row['embedded'], row['length']), (768, 768, 768))

    def other_project(self):
        other = 'o-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.actor, {'id': other, 'title': 'Other corpus'})
        return other

    def test_short_answer_is_judged_on_authorized_rows_only(self):
        """A small project inside a large shared index is answered exactly, whatever other projects hold."""
        other = self.other_project()
        self.add(vectors(150, 768, 20), prefix='big', project=other)
        mine = vectors(5, 768, 21)
        self.add(mine)
        query = vectors(1, 768, 22)[0]
        exact, ann = self.routes()
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 100), exact as exact_spy, ann as ann_spy:
            found = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=10)
        self.assertEqual((ann_spy.call_count, exact_spy.call_count), (1, 1))
        self.assertEqual([hit['item_id'] for hit in found], [f'doc-{i:04d}' for i in sorted(range(5), key=lambda i: -cosine(query, mine[i]))])
        self.assertFalse(found.candidates_truncated)
        self.assertTrue(all(hit['project_id'] == self.pid for hit in found))

    def stub_connection(self, ranking_rows):
        """Connection whose index scan answered `ranking_rows`; a separate population count would fail the test."""
        class Result:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

            def fetchone(self):
                return self.rows[0]

        class Savepoint:
            def __enter__(_):
                return _

            def __exit__(_, *exc):
                return False

        class Stub:
            def execute(_, query, params=None, **kwargs):
                text = str(query)
                if 'set_config' in text:
                    return Result([])
                assert 'SELECT count(*)' not in text, 'the separate population count must not exist'
                return Result(ranking_rows)

            def transaction(_):
                return Savepoint()
        return Stub()

    def test_short_or_empty_scan_over_a_large_authorized_population_is_truncated(self):
        """pgvector may stop at max_scan_tuples inside rows the caller cannot read: empty, yet truncated.

        The exact fallback reports `truncated` itself (more than EXACT_CANDIDATE_LIMIT current candidates): the
        index rows are returned flagged instead of the partial exact ranking.
        """
        unit = [1.0] + [0.0] * 767
        some = [{'project_id': self.pid, 'item_id': 'x', 'resource_type': 'document', 'version': 1, 'canonical_hash': 'h', 'score': 0.5}]
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 100), patch.object(store_vectors, 'rank_exact', return_value=(['partial'], 100, True)) as exact:
            rows, limit, truncated = store_vectors.rank_ann(self.stub_connection([]), [self.pid], MODEL, 768, unit, None, None, 10)
            self.assertEqual((rows, limit, truncated), ([], store_vectors.HNSW_MAX_SCAN_TUPLES, True))
            rows, limit, truncated = store_vectors.rank_ann(self.stub_connection(some), [self.pid], MODEL, 768, unit, None, None, 10)
            self.assertEqual((rows, limit, truncated), (some, store_vectors.HNSW_MAX_SCAN_TUPLES, True))
            self.assertEqual(exact.call_count, 2)  # one traversal per search: the exact route is the only count

    def test_short_scan_over_a_population_within_the_exact_limit_is_recomputed(self):
        unit = [1.0] + [0.0] * 767
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 100), patch.object(store_vectors, 'rank_exact', return_value=(['exact'], 100, False)) as exact:
            self.assertEqual(store_vectors.rank_ann(self.stub_connection([]), [self.pid], MODEL, 768, unit, None, None, 10), (['exact'], 100, False))
            exact.assert_called_once()

    def test_a_full_scan_never_runs_the_exact_fallback(self):
        unit = [1.0] + [0.0] * 767
        full = [{'project_id': self.pid, 'item_id': f'x{n}', 'resource_type': 'document', 'version': 1, 'canonical_hash': 'h', 'score': 0.5} for n in range(3)]
        with patch.object(store_vectors, 'rank_exact') as exact:
            self.assertEqual(store_vectors.rank_ann(self.stub_connection(full), [self.pid], MODEL, 768, unit, None, None, 3), (full, store_vectors.HNSW_MAX_SCAN_TUPLES, False))
            exact.assert_not_called()

    def test_short_answer_over_more_current_candidates_than_the_exact_limit_is_flagged_with_the_index_rows(self):
        """Real rows: 8 current candidates, exact limit patched to 5 -> the 8 index rows come back, truncated."""
        self.add(vectors(8, 768, 40))
        exact, ann = self.routes()
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 5), exact as exact_spy, ann:
            found = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 41)[0], MODEL, limit=10)
        self.assertEqual(exact_spy.call_count, 1)
        self.assertEqual(len(found), 8)
        self.assertTrue(found.candidates_truncated and all(hit['candidates_truncated'] and hit['candidate_limit'] == 20000 for hit in found))

    def slow_fallback(self):
        """rank_exact stand-in that arms the fallback budget and then overruns it."""
        def slow(c, projects, model, dims, unit, categories, tags, size, arm=lambda: None):
            arm()
            c.execute('SELECT pg_sleep(10)')
        return patch.object(store_vectors, 'rank_exact', side_effect=slow)

    def test_exhausted_fallback_budget_returns_the_index_rows_as_partial_and_keeps_the_transaction_usable(self):
        self.add(vectors(5, 768, 42))
        self.add(vectors(1, 768, 43), prefix='lone')
        statements = []
        started = time.monotonic()
        with patch.object(store_vectors, 'exact_fallback_ms', return_value=300), self.slow_fallback() as slow, self.spied_transaction(statements):
            found = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 44)[0], MODEL, limit=10, deadline=time.monotonic() + 60)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(slow.call_count, 1)
        # the same transaction served the final payload read after the savepoint was rolled back
        self.assertEqual(len(found), 6)
        self.assertTrue(found.candidates_truncated and all(hit['candidates_truncated'] and hit['candidate_limit'] == 20000 for hit in found))
        timeouts = [int(params[0]) for query, params in statements if 'statement_timeout' in query]
        self.assertIn(300, timeouts)  # min(what is left of the deadline, the fallback budget)
        self.assertTrue(all(1 <= value <= 60000 for value in timeouts))

    def test_exhausted_fallback_budget_without_a_deadline_still_degrades_to_partial(self):
        self.add(vectors(4, 768, 45))
        with patch.object(store_vectors, 'exact_fallback_ms', return_value=300), self.slow_fallback():
            found = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 46)[0], MODEL, limit=10)
        self.assertEqual(len(found), 4)
        self.assertTrue(found.candidates_truncated)

    def test_the_global_deadline_expiring_during_the_fallback_keeps_semantic_deadline_exceeded(self):
        self.add(vectors(4, 768, 47))
        with patch.object(store_vectors, 'exact_fallback_ms', return_value=30000), self.slow_fallback():
            with self.assertRaises(MemoryError) as raised:
                self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 48)[0], MODEL, limit=10, deadline=time.monotonic() + 1.0)
        self.assertEqual((raised.exception.code, raised.exception.status), ('semantic_deadline_exceeded', 503))

    def test_a_truncated_route_marks_the_results_object_and_every_hit(self):
        self.add(vectors(5, 768, 25))
        real = store_vectors.rank_ann

        def truncated_route(*args, **kwargs):
            rows, limit, _ = real(*args, **kwargs)
            return rows, limit, True
        with patch.object(store_vectors, 'rank_ann', side_effect=truncated_route):
            found = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 26)[0], MODEL, limit=3)
        self.assertEqual(len(found), 3)
        self.assertTrue(found.candidates_truncated and all(hit['candidates_truncated'] for hit in found))

    def test_population_count_uses_only_the_authorized_projects(self):
        """The fallback is the only traversal and it is scoped to the authorized projects."""
        other = self.other_project()
        self.add(vectors(30, 768, 27), prefix='big', project=other)
        self.add(vectors(2, 768, 28))
        statements = []
        with self.spied_transaction(statements):
            self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 29)[0], MODEL, limit=10)
        self.assertFalse([1 for query, _ in statements if 'SELECT count(*) AS n' in query])
        scans = [(query, params) for query, params in statements if 'WITH cand AS' in query]
        self.assertEqual(len(scans), 1)
        self.assertIn('e.project_id=ANY(%s)', scans[0][0])
        self.assertEqual(scans[0][1][2], [self.pid])
        self.assertIn('NOT d.deleted', scans[0][0])

    def test_withdrawn_and_old_rows_do_not_count_towards_the_exact_route_limit(self):
        self.add(vectors(150, 768, 30))
        with self.store.transaction() as c:
            c.execute("UPDATE memory.documents SET deleted=true WHERE project_id=%s AND id < 'doc-0120'", (self.pid,))
            c.execute("UPDATE memory.documents SET version=2 WHERE project_id=%s AND id = 'doc-0125'", (self.pid,))
        exact, ann = self.routes()
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 100), exact as exact_spy, ann:
            found = self.store.search_vectors(self.actor, [self.pid], vectors(1, 768, 31)[0], MODEL, limit=40)
        # 150 rows exist but only 29 are current: exact route, no truncation flag.
        self.assertEqual(exact_spy.call_count, 1)
        self.assertFalse(found.candidates_truncated)
        self.assertEqual(len(found), 29)

class ExactFallbackSettingTests(unittest.TestCase):
    def test_default_and_validation(self):
        from memory_platform.config import exact_fallback_ms
        self.assertEqual(exact_fallback_ms({}), 1500)
        self.assertEqual(exact_fallback_ms({'MEMORY_VECTOR_EXACT_FALLBACK_MS': ' 250 '}), 250)
        for bad in ('0', '-5', '1.5', 'abc', '', '600001', '\u0661\u0662\u0663'):
            with self.assertRaises(ValueError, msg=bad):
                exact_fallback_ms({'MEMORY_VECTOR_EXACT_FALLBACK_MS': bad})
