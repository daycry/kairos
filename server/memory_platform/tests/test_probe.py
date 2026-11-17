"""T-69 and T-70 (CA-30, CA-31, CA-33): the round-trip probe, with an injected clock (nothing in this file waits) and, for the chain, the real server over an isolated PostgreSQL.

| scenario (T-70)                | worker      | what is cut / missing              | stage that fails | code                   | retired |
|--------------------------------|-------------|------------------------------------|------------------|------------------------|---------|
| healthy                        | drains      | nothing                            | none (exit 0)    | -                      | -       |
| worker stopped                 | never runs  | the `embed` job stays pending      | index            | timeout (<= budget)    | True    |
| search without a result        | drains      | the note is retired meanwhile      | search           | no_result              | True    |
| database cut (before / during) | -           | the proxy between server and DB    | write / index    | server_error           | False   |
| server answers 401             | -           | a revoked key                      | write            | unauthorized           | None    |

The scenarios of the first half use a scripted `/v1` (`FakeServer`); the second half runs the same `Probe` against the real application, with the key `provision` makes and a `Worker` over `FakeEmbeddings`.
"""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from memory_platform import admin, observability, probe
from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform.config import Settings
from memory_platform.retrieval import Retrieval
from memory_platform.store import Store
from memory_platform.store_pool import attach_pool, close_pool
from memory_platform.tests.fault_proxy import FaultProxy
from memory_platform.tests.retrieval_eval.fake_embeddings import FakeEmbeddings
from memory_platform.tests.test_probe_provisioning import ORIGIN, ROOT, ClientApi, IsolatedDatabase, settings_for
from memory_platform.worker import Worker


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    def sleep(self, seconds):
        self.advance(seconds)


class FakeServer:
    """`/v1` as the probe sees it, scripted. Every request costs `costs[kind]` seconds of the injected clock; `polls_before_done` status reads see the job pending (None: for ever)."""
    COSTS = {'write': 0.1, 'status': 0.05, 'search': 0.3, 'delete': 0.2}

    def __init__(self, clock, **options):
        self.clock = clock
        self.options = dict({'write_status': 202, 'polls_before_done': 2, 'job_state': 'succeeded', 'embed_jobs': True, 'found': True, 'semantic': 'ok', 'delete_status': 202,
                             'still_active': False, 'status_code': 200, 'raises': None, 'delete_statuses': None}, **options)
        self.requests, self.polls, self.item_id = [], 0, None

    def call(self, method, path, body=None, timeout=None):
        o = self.options
        kind = 'write' if (method, path) == ('POST', '/v1/events') and body['event_type'] == 'note' else 'delete' if path == '/v1/events' else 'search' if path == '/v1/search' else 'status'
        self.requests.append((kind, body, timeout))
        self.clock.advance(self.COSTS[kind])
        if o['raises'] and o['raises'][0] == kind:
            raise o['raises'][1]
        if kind == 'write':
            self.item_id = body['item_id']
            return o['write_status'], ({'jobs': ['j1'], 'status': 'accepted'} if o['write_status'] in (200, 202) else {'error': {'code': 'x\x1b[31mcontrol'}})
        if kind == 'status':
            self.polls += 1
            done = o['polls_before_done'] is not None and self.polls > o['polls_before_done']
            jobs = [{'id': 'j1', 'destination': 'embed' if o['embed_jobs'] else 'extract', 'state': o['job_state'] if done else 'pending'}]
            return o['status_code'], {'found': True, 'jobs': jobs, 'complete': done}
        if kind == 'delete':
            statuses = o['delete_statuses']
            status = statuses.pop(0) if statuses else o['delete_status']
            return status, {'status': 'accepted'}
        lexical = body.get('semantic') is False
        items = [{'item_id': self.item_id}] if (o['found'] and not lexical) or (lexical and o['still_active']) else []
        return 200, {'items': items, 'backends': {'semantic': {'status': o['semantic'], 'count': len(items) if o['semantic'] == 'ok' else 0}}}

    def kinds(self):
        return [kind for kind, _, _ in self.requests]


