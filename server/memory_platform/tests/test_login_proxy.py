"""CA-13, CA-14 (T-28): the login through real HTTP proxies, end to end over TCP.

The API runs in a real uvicorn server with the options of the service (`app.SERVER_OPTIONS`: uvicorn's own proxy headers off, so `MEMORY_TRUSTED_PROXIES` is the only
authority on the address of the client). In front of it, simulated proxies that do what nginx does with `$proxy_add_x_forwarded_for`: append the address of the peer
that connected to them to the `X-Forwarded-For` they received. Every party has its own loopback address (127.0.0.0/8 is all loopback on Linux), so the API sees each one
as a different peer: clients at 127.0.0.11 and .12, the proxy next to the API at 127.0.0.2 and the one in front of it at 127.0.0.3.
"""
import http.client
import http.server
import json
import socket
import threading
import unittest

import uvicorn

from memory_platform import limits, passwords
from memory_platform.app import SERVER_OPTIONS, create_app
from memory_platform.config import Settings
from memory_platform.tests import test_passwords as pw

ORIGIN = 'http://127.0.0.1:5173'
WRONG = 'not-the-password-999'
A, B, NEAR, FAR = '127.0.0.11', '127.0.0.12', '127.0.0.2', '127.0.0.3'


def free_port(host='127.0.0.1'):
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


