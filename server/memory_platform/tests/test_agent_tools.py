"""Agent workflow regressions; database cases require isolated real PostgreSQL."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from unittest.mock import Mock
import uuid

from memory_platform.agent_store import AgentStore, apply_fields, corpus_filters, fields, migrate_agent_schema, visible_state
from memory_platform.agent_tools import DETAIL_BYTES, NORMAL_BYTES, TRUNCATION, register_agent_tools, render
from memory_platform.errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from memory_platform.tests.chain_services import ChainAgentStore, ChainSession
from memory_platform.tests.test_store import create_core, event


class AgentValidationTests(unittest.TestCase):
    def test_scalar_work_state_update_and_clear(self):
        original = {'fields': {}, 'tasks': {}}
        current = apply_fields(original, fields({'task': 'Preparar índice: "Árbol" 🌳', 'status': 'doing', 'owner': 'Inés'}))
        current = apply_fields(current, fields({'task': 'Preparar índice: "Árbol" 🌳', 'owner': None, 'status': 'done'}))
        self.assertEqual(visible_state(current)['tasks'], {})
        self.assertEqual(list(visible_state(current, True)['tasks'].values()), [{'status': 'done'}])
        self.assertEqual(original, {'fields': {}, 'tasks': {}})
        current = apply_fields(current, fields({'status': 'done'}))
        self.assertIsNone(visible_state(current))

    def test_invalid_or_sensitive_work_fields_are_rejected(self):
        for value in ({}, {'task': None}, {'a': []}, {'status': 'unknown'}, {'a': float('nan')}, {'a': 10**1000}, {'a': '\ud800'}, {'a': 'x'*20_000}, {'a': '<private>do not store</private>'}, {'a': 'sk-'+('z'*40)}):
            with self.subTest(value_type=type(next(iter(value.values()), None)).__name__):
                with self.assertRaises(MemoryError):
                    fields(value)

    def test_unicode_byte_budget_marks_every_shortened_output(self):
        value = {'title': 'Título: "Árbol" 🌳', 'content': 'é🌳'*100_000}
        for budget in (NORMAL_BYTES, DETAIL_BYTES):
            result = render(value, budget)
            self.assertLessEqual(len(result.encode('utf-8')), budget)
            self.assertTrue(result.endswith(TRUNCATION))
        self.assertEqual(json.loads(render({'tags': ['area:despliegue', 'nota:uno,dos', '"Árbol" 🌳']}))['tags'][1], 'nota:uno,dos')

    def test_corpus_filters_are_bounded_and_dates_ordered(self):
        value = corpus_filters(types='decision, decision,bugfix', date_start='2026-11-04', date_end='2026-11-05')
        self.assertEqual(value['types'], ['decision', 'bugfix'])
        exact = ['nota:uno,dos', '"\u00c1rbol" \U0001f333']
        self.assertEqual(corpus_filters(concepts=exact)['concepts'], exact)
        for args in ({'limit': True}, {'limit': 501}, {'date_start': 'yesterday'}, {'date_start': '2026-12-01', 'date_end': '2026-11-01'}, {'query': 'sk-'+('z'*40)}):
            with self.assertRaises(MemoryError):
                corpus_filters(**args)

    def test_registration_only_advertises_implemented_workflows(self):
        class Server:
            def __init__(self):
                self.tools = {}
            def tool(self, name, annotations):
                def register(fn):
                    self.tools[name] = fn
                    return fn
                return register
        server = Server()
        actor = Mock(return_value={'id': 'authenticated'})
        async def safe(operation):
            return await operation
        store = Mock()
        register_agent_tools(server, actor, safe, store)
        self.assertEqual(set(server.tools), {'work_state_write', 'work_state_read', 'build_corpus', 'list_corpora', 'prime_corpus', 'query_corpus', 'rebuild_corpus', 'reprime_corpus', 'get_observations', 'observation_search', 'observation_context', 'observation_generation_status', 'important_workflow'})
        result = asyncio.run(server.tools['important_workflow']())
        self.assertIn('untrusted', result)
        actor.assert_called_once()
        store.assert_not_called()

    def test_real_mcp_schemas_require_project_and_retry_identity(self):
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('isolated-agent-tests')
        async def safe(operation):
            return await operation
        register_agent_tools(server, lambda: {'id': 'fixture'}, safe, Mock())
        tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
        self.assertEqual(len(tools), 13)
        schema = tools['work_state_write'].inputSchema
        self.assertTrue({'project', 'list', 'fields', 'request_id'} <= set(schema['required']))
        self.assertEqual(tools['get_observations'].inputSchema['properties']['ids']['items']['type'], 'string')
        self.assertFalse(tools['query_corpus'].annotations.readOnlyHint)


class AgentPostgresTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        with self.store.transaction() as connection:
            migrate_agent_schema(connection)
        self.service = self.make_service()

    def make_service(self):
        """A new `AgentStore` over the store of the test (its chain variant: the same methods, each one a tool call through kairos-mcp)."""
        return AgentStore(self.store)

    def add(self, content='Database fencing prevents stale updates', **payload):
        data = event(self.project, generate=False, payload={'title': 'Índice: "Árbol", decisión 🌳', 'content': content, 'tags': ['area:despliegue', 'nota:uno,dos', '"Árbol" 🌳'], 'category': 'decision', 'source': {'uri': 'fixture://approved/source'}, 'validation_status': 'unverified', **payload})
        self.store.ingest_event(self.actor, data)
        return data

    def change(self, data, delete=False):
        updated = {**data, 'event_id': str(uuid.uuid4()), 'version': data['version']+1, 'event_type': 'delete' if delete else 'note', 'payload': {**data['payload'], 'content': 'Database fencing now also requires a lease'}}
        self.store.ingest_event(self.actor, updated)
        return updated

    def test_append_retry_revision_and_restart_recovery(self):
        first = self.service.work_write(self.actor, self.project, 'release', {'task': 'Preparar índice', 'status': 'doing'}, 'r1', 0)
        second = self.service.work_write(self.actor, self.project, 'release', {'task': 'Preparar índice', 'status': 'done'}, 'r2', 1)
        recovered = self.make_service()
        self.assertEqual(recovered.work_write(self.actor, self.project, 'release', {'task': 'Preparar índice', 'status': 'doing'}, 'r1', 0), first)
        self.assertEqual(second['version'], 2)
        self.assertEqual(recovered.work_read(self.actor, self.project)['lists'][0]['state']['tasks'], {})
        self.assertEqual(recovered.work_read(self.actor, self.project, include_closed=True)['lists'][0]['state']['tasks']['Preparar índice']['status'], 'done')
        with self.assertRaises(Conflict):
            recovered.work_write(self.actor, self.project, 'release', {'status': 'doing'}, 'r2', 1)
        with self.assertRaises(Conflict):
            recovered.work_write(self.actor, self.project, 'release', {'status': 'doing'}, 'r3', 1)
        with self.store.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM memory.agent_work_entries WHERE project_id=%s', (self.project,)).fetchone()['n'], 2)

    def test_concurrent_same_request_has_one_durable_effect(self):
        def write(_):
            return self.service.work_write(self.actor, self.project, 'release', {'task': 'ship', 'status': 'todo'}, 'same', 0)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(write, range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.service.work_read(self.actor, self.project)['lists'][0]['version'], 1)

    def test_capture_off_and_current_actor_grants(self):
        self.store.set_policy(self.actor, self.project, {'capture_mode': 'off', 'temporal_projection': False})
        with self.assertRaises(Forbidden):
            self.service.work_write(self.actor, self.project, 'release', {'status': 'todo'}, 'r1')
        with self.store.transaction() as c:
            c.execute('UPDATE memory.actors SET disabled=true WHERE id=%s', (self.actor['id'],))
        with self.assertRaises(Unauthorized):
            self.service.work_read(self.actor, self.project)

    def test_actor_and_project_isolation(self):
        self.service.work_write(self.actor, self.project, 'private', {'task': 'first'}, 'r1')
        aid = str(uuid.uuid4())
        with self.store.transaction() as c:
            c.execute('INSERT INTO memory.actors(id,username,password_hash) VALUES(%s,%s,%s)', (aid, 'synthetic-'+aid, 'not-a-login-hash'))
            for permission in ('read', 'write'):
                c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s)', (aid, self.project, permission))
        other = {'id': aid, 'credential_type': 'bootstrap'}
        self.assertEqual(self.service.work_read(other, self.project)['lists'], [])
        self.service.work_write(other, self.project, 'private', {'task': 'second'}, 'r1')
        self.assertEqual(list(self.service.work_read(self.actor, self.project)['lists'][0]['state']['tasks']), ['first'])
        with self.assertRaises(NotFound):
            self.service.work_read(other, 'unknown-project')
        self.add()
        self.service.build_corpus(self.actor, self.project, 'private')
        with self.assertRaises(NotFound):
            self.service.prime_corpus(other, self.project, 'private')

    def test_corpus_persistence_prime_query_revision_and_withdrawal(self):
        source = self.add()
        built = self.service.build_corpus(self.actor, self.project, 'decisions', types='decision', files='fixture://approved/source')
        self.assertEqual(built['count'], 1)
        with self.assertRaises(Conflict):
            self.service.query_corpus(self.actor, self.project, 'decisions', 'Database')
        primed = self.service.prime_corpus(self.actor, self.project, 'decisions')
        first = self.service.query_corpus(self.actor, self.project, 'decisions', 'Database')
        self.assertEqual(first['mode'], 'lexical_evidence')
        self.assertEqual(first['items'][0]['tags'], source['payload']['tags'])
        self.assertEqual(first['items'][0]['id'], source['item_id'])
        self.assertEqual(first['items'][0]['title'], source['payload']['title'])
        recovered = self.make_service()
        self.assertEqual(recovered.query_corpus(self.actor, self.project, 'decisions', 'Database'), first)
        self.assertEqual(recovered.prime_corpus(self.actor, self.project, 'decisions')['session_id'], primed['session_id'])
        source = self.change(source)
        with self.assertRaises(Conflict):
            recovered.query_corpus(self.actor, self.project, 'decisions', 'Database')
        updated = recovered.rebuild_corpus(self.actor, self.project, 'decisions', expected_version=1)
        self.assertEqual(updated['version'], 2)
        self.assertFalse(updated['primed'])
        with self.assertRaises(Conflict):
            recovered.query_corpus(self.actor, self.project, 'decisions', 'Database')
        reprinted = recovered.prime_corpus(self.actor, self.project, 'decisions', fresh=True)
        self.assertNotEqual(reprinted['session_id'], primed['session_id'])
        self.assertIn('lease', recovered.query_corpus(self.actor, self.project, 'decisions', 'Database')['answer'])
        self.change(source, delete=True)
        with self.assertRaises(Conflict):
            recovered.query_corpus(self.actor, self.project, 'decisions', 'Database')

    def test_rebuild_shrink_keeps_current_generation_until_explicit_force(self):
        entries = [self.add() for _ in range(3)]
        built = self.service.build_corpus(self.actor, self.project, 'protected')
        for source in entries[:2]:
            self.change(source, delete=True)
        with self.assertRaises(Conflict):
            self.service.rebuild_corpus(self.actor, self.project, 'protected')
        with self.store.transaction() as c:
            row = c.execute('SELECT version,canonical_hash FROM memory.agent_corpora WHERE id=%s', (built['id'],)).fetchone()
        self.assertEqual(row['version'], 1)
        self.assertEqual(row['canonical_hash'], built['hash'])
        result = self.service.rebuild_corpus(self.actor, self.project, 'protected', force=True)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['version'], 2)

    def test_get_observations_preserves_strings_tags_provenance_and_live_revocation(self):
        source = self.add()
        result = self.service.observations(self.actor, self.project, ids=[source['item_id']])
        self.assertEqual(result['items'][0]['sourceDetails'], source['payload']['source'])
        self.assertEqual(result['items'][0]['tags'], source['payload']['tags'])
        self.assertIsInstance(result['items'][0]['id'], str)
        self.change(source, delete=True)
        self.assertEqual(self.service.observations(self.actor, self.project, ids=[source['item_id']])['items'], [])

    def test_corpus_selection_matches_a_query_without_accent(self):
        """CA-23 (agent_store `_select`): `configuracion` did not match `configuración` before the language vectors."""
        source = self.add('La configuración de las canciones vive en el servidor')
        self.add('Nada que ver con este tema')
        built = self.service.build_corpus(self.actor, self.project, 'accents', query='configuracion cancion')
        self.assertEqual(built['count'], 1)
        self.assertEqual(self.service.build_corpus(self.actor, self.project, 'nothing', query='zzzunrelated')['count'], 0)
        self.assertTrue(source)

    def test_corpus_query_matches_a_question_without_accent(self):
        """CA-23 (agent_store `query_corpus`)."""
        source = self.add('La configuración de las canciones vive en el servidor')
        self.service.build_corpus(self.actor, self.project, 'ask')
        self.service.prime_corpus(self.actor, self.project, 'ask')
        found = self.service.query_corpus(self.actor, self.project, 'ask', 'configuracion cancion')
        self.assertEqual([item['id'] for item in found['items']], [source['item_id']])

    def test_observation_search_matches_a_query_without_accent(self):
        """CA-23 (agent_store `observations`)."""
        source = self.add('La configuración de las canciones vive en el servidor')
        self.add('Otra nota distinta')
        found = self.service.observations(self.actor, self.project, query='configuracion cancion')
        self.assertEqual([item['id'] for item in found['items']], [source['item_id']])

    def test_corpus_retry_and_saved_filter_bounds(self):
        self.add()
        built = self.service.build_corpus(self.actor, self.project, 'subset', query='Database', limit=1)
        self.assertEqual(self.service.build_corpus(self.actor, self.project, 'subset', query='Database', limit=1), built)
        with self.assertRaises(Conflict):
            self.service.build_corpus(self.actor, self.project, 'subset', query='other')
        self.service.prime_corpus(self.actor, self.project, 'subset')
        self.assertEqual(self.service.query_corpus(self.actor, self.project, 'subset', 'absentword')['items'], [])


class AgentPostgresChainTests(AgentPostgresTests):
    """T-48 (CA-11): the same scenarios, each service call a tool call through kairos-mcp over the same store; the results and refusals are those of the service."""

    def make_service(self):
        if getattr(self, 'chain', None) is None:
            self.chain = ChainSession(self.store, self.actor)
            self.addCleanup(self.chain.close)
        return ChainAgentStore(self.chain)


if __name__ == '__main__':
    unittest.main()
