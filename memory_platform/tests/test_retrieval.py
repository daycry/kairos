import asyncio
import threading
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
