"""Generated corpus transport and isolated PostgreSQL admission/freshness tests."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import unittest

import httpx

from memory_platform.agent_store import AgentStore
from memory_platform.corpus_answers import (ANSWER_SCHEMA, AnswerLimits, CorpusAnswers,
                                           NativeCorpusProvider, migrate_corpus_answers, validate_answer)
from memory_platform.corpus_answer_tools import register_corpus_answer_tools
from memory_platform.errors import Conflict, MemoryError, Unauthorized
from memory_platform.providers import ProviderError
from memory_platform.tests.test_store import create_core, event


def settings():
    return SimpleNamespace(ollama_url='http://synthetic.invalid', llm_model='synthetic-model', provider_timeout=5, corpus_answer_enabled=True)


def output(sources):
    return {'answer': 'Use fencing before projection.', 'citations': [{'ref': sources[0]['ref'], 'quote': 'fencing'}],
            'input_tokens': 200, 'output_tokens': 40}


class CorpusAnswerTransportTests(unittest.TestCase):
    def test_native_schema_usage_and_no_retries(self):
        requests = []
        evidence = [{'ref': 'episodic:p:id:1', 'content': 'Use fencing before projection'}]
        # Only the answer schema goes into message.content; counters are native envelope fields.
        def valid(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({k:v for k,v in output(evidence).items() if k in ('answer','citations')})}, 'prompt_eval_count': 200, 'eval_count': 40})
        provider = NativeCorpusProvider(settings(), httpx.MockTransport(valid))
        result = asyncio.run(provider.answer([{'role': 'user', 'content': 'fencing'}], evidence, AnswerLimits()))
        self.assertEqual(result, output(evidence))
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['format'], ANSWER_SCHEMA)
        self.assertFalse(requests[0]['stream']); self.assertFalse(requests[0]['think'])
        self.assertEqual(requests[0]['options']['num_predict'], 1024)
        self.assertEqual(requests[0]['model'], settings().llm_model)
        requests.clear()
        async def limited(request):
            requests.append(request)
            return httpx.Response(429)
        with self.assertRaises(ProviderError):
            asyncio.run(NativeCorpusProvider(settings(), httpx.MockTransport(limited)).answer([], evidence, AnswerLimits()))
        self.assertEqual(len(requests), 1)

    def test_transport_timeout_is_ambiguous_and_single_attempt(self):
        calls = []
        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout('synthetic timeout')
        with self.assertRaises(ProviderError) as caught:
            asyncio.run(NativeCorpusProvider(settings(), httpx.MockTransport(timeout)).answer([], [], AnswerLimits()))
        self.assertTrue(caught.exception.ambiguous)
        self.assertEqual(len(calls), 1)

    def test_schema_rejects_foreign_ids_fabricated_quotes_and_sensitive_outputs(self):
        sources = [{'ref': 'episodic:p:one:1', 'content': 'área: "fencing", árbol 🌳'}]
        good = {'answer': 'Árbol: "fencing", sí 🌳', 'citations': [{'ref': sources[0]['ref'], 'quote': '"fencing", árbol 🌳'}]}
        self.assertEqual(validate_answer(good, sources), good)
        for bad in ({**good, 'citations': [{'ref': 'episodic:other:one:1', 'quote': 'fencing'}]},
                    {**good, 'citations': [{'ref': sources[0]['ref'], 'quote': 'invented'}]},
                    {**good, 'answer': 'Unsupported [episodic:other:one:1]'},
                    {**good, 'citations': []}, {**good, 'answer': '<private>hidden</private>'},
                    {**good, 'extra': True}):
            with self.assertRaises(ProviderError):
                validate_answer(bad, sources)

    def test_truncated_or_invalid_usage_is_not_accepted(self):
        sources = [{'ref': 'episodic:p:id:1', 'content': 'fencing'}]
        for changes in ({'done_reason': 'length'}, {'done': False}, {'eval_count': 1025}, {'prompt_eval_count': True}, {'message': {'content': 'not json'}}):
            payload = {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({'answer': 'fencing', 'citations': [{'ref': sources[0]['ref'], 'quote': 'fencing'}]})}, **changes}
            with self.assertRaises(ProviderError):
                asyncio.run(NativeCorpusProvider(settings(), httpx.MockTransport(lambda _: httpx.Response(200, json=payload))).answer([], sources, AnswerLimits()))

    def test_mcp_schema_requires_explicit_idempotency_and_generation(self):
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('synthetic-corpus-answer')
        async def safe(operation): return await operation
        register_corpus_answer_tools(server, lambda: {'id': 'fixture'}, safe, None, settings())
        tools = asyncio.run(server.list_tools())
        self.assertEqual({tool.name for tool in tools}, {'corpus_answer', 'corpus_answer_status'})
        tool = next(t for t in tools if t.name == 'corpus_answer')
        self.assertTrue({'request_id','expected_session_id','expected_generation'} <= set(tool.inputSchema['required']))
        self.assertTrue(tool.annotations.openWorldHint)


class FakeProvider:
    def __init__(self, callback=None): self.calls = []; self.callback = callback
    async def answer(self, messages, sources, limits):
        self.calls.append((messages, sources))
        if self.callback: self.callback()
        return output(sources)


class CorpusAnswerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        with self.store.transaction() as c: migrate_corpus_answers(c)
        self.agent = AgentStore(self.store)
        self.source = event(self.project, generate=False)
        self.store.ingest_event(self.actor, self.source)
        self.agent.build_corpus(self.actor, self.project, 'review')
        self.corpus = self.agent.prime_corpus(self.actor, self.project, 'review')
        self.provider = FakeProvider()
        self.service = CorpusAnswers(self.store, settings(), self.provider)

    def args(self, request='request-1', question='fencing'):
        return (self.actor, self.project, 'review', question, request, self.corpus['session_id'], self.corpus['version'])

    def test_generation_persist_reload_continuity_and_exact_repeat(self):
        first = asyncio.run(self.service.answer(*self.args()))
        self.assertEqual(first['status'], 'completed'); self.assertEqual(first['reserved_token_units'], 240)
        again = asyncio.run(CorpusAnswers(self.store, settings(), self.provider).answer(*self.args()))
        self.assertEqual(first, again); self.assertEqual(len(self.provider.calls), 1)
        second = asyncio.run(self.service.answer(*self.args('request-2')))
        self.assertEqual(second['status'], 'completed')
        self.assertEqual([m['role'] for m in self.provider.calls[1][0]], ['system','user','assistant','user'])
        assistant = next(message for message in self.provider.calls[1][0] if message['role']=='assistant')
        self.assertEqual(set(json.loads(assistant['content'])), {'answer','citations'})
        self.assertEqual(self.service.status(self.actor, self.project, 'review', 'request-1'), first)
        with self.assertRaises(Conflict): asyncio.run(self.service.answer(*self.args(question='different')))

    def test_sources_are_found_with_a_question_without_accent(self):
        """CA-23 (corpus_answers): `configuracion` did not match `configuración` before the language vectors."""
        accented = event(self.project, generate=False, payload={'title': 'Servidor', 'content': 'La configuración de las canciones vive en el servidor', 'source': {'uri': 'fixture://fts'}})
        self.store.ingest_event(self.actor, accented)
        self.agent.rebuild_corpus(self.actor, self.project, 'review', expected_version=self.corpus['version'])
        corpus = self.agent.prime_corpus(self.actor, self.project, 'review', fresh=True)
        class Quoting(FakeProvider):
            async def answer(self, messages, sources, limits):
                self.calls.append((messages, sources))
                return {'answer': 'La configuración vive en el servidor.', 'citations': [{'ref': sources[0]['ref'], 'quote': 'configuración'}], 'input_tokens': 200, 'output_tokens': 40}
        self.provider = Quoting()
        self.service = CorpusAnswers(self.store, settings(), self.provider)
        receipt = asyncio.run(self.service.answer(self.actor, self.project, 'review', 'configuracion cancion', 'accents', corpus['session_id'], corpus['version']))
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual([source['ref'].split(':')[2] for source in self.provider.calls[0][1]], [accented['item_id']])

    def test_no_evidence_never_calls_model(self):
        receipt = asyncio.run(self.service.answer(*self.args(question='unfindableword')))
        self.assertEqual(receipt['status'], 'no_evidence'); self.assertEqual(receipt['reserved_token_units'], 0)
        self.assertEqual(self.provider.calls, [])

    def test_followup_without_lexical_match_reuses_current_pinned_citations(self):
        first = asyncio.run(self.service.answer(*self.args()))
        second = asyncio.run(self.service.answer(*self.args('followup','Why?')))
        self.assertEqual(second['status'],'completed')
        self.assertEqual(len(self.provider.calls),2)
        messages,sources=self.provider.calls[1]
        self.assertEqual([m['role'] for m in messages],['system','user','assistant','user'])
        self.assertEqual(sources[0]['ref'],first['result']['citations'][0]['ref'])
        self.assertEqual(sources[0]['content'],self.source['payload']['content'])

    def test_native_transport_to_persistence_grounding_and_reload(self):
        calls = []
        def transport(request):
            body = json.loads(request.content); calls.append(body)
            sources = json.loads(body['messages'][-1]['content'])['evidence']
            generated = output(sources)
            return httpx.Response(200,json={'done':True,'done_reason':'stop',
                'message':{'content':json.dumps({k:v for k,v in generated.items() if k in ('answer','citations')})},
                'prompt_eval_count':200,'eval_count':40})
        service = CorpusAnswers(self.store,settings(),NativeCorpusProvider(settings(),httpx.MockTransport(transport)))
        result = asyncio.run(service.answer(*self.args()))
        self.assertEqual(result['result']['mode'],'generated_unverified')
        self.assertIn(self.source['item_id'],result['result']['citations'][0]['ref'])
        self.assertIn(result['result']['citations'][0]['quote'],self.source['payload']['content'])
        reloaded = CorpusAnswers(self.store,settings()).status(self.actor,self.project,'review','request-1')
        self.assertEqual(reloaded,result); self.assertEqual(len(calls),1)

    def test_simultaneous_same_id_has_only_one_provider_packet(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.service._reserve(*self.args()), range(2)))
        self.assertEqual(sum(packet is not None for _,packet in results),1)
        self.assertEqual(results[0][0],results[1][0])

    def test_reprime_does_not_reset_session_admission_budget(self):
        service = CorpusAnswers(self.store,settings(),self.provider,AnswerLimits(max_sessions=1))
        asyncio.run(service.answer(*self.args()))
        self.corpus = self.agent.prime_corpus(self.actor,self.project,'review',True)
        with self.assertRaises(MemoryError) as error: asyncio.run(service.answer(*self.args('session-2')))
        self.assertEqual(error.exception.code,'corpus_answer_budget_exceeded')
        self.assertEqual(len(self.provider.calls),1)

    def test_atomic_last_budget_and_duplicate_admission(self):
        self.service = CorpusAnswers(self.store, settings(), self.provider, AnswerLimits(corpus_tokens=9216))
        def reserve(request):
            try: return self.service._reserve(*self.args(request))
            except MemoryError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes = list(pool.map(reserve, ['one','two']))
        self.assertEqual(sum(isinstance(value, tuple) for value in outcomes), 1)
        self.assertIn('corpus_answer_budget_exceeded', outcomes)
        self.assertEqual(self.provider.calls, [])
        with self.store.transaction() as c:
            row = c.execute('SELECT request_id FROM memory.corpus_answers WHERE project_id=%s', (self.project,)).fetchone()
        result, packet = self.service._reserve(*self.args(row['request_id']))
        self.assertEqual(result['status'], 'pending'); self.assertIsNone(packet)

    def test_timeout_and_process_loss_keep_reservation_without_resend(self):
        class TimeoutProvider:
            calls = 0
            async def answer(self, *args):
                self.calls += 1
                raise ProviderError('provider_transport', ambiguous=True)
        provider = TimeoutProvider(); service = CorpusAnswers(self.store, settings(), provider)
        receipt = asyncio.run(service.answer(*self.args()))
        self.assertEqual(receipt['status'], 'unknown'); self.assertEqual(receipt['reserved_token_units'], 9216)
        self.assertEqual(asyncio.run(service.answer(*self.args())), receipt); self.assertEqual(provider.calls, 1)
        service._reserve(*self.args('lost-process'))
        with self.store.transaction() as c:
            c.execute("UPDATE memory.corpus_answers SET expires_at=clock_timestamp()-interval '1 second' WHERE project_id=%s", (self.project,))
        self.assertEqual(service.status(self.actor,self.project,'review','lost-process')['status'], 'unknown')

    def test_no_database_lock_during_provider_and_withdrawal_discards_answer(self):
        def withdraw():
            with self.store.transaction() as c:
                c.execute("SET LOCAL lock_timeout='1s'")
                c.execute('UPDATE memory.memory_items SET deleted=true WHERE id=%s', (self.source['item_id'],))
        provider = FakeProvider(withdraw)
        with self.assertRaises(Conflict): asyncio.run(CorpusAnswers(self.store,settings(),provider).answer(*self.args()))
        with self.store.transaction() as c:
            row = c.execute('SELECT state,result,reservation FROM memory.corpus_answers WHERE project_id=%s', (self.project,)).fetchone()
        self.assertEqual(row['state'], 'invalidated'); self.assertIsNone(row['result']); self.assertEqual(row['reservation'],9216)

    def test_revocation_after_call_discards_result(self):
        def revoke():
            with self.store.transaction() as c:
                c.execute("SET LOCAL lock_timeout='1s'")
                c.execute('UPDATE memory.actors SET disabled=true WHERE id=%s', (self.actor['id'],))
        with self.assertRaises(Unauthorized):
            asyncio.run(CorpusAnswers(self.store,settings(),FakeProvider(revoke)).answer(*self.args()))
        with self.store.transaction() as c:
            row = c.execute('SELECT state,result FROM memory.corpus_answers WHERE project_id=%s', (self.project,)).fetchone()
        self.assertEqual(row, {'state':'invalidated','result':None})

    def test_reprime_and_source_update_invalidate_cached_answer(self):
        asyncio.run(self.service.answer(*self.args()))
        self.agent.prime_corpus(self.actor,self.project,'review',True)
        with self.assertRaises(Conflict): self.service.status(self.actor,self.project,'review','request-1')
        with self.assertRaises(Conflict): asyncio.run(self.service.answer(*self.args()))

    def test_failed_schema_does_not_release_uncertain_consumption(self):
        class InvalidProvider:
            async def answer(self,*_): return {'answer':'invented','citations':[]}
        service = CorpusAnswers(self.store,settings(),InvalidProvider())
        receipt = asyncio.run(service.answer(*self.args()))
        self.assertEqual(receipt['status'],'failed'); self.assertEqual(receipt['reserved_token_units'],9216)

    def test_safe_provider_error_codes_are_distinct_persisted_and_never_retried(self):
        for number,(reason,citations,expected) in enumerate([
            ('length',None,'corpus_answer_truncated'),
            ('stop',[{'ref':'episodic:other:foreign:1','quote':'fencing'}],'corpus_answer_citation_invalid')]):
            calls=[]
            def transport(request):
                calls.append(request);sources=json.loads(json.loads(request.content)['messages'][-1]['content'])['evidence']
                value=output(sources)
                if citations is not None:value['citations']=citations
                return httpx.Response(200,json={'done':True,'done_reason':reason,'message':{'content':json.dumps({k:v for k,v in value.items() if k in ('answer','citations')})}})
            service=CorpusAnswers(self.store,settings(),NativeCorpusProvider(settings(),httpx.MockTransport(transport)))
            receipt=asyncio.run(service.answer(*self.args('failure-'+str(number))))
            self.assertEqual(receipt['status'],'failed');self.assertEqual(receipt['error_code'],expected)
            self.assertEqual(CorpusAnswers(self.store,settings()).status(self.actor,self.project,'review','failure-'+str(number)),receipt)
            self.assertEqual(asyncio.run(service.answer(*self.args('failure-'+str(number)))),receipt);self.assertEqual(len(calls),1)

    def test_uncertain_error_codes_redact_provider_text_and_expired_pending(self):
        class InvalidCode:
            async def answer(self,*_):raise ProviderError('http://private.invalid/secret?key=hidden',ambiguous=True)
        receipt=asyncio.run(CorpusAnswers(self.store,settings(),InvalidCode()).answer(*self.args()))
        self.assertEqual(receipt['status'],'unknown');self.assertEqual(receipt['error_code'],'corpus_answer_failed')
        self.assertNotIn('private.invalid',json.dumps(receipt))
        self.service._reserve(*self.args('expired'))
        with self.store.transaction() as c:c.execute("UPDATE memory.corpus_answers SET expires_at=clock_timestamp()-interval '1 second' WHERE project_id=%s",(self.project,))
        expired=self.service.status(self.actor,self.project,'review','expired')
        self.assertEqual(expired['status'],'unknown');self.assertEqual(expired['error_code'],'corpus_answer_timeout')

    def test_input_and_turn_limits_reject_before_call(self):
        service = CorpusAnswers(self.store,settings(),self.provider, AnswerLimits(max_turns=1))
        asyncio.run(service.answer(*self.args()))
        with self.assertRaises(MemoryError) as error: asyncio.run(service.answer(*self.args('second')))
        self.assertEqual(error.exception.code,'corpus_answer_budget_exceeded'); self.assertEqual(len(self.provider.calls),1)
        service = CorpusAnswers(self.store,settings(),self.provider, AnswerLimits(input_bytes=1024))
        with self.assertRaises(MemoryError) as error: asyncio.run(service.answer(*self.args('long','fencing '+('word '*400))))
        self.assertEqual(error.exception.code,'corpus_answer_input_budget'); self.assertEqual(len(self.provider.calls),1)


class CorpusAnswerSwitchTests(unittest.TestCase):
    """MEMORY_CORPUS_ANSWER (CA-15, P-04): off by default, `corpus_answer_disabled` without touching any provider."""

    def setUp(self):
        self.store, self.actor, self.project = create_core()
        with self.store.transaction() as c: migrate_corpus_answers(c)
        agent = AgentStore(self.store)
        self.store.ingest_event(self.actor, event(self.project, generate=False))
        agent.build_corpus(self.actor, self.project, 'review')
        self.corpus = agent.prime_corpus(self.actor, self.project, 'review')
        self.provider = FakeProvider()

    def args(self, request='request-1'):
        return (self.actor, self.project, 'review', 'fencing', request, self.corpus['session_id'], self.corpus['version'])

    def test_default_settings_have_the_switch_off(self):
        from memory_platform.config import Settings
        self.assertIs(Settings('unused').corpus_answer_enabled, False)

    def test_off_answers_the_error_and_never_calls_a_provider(self):
        off = SimpleNamespace(ollama_url='http://synthetic.invalid', llm_model='', provider_timeout=5, corpus_answer_enabled=False)
        service = CorpusAnswers(self.store, off, self.provider)
        with self.assertRaises(MemoryError) as error: asyncio.run(service.answer(*self.args()))
        self.assertEqual(error.exception.code, 'corpus_answer_disabled')
        self.assertIn('corpus_answer_disabled', error.exception.message)
        self.assertEqual(self.provider.calls, [])
        with self.store.transaction() as c:  # nothing was reserved either
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.corpus_answers WHERE project_id=%s', (self.project,)).fetchone()['n'], 0)

    def test_status_still_reads_answers_stored_while_it_was_on(self):
        on = CorpusAnswers(self.store, settings(), self.provider)
        stored = asyncio.run(on.answer(*self.args()))
        off = SimpleNamespace(ollama_url='http://synthetic.invalid', llm_model='', provider_timeout=5, corpus_answer_enabled=False)
        read = CorpusAnswers(self.store, off, self.provider).status(self.actor, self.project, 'review', 'request-1')
        self.assertEqual(read, stored)
        self.assertEqual(len(self.provider.calls), 1)

    def test_off_reusing_a_stored_request_id_reads_the_operation_and_a_new_one_is_refused(self):
        on = CorpusAnswers(self.store, settings(), self.provider)
        stored = asyncio.run(on.answer(*self.args()))
        off = CorpusAnswers(self.store, SimpleNamespace(ollama_url='http://synthetic.invalid', llm_model='', provider_timeout=5, corpus_answer_enabled=False), self.provider)
        self.assertEqual(asyncio.run(off.answer(*self.args())), stored)  # same request_id: reads, never resends
        self.assertEqual(len(self.provider.calls), 1)
        with self.assertRaises(MemoryError) as error: asyncio.run(off.answer(*self.args('request-2')))
        self.assertEqual(error.exception.code, 'corpus_answer_disabled')
        with self.store.transaction() as c:  # nothing new reserved
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.corpus_answers WHERE project_id=%s', (self.project,)).fetchone()['n'], 1)
        stranger = {'id': '00000000-0000-0000-0000-000000000000', 'credential_type': 'bootstrap'}  # no grant on the project: authorization is unchanged
        with self.assertRaises(Exception) as denied: asyncio.run(off.answer(stranger, *self.args()[1:]))
        self.assertNotEqual(getattr(denied.exception, 'code', None), None)
        self.assertEqual(len(self.provider.calls), 1)


if __name__ == '__main__':
    # The same owned temporary-PG harness, restricted to this domain's tests.
    from memory_platform.tests import run_postgres
    unittest.defaultTestLoader.discover = lambda *args, **kwargs: unittest.defaultTestLoader.loadTestsFromName('memory_platform.tests.test_corpus_answers')
    run_postgres.main()