def run(server, clock, timeout=120.0, poll=2.0):
    return probe.Probe(server, timeout=timeout, poll=poll, clock=clock, sleep=clock.sleep).run()


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        # The real clock and sleep must never be reached: a run that waits for real would hang the suite. Only the probe's own reference to `time` is replaced.
        def forbidden(name):
            def refuse(*arguments):
                raise AssertionError('the probe used the real time.' + name)
            return refuse
        patcher = patch('memory_platform.probe.time', SimpleNamespace(monotonic=forbidden('monotonic'), sleep=forbidden('sleep')))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_healthy_server_ends_ok_and_every_stage_has_its_duration(self):
        server = FakeServer(self.clock)
        report = run(server, self.clock)
        self.assertEqual((report['status'], report['kairos_probe_success']), ('probe_ok', 1))
        # write 0.1; index: 3 reads of 0.05 and 2 sleeps of 2.0; search 0.3; retire: a delete of 0.2 and a lexical search of 0.3 (the same cost as any search).
        self.assertEqual(report['stages'], {'write': 0.1, 'index': 4.15, 'search': 0.3, 'retire': 0.5})
        self.assertEqual(server.kinds(), ['write', 'status', 'status', 'status', 'search', 'delete', 'search'])
        self.assertEqual(report['total_seconds'], 5.05)
        self.assertNotIn('stage', report)

    def test_the_durations_become_the_series_of_the_probe_and_a_failure_sets_success_to_zero(self):
        observability.record_probe(True, {'write': 1.5}, now=5)
        stages = run(FakeServer(self.clock), self.clock)['stages']
        observability.record_probe(True, stages, now=7)
        series = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value for family in text_string_to_metric_families(observability.render_probe_metrics().decode())
                  for sample in family.samples}
        self.assertEqual(series[('kairos_probe_success', ())], 1)
        self.assertEqual({label[0][1]: value for (name, label), value in series.items() if name == 'kairos_probe_stage_seconds'}, stages)
        self.assertEqual(series[('kairos_probe_last_run_timestamp_seconds', ())], 7)
        server = FakeServer(self.clock, write_status=500)
        failed = probe.run_probe(server, 120.0, clock=self.clock, sleep=self.clock.sleep)
        text = observability.render_probe_metrics().decode()
        self.assertIn('kairos_probe_success 0.0', text)
        self.assertNotIn('stage="index"', text)  # a stage that did not run has no series
        self.assertEqual(failed['stage'], 'write')

    def test_with_the_worker_stopped_it_fails_at_index_within_the_budget_and_tries_to_retire(self):
        server = FakeServer(self.clock, polls_before_done=None)
        report = run(server, self.clock, timeout=30.0)
        self.assertEqual((report['status'], report['stage'], report['code'], report['kairos_probe_success']), ('probe_failed', 'index', 'timeout', 0))
        self.assertLessEqual(report['stages']['index'], 30.0)
        self.assertLessEqual(report['stages']['write'] + report['stages']['index'], 30.0 + FakeServer.COSTS['write'])  # the budget runs from the first request
        self.assertIs(report['retired'], True)
        self.assertEqual(server.kinds()[-2:], ['delete', 'search'])  # the retirement and its check
        self.assertNotIn('search', server.kinds()[:-1])  # the semantic search was never reached
        deleted = [body for kind, body, _ in server.requests if kind == 'delete']
        self.assertEqual([(b['event_type'], b['version'], b['item_id']) for b in deleted], [('delete', 2, server.item_id)])

    def test_every_request_is_bounded_by_what_is_left_of_the_budget(self):
        server = FakeServer(self.clock, polls_before_done=None)
        run(server, self.clock, timeout=7.0)
        timeouts = [timeout for kind, _, timeout in server.requests if kind in ('write', 'status')]
        self.assertTrue(all(0 < timeout <= 7.0 for timeout in timeouts), timeouts)
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))  # the budget only shrinks

    def test_each_failure_names_its_stage_and_code_and_retires_what_it_wrote(self):
        cases = [
            ('write refused', {'write_status': 422}, ('write', 'rejected'), None),
            ('write unauthorized', {'write_status': 401}, ('write', 'unauthorized'), None),
            ('write server error may have landed', {'write_status': 503}, ('write', 'server_error'), True),
            ('no embed job', {'embed_jobs': False}, ('index', 'no_embed_job'), True),
            ('job failed', {'job_state': 'failed'}, ('index', 'job_failed'), True),
            ('status server error', {'status_code': 502}, ('index', 'server_error'), True),
            ('no result', {'found': False}, ('search', 'no_result'), True),
            ('lexical only', {'semantic': 'unavailable'}, ('search', 'semantic_unavailable'), True),
            ('still active', {'still_active': True}, ('retire', 'still_active'), False),
            ('retire refused', {'delete_status': 403}, ('retire', 'unauthorized'), False),
        ]
        for name, options, expected, retired in cases:
            with self.subTest(name):
                clock = Clock()
                server = FakeServer(clock, **options)
                report = probe.Probe(server, timeout=60.0, poll=1.0, clock=clock, sleep=clock.sleep).run()
                self.assertEqual((report['status'], report['stage'], report['code']), ('probe_failed',) + expected)
                self.assertEqual(report['kairos_probe_success'], 0)
                self.assertIs(report['retired'], retired)
                self.assertIn(report['stage'], report['stages'])

    def test_a_write_that_may_not_have_landed_is_retired_at_version_two_then_one(self):
        server = FakeServer(self.clock, write_status=503, delete_statuses=[409, 202])
        report = run(server, self.clock)
        self.assertEqual((report['stage'], report['retired']), ('write', True))
        self.assertEqual([b['version'] for kind, b, _ in server.requests if kind == 'delete'], [2, 1])

    def test_a_transport_error_reports_its_type_and_never_its_message(self):
        secret = 'Bearer mp_SECRET-TOKEN at postgresql://user:pass@host/db'
        for stage in ('write', 'status', 'search'):
            with self.subTest(stage):
                clock = Clock()
                server = FakeServer(clock, raises=(stage, ConnectionError(secret)))
                report = probe.Probe(server, timeout=60.0, poll=1.0, clock=clock, sleep=clock.sleep).run()
                self.assertEqual((report['code'], report['error_type']), ('unreachable', 'ConnectionError'))
                self.assertNotIn('SECRET', json.dumps(report))
                self.assertNotIn('pass', json.dumps(report))

    def test_what_the_peer_sends_never_reaches_the_report(self):
        """CWE-150: the 422 body of FakeServer carries an ESC sequence in its error code: only the status and the closed codes of the probe come out."""
        report = run(FakeServer(self.clock, write_status=422), self.clock)
        text = json.dumps(report)
        self.assertNotIn('control', text)
        self.assertNotIn('\\u001b', text)
        self.assertEqual(report['http_status'], 422)
        self.assertLessEqual(set(report['stages']), set(probe.STAGES))
        self.assertIn(report['code'], probe.CODES)

    def test_the_timeout_setting_is_a_number_of_seconds_in_range(self):
        self.assertEqual(probe.probe_timeout({}), 120.0)
        self.assertEqual(probe.probe_timeout({'MEMORY_PROBE_TIMEOUT': '5'}), 5.0)
        for bad in ('abc', '0', '-3', 'nan', 'inf', '99999', '0.5'):
            with self.subTest(bad), self.assertRaises(probe.ProbeError) as raised:
                probe.probe_timeout({'MEMORY_PROBE_TIMEOUT': bad})
            self.assertEqual(raised.exception.code, 'timeout_invalid')

    def test_the_url_is_an_origin_with_no_credentials_path_or_query(self):
        self.assertEqual(probe.probe_url({}), probe.DEFAULT_URL)
        self.assertEqual(probe.probe_url({'MEMORY_PROBE_URL': 'http://memory-api:8790/'}), 'http://memory-api:8790')
        for bad in ('ftp://x', 'http://user:pw@x', 'http://x/path', 'http://x?q=1', 'memory-api:8790', 'http://'):
            with self.subTest(bad), self.assertRaises(probe.ProbeError):
                probe.probe_url({'MEMORY_PROBE_URL': bad})


