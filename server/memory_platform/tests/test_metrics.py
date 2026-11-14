"""CA-30/CA-31: Prometheus registry, instrumentation of layers/providers/worker and the internal-only `/metrics` route."""
import asyncio
import inspect
import io
import os
import pathlib
import re
import unittest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import httpx
import yaml
from fastapi.testclient import TestClient
from memory_platform import observability
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.providers import Embeddings, Ollama, ProviderError
from memory_platform.retrieval import Retrieval
from memory_platform.tests.test_observability import SECRET, QUERY, fake_app

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]


def sample(name, **labels):
    return observability.REGISTRY.get_sample_value(name, labels) or 0.0


def no_cache(case):
    """The scrape cache would hand a test the values of the previous one."""
    patcher = patch.object(observability, 'QUEUE_CACHE_SECONDS', 0)
    patcher.start()
    case.addCleanup(patcher.stop)
    observability.reset_queue_cache()


def jobs_store(states=(), failed=()):
    """A store whose connection answers the two scrape queries (counts by state, failed by code) and remembers what it was asked."""
    connection, asked = MagicMock(), []

    def execute(sql, *args):
        asked.append(sql)
        result = MagicMock()
        result.fetchall.return_value = list(failed if 'error_code' in sql else states)
        return result
    connection.execute.side_effect = execute
    store = MagicMock()
    store.transaction.return_value.__enter__.return_value = connection
    return store, asked


