"""CA-11 (T-22): the revocation matrix. A key that answers 200 on `/v1`, on the internal `/mcp` and on the `/mcp` of kairos-mcp, and that keeps an activity stream open, gets 401
on the NEXT request of each route once it is revoked, once it expires and once its owner is disabled; the open stream closes within one poll interval and a margin. A session of the
portal that is closed, or whose user is disabled, gets 401 too.

Where each route is: `/v1` and the internal `/mcp` are the server application (the internal MCP authenticates with the same functions as `/v1`, `mcp.py` `AuthenticatedMCP`: this
matrix confirms the hypothesis of the spec); the `/mcp` of kairos-mcp is kairos-mcp in process in front of that application (`chain_harness.py`: every call it makes is the real `/v1`
request, its credential check is `GET /v1/auth/me`). The hop through the web proxy is `location /mcp` -> `memory-mcp:8791`, which drops the cookie: its rules are checked as text in
`test_nginx_routes.py` and with a real nginx by `nginx_portal_probe.py`; the proxy adds nothing to the credential, so the matrix does not need a Docker daemon.

The store has a pool of ONE connection: what a transaction resolved about permissions must not outlive it, and a single connection is where a cache that did would show.
No sleep: the stream is driven over ASGI and its frames are timed as they are sent.
"""
import asyncio
import time
import unittest
import uuid

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.store_pool import close_pool
from memory_platform.tests import test_passwords as pw
from memory_platform.tests.chain_harness import ChainClient
from memory_platform.tests.test_access_users import ORIGIN, UsersFixture
from memory_platform.tests.test_store_pool import pool_store

BASE = 'http://localhost:8790'
POLL = 0.05  # the poll interval of the stream in these tests (2 s in a deployment)
MARGIN = 2.0  # what a busy test container may add to one poll before the closing frame is sent
ACCEPT = 'application/json, text/event-stream'
CALL = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'projects', 'arguments': {}}}
CAUSES = ('revoked', 'expired', 'disabled')
ROUTES = ('/v1', '/mcp internal', '/mcp kairos-mcp')


class MatrixFixture(UsersFixture):
    def setUp(self):
        super().setUp()
        self.pooled = pool_store(self.dsn, minimum=1, maximum=1)
        self.addCleanup(close_pool, self.pooled)
        self.auth = Auth(self.pooled, [ORIGIN, BASE])
        self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN, BASE), mount_mcp=True), store=self.pooled, auth=self.auth,
                              activity_duration=20.0, activity_poll_interval=POLL)
        self.chain = ChainClient(self.app, base_url=BASE)
        self.chain.__enter__()
        self.addCleanup(self.chain.__exit__, None, None, None)
        self.root_actor = self.auth.login('root-user', 'root-password-123', '198.51.100.200')['actor']

    def owner(self):
        """A fresh user, administrator of p1, and a key of it (each cause kills a credential of its own)."""
        name = 'm-' + uuid.uuid4().hex[:10]
        user = self.store.create_user(self.admin, {'username': name, 'password': pw.PASSWORD, 'project_ids': ['p1'], 'scopes': ['read', 'admin']})
        actor = self.auth.login(name, pw.PASSWORD, '198.51.100.%d' % (uuid.uuid4().int % 200 + 1))['actor']
        return user['id'], self.store.create_key(actor, {'name': 'matrix', 'project_ids': ['p1'], 'scopes': ['read']})

    def kill(self, cause, user_id, key):
        if cause == 'revoked':
            return self.pooled.revoke_key(self.root_actor, key['id'])
        if cause == 'expired':  # the row dated back: the clock of the database says it expired
            return self.observer.execute("UPDATE memory.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (key['id'],))
        return self.pooled.set_user_disabled(self.root_actor, user_id, True)

    def request(self, route, token=None, client=None, headers=None):
        sent = {'Authorization': 'Bearer ' + token} if token else {}
        sent.update(headers or {})
        if route == '/v1':
            response = (client or self.chain).get('/v1/projects', headers=sent)
        elif route == '/mcp internal':
            response = (client or self.chain.server_mcp).post('/mcp/', headers={**sent, 'Accept': ACCEPT}, json=CALL)
        else:
            response = self.chain.post('/mcp/', headers={**sent, 'Accept': ACCEPT}, json=CALL)
        if response.status_code == 200 and route != '/v1':
            self.assertFalse(response.json()['result'].get('isError'), response.text[:300])
        return response.status_code

    def stream(self, token, kill):
        """Open `GET /v1/activity` with the key over ASGI, kill the credential once the stream is connected, and return (status, seconds from the kill to the closing frame, text)."""
        async def run():
            connected, done, frames, status = asyncio.Event(), asyncio.Event(), [], []
            first = [True]

            async def receive():
                if first[0]:
                    first[0] = False
                    return {'type': 'http.request', 'body': b'', 'more_body': False}
                await done.wait()
                return {'type': 'http.disconnect'}

            async def send(message):
                if message['type'] == 'http.response.start':
                    status.append(message['status'])
                elif message['type'] == 'http.response.body':
                    body = message.get('body', b'')
                    frames.append((time.monotonic(), body))
                    if b': connected' in body:
                        connected.set()
                    if not message.get('more_body', False):
                        done.set()
            scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.0'}, 'http_version': '1.1', 'method': 'GET', 'scheme': 'http', 'path': '/v1/activity',
                     'raw_path': b'/v1/activity', 'query_string': b'project_id=p1', 'root_path': '',
                     'headers': [(b'host', b'localhost'), (b'authorization', ('Bearer ' + token).encode())], 'client': ('127.0.0.1', 50000), 'server': ('localhost', 8790)}
            served = asyncio.create_task(self.app(scope, receive, send))
            await asyncio.wait_for(connected.wait(), 30)
            await asyncio.to_thread(kill)
            killed = time.monotonic()
            await asyncio.wait_for(done.wait(), 30)
            await asyncio.wait_for(served, 30)
            closing = [at for at, body in frames if b'event: error' in body]
            return status[0], (closing[0] - killed) if closing else None, b''.join(body for _, body in frames).decode()
        return asyncio.run(run())


