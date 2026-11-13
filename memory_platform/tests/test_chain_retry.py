"""T-47/T-48 (CA-11, debt of Phase 3): the retry rule of `rebuild_corpus`, the order of its errors and the isolation between actors, through the real chain.

Nothing is scripted: kairos-mcp reads the version from the real server, sends the real rebuild, and a concurrent change lands between the two exactly where a
second client would make it (a hook that runs after the server has answered the read). The requests kairos-mcp sent are recorded, so `reread`,
`only_if_value_changed` and `max` are read from what crossed the wire; a second real actor, a read-only key and a revoked key are asked as well, and each answer is
compared with the one the internal MCP gives for the same call over the same state.
"""
import unittest
import uuid

from memory_platform.agent_store import AgentStore
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests.chain_harness import ChainClient, RecordingTransport
from memory_platform.tests.test_store import create_core, event

ACCEPT = 'application/json, text/event-stream'
MORE_THAN_HALF = 'Rebuild would remove more than half the corpus; review and explicitly force'


class ChainRebuildTests(unittest.TestCase):
    def setUp(self):
        self.store, self.admin, self.pid = create_core()
        self.sources = [event(self.pid, generate=False, payload={'title': 'Fencing %d' % number, 'content': 'Use fencing before projection', 'source': {'uri': 'fixture://chain'}})
                        for number in range(3)]
        for source in self.sources:
            self.store.ingest_event(self.admin, source)
        AgentStore(self.store).build_corpus(self.admin, self.pid, 'c1', query='fencing')
        self.owner = self.key(self.admin, ['read', 'write'])
        self.app = create_app(Settings('unused'), store=self.store, auth=Auth(self.store))
        self.transport = RecordingTransport(self.app)
        self.client = ChainClient(self.app, transport=self.transport)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def key(self, actor, scopes, owner=None):
        made = self.store.create_key(self.admin, {'name': 'chain-' + uuid.uuid4().hex[:6], 'project_ids': [self.pid], 'scopes': scopes})
        if owner:
            with self.store.transaction() as c:
                c.execute('UPDATE memory.api_keys SET actor_id=%s WHERE id=%s', (owner['id'], made['id']))
        return made['token']

    def tool(self, client, name, arguments, token=None):
        response = client.post('/mcp/', headers={'Authorization': 'Bearer ' + (token or self.owner), 'Accept': ACCEPT},
                               json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
        return response

    def both(self, arguments, token=None):
        """The same `rebuild_corpus` call through kairos-mcp and on the internal MCP; the requests of the first are what the transport recorded."""
        self.transport.requests.clear()
        chain = self.tool(self.client.chain, 'rebuild_corpus', {'project': self.pid, **arguments}, token)
        sent = list(self.transport.requests)
        return chain, self.tool(self.client.server_mcp, 'rebuild_corpus', {'project': self.pid, **arguments}, token), sent

    def version(self, name='c1'):
        with self.store.transaction() as c:
            return c.execute('SELECT version FROM memory.agent_corpora WHERE project_id=%s AND name=%s', (self.pid, name)).fetchone()['version']

    def concurrent_rebuild(self, times=None):
        """A hook: another rebuild of the corpus lands (its version grows) right after the server answered the read of the version."""
        done = []

        def after(request, response):
            if request.method == 'GET' and request.url.path.endswith('/corpus') and response.status_code == 200 and (times is None or len(done) < times):
                done.append(1)
                with self.store.transaction() as c:
                    c.execute('UPDATE memory.agent_corpora SET version=version+1 WHERE project_id=%s AND name=%s', (self.pid, 'c1'))
        self.transport.after = after
        return done

    def error(self, response):
        result = response.json()['result']
        return result['isError'], result['content'][0]['text']

    def test_a_rebuild_that_lands_between_the_read_and_the_post_is_read_again_and_sent_again(self):
        done = self.concurrent_rebuild(times=1)
        self.transport.requests.clear()
        response = self.tool(self.client.chain, 'rebuild_corpus', {'project': self.pid, 'name': 'c1'})
        self.assertEqual(self.error(response)[0], False, response.text)
        self.assertEqual(len(done), 1)
        self.assertEqual([(method, status) for method, _, status in self.transport.requests], [('GET', 200), ('POST', 409), ('GET', 200), ('POST', 200)])
        self.assertEqual(self.version(), 2)  # the version the concurrent rebuild made; the retry rebuilt over it without changing the content

    def test_a_conflict_with_the_version_unchanged_is_the_real_one_and_is_not_sent_again(self):
        for source in self.sources[:2]:  # two of the three sources withdrawn: the rebuild would remove more than half
            self.store.ingest_event(self.admin, {**source, 'event_id': str(uuid.uuid4()), 'version': 2, 'event_type': 'delete'})
        chain, internal, sent = self.both({'name': 'c1'})
        self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: ' + MORE_THAN_HALF))
        self.assertEqual(self.error(chain), self.error(internal))
        self.assertEqual([(method, status) for method, _, status in sent], [('GET', 200), ('POST', 409), ('GET', 200)])  # read, send, read again: unchanged
        self.assertEqual(self.version(), 1)

    def test_the_retries_stop_after_three_more_attempts(self):
        self.concurrent_rebuild()  # the version changes after every read: the race never settles
        self.transport.requests.clear()
        response = self.tool(self.client.chain, 'rebuild_corpus', {'project': self.pid, 'name': 'c1'})
        self.assertEqual(self.error(response), (True, 'Error executing tool rebuild_corpus: Corpus version changed'))
        methods = [method for method, _, _ in self.transport.requests]
        self.assertEqual((methods.count('GET'), methods.count('POST')), (4, 4))  # `max: 3` more sends after the first, then the conflict is the answer

    def test_an_explicit_version_is_sent_once_and_never_read_or_retried(self):
        stale = self.version() + 5
        chain, internal, sent = self.both({'name': 'c1', 'expected_version': stale})
        self.assertEqual(self.error(chain), self.error(internal))
        self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: Corpus version changed'))
        self.assertEqual([(method, status) for method, _, status in sent], [('POST', 409)])

    def test_a_zero_version_reads_first_and_is_the_conflict_only_for_a_corpus_the_caller_has(self):
        chain, internal, sent = self.both({'name': 'c1', 'expected_version': 0})
        self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: Corpus version changed'))
        self.assertEqual(self.error(chain), self.error(internal))
        self.assertEqual([(method, status) for method, _, status in sent], [('GET', 200)])  # no rebuild was sent
        self.assertEqual(self.version(), 1)
        chain, internal, sent = self.both({'name': 'no-such-corpus', 'expected_version': 0})
        self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: Resource not found'))
        self.assertEqual(self.error(chain), self.error(internal))
        self.assertEqual([status for _, _, status in sent], [404])

    def test_another_actor_with_read_and_write_hides_and_cannot_touch_the_corpora_of_the_first(self):
        user = self.store.create_user(self.admin, {'username': 'peer-' + uuid.uuid4().hex[:10], 'password': 'synthetic-password-123',
                                                   'project_ids': [self.pid], 'scopes': ['read', 'write']})
        peer = self.key(self.admin, ['read', 'write'], owner={'id': user['id']})
        for arguments in ({'name': 'c1'}, {'name': 'c1', 'expected_version': 0}, {'name': 'c1', 'expected_version': 1}, {'name': 'c1', 'force': True}):
            with self.subTest(arguments=arguments):
                chain, internal, sent = self.both(arguments, peer)
                self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: Resource not found'))
                self.assertEqual(self.error(chain), self.error(internal))
                self.assertTrue(all(status == 404 for _, _, status in sent), sent)  # the peer's read or send is refused as not found: nothing of the first actor's is touched
        self.assertEqual(self.version(), 1)
        listed = self.tool(self.client.chain, 'list_corpora', {'project': self.pid}, peer).json()['result']
        self.assertIn('"items":[]', listed['content'][0]['text'])  # the peer does not even see that the corpus exists
        self.assertEqual(self.error(self.tool(self.client.chain, 'rebuild_corpus', {'project': self.pid, 'name': 'c1'}))[0], False)  # the owner can

    def test_a_key_without_write_gets_the_403_of_the_internal_tool_for_any_name(self):
        reader = self.key(self.admin, ['read'])
        for arguments in ({'name': 'c1'}, {'name': 'no-such-corpus'}, {'name': 'c1', 'expected_version': 0}, {'name': 'no-such-corpus', 'expected_version': 0}):
            with self.subTest(arguments=arguments):
                chain, internal, sent = self.both(arguments, reader)
                self.assertEqual(self.error(chain), (True, 'Error executing tool rebuild_corpus: Operation not permitted'))
                self.assertEqual(self.error(chain), self.error(internal))
                self.assertNotIn('POST', [method for method, _, _ in sent])

    def test_a_revoked_key_is_a_401_of_the_endpoint_like_on_the_internal_mcp(self):
        token = self.key(self.admin, ['read', 'write'])
        key = next(k for k in self.store.list_keys(self.admin) if k['prefix'] == token[:10])
        self.store.revoke_key(self.admin, str(key['id']))
        chain = self.tool(self.client.chain, 'rebuild_corpus', {'project': self.pid, 'name': 'c1'}, token)
        internal = self.tool(self.client.server_mcp, 'rebuild_corpus', {'project': self.pid, 'name': 'c1'}, token)
        self.assertEqual((chain.status_code, internal.status_code), (401, 401))
        self.assertEqual(chain.json()['error']['code'], internal.json()['error']['code'])
        self.assertEqual(chain.json()['error']['message'], internal.json()['error']['message'])


if __name__ == '__main__':
    unittest.main()
