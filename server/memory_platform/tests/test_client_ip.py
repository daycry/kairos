"""CA-14, CA-15 (T-27): the IP of the client behind the web proxy, `MEMORY_TRUSTED_PROXIES` and `X-Forwarded-For`.

The API takes the rightmost address of `X-Forwarded-For` that is not a trusted proxy, and only when the peer that connected is one; with no trusted proxy, the
header is ignored and the peer is the client, as before. The proxy is simulated at the ASGI boundary (the peer of the connection is set; the HTTP proxies are in
`test_login_proxy.py`).
"""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import config, limits, passwords
from memory_platform.app import client_address, create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.tests import test_passwords as pw

ORIGIN = 'http://127.0.0.1:5173'
WRONG = 'not-the-password-999'
TRUSTED = config.trusted_proxies('10.0.0.0/8, 172.16.0.0/12')


def through(app, peer):
    """The app as a client at `peer` reaches it: the address of the connection is the peer, whatever the headers say."""
    async def asgi(scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            scope = {**scope, 'client': (peer, 40000)}
        await app(scope, receive, send)
    return asgi


class AddressTests(unittest.TestCase):
    def test_without_trusted_proxies_the_header_is_ignored(self):
        self.assertEqual(client_address('10.0.0.2', ['203.0.113.5'], ()), '10.0.0.2')

    def test_a_peer_that_is_not_trusted_is_the_client_whatever_it_sends(self):
        self.assertEqual(client_address('198.51.100.7', ['203.0.113.5'], TRUSTED), '198.51.100.7')
        self.assertEqual(client_address('testclient', ['203.0.113.5'], TRUSTED), 'testclient')

    def test_a_trusted_peer_gives_the_rightmost_address_that_is_not_trusted(self):
        self.assertEqual(client_address('10.0.0.2', ['203.0.113.5'], TRUSTED), '203.0.113.5')
        self.assertEqual(client_address('10.0.0.2', ['1.1.1.1, 203.0.113.5'], TRUSTED), '203.0.113.5', 'what the client wrote on the left is not believed')

    def test_two_trusted_proxies_chained(self):
        self.assertEqual(client_address('10.0.0.2', ['203.0.113.5, 172.18.0.3'], TRUSTED), '203.0.113.5')
        self.assertEqual(client_address('10.0.0.2', ['9.9.9.9, 203.0.113.5', '172.18.0.3'], TRUSTED), '203.0.113.5', 'several header lines are one list, in order')

    def test_a_malformed_header_falls_back_to_the_peer(self):
        for header in (['not-an-ip'], ['203.0.113.5:443'], ['203.0.113.5, , 172.18.0.3'], [''], ['[2001:db8::1]']):
            with self.subTest(header=header):
                self.assertEqual(client_address('10.0.0.2', header, TRUSTED), '10.0.0.2')
        self.assertEqual(client_address('10.0.0.2', ['garbage, 203.0.113.5'], TRUSTED), '203.0.113.5', 'only what is walked must parse: the left part is the client\'s')

    def test_no_header_is_the_peer_and_every_hop_trusted_is_the_leftmost(self):
        self.assertEqual(client_address('10.0.0.2', [], TRUSTED), '10.0.0.2')
        self.assertEqual(client_address('10.0.0.2', ['172.18.0.9, 10.0.0.3'], TRUSTED), '172.18.0.9')

    def test_ipv6_and_mapped_ipv4(self):
        trusted = config.trusted_proxies('10.0.0.0/8,fd00::/8')
        self.assertEqual(client_address('::ffff:10.0.0.2', ['2001:db8::5'], trusted), '2001:db8::5')
        self.assertEqual(client_address('fd00::2', ['::ffff:203.0.113.5'], trusted), '203.0.113.5')


class SettingsTests(unittest.TestCase):
    def test_the_list_and_its_refusals(self):
        self.assertEqual(config.trusted_proxies(''), ())
        self.assertEqual([str(n) for n in config.trusted_proxies(' 10.0.0.0/8 , 172.18.0.5,fd00::/8 ')], ['10.0.0.0/8', '172.18.0.5/32', 'fd00::/8'])
        for raw in ('nonsense', '10.0.0.1/8', '0.0.0.0/0', '::/0', '10.0.0.0/8,,', '10.0.0.0/33'):
            with self.subTest(raw=raw), self.assertRaises(ValueError) as raised:
                config.trusted_proxies(raw)
            self.assertIn('MEMORY_TRUSTED_PROXIES', str(raised.exception))

    def test_an_invalid_list_stops_the_start(self):
        with patch.dict('os.environ', {'MEMORY_DSN': 'postgresql://unused', 'MEMORY_TRUSTED_PROXIES': '10.0.0.0/8,example.org'}), self.assertRaises(ValueError) as raised:
            Settings.from_env()
        self.assertIn('MEMORY_TRUSTED_PROXIES', str(raised.exception))
        with self.assertRaises(ValueError):
            Settings('unused', trusted_proxies=('bad',))
        with patch.dict('os.environ', {'MEMORY_DSN': 'postgresql://unused', 'MEMORY_TRUSTED_PROXIES': '172.16.0.0/12'}):
            self.assertEqual(Settings.from_env().trusted_proxies, ('172.16.0.0/12',))
        with patch.dict('os.environ', {'MEMORY_DSN': 'postgresql://unused'}):
            self.assertEqual(Settings.from_env().trusted_proxies, (), 'unset: no proxy is trusted, as before')


class GateSpy:
    def __init__(self):
        self.ips = []

    @contextmanager
    def hold(self, ip):
        self.ips.append(ip)
        yield


class HttpTests(pw.Fixture):
    def setUp(self):
        super().setUp()
        self.addCleanup(limits.configure_login, limits.DEFAULT_MAX_FAILURES, limits.DEFAULT_WINDOW)
        self.auth = Auth(self.store, [ORIGIN])  # the CSRF of a session is checked against the origins of Auth
        with patch.object(passwords, 'GATE', passwords.GATE):
            self.app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False, trusted_proxies=('10.0.0.0/8',)), store=self.store, auth=self.auth)

    def client(self, peer):
        client = TestClient(through(self.app, peer))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def login(self, client, forwarded=None, password=pw.PASSWORD, username='ana'):
        headers = {'Origin': ORIGIN, **({'X-Forwarded-For': forwarded} if forwarded else {})}
        return client.post('/v1/auth/login', json={'username': username, 'password': password}, headers=headers)

    def test_ca13_through_the_proxy_a_fails_ten_times_b_enters_and_the_eleventh_of_a_is_429(self):
        proxy = self.client('10.0.0.2')
        for _ in range(10):
            self.assertEqual(self.login(proxy, '203.0.113.1', WRONG).status_code, 401)
        entered = self.login(proxy, '203.0.113.2')
        self.assertEqual(entered.status_code, 200, entered.text)
        blocked = self.login(proxy, '203.0.113.1')
        self.assertEqual((blocked.status_code, blocked.json()['error']['code']), (429, 'rate_limited'))
        self.assertGreaterEqual(int(blocked.headers['Retry-After']), 1)

    def test_the_session_and_the_failures_keep_the_ip_of_the_client_not_the_one_of_the_proxy(self):
        proxy = self.client('10.0.0.2')
        self.assertEqual(self.login(proxy, '203.0.113.3', WRONG).status_code, 401)
        self.assertEqual(self.login(proxy, '203.0.113.4').status_code, 200)
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute('SELECT client_ip FROM memory.login_attempts').fetchall(), [('203.0.113.3',)])
            self.assertEqual(c.execute('SELECT client_ip FROM memory.web_sessions').fetchall(), [('203.0.113.4',)])
        self.assertEqual([s['client_ip'] for s in proxy.get('/v1/auth/sessions').json()['items']], ['203.0.113.4'])

    def test_a_header_from_a_peer_that_is_not_trusted_neither_dodges_the_block_nor_blocks_another_ip(self):
        attacker, proxy = self.client('198.51.100.7'), self.client('10.0.0.2')
        for index in range(10):  # a new address each time: it is still the peer that is counted
            self.assertEqual(self.login(attacker, f'203.0.113.{100 + index}', WRONG).status_code, 401)
        self.assertEqual(self.login(attacker, '203.0.113.200').status_code, 429, 'the header does not dodge the block')
        for _ in range(10):  # in the name of a victim: the failures go to the attacker's own address, already blocked
            self.login(attacker, '203.0.113.9', WRONG)
        self.assertEqual(self.login(proxy, '203.0.113.9').status_code, 200, 'nor does it block another IP')
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute('SELECT DISTINCT client_ip FROM memory.login_attempts').fetchall(), [('198.51.100.7',)])

    def test_the_change_of_password_and_the_creation_of_a_user_take_the_slot_of_the_real_ip(self):
        proxy = self.client('10.0.0.2')
        login = self.login(proxy, '203.0.113.20')
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': login.json()['csrf_token'], 'X-Forwarded-For': '203.0.113.20'}
        root = self.client('10.0.0.2')
        root_login = self.login(root, '203.0.113.21', 'root-password-123', 'root-user')
        root_headers = {'Origin': ORIGIN, 'X-CSRF-Token': root_login.json()['csrf_token'], 'X-Forwarded-For': '203.0.113.21'}
        spy = GateSpy()
        with patch.object(passwords, 'GATE', spy):
            changed = proxy.post('/v1/auth/password', json={'current_password': pw.PASSWORD, 'new_password': 'brand-new-password-456'}, headers=headers)
            self.assertEqual(changed.status_code, 200, changed.text)
            created = root.post('/v1/users', json={'username': 'bea', 'password': 'another-password-123', 'project_ids': ['p1'], 'scopes': ['read']}, headers=root_headers)
            self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(spy.ips, ['203.0.113.20', '203.0.113.21'])

    def test_metrics_in_internal_mode_is_still_404_through_the_proxy(self):
        proxy = self.client('10.0.0.2')
        self.assertEqual(proxy.get('/metrics', headers={'X-Forwarded-For': '203.0.113.30'}).status_code, 404)
        self.assertEqual(self.client('10.0.0.2').get('/metrics').status_code, 200, 'without the headers of a proxy, the internal network still reads it')

    def test_without_trusted_proxies_the_peer_is_the_client_as_before(self):
        with patch.object(passwords, 'GATE', passwords.GATE):
            app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        client = TestClient(through(app, '10.0.0.2'))
        with client:
            client.post('/v1/auth/login', json={'username': 'ana', 'password': WRONG}, headers={'Origin': ORIGIN, 'X-Forwarded-For': '203.0.113.40'})
        with self.psycopg.connect(self.dsn) as c:
            self.assertEqual(c.execute('SELECT client_ip FROM memory.login_attempts').fetchall(), [('10.0.0.2',)])


if __name__ == '__main__':
    unittest.main()
