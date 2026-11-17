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


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()
