"""CA-12, CA-13, CA-15 (T-26): the login counts only failures and blocks only by the IP of the client, with a 429 `rate_limited` and `Retry-After` from the one constructor of DC-2.

The oracle of A-02: ten failures from the IP `a` for the user U; the correct login of U from the IP `b` answers 200 and the eleventh attempt of `a` gets 429 with `Retry-After`.
Derivations are counted (`passwords._derive`), never timed; the concurrency tests wait on conditions, not on sleeps.
"""
import re
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from memory_platform import config, limits, observability, passwords
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.errors import MemoryError, Unauthorized
from memory_platform.tests import test_passwords as pw

ORIGIN = 'http://127.0.0.1:5173'
WRONG = 'not-the-password-999'
MESSAGE = re.compile(r'^Rate limit exceeded \[code=rate_limited retry_after=(\d+)\]$')


class OpenGate:
    """A gate that lets every attempt through at once: what several processes of the API (each with its own gate) look like to the database."""
    def __init__(self):
        self.held = []

    @contextmanager
    def hold(self, ip):
        self.held.append(ip)
        yield


class Fixture(pw.Fixture):
    def setUp(self):
        super().setUp()
        self.addCleanup(limits.configure_login, limits.DEFAULT_MAX_FAILURES, limits.DEFAULT_WINDOW)

    def rows(self, query='SELECT count(*) FROM memory.login_attempts', *args):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute(query, args).fetchone()[0]

    def fail_login(self, ip, username='ana', times=1):
        for _ in range(times):
            with self.assertRaises(Unauthorized):
                self.auth.login(username, WRONG, ip)

    def blocked(self, ip, username='ana', password=pw.PASSWORD):
        with self.assertRaises(MemoryError) as raised:
            self.auth.login(username, password, ip)
        return raised.exception


class FailuresOnlyTests(Fixture):
    def test_ca12_thirty_correct_logins_in_a_row_from_one_ip_get_no_429_and_leave_no_row(self):
        for _ in range(30):
            self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.10')['actor']['username'], 'ana')
        self.assertEqual(self.rows(), 0, 'a correct login is not a failure: it leaves nothing in login_attempts')

    def test_ca13_ten_failures_from_a_do_not_stop_u_from_b_and_the_eleventh_of_a_is_429_with_retry_after(self):
        self.fail_login('192.0.2.11', times=10)
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.12')['actor']['username'], 'ana', 'the name is not a bucket: U enters from b')
        error = self.blocked('192.0.2.11')
        self.assertEqual((error.code, error.status_code), ('rate_limited', 429))
        self.assertTrue(1 <= error.retry_after <= limits.DEFAULT_WINDOW, error.retry_after)
        self.assertEqual(MESSAGE.match(error.message).group(1), str(error.retry_after), 'the plazo travels in the fixed message too (DC-2)')
        self.assertEqual(self.rows("SELECT count(*) FROM memory.login_attempts WHERE client_ip='192.0.2.11'"), 10, 'the eleventh is not written')

    def test_a_correct_login_neither_counts_nor_clears_the_failures_of_its_ip(self):
        self.fail_login('192.0.2.13', times=9)
        self.auth.login('ana', pw.PASSWORD, '192.0.2.13')
        self.assertEqual(self.rows("SELECT count(*) FROM memory.login_attempts WHERE client_ip='192.0.2.13'"), 9, 'an attacker with an account of its own does not clear its counter')
        self.fail_login('192.0.2.13')
        self.assertEqual(self.blocked('192.0.2.13').code, 'rate_limited', 'the right password of a blocked IP is refused too')

    def test_p05_failures_of_one_name_from_many_ips_never_block_that_name(self):
        for index in range(15):
            self.fail_login(f'198.51.100.{index}')
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '198.51.100.200')['actor']['username'], 'ana')

    def test_the_window_ends_the_block_and_retry_after_says_when(self):
        with self.psycopg.connect(self.dsn) as c:  # nine failures of an hour ago (outside the window) and ten of 14 min 50 s ago (inside)
            c.execute("INSERT INTO memory.login_attempts(username,client_ip,happened_at) SELECT 'ana','192.0.2.14',clock_timestamp()-interval '1 hour' FROM generate_series(1,9)")
            c.execute("INSERT INTO memory.login_attempts(username,client_ip,happened_at) SELECT 'ana','192.0.2.14',clock_timestamp()-interval '890 seconds' FROM generate_series(1,10)")
        error = self.blocked('192.0.2.14')
        self.assertTrue(1 <= error.retry_after <= 11, error.retry_after)
        with self.psycopg.connect(self.dsn) as c:
            c.execute("UPDATE memory.login_attempts SET happened_at=happened_at-interval '11 seconds' WHERE client_ip='192.0.2.14'")
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '192.0.2.14')['actor']['username'], 'ana', 'out of the window, the IP enters again')


