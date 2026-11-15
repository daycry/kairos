"""The four controls of the API that no other test would miss if they were removed (I3 / CA-35): the body limit, `/v1/users`,
`/health/ready` and the work-state budget. Each has a positive and a negative test; removing the control turns the negative one red."""
import unittest
import uuid
from unittest.mock import Mock, AsyncMock

from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.test_store import create_core

LIMIT = 256


def mock_app():
    store, auth = Mock(), Mock()
    auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer', 'is_admin': False}
    return create_app(Settings('unused', max_body_bytes=LIMIT), store, auth, Mock(search=AsyncMock(return_value={'items': []}))), store, auth


class BodyLimitTests(unittest.TestCase):
    """`BodyLimit` (app.py): 413 `body_too_large` before authentication, by Content-Length and by chunks, exact at the boundary."""

    def post(self, content, **kwargs):
        app, store, auth = mock_app()
        with TestClient(app) as client:
            response = client.post('/v1/search', content=content, headers={'Authorization': 'Bearer fixture', 'Content-Type': 'application/json'}, **kwargs)
        return response, auth

    def test_a_body_over_the_limit_is_refused_before_authentication(self):
        response, auth = self.post(b'{"q":"' + b'a' * LIMIT + b'"}')
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(response.json()['error']['code'], 'body_too_large')
        self.assertTrue(response.json()['request_id'])
        auth.authenticate_bearer.assert_not_called()

    def test_a_chunked_body_over_the_limit_is_refused(self):
        response, auth = self.post(iter([b'a' * 200, b'b' * 100]))
        self.assertEqual((response.status_code, response.json()['error']['code']), (413, 'body_too_large'))
        auth.authenticate_bearer.assert_not_called()

    def test_a_body_of_exactly_the_limit_is_not_refused(self):
        response, auth = self.post(b' ' * LIMIT)  # whitespace: not valid JSON, so a 422 from the contract, which proves the body got through
        self.assertEqual(response.status_code, 422, response.text)

    def test_a_body_one_byte_over_the_limit_is_refused(self):
        response, auth = self.post(b' ' * (LIMIT + 1))
        self.assertEqual(response.status_code, 413, response.text)

    def test_a_small_body_reaches_the_handler(self):
        response, auth = self.post(b'{"project_ids":["a"],"q":"x"}')
        self.assertNotEqual(response.status_code, 413, response.text)
        auth.authenticate_bearer.assert_called_once()


