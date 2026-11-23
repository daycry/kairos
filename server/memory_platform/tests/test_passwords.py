"""CA-09 (T-07): scrypt at the measured cost, the dummy hash, the ceiling and the transparent rehash.

Derivations are counted (`passwords._derive` is the only call to `hashlib.scrypt`), never timed. The suite runs at a lower cost (`tests/__init__.py`);
the tests marked REAL run `passwords.DEFAULT_PARAMS`.
"""
import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch

from memory_platform import passwords
from memory_platform.auth import Auth
from memory_platform.errors import MemoryError, Unauthorized
from memory_platform.store import Store

PASSWORD = 'synthetic-password-123'
OLD = (2 ** 10, 8, 1)  # a cost below the target of every configuration of the suite: "the hash of an earlier release"


class Derivations:
    """Counts the calls of `passwords._derive` and keeps their parameters; the derivation itself still runs."""
    def __init__(self):
        self.calls = []
        self._real = passwords._derive

    def __enter__(self):
        def counted(password, salt, params):
            self.calls.append(params)
            return self._real(password, salt, params)
        self._patch = patch.object(passwords, '_derive', counted)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


def old_hash(password=PASSWORD, params=OLD):
    salt = bytes(range(16))
    return passwords._encode(salt, params, passwords._derive(password, salt, params))


class PasswordFunctionTests(unittest.TestCase):
    def test_the_default_cost_is_the_one_measured_in_t01(self):
        self.assertEqual(passwords.DEFAULT_PARAMS, (2 ** 17, 8, 1))

    def test_REAL_cost_hashes_and_verifies_with_an_explicit_maxmem(self):
        with patch.object(passwords, 'TARGET', passwords.DEFAULT_PARAMS):
            encoded = passwords.hash_password(PASSWORD)
            data = json.loads(encoded)
            self.assertEqual((data['v'], data['n'], data['r'], data['p']), (1, 2 ** 17, 8, 1))
            self.assertTrue(passwords.verify_password(PASSWORD, encoded))
            self.assertFalse(passwords.verify_password(PASSWORD + 'x', encoded))
        with self.assertRaises(ValueError):  # what T-01 found: the default `maxmem` (32 MiB) rejects the target cost
            hashlib.scrypt(b'x', salt=bytes(16), n=2 ** 17, r=8, p=1)

    def test_a_new_hash_uses_the_target_parameters_and_a_fresh_salt(self):
        first, second = passwords.hash_password(PASSWORD), passwords.hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        for encoded in (first, second):
            data = json.loads(encoded)
            self.assertEqual((data['n'], data['r'], data['p']), passwords.TARGET)
            self.assertTrue(passwords.verify_password(PASSWORD, encoded))

    def test_the_length_rule_is_checked_before_deriving(self):
        with Derivations() as spy:
            for bad in ('short', 'x' * 11, 'x' * 1025, None, 12345678901234):
                with self.assertRaises(MemoryError) as raised:
                    passwords.hash_password(bad)
                self.assertEqual((raised.exception.code, raised.exception.status_code), ('invalid_password', 422))
        self.assertEqual(spy.calls, [])

    def test_stored_parameters_above_the_target_are_rejected_without_deriving(self):
        n, r, p = passwords.TARGET
        for params in ((n * 2, r, p), (n, r * 2, p), (n, r, p + 1), (n * 2, r * 2, p * 2)):
            encoded = json.dumps({'v': 1, 'n': params[0], 'r': params[1], 'p': params[2], 'salt': '00' * 16, 'hash': '00' * 64})
            with Derivations() as spy:
                self.assertFalse(passwords.verify_password(PASSWORD, encoded), params)
            self.assertEqual(spy.calls, [], params)

    def test_a_hash_that_is_not_ours_never_verifies_and_never_derives(self):
        for encoded in ('!service-account', '', 'null', '[]', '{}', '{"v":2,"n":1024,"r":8,"p":1,"salt":"00","hash":"00"}', '{"v":1,"n":1000,"r":8,"p":1,"salt":"00","hash":"00"}',
                        '{"v":1,"n":true,"r":8,"p":1,"salt":"00","hash":"00"}', '{"v":1,"n":1024,"r":8,"p":1,"salt":"zz","hash":"00"}', None):
            with Derivations() as spy:
                self.assertFalse(passwords.verify_password(PASSWORD, encoded), encoded)
            self.assertEqual(spy.calls, [], encoded)

    def test_an_old_hash_still_verifies_at_its_own_cost(self):
        encoded = old_hash()
        self.assertTrue(passwords.needs_rehash(encoded))
        self.assertFalse(passwords.needs_rehash(passwords.hash_password(PASSWORD)))
        with Derivations() as spy:
            self.assertTrue(passwords.verify_password(PASSWORD, encoded))
        self.assertEqual(spy.calls, [OLD])