class RegistryTests(unittest.TestCase):
    def setUp(self):
        no_cache(self)

    def test_the_three_metrics_exist_with_the_spec_names_and_labels(self):
        observability.observe_layer('episodic', 0.01)
        observability.count_provider_error('embed', 'provider_unavailable')
        text = observability.render_metrics().decode()
        self.assertIn('# TYPE kairos_retrieval_layer_seconds histogram', text)
        self.assertIn('kairos_retrieval_layer_seconds_bucket{layer="episodic",le="0.005"}', text)
        self.assertIn('# TYPE kairos_provider_errors_total counter', text)
        self.assertIn('kairos_provider_errors_total{code="provider_unavailable",provider="embed"}', text)
        observability.refresh_queue_depth(MagicMock())
        self.assertIn('# TYPE kairos_jobs_queue_depth gauge', observability.render_metrics().decode())

    def test_labels_only_take_closed_values(self):
        observability.observe_layer('project-secret-layer', 0.01)
        observability.count_provider_error('http://evil.invalid/?token=' + SECRET, 'sk-' + 'z' * 40)
        text = observability.render_metrics().decode()
        for leaked in ('project-secret-layer', 'evil.invalid', SECRET, 'z' * 40):
            self.assertNotIn(leaked, text)
        self.assertEqual(sample('kairos_retrieval_layer_seconds_count', layer='other') >= 1, True)
        self.assertEqual(sample('kairos_provider_errors_total', provider='other', code='other') >= 1, True)

    def test_the_queue_depth_is_read_from_the_jobs_table_at_scrape_time(self):
        store, asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 7}, {'state': 'weird-state', 'destination': 'project-x', 'n': 1}],
                                  [{'destination': 'extract', 'error_code': 'provider_rejected', 'n': 1}, {'destination': 'extract', 'error_code': 'provider_timeout', 'n': 1}])
        observability.refresh_queue_depth(store)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 7)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='failed', destination='extract'), 2)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='running', destination='embed'), 0)  # every closed pair is present
        self.assertEqual(sample('kairos_jobs_queue_depth', state='other', destination='other'), 1)
        store, asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 1}])
        observability.refresh_queue_depth(store)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 1)  # no stale value
        self.assertEqual(sample('kairos_jobs_queue_depth', state='failed', destination='extract'), 0)

    def test_the_scrape_query_is_bounded_and_skips_the_terminal_bulk(self):
        store, asked = jobs_store()
        observability.refresh_queue_depth(store)
        self.assertRegex(asked[0], r'(?i)^SET LOCAL statement_timeout\s*=\s*\d+$')
        counts = [sql for sql in asked if 'GROUP BY state' in sql][0]
        self.assertIn("state IN ('pending','running','unknown')", counts)
        self.assertNotIn('succeeded', counts)
        self.assertNotIn('failed', counts)  # Gap 1: the queue read never touches the historical failed rows; their count comes from the indexed failed-by-code read
        self.assertIn("WHERE state='failed'", [sql for sql in asked if 'error_code' in sql][0])

    def test_gap1_the_failed_depth_comes_from_the_failed_by_code_read_and_the_queue_sql_has_no_failed(self):
        store, asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 3}],
                                  [{'destination': 'embed', 'error_code': 'provider_timeout', 'n': 4}, {'destination': 'embed', 'error_code': None, 'n': 1},
                                   {'destination': 'project-x', 'error_code': 'provider_timeout', 'n': 2}])
        observability.refresh_queue_depth(store)
        queue_sql = [sql for sql in asked if 'GROUP BY state' in sql][0]
        self.assertNotIn('failed', queue_sql.lower())
        self.assertEqual(sample('kairos_jobs_queue_depth', state='failed', destination='embed'), 5)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='failed', destination='extract'), 0)
        self.assertEqual(sample('kairos_jobs_failed', destination='other', code='provider_timeout'), 2)  # a failed row of an unknown destination is still visible by code

    def test_a_loop_of_scrapes_reads_the_database_once_per_window(self):
        store, asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 4}])
        with patch.object(observability, 'QUEUE_CACHE_SECONDS', 10):
            observability.reset_queue_cache()
            for _ in range(5):
                self.assertTrue(observability.refresh_queue_depth(store))
            self.assertEqual(store.transaction.call_count, 2)  # the two reads (live states, failed by code), each in its own transaction
            observability._QUEUE_CACHE['at'] -= 11  # the window is over
            observability.refresh_queue_depth(store)
        self.assertEqual(store.transaction.call_count, 4)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 4)

    def test_failed_jobs_are_derived_from_the_table_by_closed_code(self):
        store, asked = jobs_store(failed=[{'destination': 'extract', 'error_code': 'provider_rejected', 'n': 3},
                                          {'destination': 'embed', 'error_code': 'provider_timeout', 'n': 2},
                                          {'destination': 'embed', 'error_code': 'superseded', 'n': 1},
                                          {'destination': 'embed', 'error_code': 'sk-' + 'q' * 40, 'n': 5}, {'destination': 'embed', 'error_code': None, 'n': 1}])
        observability.refresh_queue_depth(store)
        self.assertEqual(sample('kairos_jobs_failed', destination='extract', code='provider_rejected'), 3)
        self.assertEqual(sample('kairos_jobs_failed', destination='embed', code='provider_timeout'), 2)
        self.assertEqual(sample('kairos_jobs_failed', destination='embed', code='superseded'), 1)
        self.assertEqual(sample('kairos_jobs_failed', destination='embed', code='other'), 6)  # unknown codes and NULL collapse, never a free label
        self.assertNotIn('q' * 40, observability.render_metrics().decode())
        store, asked = jobs_store()
        observability.refresh_queue_depth(store)
        self.assertEqual(sample('kairos_jobs_failed', destination='extract', code='provider_rejected'), 0)  # nothing stale

    def test_a_failing_read_is_visible_in_the_scrape_success_gauge(self):
        store, asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 9}])
        self.assertTrue(observability.refresh_queue_depth(store))
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 1)
        broken = MagicMock()
        broken.transaction.side_effect = RuntimeError('database down')
        self.assertFalse(observability.refresh_queue_depth(broken))
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 0)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 9)  # the last good value stays, flagged by the gauge
        self.assertTrue(observability.refresh_queue_depth(store))
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 1)

    def test_n2_a_failing_failed_jobs_read_does_not_cost_the_queue_depth(self):
        """N2: the two scrape queries run in separate transactions; the slow `failed` one (statement_timeout) cannot take the queue depth with it."""
        def store_failing(marker):
            connection, asked = MagicMock(), []

            def execute(sql, *args):
                asked.append(sql)
                if marker in sql:
                    raise RuntimeError('canceling statement due to statement timeout')
                result = MagicMock()
                result.fetchall.return_value = [{'state': 'pending', 'destination': 'embed', 'n': 5}] if 'GROUP BY state' in sql else [{'destination': 'embed', 'error_code': 'provider_timeout', 'n': 2}]
                return result
            connection.execute.side_effect = execute
            store = MagicMock()
            store.transaction.return_value.__enter__.return_value = connection
            return store
        good, _asked = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 1}], [{'destination': 'embed', 'error_code': 'provider_timeout', 'n': 1}])
        observability.refresh_queue_depth(good)
        observability.reset_queue_cache()
        self.assertFalse(observability.refresh_queue_depth(store_failing('error_code')))
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 5)  # the queue depth is fresh
        self.assertEqual(sample('kairos_jobs_failed', destination='embed', code='provider_timeout'), 1)  # the failed series keeps its last good value
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 0)
        observability.reset_queue_cache()
        self.assertFalse(observability.refresh_queue_depth(store_failing('GROUP BY state')))
        self.assertEqual(sample('kairos_jobs_failed', destination='embed', code='provider_timeout'), 2)  # and the other way round
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination='embed'), 5)
        observability.reset_queue_cache()
        self.assertTrue(observability.refresh_queue_depth(store_failing('never-matches')))
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 1)

    def test_n2_each_read_runs_in_its_own_bounded_transaction(self):
        store, asked = jobs_store()
        observability.refresh_queue_depth(store)
        self.assertEqual(store.transaction.call_count, 2)
        self.assertEqual(len([sql for sql in asked if sql.upper().startswith('SET LOCAL STATEMENT_TIMEOUT')]), 2)

    def test_the_queue_depth_follows_real_jobs(self):
        from memory_platform.tests.test_store import create_core, event
        store, actor, pid = create_core(extraction=True)
        accepted = store.ingest_event(actor, event(pid))
        with store.transaction() as c:
            row = c.execute('SELECT destination FROM memory.jobs WHERE id=%s', (accepted['jobs'][0],)).fetchone()
        destination = row['destination']
        observability.refresh_queue_depth(store)
        before = sample('kairos_jobs_queue_depth', state='pending', destination=destination)
        failed_before = sample('kairos_jobs_queue_depth', state='failed', destination=destination)
        self.assertGreaterEqual(before, 1)  # the new job is counted at the moment of reading
        failed_code_before = sample('kairos_jobs_failed', destination=destination, code='provider_rejected')
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='failed',error_code='provider_rejected' WHERE id=%s", (accepted['jobs'][0],))
        observability.refresh_queue_depth(store)
        self.assertEqual(sample('kairos_jobs_failed', destination=destination, code='provider_rejected'), failed_code_before + 1)
        self.assertEqual(sample('kairos_jobs_queue_scrape_success'), 1)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='pending', destination=destination), before - 1)
        self.assertEqual(sample('kairos_jobs_queue_depth', state='failed', destination=destination), failed_before + 1)

    def test_prometheus_client_is_pinned_to_an_exact_version(self):
        text = (PACKAGE / 'requirements.txt').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^prometheus_client==\d+\.\d+\.\d+\r?$')

    def test_one_uvicorn_process_serves_the_registry(self):
        from memory_platform import app
        self.assertNotIn('workers', inspect.getsource(app.main))
        self.assertNotIn('--workers', (PACKAGE / 'Dockerfile').read_text(encoding='utf-8'))
        self.assertNotIn('workers', (ROOT / 'docker-compose.yml').read_text(encoding='utf-8').split('memory-api:')[1].split('memory-worker:')[0])


class InstrumentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_search_records_the_latency_of_the_layers_it_ran(self):
        app, store, auth, retrieval = fake_app()
        before = {layer: sample('kairos_retrieval_layer_seconds_count', layer=layer) for layer in ('episodic', 'documental')}
        await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic', 'documental'], 'semantic': False})
        for layer, count in before.items():
            self.assertEqual(sample('kairos_retrieval_layer_seconds_count', layer=layer), count + 1)

    async def test_the_semantic_layer_records_its_latency_when_it_runs(self):
        app, store, auth, retrieval = fake_app()
        store.has_vectors.return_value = False
        before = sample('kairos_retrieval_layer_seconds_count', layer='semantic')
        await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic']})
        self.assertEqual(sample('kairos_retrieval_layer_seconds_count', layer='semantic'), before + 1)
        before = sample('kairos_retrieval_layer_seconds_count', layer='semantic')
        await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic'], 'semantic': False})
        self.assertEqual(sample('kairos_retrieval_layer_seconds_count', layer='semantic'), before)  # off: nothing ran

    async def test_a_failing_layer_is_measured_too(self):
        app, store, auth, retrieval = fake_app()
        store.search_items.side_effect = RuntimeError('boom')
        before = sample('kairos_retrieval_layer_seconds_count', layer='episodic')
        await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic'], 'semantic': False})
        self.assertEqual(sample('kairos_retrieval_layer_seconds_count', layer='episodic'), before + 1)

    async def test_the_responses_do_not_change(self):
        app, store, auth, retrieval = fake_app()
        store.search_items.return_value = [{'ref': 'episodic:a:i:1', 'project_id': 'a', 'item_id': 'i', 'version': 1, 'layer': 'episodic', 'title': 't', 'excerpt': 'e', 'validation_status': 'validated'}]
        result = await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic'], 'semantic': False})
        self.assertEqual([item['item_id'] for item in result['items']], ['i'])
        self.assertEqual(set(result), {'items', 'backends', 'partial'})

    async def test_a_provider_failure_counts_its_code(self):
        settings = Settings('unused')
        server_error = httpx.MockTransport(lambda request: httpx.Response(500, json={}))
        before = sample('kairos_provider_errors_total', provider='embed', code='provider_unavailable')
        with self.assertRaises(ProviderError):
            await Embeddings(settings, transport=server_error).embed('texto')
        self.assertEqual(sample('kairos_provider_errors_total', provider='embed', code='provider_unavailable'), before + 1)
        before = sample('kairos_provider_errors_total', provider='embed', code='embedding_invalid')
        wrong = httpx.MockTransport(lambda request: httpx.Response(200, json={'embeddings': [[]]}))
        with self.assertRaises(ProviderError):
            await Embeddings(settings, transport=wrong).embed('texto')
        self.assertEqual(sample('kairos_provider_errors_total', provider='embed', code='embedding_invalid'), before + 1)
        before = sample('kairos_provider_errors_total', provider='extract', code='provider_rejected')
        rejected = httpx.MockTransport(lambda request: httpx.Response(422, json={}))
        with self.assertRaises(ProviderError):
            await Ollama(settings, transport=rejected).extract({'content': 'x'})
        self.assertEqual(sample('kairos_provider_errors_total', provider='extract', code='provider_rejected'), before + 1)

    async def test_a_query_whose_budget_runs_out_during_the_embedding_counts_provider_timeout(self):
        """The layer's own plazo (semantic_budget_ms) expires before the provider's: `counted` only sees a cancellation, the layer counts it."""
        async def slow(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5]]})
        settings = Settings('unused', request_timeout=5, embedding_query_timeout=5)
        store = Mock(has_vectors=Mock(return_value=True), search_items=Mock(return_value=[]))
        retrieval = Retrieval(store, settings, Embeddings(settings, transport=httpx.MockTransport(slow)))
        before = sample('kairos_provider_errors_total', provider='embed', code='provider_timeout')
        result = await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic'], 'semantic_budget_ms': 50})
        self.assertEqual(result['degraded'], {'layer': 'semantic', 'reason': 'timeout'})
        self.assertEqual(sample('kairos_provider_errors_total', provider='embed', code='provider_timeout'), before + 1)

    async def test_the_providers_own_timeout_is_counted_once(self):
        async def slow(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5]]})
        settings = Settings('unused', request_timeout=5, embedding_query_timeout=0.05)
        store = Mock(has_vectors=Mock(return_value=True), search_items=Mock(return_value=[]))
        retrieval = Retrieval(store, settings, Embeddings(settings, transport=httpx.MockTransport(slow)))
        before = sample('kairos_provider_errors_total', provider='embed', code='provider_timeout')
        result = await retrieval.search({}, {'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic']})
        self.assertEqual(result['degraded']['reason'], 'timeout')
        self.assertEqual(sample('kairos_provider_errors_total', provider='embed', code='provider_timeout'), before + 1)

    async def test_embedding_saturation_is_measured_per_caller(self):
        seen = {}

        async def slow(request):
            seen.setdefault('in_use', sample('kairos_embedding_slots_in_use', caller='query'))
            await asyncio.sleep(0.25)
            return httpx.Response(200, json={'embeddings': [[1.0, 0.5]]})
        embeddings = Embeddings(Settings('unused'), transport=httpx.MockTransport(slow))
        before = {caller: (sample('kairos_embedding_wait_seconds_count', caller=caller), sample('kairos_embedding_wait_seconds_sum', caller=caller)) for caller in ('query', 'worker')}
        first = asyncio.create_task(embeddings.embed('consulta', query=True))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(embeddings.embed('documento'))  # waits for the single slot
        await asyncio.gather(first, second)
        self.assertEqual(seen['in_use'], 1)
        self.assertEqual(sample('kairos_embedding_slots_in_use', caller='query'), 0)
        self.assertEqual(sample('kairos_embedding_slots_in_use', caller='worker'), 0)
        self.assertEqual(sample('kairos_embedding_wait_seconds_count', caller='query'), before['query'][0] + 1)
        self.assertEqual(sample('kairos_embedding_wait_seconds_count', caller='worker'), before['worker'][0] + 1)
        self.assertGreater(sample('kairos_embedding_wait_seconds_sum', caller='worker') - before['worker'][1], 0.1)
        self.assertLess(sample('kairos_embedding_wait_seconds_sum', caller='query') - before['query'][1], 0.1)

    async def test_embed_many_counts_as_the_worker_or_the_query(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'embeddings': [[1.0, 0.5], [1.0, 0.5]]}))
        embeddings = Embeddings(Settings('unused'), transport=transport)
        before = sample('kairos_embedding_wait_seconds_count', caller='worker')
        await embeddings.embed_many(['a', 'b'])
        self.assertEqual(sample('kairos_embedding_wait_seconds_count', caller='worker'), before + 1)
        before = sample('kairos_embedding_wait_seconds_count', caller='query')
        await embeddings.embed_many(['a', 'b'], query=True)
        self.assertEqual(sample('kairos_embedding_wait_seconds_count', caller='query'), before + 1)

    async def test_the_worker_counts_a_failed_job_by_destination_and_code(self):
        from memory_platform.worker import Worker
        store = Mock()
        store.claim_job.return_value = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'project_id': 'p', 'payload': {}}
        provider = Mock(extract=AsyncMock(side_effect=ProviderError('provider_rejected')))
        before = sample('kairos_worker_jobs_total', destination='extract', outcome='failed')
        await Worker(store, Settings('unused', lease_seconds=0.3), {'extract': provider}).run_once()
        self.assertEqual(sample('kairos_worker_jobs_total', destination='extract', outcome='failed'), before + 1)
        self.assertGreaterEqual(sample('kairos_worker_job_seconds_count', destination='extract'), 1)