class UsersEndpointTests(unittest.TestCase):
    """`/v1/users` is for global administrators only: a project administrator manages users of their own projects, never lists them."""

    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.other = 'other-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.admin, {'id': self.other, 'title': 'Another synthetic project'})

        class Identities(Auth):
            """Tokens `actor:<id>` stand for an actor with the bootstrap credential; anything else is an API key, as in production."""
            def authenticate_bearer(self, token):
                if token.startswith('actor:'):
                    return {'id': token[6:], 'credential_type': 'bootstrap'}
                return super().authenticate_bearer(token)

        self.client = TestClient(create_app(Settings(self.store.dsn), store=self.store, auth=Identities(self.store, [])))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.as_admin = {'Authorization': 'Bearer actor:' + self.admin['id']}
        self.owner = self.make_user('owner', [self.pid])      # administrator of its project, not a global one
        self.stranger = self.make_user('stranger', [self.other])

    def make_user(self, label, projects):
        created = self.store.create_user(self.admin, {'username': f'{label}-{uuid.uuid4().hex[:10]}', 'password': 'fixture-password-123',
                                                      'project_ids': projects, 'scopes': ['read', 'write', 'admin']})
        return {'created': created, 'headers': {'Authorization': 'Bearer actor:' + created['id']}}

    def body(self, projects, label='new'):
        return {'username': f'{label}-{uuid.uuid4().hex[:10]}', 'password': 'fixture-password-123', 'project_ids': projects, 'scopes': ['read']}

    def test_the_global_administrator_lists_users_with_their_grants(self):
        response = self.client.get('/v1/users', headers=self.as_admin)
        self.assertEqual(response.status_code, 200, response.text)
        mine = {item['username']: item for item in response.json()['items']}[self.owner['created']['username']]
        self.assertEqual((mine['project_ids'], mine['scopes']), ([self.pid], ['admin', 'read', 'write']))
        self.assertNotIn('password_hash', mine)

    def test_the_global_administrator_creates_a_user(self):
        body = self.body([self.pid])
        response = self.client.post('/v1/users', json=body, headers=self.as_admin)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()['username'], response.json()['project_ids']), (body['username'], [self.pid]))
        self.assertNotIn('password', response.json())

    def test_a_project_administrator_cannot_list_users(self):
        self.assertEqual(self.client.get('/v1/users', headers=self.owner['headers']).status_code, 403)

    def test_an_administrator_key_cannot_list_users_either(self):
        key = self.store.create_key(self.admin, {'name': 'admin key', 'project_ids': [self.pid], 'scopes': ['read', 'write', 'admin']})
        self.assertEqual(self.client.get('/v1/users', headers={'Authorization': 'Bearer ' + key['token']}).status_code, 403)

    def test_a_project_administrator_creates_users_for_their_own_project(self):
        response = self.client.post('/v1/users', json=self.body([self.pid], 'delegated'), headers=self.owner['headers'])
        self.assertEqual(response.status_code, 200, response.text)

    def test_a_user_of_another_project_cannot_create_users_here(self):
        body = self.body([self.pid], 'intruder')
        response = self.client.post('/v1/users', json=body, headers=self.stranger['headers'])
        self.assertIn(response.status_code, (403, 404), response.text)
        self.assertNotIn(body['username'], {item['username'] for item in self.client.get('/v1/users', headers=self.as_admin).json()['items']})

    def test_a_user_cannot_delegate_a_project_they_do_not_hold(self):
        body = self.body([self.pid, self.other], 'wider')
        response = self.client.post('/v1/users', json=body, headers=self.owner['headers'])
        self.assertIn(response.status_code, (403, 404), response.text)
        self.assertNotIn(body['username'], {item['username'] for item in self.client.get('/v1/users', headers=self.as_admin).json()['items']})

    def test_anonymous_and_unknown_callers_are_refused(self):
        self.assertEqual(self.client.get('/v1/users').status_code, 401)
        self.assertEqual(self.client.get('/v1/users', headers={'Authorization': 'Bearer mp_unknown'}).status_code, 401)
        self.assertEqual(self.client.post('/v1/users', json=self.body([self.pid])).status_code, 401)


class ReadinessTests(unittest.TestCase):
    """`/health/ready` answers from the database: ready when the migration table is readable, 503 `not_ready` when it is not."""

    def test_ready_when_the_database_answers(self):
        store, *_ = create_core()
        with TestClient(create_app(Settings(store.dsn), store=store, auth=Mock(), retrieval=Mock())) as client:
            response = client.get('/health/ready')
        self.assertEqual((response.status_code, response.json()), (200, {'status': 'ready'}))

    def test_not_ready_when_the_database_cannot_be_read(self):
        store = Mock()
        store.transaction.side_effect = RuntimeError('database down')
        with TestClient(create_app(Settings('unused'), store=store, auth=Mock(), retrieval=Mock())) as client:
            response = client.get('/health/ready')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'not_ready')
        self.assertNotIn('database down', response.text)

    def test_not_ready_without_the_migration_table(self):
        store = Mock()
        store.transaction.return_value.__enter__ = Mock(return_value=Mock(execute=Mock(side_effect=RuntimeError('relation does not exist'))))
        store.transaction.return_value.__exit__ = Mock(return_value=False)
        with TestClient(create_app(Settings('unused'), store=store, auth=Mock(), retrieval=Mock())) as client:
            self.assertEqual(client.get('/health/ready').status_code, 503)

    def test_readiness_follows_the_database_through_a_cut_and_a_restore(self):
        from memory_platform.store import Store
        from memory_platform.tests.fault_proxy import FaultProxy
        real, *_ = create_core()  # migrated through the direct connection
        with FaultProxy() as proxy:
            store = Store(proxy.dsn())
            with TestClient(create_app(Settings(store.dsn), store=store, auth=Mock(), retrieval=Mock())) as client:
                self.assertEqual(client.get('/health/ready').status_code, 200)
                proxy.cut()
                down = client.get('/health/ready')
                self.assertEqual((down.status_code, down.json()['error']['code']), (503, 'not_ready'))
                self.assertEqual(client.get('/health/live').status_code, 200)  # liveness never depends on the database
                proxy.restore()
                self.assertEqual(client.get('/health/ready').status_code, 200)


