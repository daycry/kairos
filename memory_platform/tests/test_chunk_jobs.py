"""complete_job writes the item vector and every fragment in ONE transaction (CA-27): never a partial set of fragments."""
import asyncio
import hashlib
import json
import unittest
import uuid

import httpx

from memory_platform.chunking import chunk_text, embedding_text
from memory_platform.config import Settings
from memory_platform.errors import MemoryError
from memory_platform.providers import Embeddings
from memory_platform.store import Store
from memory_platform.tests.test_store import create_core
from memory_platform.worker import Worker

MODEL = 'nomic-embed-text'


def long_content(characters, marker=''):
    paragraphs, total = [], 0
    while total < characters:
        paragraphs.append(('palabra ' * 60).strip() + '.')
        total += len(paragraphs[-1]) + 2
    return ('\n\n'.join(paragraphs)[:characters] + ' ' + marker).strip()


class ChunkJobTests(unittest.TestCase):
    def setUp(self):
        base, self.actor, self.pid = create_core()
        self.store = Store(base.dsn, embedding_enabled=True)

    def publish(self, content, version=1, document_id=None, title='Long document'):
        document_id = document_id or str(uuid.uuid4())
        document = {'document_id': document_id, 'version': version, 'title': title, 'content': content,
                    'source': {'uri': 'fixture://chunks', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['fixture://review']}}
        receipt = self.store.publish_document(self.actor, self.pid, document)
        return document_id, receipt

    def running_job(self, receipt):
        with self.store.transaction() as c:
            job = c.execute("SELECT * FROM memory.jobs WHERE id=ANY(%s) AND destination='embed'", (receipt['jobs'],)).fetchone()
            c.execute("UPDATE memory.jobs SET state='running',fence=5,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (job['id'],))
        return job

    def receipt_for(self, job, text, vectors=None, truncated=False):
        chunks = chunk_text(text)
        vectors = vectors or [[1.0 + number, 0.5] for number in range(len(chunks))]
        value = {'vector': vectors[0], 'model': MODEL, 'verified': True, 'canonical_hash': job['canonical_hash'],
                 'chunks': [{'ordinal': c.ordinal, 'char_start': c.char_start, 'char_end': c.char_end, 'vector': v} for c, v in zip(chunks, vectors)]}
        if truncated:
            value.update(chunks_truncated=True, chunks_covered_chars=chunks[-1].char_end)
        return value

    def rows(self, document_id, table='memory.embedding_chunks'):
        with self.store.transaction() as c:
            return c.execute(f'SELECT * FROM {table} WHERE project_id=%s AND item_id=%s ORDER BY version,ordinal' if table.endswith('chunks') else f'SELECT * FROM {table} WHERE project_id=%s AND item_id=%s ORDER BY version',
                             (self.pid, document_id)).fetchall()

    def job_state(self, job):
        with self.store.transaction() as c:
            return c.execute('SELECT state,error_code FROM memory.jobs WHERE id=%s', (job['id'],)).fetchone()

    def test_all_fragments_and_the_item_vector_are_written_together(self):
        content = long_content(12000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        text = embedding_text('Long document', content)
        value = self.receipt_for(job, text)
        self.assertTrue(self.store.complete_job(job['id'], 5, value))
        chunks = chunk_text(text)
        stored = self.rows(document_id)
        self.assertEqual([(r['ordinal'], r['char_start'], r['char_end']) for r in stored], [tuple(c) for c in chunks])
        self.assertTrue(all((r['model'], r['dims'], r['resource_type'], r['version']) == (MODEL, 2, 'document', 1) for r in stored))
        item = self.rows(document_id, 'memory.embeddings')
        self.assertEqual(len(item), 1)
        self.assertEqual(item[0]['vector'], value['vector'])
        with self.store.transaction() as c:
            recorded = c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s', (job['id'],)).fetchone()['receipt']
        self.assertEqual(recorded['chunks'], len(chunks))
        self.assertNotIn('vector', json.dumps(recorded))
        self.assertNotIn('chunks_truncated', recorded)

    def test_a_truncated_text_is_recorded_in_the_receipt(self):
        content = long_content(12000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        text = embedding_text('Long document', content)
        value = self.receipt_for(job, text)
        value['chunks'] = value['chunks'][:4]
        value.update(chunks_truncated=True, chunks_covered_chars=value['chunks'][-1]['char_end'])
        self.assertTrue(self.store.complete_job(job['id'], 5, value))
        with self.store.transaction() as c:
            recorded = c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s', (job['id'],)).fetchone()['receipt']
        self.assertEqual((recorded['chunks'], recorded['chunks_truncated']), (4, True))
        self.assertEqual(recorded['chunks_covered_chars'], value['chunks'][-1]['char_end'])

    def test_a_receipt_without_fragments_stores_one_fragment_for_the_whole_short_text(self):
        document_id, receipt = self.publish('Short body')
        job = self.running_job(receipt)
        self.assertTrue(self.store.complete_job(job['id'], 5, {'vector': [1.0, 0.0], 'model': MODEL, 'canonical_hash': job['canonical_hash'], 'verified': True}))
        stored = self.rows(document_id)
        self.assertEqual([(r['ordinal'], r['char_start'], r['char_end']) for r in stored], [(0, 0, len(embedding_text('Long document', 'Short body')))])
        with self.store.transaction() as c:
            recorded = c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s', (job['id'],)).fetchone()['receipt']
        self.assertEqual(set(recorded), {'model', 'dimensions', 'hash', 'status', 'verified'})

    def test_one_invalid_fragment_leaves_nothing_stored_and_the_job_running(self):
        """CA-27 at the store: the whole receipt is atomic. An error on the LAST fragment rolls back the item vector and every other fragment."""
        content = long_content(12000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        text = embedding_text('Long document', content)
        base = self.receipt_for(job, text)
        broken = [
            lambda v: v['chunks'][-1].update(vector=[1.0, 0.5, 0.25]),            # another dimension
            lambda v: v['chunks'][-1].update(vector=[0.0, 0.0]),                    # zero norm
            lambda v: v['chunks'][-1].update(vector=[1.0, float('inf')]),           # not finite
            lambda v: v['chunks'][2].update(ordinal=7),                             # ordinals are not consecutive
            lambda v: v['chunks'][-1].update(char_start=v['chunks'][-2]['char_end'] + 5),   # a gap in the coverage
            lambda v: v['chunks'][-1].update(char_end=len(text) + 10),              # beyond the text
            lambda v: v['chunks'][-1].update(char_end=v['chunks'][-1]['char_start']),
            lambda v: v['chunks'].__setitem__(slice(None, None), v['chunks'][:-1]),  # the tail of the text is missing without saying so
            lambda v: v.update(chunks=[]),
            lambda v: v.update(chunks='x'),
            lambda v: v.update(chunks=v['chunks'] * 40),                            # above the hard bound
        ]
        for index, damage in enumerate(broken):
            value = json.loads(json.dumps(base))
            damage(value)
            if index == 2:
                value['chunks'][-1]['vector'] = [1.0, 1e999]
            with self.assertRaises(MemoryError, msg=index) as raised:
                self.store.complete_job(job['id'], 5, value)
            self.assertEqual(raised.exception.code, 'invalid_embedding', index)
            self.assertEqual(self.rows(document_id), [], index)
            self.assertEqual(self.rows(document_id, 'memory.embeddings'), [], index)
            self.assertEqual(self.job_state(job)['state'], 'running', index)

    def test_a_vector_of_the_item_with_other_dimensions_than_the_fragments_is_rejected(self):
        content = long_content(6000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        value = self.receipt_for(job, embedding_text('Long document', content))
        value['vector'] = [1.0, 0.5, 0.1]
        with self.assertRaises(MemoryError):
            self.store.complete_job(job['id'], 5, value)
        self.assertEqual(self.rows(document_id), [])

    def test_completing_again_replaces_the_fragments_of_that_version(self):
        content = long_content(12000)
        document_id, receipt = self.publish(content)
        text = embedding_text('Long document', content)
        job = self.running_job(receipt)
        self.assertTrue(self.store.complete_job(job['id'], 5, self.receipt_for(job, text)))
        first = len(self.rows(document_id))
        with self.store.transaction() as c:  # a backfill re-queues the very same job
            c.execute("UPDATE memory.jobs SET state='running',fence=6,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (job['id'],))
        shorter = self.receipt_for(job, text)
        shorter['chunks'] = shorter['chunks'][:3]
        shorter.update(chunks_truncated=True, chunks_covered_chars=shorter['chunks'][-1]['char_end'])
        self.assertTrue(self.store.complete_job(job['id'], 6, shorter))
        self.assertGreater(first, 3)
        self.assertEqual([r['ordinal'] for r in self.rows(document_id)], [0, 1, 2])

    def test_a_new_version_drops_the_previous_versions_fragments(self):
        """CA-26 at the store: the old version's fragments are gone, not only filtered."""
        content = long_content(9000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        self.assertTrue(self.store.complete_job(job['id'], 5, self.receipt_for(job, embedding_text('Long document', content))))
        newer = long_content(9000, 'version-two')
        _, receipt2 = self.publish(newer, version=2, document_id=document_id)
        job2 = self.running_job(receipt2)
        self.assertTrue(self.store.complete_job(job2['id'], 5, self.receipt_for(job2, embedding_text('Long document', newer))))
        self.assertEqual({r['version'] for r in self.rows(document_id)}, {2})

    def test_a_stale_fence_or_superseded_version_writes_no_fragment(self):
        content = long_content(9000)
        document_id, receipt = self.publish(content)
        job = self.running_job(receipt)
        value = self.receipt_for(job, embedding_text('Long document', content))
        self.assertFalse(self.store.complete_job(job['id'], 4, value))
        self.assertEqual(self.rows(document_id), [])

    def test_a_blank_run_document_completes_with_every_fragment_and_the_whole_text_vector(self):
        """Gap 3 end to end: the receipt of `'T\\nintro\\n' + 4000 newlines + 'fin'` is accepted by complete_job."""
        content = 'intro\n' + '\n' * 4000 + 'fin'
        document_id, receipt = self.publish(content, title='T')
        job = self.running_job(receipt)
        text = embedding_text('T', content)
        value = self.receipt_for(job, text)
        self.assertTrue(self.store.complete_job(job['id'], 5, value))
        stored = self.rows(document_id)
        self.assertEqual((stored[0]['char_start'], stored[-1]['char_end']), (0, len(text)))
        self.assertTrue(self.rows(document_id, 'memory.embeddings')[0]['chunked'])


class ChunkJobWorkerTests(unittest.TestCase):
    """End to end with the real worker and provider, in a database of its own (the worker claims whatever job is next)."""
    def setUp(self):
        import os
        dsn = os.getenv('MEMORY_TEST_DSN')
        if not dsn:
            raise unittest.SkipTest('MEMORY_TEST_DSN must point to an isolated PostgreSQL test database')
        import psycopg
        from psycopg.conninfo import make_conninfo
        from memory_platform.auth import hash_password
        self.psycopg, self.base_dsn = psycopg, dsn
        self.name = 'cjw_' + uuid.uuid4().hex[:12]
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE {self.name}')
        self.addCleanup(self.drop_database)
        self.store = Store(make_conninfo(dsn, dbname=self.name), embedding_enabled=True)
        self.store.migrate()
        self.pid = 'p-' + uuid.uuid4().hex[:10]
        with self.store.transaction() as c:
            aid = str(uuid.uuid4())
            c.execute('INSERT INTO memory.actors(id,username,password_hash,is_admin) VALUES(%s,%s,%s,true)', (aid, 'u-' + aid[:8], hash_password('fixture-password-123')))
        self.actor = {'id': aid, 'credential_type': 'bootstrap'}
        self.store.create_project(self.actor, {'id': self.pid, 'title': 'Chunk worker test'})
        self.store.set_policy(self.actor, self.pid, {'capture_mode': 'summary', 'temporal_projection': True})

    def drop_database(self):
        with self.psycopg.connect(self.base_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {self.name} WITH (FORCE)')

    def count(self, table):
        with self.store.transaction() as c:
            return c.execute(f'SELECT count(*) AS n FROM memory.{table}').fetchone()['n']

    def test_provider_failure_at_fragment_k_of_n_leaves_no_fragment_and_follows_max_attempts(self):
        content = long_content(12000)
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Long document', 'content': content,
                    'source': {'uri': 'fixture://chunks', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['fixture://review']}}
        receipt = self.store.publish_document(self.actor, self.pid, document)
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(len(body['input']))
            if len(requests) == 3:
                return httpx.Response(503)
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5] for _ in body['input']]})
        settings = Settings('unused', lease_seconds=30, max_attempts=2, embedding_batch_size=2)
        worker = Worker(self.store, settings, {'embed': Embeddings(settings, httpx.MockTransport(respond))}, worker_id='chunk-test')
        self.assertTrue(asyncio.run(worker.run_once()))
        self.assertEqual(requests, [2, 2, 2])  # the failure came at the third batch: nothing after it was requested
        with self.store.transaction() as c:
            state = c.execute('SELECT state,error_code,attempts FROM memory.jobs WHERE id=ANY(%s)', (receipt['jobs'],)).fetchone()
        self.assertEqual((state['state'], state['error_code'], state['attempts']), ('pending', 'provider_unavailable', 1))  # attempt 1 of 2: retried
        self.assertEqual((self.count('embedding_chunks'), self.count('embeddings')), (0, 0))
        with self.store.transaction() as c:
            c.execute("UPDATE memory.jobs SET available_at=clock_timestamp()-interval '1 second' WHERE id=ANY(%s)", (receipt['jobs'],))
        requests.clear()
        self.assertTrue(asyncio.run(worker.run_once()))  # attempt 2 of 2: the transport fails again on its third request
        with self.store.transaction() as c:
            state = c.execute('SELECT state,error_code,attempts FROM memory.jobs WHERE id=ANY(%s)', (receipt['jobs'],)).fetchone()
        self.assertEqual((state['state'], state['error_code'], state['attempts']), ('failed', 'provider_unavailable', 2))
        self.assertEqual((self.count('embedding_chunks'), self.count('embeddings')), (0, 0))

    def test_a_successful_run_stores_every_fragment_once(self):
        content = long_content(12000)
        document = {'document_id': str(uuid.uuid4()), 'version': 1, 'title': 'Long document', 'content': content,
                    'source': {'uri': 'fixture://chunks', 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()},
                    'validation': {'status': 'validated', 'validated_by': 'fixture', 'evidence': ['fixture://review']}}
        self.store.publish_document(self.actor, self.pid, document)

        def respond(request):
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5] for _ in json.loads(request.content)['input']]})
        settings = Settings('unused', lease_seconds=30, embedding_batch_size=4)
        worker = Worker(self.store, settings, {'embed': Embeddings(settings, httpx.MockTransport(respond))}, worker_id='chunk-test')
        self.assertTrue(asyncio.run(worker.run_once()))
        self.assertEqual(self.count('embedding_chunks'), len(chunk_text(embedding_text('Long document', content))))
        self.assertEqual(self.count('embeddings'), 1)


if __name__ == '__main__':
    unittest.main()