class Proxy:
    """A reverse proxy in a thread: forwards every request to `upstream` from the source address `source`, appending the peer to `X-Forwarded-For` (`forward=False`:
    a proxy that does not send the header, which is what `web/nginx.conf` did before T-27)."""
    def __init__(self, upstream, source, forward=True):
        self.port, upstream_host, upstream_port = free_port(), *upstream
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def relay(self):
                body = self.rfile.read(int(self.headers.get('content-length') or 0))
                headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection', 'x-forwarded-for', 'content-length')}
                if forward:
                    received = ', '.join(self.headers.get_all('x-forwarded-for') or [])
                    headers['X-Forwarded-For'] = (received + ', ' if received else '') + self.client_address[0]
                connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=30, source_address=(source, 0))
                connection.request(self.command, self.path, body=body or None, headers=headers)
                answer = connection.getresponse()
                data = answer.read()
                self.send_response(answer.status)
                for key, value in answer.getheaders():
                    if key.lower() not in ('content-length', 'connection', 'transfer-encoding', 'date', 'server'):
                        self.send_header(key, value)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                connection.close()
            do_GET = do_POST = relay

            def log_message(self, *args):
                pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        proxy.address = ('127.0.0.1', self.port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def request(target, source, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection(*target, timeout=30, source_address=(source, 0))
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers={'Content-Type': 'application/json', **(headers or {})})
    answer = connection.getresponse()
    data = answer.read()
    connection.close()
    return answer.status, answer.headers, json.loads(data) if data else None  # headers: case-insensitive


class ProxyFixture(pw.Fixture):
    TRUSTED = (NEAR + '/32', FAR + '/32')

    def setUp(self):
        super().setUp()
        self.addCleanup(limits.configure_login, limits.DEFAULT_MAX_FAILURES, limits.DEFAULT_WINDOW)
        gate = passwords.GATE
        self.addCleanup(setattr, passwords, 'GATE', gate)
        app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False, trusted_proxies=self.TRUSTED), store=self.store, auth=self.auth)
        port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, **{**SERVER_OPTIONS, 'host': '127.0.0.1', 'port': port}))
        thread = threading.Thread(target=self.server.run, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(setattr, self.server, 'should_exit', True)
        while not self.server.started and thread.is_alive():
            thread.join(0.05)
        self.assertTrue(self.server.started, 'uvicorn did not start')
        self.api = ('127.0.0.1', port)

    def proxy(self, upstream, source, forward=True):
        proxy = Proxy(upstream, source, forward)
        self.addCleanup(proxy.close)
        return proxy.address

    def login(self, target, source, password=pw.PASSWORD, forwarded=None):
        headers = {'Origin': ORIGIN, **({'X-Forwarded-For': forwarded} if forwarded else {})}
        return request(target, source, 'POST', '/v1/auth/login', {'username': 'ana', 'password': password}, headers)

    def stored(self, table):
        with self.psycopg.connect(self.dsn) as c:
            return sorted({row[0] for row in c.execute(f'SELECT client_ip FROM memory.{table}').fetchall()})


class LoginThroughProxyTests(ProxyFixture):
    def test_ca13_through_the_proxy_a_fails_ten_times_b_enters_and_the_eleventh_of_a_gets_429_with_retry_after(self):
        proxy = self.proxy(self.api, NEAR)
        for _ in range(10):
            self.assertEqual(self.login(proxy, A, WRONG)[0], 401)
        self.assertEqual(self.login(proxy, B)[0], 200, 'B, from another IP, enters')
        status, headers, body = self.login(proxy, A)
        self.assertEqual((status, body['error']['code']), (429, 'rate_limited'))
        self.assertGreaterEqual(int(headers['Retry-After']), 1)
        self.assertEqual((self.stored('login_attempts'), self.stored('web_sessions')), ([A], [B]), 'the API keeps the IP of each client, never the one of the proxy')

    def test_two_chained_trusted_proxies_give_the_rightmost_untrusted_address(self):
        near = self.proxy(self.api, NEAR)
        far = self.proxy(near, FAR)
        self.assertEqual(self.login(far, B, forwarded='203.0.113.66')[0], 200, 'what B wrote on the left is not believed')
        self.assertEqual(self.stored('web_sessions'), [B])
        for _ in range(10):
            self.login(far, A, WRONG, forwarded='203.0.113.77')
        self.assertEqual(self.login(far, A, forwarded='203.0.113.78')[0], 429, 'a new address on the left each time does not dodge the block')
        self.assertEqual(self.login(far, B)[0], 200)
        self.assertEqual(self.stored('login_attempts'), [A])

    def test_a_peer_that_is_not_a_trusted_proxy_is_the_client_whatever_header_it_sends(self):
        for index in range(10):
            self.assertEqual(self.login(self.api, A, WRONG, forwarded=f'203.0.113.{index}')[0], 401)
        self.assertEqual(self.login(self.api, A, forwarded='203.0.113.200')[0], 429)
        self.assertEqual(self.login(self.proxy(self.api, NEAR), B)[0], 200)
        self.assertEqual(self.stored('login_attempts'), [A])

    def test_a_proxy_that_does_not_send_the_header_puts_every_client_behind_one_address(self):
        # What happened before T-27 (and what a `web/nginx.conf` without the header would bring back): the failures of A block B.
        proxy = self.proxy(self.api, NEAR, forward=False)
        for _ in range(10):
            self.login(proxy, A, WRONG)
        self.assertEqual(self.login(proxy, B)[0], 429)
        self.assertEqual(self.stored('login_attempts'), [NEAR])


class UntrustedProxyTests(ProxyFixture):
    TRUSTED = ()

    def test_without_trusted_proxies_the_header_of_the_proxy_is_ignored_as_before(self):
        proxy = self.proxy(self.api, NEAR)
        self.assertEqual(self.login(proxy, B)[0], 200)
        self.assertEqual(self.stored('web_sessions'), [NEAR])

    def test_uvicorn_does_not_take_the_header_on_its_own_from_the_loopback(self):
        # uvicorn trusts `X-Forwarded-For` from FORWARDED_ALLOW_IPS (127.0.0.1 by default) unless `proxy_headers` is off (SERVER_OPTIONS): MEMORY_TRUSTED_PROXIES is the only authority
        self.assertEqual(self.login(self.api, '127.0.0.1', forwarded='203.0.113.50')[0], 200)
        self.assertEqual(self.stored('web_sessions'), ['127.0.0.1'])


if __name__ == '__main__':
    unittest.main()