class CheckLoginTests(unittest.TestCase):
    """One derivation at the target cost per attempt, in every case (DC-5): counted, not timed."""
    def count(self, password, encoded):
        with Derivations() as spy:
            result = passwords.check_login(password, encoded)
        return result, spy.calls

    def test_a_current_hash_costs_one_target_derivation_right_or_wrong(self):
        encoded = passwords.hash_password(PASSWORD)
        for password, expected in ((PASSWORD, True), ('another-password-123', False)):
            (right, rehash), calls = self.count(password, encoded)
            self.assertEqual((right, rehash, calls), (expected, None, [passwords.TARGET]))

    def test_an_unknown_or_disabled_user_costs_the_same_single_derivation(self):
        (right, rehash), calls = self.count(PASSWORD, None)  # the row of a missing or disabled user is None
        self.assertEqual((right, rehash, calls), (False, None, [passwords.TARGET]))

    def test_a_dummy_hash_has_the_target_cost_and_nobody_matches_it(self):
        data = json.loads(passwords.dummy_hash())
        self.assertEqual((data['n'], data['r'], data['p']), passwords.TARGET)
        self.assertFalse(passwords.verify_password(PASSWORD, passwords.dummy_hash()))
        self.assertFalse(passwords.needs_rehash(passwords.dummy_hash()))

    def test_an_old_hash_costs_its_own_cheap_check_plus_one_target_derivation(self):
        encoded = old_hash()
        (right, rehash), calls = self.count(PASSWORD, encoded)
        self.assertEqual((right, calls), (True, [OLD, passwords.TARGET]))
        self.assertEqual(json.loads(rehash)['n'], passwords.TARGET[0])
        self.assertTrue(passwords.verify_password(PASSWORD, rehash))
        (right, rehash), calls = self.count('another-password-123', encoded)
        self.assertEqual((right, rehash, calls), (False, None, [OLD, passwords.TARGET]), 'a wrong password costs the same and yields no hash')

    def test_unreadable_or_above_target_hashes_cost_one_target_derivation_and_never_verify(self):
        n, r, p = passwords.TARGET
        above = json.dumps({'v': 1, 'n': n * 2, 'r': r, 'p': p, 'salt': '00' * 16, 'hash': '00' * 64})
        for encoded in ('!service-account', 'not json', above):
            (right, rehash), calls = self.count(PASSWORD, encoded)
            self.assertEqual((right, rehash, calls), (False, None, [passwords.TARGET]), encoded)


class Fixture(unittest.TestCase):
    """A database of its own (a trigger or a changed hash must not touch the shared one)."""
    def setUp(self):
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'pwd_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.dsn = make_conninfo(dsn, dbname=self.name)
        self.addCleanup(self.drop_database)
        self.store = Store(self.dsn)
        self.store.migrate()
        self.auth = Auth(self.store, ['https://memory.example'])
        self.admin = self.store.bootstrap_user('root-user', 'root-password-123')
        self.store.create_project(self.admin, {'id': 'p1', 'title': 'Project 1'})
        self.store.create_user(self.admin, {'username': 'ana', 'password': PASSWORD, 'project_ids': ['p1'], 'scopes': ['read']})

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def stored_hash(self, username='ana'):
        with self.psycopg.connect(self.dsn) as c:
            return c.execute('SELECT password_hash FROM memory.actors WHERE username=%s', (username,)).fetchone()[0]

    def set_hash(self, encoded, username='ana'):
        with self.psycopg.connect(self.dsn) as c:
            c.execute('UPDATE memory.actors SET password_hash=%s WHERE username=%s', (encoded, username))