class RevocationMatrixTests(MatrixFixture):
    def test_three_causes_by_three_routes_get_401_on_the_next_request(self):
        for cause in CAUSES:
            user_id, key = self.owner()
            with self.subTest(cause=cause, moment='alive'):
                self.assertEqual([self.request(route, key['token']) for route in ROUTES], [200, 200, 200])
            self.kill(cause, user_id, key)
            for route in ROUTES:
                with self.subTest(cause=cause, route=route):
                    self.assertEqual(self.request(route, key['token']), 401)

    def test_an_open_stream_closes_within_one_poll_and_a_margin_for_each_cause(self):
        for cause in CAUSES:
            user_id, key = self.owner()
            with self.subTest(cause=cause):
                status, seconds, text = self.stream(key['token'], lambda: self.kill(cause, user_id, key))
                self.assertEqual(status, 200)
                self.assertIsNotNone(seconds, 'the stream ended without the closing frame: ' + text[-300:])
                self.assertLessEqual(seconds, POLL + MARGIN, 'the stream outlived the credential for %.2f s' % seconds)
                self.assertIn('"code":"unauthorized"', text)
                self.assertEqual(self.request('/v1', key['token']), 401, 'and the next request is refused')

    def test_a_closed_session_and_a_session_of_a_disabled_user_get_401(self):
        api = self.chain.api  # the server application; the cookie travels with each request, so each session is its own
        for cause in ('closed', 'disabled'):
            user_id, _ = self.owner()
            name = self.count('SELECT username FROM memory.actors WHERE id=%s', user_id)
            cookies = {'memory_session': self.auth.login(name, pw.PASSWORD, '198.51.100.%d' % (uuid.uuid4().int % 200 + 1))['session_token']}

            def csrf():  # `me` gives a session a new token each time
                return {'Origin': ORIGIN, 'X-CSRF-Token': api.get('/v1/auth/me', cookies=cookies).json()['csrf_token']}

            def routes(headers):
                return [api.get('/v1/projects', cookies=cookies).status_code, api.post('/mcp/', cookies=cookies, headers={**headers, 'Accept': ACCEPT}, json=CALL).status_code,
                        api.get('/v1/auth/me', cookies=cookies).status_code]
            with self.subTest(cause=cause, moment='alive'):
                self.assertEqual(routes(csrf()), [200, 200, 200])
            headers = csrf()
            if cause == 'closed':
                self.assertEqual(api.post('/v1/auth/logout', cookies=cookies, headers=headers).status_code, 200)
            else:
                self.pooled.set_user_disabled(self.root_actor, user_id, True)
            with self.subTest(cause=cause):
                self.assertEqual(routes(headers), [401, 401, 401])

if __name__ == '__main__':
    unittest.main()
