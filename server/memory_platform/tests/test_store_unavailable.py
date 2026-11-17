"""`StoreUnavailable` and `is_store_unavailable` (I3 / CA-10, CA-11): "the database does not answer" is told apart from "the provider failed".

The database goes away through the `FaultProxy`: the store connects to the proxy, the test cuts it, and nothing waits for a timer."""
import os
import traceback
import unittest

from memory_platform.errors import Conflict, MemoryError, NotFound, StoreUnavailable, is_store_error, is_store_unavailable
from memory_platform.providers import ProviderError
from memory_platform.store import Store
from memory_platform.tests.fault_proxy import FaultProxy

PASSWORD = 's3kr3t-pw-never-in-a-message'


class ClassifierTests(unittest.TestCase):
    def test_the_connection_errors_of_the_driver_and_the_class_itself_are_the_database_not_answering(self):
        import psycopg
        from psycopg import errors
        for exc in (psycopg.OperationalError('server closed the connection unexpectedly'), psycopg.InterfaceError('the connection is closed'),
                    errors.AdminShutdown('terminating connection'), errors.ConnectionTimeout('connection timeout expired'), StoreUnavailable('OperationalError')):
            self.assertTrue(is_store_unavailable(exc), type(exc).__name__)

    def test_only_the_connection_and_shutdown_sqlstates_are_an_outage(self):
        """The server going away says class 08 or 57P01/57P02/57P03, or says nothing at all; an OperationalError the server answered with is one statement's problem."""
        import psycopg
        from psycopg import errors
        outage = ('08000', '08001', '08003', '08004', '08006', '08007', '08P01', '57P01', '57P02', '57P03')
        answered = ('57014', '55P03', '54000', '54001', '54011', '54023', '40001', '40P01', '53100', '53200', '53300', '57P04', '55006', '25006')
        for state in outage:
            exc = errors.lookup(state)('x')
            self.assertEqual(exc.sqlstate, state)
            self.assertTrue(is_store_unavailable(exc), state)
            self.assertFalse(is_store_error(exc), state)
        for state in answered:
            exc = errors.lookup(state)('x')
            self.assertEqual(exc.sqlstate, state)
            self.assertFalse(is_store_unavailable(exc), state)
            self.assertTrue(is_store_error(exc), state)  # an error of the database all the same: it is not the provider's either
        self.assertTrue(is_store_unavailable(psycopg.OperationalError('connection refused')))  # no SQLSTATE: the server never answered
        self.assertTrue(is_store_unavailable(psycopg.InterfaceError('the connection is closed')))
        self.assertFalse(is_store_error(ValueError('x')))
        self.assertFalse(is_store_error(ProviderError('provider_unavailable', retryable=True)))

    def test_a_provider_error_is_never_the_database_not_answering(self):
        for exc in (ProviderError('provider_unavailable', retryable=True), ProviderError('provider_transport', retryable=True, ambiguous=True),
                    ProviderError('provider_rejected'), TimeoutError('provider took too long'), ConnectionError('provider refused'), OSError('socket')):
            self.assertFalse(is_store_unavailable(exc), repr(exc))

    def test_a_provider_error_is_not_the_database_even_when_it_wraps_a_database_one(self):
        import psycopg
        try:
            try:
                raise psycopg.OperationalError('x')
            except psycopg.OperationalError as cause:
                raise ProviderError('provider_transport', retryable=True) from cause
        except ProviderError as exc:
            self.assertFalse(is_store_unavailable(exc))

    def test_application_and_data_errors_are_not_the_database_not_answering(self):
        from psycopg import errors
        for exc in (MemoryError('invalid_embedding', 'x', 422), NotFound(), Conflict(), errors.UniqueViolation('duplicate'), errors.CheckViolation('check'),
                    ValueError('x'), KeyError('x')):
            self.assertFalse(is_store_unavailable(exc), type(exc).__name__)

    def test_the_class_is_not_a_domain_error_so_it_never_reaches_fail_job_as_a_code(self):
        self.assertFalse(issubclass(StoreUnavailable, MemoryError))
        self.assertEqual(str(StoreUnavailable('OperationalError')), 'Database unavailable')


class FaultedStoreTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        from psycopg.conninfo import make_conninfo
        self.store = Store(make_conninfo(self.proxy.dsn(), password=PASSWORD))

    def one(self):
        with self.store.transaction() as c:
            return c.execute('SELECT 1 AS one').fetchone()['one']

    def test_a_working_database_answers_and_nothing_is_wrapped(self):
        self.assertEqual(self.one(), 1)

    def test_a_cut_database_refuses_the_connection_as_store_unavailable_and_recovers_after_restore(self):
        self.proxy.cut()
        with self.assertRaises(StoreUnavailable) as caught:
            self.one()
        self.assertIn(caught.exception.cause_type, {'OperationalError', 'InterfaceError'})
        self.proxy.restore()
        self.assertEqual(self.one(), 1)

    def test_a_connection_cut_in_the_middle_of_a_query_is_store_unavailable(self):
        with self.assertRaises(StoreUnavailable):
            with self.store.transaction() as c:
                self.assertEqual(c.execute('SELECT 1 AS one').fetchone()['one'], 1)
                self.proxy.cut()
                c.execute('SELECT 2 AS two')

    def test_a_connection_cut_before_the_commit_is_store_unavailable(self):
        with self.assertRaises(StoreUnavailable):
            with self.store.transaction() as c:
                c.execute('SELECT 1 AS one').fetchone()
                self.proxy.cut()  # nothing else runs: the failure surfaces when the transaction commits

    def test_the_error_names_neither_the_password_nor_the_address_and_keeps_no_chain_that_could(self):
        self.proxy.cut()
        with self.assertRaises(StoreUnavailable) as caught:
            self.one()
        text = ' '.join([str(caught.exception), repr(caught.exception), ''.join(traceback.format_exception(caught.exception))])
        for secret in (PASSWORD, str(self.proxy.port), self.proxy.host, self.store.dsn):
            self.assertNotIn(secret, text)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_a_query_the_server_cancels_is_not_an_outage_and_leaves_as_it_was(self):
        from psycopg import errors
        with self.assertRaises(errors.QueryCanceled):
            with self.store.transaction() as c:
                c.execute("SET LOCAL statement_timeout = '50ms'")
                c.execute('SELECT pg_sleep(30)')
        self.assertEqual(self.one(), 1)

    def test_a_lock_timeout_and_a_serialization_failure_are_not_an_outage_either(self):
        import psycopg
        from psycopg import errors
        with psycopg.connect(os.environ['MEMORY_TEST_DSN'], autocommit=True) as holder:
            holder.execute('SELECT pg_advisory_lock(7310)')
            try:
                with self.assertRaises(errors.LockNotAvailable):
                    with self.store.transaction() as c:
                        c.execute("SET LOCAL lock_timeout = '50ms'")
                        c.execute('SELECT pg_advisory_xact_lock(7310)')
            finally:
                holder.execute('SELECT pg_advisory_unlock(7310)')
        with self.assertRaises(errors.SerializationFailure):
            with self.store.transaction():
                raise errors.SerializationFailure('could not serialize access')
        self.assertEqual(self.one(), 1)

    def test_other_errors_of_the_body_leave_untouched(self):
        from psycopg import errors
        with self.assertRaises(ValueError):
            with self.store.transaction():
                raise ValueError('mine')
        with self.assertRaises(NotFound):
            with self.store.transaction():
                raise NotFound()
        with self.assertRaises(errors.UniqueViolation):
            with self.store.transaction() as c:
                c.execute('CREATE TEMP TABLE once(id int PRIMARY KEY)')
                c.execute('INSERT INTO once VALUES (1)')
                c.execute('INSERT INTO once VALUES (1)')
        self.assertEqual(self.one(), 1)  # and the store is still usable


if __name__ == '__main__':
    unittest.main()
