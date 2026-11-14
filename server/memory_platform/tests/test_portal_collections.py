"""Current, filter-bound portal pages on isolated PostgreSQL."""
import unittest
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import MemoryError, NotFound
from memory_platform.portal_store import PortalStore
from memory_platform.tests.test_store import create_core, event


class PortalCollectionsTests(unittest.TestCase):
    def test_category_filters_sessions_jobs_and_history_before_paging_and_http(self):
        store, actor, project = create_core(extraction=True)
        service, source = PortalStore(store), {}
        for category, session in [('other', 'excluded'), ('API', 'session-a'), ('API', 'session-b')]:
            value = event(project, session_id=session, payload={'title': 'Selected '+session,
                          'content': 'Synthetic evidence', 'category': category})
            receipt = store.ingest_event(actor, value)
            source[session] = (value, receipt)
        first = service.page(actor, project, 'sessions', category='API', limit=1)
        second = service.page(actor, project, 'sessions', category='API', limit=1, cursor=first['next_cursor'])
        self.assertEqual({item['id'] for item in first['items']+second['items']}, {'session-a', 'session-b'})
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        expected_ids = {'sessions': 'session-a', 'jobs': source['session-a'][1]['jobs'][0],
                        'history': source['session-a'][0]['event_id']}
        for kind in ('sessions', 'jobs', 'history'):
            with self.subTest(collection=kind):
                result = service.page(actor, project, kind, category='API', session_id='session-a')
                self.assertEqual(len(result['items']), 1)
                item = result['items'][0]
                self.assertEqual(item['event_id'] if kind == 'history' else item['id'], expected_ids[kind])
                self.assertEqual(service.page(actor, project, kind, category='other', session_id='session-a')['items'], [])
                with self.assertRaises(MemoryError):
                    wrong_category = 'other' if kind == 'sessions' else 'API'
                    service.page(actor, project, kind, category=wrong_category, cursor=first['next_cursor'])
        token = store.create_key(actor, {'name': 'filtered-read', 'project_ids': [project], 'scopes': ['read']})['token']
        with TestClient(create_app(Settings('unused'), store=store, auth=Auth(store))) as client:
            for kind in ('sessions', 'jobs', 'history'):
                response = client.get('/v1/'+kind, params={'project_id': project, 'category': 'API', 'session_id': 'session-a'}, headers={'Authorization': 'Bearer '+token})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()['items']), 1)

    def test_each_text_filter_matches_a_query_without_accent_or_inflection(self):
        """Decision P-03: the five text filters use the Spanish/English configurations too (all failed before)."""
        store, actor, project = create_core(extraction=True)
        service = PortalStore(store)
        value = event(project, session_id='session-fts', agent_id='configuración-ágil', payload={
            'title': 'Configuración de las canciones', 'content': 'La configuración vive en el servidor', 'category': 'API'})
        store.ingest_event(actor, value)
        other = event(project, session_id='session-other', agent_id='fixture', payload={'title': 'Sin relación', 'content': 'Texto distinto', 'category': 'API'})
        store.ingest_event(actor, other)
        expected = {'sessions': ('configuracion agil', 'id', 'session-fts'), 'jobs': ('upserting', 'item_id', value['item_id']),
                    'history': ('configuracion cancion', 'event_id', value['event_id']), 'activity-log': ('notes', 'item_id', value['item_id']),
                    'notes': ('configuracion cancion', 'item_id', value['item_id'])}
        for kind, (query, key, wanted) in expected.items():
            with self.subTest(collection=kind):
                found = [item[key] for item in service.page(actor, project, kind, query=query, limit=50)['items']]
                self.assertIn(wanted, found)
        self.assertEqual([i['item_id'] for i in service.page(actor, project, 'notes', query='configuracion cancion')['items']], [value['item_id']])
        self.assertEqual(service.page(actor, project, 'notes', query='zzzunrelated')['items'], [])

    def test_notes_filter_reads_the_stored_language_vectors(self):
        """The notes filter uses the indexed `search_vector_es`/`_en` (nothing recomputed per row for those two)."""
        from contextlib import contextmanager
        from unittest.mock import patch
        store, actor, project = create_core()
        service = PortalStore(store)
        statements = []
        original = store.transaction

        @contextmanager
        def spied():
            with original() as connection:
                class Spy:
                    def execute(_, query, params=None, **kw):
                        statements.append(str(query))
                        return connection.execute(query, params, **kw) if params is not None else connection.execute(query, **kw)

                    def __getattr__(_, name):
                        return getattr(connection, name)
                yield Spy()
        with patch.object(store, 'transaction', spied):
            service.page(actor, project, 'notes', query='configuracion cancion')
        notes = next(s for s in statements if 'FROM memory.memory_items i' in s)
        self.assertIn('i.search_vector_es @@', notes)
        self.assertIn('i.search_vector_en @@', notes)
        self.assertNotIn("to_tsvector('spanish'", notes)
        self.assertNotIn('i.*', notes)

    def test_filters_precede_paging_cursor_is_bound_and_withdrawal_hides_rule(self):
        store, actor, project = create_core()
        service = PortalStore(store)
        ids = []
        for category, session, title in [('other', 'old', 'Excluded'), ('API', 'older-session', 'First'), ('API', 'older-session', 'Second')]:
            value = event(project, generate=False, session_id=session,
                          payload={'title': title, 'content': 'Evidence', 'category': category, 'tags': ['kairos:rule', 'note:one,two']})
            store.ingest_event(actor, value)
            if category == 'API':
                ids.append(value['item_id'])
        first = service.page(actor, project, 'rules', category='API', session_id='older-session', limit=1)
        self.assertEqual(len(first['items']), 1)
        self.assertTrue(first['has_more'])
        second = service.page(actor, project, 'rules', category='API', session_id='older-session', limit=1, cursor=first['next_cursor'])
        self.assertFalse(second['has_more'])
        self.assertEqual({row['item_id'] for row in first['items']+second['items']}, set(ids))
        with self.assertRaises(MemoryError):
            service.page(actor, project, 'notes', category='API', session_id='older-session', cursor=first['next_cursor'])
        with self.assertRaises(MemoryError):
            service.page(actor, project, 'rules', category='other', session_id='older-session', cursor=first['next_cursor'])
        store.ingest_event(actor, event(project, item_id=ids[0], version=2, event_type='delete', generate=False))
        self.assertEqual(len(service.page(actor, project, 'rules', category='API')['items']), 1)
        with self.assertRaises(NotFound):
            service.page(actor, 'unknown-project', 'rules')

    def test_http_session_filter_and_activity_metadata_only(self):
        store, actor, project = create_core()
        value = event(project, generate=False, session_id='selected-session',
                      payload={'title': '<script>text only</script>', 'content': 'Private fixture body', 'category': 'API'})
        store.ingest_event(actor, value)
        token = store.create_key(actor, {'name': 'read', 'project_ids': [project], 'scopes': ['read']})['token']
        headers = {'Authorization': 'Bearer '+token}
        with TestClient(create_app(Settings('unused'), store=store, auth=Auth(store))) as client:
            result = client.get('/v1/notes', params={'project_id': project, 'session_id': 'selected-session', 'category': 'API'}, headers=headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['items'][0]['item_id'], value['item_id'])
            empty = client.get('/v1/observations', params={'project_id': project, 'session_id': 'different-session'}, headers=headers)
            self.assertEqual(empty.json()['items'], [])
            activity = client.get('/v1/activity-log', params={'project_id': project}, headers=headers)
            self.assertEqual(activity.status_code, 200)
            self.assertNotIn('Private fixture body', activity.text)
            self.assertNotIn('<script>', activity.text)
            self.assertEqual(activity.json()['items'][0]['event_id'], value['event_id'])
