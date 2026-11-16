"""Minor debt of the review of phase 4 (attempt 2, n.os 3-7), closed in phase 5 (T-30), each with a test that fails without its fix:

* n.o 4: `complete_job` writes the fragments in bounded batches, so the client-side plazo of a pooled connection (one per wait) never covers hundreds of rows at once;
* n.o 5: `/health/ready` answers `saturated`, never a 503, during the instant a connection is being given back (the slot is counted as in use until it is back in the pool);
* n.o 6: the busy-or-down decision of the pool does not depend on timers: `StoreBusy` only when every connection was in use at the timeout, `StoreUnavailable` otherwise
  (a host with several addresses, connections closed by the client-side plazo that the pool is replacing);
* n.o 7: a `StoreUnavailable` inside a layer of a search is the 503 of the request, never a 200 `partial`.

Real PostgreSQL where the database matters; no test waits for a clock to observe a state (the waits are events)."""
import asyncio
import math
import os
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

import psycopg
from psycopg_pool import PoolTimeout

from memory_platform import models as m
from memory_platform import store_jobs
from memory_platform.chunking import chunk_text, embedding_text
from memory_platform.config import Settings
from memory_platform.errors import StoreBusy, StoreUnavailable
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import close_pool, ready_probe
from memory_platform.tests import test_chunk_jobs  # the module, not its test class: importing the class here would run its tests a second time
from memory_platform.tests.test_chunk_jobs import long_content
from memory_platform.tests.test_store_pool import pool_store


