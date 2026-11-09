"""HNSW on >= 2,000 768-d embeddings: plan, recall@10 against the exact cosine, and filtered scans."""
from contextlib import contextmanager
import json
import math
import os
import random
import unittest
import uuid
from unittest.mock import patch

from memory_platform.store import Store
from memory_platform import store_vectors

MODEL = 'nomic-embed-text'
DIMS = 768
SELECTED = 2000     # embeddings of the project the actor can read
OTHER = 600         # embeddings of a project the actor cannot read, interleaved in the same index
QUERIES = 20
RECALL_FLOOR = 0.95


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def clustered(count, seed, centers=40, noise=0.35):
    """Deterministic embedding-like data: documents around topic centers."""
    generator = random.Random(seed)
    middle = [[generator.gauss(0, 1) for _ in range(DIMS)] for _ in range(centers)]
    return [[c + noise * generator.gauss(0, 1) for c in middle[n % centers]] for n in range(count)], middle, generator


class Spy:
    def __init__(self, connection, statements):
        self.connection, self.statements = connection, statements

    def execute(self, query, params=None, **kwargs):
        self.statements.append((query, params))
        return self.connection.execute(query, params, **kwargs)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class VectorIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        from memory_platform.auth import hash_password
        cls.admin_dsn, cls.name = dsn, 'idx_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {cls.name}')
        cls.store = Store(make_conninfo(dsn, dbname=cls.name), embedding_enabled=True)
        cls.store.migrate()
        cls.pid, cls.other = 'p-' + uuid.uuid4().hex[:10], 'o-' + uuid.uuid4().hex[:10]
        with cls.store.transaction() as c:
            aid, bid = str(uuid.uuid4()), str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true),(%s,%s,%s,false)',
                      (aid, 'a-' + aid[:8], hash_password('fixture-password-123'), bid, 'b-' + bid[:8], hash_password('fixture-password-123')))
        cls.admin = {'id': aid, 'credential_type': 'bootstrap'}
        cls.outsider = {'id': bid, 'credential_type': 'bootstrap'}
        cls.store.create_project(cls.admin, {'id': cls.pid, 'title': 'Indexed corpus'})
        cls.store.create_project(cls.admin, {'id': cls.other, 'title': 'Other corpus'})
        with cls.store.transaction() as c:
            c.execute("INSERT INTO memory.project_grants(actor_id,project_id,permission) VALUES(%s,%s,'read')", (bid, cls.other))
        cls.corpus, centers, generator = clustered(SELECTED + OTHER, 11)
        with cls.store.transaction() as c:
            for number, vector in enumerate(cls.corpus):
                project = cls.pid if number < SELECTED else cls.other
                ident = f'd-{number:05d}'
                tags = ['rare'] if number % 130 == 7 else ['common']
                deleted = number % 97 == 5
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body,deleted) VALUES(%s,%s,1,repeat('a',64),jsonb_build_object('title',%s::text,'content','x','category','ops','tags',%s::jsonb),%s)",
                          (project, ident, ident, json.dumps(tags), deleted))
                c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',1,repeat('a',64),%s,%s)", (project, ident, MODEL, vector))
            c.execute('ANALYZE memory.embeddings')
            c.execute('ANALYZE memory.documents')
        cls.queries = [[c + 0.5 * generator.gauss(0, 1) for c in centers[n * 7 % len(centers)]] for n in range(QUERIES)]
        cls.visible = [n for n in range(SELECTED) if n % 97 != 5]

    @classmethod
    def tearDownClass(cls):
        import psycopg
        with psycopg.connect(cls.admin_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {cls.name} WITH (FORCE)')

    def exact_top(self, query, count=10, only=None):
        pool = self.visible if only is None else only
        return [f'd-{n:05d}' for n in sorted(pool, key=lambda n: -cosine(query, self.corpus[n]))[:count]]

    @contextmanager
    def captured(self, statements):
        original = self.store.transaction

        @contextmanager
        def spied():
            with original() as connection:
                yield Spy(connection, statements)
        with patch.object(self.store, 'transaction', spied):
            yield

    def test_plan_uses_the_hnsw_index_and_recall_at_10_matches_the_exact_cosine(self):
        from psycopg import sql
        statements = []
        with self.captured(statements):
            self.store.search_vectors(self.admin, [self.pid], self.queries[0], MODEL, limit=10)
        ranked = [(q, p) for q, p in statements if isinstance(q, sql.Composed) and 'memory.embeddings' in q.as_string(None) and 'ORDER BY' in q.as_string(None)]
        self.assertEqual(len(ranked), 1)
        with self.store.transaction() as c:
            for name, value in (('hnsw.iterative_scan', 'relaxed_order'), ('hnsw.max_scan_tuples', '20000'), ('hnsw.ef_search', '100')):
                c.execute('SELECT set_config(%s,%s,true)', (name, value))
            plan = '\n'.join(next(iter(row.values())) for row in c.execute(sql.SQL('EXPLAIN ') + ranked[0][0], ranked[0][1]).fetchall())
        self.assertIn('Index Scan using memory_embedding_hnsw_', plan, plan)
        exact, ann = (patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact), patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann))
        hits = total = 0
        with exact as exact_spy, ann:
            for query in self.queries:
                found = {hit['item_id'] for hit in self.store.search_vectors(self.admin, [self.pid], query, MODEL, limit=10)}
                hits += len(found & set(self.exact_top(query)))
                total += 10
        recall = hits / total
        print('HNSW_RECALL_RESULT ' + json.dumps({'rows': SELECTED + OTHER, 'readable_rows': len(self.visible), 'queries': QUERIES, 'k': 10, 'recall_at_10': round(recall, 4),
                                                  'exact_fallbacks': exact_spy.call_count, 'ef_search': 100, 'max_scan_tuples': 20000, 'iterative_scan': 'relaxed_order'}, sort_keys=True), flush=True)
        self.assertEqual(exact_spy.call_count, 0, 'the HNSW route must answer on its own here')
        self.assertGreaterEqual(recall, RECALL_FLOOR)

    def test_filters_keep_results_when_most_index_rows_are_not_visible(self):
        """Permission, project, deleted-version and tag filters are applied while scanning, not after a fixed top-k."""
        exact, ann = (patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact), patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann))
        rare = [n for n in self.visible if n % 130 == 7]
        self.assertGreaterEqual(len(rare), 10)
        with exact as exact_spy, ann as ann_spy:
            wide = self.store.search_vectors(self.admin, [self.pid], self.queries[3], MODEL, limit=10)
            narrow = self.store.search_vectors(self.admin, [self.pid], self.queries[3], MODEL, limit=10, tags=['rare'])
            hidden = self.store.search_vectors(self.outsider, [self.other], self.queries[3], MODEL, limit=10)
        self.assertEqual(ann_spy.call_count, 3)
        self.assertEqual(exact_spy.call_count, 0, 'iterative scan must fill the answer without the exact fallback')
        self.assertEqual(len(wide), 10)
        self.assertTrue(all(hit['project_id'] == self.pid for hit in wide))
        self.assertTrue(all(int(hit['item_id'][2:]) % 97 != 5 for hit in wide))
        self.assertEqual(len(narrow), 10)
        self.assertTrue(all(int(hit['item_id'][2:]) in set(rare) for hit in narrow))
        self.assertGreaterEqual(len({hit['item_id'] for hit in narrow} & set(self.exact_top(self.queries[3], 10, only=rare))), 9)
        self.assertTrue(all(hit['project_id'] == self.other for hit in hidden))
        from memory_platform.errors import Forbidden, NotFound
        with self.assertRaises((Forbidden, NotFound)):
            self.store.search_vectors(self.outsider, [self.pid], self.queries[3], MODEL)

    def test_a_tiny_project_inside_the_large_index_gets_all_its_hits_exactly(self):
        """The short-answer decision looks at the authorized rows only: 4 rows among 2,600 are ranked exactly."""
        tiny = 't-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.admin, {'id': tiny, 'title': 'Tiny corpus'})
        mine = [self.corpus[n] for n in (1, 2, 3, 4)]
        with self.store.transaction() as c:
            for number, vector in enumerate(mine):
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,1,repeat('a',64),jsonb_build_object('title','t','content','x','category','ops','tags','[]'::jsonb))", (tiny, f'tiny-{number}'))
                c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',1,repeat('a',64),%s,%s)", (tiny, f'tiny-{number}', MODEL, vector))
        query = self.queries[5]
        exact, ann = (patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact), patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann))
        with exact as exact_spy, ann:
            found = self.store.search_vectors(self.admin, [tiny], query, MODEL, limit=10)
        self.assertEqual(exact_spy.call_count, 1)
        self.assertEqual([hit['item_id'] for hit in found], [f'tiny-{n}' for n in sorted(range(4), key=lambda n: -cosine(query, mine[n]))])
        self.assertFalse(found.candidates_truncated)