class WorkerDeadlineTests(unittest.IsolatedAsyncioTestCase):
    """Phase 6 debt R1: the extra single-text call is only planned when a stored item vector exists."""

    def test_the_deadline_adds_the_extra_call_only_with_a_stored_vector(self):
        from memory_platform.worker import worker_deadline, JOB_DEADLINE_MARGIN
        from memory_platform.config import embedding_job_timeout
        settings = Settings('unused')
        self.assertEqual(worker_deadline(settings, 20, stored_vector=False), embedding_job_timeout(settings, 20) + JOB_DEADLINE_MARGIN)
        self.assertEqual(worker_deadline(settings, 20, stored_vector=True),
                         embedding_job_timeout(settings, 20) + embedding_job_timeout(settings, 1) + JOB_DEADLINE_MARGIN)
        self.assertEqual(worker_deadline(settings, 1, stored_vector=True), embedding_job_timeout(settings, 1) + JOB_DEADLINE_MARGIN)

    def job_worker(self, stored, limit=0.25):
        from memory_platform.tests.test_worker import long_text
        from memory_platform.worker import Worker
        settings = Settings('unused', lease_seconds=5, embedding_worker_timeout=limit, embedding_batch_timeout=limit, embedding_job_timeout_max=limit)
        store = Mock()
        job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'embed', 'canonical_hash': 'a' * 64, 'policy': {}, 'project_id': 'p',
               'item_id': 'i', 'resource_type': 'document', 'version': 1, 'payload': {'title': 'Long note', 'content': long_text(20000)}}
        store.claim_job.return_value = job

        async def slow(texts, query=False):
            await asyncio.sleep(0.4)
            return {'embeddings': [[1.0, 0.5] for _ in texts], 'model': 'm', 'verified': True}
        provider = Mock(embed=AsyncMock(side_effect=AssertionError('unexpected')), embed_many=slow)
        patcher = patch('memory_platform.worker.stored_item_vector', return_value=stored)
        patcher.start()
        self.addCleanup(patcher.stop)
        return Worker(store, settings, {'embed': provider}), store

    async def test_without_a_stored_vector_the_job_does_not_get_the_extra_call(self):
        worker, store = self.job_worker(None)
        with patch('memory_platform.worker.JOB_DEADLINE_MARGIN', 0):
            await worker.run_once()  # 0.4 s of batches against 0.25 s: no extra call could ever use the spare time
        store.complete_job.assert_not_called()
        self.assertEqual(store.fail_job.call_args.args[2], 'provider_timeout')

    async def test_with_a_stored_vector_of_other_dimensions_the_extra_call_still_fits(self):
        """Batch call (0.35 s) plus the extra single-text call (0.35 s) take 0.7 s: over the base deadline (0.5 s), inside the extended one (1.0 s).
        It only completes because the worker `reschedule`s the deadline when a stored vector exists."""
        worker, store = self.job_worker([9.0, 9.0, 9.0], limit=0.5)

        async def single(text, query=False):
            await asyncio.sleep(0.35)
            return {'embedding': [1.0, 0.5], 'model': 'm', 'verified': True}

        async def batch(texts, query=False):
            await asyncio.sleep(0.35)
            return {'embeddings': [[1.0, 0.5] for _ in texts], 'model': 'm', 'verified': True}
        worker.providers['embed'].embed = single
        worker.providers['embed'].embed_many = batch
        with patch('memory_platform.worker.JOB_DEADLINE_MARGIN', 0):
            await worker.run_once()
        store.fail_job.assert_not_called()
        store.complete_job.assert_called_once()


