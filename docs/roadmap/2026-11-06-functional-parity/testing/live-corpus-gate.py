"""Two-call real-model proof over a newly created disposable PostgreSQL database.

Run in the test image with its default bridge network and this source mounted at
/candidate read-only. Only synthetic evidence is sent to the existing local model
endpoint. No product database, credentials, configuration or model is modified.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest


candidate = Path('/candidate').resolve()
snapshot = Path(tempfile.mkdtemp(prefix='kairos-live-corpus-source-')).resolve()
output = Path('/test-output')
manifest = {}


def copy(source, target):
    if source.is_symlink() or not source.resolve().is_relative_to(candidate):
        raise RuntimeError('Live proof rejects source symlinks and traversal')
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            if child.name not in {'__pycache__', '.private', '.env', '.npmrc', '.cache', '.pytest_cache'} and not child.name.startswith('.env.'):
                copy(child, target/child.name)
    elif source.suffix != '.pyc':
        content = source.read_bytes()
        target.write_bytes(content)
        manifest[target.relative_to(snapshot).as_posix()] = hashlib.sha256(content).hexdigest()


copy(candidate/'memory_platform', snapshot/'memory_platform')
os.chdir(snapshot)
sys.path.insert(0, str(snapshot))
import httpx
from memory_platform.agent_store import AgentStore
from memory_platform.corpus_answers import AnswerLimits, CorpusAnswers, NativeCorpusProvider
from memory_platform.errors import Conflict
from memory_platform.providers import ProviderError
from memory_platform.tests.test_store import create_core, event


MODEL = 'beam:cloud'
ENDPOINT = 'http://host.docker.internal:11434'
LIMITS = AnswerLimits(max_sessions=1, max_turns=3, input_tokens=4096, output_tokens=1024,
                      session_tokens=12_288, corpus_tokens=16_384, max_sources=1)
settings = SimpleNamespace(ollama_url=ENDPOINT, llm_model=MODEL, provider_timeout=90)
evidence = {'schema': 1, 'status': 'running', 'model': MODEL, 'endpoint': ENDPOINT,
            'synthetic_only': True, 'product_database_accessed': False,
            'network': 'default-bridge-for-fixed-provider-and-isolated-loopback-db',
            'max_model_calls': 2, 'actual_model_calls': 0, 'provider_retries': 0,
            'provider_timeout_seconds': 90, 'max_output_tokens_per_call': 1024,
            'max_input_tokens_per_call': 4096, 'steps': [],
            'source_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


class CountedRealProvider:
    def __init__(self):
        self.calls = []
        evidence['packets'] = self.calls

    async def answer(self, messages, sources, limits):
        if len(self.calls) >= 2:
            raise AssertionError('Real proof refuses more than two model calls')
        packet = {'roles': [message['role'] for message in messages], 'sources': [source['ref'] for source in sources]}
        self.calls.append(packet)
        evidence['actual_model_calls'] = len(self.calls)
        started = time.perf_counter()
        provider = NativeCorpusProvider(settings, ObservedTransport(packet, sources))
        try:
            return await provider.answer(messages, sources, limits)
        except ProviderError as error:
            packet['error_code'] = error.code
            raise
        finally:
            packet['elapsed_seconds'] = round(time.perf_counter()-started, 3)


class ObservedTransport(httpx.AsyncBaseTransport):
    """Inspect bounded metadata only, without changing a real provider response."""
    def __init__(self, packet, sources):
        self.packet, self.sources = packet, sources
        self.transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        if str(request.url) != ENDPOINT+'/api/chat' or request.method != 'POST':
            raise AssertionError('Live proof allows only the fixed native chat endpoint')
        response = await self.transport.handle_async_request(request)
        await response.aread()
        self.packet['http_status'] = response.status_code
        try:
            body = response.json()
            self.packet['native'] = {key: value if isinstance(value, (bool, int)) else value[:32] if isinstance(value, str) else None
                                     for key, value in ((key, body.get(key)) for key in ('done', 'done_reason', 'prompt_eval_count', 'eval_count'))}
            content = body.get('message', {}).get('content', '')
            if isinstance(content, str):
                self.packet['content_bytes'] = len(content.encode())
        except (ValueError, TypeError, AttributeError):
            self.packet['native_metadata_valid'] = False
        return response

    async def aclose(self):
        await self.transport.aclose()


class LiveCorpusProof(unittest.TestCase):
    def test_real_generation_continuity_exact_retry_persistence_and_withdrawal(self):
        store, actor, project = create_core()
        self.assertTrue(os.environ['MEMORY_TEST_DSN'].startswith('postgresql://postgres@127.0.0.1:55432/'))
        text = ('Synthetic rule ZEPHYR-482: deployment requires two approvals. '
                'This prevents accidental releases when one reviewer misses a defect.')
        source = event(project, generate=False, payload={'title': 'Synthetic Zephyr deployment gate',
            'content': text, 'tags': ['synthetic:live-proof'],
            'source': {'uri': 'fixture://synthetic/live-corpus-proof', 'sha256': hashlib.sha256(text.encode()).hexdigest()}})
        store.ingest_event(actor, source)
        item = store.get_item(actor, project, source['item_id'])
        agent = AgentStore(store)
        agent.build_corpus(actor, project, 'synthetic-live-proof')
        corpus = agent.prime_corpus(actor, project, 'synthetic-live-proof')
        provider = CountedRealProvider()
        service = CorpusAnswers(store, settings, provider, LIMITS)
        def arguments(question, request):
            return (actor, project, 'synthetic-live-proof', question, request, corpus['session_id'], corpus['version'])
        expected_ref = 'episodic:'+project+':'+source['item_id']+':1'
        evidence['source'] = {'item_id': source['item_id'], 'version': 1, 'canonical_hash': item['canonical_hash'],
                              'text_sha256': hashlib.sha256(text.encode()).hexdigest(), 'ref': expected_ref}
        unsupported = asyncio.run(service.answer(*arguments('xylophone zeppelin', 'unsupported-first')))
        self.assertEqual(unsupported['status'], 'no_evidence')
        self.assertEqual(len(provider.calls), 0)
        evidence['steps'].append({'step': 'unsupported_without_evidence', 'status': 'passed', 'model_calls': 0})
        question = 'ZEPHYR-482 deployment approvals?'
        first = asyncio.run(service.answer(*arguments(question, 'real-answer-one')))
        self.assertEqual(first['status'], 'completed', 'First real model answer was not completed')
        answer = first['result']['answer'].casefold()
        self.assertTrue(('two' in answer or '2' in answer) and 'approval' in answer, 'Synthetic key fact was not recovered')
        for label, result in [('primary', first)]:
            citations = result['result']['citations']
            self.assertTrue(citations)
            self.assertTrue(all(cite['ref'] == expected_ref and cite['quote'] in text for cite in citations))
            evidence['steps'].append({'step': label, 'status': result['status'],
                'literal_quotes_checked': True, 'key_fact_checked': True,
                'answer_sha256': hashlib.sha256(result['result']['answer'].encode()).hexdigest(),
                'input_tokens': result['input_tokens'], 'output_tokens': result['output_tokens']})
        reloaded = CorpusAnswers(store, settings, provider, LIMITS)
        self.assertEqual(asyncio.run(reloaded.answer(*arguments(question, 'real-answer-one'))), first)
        self.assertEqual(reloaded.status(actor, project, 'synthetic-live-proof', 'real-answer-one'), first)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(store.get_item(actor, project, source['item_id'])['canonical_hash'], item['canonical_hash'])
        evidence['steps'].append({'step': 'exact_retry_and_reload', 'status': 'passed', 'model_calls': 1,
                                  'generation_hash': first['generation_hash'], 'generation': first['generation']})
        second = asyncio.run(reloaded.answer(*arguments('Why?', 'real-answer-followup')))
        self.assertEqual(second['status'], 'completed', 'Real follow-up was not completed')
        answer = second['result']['answer'].casefold()
        self.assertTrue('accidental' in answer and ('release' in answer or 'defect' in answer), 'Follow-up missed synthetic rationale')
        self.assertTrue(all(cite['ref'] == expected_ref and cite['quote'] in text for cite in second['result']['citations']))
        self.assertEqual(provider.calls[1]['roles'], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(provider.calls[1]['sources'], [expected_ref])
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(CorpusAnswers(store, settings, provider, LIMITS).status(actor, project, 'synthetic-live-proof', 'real-answer-followup'), second)
        evidence['steps'].append({'step': 'followup_why', 'status': 'completed', 'literal_quotes_checked': True,
                                  'rationale_checked': True, 'continuity_messages_checked': True,
                                  'answer_sha256': hashlib.sha256(second['result']['answer'].encode()).hexdigest(),
                                  'input_tokens': second['input_tokens'], 'output_tokens': second['output_tokens']})
        store.ingest_event(actor, event(project, item_id=source['item_id'], version=2, event_type='delete', generate=False))
        with self.assertRaises(Conflict):
            asyncio.run(reloaded.answer(*arguments(question, 'real-answer-one')))
        with self.assertRaises(Conflict):
            reloaded.status(actor, project, 'synthetic-live-proof', 'real-answer-followup')
        self.assertEqual(len(provider.calls), 2)
        evidence['steps'].append({'step': 'withdrawal_blocks_cached_answers', 'status': 'passed', 'model_calls': 2})
        evidence['packets'] = provider.calls


output.mkdir(exist_ok=True)
(output/'live-corpus-source.json').write_text(json.dumps({'source_sha256': evidence['source_sha256'], 'files': manifest}, indent=2)+'\n', encoding='utf-8')
original_runner = unittest.TextTestRunner


class EvidenceRunner(original_runner):
    def run(self, suite):
        started = time.perf_counter()
        result = super().run(suite)
        evidence.update(status='passed' if result.wasSuccessful() and not result.skipped and result.testsRun == 1 else 'failed',
                        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                        elapsed_seconds=round(time.perf_counter()-started, 3),
                        database='PostgreSQL', database_version=subprocess.check_output(['postgres', '--version'], text=True).strip())
        (output/'live-corpus-result.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
        print('KAIROS_LIVE_CORPUS_RESULT '+json.dumps({key: value for key, value in evidence.items() if key not in {'steps', 'packets', 'source'}}), flush=True)
        return result


unittest.TextTestRunner = EvidenceRunner
unittest.defaultTestLoader.discover = lambda *args, **kwargs: unittest.defaultTestLoader.loadTestsFromTestCase(LiveCorpusProof)
os.environ.pop('MEMORY_LIVE_PROBE', None)
os.environ.pop('MEMORY_CLIENT_PROBE', None)
from memory_platform.tests.run_postgres import main
main()