class WorkBudgetTests(unittest.TestCase):
    """`work_write` refuses past 100 lists per actor and project, or 10,000 entries: 409 `work_budget_exceeded`."""

    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.client = TestClient(create_app(Settings(self.store.dsn), store=self.store, auth=Auth(self.store, [])))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        key = self.store.create_key(self.admin, {'name': 'work', 'project_ids': [self.pid], 'scopes': ['read', 'write']})
        self.headers = {'Authorization': 'Bearer ' + key['token']}
        self.actor_id = self.admin['id']

    def write(self, name, request_id=None):
        return self.client.post(f'/v1/projects/{self.pid}/work-state', headers=self.headers,
                                json={'list': name, 'fields': {'note': 'x'}, 'request_id': request_id or uuid.uuid4().hex})

    def seed_lists(self, count):
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.agent_work_lists(project_id,actor_id,name,version,canonical_hash,state) "
                      "SELECT %s,%s,'seed-'||g,1,'h','{\"fields\":{},\"tasks\":{}}'::jsonb FROM generate_series(1,%s) g", (self.pid, self.actor_id, count))

    def seed_entries(self, list_name, count):
        with self.store.transaction() as c:
            c.execute("INSERT INTO memory.agent_work_entries(project_id,actor_id,list_name,request_id,request_hash,fields,receipt) "
                      "SELECT %s,%s,%s,'seed-'||g,'h','{}'::jsonb,'{}'::jsonb FROM generate_series(1,%s) g", (self.pid, self.actor_id, list_name, count))

    def test_writes_below_the_budget_succeed(self):
        self.seed_lists(99)
        response = self.write('the-hundredth')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['version'], 1)

    def test_a_new_list_past_one_hundred_is_refused(self):
        self.seed_lists(100)
        response = self.write('one-too-many')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['error']['code'], 'work_budget_exceeded')
        with self.store.transaction() as c:
            self.assertEqual(c.execute("SELECT count(*) AS n FROM memory.agent_work_lists WHERE project_id=%s AND name='one-too-many'", (self.pid,)).fetchone()['n'], 0)

    def test_an_existing_list_is_still_written_when_only_the_list_count_is_full(self):
        self.seed_lists(100)
        response = self.write('seed-1')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['version'], 2)

    def test_entries_past_ten_thousand_are_refused_even_for_an_existing_list(self):
        self.assertEqual(self.write('main').status_code, 200)
        self.seed_entries('main', 9_998)  # 9,999 in all: one more fits
        self.assertEqual(self.write('main').status_code, 200)
        refused = self.write('main')
        self.assertEqual((refused.status_code, refused.json()['error']['code']), (409, 'work_budget_exceeded'))

    def test_another_project_is_not_charged_with_this_budget(self):
        self.seed_lists(100)
        other = 'budget-' + uuid.uuid4().hex[:10]
        self.store.create_project(self.admin, {'id': other, 'title': 'Isolated budget project'})
        self.store.set_policy(self.admin, other, {'capture_mode': 'summary', 'temporal_projection': True})
        key = self.store.create_key(self.admin, {'name': 'work2', 'project_ids': [other], 'scopes': ['read', 'write']})
        response = self.client.post(f'/v1/projects/{other}/work-state', headers={'Authorization': 'Bearer ' + key['token']},
                                    json={'list': 'fresh', 'fields': {'note': 'x'}, 'request_id': uuid.uuid4().hex})
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == '__main__':
    unittest.main()