def metrics_app(mode='internal'):
    store, auth = MagicMock(), Mock()
    auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer', 'is_admin': False}
    store.search_items.return_value = []
    store.search_documents.return_value = []
    store.search_native_facts.return_value = []
    retrieval = Retrieval(store, Settings('unused', request_timeout=5), Mock(embed=AsyncMock()))
    return create_app(Settings('unused', metrics_mode=mode), store, auth, retrieval), store, auth


class MetricsRouteTests(unittest.TestCase):
    def setUp(self):
        no_cache(self)

    def test_internal_access_answers_200_with_the_three_metrics(self):
        app, store, _ = metrics_app('internal')
        store.transaction.return_value = jobs_store([{'state': 'pending', 'destination': 'embed', 'n': 3}])[0].transaction.return_value
        observability.observe_layer('episodic', 0.01)
        observability.count_provider_error('embed', 'provider_unavailable')
        with TestClient(app) as client:
            response = client.get('/metrics')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers['content-type'].startswith('text/plain; version=0.0.4'), response.headers['content-type'])
        for name in ('kairos_retrieval_layer_seconds', 'kairos_provider_errors_total', 'kairos_jobs_queue_depth', 'kairos_jobs_failed', 'kairos_jobs_queue_scrape_success'):
            self.assertIn(name, response.text)
        self.assertIn('kairos_jobs_queue_depth{destination="embed",state="pending"} 3.0', response.text)

    def test_a_request_that_came_through_the_public_proxy_is_rejected(self):
        app, *_ = metrics_app('internal')
        with TestClient(app) as client:
            for header in ({'X-Forwarded-For': '203.0.113.9'}, {'X-Forwarded-Proto': 'https'}, {'X-Forwarded-Host': 'memory.example.com'},
                           {'Forwarded': 'for=203.0.113.9'}, {'X-Real-IP': '203.0.113.9'}):
                response = client.get('/metrics', headers=header)
                self.assertEqual(response.status_code, 404, header)
                self.assertNotIn('kairos_', response.text)

    def test_off_disables_the_route(self):
        app, *_ = metrics_app('off')
        with TestClient(app) as client:
            self.assertEqual(client.get('/metrics').status_code, 404)

    def test_admin_mode_requires_an_administrator(self):
        app, store, auth = metrics_app('admin')
        from memory_platform.errors import Unauthorized
        auth.authenticate_bearer.side_effect = auth.authenticate_session.side_effect = Unauthorized()
        with TestClient(app) as client:
            self.assertEqual(client.get('/metrics').status_code, 401)
            auth.authenticate_bearer.side_effect = None
            auth.authenticate_bearer.return_value = {'id': 'u', 'credential_type': 'bearer', 'is_admin': False}
            self.assertEqual(client.get('/metrics', headers={'Authorization': 'Bearer fixture'}).status_code, 403)
            auth.authenticate_bearer.return_value = {'id': 'root', 'credential_type': 'bearer', 'is_admin': True}
            response = client.get('/metrics', headers={'Authorization': 'Bearer fixture', 'X-Forwarded-For': '203.0.113.9'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('kairos_retrieval_layer_seconds', response.text)

    def test_a_database_failure_does_not_take_the_metrics_down(self):
        app, store, _ = metrics_app('internal')
        store.transaction.side_effect = RuntimeError('database down')
        with TestClient(app) as client:
            response = client.get('/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn('kairos_jobs_queue_scrape_success 0.0', response.text)

    def test_the_route_is_not_part_of_the_published_api_contract(self):
        app, *_ = metrics_app('internal')
        self.assertNotIn('/metrics', app.openapi()['paths'])

    def test_ca31_a_query_and_a_token_never_reach_the_metrics_or_the_logs(self):
        app, store, auth = metrics_app('internal')
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        with TestClient(app) as client:
            headers = {'Authorization': 'Bearer ' + SECRET}
            client.post('/v1/search', headers=headers, json={'project_ids': ['proyecto-secreto-77'], 'q': QUERY + ' ' + SECRET, 'layers': ['episodic', 'documental'], 'semantic': False})
            store.search_items.side_effect = RuntimeError(QUERY + SECRET)
            client.post('/v1/search', headers=headers, json={'project_ids': ['proyecto-secreto-77'], 'q': QUERY, 'layers': ['episodic'], 'semantic': False})
            metrics = client.get('/metrics').text
        for leaked in (QUERY, SECRET, 'proyecto-secreto-77'):
            self.assertNotIn(leaked, metrics)
            self.assertNotIn(leaked, stream.getvalue())

    def test_metrics_setting_is_read_from_the_environment_and_validated(self):
        base = {'MEMORY_DSN': 'postgresql://unused'}
        with patch.dict(os.environ, base):
            os.environ.pop('MEMORY_METRICS', None)
            self.assertEqual(Settings.from_env().metrics_mode, 'internal')
        for mode in ('off', 'internal', 'admin'):
            with patch.dict(os.environ, dict(base, MEMORY_METRICS=mode)):
                self.assertEqual(Settings.from_env().metrics_mode, mode)
        with patch.dict(os.environ, dict(base, MEMORY_METRICS='public')):
            with self.assertRaises(ValueError):
                Settings.from_env()
        with self.assertRaises(ValueError):
            Settings('unused', metrics_mode='public')


class DeploymentTests(unittest.TestCase):
    def test_nginx_never_publishes_metrics(self):
        text = (ROOT / 'web' / 'nginx.conf').read_text(encoding='utf-8')
        block = re.search(r'location\s+~\*?\s+(\S*metrics\S*)\s*\{\s*return 404;\s*\}', text)
        self.assertIsNotNone(block, 'nginx must answer 404 for /metrics and /memory-api/metrics')
        pattern = re.compile(block.group(1))
        self.assertTrue(pattern.search('/metrics') and pattern.search('/memory-api/metrics') and not pattern.search('/v1/search'))

    def test_the_host_proxy_example_blocks_metrics(self):
        text = (PACKAGE / 'Caddyfile.example').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?s)path[^\n]*metrics[^\n]*\n[^\n]*respond[^\n]*404[\s\S]*reverse_proxy')

    def test_compose_publishes_no_new_port_for_the_api_and_sets_the_mode(self):
        compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
        self.assertEqual(compose['services']['memory-api']['ports'], ['127.0.0.1:8790:8790'])
        published = [port for service in compose['services'].values() for port in service.get('ports', [])]
        self.assertEqual(sum('8790' in str(port) for port in published), 1)
        self.assertIn('internal', str(compose['services']['memory-api']['environment']['MEMORY_METRICS']))


if __name__ == '__main__':
    unittest.main()
