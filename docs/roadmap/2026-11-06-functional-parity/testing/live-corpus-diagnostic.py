"""Two real Why calls: stored assistant envelope versus projected answer schema.

Only synthetic observations live in the disposable PostgreSQL harness. Native
response diagnostics contain types, lengths and keys, never content or prompts.
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
snapshot = Path(tempfile.mkdtemp(prefix='kairos-corpus-diagnostic-')).resolve()
output = Path('/test-output')
manifest = {}


def copy(source, target):
    if source.is_symlink() or not source.resolve().is_relative_to(candidate):
        raise RuntimeError('Diagnostic rejects source symlinks and traversal')
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
from memory_platform.providers import ProviderError
from memory_platform.store import canonical
from memory_platform.tests.test_store import create_core, event

ENDPOINT = 'http://host.docker.internal:11434'
settings = SimpleNamespace(ollama_url=ENDPOINT, llm_model='beam:cloud', provider_timeout=90)
limits = AnswerLimits(input_tokens=4096, output_tokens=1024)
evidence = {'schema': 1, 'kind': 'synthetic-shape-diagnostic', 'max_model_calls': 2, 'actual_model_calls': 0,
            'model': settings.llm_model, 'endpoint': ENDPOINT, 'provider_timeout_seconds': 90,
            'output_tokens_per_call': 1024, 'provider_retries': 0, 'product_database_accessed': False,
            'source_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'packets': [], 'cases': []}


def shape(value):
    kind = type(value).__name__
    return {'type': kind, 'bytes': len(value.encode()) if isinstance(value, str) else None}


class ShapeTransport(httpx.AsyncBaseTransport):
    def __init__(self, packet):
        self.packet, self.transport = packet, httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        if str(request.url) != ENDPOINT+'/api/chat' or request.method != 'POST':
            raise AssertionError('Diagnostic allows only the fixed native chat endpoint')
        response = await self.transport.handle_async_request(request)
        await response.aread()
        self.packet['http_status'] = response.status_code
        try:
            body = response.json()
            self.packet['native'] = {key: value if isinstance(value, (bool, int)) else value[:32] if isinstance(value, str) else None
                for key, value in ((key, body.get(key)) for key in ('done', 'done_reason', 'prompt_eval_count', 'eval_count'))}
            content = body.get('message', {}).get('content', '')
            self.packet['content_bytes'] = len(content.encode()) if isinstance(content, str) else None
            parsed = json.loads(content)
            self.packet['json_type'] = type(parsed).__name__
            if isinstance(parsed, dict):
                self.packet['top_level_keys'] = sorted(str(key)[:80] for key in parsed)[:20]
                self.packet['answer'] = shape(parsed.get('answer'))
                citations = parsed.get('citations')
                self.packet['citations'] = {'type': type(citations).__name__, 'count': len(citations) if isinstance(citations, list) else None}
                if isinstance(citations, list):
                    self.packet['citation_shapes'] = [
                        {'keys': sorted(str(key)[:80] for key in cite)[:10], 'ref': shape(cite.get('ref')), 'quote': shape(cite.get('quote'))}
                        if isinstance(cite, dict) else {'type': type(cite).__name__}
                        for cite in citations[:3]]
        except (ValueError, TypeError, AttributeError):
            self.packet['json_shape_readable'] = False
        return response

    async def aclose(self):
        await self.transport.aclose()


class SeedProvider:
    async def answer(self, messages, sources, budget):
        return {'answer': 'ZEPHYR-482 requires two approvals for deployment.',
                'citations': [{'ref': sources[0]['ref'], 'quote': 'deployment requires two approvals'}],
                'input_tokens': 100, 'output_tokens': 60}


class DiagnosticProvider:
    def __init__(self, projection):
        self.projection = projection

    async def answer(self, messages, sources, budget):
        if evidence['actual_model_calls'] >= 2:
            raise AssertionError('Diagnostic model budget exhausted')
        messages = json.loads(json.dumps(messages))
        for message in messages:
            if message['role'] == 'assistant' and self.projection:
                previous = json.loads(message['content'])
                message['content'] = canonical({key: previous[key] for key in ('answer', 'citations')})
        packet = {'case': 'projected' if self.projection else 'current-envelope',
                  'assistant_keys': [sorted(json.loads(message['content'])) for message in messages if message['role'] == 'assistant']}
        evidence['packets'].append(packet)
        evidence['actual_model_calls'] += 1
        started = time.perf_counter()
        try:
            return await NativeCorpusProvider(settings, ShapeTransport(packet)).answer(messages, sources, budget)
        except ProviderError as error:
            packet['error_code'] = error.code
            raise
        finally:
            packet['elapsed_seconds'] = round(time.perf_counter()-started, 3)


class LiveShapeDiagnostic(unittest.TestCase):
    def test_matched_history_projection(self):
        store, actor, project = create_core()
        text = ('Synthetic rule ZEPHYR-482: deployment requires two approvals. '
                'This prevents accidental releases when one reviewer misses a defect.')
        source = event(project, generate=False, payload={'title': 'Synthetic Zephyr deployment gate', 'content': text})
        store.ingest_event(actor, source)
        agent = AgentStore(store)
        for projection in (False, True):
            name = 'projected' if projection else 'envelope'
            agent.build_corpus(actor, project, name)
            corpus = agent.prime_corpus(actor, project, name)
            seed = CorpusAnswers(store, settings, SeedProvider(), limits)
            seeded = asyncio.run(seed.answer(actor, project, name, 'ZEPHYR-482 deployment approvals?', 'seed-'+name, corpus['session_id'], corpus['version']))
            self.assertEqual(seeded['status'], 'completed')
            service = CorpusAnswers(store, settings, DiagnosticProvider(projection), limits)
            result = asyncio.run(service.answer(actor, project, name, 'Why?', 'why-'+name, corpus['session_id'], corpus['version']))
            case = {'name': name, 'status': result['status'], 'generation': result['generation'],
                    'generation_hash': result['generation_hash'], 'error_code': result.get('error_code')}
            evidence['cases'].append(case)
            self.assertEqual(CorpusAnswers(store, settings, SeedProvider(), limits).status(actor, project, name, 'why-'+name), result)
            case['reload_matches'] = True
            if result['status'] == 'completed':
                answer = result['result']['answer'].casefold()
                case['rationale_checked'] = 'accidental' in answer and ('release' in answer or 'defect' in answer)
                case['literal_quotes_checked'] = all(cite['quote'] in text for cite in result['result']['citations'])
        self.assertEqual(evidence['actual_model_calls'], 2)
        evidence['difference_observed'] = evidence['cases'][0]['status'] != 'completed' and evidence['cases'][1]['status'] == 'completed'
        self.assertEqual(evidence['cases'][1]['status'], 'completed', 'Projected positive control did not complete')
        self.assertTrue(evidence['cases'][1]['rationale_checked'])
        self.assertTrue(evidence['cases'][1]['literal_quotes_checked'])


output.mkdir(exist_ok=True)
(output/'live-corpus-diagnostic-source.json').write_text(json.dumps({'source_sha256': evidence['source_sha256'], 'files': manifest}, indent=2)+'\n', encoding='utf-8')
print('KAIROS_DIAGNOSTIC_FROZEN '+json.dumps({'source_sha256': evidence['source_sha256'], 'corpus_answers_sha256': manifest['memory_platform/corpus_answers.py']}), flush=True)
original_runner = unittest.TextTestRunner


class EvidenceRunner(original_runner):
    def run(self, suite):
        result = super().run(suite)
        evidence.update(status='positive_control_passed' if result.wasSuccessful() else 'diagnostic_failed',
                        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                        database='PostgreSQL', database_version=subprocess.check_output(['postgres', '--version'], text=True).strip())
        (output/'live-corpus-diagnostic-result.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
        print('KAIROS_DIAGNOSTIC_RESULT '+json.dumps({key: value for key, value in evidence.items() if key not in {'packets', 'cases'}}), flush=True)
        return result


unittest.TextTestRunner = EvidenceRunner
unittest.defaultTestLoader.discover = lambda *args, **kwargs: unittest.defaultTestLoader.loadTestsFromTestCase(LiveShapeDiagnostic)
os.environ.pop('MEMORY_LIVE_PROBE', None)
os.environ.pop('MEMORY_CLIENT_PROBE', None)
from memory_platform.tests.run_postgres import main
main()