class OrderTests(Fixture):
    def test_a_blocked_ip_derives_nothing_and_takes_no_slot_of_the_gate(self):
        self.fail_login('192.0.2.20', times=10)
        gate = OpenGate()
        with patch.object(passwords, 'GATE', gate), pw.Derivations() as spy:
            error = self.blocked('192.0.2.20')
        self.assertEqual((error.code, spy.calls, gate.held), ('rate_limited', [], []))

    def test_twenty_concurrent_failures_of_one_ip_let_at_most_ten_verifications_through(self):
        # An open gate stands for several processes. Every derivation waits until each of the twenty attempts has either reached its derivation or been refused, so
        # no failure is known (or written) before all of them have decided: the count must hold with the attempts in flight.
        total, state, cond = 20, {'derived': 0, 'refused': 0}, threading.Condition()
        real = passwords._derive

        def derive(password, salt, params):
            with cond:
                state['derived'] += 1
                cond.notify_all()
                cond.wait_for(lambda: state['derived'] + state['refused'] >= total, timeout=30)
            return real(password, salt, params)
        outcomes = []

        def attempt():
            try:
                self.auth.login('ana', WRONG, '192.0.2.21')
            except MemoryError as exc:
                outcomes.append(exc.code)
                if exc.code == 'rate_limited':
                    with cond:
                        state['refused'] += 1
                        cond.notify_all()
        with patch.object(passwords, 'GATE', OpenGate()), patch.object(passwords, '_derive', derive):
            threads = [threading.Thread(target=attempt) for _ in range(total)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        self.assertEqual(state['derived'], 10, 'no more verifications than the limit')
        self.assertEqual(sorted(outcomes), ['rate_limited'] * 10 + ['unauthorized'] * 10)
        self.assertEqual(self.rows("SELECT count(*) FROM memory.login_attempts WHERE client_ip='192.0.2.21'"), 10)

    def test_the_count_reads_the_index_login_attempt_ip_time(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.login_attempts(username,client_ip) SELECT 'u'||g, '10.'||(g%250)||'.'||(g/250%250)||'.1' FROM generate_series(1,20000) g")
            c.execute('ANALYZE memory.login_attempts')
            plan = '\n'.join(row[0] for row in c.execute('EXPLAIN ' + limits.IP_WAIT, {'ip': '10.1.1.1', 'window': 900, 'skip': 9}).fetchall())
        self.assertIn('login_attempt_ip_time', plan)


class UserFailuresTests(Fixture):
    def published(self):
        return observability.REGISTRY.get_sample_value('kairos_login_user_failures_total') or 0

    def test_login_user_failures_is_published_with_the_user_and_the_count_and_blocks_nothing(self):
        events, before = [], self.published()
        real = observability.log_event

        def log(event, level='info', **fields):
            events.append((event, level, fields))
            return real(event, level, **fields)
        with patch.object(observability, 'log_event', log):
            for index in range(3):
                self.fail_login(f'203.0.113.{index}')
            self.fail_login('203.0.113.9', username='nobody-here')
        failures = [fields for event, level, fields in events if event == 'login_user_failures']
        ana = self.rows("SELECT id FROM memory.actors WHERE username='ana'")
        self.assertEqual([(f.get('user_id'), f['count']) for f in failures], [(ana, 1), (ana, 2), (ana, 3), (None, 1)])
        self.assertEqual(self.published() - before, 4)
        self.assertEqual(self.auth.login('ana', pw.PASSWORD, '203.0.113.50')['actor']['username'], 'ana')

    def test_no_record_of_a_login_keeps_the_password(self):
        secret = 'Secret-Passw0rd-Never-Stored-77'
        stream = __import__('io').StringIO()
        observability.configure_logging(stream, 'DEBUG')
        self.addCleanup(observability.remove_logging)
        for username in ('ana', 'nobody-here'):
            with self.assertRaises(Unauthorized):
                self.auth.login(username, secret, '203.0.113.60')
        with self.psycopg.connect(self.dsn) as c:
            for table in ('login_attempts', 'audit_events', 'web_sessions', 'actors'):
                self.assertNotIn(secret, str(c.execute(f'SELECT * FROM memory.{table}').fetchall()), table)
        with self.assertRaises(Unauthorized):  # a password typed in the name field: the log never carries the name
            self.auth.login(secret, WRONG, '203.0.113.61')
        self.assertNotIn(secret, stream.getvalue())
        self.assertIn('login_user_failures', stream.getvalue())


class SettingsTests(Fixture):
    def test_the_limits_come_from_the_settings(self):
        create_app(Settings(self.dsn, login_max_failures=3, login_window=60, mount_mcp=False), store=self.store, auth=self.auth)
        self.fail_login('192.0.2.30', times=3)
        error = self.blocked('192.0.2.30')
        self.assertEqual(error.code, 'rate_limited')
        self.assertTrue(1 <= error.retry_after <= 60, error.retry_after)
        create_app(Settings(self.dsn, mount_mcp=False), store=self.store, auth=self.auth)
        self.assertEqual((limits.LOGIN.max_failures, limits.LOGIN.window), (10, 900))

    def test_the_variables_and_their_refusals(self):
        self.assertEqual(config.login_failure_settings({}), (10, 900))
        self.assertEqual(config.login_failure_settings({'MEMORY_LOGIN_MAX_FAILURES': '5', 'MEMORY_LOGIN_WINDOW': '600'}), (5, 600))
        for env in ({'MEMORY_LOGIN_MAX_FAILURES': '0'}, {'MEMORY_LOGIN_MAX_FAILURES': 'ten'}, {'MEMORY_LOGIN_MAX_FAILURES': '1001'},
                    {'MEMORY_LOGIN_WINDOW': '59'}, {'MEMORY_LOGIN_WINDOW': '86401'}, {'MEMORY_LOGIN_WINDOW': '15m'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                config.login_failure_settings(env)
        with self.assertRaises(ValueError):
            Settings('unused', login_max_failures=0)


class HttpTests(Fixture):
    def test_the_http_429_has_retry_after_and_the_body_of_dc2(self):
        app = create_app(Settings(self.dsn, allowed_origins=(ORIGIN,), mount_mcp=False), store=self.store, auth=self.auth)
        with TestClient(app) as client:
            for _ in range(10):
                self.assertEqual(client.post('/v1/auth/login', json={'username': 'ana', 'password': WRONG}, headers={'Origin': ORIGIN}).status_code, 401)
            blocked = client.post('/v1/auth/login', json={'username': 'ana', 'password': pw.PASSWORD}, headers={'Origin': ORIGIN})
        self.assertEqual(blocked.status_code, 429)
        seconds = int(blocked.headers['Retry-After'])
        body = blocked.json()
        self.assertGreaterEqual(seconds, 1)
        self.assertEqual(body['error'], {'code': 'rate_limited', 'message': f'Rate limit exceeded [code=rate_limited retry_after={seconds}]', 'retry_after': seconds})
        self.assertEqual(body['request_id'], blocked.headers['X-Request-ID'])


class ConstructorTests(unittest.TestCase):
    def test_one_shape_for_every_429(self):
        for asked, seconds in ((0, 1), (0.2, 1), (16.2, 17), (17, 17)):
            with self.subTest(asked=asked):
                error = limits.too_many('rate_limited', asked)
                self.assertEqual((error.status_code, error.code, error.retry_after, error.message), (429, 'rate_limited', seconds, f'Rate limit exceeded [code=rate_limited retry_after={seconds}]'))
        self.assertEqual(limits.too_many('too_many_attempts', 30).message, 'Too many password changes [code=too_many_attempts retry_after=30]')
        with self.assertRaises(KeyError):
            limits.too_many('made_up', 3)


if __name__ == '__main__':
    unittest.main()
