import asyncio
import unittest
from unittest.mock import Mock, AsyncMock, patch
from memory_platform.config import Settings
from memory_platform.providers import ProviderError
from memory_platform.worker import Worker


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'payload': {'title': 'Source', 'content': 'Synthetic summary'}}
        self.store = Mock()
        self.store.claim_job.return_value = self.job
        self.receipt = {'payload': {'title': 'Lesson', 'content': 'Synthetic summary'}, 'status': 'extracted'}
        self.provider = Mock(extract=AsyncMock(return_value=self.receipt))
        self.worker = Worker(self.store, Settings('unused', lease_seconds=0.3), {'extract': self.provider})

    async def test_confirm_with_fence_after_readback(self):
        await self.worker.run_once()
        self.store.complete_job.assert_called_once_with('job', 4, self.receipt)
        self.store.fail_job.assert_not_called()

    async def test_unsupported_destination_never_runs_even_if_provider_is_injected(self):
        self.job['destination'] = 'retired-adapter'
        self.worker.providers['retired-adapter'] = self.provider
        await self.worker.run_once()
        self.provider.extract.assert_not_called()
        self.store.complete_job.assert_not_called()
        self.assertEqual(self.store.fail_job.call_args.args[2], 'unsupported_destination')

    async def test_deterministic_error_no_retry(self):
        self.provider.extract.side_effect = ProviderError('provider_rejected')
        await self.worker.run_once()
        self.assertEqual(self.store.fail_job.call_args.args, ('job', 4, 'provider_rejected', None, False))

    async def test_heartbeat_fence_loss_cannot_complete(self):
        async def slow(job):
            await asyncio.sleep(0.2)
            return {'verified': True}
        self.store.renew_lease.return_value = False
        self.provider.extract.side_effect = slow
        await self.worker.run_once()
        self.store.renew_lease.assert_called_once()
        self.store.complete_job.assert_not_called()

    async def test_no_job_no_provider(self):
        self.store.claim_job.return_value = None
        self.assertFalse(await self.worker.run_once())
        self.provider.extract.assert_not_called()

    async def test_explicit_extraction_persists_result_without_projection(self):
        self.job.update(destination='extract', payload={'title': 'fixture', 'content': 'summary'})
        extraction = {'payload': {'title': 'lesson', 'content': 'correction'}, 'model': 'beam:cloud', 'prompt_version': 'memory-extract-v1', 'input_hash': 'a'*64, 'status': 'extracted'}
        self.provider.extract = AsyncMock(return_value=extraction)
        self.worker.providers['extract'] = self.provider
        await self.worker.run_once()
        self.provider.extract.assert_awaited_once()
        self.store.complete_job.assert_called_once_with('job', 4, extraction)

    async def test_extraction_receives_source_payload_without_storage_envelope(self):
        source = {'title': 'Grounded lesson', 'content': 'Use fencing before projection', 'tags': ['nota:uno,dos']}
        self.job.update(destination='extract', payload={**source, 'payload': source, 'ref': 'episodic:a:uuid:1',
                        'project_id': 'a', 'canonical_hash': 'a'*64, 'layer': 'episodic'})
        self.provider.extract = AsyncMock(return_value={'payload': source, 'status': 'extracted'})
        self.worker.providers['extract'] = self.provider
        await self.worker.run_once()
        self.provider.extract.assert_awaited_once_with(source)

    async def test_extraction_transport_budget_exhausted_never_unknown_loop(self):
        self.job.update(destination='extract', payload={}, attempts=3)
        self.provider.extract = AsyncMock(side_effect=ProviderError('provider_transport', retryable=True, ambiguous=True))
        self.worker.providers['extract'] = self.provider
        await self.worker.run_once()
        self.assertEqual(self.store.fail_job.call_args.args, ('job', 4, 'provider_transport', None, False))

    async def test_native_embedding_worker_passes_current_hash_and_model(self):
        self.job.update(destination='embed', payload={'title': 'Source', 'content': 'Memory body'}, canonical_hash='a'*64)
        self.provider.embed = AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True})
        self.worker.providers['embed'] = self.provider
        await self.worker.run_once()
        self.provider.embed.assert_awaited_once_with('Source\nMemory body')
        self.store.complete_job.assert_called_once_with('job', 4, {'vector': [1.0, 0.0], 'model': 'nomic-embed-text', 'canonical_hash': 'a'*64, 'verified': True})


def long_text(characters):
    paragraphs, total = [], 0
    while total < characters:
        paragraphs.append(('palabra ' * 60).strip() + '.')
        total += len(paragraphs[-1]) + 2
    return '\n\n'.join(paragraphs)[:characters]


