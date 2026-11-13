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
        provider = Ollama(Settings('unused', llm_model='fixture-model'), httpx.MockTransport(respond))
        with self.assertRaises(ProviderError) as raised:
            await provider.extract({'content': 'fixture'})
        self.assertEqual(raised.exception.code, 'extraction_invalid')
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]['think'])
        self.assertFalse(calls[0]['stream'])
        self.assertEqual(calls[0]['model'], 'fixture-model')
        self.assertIn('properties', calls[0]['format'])

    async def test_extraction_never_offers_nor_keeps_structured(self):
        # Gap 3 of the phase 4 review: `structured` belongs to the client and is validated on ingest; the model neither sees nor returns it.
        import json
        calls = []
        def respond(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'message': {'content': canonical({'title': 'x', 'content': 'x', 'structured': {'schema_version': 'observation.v1'}})}})
        extracted = await Ollama(Settings('unused'), httpx.MockTransport(respond)).extract({'content': 'x'})
        self.assertNotIn('structured', calls[0]['format']['properties'])
        self.assertNotIn('structured', extracted['payload'])

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


class ModelRequirementTests(unittest.TestCase):
    """CA-16: no default language model; the startup says which variable is missing when a model feature is on."""

    ENV = {'MEMORY_DSN': 'postgresql://unused/unused'}

    def settings(self, **extra):
        from unittest.mock import patch
        with patch.dict('os.environ', {**self.ENV, **extra}, clear=True):
            return Settings.from_env()

    def test_default_startup_needs_no_model_and_keeps_both_features_off(self):
        settings = self.settings()
        self.assertEqual(settings.llm_model, '')
        self.assertIs(settings.extract_enabled, False)
        self.assertIs(settings.corpus_answer_enabled, False)

    def test_extraction_without_a_model_fails_naming_the_variable(self):
        with self.assertRaises(ValueError) as raised:
            self.settings(MEMORY_EXTRACT_ENABLED='1')
        self.assertIn('MEMORY_LLM_MODEL', str(raised.exception))

    def test_corpus_answer_without_a_model_fails_naming_the_variable(self):
        with self.assertRaises(ValueError) as raised:
            self.settings(MEMORY_CORPUS_ANSWER='on')
        self.assertIn('MEMORY_LLM_MODEL', str(raised.exception))

    def test_blank_model_counts_as_missing(self):
        with self.assertRaises(ValueError):
            self.settings(MEMORY_EXTRACT_ENABLED='1', MEMORY_LLM_MODEL='  ')

    def test_a_model_with_the_feature_on_is_accepted(self):
        settings = self.settings(MEMORY_EXTRACT_ENABLED='1', MEMORY_CORPUS_ANSWER='on', MEMORY_LLM_MODEL='fixture-model')
        self.assertEqual((settings.llm_model, settings.extract_enabled, settings.corpus_answer_enabled), ('fixture-model', True, True))

    def test_unknown_switch_values_fail_closed_instead_of_guessing(self):
        for name, value in (('MEMORY_EXTRACT_ENABLED', 'yes'), ('MEMORY_CORPUS_ANSWER', 'true')):
            with self.subTest(name), self.assertRaises(ValueError) as raised:
                self.settings(**{name: value, 'MEMORY_LLM_MODEL': 'fixture-model'})
            self.assertIn(name, str(raised.exception))

    def test_no_file_ships_the_retired_default_model(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        for name in ('memory_platform/config.py', 'docker-compose.yml', 'docs/configuration.md'):
            path = root / name
            if path.exists():  # the test image carries the compose file but not the manuals
                self.assertNotIn('beam', path.read_text(encoding='utf-8'), name)
