"""Semantic search over fragments: best fragment per item (CA-24, CA-25, CA-26), `matched_chunk`, authorization and routes."""
import asyncio
import hashlib
import json
import os
import random
import unittest
import uuid

from memory_platform import store_vectors
from memory_platform.chunking import chunk_text, embedding_text
from memory_platform.config import Settings
from memory_platform.errors import Forbidden, NotFound
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
from memory_platform.worker import Worker

MODEL = 'nomic-embed-text'
VOCABULARY = ['servidor', 'cluster', 'despliegue', 'copia', 'archivo', 'registro', 'cola', 'proceso', 'memoria', 'tarea', 'usuario', 'permiso',
              'sesion', 'token', 'indice', 'consulta', 'tabla', 'columna', 'fila', 'esquema', 'version', 'cambio', 'revision', 'entrega']
PHRASE = 'quimera cobalto zafiro nebulosa tungsteno'


def filler(characters, seed):
    generator = random.Random(seed)
    words, total = [], 0
    while total < characters:
        word = generator.choice(VOCABULARY)
        words.append(word)
        total += len(word) + 1
    text = ' '.join(words)
    return text[:characters]


def document_text(total, phrase_at, phrase, seed=1):
    base = filler(total, seed)
    return base[:phrase_at] + ' ' + phrase + ' ' + base[phrase_at:total - len(phrase) - 2]