class ChunkedEmbeddingWorkerTests(unittest.IsolatedAsyncioTestCase):
    """Embed jobs for long text: fragments in batches, whole-job failure on any fragment failure, nothing partial reaches the store."""
    def setUp(self):
        self.content = long_text(20000)
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a'*64, 'policy': {},
                    'project_id': 'p', 'item_id': 'i', 'resource_type': 'document', 'version': 1,
                    'payload': {'title': 'Long note', 'content': self.content}}
        self.store = Mock()
        self.store.claim_job.return_value = self.job
        patcher = patch('memory_platform.worker.stored_item_vector', return_value=None)  # no stored item vector unless a test says so
        self.stored = patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = Settings('unused', lease_seconds=5, max_attempts=3)
        self.calls = []

    def worker(self, embed_many, embed=None):
        provider = Mock(embed=embed or AsyncMock(side_effect=AssertionError('a long text goes through embed_many')), embed_many=embed_many)
        return Worker(self.store, self.settings, {'embed': provider})

    async def test_long_text_is_split_embedded_in_one_call_and_delivered_whole(self):
        async def embed_many(texts, query=False):
            self.calls.append(list(texts))
            return {'embeddings': [[float(index + 1), 0.5] for index in range(len(texts))], 'model': 'nomic-embed-text', 'verified': True}
        await self.worker(embed_many).run_once()
        from memory_platform.chunking import chunk_text, embedding_text
        text = embedding_text('Long note', self.content)
        expected = chunk_text(text)
        self.assertGreater(len(expected), 10)
        self.assertEqual(self.calls, [[chunk.text(text).strip() for chunk in expected] + [text]])  # fragments, then the whole text (the item vector)
        self.store.fail_job.assert_not_called()
        receipt = self.store.complete_job.call_args.args[2]
        self.assertEqual([(c['ordinal'], c['char_start'], c['char_end']) for c in receipt['chunks']], [tuple(c) for c in expected])
        self.assertEqual(receipt['vector'], [float(len(expected) + 1), 0.5])  # the item vector is the embedding of the whole text (as before fragments), not the first fragment's
        self.assertNotEqual(receipt['vector'], receipt['chunks'][0]['vector'])
        self.assertEqual((receipt['model'], receipt['verified'], receipt['canonical_hash']), ('nomic-embed-text', True, 'a'*64))
        self.assertNotIn('chunks_truncated', receipt)
        self.assertEqual(self.store.complete_job.call_count, 1)

    async def test_text_beyond_the_old_cut_of_eight_thousand_characters_is_embedded(self):
        async def embed_many(texts, query=False):
            self.calls.append(list(texts))
            return {'embeddings': [[1.0, 0.5] for _ in texts], 'model': 'm', 'verified': True}
        marker = 'unico-dato-final'
        self.job['payload'] = {'title': 'T', 'content': self.content + ' ' + marker}
        await self.worker(embed_many).run_once()
        self.assertTrue(any(marker in text for text in self.calls[0]))

    async def test_failure_at_fragment_k_of_n_retries_and_delivers_nothing(self):
        async def embed_many(texts, query=False):
            raise ProviderError('provider_unavailable', retryable=True)
        await self.worker(embed_many).run_once()
        self.store.complete_job.assert_not_called()
        args = self.store.fail_job.call_args.args
        self.assertEqual(args[:3], ('job', 4, 'provider_unavailable'))
        self.assertIsNotNone(args[3], 'attempt 1 of 3 must be retried')

    async def test_failure_with_the_attempt_budget_spent_fails_the_job(self):
        self.job['attempts'] = 3

        async def embed_many(texts, query=False):
            raise ProviderError('provider_unavailable', retryable=True)
        await self.worker(embed_many).run_once()
        self.store.complete_job.assert_not_called()
        self.assertEqual(self.store.fail_job.call_args.args, ('job', 4, 'provider_unavailable', None, False))

    async def test_a_wrong_number_of_vectors_is_never_delivered(self):
        async def embed_many(texts, query=False):
            return {'embeddings': [[1.0, 0.5]] * (len(texts) - 1), 'model': 'm', 'verified': True}
        await self.worker(embed_many).run_once()
        self.store.complete_job.assert_not_called()
        self.assertEqual(self.store.fail_job.call_args.args[2], 'embedding_invalid')

    async def test_the_job_deadline_still_applies_to_the_batches(self):
        self.settings = Settings('unused', lease_seconds=5, embedding_worker_timeout=0.05, embedding_batch_timeout=0.05, embedding_job_timeout_max=0.05)

        async def embed_many(texts, query=False):
            await asyncio.sleep(30)
        started = asyncio.get_running_loop().time()
        with patch('memory_platform.worker.JOB_DEADLINE_MARGIN', 0.05):
            await self.worker(embed_many).run_once()
        self.assertLess(asyncio.get_running_loop().time() - started, 5)
        self.store.complete_job.assert_not_called()
        self.assertEqual(self.store.fail_job.call_args.args[2], 'provider_timeout')

    async def test_text_beyond_the_fragment_cap_is_reported_not_silently_cut(self):
        self.settings = Settings('unused', lease_seconds=5, chunk_max=5)

        async def embed_many(texts, query=False):
            return {'embeddings': [[1.0, 0.5] for _ in texts], 'model': 'm', 'verified': True}
        await self.worker(embed_many).run_once()
        receipt = self.store.complete_job.call_args.args[2]
        self.assertEqual(len(receipt['chunks']), 5)
        self.assertIs(receipt['chunks_truncated'], True)
        self.assertEqual(receipt['chunks'][-1]['char_end'], receipt['chunks_covered_chars'])

    async def test_an_existing_item_vector_is_reused_and_only_the_fragments_are_embedded(self):
        """Attempt 2, gap 3: the backfill of a resource that only lacks fragments does not embed its whole text again."""
        stored = [9.0, 9.0]
        self.stored.return_value = stored
        async def embed_many(texts, query=False):
            self.calls.append(list(texts))
            return {'embeddings': [[float(index + 1), 0.5] for index in range(len(texts))], 'model': 'nomic-embed-text', 'verified': True}
        await self.worker(embed_many).run_once()
        from memory_platform.chunking import chunk_text, embedding_text
        text = embedding_text('Long note', self.content)
        expected = chunk_text(text)
        self.assertEqual(self.calls, [[chunk.text(text).strip() for chunk in expected]])  # no whole-text input
        receipt = self.store.complete_job.call_args.args[2]
        self.assertEqual((receipt['vector'], len(receipt['chunks'])), (stored, len(expected)))

    async def test_a_text_with_a_long_blank_run_is_embedded_without_blank_fragments_and_keeps_its_item_vector(self):
        """Gap 3: a run of blanks as long as a fragment used to fail the job for good (embedding_empty_input)."""
        self.job['payload'] = {'title': 'T', 'content': 'intro\n' + '\n' * 4000 + 'fin'}

        async def embed_many(texts, query=False):
            self.calls.append(list(texts))
            return {'embeddings': [[float(index + 1), 0.5] for index in range(len(texts))], 'model': 'm', 'verified': True}
        await self.worker(embed_many).run_once()
        self.store.fail_job.assert_not_called()
        self.assertTrue(all(text.strip() for text in self.calls[0]), self.calls[0])
        receipt = self.store.complete_job.call_args.args[2]
        self.assertEqual(receipt['vector'], [float(len(receipt['chunks']) + 1), 0.5])
        self.assertEqual(receipt['chunks'][0]['char_start'], 0)
        self.assertEqual(receipt['chunks'][-1]['char_end'], len('T\nintro\n' + '\n' * 4000 + 'fin'))

    async def test_a_single_fragment_cap_still_reports_the_truncation(self):
        """Gap 9: MEMORY_CHUNK_MAX=1 must not lose the truncation notice."""
        self.settings = Settings('unused', lease_seconds=5, chunk_max=1)

        async def embed_many(texts, query=False):
            self.calls.append(list(texts))
            return {'embeddings': [[1.0, 0.5] for _ in texts], 'model': 'm', 'verified': True}
        await self.worker(embed_many).run_once()
        receipt = self.store.complete_job.call_args.args[2]
        self.assertEqual(len(receipt['chunks']), 1)
        self.assertIs(receipt['chunks_truncated'], True)
        self.assertEqual(receipt['chunks_covered_chars'], receipt['chunks'][0]['char_end'])

    async def test_the_job_deadline_grows_with_the_batches_up_to_the_global_ceiling(self):
        """Gap 5: 151 fragments no longer share the 120 s of one text."""
        from memory_platform.config import embedding_job_timeout
        settings = Settings('unused', embedding_worker_timeout=120.0, embedding_batch_size=8, embedding_batch_timeout=60.0, embedding_job_timeout_max=900.0)
        self.assertEqual(embedding_job_timeout(settings, 1), 120.0)
        self.assertEqual(embedding_job_timeout(settings, 9), 120.0)  # two batches of 60 s
        self.assertEqual(embedding_job_timeout(settings, 24), 180.0)  # three batches
        self.assertEqual(embedding_job_timeout(settings, 152), 900.0)  # 19 batches x 60 s, capped by the ceiling
        self.assertEqual(embedding_job_timeout(Settings('unused', embedding_batch_timeout=10.0, embedding_job_timeout_max=900.0), 40), 120.0)  # never below the single-text deadline

    async def test_a_short_text_keeps_the_single_input_call_and_the_previous_receipt(self):
        self.job['payload'] = {'title': 'Short', 'content': 'tiny body'}
        embed = AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True})
        many = AsyncMock()
        await self.worker(many, embed).run_once()
        embed.assert_awaited_once_with('Short\ntiny body')
        many.assert_not_awaited()
        self.store.complete_job.assert_called_once_with('job', 4, {'vector': [1.0, 0.0], 'model': 'nomic-embed-text', 'canonical_hash': 'a'*64, 'verified': True})
