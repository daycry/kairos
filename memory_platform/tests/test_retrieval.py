import asyncio
import threading
import time
import unittest
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import replace
from memory_platform.config import Settings
from memory_platform.retrieval import Retrieval, external_ref
from memory_platform.errors import NotFound, MemoryError
from memory_platform import models as m


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Mock()
        self.store.list_documents.return_value = []
        self.store.get_policy.return_value = {'temporal_projection': False}
        self.row = {'ref': 'episodic:a:uuid:1', 'project_id': 'a', 'item_id': 'uuid', 'version': 1, 'layer': 'episodic', 'title': 'Validated correction',
                    'excerpt': 'é'*500, 'content': 'é'*500, 'validation_status': 'validated', 'payload': {'content': 'é'*500}}
        self.store.search_items.return_value = [self.row]
        self.store.get_item.return_value = self.row
        self.store.search_native_facts.return_value = []
        self.store.search_documents.return_value = []
        self.store.has_vectors.return_value = False
        self.embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True}))
        self.retrieval = Retrieval(self.store, Settings('unused', request_timeout=5), self.embeddings)

    async def test_trigram_fallback_hits_are_reported_in_the_layer_status(self):
        """A fuzzy (pg_trgm) completion is distinguishable by the caller: `fuzzy_matches` appears only when it happened."""
        exact = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['episodic', 'documental']))
        self.assertNotIn('fuzzy_matches', exact['backends']['episodic'])
        self.assertNotIn('fuzzy_matches', exact['backends']['documental']['providers']['native'])
        self.store.search_items.return_value = [self.row, dict(self.row, item_id='near', ref='episodic:a:near:1', lexical_match='trigram')]
        self.store.search_documents.return_value = [dict(self.row, layer='documental', item_id='doc', ref='documental:a:doc:1', lexical_match='trigram')]
        fuzzy = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['episodic', 'documental']))
        self.assertEqual(fuzzy['backends']['episodic']['fuzzy_matches'], 1)
        self.assertEqual(fuzzy['backends']['documental']['providers']['native']['fuzzy_matches'], 1)
        self.assertFalse(fuzzy['partial'])
        marked = {item['item_id']: item.get('lexical_match') for item in fuzzy['items']}
        self.assertEqual(marked, {'uuid': None, 'near': 'trigram', 'doc': 'trigram'}, 'only fallback hits carry lexical_match')
        self.assertTrue(all('lexical_match' not in item for item in exact['items']))

    async def test_trigram_fallback_timeout_is_reported_and_keeps_the_lexical_hits(self):
        from memory_platform.store_common import LexicalResults
        late = LexicalResults([self.row])
        late.fuzzy_timed_out = True
        self.store.search_items.return_value = late
        timed_out = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['episodic']))
        self.assertEqual([item['item_id'] for item in timed_out['items']], ['uuid'])
        self.assertTrue(timed_out['backends']['episodic']['fuzzy_timeout'])
        self.assertEqual(timed_out['backends']['episodic']['status'], 'ok')
        self.assertNotIn('fuzzy_matches', timed_out['backends']['episodic'])
        self.store.search_items.return_value = [self.row]
        again = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['episodic']))
        self.assertNotIn('fuzzy_timeout', again['backends']['episodic'])

    async def test_scope_denied_before_all_calls(self):
        self.store.require_permission.side_effect = NotFound()
        with self.assertRaises(NotFound):
            await self.retrieval.search({}, m.Search(project_ids=['a'], q='x'))
        self.store.search_native_facts.assert_not_called()
        self.store.search_items.assert_not_called()
        self.embeddings.embed.assert_not_called()

    async def test_timed_out_vectors_keep_bounded_slots_without_starving_authentication(self):
        entered=threading.Event();release=threading.Event();lock=threading.Lock();calls=0
        def blocked(*args,**kwargs):
            nonlocal calls
            with lock:
                calls+=1
                if calls==2: entered.set()
            release.wait(3)
            return []
        self.store.search_vectors.side_effect=blocked
        self.store.has_vectors.return_value=True
        self.retrieval.settings=replace(self.retrieval.settings,embedding_query_timeout=0.05)
        request=m.Search(project_ids=['a'],q='knowledge',layers=['episodic'])
        tasks=[asyncio.create_task(self.retrieval.search({},request)) for _ in range(2)]
        try:
            async with asyncio.timeout(2):
                while not entered.is_set(): await asyncio.sleep(0.001)
            results=await asyncio.gather(*tasks)
            self.assertTrue(all(r['backends']['semantic']['status']=='unavailable' for r in results))
            # Request timeouts do not free slots belonging to running threads.
            third=asyncio.create_task(self.retrieval.search({},request))
            self.assertEqual(await asyncio.wait_for(asyncio.to_thread(lambda:'authentication executor available'),0.5),'authentication executor available')
            await third
            self.assertEqual(calls,2)
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            await asyncio.sleep(0.02)

    async def test_default_recall_uses_only_native_layers(self):
        result = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x'))
        self.assertFalse(result['partial'])
        self.assertNotIn('temporal', result['backends'])
        self.assertEqual(result['backends']['documental']['status'], 'ok')
        self.store.search_native_facts.assert_not_called()

    async def test_explicit_temporal_uses_native_store_without_service(self):
        result = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['temporal']))
        self.assertEqual(result['backends']['temporal']['status'], 'ok')
        self.assertFalse(result['partial'])
        self.store.search_native_facts.assert_called_once()

    async def test_budget_counts_unicode_and_no_duplicate_payload(self):
        result = await self.retrieval.details({}, m.Details(refs=[self.row['ref']], max_chars=100))
        self.assertEqual(len(result['items'][0]['content']), 100)
        self.assertNotIn('payload', result['items'][0])
        self.assertTrue(result['truncated'])
        context = await self.retrieval.context({}, m.Context(project_ids=['a'], q='x', layers=['episodic'], max_chars=100))
        self.assertEqual(len(context['context']), 100)
        self.assertIn('untrusted data', context['warnings'][0])

    async def test_stale_reference_rejected(self):
        self.store.get_item.return_value = dict(self.row, version=2)
        with self.assertRaises(MemoryError) as raised:
            await self.retrieval.details({}, m.Details(refs=[self.row['ref']]))
        self.assertEqual(raised.exception.status_code, 409)

    async def test_native_document_reference_requires_current_version(self):
        self.store.get_document.return_value = {'project_id': 'a', 'item_id': 'doc', 'version': 1, 'content': 'Canonical publication'}
        details = await self.retrieval.details({}, m.Details(refs=['documental:a:doc:1']))
        self.assertEqual(details['items'][0]['content'], 'Canonical publication')
        self.store.get_document.return_value['version'] = 2
        with self.assertRaises(MemoryError) as raised:
            await self.retrieval.details({}, m.Details(refs=['documental:a:doc:1']))
        self.assertEqual(raised.exception.status_code, 409)

    async def test_native_fact_detail_rechecks_hash_and_scope(self):
        fact = {'ref': 'native:a:memory:1:1', 'project_id': 'a', 'item_id': 'memory', 'version': 1, 'title': 'Correctness', 'subject': 'worker', 'predicate': 'uses',
                'object': 'fencing', 'evidence': 'Use fencing', 'validation_status': 'unverified'}
        self.store.search_native_facts.return_value = [fact]
        self.store.get_native_fact.return_value = fact
        search = await self.retrieval.search({}, m.Search(project_ids=['a'], q='fencing', layers=['temporal']))
        details = await self.retrieval.details({}, m.Details(refs=[search['items'][0]['ref']]))
        self.assertIn('fencing', details['items'][0]['content'])
        self.store.get_native_fact.side_effect = NotFound()
        with self.assertRaises(NotFound):
            await self.retrieval.details({}, m.Details(refs=[search['items'][0]['ref']]))

    async def test_timeline_denies_foreign_anchor_before_history(self):
        with self.assertRaises(NotFound):
            await self.retrieval.timeline({}, m.Timeline(project_ids=['a'], anchor_ref='episodic:foreign:uuid:1'))
        self.store.timeline.assert_not_called()

    async def test_timeline_checks_version_and_chronological_window(self):
        self.store.timeline.return_value = {'items': [self.row], 'partial': False}
        result = await self.retrieval.timeline({}, m.Timeline(project_ids=['a'], anchor_ref=self.row['ref']))
        self.assertEqual(result['items'][0]['item_id'], 'uuid')
        self.store.get_item.return_value = dict(self.row, version=2)
        with self.assertRaises(MemoryError):
            await self.retrieval.timeline({}, m.Timeline(project_ids=['a'], anchor_ref=self.row['ref']))
        with self.assertRaises(MemoryError):
            await self.retrieval.timeline({}, m.Timeline(project_ids=['a'], before='2026-11-01T00:00:00Z', after='2026-11-02T00:00:00Z'))

    async def test_partial_layer_timeout_preserves_episodic(self):
        self.retrieval.settings = replace(self.retrieval.settings, request_timeout=0.02)
        stalled = asyncio.Event()
        async def dispatch(function, *args, **kwargs):
            if function == self.store.search_documents:
                await stalled.wait()
            return function(*args, **kwargs)
        # Model one blocked database branch without tying the fast branch to
        # OS thread-start latency on a busy Windows workstation.
        with patch('memory_platform.retrieval.asyncio.to_thread', side_effect=dispatch):
            result = await self.retrieval.search({}, m.Search(project_ids=['a'], q='x', layers=['episodic', 'documental']))
        self.assertTrue(result['partial'])
        self.assertEqual(result['items'][0]['ref'], self.row['ref'])
        self.assertEqual(result['backends']['documental']['status'], 'unavailable')

    async def test_forged_temporal_group_rejected(self):
        ref = external_ref({'layer': 'temporal', 'project_id': 'a', 'item_id': 'fact', 'hash': 'bad', 'group': 'foreign'})
        with self.assertRaises(NotFound):
            await self.retrieval.details({}, m.Details(refs=[ref]))
        self.store.search_native_facts.assert_not_called()


    async def test_pending_document_search_works_before_any_external_index(self):
        document = {**self.row, 'ref': 'documental:a:doc:1', 'layer': 'documental', 'item_id': 'doc', 'index_status': 'pending'}
        self.store.search_documents.return_value = [document]
        found = await self.retrieval.search({}, m.Search(project_ids=['a'], q='document', layers=['documental']))
        self.assertEqual(found['items'][0]['ref'], document['ref'])
        self.assertEqual(found['items'][0]['index_status'], 'pending')
        self.assertFalse(found['partial'])

    async def test_hybrid_query_embeds_once_and_deduplicates_native_results(self):
        self.store.has_vectors.return_value = True
        vector_only = {**self.row, 'ref': 'episodic:a:semantic:1', 'item_id': 'semantic', 'title': 'Semantic paraphrase'}
        self.store.search_vectors.return_value = [self.row, vector_only]
        found = await self.retrieval.search({}, m.Search(project_ids=['a'], q='paraphrase', layers=['episodic', 'documental']))
        self.embeddings.embed.assert_awaited_once_with('paraphrase', query=True)
        self.assertEqual({value['item_id'] for value in found['items']}, {'uuid', 'semantic'})
        self.assertEqual(len(found['items']), 2)
        self.assertEqual(found['backends']['semantic']['status'], 'ok')
        args = self.store.search_vectors.call_args.args
        self.assertEqual(args[1], ['a'])
        self.assertEqual(args[3], 'nomic-embed-text')

    async def test_truncated_semantic_scan_marks_response_partial(self):
        self.store.has_vectors.return_value=True
        self.store.search_vectors.return_value=[dict(self.row,candidates_truncated=True)]
        found=await self.retrieval.search({},m.Search(project_ids=['a'],q='knowledge'))
        self.assertTrue(found['partial'])
        self.assertEqual(found['backends']['semantic']['status'],'partial')
        self.assertTrue(found['backends']['semantic']['candidates_truncated'])

    async def test_backend_reports_the_candidate_limit_of_the_route_that_ran(self):
        from memory_platform.store_vectors import vector_results
        self.store.has_vectors.return_value=True
        self.store.search_vectors.return_value=vector_results([dict(self.row,candidate_limit=20000,candidates_truncated=False)],20000,False)
        found=await self.retrieval.search({},m.Search(project_ids=['a'],q='knowledge'))
        self.assertEqual(found['backends']['semantic']['candidate_limit'],20000)
        self.store.search_vectors.return_value=[dict(self.row,candidate_limit=20000)]
        found=await self.retrieval.search({},m.Search(project_ids=['a'],q='knowledge'))
        self.assertEqual(found['backends']['semantic']['candidate_limit'],20000)

    async def test_truncated_empty_semantic_answer_is_partial(self):
        from memory_platform.store_vectors import vector_results
        self.store.has_vectors.return_value=True
        self.store.search_vectors.return_value=vector_results([],20000,True)
        found=await self.retrieval.search({},m.Search(project_ids=['a'],q='knowledge'))
        self.assertTrue(found['partial'])
        self.assertEqual(found['backends']['semantic']['status'],'partial')
        self.assertEqual((found['backends']['semantic']['candidate_limit'],found['backends']['semantic']['candidates_truncated']),(20000,True))

    async def test_semantic_unavailable_preserves_native_lexical_and_is_partial(self):
        self.store.has_vectors.return_value = True
        self.embeddings.embed.side_effect = TimeoutError()
        found = await self.retrieval.search({}, m.Search(project_ids=['a'], q='fencing', layers=['episodic']))
        self.assertEqual(found['items'][0]['ref'], self.row['ref'])
        self.assertTrue(found['partial'])
        self.assertEqual(found['backends']['semantic']['status'], 'unavailable')
        self.store.search_vectors.assert_not_called()