class LoginTests(Fixture):
    def test_an_old_hash_is_replaced_after_the_first_correct_login_and_only_then(self):
        self.set_hash(old_hash())
        with self.assertRaises(Unauthorized):
            self.auth.login('ana', 'another-password-123', '192.0.2.1')
        self.assertEqual(json.loads(self.stored_hash())['n'], OLD[0], 'a wrong password does not replace the hash')
        with Derivations() as spy:
            session = self.auth.login('ana', PASSWORD, '192.0.2.1')
        self.assertEqual(spy.calls, [OLD, passwords.TARGET])
        self.assertEqual(session['actor']['username'], 'ana')
        data = json.loads(self.stored_hash())
        self.assertEqual((data['n'], data['r'], data['p']), passwords.TARGET)
        self.assertTrue(passwords.verify_password(PASSWORD, self.stored_hash()))
        with Derivations() as spy:  # the second login verifies the new hash: one derivation, nothing to replace
            self.auth.login('ana', PASSWORD, '192.0.2.1')
        self.assertEqual(spy.calls, [passwords.TARGET])
        self.assertEqual(self.stored_hash(), json.dumps(data))

    def test_unknown_disabled_and_wrong_password_cost_one_target_derivation_each(self):
        with self.psycopg.connect(self.dsn) as c:
            c.execute("INSERT INTO memory.actors(id,username,password_hash,disabled) VALUES('u9','off',%s,true)", (passwords.hash_password(PASSWORD),))
        for username, password in (('nobody', PASSWORD), ('off', PASSWORD), ('ana', 'another-password-123')):
            with Derivations() as spy:
                with self.assertRaises(Unauthorized):
                    self.auth.login(username, password, '192.0.2.2')
            self.assertEqual(spy.calls, [passwords.TARGET], username)

    def test_a_password_changed_while_the_login_derived_is_not_overwritten(self):
        self.set_hash(old_hash())
        real = passwords.check_login

        def changed_meanwhile(password, encoded):
            result = real(password, encoded)
            self.set_hash(old_hash('the-new-password-456'), 'ana')  # another request changed the password after this one read the hash
            return result
        with patch('memory_platform.auth.check_login', changed_meanwhile):
            self.auth.login('ana', PASSWORD, '192.0.2.3')
        self.assertTrue(passwords.verify_password('the-new-password-456', self.stored_hash()), 'UPDATE ... WHERE password_hash=<the one read> found nothing to replace')

    def test_a_failed_replacement_does_not_stop_the_login(self):
        self.set_hash(old_hash())
        with self.psycopg.connect(self.dsn) as c:
            c.execute("CREATE FUNCTION memory.refuse_rehash() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'refused'; END $$")
            c.execute('CREATE TRIGGER refuse_rehash BEFORE UPDATE OF password_hash ON memory.actors FOR EACH ROW EXECUTE FUNCTION memory.refuse_rehash()')
        session = self.auth.login('ana', PASSWORD, '192.0.2.4')
        self.assertEqual(session['actor']['username'], 'ana')
        self.assertEqual(json.loads(self.stored_hash())['n'], OLD[0], 'the old hash stays: the write failed')
        self.assertEqual(self.auth.authenticate_session(session['session_token'])['username'], 'ana', 'the session works')


class BootstrapTests(Fixture):
    def test_the_bootstrap_derives_once(self):
        """`memory-bootstrap` has 256 MB (T-01): one derivation at a time. The call is synchronous: it derives once and returns before anything else starts."""
        with self.psycopg.connect(self.dsn) as c:
            c.execute('DELETE FROM memory.project_grants')
            c.execute('DELETE FROM memory.api_keys')
            c.execute('DELETE FROM memory.web_sessions')
            c.execute('DELETE FROM memory.actors')
        with Derivations() as spy:
            self.store.bootstrap_user('first-admin', 'first-password-123')
        self.assertEqual(spy.calls, [passwords.TARGET])
        self.assertTrue(passwords.verify_password('first-password-123', self.stored_hash('first-admin')))

if __name__ == '__main__':
    unittest.main()