class ChunkSearchTests(unittest.TestCase):
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        from memory_platform.auth import hash_password
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'cs_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.addCleanup(self.drop_database)
        self.store = Store(make_conninfo(dsn, dbname=self.name), embedding_enabled=True)
        self.store.migrate()
        self.pid = 'p-' + uuid.uuid4().hex[:10]
        with self.store.transaction() as c:
            aid = str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (aid, 'u-' + aid[:8], hash_password('fixture-password-123')))
        self.actor = {'id': aid, 'credential_type': 'bootstrap'}
        self.store.create_project(self.actor, {'id': self.pid, 'title': 'Chunk search'})
        self.store.set_policy(self.actor, self.pid, {'capture_mode': 'summary', 'temporal_projection': True})
        self.settings = Settings('unused', lease_seconds=60, request_timeout=30.0, embedding_query_timeout=30.0)
        self.provider = FakeEmbeddings(self.settings)

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def publish(self, content, title='Documento', version=1, document_id=None, project=None):
        document_id = document_id or str(uuid.uuid4())
        self.store.publish_document(self.actor, project or self.pid, {
            'document_id': document_id, 'version': version, 'title': title, 'content': content,
            'source': {'uri': 'fixture://chunk-search', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
            'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['fixture://review']}})
        return document_id

    def drain(self):
        worker = Worker(self.store, self.settings, {'embed': self.provider}, worker_id='chunk-search')

        async def run():
            while await worker.run_once():
                pass
        asyncio.run(run())

    def query(self, text):
        return asyncio.run(self.provider.embed(text, query=True))['embedding']

    def search(self, text, **options):
        return self.store.search_vectors(self.actor, [self.pid], self.query(text), MODEL, **options)

    def insert_chunks(self, project, item_id, vectors, version=1, model=MODEL, content='x'):
        """Fragments with chosen vectors (the item-level row too), bypassing the worker."""
        chunks = chunk_text(embedding_text('T', content)) or None
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,%s,repeat('a',64),%s::jsonb) ON CONFLICT DO NOTHING",
                      (project, item_id, version, json.dumps({'title': 'T', 'content': (content + ' ') * 60})))  # longer than any offset below: the fragments are partial
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector,chunked) VALUES(%s,%s,'document',%s,repeat('a',64),%s,%s,true)",
                      (project, item_id, version, model, vectors[0]))
            for ordinal, vector in enumerate(vectors):
                c.execute("INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding) VALUES(%s,%s,'document',%s,repeat('a',64),%s,%s,%s,%s,%s::vector)",
                          (project, item_id, version, model, ordinal, ordinal * 10, ordinal * 10 + 12, '[' + ','.join(repr(float(v)) for v in vector) + ']'))

    def test_a_phrase_at_character_forty_thousand_of_a_fifty_thousand_document_is_found_in_the_top_three(self):
        """CA-24: the whole path (worker, fragments, HNSW route, aggregation) with the deterministic offline provider."""
        content = document_text(50000, 40000, PHRASE)
        self.assertGreater(content.index(PHRASE), 39000)
        target = self.publish(content, title='Manual largo')
        for number in range(8):
            self.publish(document_text(3000, 1500, 'alfa%d beta%d gamma%d' % (number, number, number), seed=10 + number), title='Otro %d' % number)
        self.drain()
        text = embedding_text('Manual largo', content)
        position = text.index(PHRASE)
        expected = [c for c in chunk_text(text) if c.char_start <= position and position + len(PHRASE) <= c.char_end]
        self.assertTrue(expected)
        found = self.search(PHRASE, limit=10)
        ids = [hit['item_id'] for hit in found]
        self.assertIn(target, ids[:3], ids)
        hit = found[ids.index(target)]
        self.assertIn(hit['matched_chunk']['ordinal'], [c.ordinal for c in expected])
        chunk = chunk_text(text)[hit['matched_chunk']['ordinal']]
        self.assertEqual((hit['matched_chunk']['char_start'], hit['matched_chunk']['char_end']), (chunk.char_start, chunk.char_end))
        self.assertEqual(ids.count(target), 1)
        with self.store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.embedding_chunks WHERE item_id=%s', (target,)).fetchone()['n'], len(chunk_text(text)))

    def test_the_public_search_returns_matched_chunk_and_the_text_of_the_winning_fragment(self):
        content = document_text(30000, 22000, PHRASE)
        target = self.publish(content, title='Manual')
        self.publish(document_text(2000, 500, 'delta epsilon', seed=3), title='Corto')
        self.drain()
        retrieval = Retrieval(self.store, self.settings, self.provider)
        result = asyncio.run(retrieval.search(self.actor, {'project_ids': [self.pid], 'q': PHRASE, 'limit': 5}))
        item = next(i for i in result['items'] if i['item_id'] == target)
        chunk = item['matched_chunk']
        self.assertEqual(set(chunk), {'ordinal', 'char_start', 'char_end'})
        text = embedding_text('Manual', content)
        self.assertIn(PHRASE, text[chunk['char_start']:chunk['char_end']])
        self.assertIn(PHRASE, item['excerpt'])
        self.assertEqual(item['excerpt'], text[chunk['char_start']:chunk['char_end']].strip())  # the fragment itself, not the first 500 characters of the item
        self.assertLessEqual(len(item['excerpt']), 1500)
        self.assertEqual(item['ref'], f'documental:{self.pid}:{target}:1')  # the reference keeps its format
        self.assertEqual(result['backends']['semantic']['status'], 'ok')

    def test_an_item_appears_once_with_the_score_of_its_best_fragment(self):
        """CA-25."""
        query = [1.0, 0.0] + [0.0] * 766
        near, mid, far = [0.9, 0.1] + [0.0] * 766, [0.5, 0.5] + [0.0] * 766, [0.0, 1.0] + [0.0] * 766
        self.insert_chunks(self.pid, 'many', [far, near, mid, far])
        self.insert_chunks(self.pid, 'other', [[0.8, 0.2] + [0.0] * 766])
        found = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['many', 'other'])
        best = found[0]
        norm = (0.9 ** 2 + 0.1 ** 2) ** 0.5
        self.assertAlmostEqual(best['score'], 0.9 / norm, places=5)
        self.assertEqual(best['matched_chunk']['ordinal'], 1)
        self.assertEqual(found[1]['matched_chunk']['ordinal'], 0)

    def test_the_exact_route_aggregates_fragments_too(self):
        self.insert_chunks(self.pid, 'many', [[0.0, 1.0], [0.9, 0.1], [0.5, 0.5]], model='other-model')
        self.insert_chunks(self.pid, 'other', [[0.8, 0.2]], model='other-model')
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], 'other-model', limit=10)
        self.assertEqual([(hit['item_id'], hit['matched_chunk']['ordinal']) for hit in found], [('many', 1), ('other', 0)])
        self.assertEqual({hit['candidate_limit'] for hit in found}, {10000})

    def test_a_flood_of_matching_fragments_of_one_item_is_reported_as_truncated(self):
        """The fetch widens while a few items crowd it and is bounded: at its cap the answer says so instead of looking complete."""
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'flood', [[1.0, 0.0] + [0.0] * 766] * 60)
        self.insert_chunks(self.pid, 'quiet', [[0.0, 1.0] + [0.0] * 766])
        query = [1.0, 0.0] + [0.0] * 766
        widened = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=3)  # 15 -> 60 -> 240 fragments: the whole index
        self.assertEqual([hit['item_id'] for hit in widened], ['flood', 'quiet'])
        self.assertFalse(widened.candidates_truncated)
        with patch.object(store_vectors, 'CHUNK_FETCH_CAP', 30):
            found = self.store.search_vectors(self.actor, [self.pid], query, MODEL, limit=3)
        self.assertEqual([hit['item_id'] for hit in found].count('flood'), 1)
        self.assertTrue(found.candidates_truncated)
        self.assertTrue(all(hit['candidates_truncated'] for hit in found))
        calm = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=1)
        self.assertEqual([hit['item_id'] for hit in calm], ['flood'])
        self.assertFalse(calm.candidates_truncated)

    def test_a_new_version_never_returns_fragments_of_the_previous_one(self):
        """CA-26: before the new version is embedded nothing stale answers; afterwards only the new fragments."""
        old = document_text(9000, 6000, 'obsoleto vetusto anticuado caduco rancio')
        document_id = self.publish(old, title='Guia')
        self.drain()
        self.assertEqual([h['item_id'] for h in self.search('obsoleto vetusto anticuado caduco rancio')], [document_id])
        new = document_text(9000, 6000, 'moderno reciente actual novedoso flamante', seed=5)
        self.publish(new, title='Guia', version=2, document_id=document_id)
        self.assertEqual(self.search('obsoleto vetusto anticuado caduco rancio'), [], 'the previous version must not answer while the new one is not embedded')
        self.drain()
        found = self.search('moderno reciente actual novedoso flamante')
        self.assertEqual([(h['item_id'], h['version']) for h in found], [(document_id, 2)])
        text = embedding_text('Guia', new)
        chunk = found[0]['matched_chunk']
        self.assertIn('moderno reciente actual novedoso flamante', text[chunk['char_start']:chunk['char_end']])
        stale = self.search('obsoleto vetusto anticuado caduco rancio')
        self.assertTrue(all(h['version'] == 2 for h in stale))

    def test_hits_without_fragments_omit_matched_chunk_and_keep_their_excerpt(self):
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,'legacy',1,repeat('a',64),%s::jsonb)", (self.pid, '{"title":"Legacy","content":"contenido previo al troceado"}'))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,'legacy','document',1,repeat('a',64),%s,%s)", (self.pid, MODEL, [1.0] + [0.0] * 767))
        self.insert_chunks(self.pid, 'chunked', [[0.9, 0.1] + [0.0] * 766])
        found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10)
        by_id = {hit['item_id']: hit for hit in found}
        self.assertEqual(set(by_id), {'legacy', 'chunked'})
        self.assertNotIn('matched_chunk', by_id['legacy'])
        self.assertEqual(by_id['legacy']['excerpt'], 'contenido previo al troceado')
        self.assertEqual(by_id['chunked']['matched_chunk']['ordinal'], 0)
        self.assertEqual([hit['item_id'] for hit in found], ['legacy', 'chunked'])

    def test_a_resource_with_fragments_is_not_answered_twice_by_its_item_vector(self):
        self.insert_chunks(self.pid, 'both', [[0.0, 1.0] + [0.0] * 766, [1.0, 0.0] + [0.0] * 766])
        with self.store.transaction() as c:  # the item-level row says the opposite of the best fragment
            c.execute("UPDATE memory.embeddings SET vector=%s WHERE item_id='both'", ([0.0, 1.0] + [0.0] * 766,))
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=10)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['matched_chunk']['ordinal'], 1)
        self.assertAlmostEqual(found[0]['score'], 1.0, places=5)

    def test_fragments_follow_the_projects_authorization_and_deletions(self):
        other = 'o-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.actor, {'id': other, 'title': 'Other'})
        self.insert_chunks(other, 'foreign', [[1.0, 0.0] + [0.0] * 766])
        self.insert_chunks(self.pid, 'mine', [[0.9, 0.1] + [0.0] * 766])
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['mine'])
        with self.store.transaction() as c:
            from memory_platform.auth import hash_password
            reader = str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,false)', (reader, 'r-' + reader[:8], hash_password('fixture-password-123')))
        outsider = {'id': reader, 'credential_type': 'bootstrap'}
        with self.assertRaises((Forbidden, NotFound)):
            self.store.search_vectors(outsider, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL)
        with self.store.transaction() as c:
            c.execute("UPDATE memory.documents SET deleted=true WHERE project_id=%s AND id='mine'", (self.pid,))
        self.assertEqual(self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL), [])

    def test_a_search_without_any_fragment_in_scope_runs_the_previous_single_route(self):
        """Nothing changes before the backfill: one route, no probe-induced second ranking."""
        from unittest.mock import patch
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,'old',1,repeat('a',64),%s::jsonb)", (self.pid, '{"title":"Old","content":"x"}'))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,'old','document',1,repeat('a',64),%s,%s)", (self.pid, MODEL, [1.0] + [0.0] * 767))
        with patch.object(store_vectors, 'rank_chunks_ann', wraps=store_vectors.rank_chunks_ann) as chunk_ann, patch.object(store_vectors, 'rank_chunks_exact', wraps=store_vectors.rank_chunks_exact) as chunk_exact:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL)
        self.assertEqual([hit['item_id'] for hit in found], ['old'])
        self.assertEqual((chunk_ann.call_count, chunk_exact.call_count), (0, 0))
        self.assertNotIn('matched_chunk', found[0])


    def test_an_exhausted_fallback_budget_over_fragments_returns_the_index_rows_as_partial_and_keeps_the_transaction_usable(self):
        """Same contract as the item route: the bounded exact fallback is cancelled in its savepoint and the answer says so."""
        import time
        from unittest.mock import patch
        for number in range(4):
            self.insert_chunks(self.pid, f'item-{number}', [[1.0 - number * 0.1, number * 0.1] + [0.0] * 766, [0.2, 0.9] + [0.0] * 766])

        def slow(c, projects, model, dims, unit, categories, tags, size, arm=lambda cap=None: None):
            arm()
            c.execute('SELECT pg_sleep(10)')
        started = time.monotonic()
        with patch.object(store_vectors, 'exact_fallback_ms', return_value=300), patch.object(store_vectors, 'chunk_exact_rows', side_effect=slow) as fallback:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=10, deadline=time.monotonic() + 60)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(fallback.call_count, 1)
        self.assertEqual([hit['item_id'] for hit in found][:2], ['item-0', 'item-1'])
        self.assertEqual(len(found), 4)
        self.assertTrue(found.candidates_truncated and all(hit['candidates_truncated'] for hit in found))
        self.assertTrue(all(hit['matched_chunk']['ordinal'] in (0, 1) for hit in found))

    def test_once_everything_is_chunked_the_item_route_never_runs_and_no_fallback_is_paid(self):
        """Gap 1: with every resource chunked the item vectors cannot answer anything, so that route is skipped (it used to traverse the
        index up to its scan limit and then run the exact fallback on every query)."""
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'a', [[1.0, 0.0] + [0.0] * 766, [0.0, 1.0] + [0.0] * 766])
        self.insert_chunks(self.pid, 'b', [[0.5, 0.5] + [0.0] * 766])
        with patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann) as item_route, patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact) as item_exact, \
                patch.object(store_vectors, 'rank_chunks_ann', wraps=store_vectors.rank_chunks_ann) as chunk_route:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=2)
        self.assertEqual([hit['item_id'] for hit in found], ['a', 'b'])
        self.assertEqual((item_route.call_count, item_exact.call_count, chunk_route.call_count), (0, 0, 1))

    def legacy_document(self, item_id='legacy'):
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,1,repeat('a',64),%s::jsonb)", (self.pid, item_id, '{"title":"Legacy","content":"x"}'))
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,%s,'document',1,repeat('a',64),%s,%s)", (self.pid, item_id, MODEL, [1.0] + [0.0] * 767))

    def test_a_resource_still_without_fragments_is_answered_by_its_item_vector_next_to_the_chunked_ones(self):
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'chunked', [[0.9, 0.1] + [0.0] * 766])
        self.legacy_document()
        with patch.object(store_vectors, 'UNCHUNKED_ONLY_LIMIT', 0), patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann) as item_route:  # above the cap: the whole-scope route
            found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['legacy', 'chunked'])
        self.assertEqual(item_route.call_count, 1)

    def test_a_handful_of_resources_without_fragments_is_scored_by_itself_not_by_a_scan_of_the_scope(self):
        """Gap 2 (attempt 2): one failed resource must not give every query of the scope an item-vector traversal."""
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'chunked', [[0.9, 0.1] + [0.0] * 766])
        self.legacy_document()
        with patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann) as ann, patch.object(store_vectors, 'rank_exact', wraps=store_vectors.rank_exact) as exact:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['legacy', 'chunked'])
        self.assertEqual(ann.call_count, 0)
        self.assertEqual(exact.call_count, 1)
        self.assertEqual(exact.call_args.kwargs['only'], [(self.pid, 'legacy', 'document')])

    def test_the_exact_route_over_fragments_reports_more_than_the_element_limit_as_truncated(self):
        """Gap 8 (attempt 2, CA-11): more than EXACT_CANDIDATE_LIMIT ELEMENTS scored is `candidates_truncated`, whatever the fragment count."""
        from unittest.mock import patch
        for name in ('a', 'b', 'c'):
            self.insert_chunks(self.pid, name, [[1.0, 0.0]], model='other-model')
        self.assertFalse(self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], 'other-model', limit=10).candidates_truncated)
        with patch.object(store_vectors, 'EXACT_CANDIDATE_LIMIT', 2):
            found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0], 'other-model', limit=10)
        self.assertTrue(found.candidates_truncated)

    def test_an_old_unchunked_version_of_a_chunked_resource_does_not_wake_the_item_route(self):
        """Stale rows (a previous version nobody can read) must not make the item route run on every query."""
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'doc', [[1.0, 0.0] + [0.0] * 766])
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector) VALUES(%s,'doc','document',0,repeat('b',64),%s,%s)", (self.pid, MODEL, [1.0] + [0.0] * 767))
        with patch.object(store_vectors, 'rank_ann', wraps=store_vectors.rank_ann) as item_route:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['doc'])
        self.assertEqual(item_route.call_count, 0)

    def test_the_two_routes_share_one_exact_fallback_allowance(self):
        """Gap 12: not 2x MEMORY_VECTOR_EXACT_FALLBACK_MS. The item route spends it all; the fragment route then runs no fallback and says so."""
        import time
        from unittest.mock import patch
        self.insert_chunks(self.pid, 'chunked', [[0.9, 0.1] + [0.0] * 766])
        self.legacy_document()

        def slow(c, projects, model, dims, unit, categories, tags, size, arm=lambda cap=None: None, **kwargs):
            arm()
            c.execute('SELECT pg_sleep(10)')
        started = time.monotonic()
        with patch.object(store_vectors, 'UNCHUNKED_ONLY_LIMIT', 0), patch.object(store_vectors, 'exact_fallback_ms', return_value=300), patch.object(store_vectors, 'rank_exact', side_effect=slow) as item_fallback, \
                patch.object(store_vectors, 'chunk_exact_rows', side_effect=slow) as chunk_fallback:
            found = self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10, deadline=time.monotonic() + 60)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual((item_fallback.call_count, chunk_fallback.call_count), (1, 0))
        self.assertTrue(found.candidates_truncated)
        self.assertEqual({hit['item_id'] for hit in found}, {'legacy', 'chunked'})

    def test_an_element_found_by_both_routes_appears_once_with_its_best_score(self):
        """Gap 7: de-duplicated by element when the routes are merged."""
        self.insert_chunks(self.pid, 'both', [[0.0, 1.0] + [0.0] * 766, [0.6, 0.4] + [0.0] * 766])
        with self.store.transaction() as c:  # an inconsistent row (chunks present, flag off) reaches the item route as well
            c.execute("UPDATE memory.embeddings SET chunked=false,vector=%s WHERE item_id='both'", ([1.0, 0.0] + [0.0] * 766,))
        found = self.store.search_vectors(self.actor, [self.pid], [1.0, 0.0] + [0.0] * 766, MODEL, limit=10)
        self.assertEqual([hit['item_id'] for hit in found], ['both'])
        self.assertAlmostEqual(found[0]['score'], 1.0, places=5)

    def test_matched_chunk_only_when_the_fragment_is_not_the_whole_text_and_the_excerpt_is_bounded_without_the_title(self):
        """Gaps 8 and 13: short texts add no `matched_chunk` noise; the excerpt of a previous receipt never repeats the title nor exceeds MEMORY_CHUNK_CHARS."""
        with self.store.transaction() as c:
            for item_id, content in (('whole', 'texto corto'), ('old-receipt', 'palabra ' * 1500)):
                text = embedding_text('Titulo', content)
                c.execute("INSERT INTO memory.documents(project_id,id,version,canonical_hash,body) VALUES(%s,%s,1,repeat('a',64),%s::jsonb)", (self.pid, item_id, json.dumps({'title': 'Titulo', 'content': content})))
                c.execute("INSERT INTO memory.embeddings(project_id,item_id,resource_type,version,canonical_hash,model,vector,chunked) VALUES(%s,%s,'document',1,repeat('a',64),%s,%s,true)", (self.pid, item_id, MODEL, [1.0] + [0.0] * 767))
                # a receipt of the previous worker: ONE fragment over the first 8,000 characters
                c.execute("INSERT INTO memory.embedding_chunks(project_id,item_id,resource_type,version,canonical_hash,model,ordinal,char_start,char_end,embedding) VALUES(%s,%s,'document',1,repeat('a',64),%s,0,0,%s,%s::vector)",
                          (self.pid, item_id, MODEL, min(len(text), 8000), '[' + ','.join(['1.0'] + ['0.0'] * 767) + ']'))
        found = {hit['item_id']: hit for hit in self.store.search_vectors(self.actor, [self.pid], [1.0] + [0.0] * 767, MODEL, limit=10)}
        self.assertNotIn('matched_chunk', found['whole'])
        self.assertEqual(found['whole']['excerpt'], 'texto corto')
        self.assertEqual(found['old-receipt']['matched_chunk'], {'ordinal': 0, 'char_start': 0, 'char_end': 8000})
        self.assertLessEqual(len(found['old-receipt']['excerpt']), 1500)
        self.assertFalse(found['old-receipt']['excerpt'].startswith('Titulo'))

    def test_live_writes_are_claimed_before_older_backfill_jobs(self):
        """Gap 2: the ~40,000 jobs of `admin backfill-chunks` (priority 1) never go ahead of new content (priority 0), however old they are."""
        backfill = self.publish('contenido antiguo del relleno ' * 40, title='Relleno')
        live = self.publish('contenido nuevo escrito en vivo ' * 40, title='Vivo')
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET priority=1,available_at=clock_timestamp()-interval '1 hour' WHERE item_id=%s AND destination='embed'", (backfill,))
        self.assertEqual([self.store.claim_job('w1')['item_id'], self.store.claim_job('w1')['item_id']], [live, backfill])


if __name__ == '__main__':
    unittest.main()