class DegradationTests(unittest.IsolatedAsyncioTestCase):
    """CA-15..CA-17 and CA-33: a failing semantic layer never fails the answer, and the caller can tell it apart from a fault."""
    def setUp(self):
        self.store = Mock()
        self.row = {'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic', 'title': 'Lexical hit',
                    'excerpt': 'x', 'content': 'x', 'validation_status': 'unknown'}
        self.store.search_items.return_value = [self.row]
        self.store.search_documents.return_value = []
        self.store.search_native_facts.return_value = []
        self.store.has_vectors.return_value = True
        self.embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True}))
        self.settings = Settings('unused', request_timeout=5, embedding_query_timeout=0.3)
        self.retrieval = Retrieval(self.store, self.settings, self.embeddings)

    def request(self, **extra):
        return m.Search(project_ids=['a'], q='fencing', layers=['episodic', 'documental'], **extra)

    async def test_ca15_semantic_only_hit_is_fused_with_the_lexical_ones(self):
        self.store.search_vectors.return_value = [self.row, {**self.row, 'ref': 'episodic:a:sem:1', 'item_id': 'sem', 'title': 'Semantic only'}]
        found = await self.retrieval.search({}, self.request())
        self.assertEqual(found['backends']['semantic']['status'], 'ok')
        self.assertEqual({v['item_id'] for v in found['items']}, {'lex', 'sem'})
        self.assertNotIn('degraded', found)

    async def test_ca16_provider_503_keeps_the_lexical_answer_and_reports_degraded(self):
        from memory_platform.providers import ProviderError
        self.embeddings.embed.side_effect = ProviderError('http_503')
        for call in (self.retrieval.search, self.retrieval.context):
            found = await call({}, self.request() if call == self.retrieval.search else m.Context(project_ids=['a'], q='fencing', layers=['episodic', 'documental']))
            self.assertEqual([v['item_id'] for v in found['items']], ['lex'])
            self.assertEqual(found['backends']['semantic']['status'], 'unavailable')
            self.assertEqual(found['backends']['semantic']['reason'], 'provider_error')
            self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'provider_error'})
            self.assertTrue(found['partial'])

    async def test_ca16_provider_timeout_answers_within_the_query_deadline_plus_one_second(self):
        async def stalled(*args, **kwargs):
            await asyncio.sleep(30)
        self.embeddings.embed.side_effect = stalled
        started = time.monotonic()
        found = await self.retrieval.search({}, self.request())
        self.assertLessEqual(time.monotonic() - started, self.settings.embedding_query_timeout + 1.0)
        self.assertEqual([v['item_id'] for v in found['items']], ['lex'])
        self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'timeout'})

    async def test_ca17_semantic_false_is_off_without_provider_calls_and_is_not_degraded(self):
        found = await self.retrieval.search({}, self.request(semantic=False))
        self.assertEqual(found['backends']['semantic'], {'status': 'off', 'count': 0})
        self.embeddings.embed.assert_not_awaited()
        self.store.search_vectors.assert_not_called()
        self.assertNotIn('degraded', found)
        self.assertFalse(found['partial'])

    async def test_a_project_without_vectors_is_off_but_says_why(self):
        self.store.has_vectors.return_value = False
        found = await self.retrieval.search({}, self.request())
        self.assertEqual(found['backends']['semantic']['status'], 'off')
        self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'no_vectors'})
        self.embeddings.embed.assert_not_awaited()

    async def test_disabled_embeddings_say_why(self):
        retrieval = Retrieval(self.store, replace(self.settings, embed_enabled=False), self.embeddings)
        found = await retrieval.search({}, self.request())
        self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'embeddings_disabled'})

    async def test_degraded_is_only_reported_when_the_semantic_layer_alone_fails(self):
        from memory_platform.providers import ProviderError
        self.embeddings.embed.side_effect = ProviderError('http_503')
        self.store.search_items.side_effect = RuntimeError('database down')
        found = await self.retrieval.search({}, self.request())
        self.assertEqual(found['backends']['episodic']['status'], 'unavailable')
        self.assertEqual(found['backends']['semantic']['status'], 'unavailable')
        self.assertNotIn('degraded', found)

    async def test_the_semantic_budget_of_the_request_cuts_the_semantic_layer_short_of_the_configured_deadline(self):
        """Review of phase 6: a caller with a short deadline asks for a budget and still gets the lexical answer, with `degraded` timeout."""
        async def stalled(*args, **kwargs):
            await asyncio.sleep(30)
        self.embeddings.embed.side_effect = stalled
        retrieval = Retrieval(self.store, replace(self.settings, embedding_query_timeout=5.0), self.embeddings)
        for call, request in ((retrieval.search, self.request(semantic_budget_ms=150)),
                              (retrieval.context, m.Context(project_ids=['a'], q='fencing', layers=['episodic', 'documental'], semantic_budget_ms=150))):
            started = time.monotonic()
            found = await call({}, request)
            self.assertLessEqual(time.monotonic() - started, 0.15 + 0.5)  # the budget plus a margin, nowhere near the 5 s configured
            self.assertEqual([v['item_id'] for v in found['items']], ['lex'])
            self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'timeout'})
            self.assertEqual(found['backends']['semantic']['reason'], 'timeout')

    async def test_a_budget_above_the_configured_deadline_never_extends_it(self):
        async def stalled(*args, **kwargs):
            await asyncio.sleep(30)
        self.embeddings.embed.side_effect = stalled
        started = time.monotonic()
        found = await self.retrieval.search({}, self.request(semantic_budget_ms=600000))
        self.assertLessEqual(time.monotonic() - started, self.settings.embedding_query_timeout + 1.0)
        self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'timeout'})

    async def test_a_budget_that_is_met_changes_nothing(self):
        self.store.search_vectors.return_value = [self.row]
        found = await self.retrieval.search({}, self.request(semantic_budget_ms=1000))
        self.assertEqual(found['backends']['semantic']['status'], 'ok')
        self.assertNotIn('degraded', found)

    async def test_the_budget_covers_the_vector_existence_check_too(self):
        """Review of phase 6 (N3): a slow `has_vectors` used to run outside the budget."""
        def slow(*args, **kwargs):
            time.sleep(1.0)
            return True
        self.store.has_vectors.side_effect = slow
        started = time.monotonic()
        found = await self.retrieval.search({}, self.request(semantic_budget_ms=150))
        self.assertLessEqual(time.monotonic() - started, 0.15 + 0.5)
        self.assertEqual([v['item_id'] for v in found['items']], ['lex'])
        self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': 'timeout'})
        self.embeddings.embed.assert_not_awaited()

    def test_the_semantic_budget_is_validated_in_range(self):
        for value in (0, -5, 600001, True, False, '1100', 1100.0, 1.5):  # out of range, and not an integer (a bool or a string is not a budget)
            for model, extra in ((m.Search, {}), (m.Context, {})):
                with self.assertRaises(Exception) as raised:
                    model(project_ids=['a'], q='x', semantic_budget_ms=value, **extra)
                self.assertIn('semantic_budget_ms', str(raised.exception))
        self.assertIsNone(m.Search(project_ids=['a'], q='x').semantic_budget_ms)
        self.assertEqual(m.Context(project_ids=['a'], q='x', semantic_budget_ms=1).semantic_budget_ms, 1)

    async def test_each_failure_of_the_semantic_layer_has_its_own_reason(self):
        from memory_platform.providers import ProviderError
        cases = []
        self.embeddings.embed.side_effect = ProviderError('http_503')
        cases.append(('provider_error', await self.retrieval.search({}, self.request())))
        self.embeddings.embed.side_effect = None
        self.store.has_vectors.side_effect = RuntimeError('database down')  # the database, before any provider call
        cases.append(('store_error', await self.retrieval.search({}, self.request())))
        self.store.has_vectors.side_effect = None
        self.store.search_vectors.side_effect = RuntimeError('scan failed')  # the database, after the provider answered
        cases.append(('store_error', await self.retrieval.search({}, self.request())))
        self.store.search_vectors.side_effect = MemoryError('semantic_deadline_exceeded', 'Semantic query exceeded its time budget', 503)
        cases.append(('timeout', await self.retrieval.search({}, self.request())))
        self.store.search_vectors.side_effect = None
        self.embeddings.embed.side_effect = TimeoutError()
        cases.append(('timeout', await self.retrieval.search({}, self.request())))
        for reason, found in cases:
            self.assertEqual(found['backends']['semantic']['reason'], reason)
            self.assertEqual(found['degraded'], {'layer': 'semantic', 'reason': reason})
            self.assertEqual([v['item_id'] for v in found['items']], ['lex'])
        self.assertEqual(m.Degraded(layer='semantic', reason='store_error').reason, 'store_error')


