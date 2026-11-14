"""Batched `/api/embed` for fragments: bounded batches, the single-request semaphore and one overall deadline."""
import asyncio
import json
import unittest

import httpx

from memory_platform.config import Settings
from memory_platform.providers import Embeddings, ProviderError


class EmbedManyTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, respond, **settings):
        return Embeddings(Settings('unused', **settings), httpx.MockTransport(respond))

    async def test_fragments_travel_in_bounded_batches_with_the_document_prefix(self):
        calls = []

        def respond(request):
            body = json.loads(request.content)
            calls.append(body)
            return httpx.Response(200, json={'embeddings': [[float(len(text)), 1.0] for text in body['input']]})
        result = await self.provider(respond, embedding_batch_size=3).embed_many(['a' * n for n in range(1, 8)])
        self.assertEqual([len(call['input']) for call in calls], [3, 3, 1])
        self.assertEqual(calls[0]['input'][0], 'search_document: a')
        self.assertTrue(all(call['truncate'] is True and call['model'] == 'nomic-embed-text' for call in calls))
        self.assertEqual([vector[0] for vector in result['embeddings']], [float(n + len('search_document: ')) for n in range(1, 8)])
        self.assertEqual((result['model'], result['verified']), ('nomic-embed-text', True))

    async def test_requests_never_overlap_inside_one_provider(self):
        running, peak = 0, 0

        class Tracking(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                nonlocal running, peak
                running += 1
                peak = max(peak, running)
                await asyncio.sleep(0.02)
                running -= 1
                body = json.loads(request.content)
                return httpx.Response(200, json={'embeddings': [[1.0, 2.0] for _ in body['input']]})
        provider = Embeddings(Settings('unused', embedding_batch_size=1), Tracking())
        await asyncio.gather(provider.embed_many(['one', 'two', 'three']), provider.embed('four'), provider.embed_many(['five', 'six']))
        self.assertEqual(peak, 1)

    async def test_a_failing_batch_fails_the_whole_call(self):
        calls = []

        def respond(request):
            calls.append(1)
            if len(calls) == 2:
                return httpx.Response(503)
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5] for _ in json.loads(request.content)['input']]})
        with self.assertRaises(ProviderError) as raised:
            await self.provider(respond, embedding_batch_size=2).embed_many(['a', 'b', 'c', 'd', 'e'])
        self.assertEqual((raised.exception.code, raised.exception.retryable), ('provider_unavailable', True))
        self.assertEqual(len(calls), 2)  # nothing after the failure is requested

    async def test_a_short_or_inconsistent_answer_is_rejected(self):
        answers = ([[1.0, 2.0]], [[1.0, 2.0], [1.0]], [[1.0, 2.0], [0.0, 0.0]], [[1.0, 2.0], [True, 1.0]])
        for answer in answers:
            def respond(request, answer=answer):
                return httpx.Response(200, json={'embeddings': answer})
            with self.assertRaises(ProviderError, msg=answer) as raised:
                await self.provider(respond).embed_many(['a', 'b'])
            self.assertEqual(raised.exception.code, 'embedding_invalid')

    async def test_the_overall_deadline_bounds_all_batches(self):
        class Slow(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                await asyncio.sleep(0.2)
                return httpx.Response(200, json={'embeddings': [[1.0, 2.0] for _ in json.loads(request.content)['input']]})
        provider = Embeddings(Settings('unused', embedding_batch_size=1, embedding_worker_timeout=0.5, embedding_batch_timeout=0.3, embedding_job_timeout_max=0.5), Slow())
        started = asyncio.get_running_loop().time()
        with self.assertRaises((TimeoutError, ProviderError)):
            await provider.embed_many(['a'] * 10)
        self.assertLess(asyncio.get_running_loop().time() - started, 1.5)

    async def test_the_deadline_is_proportional_to_the_number_of_batches(self):
        """Gap 5: three batches of 0.2 s pass with 0.4 s per batch although a shared 0.3 s would not."""
        class Slow(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                await asyncio.sleep(0.2)
                return httpx.Response(200, json={'embeddings': [[1.0, 2.0] for _ in json.loads(request.content)['input']]})
        settings = dict(embedding_batch_size=1, embedding_worker_timeout=0.3, embedding_batch_timeout=0.4, embedding_job_timeout_max=2.0)
        result = await Embeddings(Settings('unused', **settings), Slow()).embed_many(['a', 'b', 'c'])
        self.assertEqual(len(result['embeddings']), 3)
        with self.assertRaises((TimeoutError, ProviderError)):  # the global ceiling still bounds it
            await Embeddings(Settings('unused', **dict(settings, embedding_job_timeout_max=0.3)), Slow()).embed_many(['a', 'b', 'c'])

    def test_the_timeouts_are_configurable_and_validated(self):
        from memory_platform.config import embed_timeouts
        self.assertEqual(embed_timeouts({}), (60.0, 900.0))
        self.assertEqual(embed_timeouts({'MEMORY_EMBED_BATCH_TIMEOUT': '30', 'MEMORY_EMBED_JOB_MAX_TIMEOUT': '600'}), (30.0, 600.0))
        for environ in ({'MEMORY_EMBED_BATCH_TIMEOUT': '0'}, {'MEMORY_EMBED_BATCH_TIMEOUT': 'x'}, {'MEMORY_EMBED_BATCH_TIMEOUT': 'nan'}, {'MEMORY_EMBED_BATCH_TIMEOUT': '601'},
                        {'MEMORY_EMBED_JOB_MAX_TIMEOUT': '4000'}, {'MEMORY_EMBED_BATCH_TIMEOUT': '100', 'MEMORY_EMBED_JOB_MAX_TIMEOUT': '50'}):
            with self.assertRaises(ValueError, msg=environ):
                embed_timeouts(environ)

    async def test_empty_inputs_are_rejected(self):
        provider = self.provider(lambda request: httpx.Response(200, json={'embeddings': []}))
        for texts in ([], [''], ['ok', '  '], 'text', [1]):
            with self.assertRaises(ProviderError, msg=texts) as raised:
                await provider.embed_many(texts)
            self.assertEqual(raised.exception.code, 'embedding_empty_input')


if __name__ == '__main__':
    unittest.main()
