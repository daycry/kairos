import unittest
import json
import httpx
from memory_platform.config import Settings
from memory_platform.providers import Embeddings, Ollama, ProviderError, canonical




class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_embeddings_nomic_prefix_single_input_and_finite_vector(self):
        calls = []
        def respond(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'embeddings': [[0.25, -0.5, 1.0]]})
        provider = Embeddings(Settings('unused'), httpx.MockTransport(respond))
        await provider.embed('search concept', query=True)
        result = await provider.embed('document content')
        self.assertEqual(calls[0]['input'], ['search_query: search concept'])
        self.assertEqual(calls[1]['input'], ['search_document: document content'])
        self.assertEqual(calls[0]['model'], 'nomic-embed-text')
        self.assertEqual(result['embedding'], [0.25, -0.5, 1.0])

    async def test_embeddings_reject_zero_vector_and_invalid_dimensions(self):
        for vector in ([0.0, 0.0], [True], [], [1.0]*4097):
            def respond(request):
                return httpx.Response(200, json={'embeddings': [vector]})
            with self.assertRaises(ProviderError):
                await Embeddings(Settings('unused'), httpx.MockTransport(respond)).embed('input')

    async def test_ollama_rate_limit_retries_once_with_retry_after(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(429, headers={'Retry-After': '0'})
        with self.assertRaises(ProviderError) as raised:
            await Ollama(Settings('unused'), httpx.MockTransport(respond)).extract({})
        self.assertEqual(len(calls), 2)
        self.assertFalse(raised.exception.retryable)

    async def test_ollama_native_schema_model_and_invalid_json_no_retry(self):
        calls = []
        def respond(request):
            import json
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'message': {'content': 'not json'}})
        provider = Ollama(Settings('unused'), httpx.MockTransport(respond))
        with self.assertRaises(ProviderError) as raised:
            await provider.extract({'content': 'fixture'})
        self.assertEqual(raised.exception.code, 'extraction_invalid')
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]['think'])
        self.assertFalse(calls[0]['stream'])
        self.assertEqual(calls[0]['model'], 'beam:cloud')
        self.assertIn('properties', calls[0]['format'])

    async def test_ollama_cannot_validate_knowledge(self):
        def respond(request):
            return httpx.Response(200, json={'message': {'content': canonical({'title': 'x', 'content': 'x', 'validation_status': 'validated'})}})
        with self.assertRaises(ProviderError):
            await Ollama(Settings('unused'), httpx.MockTransport(respond)).extract({})

    async def test_native_fact_requires_literal_input_quote(self):
        payload = {'title': 'A correction', 'content': 'Do not infer approval', 'facts': [
            {'subject': 'writer', 'predicate': 'needs', 'object': 'fencing', 'evidence_quote': 'invented evidence'}]}
        def respond(request):
            return httpx.Response(200, json={'message': {'content': canonical(payload)}})
        provider = Ollama(Settings('unused'), httpx.MockTransport(respond))
        with self.assertRaises(ProviderError) as raised:
            await provider.extract({'content': 'Only genuine source content'})
        self.assertEqual(raised.exception.code, 'extraction_invalid')
        payload['facts'][0]['evidence_quote'] = 'genuine source'
        extracted = await provider.extract({'content': 'Only genuine source content'})
        self.assertEqual(extracted['payload']['validation_status'], 'unverified')
        self.assertEqual(extracted['payload']['facts'][0]['evidence_quote'], 'genuine source')
