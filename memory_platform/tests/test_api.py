import asyncio
import time
import unittest
import hashlib
import uuid
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.errors import Unauthorized, Forbidden
from memory_platform.tests.test_store import create_core, event


def fake_app():
    store, auth = Mock(), Mock()
    auth.authenticate_session.side_effect = Unauthorized()
    auth.authenticate_bearer.side_effect = Unauthorized()
    retrieval = Mock(search=AsyncMock(), details=AsyncMock(), context=AsyncMock())
    app = create_app(Settings('unused', max_body_bytes=256), store, auth, retrieval)
    return app, store, auth, retrieval


class BoundaryTests(unittest.TestCase):
    def test_unauthenticated_denies_before_providers(self):
        app, store, auth, retrieval = fake_app()
        with TestClient(app) as client:
            for path, body in [('/v1/search', {'project_ids': ['a'], 'q': 'x'}), ('/v1/details', {'refs': ['episodic:a:a:1']}), ('/v1/context', {'project_ids': ['a'], 'q': 'x'})]:
                response = client.post(path, json=body)
                self.assertEqual(response.status_code, 401, response.text)
            response = client.get('/v1/projects')
            self.assertEqual(response.status_code, 401)
        retrieval.search.assert_not_called()
        retrieval.details.assert_not_called()
        retrieval.context.assert_not_called()
        store.list_projects.assert_not_called()

    def test_chunked_body_limit(self):
        app, _, auth, _ = fake_app()
        with TestClient(app) as client:
            response = client.post('/v1/events', content=iter([b'a'*200, b'b'*100]))
            self.assertEqual(response.status_code, 413, response.text)
        auth.authenticate_bearer.assert_not_called()

    def test_cookie_csrf_applies_to_read_post_and_origin(self):
        app, _, auth, retrieval = fake_app()
        auth.authenticate_session.side_effect = None
        auth.authenticate_session.return_value = {'id': 'actor', 'credential_type': 'session'}
        auth.require_csrf.side_effect = Forbidden()
        with TestClient(app) as client:
            response = client.post('/v1/search', json={'project_ids': ['a'], 'q': 'x'})
            self.assertEqual(response.status_code, 403)
        retrieval.search.assert_not_called()
        auth.require_csrf.assert_called_once()


class ActivityAndPaginationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store, self.auth = Mock(), Mock()
        self.auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer'}
        self.auth.authenticate_session.side_effect = Unauthorized()
        self.retrieval = Mock(search=AsyncMock())
        self.app = create_app(Settings('unused'), self.store, self.auth, self.retrieval,
                              activity_duration=0.025, activity_poll_interval=0.005)
        self.headers = {'Authorization': 'Bearer fixture'}

    def test_activity_bounded_metadata_only_and_resume_has_no_duplicates(self):
        row = {'event_id': 'synthetic-event', 'project_id': 'a', 'event_type': 'note', 'ref': 'episodic:a:uuid:1',
               'created_at': '2026-11-04T10:00:00Z', 'cursor': 'opaque-project-a-event', 'body': 'PRIVATE BODY', 'title': 'PRIVATE TITLE'}
        def activity(actor, pid, cursor=None, limit=50):
            return {'items': [] if cursor else [row], 'next_cursor': cursor or row['cursor'], 'has_more': False}
        self.store.list_activity.side_effect = activity
        with TestClient(self.app) as client:
            response = client.get('/v1/activity?project_id=a', headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn('text/event-stream', response.headers['content-type'])
            self.assertEqual(response.headers['x-accel-buffering'], 'no')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.text.count('event: activity'), 1)
            self.assertIn('event: end', response.text)
            self.assertNotIn('PRIVATE', response.text)
            resumed = client.get('/v1/activity?project_id=a', headers={**self.headers, 'Last-Event-ID': row['cursor']})
            self.assertNotIn('event: activity', resumed.text)
            resumed_with_old_url = client.get('/v1/activity?project_id=a&cursor=older-url-cursor', headers={**self.headers, 'Last-Event-ID': row['cursor']})
            self.assertNotIn('event: activity', resumed_with_old_url.text)
            self.assertEqual(self.store.list_activity.call_args.kwargs['cursor'], row['cursor'])
        self.retrieval.search.assert_not_called()

    def test_activity_rechecks_revocation_and_streams_safe_error(self):
        self.store.list_activity.side_effect = [{'items': [], 'next_cursor': None, 'has_more': False}, Unauthorized()]
        with TestClient(self.app) as client:
            response = client.get('/v1/activity?project_id=a', headers=self.headers)
            self.assertIn('event: error', response.text)
            self.assertIn('unauthorized', response.text)
        self.assertGreaterEqual(self.store.list_activity.call_count, 2)
        self.retrieval.search.assert_not_called()

    def test_activity_denies_missing_auth_and_foreign_origin_before_data(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get('/v1/activity?project_id=a').status_code, 401)
            self.assertEqual(client.get('/v1/activity?project_id=a', headers={**self.headers, 'Origin': 'https://foreign.example'}).status_code, 403)
        self.store.list_activity.assert_not_called()

    async def test_asgi_disconnect_stops_stream_without_further_database_poll(self):
        import asyncio
        self.store.list_activity.return_value = {'items': [], 'next_cursor': None, 'has_more': False}
        app = create_app(Settings('unused'), self.store, self.auth, self.retrieval,
                         activity_duration=5, activity_poll_interval=2)
        disconnected = asyncio.Event()
        initial = True
        messages = []
        async def receive():
            nonlocal initial
            if initial:
                initial = False
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            messages.append(message)
            if message['type'] == 'http.response.body' and b': connected' in message.get('body', b''):
                disconnected.set()
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.0'}, 'http_version': '1.1',
                 'method': 'GET', 'scheme': 'http', 'path': '/v1/activity', 'raw_path': b'/v1/activity',
                 'query_string': b'project_id=a', 'headers': [(b'host', b'localhost'), (b'authorization', b'Bearer fixture')],
                 'client': ('127.0.0.1', 12345), 'server': ('localhost', 8790)}
        # This is a disconnect invariant, not a wall-clock benchmark. A busy
        # container may need seconds to start middleware before sending headers.
        # The call-count assertion still rejects a post-disconnect database poll.
        await asyncio.wait_for(app(scope, receive, send), timeout=10)
        self.assertTrue(disconnected.is_set())
        self.store.list_activity.assert_called_once()
        self.retrieval.search.assert_not_called()

    def test_notes_pagination_exceeds_100_and_cursor_is_project_bound(self):
        notes = [{'id': f'{index:04}', 'item_id': f'{index:04}'} for index in range(103)]
        def listing(actor, pid, limit, cursor):
            return [row for row in notes if cursor is None or row['id'] > cursor][:min(limit, 100)]
        self.store.list_notes.side_effect = listing
        with TestClient(self.app) as client:
            first = client.get('/v1/notes?project_id=a&limit=100', headers=self.headers)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertTrue(first.json()['has_more'])
            cursor = first.json()['next_cursor']
            second = client.get('/v1/notes', params={'project_id': 'a', 'limit': 100, 'cursor': cursor}, headers=self.headers)
            self.assertFalse(second.json()['has_more'])
            self.assertEqual(len(first.json()['items'])+len(second.json()['items']), 103)
            calls = self.store.list_notes.call_count
            denied = client.get('/v1/notes', params={'project_id': 'foreign', 'cursor': cursor}, headers=self.headers)
            self.assertEqual(denied.status_code, 422)
            self.assertEqual(self.store.list_notes.call_count, calls)


