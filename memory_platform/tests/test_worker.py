import asyncio
import unittest
from unittest.mock import Mock, AsyncMock
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