class HttpApiTests(unittest.TestCase):
    """The real transport of `admin probe` (`HttpApi`, httpx) against a stub server on the loopback of the test container: what it sends, what it refuses to follow and how it fails."""

    def setUp(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        seen = self.seen = []

        class Handler(BaseHTTPRequestHandler):
            def reply(handler, status, body=b'', headers=()):
                handler.send_response(status)
                for name, value in headers:
                    handler.send_header(name, value)
                handler.send_header('Content-Length', str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)

            def serve(handler):
                length = int(handler.headers.get('Content-Length') or 0)
                body = handler.rfile.read(length) if length else b''
                seen.append((handler.command, handler.path, handler.headers.get('Authorization'), body))
                if handler.path == '/redirect':
                    handler.reply(302, headers=[('Location', 'http://127.0.0.1:%d/stolen' % handler.server.server_address[1])])
                elif handler.path == '/text':
                    handler.reply(200, b'not json')
                elif handler.path == '/list':
                    handler.reply(200, b'[1, 2]', [('Content-Type', 'application/json')])
                else:
                    handler.reply(202, body or b'{"ok": true}', [('Content-Type', 'application/json')])
            do_GET = do_POST = serve

            def log_message(handler, *arguments):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:%d' % self.server.server_address[1]
        self.api = probe.HttpApi(self.url, 'mp_token-under-test')
        self.addCleanup(self.api.close)

    def test_it_sends_the_bearer_and_the_json_body_and_returns_status_and_object(self):
        status, data = self.api.call('POST', '/echo', {'a': 1}, 5.0)
        self.assertEqual((status, data), (202, {'a': 1}))
        self.assertEqual(self.seen, [('POST', '/echo', 'Bearer mp_token-under-test', b'{"a":1}')])

    def test_a_redirect_is_not_followed_so_the_token_goes_only_to_the_configured_url(self):
        status, data = self.api.call('GET', '/redirect')
        self.assertEqual((status, data), (302, None))
        self.assertEqual([path for _, path, _, _ in self.seen], ['/redirect'])

    def test_an_answer_that_is_not_a_json_object_is_none(self):
        self.assertEqual(self.api.call('GET', '/text'), (200, None))
        self.assertEqual(self.api.call('GET', '/list'), (200, None))

    def test_a_refused_connection_is_an_unreachable_stage_with_the_exception_type_only(self):
        import socket
        with socket.socket() as closed:
            closed.bind(('127.0.0.1', 0))
            port = closed.getsockname()[1]
        report = probe.Probe(probe.HttpApi('http://127.0.0.1:%d' % port, 'mp_token-under-test'), timeout=5.0, poll=1.0, clock=Clock(), sleep=lambda seconds: None).run()
        self.assertEqual((report['stage'], report['code'], report['error_type'], report['retired']), ('write', 'unreachable', 'ConnectError', False))  # it tried to retire what a dead request may have written
        self.assertNotIn('mp_token', json.dumps(report))


class CommandTests(unittest.TestCase):
    """`admin probe` end to end with the metrics file: the exit code, the report and what reaches the terminal."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.metrics = self.directory / 'kairos-probe.prom'
        self.key = self.directory / 'kairos-probe.key'
        self.addCleanup(observability.remove_logging)  # `admin probe` configures the JSON logs of the process

    def command(self, *arguments, api=None, environ=None):
        out, err = io.StringIO(), io.StringIO()
        factory = (lambda url, token: api) if api is not None else probe.HttpApi
        with patch.dict(os.environ, environ or {}, clear=False), patch.object(probe, 'HttpApi', factory), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                admin.main(['probe', '--metrics-file', str(self.metrics), '--key-file', str(self.key)] + list(arguments))
                code = 0
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    def test_a_missing_key_file_is_a_failure_at_setup_with_success_zero_in_the_file_and_no_request(self):
        code, out, _ = self.command(api=object())
        self.assertEqual(code, 'probe_failed: stage=setup code=key_unreadable')
        report = json.loads(out)
        self.assertEqual((report['status'], report['stage'], report['code'], report['kairos_probe_success']), ('probe_failed', 'setup', 'key_unreadable', 0))
        self.assertIn('kairos_probe_success 0.0', self.metrics.read_text(encoding='utf-8'))

    def test_a_bad_timeout_or_url_fails_at_setup_too(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        for environ, expected in (({'MEMORY_PROBE_TIMEOUT': '0'}, 'timeout_invalid'), ({'MEMORY_PROBE_URL': 'http://x/y'}, 'url_invalid')):
            with self.subTest(expected):
                code, _, _ = self.command(api=object(), environ=environ)
                self.assertEqual(code, 'probe_failed: stage=setup code=' + expected)

    def test_a_healthy_run_exits_zero_prints_the_report_and_writes_the_series(self):
        self.key.write_text('mp_not-printed\n', encoding='utf-8')
        clock = Clock()
        server = FakeServer(clock)
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):
            code, out, err = self.command(api=server)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['status'], 'probe_ok')
        text = self.metrics.read_text(encoding='utf-8')
        self.assertIn('kairos_probe_success 1.0', text)
        for stage in probe.STAGES:
            self.assertIn('kairos_probe_stage_seconds{stage="%s"}' % stage, text)
        self.assertNotIn('not-printed', out + err + text)

    def test_a_failed_run_exits_nonzero_with_probe_failed_stage_and_the_log_line(self):
        self.key.write_text('mp_not-printed\n', encoding='utf-8')
        clock = Clock()
        server = FakeServer(clock, polls_before_done=None)
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch.dict(os.environ, {'MEMORY_PROBE_TIMEOUT': '10'}):
            code, out, err = self.command(api=server)
        self.assertEqual(code, 'probe_failed: stage=index code=timeout')
        self.assertEqual(json.loads(out)['retired'], True)
        self.assertIn('kairos_probe_success 0.0', self.metrics.read_text(encoding='utf-8'))
        lines = [json.loads(line) for line in err.splitlines() if line.startswith('{')]
        self.assertEqual([(line['event'], line['level'], line['stage'], line['code']) for line in lines], [('probe_failed', 'error', 'index', 'timeout')])
        self.assertNotIn('not-printed', err)
        self.assertIn('stage', observability.FIELDS)


class ChainTests(IsolatedDatabase, unittest.TestCase):
    """The probe against the real application over its own database; the worker is the real `Worker` over the deterministic embeddings, run only where a test lets time pass."""

    def setUp(self):
        self.clock = Clock()
        self.store = self.make_store()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.key_file = Path(directory.name) / 'kairos-probe.key'
        probe.provision(self.store, self.key_file)
        self.token = self.key_file.read_text(encoding='utf-8').strip()
        self.settings = settings_for()
        self.worker = Worker(self.store, self.settings, {'embed': FakeEmbeddings(self.settings)}, worker_id='probe-chain')
        self.app = self.make_app(self.store)
        self.client = TestClient(self.app, base_url=ORIGIN, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.api = ClientApi(self.client, self.token)

    def drain(self):
        async def work():
            while await self.worker.run_once():
                pass
        asyncio.run(work())

    def sleep_while_the_worker_runs(self, seconds):
        self.drain()
        self.clock.advance(seconds)

    def probe(self, sleep=None, timeout=60.0, api=None):
        return probe.Probe(api or self.api, timeout=timeout, poll=2.0, clock=self.clock, sleep=sleep or self.clock.sleep).run()

    def rows(self, sql, *parameters, store=None):
        with (store or self.store).transaction() as c:
            return c.execute(sql, parameters).fetchall()

    def memories(self):
        """(active, retired) notes of the probe project."""
        counts = self.rows("SELECT deleted,count(*) AS n FROM memory.memory_items WHERE project_id=%s GROUP BY deleted", probe.PROBE_PROJECT)
        by = {row['deleted']: row['n'] for row in counts}
        return by.get(False, 0), by.get(True, 0)

    def embed_states(self):
        return [row['state'] for row in self.rows("SELECT state FROM memory.jobs WHERE project_id=%s AND destination='embed' ORDER BY created_at", probe.PROBE_PROJECT)]

    def test_healthy_the_note_goes_through_the_worker_and_is_found_semantically_then_retired(self):
        report = self.probe(self.sleep_while_the_worker_runs)
        self.assertEqual((report['status'], report.get('stage')), ('probe_ok', None), report)
        self.assertEqual(set(report['stages']), set(probe.STAGES))
        self.assertEqual(self.memories(), (0, 1))  # CA-33: no active memory is left, one retired
        self.assertEqual(self.embed_states(), ['succeeded'])

    def test_run_after_run_leaves_no_active_memory_and_one_retired_per_run(self):
        for _ in range(3):
            self.assertEqual(self.probe(self.sleep_while_the_worker_runs)['status'], 'probe_ok')
        self.assertEqual(self.memories(), (0, 3))

    def test_with_the_worker_stopped_it_fails_at_index_in_the_budget_and_retires_the_note(self):
        report = self.probe(self.clock.sleep, timeout=20.0)
        self.assertEqual((report['status'], report['stage'], report['code'], report['retired']), ('probe_failed', 'index', 'timeout', True), report)
        self.assertLessEqual(report['stages']['index'], 20.0)
        self.assertEqual(self.memories(), (0, 1))  # retired even though nothing was ever indexed
        self.assertEqual(self.embed_states(), ['pending'])  # the worker never ran

    def test_a_note_retired_meanwhile_is_not_found_by_the_search(self):
        retire = {}

        class Meddling(ClientApi):
            def call(inner, method, path, body=None, timeout=None):
                answer = ClientApi.call(inner, method, path, body, timeout)
                if method == 'GET' and path.endswith('/status') and answer[1] and answer[1].get('complete') and not retire:  # a second client retires the note before the probe searches
                    note = next(r for r in self.rows("SELECT id,project_id FROM memory.memory_items WHERE project_id=%s AND NOT deleted", probe.PROBE_PROJECT))
                    retire['status'] = ClientApi.call(inner, 'POST', '/v1/events', {'event_id': str(uuid.uuid4()), 'project_id': probe.PROBE_PROJECT, 'session_id': 's', 'agent_id': 'a',
                                                       'event_type': 'delete', 'occurred_at': '2026-11-17T10:00:00Z', 'item_id': note['id'], 'version': 2, 'generate': False,
                                                       'payload': {'title': 'x', 'content': 'x'}})[0]
                return answer
        # The meddling happens after the status read that sees the job `succeeded`, so the note is already indexed and live.
        api = Meddling(self.client, self.token)
        report = self.probe(self.sleep_while_the_worker_runs, api=api)
        self.assertEqual(retire.get('status'), 202)
        self.assertEqual((report['stage'], report['code']), ('search', 'no_result'), report)
        self.assertIs(report['retired'], False)  # the probe's own retirement found the version taken (409): reported, not hidden
        self.assertEqual(self.memories(), (0, 1))

    def test_a_revoked_key_fails_at_write_with_nothing_to_retire(self):
        key_id = self.rows('SELECT id FROM memory.api_keys WHERE revoked_at IS NULL')[0]['id']
        self.store.revoke_key(self.actor, key_id)
        report = self.probe()
        self.assertEqual((report['stage'], report['code'], report['http_status'], report['retired']), ('write', 'unauthorized', 401, None))
        self.assertEqual(self.memories(), (0, 0))

    def test_a_server_without_embeddings_fails_at_index_with_no_embed_job(self):
        self.store.embedding_enabled = False  # what MEMORY_EMBED_ENABLED=0 gives the API process
        report = self.probe()
        self.assertEqual((report['stage'], report['code']), ('index', 'no_embed_job'), report)
        self.assertEqual(self.memories(), (0, 1))


class CutDatabaseTests(IsolatedDatabase, unittest.TestCase):
    """The database behind a `FaultProxy` (CA-34): the probe says where it stopped."""

    def setUp(self):
        self.clock = Clock()
        direct = self.make_store()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_file = Path(directory.name) / 'kairos-probe.key'
        probe.provision(direct, key_file)
        self.direct, self.token = direct, key_file.read_text(encoding='utf-8').strip()
        self.proxy = FaultProxy().start()
        self.addCleanup(self.proxy.stop)
        self.store = Store(self.proxy.dsn(direct.dsn), embedding_enabled=True)
        attach_pool(self.store, Settings('unused', pool_min=1, pool_max=2, pool_timeout=0.5, connect_timeout=2, statement_timeout_ms=2000), 'api')
        self.addCleanup(close_pool, self.store)
        self.client = TestClient(self.make_app(self.store), base_url=ORIGIN, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.api = ClientApi(self.client, self.token)

    def active(self):
        with self.direct.transaction() as c:
            return c.execute('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND NOT deleted', (probe.PROBE_PROJECT,)).fetchone()['n']

    def test_a_cut_database_before_the_probe_fails_at_write_and_the_retirement_fails_too(self):
        self.assertEqual(self.api.call('GET', '/v1/projects')[0], 200)  # warm: the pool holds a connection that dies with the cut
        self.proxy.cut()
        report = probe.Probe(self.api, timeout=30.0, poll=1.0, clock=self.clock, sleep=self.clock.sleep).run()
        self.assertEqual((report['stage'], report['code'], report['http_status']), ('write', 'server_error', 503), report)
        self.assertIs(report['retired'], False)  # it tried (a 503 may have landed) and the database was still cut
        self.assertEqual(self.active(), 0)

    def test_a_database_cut_while_it_waits_for_the_index_fails_at_index_and_leaves_the_note_active_and_says_so(self):
        def cut_then_wait(seconds):
            self.proxy.cut()
            self.clock.advance(seconds)
        report = probe.Probe(self.api, timeout=30.0, poll=1.0, clock=self.clock, sleep=cut_then_wait).run()
        self.assertEqual((report['stage'], report['code']), ('index', 'server_error'), report)
        self.assertIs(report['retired'], False)  # reported, not hidden: this is the one case in which a note stays active
        self.assertEqual(self.active(), 1)
        self.proxy.restore()


class IsolationTests(unittest.TestCase):
    """CA-33: nothing of the probe points at the installed project's resources or at the host's Ollama."""

    FILES = ('probe.py', 'admin.py', 'observability.py', 'tests/test_probe.py', 'tests/test_probe_provisioning.py')
    FORBIDDEN = ('knowledge' + '-graphs-', 'knowledge' + '_graphs_', '114' + '34')  # split: this file names them only to forbid them

    def test_no_file_of_the_probe_names_a_resource_of_the_installation_or_the_host_ollama(self):
        base = ROOT / 'server' / 'memory_platform'
        for name in self.FILES:
            text = (base / name).read_text(encoding='utf-8')
            for forbidden in self.FORBIDDEN:
                with self.subTest(file=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)

    def test_the_default_url_is_the_service_name_of_the_compose_network_not_a_host_port(self):
        self.assertEqual(probe.DEFAULT_URL, 'http://memory-api:8790')
        self.assertNotIn('localhost', probe.DEFAULT_URL)

    def test_the_tests_database_is_not_a_database_of_the_installation(self):
        dsn = os.getenv('MEMORY_TEST_DSN', '')
        for forbidden in self.FORBIDDEN:
            self.assertNotIn(forbidden, dsn)


class MutantTests(IsolatedDatabase, unittest.TestCase):
    """The checks above fail when a control is removed (T-70, second criterion): each mutant is a patched `Probe` and the assertion that must catch it."""

    def setUp(self):
        self.clock = Clock()
        self.store = self.make_store()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key_file = Path(directory.name) / 'kairos-probe.key'
        probe.provision(self.store, key_file)
        self.settings = settings_for()
        self.worker = Worker(self.store, self.settings, {'embed': FakeEmbeddings(self.settings)}, worker_id='probe-mutant')
        self.client = TestClient(self.make_app(self.store), base_url=ORIGIN, raise_server_exceptions=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.api = ClientApi(self.client, key_file.read_text(encoding='utf-8').strip())

    def active(self):
        with self.store.transaction() as c:
            return c.execute('SELECT count(*) AS n FROM memory.memory_items WHERE project_id=%s AND NOT deleted', (probe.PROBE_PROJECT,)).fetchone()['n']

    def drain_and_advance(self, seconds):
        async def work():
            while await self.worker.run_once():
                pass
        asyncio.run(work())
        self.clock.advance(seconds)

    def test_mutant_without_the_final_retirement_leaves_an_active_memory_which_the_healthy_check_reports(self):
        with patch.object(probe.Probe, 'retire', lambda self, started, state, versions=(2,): None):
            report = probe.Probe(self.api, timeout=60.0, poll=2.0, clock=self.clock, sleep=self.drain_and_advance).run()
        self.assertEqual(report['status'], 'probe_ok')  # the probe itself cannot tell...
        self.assertEqual(self.active(), 1)  # ...and `ChainTests.test_healthy_*` asserts (0, 1): it would be red

    def test_mutant_without_the_cleanup_after_a_failure_leaves_the_note_the_stopped_worker_check_reports(self):
        with patch.object(probe.Probe, 'clean_up', lambda self, state, stage: None):
            report = probe.Probe(self.api, timeout=10.0, poll=2.0, clock=self.clock, sleep=self.clock.sleep).run()
        self.assertEqual((report['stage'], report.get('retired')), ('index', None))  # `retired` is the field the stopped-worker check asserts to be True
        self.assertEqual(self.active(), 1)

    def test_mutant_without_the_index_control_passes_with_the_worker_stopped_which_the_stopped_worker_check_reports(self):
        with patch.object(probe.Probe, 'index', lambda self, started, state: None):
            report = probe.Probe(self.api, timeout=10.0, poll=2.0, clock=self.clock, sleep=self.clock.sleep).run()
        self.assertEqual(report['stage'] if report['status'] == 'probe_failed' else 'ok', 'search')  # it only trips later, at a stage that is not `index`
        self.assertEqual([request for request in self.api.requests if request[1].endswith('/status')], [])

    def test_a_lexical_only_answer_is_not_a_semantic_hit(self):
        # The embed job ran, but the search layer is told embeddings are off: the lexical layer still finds the note.
        off = Retrieval(self.store, Settings('unused', request_timeout=30.0, embed_enabled=False), FakeEmbeddings(self.settings))
        client = TestClient(create_app(settings_for(), store=self.store, auth=Auth(self.store, [ORIGIN]), retrieval=off), base_url=ORIGIN, raise_server_exceptions=False)
        with client:
            api = ClientApi(client, self.api.headers['Authorization'][7:])
            report = probe.Probe(api, timeout=60.0, poll=2.0, clock=self.clock, sleep=self.drain_and_advance).run()
        self.assertEqual((report['stage'], report['code']), ('search', 'semantic_unavailable'), report)


if __name__ == '__main__':
    unittest.main()