class PostgresAPITests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.pid = create_core()
        key = self.store.create_key(self.actor, {'name': 'writer', 'project_ids': [self.pid], 'scopes': ['read', 'write']})
        self.client = TestClient(create_app(Settings(self.store.dsn), store=self.store, activity_duration=0.025, activity_poll_interval=0.005))
        self.client.__enter__()
        self.headers = {'Authorization': 'Bearer '+key['token']}

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_ingest_dedupe_search_details_and_scope(self):
        self.store.extraction_enabled = True  # this test needs the `extract` job: explicit opt-in to MEMORY_EXTRACT_ENABLED
        value = event(self.pid)
        response = self.client.post('/v1/events', json=value, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), self.client.post('/v1/events', json=value, headers=self.headers).json())
        found = self.client.post('/v1/search', json={'project_ids': [self.pid], 'q': 'locking', 'layers': ['episodic']}, headers=self.headers)
        self.assertEqual(found.status_code, 200, found.text)
        ref = found.json()['items'][0]['ref']
        detail = self.client.post('/v1/details', json={'refs': [ref]}, headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['items'][0]['content'], value['payload']['content'])
        receipt = self.client.get('/v1/events/'+value['event_id'], headers=self.headers)
        self.assertEqual(receipt.status_code, 200, receipt.text)
        self.assertEqual(receipt.json()['event_id'], value['event_id'])
        job = self.client.get('/v1/jobs/'+response.json()['jobs'][0], headers=self.headers)
        self.assertEqual(job.status_code, 200, job.text)
        self.assertEqual(job.json()['destination'], 'extract')
        timeline = self.client.post('/v1/timeline', json={'project_ids': [self.pid], 'anchor_ref': ref}, headers=self.headers)
        self.assertEqual(timeline.status_code, 200, timeline.text)
        self.assertEqual(timeline.json()['items'][0]['item_id'], value['item_id'])
        graph = self.client.post('/v1/graph', json={'project_ids': [self.pid], 'q': '', 'layers': ['episodic']}, headers=self.headers)
        self.assertEqual(graph.status_code, 200, graph.text)
        self.assertTrue(any(node['ref'] == ref for node in graph.json()['nodes']))
        activity = self.client.get('/v1/activity', params={'project_id': self.pid}, headers=self.headers)
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertIn(value['event_id'], activity.text)
        self.assertNotIn(value['payload']['content'], activity.text)
        cursor = next(line[4:] for line in activity.text.splitlines() if line.startswith('id: '))
        resumed = self.client.get('/v1/activity', params={'project_id': self.pid}, headers={**self.headers, 'Last-Event-ID': cursor})
        self.assertNotIn('event: activity', resumed.text)
        denied = self.client.post('/v1/search', json={'project_ids': ['another-project'], 'q': 'locking'}, headers=self.headers)
        self.assertEqual(denied.status_code, 404, denied.text)

    def test_document_status_manifest_and_readback(self):
        import uuid
        key = self.store.create_key(self.actor, {'name': 'publisher', 'project_ids': [self.pid], 'scopes': ['read', 'publish', 'validate']})
        headers = {'Authorization': 'Bearer '+key['token']}
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Synthetic document', 'content': 'Canonical approved fixture',
                    'source': {'uri': 'fixture://document', 'sha256': hashlib.sha256(b'Canonical approved fixture').hexdigest()},
                    'validation': {'status': 'validated', 'evidence': ['synthetic test evidence'], 'validated_by': 'test'}}
        prefix = '/v1/projects/'+self.pid
        published = self.client.post(prefix+'/documents', headers=headers, json=document)
        self.assertEqual(published.status_code, 202, published.text)
        status = self.client.get(prefix+'/documents/'+document['document_id'], headers=self.headers)
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['version'], 1)
        self.assertFalse(status.json()['deleted'])
        manifest = self.client.get(prefix+'/manifest', headers=self.headers)
        self.assertEqual(manifest.status_code, 200, manifest.text)
        self.assertEqual(manifest.json()['items'][0]['document_id'], document['document_id'])
        detail = self.client.post('/v1/details', json={'refs': [f"documental:{self.pid}:{document['document_id']}:1"]}, headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['items'][0]['content'], document['content'])

    def test_readonly_cannot_write_or_validate(self):
        key = self.store.create_key(self.actor, {'name': 'read', 'project_ids': [self.pid], 'scopes': ['read']})
        headers = {'Authorization': 'Bearer '+key['token']}
        self.assertEqual(self.client.post('/v1/events', json=event(self.pid), headers=headers).status_code, 403)
        value = event(self.pid)
        value['payload'].update(validation_status='validated', evidence=['fixture'])
        self.assertEqual(self.client.post('/v1/events', json=value, headers=self.headers).status_code, 403)

    def test_login_session_csrf_logout(self):
        with self.store.transaction() as c:
            username = c.execute('SELECT username FROM memory.actors WHERE id=%s', (self.actor['id'],)).fetchone()['username']
        origin = 'http://localhost:5173'
        response = self.client.post('/v1/auth/login', json={'username': username, 'password': 'fixture-password-123'}, headers={'Origin': origin})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()['actor']), {'id', 'username', 'scopes', 'project_ids'})
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        restored = self.client.get('/v1/auth/me')
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertIsInstance(restored.json()['csrf_token'], str)
        self.assertEqual(self.client.post('/v1/search', json={'project_ids': [self.pid], 'q': '', 'layers': ['episodic']}).status_code, 403)
        csrf = restored.json()['csrf_token']
        self.assertEqual(self.client.post('/v1/auth/logout', headers={'Origin': origin, 'X-CSRF-Token': csrf}).status_code, 200)
        self.assertEqual(self.client.get('/v1/auth/me').status_code, 401)


