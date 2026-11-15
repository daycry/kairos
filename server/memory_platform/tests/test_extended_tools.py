"""Real PostgreSQL contracts for shared work and current-only observation adapters."""
import json
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from memory_platform.agent_store import AgentStore
from memory_platform.errors import Conflict, Forbidden, MemoryError, NotFound, Unauthorized
from memory_platform.extended_store import ExtendedStore, migrate_extended_schema, validated_event
from memory_platform.extended_tools import register_extended_tools
from memory_platform.store import digest
from memory_platform.tests.chain_services import ChainAgentStore, ChainExtendedStore, ChainSession
from memory_platform.tests.test_store import create_core, event


class ExtendedValidationTests(unittest.TestCase):
    def test_event_identity_and_extra_fields_are_required(self):
        for change in ({'event_id': 'invented'}, {'extra': 'field'}, {'occurred_at': '2026-11-04'}):
            with self.assertRaises(MemoryError):
                validated_event(event('test', **change))

    def test_registered_schemas_distinguish_destructive_observation_updates(self):
        import asyncio
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('synthetic')
        async def safe(operation):
            return await operation
        register_extended_tools(server, lambda: {'id': 'fixture'}, safe, object())
        tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
        self.assertEqual(set(tools), {'observation_add', 'observation_record_event', 'get_tool_uses',
                                     'team_work_write', 'team_work_read', 'team_search', 'team_brief'})
        self.assertTrue(tools['observation_record_event'].annotations.destructiveHint)
        self.assertTrue(tools['get_tool_uses'].annotations.readOnlyHint)
        self.assertIn('event', tools['observation_add'].inputSchema['required'])


class ExtendedPostgresTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.project = create_core()
        with self.store.transaction() as c:
            migrate_extended_schema(c)
            migrate_extended_schema(c)
            aid = str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash) VALUES(%s,%s,%s)', (aid, 'team-'+aid, 'not-a-login'))
            for permission in ('read', 'write'):
                c.execute('INSERT INTO memory.project_grants VALUES(%s,%s,%s)', (aid, self.project, permission))
        self.other = {'id': aid, 'credential_type': 'bootstrap'}
        self.service = self.make_service()

    def make_service(self):
        """An `ExtendedStore` over the store of the test (its chain variant: the same methods, each one a tool call through kairos-mcp)."""
        return ExtendedStore(self.store)

    def make_agent_service(self):
        return AgentStore(self.store)

    def captured(self, tool='Read', mode='summary', content=None):
        payload = {'title': 'Technical tool summary', 'content': content or json.dumps({'tool': tool, 'status': 'success', 'detail': 'private body omitted'}), 'category': 'agent-activity'}
        data = event(self.project, generate=False, payload=payload)
        data['capture'] = {'mode': mode, 'hook_event': 'PostToolUse', 'fingerprint': digest({'project': self.project, 'runtime': data['agent_id'], 'session': data['session_id'], 'event': 'PostToolUse', 'payload': payload})}
        if mode == 'full':
            self.store.set_policy(self.actor, self.project, {'capture_mode': 'full', 'temporal_projection': False})
        self.service.observation_add(self.actor, data)
        return data

    def test_observation_exact_retry_reload_revision_and_withdrawal(self):
        original = event(self.project, generate=False)
        first = self.service.observation_add(self.actor, original)
        self.assertEqual(self.make_service().observation_add(self.actor, original), first)
        with self.assertRaises(Conflict):
            self.service.observation_add(self.actor, {**original, 'payload': {'title': 'Different', 'content': 'Different'}})
        updated = {**original, 'event_id': str(uuid.uuid4()), 'version': 2, 'payload': {'title': 'Árbol: "índice" 🌳', 'content': 'Updated evidence', 'tags': ['a:b', 'one,two', '"sí"']}}
        self.service.observation_record_event(self.actor, updated)
        result = self.make_agent_service().observations(self.actor, self.project, ids=[original['item_id']])['items'][0]
        self.assertEqual(result['tags'], updated['payload']['tags'])
        self.assertEqual(result['version'], 2)
        self.service.observation_record_event(self.actor, {**updated, 'event_id': str(uuid.uuid4()), 'version': 3, 'event_type': 'delete'})
        self.assertEqual(self.make_agent_service().observations(self.actor, self.project, ids=[original['item_id']])['items'], [])
        with self.assertRaises(MemoryError):
            self.service.observation_add(self.actor, updated)

    def test_tool_recovery_is_current_summary_only_and_filter_bound(self):
        first = self.captured()
        self.captured(tool='Write')
        plain = event(self.project, generate=False, payload={'title': 'Not a tool event', 'content': 'Raw unrelated content'})
        self.service.observation_add(self.actor, plain)
        found = self.service.get_tool_uses(self.other, self.project, tool='Read')
        self.assertEqual(len(found['items']), 1)
        self.assertEqual(found['items'][0]['summary'], {'tool': 'Read', 'status': 'success'})
        self.assertNotIn('private body', json.dumps(found))
        page = self.service.get_tool_uses(self.actor, self.project, limit=1)
        self.assertTrue(page['has_more'])
        second = self.service.get_tool_uses(self.actor, self.project, limit=1, cursor=page['next_cursor'])
        self.assertNotEqual(second['items'][0]['event_id'], page['items'][0]['event_id'])
        with self.assertRaises(MemoryError):
            self.service.get_tool_uses(self.actor, self.project, tool='other', cursor=page['next_cursor'])
        self.service.observation_record_event(self.actor, {**first, 'capture': None, 'event_id': str(uuid.uuid4()), 'version': 2, 'event_type': 'delete'})
        self.assertEqual(self.service.get_tool_uses(self.actor, self.project, tool='Read')['items'], [])

    def test_tool_full_raw_is_not_exposed_and_revocation_is_live(self):
        self.captured(mode='full', content='Raw full-consent tool output must not be returned')
        result = self.service.get_tool_uses(self.other, self.project)
        self.assertEqual(result['items'][0]['summary'], {})
        self.assertNotIn('Raw full-consent', json.dumps(result))
        with self.store.transaction() as c:
            c.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (self.other['id'],))
        with self.assertRaises(NotFound):
            self.service.get_tool_uses(self.other, self.project)

    def test_team_two_actors_share_and_private_state_stays_private(self):
        self.make_agent_service().work_write(self.actor, self.project, 'release', {'task': 'private'}, 'private')
        first = self.service.team_write(self.actor, self.project, 'release', {'task': 'shared', 'status': 'doing'}, 'r1', 0)
        self.assertEqual(self.service.team_read(self.other, self.project)['lists'][0]['state'], first['state'])
        second = self.service.team_write(self.other, self.project, 'release', {'task': 'shared', 'owner': 'agent-b'}, 'r1', 1)
        self.assertEqual(second['updated_by'], self.other['id'])
        self.assertEqual(self.make_service().team_write(self.actor, self.project, 'release', {'task': 'shared', 'status': 'doing'}, 'r1', 0), first)
        self.assertEqual(self.make_agent_service().work_read(self.other, self.project)['lists'], [])
        self.assertEqual(self.service.team_search(self.actor, self.project, 'agent-b')['lists'][0]['version'], 2)
        with self.assertRaises(Conflict):
            self.service.team_write(self.actor, self.project, 'release', {'task': 'stale'}, 'r2', 1)
        with self.assertRaises(Conflict):
            self.service.team_write(self.actor, self.project, 'release', {'task': 'different'}, 'r1', 0)

    def test_team_concurrency_denials_capture_policy_and_closed_filter(self):
        def write(_):
            return self.service.team_write(self.actor, self.project, 'release', {'task': 'one'}, 'concurrent', 0)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(write, range(8)))
        self.assertTrue(all(value == results[0] for value in results))
        self.service.team_write(self.other, self.project, 'release', {'task': 'one', 'status': 'done'}, 'finish', 1)
        self.assertEqual(self.service.team_brief(self.actor, self.project)['lists'][0]['state']['tasks'], {})
        self.assertIn('one', self.service.team_read(self.actor, self.project, include_closed=True)['lists'][0]['state']['tasks'])
        with self.store.transaction() as c:
            c.execute("DELETE FROM memory.project_grants WHERE actor_id=%s AND permission='write'", (self.other['id'],))
        with self.assertRaises(Forbidden):
            self.service.team_write(self.other, self.project, 'release', {'task': 'no'}, 'denied')
        with self.assertRaises(NotFound):
            self.service.team_read(self.other, 'unknown-project')
        self.store.set_policy(self.actor, self.project, {'capture_mode': 'off', 'temporal_projection': False})
        with self.assertRaises(Forbidden):
            self.service.team_write(self.actor, self.project, 'release', {'task': 'no'}, 'off')
        with self.store.transaction() as c:
            c.execute('UPDATE memory.actors SET disabled=true WHERE id=%s', (self.other['id'],))
        with self.assertRaises(Unauthorized):
            self.service.team_read(self.other, self.project)

    def test_cross_actor_same_version_race_has_one_winner(self):
        def write(actor):
            try:
                return self.service.team_write(actor, self.project, 'race', {'task': actor['id']}, 'one', 0)
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, [self.actor, self.other]))
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(self.service.team_read(self.actor, self.project)['lists'][0]['version'], 1)

    def test_revocation_between_authorization_and_lock_is_rechecked(self):
        original = self.store._require
        calls = []
        def authorize(c, actor, project, permission):
            original(c, actor, project, permission)
            if not calls:
                calls.append(True)
                with self.store.transaction() as revoke:
                    revoke.execute('DELETE FROM memory.project_grants WHERE actor_id=%s', (self.other['id'],))
        with patch.object(self.store, '_require', side_effect=authorize):
            with self.assertRaises(NotFound):
                self.service.team_read(self.other, self.project)

    def test_tool_superseded_sources_and_non_capture_revisions_are_hidden(self):
        first = self.captured()
        correction = event(self.project, generate=False, event_type='correction',
                           payload={'title': 'Corrected tool observation', 'content': 'Replacement technical evidence', 'supersedes': first['item_id']})
        self.service.observation_add(self.actor, correction)
        self.assertEqual(self.service.get_tool_uses(self.actor, self.project)['items'], [])
        another = self.captured()
        revision_event = {**another, 'capture': None, 'event_id': str(uuid.uuid4()), 'version': 2,
                          'payload': {'title': 'Current noncapture revision', 'content': 'An explicit note'}}
        self.service.observation_record_event(self.actor, revision_event)
        self.assertEqual(self.service.get_tool_uses(self.actor, self.project)['items'], [])

    def test_team_utf8_budget_and_search_beyond_large_earlier_list(self):
        # Each independently valid state approaches 128 KiB using many bounded fields.
        for name in ('a-first', 'b-second', 'z-match'):
            version = 0
            for number in range(9):
                receipt = self.service.team_write(self.actor, self.project, name,
                    {'task': str(number), 'description': '\u00e1'*3500, 'note': '\u00e1'*3500}, name+str(number), version)
                version = receipt['version']
        result = self.service.team_read(self.actor, self.project)
        self.assertTrue(result['truncated'])
        self.assertLess(len(json.dumps(result, ensure_ascii=False).encode('utf-8')), 262_144)
        self.assertEqual(self.service.team_search(self.other, self.project, 'z-match')['lists'][0]['list'], 'z-match')


class ExtendedPostgresChainTests(ExtendedPostgresTests):
    """T-48 (CA-11): the same scenarios, each service call a tool call through kairos-mcp over the same store; the results and refusals are those of the service."""

    def session(self):
        if getattr(self, 'chain', None) is None:
            self.chain = ChainSession(self.store, self.actor)
            self.addCleanup(self.chain.close)
        return self.chain

    def make_service(self):
        return ChainExtendedStore(self.session())

    def make_agent_service(self):
        return ChainAgentStore(self.session())


if __name__ == '__main__':
    unittest.main()