class FusionTests(unittest.IsolatedAsyncioTestCase):
    """T-27: reciprocal rank fusion with a validated bonus (decision D-7) instead of an absolute `validated first` order."""
    def hit(self, name, status='unknown', **extra):
        return {'ref': 'episodic:a:%s:1' % name, 'project_id': 'a', 'item_id': name, 'version': 1, 'layer': 'episodic', 'title': name,
                'excerpt': 'x', 'validation_status': status, **extra}

    def retrieval(self, rows, vectors=None, **settings):
        store = Mock()
        store.search_items.return_value = rows
        store.search_documents.return_value, store.search_native_facts.return_value = [], []
        store.has_vectors.return_value = vectors is not None
        store.search_vectors.return_value = vectors or []
        embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True}))
        return Retrieval(store, Settings('unused', request_timeout=5, **settings), embeddings)

    async def order(self, retrieval):
        found = await retrieval.search({}, m.Search(project_ids=['a'], q='fencing', layers=['episodic', 'documental']))
        return [v['item_id'] for v in found['items']]

    async def test_validated_is_a_bonus_not_an_absolute_order(self):
        rows = [self.hit('first'), self.hit('second', 'validated')]
        self.assertEqual(await self.order(self.retrieval(rows, fusion_validated_bonus=0.0)), ['first', 'second'])
        self.assertEqual(await self.order(self.retrieval(rows, fusion_validated_bonus=0.001)), ['second', 'first'])
        # a bonus smaller than the rank gap (1/60 - 1/61) does not overturn a better rank: validated wins only at a reasonable tie
        self.assertEqual(await self.order(self.retrieval(rows, fusion_validated_bonus=0.0001)), ['first', 'second'])

    async def test_validated_wins_an_exact_tie_and_a_superseded_fact_gets_no_bonus(self):
        both = [self.hit('plain'), self.hit('checked', 'validated')]
        vectors = [self.hit('checked', 'validated'), self.hit('plain')]  # symmetric ranks: exact tie
        self.assertEqual(await self.order(self.retrieval(both, vectors, fusion_validated_bonus=0.001)), ['checked', 'plain'])
        old = [self.hit('first'), self.hit('old', 'validated', superseded=True)]
        self.assertEqual(await self.order(self.retrieval(old, fusion_validated_bonus=0.001)), ['first', 'old'])

    async def test_layer_weights_and_k_change_the_fused_score(self):
        rows, vectors = [self.hit('lexical')], [self.hit('semantic')]
        self.assertEqual(await self.order(self.retrieval(rows, vectors, fusion_validated_bonus=0.0)), ['lexical', 'semantic'])  # tie keeps layer order
        self.assertEqual(await self.order(self.retrieval(rows, vectors, fusion_validated_bonus=0.0, fusion_weights={'semantic': 2.0})), ['semantic', 'lexical'])
        # `p` is first in one list (1/k); `q` is sixth in two lists (2/(k+5)): q wins only when k > 5
        lexical = [self.hit(name) for name in ('p', 'f1', 'f2', 'f3', 'f4', 'q')]
        semantic = [self.hit(name) for name in ('g1', 'g2', 'g3', 'g4', 'g5', 'q')]
        for k, expected in ((1, ['p', 'q']), (60, ['q', 'p'])):
            ordered = await self.order(self.retrieval(lexical, semantic, fusion_validated_bonus=0.0, fusion_k=k))
            self.assertEqual([name for name in ordered if name in ('p', 'q')], expected, k)

    def test_settings_validate_the_fusion_parameters(self):
        for bad in ({'fusion_k': 0}, {'fusion_k': 1001}, {'fusion_k': 1.5}, {'fusion_validated_bonus': -0.1}, {'fusion_validated_bonus': 1.1},
                    {'fusion_validated_bonus': float('nan')}, {'fusion_weights': {'unknown': 1.0}}, {'fusion_weights': {'semantic': 0}}, {'fusion_weights': {'semantic': float('inf')}}):
            with self.assertRaises(ValueError, msg=str(bad)):
                Settings('unused', **bad)
        self.assertEqual(Settings('unused', fusion_validated_bonus=0.005, fusion_weights={'semantic': 1.5}).fusion_weights, {'semantic': 1.5})

    def test_environment_values_are_parsed_strictly_with_the_variable_name_in_the_error(self):
        from memory_platform.config import fusion_from_env, DEFAULT_FUSION_K, DEFAULT_FUSION_VALIDATED_BONUS
        self.assertEqual(fusion_from_env({}), (DEFAULT_FUSION_K, DEFAULT_FUSION_VALIDATED_BONUS, {}))
        self.assertEqual(fusion_from_env({'MEMORY_FUSION_K': '30', 'MEMORY_FUSION_VALIDATED_BONUS': '0.004', 'MEMORY_FUSION_WEIGHTS': 'semantic=2, episodic=0.5'}),
                         (30, 0.004, {'semantic': 2.0, 'episodic': 0.5}))
        for name, value in (('MEMORY_FUSION_K', '0'), ('MEMORY_FUSION_K', 'x'), ('MEMORY_FUSION_K', '-3'), ('MEMORY_FUSION_VALIDATED_BONUS', 'high'),
                            ('MEMORY_FUSION_VALIDATED_BONUS', '2'), ('MEMORY_FUSION_VALIDATED_BONUS', 'nan'), ('MEMORY_FUSION_WEIGHTS', 'semantic'),
                            ('MEMORY_FUSION_WEIGHTS', 'semantic=x'), ('MEMORY_FUSION_WEIGHTS', 'lexical=1')):
            with self.assertRaises(ValueError, msg=(name, value)) as caught:
                fusion_from_env({name: value})
            self.assertIn(name, str(caught.exception))