class ParityEndpointTests(unittest.TestCase):
    """C-02: every MCP tool has a `/v1` endpoint. Each endpoint is checked for an allowed caller, a reader without the permission (403) and a project that is not the caller's."""
    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        origin = 'http://localhost:8790'
        self.client = TestClient(create_app(Settings(self.store.dsn, allowed_origins=[origin]), store=self.store, auth=Auth(self.store, [origin])), base_url=origin)
        self.client.__enter__()
        self.writer = self.headers(['read', 'write'])
        self.reader = self.headers(['read'])
        self.other = 'other-' + self.pid[5:]
        self.store.create_project(self.admin, {'id': self.other, 'title': 'Another synthetic project'})
        self.foreign = self.headers(['read', 'write'], [self.other])
        self.prefix = '/v1/projects/' + self.pid

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def headers(self, scopes, projects=None):
        key = self.store.create_key(self.admin, {'name': 'parity', 'project_ids': projects or [self.pid], 'scopes': scopes})
        return {'Authorization': 'Bearer ' + key['token']}

    def tool(self, headers, name, arguments):
        """The same operation through the internal MCP endpoint, with the same credential: what the REST endpoint must equal."""
        import json
        response = self.client.post('/mcp/', headers={**headers, 'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
        result = response.json()['result']
        self.assertFalse(result.get('isError'), result)
        structured = result.get('structuredContent')
        if isinstance(structured, dict) and set(structured) == {'result'} and isinstance(structured['result'], str):
            return json.loads(structured['result'])  # the tools declared `-> str` wrap their JSON text
        return structured if isinstance(structured, dict) else json.loads(result['content'][0]['text'])

    def add(self, **changes):
        value = event(self.pid, **{'generate': False, 'payload': {'title': 'Fencing note', 'content': 'Use fencing before projection', 'category': 'decision', 'source': {'uri': 'fixture://parity'}}, **changes})
        self.store.ingest_event(self.admin, value)
        return value

    def test_build_corpus_accepts_date_start_and_date_end_like_the_tool(self):
        for day in ('2026-11-01', '2026-11-05', '2026-11-09'):
            self.add(occurred_at=day + 'T10:00:00Z')
        body = {'name': 'window', 'date_start': '2026-11-03', 'date_end': '2026-11-07'}
        built = self.client.post(self.prefix + '/corpora', json=body, headers=self.writer)
        self.assertEqual(built.status_code, 200, built.text)
        from memory_platform.agent_store import AgentStore
        direct = AgentStore(self.store).build_corpus({'id': self.admin['id'], 'credential_type': 'bootstrap'}, self.pid, 'window-direct', date_start='2026-11-03', date_end='2026-11-07')
        self.assertEqual(built.json()['count'], 1)
        self.assertEqual(built.json()['count'], direct['count'])
        unfiltered = self.client.post(self.prefix + '/corpora', json={'name': 'everything'}, headers=self.writer)
        self.assertEqual(unfiltered.json()['count'], 3)  # no field, no change: an existing request keeps its meaning
        self.assertEqual(self.client.post(self.prefix + '/corpora', json={'name': 'bad', 'date_start': 'yesterday'}, headers=self.writer).status_code, 422)
        self.assertEqual(self.client.post(self.prefix + '/corpora', json=body, headers=self.reader).status_code, 403)
        self.assertEqual(self.client.post(self.prefix + '/corpora', json=body, headers=self.foreign).status_code, 404)

    def test_capture_policy_endpoint_returns_what_the_tool_returns(self):
        url = self.prefix + '/capture-policy'
        for headers, allowed in ((self.writer, True), (self.reader, False)):
            response = self.client.get(url, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'project_id': self.pid, 'capture_mode': 'summary', 'capture_allowed': allowed})
            self.assertEqual(response.json(), self.tool(headers, 'capture_policy', {'project_id': self.pid}))
        self.store.set_policy(self.admin, self.pid, {'capture_mode': 'off', 'temporal_projection': False})
        self.assertEqual(self.client.get(url, headers=self.writer).json(), self.tool(self.writer, 'capture_policy', {'project_id': self.pid}))
        self.assertFalse(self.client.get(url, headers=self.writer).json()['capture_allowed'])
        self.assertEqual(self.client.get(url, headers=self.foreign).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 401)
        # a key that cannot even read the project gets no answer; the reader (read only) is allowed to read and told it cannot write
        none = self.headers(['write'])
        self.assertEqual(self.client.get(url, headers=none).status_code, 403)
        # `GET .../policy` keeps its own shape
        self.assertEqual(set(self.client.get(self.prefix + '/policy', headers=self.writer).json()), {'capture_mode', 'temporal_projection'})

    def test_event_status_by_project_reconciles_like_the_tool_in_one_call(self):
        import uuid
        self.store.extraction_enabled = True  # the receipt then carries a job to reconcile (explicit opt-in to MEMORY_EXTRACT_ENABLED)
        value = event(self.pid)
        self.assertEqual(self.client.post('/v1/events', json=value, headers=self.writer).status_code, 202)
        url = self.prefix + '/events/' + value['event_id'] + '/status'
        found = self.client.get(url, headers=self.writer)
        self.assertEqual(found.status_code, 200, found.text)
        body = found.json()
        self.assertEqual(body['receipt']['event_id'], value['event_id'])
        self.assertTrue(body['jobs'] and isinstance(body['complete'], bool))
        self.assertEqual(body, self.tool(self.writer, 'event_status', {'event_id': value['event_id'], 'project_id': self.pid}))
        # the two reads it composes are unchanged
        self.assertEqual(self.client.get('/v1/events/' + value['event_id'], headers=self.writer).json(), body['receipt'])
        self.assertEqual(self.client.get('/v1/jobs/' + body['receipt']['jobs'][0], headers=self.writer).json(), body['jobs'][0])
        # explicit absence is a 200 with found=false, as in the tool
        missing = str(uuid.uuid4())
        absent = self.client.get(self.prefix + '/events/' + missing + '/status', headers=self.writer)
        self.assertEqual(absent.status_code, 200, absent.text)
        self.assertEqual(absent.json(), {'found': False, 'event_id': missing, 'project_id': self.pid})
        self.assertEqual(absent.json(), self.tool(self.writer, 'event_status', {'event_id': missing, 'project_id': self.pid}))
        # reconciling needs read AND write: a reader and another project's key are refused
        self.assertEqual(self.client.get(url, headers=self.reader).status_code, 403)
        self.assertEqual(self.client.get(url, headers=self.foreign).status_code, 404)
        self.assertEqual(self.client.get(self.prefix + '/events/not-a-uuid/status', headers=self.writer).status_code, 422)

    def test_observation_reads_return_what_the_three_tools_return_and_the_portal_listing_is_untouched(self):
        fencing = self.add(item_id=str(uuid.uuid4()), occurred_at='2026-11-02T10:00:00Z')
        other = self.add(item_id=str(uuid.uuid4()), occurred_at='2026-11-03T10:00:00Z', payload={'title': 'Index choice', 'content': 'Prefer a partial index for archived rows', 'source': {'uri': 'fixture://parity'}})
        base = self.prefix + '/observations'
        # get_observations: selected ids
        got = self.client.post(base + '/get', json={'ids': [fencing['item_id'], other['item_id']]}, headers=self.reader)
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual({item['id'] for item in got.json()['items']}, {fencing['item_id'], other['item_id']})
        self.assertEqual(got.json(), self.tool(self.reader, 'get_observations', {'projectId': self.pid, 'ids': [fencing['item_id'], other['item_id']]}))
        # observation_search: lexical, bounded
        found = self.client.get(base + '/search', params={'query': 'fencing', 'limit': 5}, headers=self.reader)
        self.assertEqual(found.status_code, 200, found.text)
        self.assertEqual([item['id'] for item in found.json()['items']], [fencing['item_id']])
        self.assertEqual(found.json(), self.tool(self.reader, 'observation_search', {'projectId': self.pid, 'query': 'fencing', 'limit': 5}))
        # observation_context: the evidence plus its text and the untrusted-data warning
        context = self.client.get(base + '/context', params={'query': 'index'}, headers=self.reader)
        self.assertEqual(context.status_code, 200, context.text)
        self.assertIn('[' + other['item_id'] + ']', context.json()['context'])
        self.assertIn('untrusted', context.json()['warning'])
        self.assertEqual(context.json(), self.tool(self.reader, 'observation_context', {'projectId': self.pid, 'query': 'index'}))
        # the limits of each tool
        self.assertEqual(self.client.get(base + '/search', params={'query': 'x', 'limit': 101}, headers=self.reader).status_code, 422)
        self.assertEqual(self.client.get(base + '/context', params={'limit': 201}, headers=self.reader).status_code, 422)
        self.assertEqual(self.client.post(base + '/get', json={'ids': []}, headers=self.reader).status_code, 422)
        self.assertEqual(self.client.post(base + '/get', json={'ids': ['a'] * 101}, headers=self.reader).status_code, 422)
        # a key without read permission is refused, another project's key finds no project
        nothing = self.headers(['write'])
        for headers, status in ((nothing, 403), (self.foreign, 404)):
            self.assertEqual(self.client.post(base + '/get', json={'ids': [fencing['item_id']]}, headers=headers).status_code, status)
            self.assertEqual(self.client.get(base + '/search', params={'query': 'fencing'}, headers=headers).status_code, status)
            self.assertEqual(self.client.get(base + '/context', headers=headers).status_code, status)
        self.assertEqual(self.client.get(base + '/search', params={'query': 'fencing'}).status_code, 401)
        # no leak between projects: the other project's observation is invisible to the first project's endpoints
        mine = self.store.create_project(self.admin, {'id': 'third-' + self.pid[5:], 'title': 'Third'}) and 'third-' + self.pid[5:]
        self.assertEqual(self.client.get('/v1/projects/' + mine + '/observations/search', params={'query': 'fencing'}, headers=self.headers(['read'], [mine])).json()['items'], [])
        # non-regression: `GET /v1/observations` still serves the portal listing, with its own shape
        listing = self.client.get('/v1/observations', params={'project_id': self.pid}, headers=self.reader)
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(set(listing.json()), {'items', 'next_cursor', 'has_more', 'filters', 'ordering', 'rule_policy'})  # the shape of HEAD
        self.assertNotIn('mode', listing.json())


class DegradedSemanticHttpTests(unittest.TestCase):
    """CA-16 and CA-17 over HTTP with the real retrieval: a failing embeddings provider degrades, it does not fail."""
    def build(self, embed, query_timeout=0.3):
        from memory_platform.retrieval import Retrieval
        store, auth = Mock(), Mock()
        auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer'}
        auth.authenticate_session.side_effect = Unauthorized()
        store.search_items.return_value = [{'ref': 'episodic:a:lex:1', 'project_id': 'a', 'item_id': 'lex', 'version': 1, 'layer': 'episodic',
                                            'title': 'Lexical', 'excerpt': 'x', 'validation_status': 'unknown'}]
        store.search_documents.return_value, store.search_native_facts.return_value, store.has_vectors.return_value = [], [], True
        settings = Settings('unused', request_timeout=5, embedding_query_timeout=query_timeout)
        self.embeddings = Mock(embed=embed)
        return create_app(settings, store, auth, Retrieval(store, settings, self.embeddings))

    def test_search_and_context_answer_with_lexical_hits_and_degraded_when_the_provider_fails(self):
        from memory_platform.providers import ProviderError
        app = self.build(AsyncMock(side_effect=ProviderError('http_503')))
        with TestClient(app) as client:
            for path in ('/v1/search', '/v1/context'):
                response = client.post(path, json={'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic']}, headers={'Authorization': 'Bearer fixture'})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual([item['item_id'] for item in body['items']], ['lex'])
                self.assertEqual(body['backends']['semantic']['status'], 'unavailable')
                self.assertEqual(body['degraded'], {'layer': 'semantic', 'reason': 'provider_error'})
                self.assertTrue(body['partial'])

    def test_semantic_budget_ms_is_optional_bounded_and_cuts_the_semantic_layer_short(self):
        async def stalled(*args, **kwargs):
            await asyncio.sleep(30)
        app = self.build(AsyncMock(side_effect=stalled), query_timeout=5.0)
        headers = {'Authorization': 'Bearer fixture'}
        with TestClient(app) as client:
            for path in ('/v1/search', '/v1/context'):
                for bad in (0, -1, 600001, 'soon', True, '1100'):
                    response = client.post(path, json={'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic'], 'semantic_budget_ms': bad}, headers=headers)
                    self.assertEqual(response.status_code, 422, (path, bad, response.text))
                started = time.monotonic()
                response = client.post(path, json={'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic'], 'semantic_budget_ms': 120}, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertLessEqual(time.monotonic() - started, 0.12 + 0.5)
                self.assertEqual(response.json()['degraded'], {'layer': 'semantic', 'reason': 'timeout'})
                self.assertEqual([item['item_id'] for item in response.json()['items']], ['lex'])

    def test_semantic_false_makes_no_provider_call_and_reports_no_degradation(self):
        app = self.build(AsyncMock())
        with TestClient(app) as client:
            response = client.post('/v1/search', json={'project_ids': ['a'], 'q': 'fencing', 'layers': ['episodic'], 'semantic': False}, headers={'Authorization': 'Bearer fixture'})
        body = response.json()
        self.assertEqual(body['backends']['semantic']['status'], 'off')
        self.assertNotIn('degraded', body)
        self.embeddings.embed.assert_not_awaited()