class FragmentBatchTests(unittest.TestCase):
    publish, running_job, receipt_for, rows = (test_chunk_jobs.ChunkJobTests.publish, test_chunk_jobs.ChunkJobTests.running_job, test_chunk_jobs.ChunkJobTests.receipt_for,
                                               test_chunk_jobs.ChunkJobTests.rows)

    def setUp(self):
        from memory_platform.tests.test_store import create_core
        base, self.actor, self.pid = create_core()
        self.store = Store(base.dsn, embedding_enabled=True)

    def test_the_fragments_of_a_long_document_are_inserted_in_bounded_batches_and_all_of_them_land(self):
        self.assertLessEqual(store_jobs.CHUNK_INSERT_BATCH, 100)
        content = long_content(200000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        text = embedding_text('Long document', content)
        value = self.receipt_for(job, text, truncated=True)  # more text than MEMORY_CHUNK_MAX fragments cover: the receipt says so
        expected = len(value['chunks'])
        self.assertGreater(expected, 2 * store_jobs.CHUNK_INSERT_BATCH, 'the fixture must need several batches')
        sizes = []
        real = psycopg.Cursor.executemany

        def spy(cursor, query, params_seq, *args, **kwargs):
            params_seq = list(params_seq)
            if 'embedding_chunks' in str(query):
                sizes.append(len(params_seq))
            return real(cursor, query, params_seq, *args, **kwargs)
        with patch.object(psycopg.Cursor, 'executemany', spy):
            self.assertTrue(self.store.complete_job(job['id'], 5, value))
        self.assertEqual(sum(sizes), expected)
        self.assertLessEqual(max(sizes), store_jobs.CHUNK_INSERT_BATCH)
        self.assertEqual(len(sizes), math.ceil(expected / store_jobs.CHUNK_INSERT_BATCH))
        self.assertEqual([r['ordinal'] for r in self.rows(document_id)], list(range(expected)))  # same rows, same order, same transaction

    def test_the_batches_are_one_transaction_a_failure_in_a_later_batch_leaves_no_fragment(self):
        content = long_content(200000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        value = self.receipt_for(job, embedding_text('Long document', content), truncated=True)
        real = psycopg.Cursor.executemany
        calls = []

        def failing(cursor, query, params_seq, *args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise psycopg.errors.DataException('second batch fails')
            return real(cursor, query, params_seq, *args, **kwargs)
        with patch.object(psycopg.Cursor, 'executemany', failing):
            with self.assertRaises(psycopg.errors.DataException):
                self.store.complete_job(job['id'], 5, value)
        self.assertEqual(self.rows(document_id), [])


class PoolClassificationTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv('MEMORY_TEST_DSN'):
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')

    def opened(self, maximum):
        store = pool_store(minimum=1, maximum=maximum)
        self.addCleanup(close_pool, store)
        store.pool.wait()
        return store

    def hold(self, store):
        held, release = threading.Event(), threading.Event()

        def run():
            with store.transaction():
                held.set()
                release.wait(60)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(held.wait(30))
        self.addCleanup(lambda: (release.set(), thread.join(30)))
        return release

    def test_a_timeout_with_free_slots_and_no_fault_on_record_is_busy(self):
        # the pool growing under load with a healthy database, and the window in which a connection is being handed to the one that waits: `_in_use < max_size` and no fault
        store = self.opened(4)
        self.assertLess(store.pool._in_use, store.pool.max_size)
        with patch.object(store.pool._pool, 'getconn', side_effect=PoolTimeout('growing')):
            with self.assertRaises(StoreBusy):
                with store.transaction():
                    pass

    def test_a_timeout_with_every_connection_in_use_and_no_fault_is_busy(self):
        store = self.opened(1)
        self.hold(store)
        with patch.object(store.pool._pool, 'getconn', side_effect=PoolTimeout('full')):
            with self.assertRaises(StoreBusy):
                with store.transaction():
                    pass

    def test_a_timeout_with_a_fault_on_record_is_an_outage_with_free_slots_or_without(self):
        for maximum, held in ((1, True), (4, False)):
            with self.subTest(maximum=maximum, held=held):
                store = self.opened(maximum)
                if held:
                    self.hold(store)
                store.pool._failed_checks += 1  # a connect error or a failed check since the last connection it gave
                with patch.object(store.pool._pool, 'getconn', side_effect=PoolTimeout('down')):
                    with self.assertRaises(StoreUnavailable) as raised:
                        with store.transaction():
                            pass
                self.assertIsNot(type(raised.exception), StoreBusy)

    def test_ready_probe_follows_the_same_rule(self):
        store = self.opened(4)
        with patch.object(store.pool._pool, 'getconn', side_effect=PoolTimeout('growing')):
            self.assertEqual(ready_probe(store), 'saturated')  # free slots, healthy database: busy, not a dead database
            store.pool._failed_checks += 1
            with self.assertRaises(StoreUnavailable):
                ready_probe(store)

    def test_ready_probe_says_saturated_while_a_connection_is_being_given_back(self):
        store = self.opened(1)
        pool = store.pool
        at_put, go = threading.Event(), threading.Event()
        real = pool._pool.putconn

        def slow(connection, *args, **kwargs):
            at_put.set()  # the request is done and the connection is reset, but it is not in the pool yet
            go.wait(60)
            return real(connection, *args, **kwargs)
        self.addCleanup(go.set)
        held, release = threading.Event(), threading.Event()

        def run():
            with pool.connection():
                held.set()
                release.wait(60)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(held.wait(30))
        pool._pool.putconn = slow
        release.set()
        self.assertTrue(at_put.wait(30))
        with patch('memory_platform.store_pool.READY_WAIT', 0.05):
            self.assertEqual(ready_probe(store), 'saturated')  # it raised (503) when the slot was freed before the connection was back
        go.set()
        thread.join(30)
        pool._pool.putconn = real
        self.assertEqual(ready_probe(store), 'ready')


class SearchLayerOutageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Mock()
        self.store.search_items.return_value = []
        self.store.search_documents.return_value = []
        self.store.has_vectors.return_value = True
        self.embeddings = Mock(embed=AsyncMock(return_value={'embedding': [1.0, 0.0], 'model': 'nomic-embed-text', 'verified': True}))
        self.retrieval = Retrieval(self.store, Settings('unused', request_timeout=5), self.embeddings)

    def request(self, **changes):
        return m.Search(**{'project_ids': ['a'], 'q': 'x', 'layers': ['episodic'], 'semantic': False, **changes})

    async def test_a_database_that_does_not_answer_inside_a_layer_is_the_503_of_the_request_not_a_partial_200(self):
        outage = StoreUnavailable('OperationalError')
        cases = [('search_items', self.request()), ('search_documents', self.request(layers=['documental'])), ('has_vectors', self.request(semantic=True)),
                 ('search_vectors', self.request(semantic=True))]
        for name, request in cases:
            with self.subTest(layer=name):
                self.store.has_vectors.return_value = True
                with patch.object(self.store, name, Mock(side_effect=outage)):
                    with self.assertRaises(StoreUnavailable):
                        await self.retrieval.search({}, request)

    async def test_any_other_failure_of_a_layer_keeps_the_documented_partial_answer(self):
        with patch.object(self.store, 'search_items', Mock(side_effect=RuntimeError('boom'))):
            answer = await self.retrieval.search({}, self.request())
        self.assertTrue(answer['partial'])
        self.assertEqual(answer['backends']['episodic']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
