"""The fault proxy (I3 / CA-34): cut, restore and mute on command, deterministic, closed clean."""
import os
import socket
import threading
import unittest

from memory_platform.tests.fault_proxy import FaultProxy


class FaultProxyTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        self.psycopg = psycopg
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)

    def connect(self, **options):
        return self.psycopg.connect(self.proxy.dsn(), autocommit=True, **options)

    def test_forwards_queries_to_the_database(self):
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT 41 + 1').fetchone()[0], 42)
        self.assertEqual(self.proxy.mode, 'forward')

    def test_listens_on_loopback_only(self):
        self.assertEqual(self.proxy.host, '127.0.0.1')
        self.assertEqual(self.proxy._listener.getsockname()[0], '127.0.0.1')
        self.assertNotEqual(self.proxy.port, 0)

    def test_cut_breaks_the_open_connection_and_restore_brings_it_back(self):
        c = self.connect()
        self.assertEqual(c.execute('SELECT 1').fetchone()[0], 1)
        self.proxy.cut()
        self.assertEqual(self.proxy.mode, 'cut')
        with self.assertRaises(self.psycopg.OperationalError):
            c.execute('SELECT 1')
        c.close()
        with self.assertRaises(self.psycopg.OperationalError):
            self.connect()
        self.proxy.restore()
        with self.connect() as again:
            self.assertEqual(again.execute('SELECT 2').fetchone()[0], 2)

    def test_cut_takes_effect_before_it_returns_even_for_a_connection_being_opened(self):
        # Many threads connect while the proxy is cut and restored: every connection either works or fails with OperationalError,
        # and after the final cut() none survives (no registered socket is left behind).
        outcomes, lock = [], threading.Lock()

        def attempt():
            try:
                with self.connect() as c:
                    c.execute('SELECT 1')
                result = 'ok'
            except self.psycopg.OperationalError:
                result = 'down'
            with lock:
                outcomes.append(result)

        self.proxy.cut()
        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(outcomes, ['down'] * 8)
        self.proxy.restore()
        with self.connect() as c:
            c.execute('SELECT 1')
        self.proxy.cut()
        with self.proxy._lock:
            self.assertEqual(len(self.proxy._held), 0)

    def test_mute_accepts_and_does_not_answer(self):
        self.proxy.mute()
        self.assertEqual(self.proxy.mode, 'mute')
        client = socket.create_connection((self.proxy.host, self.proxy.port), timeout=5)
        self.addCleanup(client.close)
        self.assertTrue(self.proxy.wait_accepted(1))  # accepted, not refused
        client.sendall(b'\x00\x00\x00\x08\x04\xd2\x16\x2f')  # a PostgreSQL SSLRequest: a live server answers with one byte
        client.settimeout(0.3)
        with self.assertRaises(socket.timeout):
            client.recv(1)
        with self.assertRaises(self.psycopg.OperationalError):
            self.psycopg.connect(self.proxy.dsn(), connect_timeout=1)

    def test_restore_closes_what_was_held_mute_and_forwards_again(self):
        self.proxy.mute()
        client = socket.create_connection((self.proxy.host, self.proxy.port), timeout=5)
        self.addCleanup(client.close)
        self.assertTrue(self.proxy.wait_accepted(1))
        self.proxy.restore()
        client.settimeout(5)
        self.assertEqual(client.recv(1), b'')  # closed by restore(), not left hanging
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT 3').fetchone()[0], 3)

    def test_stop_closes_every_socket_and_thread(self):
        proxy = FaultProxy().start()
        c = self.psycopg.connect(proxy.dsn(), autocommit=True)
        c.execute('SELECT 1')
        proxy.stop()
        proxy.stop()  # idempotent
        with self.assertRaises(self.psycopg.OperationalError):
            c.execute('SELECT 1')
        c.close()
        with self.assertRaises(OSError):
            socket.create_connection((proxy.host, proxy.port), timeout=2)
        self.assertEqual([t for t in proxy._threads if t.is_alive()], [])
        self.assertFalse(proxy._acceptor.is_alive())


if __name__ == '__main__':
    unittest.main()
