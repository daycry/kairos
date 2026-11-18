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
import signal
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
    COSTS = {'write': 0.1, 'status': 0.05, 'search': 0.3, 'delete': 0.2, 'sweep': 0.3, 'control': 0.3}

    def __init__(self, clock, **options):
        self.clock = clock
        self.options = dict({'write_status': 202, 'polls_before_done': 2, 'job_state': 'succeeded', 'embed_jobs': True, 'found': True, 'semantic': 'ok', 'delete_status': 202,
                             'still_active': False, 'status_code': 200, 'raises': None, 'delete_statuses': None, 'leftovers': [], 'foreign': False, 'control_finds': False,
                             'hang_deletes': False}, **options)
        self.requests, self.polls, self.item_id = [], 0, None

    def call(self, method, path, body=None, timeout=None):
        o = self.options
        kind = 'write' if (method, path) == ('POST', '/v1/events') and body['event_type'] == 'note' else 'delete' if path == '/v1/events' else 'status'
        if path == '/v1/search':  # the sweep that starts a run, the semantic search, its lexical control, and the lexical check of the retirement
            kind = 'sweep' if body['q'] == probe.SWEEP_QUERY else 'control' if body['semantic'] is False and body['q'].startswith('sq') else 'search'
        self.requests.append((kind, body, timeout))
        self.clock.advance(timeout if kind == 'delete' and o['hang_deletes'] else self.COSTS[kind])
        if o['raises'] and o['raises'][0] == kind and not getattr(self, 'raised', False):
            self.raised = True  # once: the retirement that follows must be able to answer
            raise o['raises'][1]
        if kind == 'write':
            self.item_id = body['item_id']
            return o['write_status'], ({'jobs': ['j1'], 'status': 'accepted'} if o['write_status'] in (200, 202) else {'error': {'code': 'x\x1b[31mcontrol'}})
        if kind == 'status':
            self.polls += 1
            done = o['polls_before_done'] is not None and self.polls > o['polls_before_done']
            jobs = [{'id': 'j1', 'destination': 'embed' if o['embed_jobs'] else 'extract', 'state': o['job_state'] if done else 'pending'}]
            return o['status_code'], {'found': True, 'jobs': jobs, 'complete': done}
        if kind == 'sweep':
            return 200, {'items': [dict(left) for left in o['leftovers']], 'backends': {}}
        if kind == 'delete':
            statuses = o['delete_statuses']
            status = statuses.pop(0) if statuses else o['delete_status']
            return status, {'status': 'accepted'}
        lexical = body.get('semantic') is False
        item = {'item_id': 'somebody-elses-note' if o['foreign'] else self.item_id}
        items = [item] if (o['found'] and not lexical) or (lexical and (o['still_active'] if kind == 'search' else o['control_finds'])) else []
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
        # sweep 0.3 (outside the stages); write 0.1; index: 3 reads of 0.05 and 2 sleeps of 2.0; search: the semantic one and its control, 0.3 each; retire: a delete of 0.2 and a lexical search of 0.3.
        self.assertEqual(report['stages'], {'write': 0.1, 'index': 4.15, 'search': 0.6, 'retire': 0.5})
        self.assertEqual(server.kinds(), ['sweep', 'write', 'status', 'status', 'status', 'search', 'control', 'delete', 'search'])
        self.assertEqual(report['total_seconds'], 5.65)
        self.assertEqual(report['swept'], 0)
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
        self.assertLessEqual(FakeServer.COSTS['sweep'] + report['stages']['write'] + report['stages']['index'], 30.0 + FakeServer.COSTS['write'])  # the budget runs from the first request, the sweep included
        self.assertIs(report['retired'], True)
        self.assertEqual(server.kinds()[-2:], ['delete', 'search'])  # the retirement and its check
        self.assertNotIn('control', server.kinds())  # the semantic search was never reached
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

    # -- fix1 of the review of phase 11 (items 1, 4, 10, 12) --------------------------------------------------------------------------

    def test_a_semantic_answer_that_names_somebody_elses_note_is_not_this_runs_hit(self):
        """The false green of the review: the answer carries a semantic hit (another probe's note, or an active leftover) but not THIS run's note."""
        server = FakeServer(self.clock, foreign=True)
        report = run(server, self.clock)
        self.assertEqual((report['status'], report['stage'], report['code']), ('probe_failed', 'search', 'no_result'))
        self.assertEqual(report['kairos_probe_success'], 0)
        self.assertNotIn('control', server.kinds())

    def test_a_note_the_lexical_control_also_finds_is_not_called_a_semantic_hit(self):
        """The query shares no word with the note, so the semantic layer off must find nothing: when it does, the two paths cannot be told apart."""
        report = run(FakeServer(self.clock, control_finds=True), self.clock)
        self.assertEqual((report['stage'], report['code']), ('search', 'semantic_unavailable'))

    def test_the_semantic_query_shares_no_word_with_the_note(self):
        server = FakeServer(self.clock)
        run(server, self.clock)
        semantic = [body for kind, body, _ in server.requests if kind == 'search' and body['semantic']]
        note = next(body for kind, body, _ in server.requests if kind == 'write')
        self.assertEqual(len(semantic), 1)
        words = set((note['payload']['title'] + ' ' + note['payload']['content']).lower().replace('.', '').split())
        self.assertTrue(set(semantic[0]['q'].split()).isdisjoint(words))

    def test_every_run_has_a_marker_of_its_own_in_the_note_and_in_both_queries(self):
        first, second = FakeServer(self.clock), FakeServer(self.clock)
        run(first, self.clock)
        run(second, self.clock)

        def markers(server):
            note = next(body for kind, body, _ in server.requests if kind == 'write')
            return note['item_id'], [body['q'] for kind, body, _ in server.requests if kind in ('search', 'control')]
        (item_a, queries_a), (item_b, queries_b) = markers(first), markers(second)
        self.assertNotEqual(item_a, item_b)
        self.assertTrue(set(queries_a).isdisjoint(queries_b))

    def test_the_run_starts_by_retiring_the_active_notes_an_earlier_run_left(self):
        server = FakeServer(self.clock, leftovers=[{'item_id': 'old-1', 'version': 1}, {'item_id': 'old-2', 'version': 3}])
        report = run(server, self.clock)
        self.assertEqual((report['status'], report['swept']), ('probe_ok', 2))
        sweeps = [(body['item_id'], body['event_type'], body['version']) for kind, body, _ in server.requests if kind == 'delete' and body['item_id'].startswith('old-')]
        self.assertEqual(sweeps, [('old-1', 'delete', 2), ('old-2', 'delete', 4)])
        self.assertEqual(server.kinds()[:4], ['sweep', 'delete', 'delete', 'write'])

    def test_a_sweep_that_fails_does_not_stop_the_run_and_the_write_tells_the_truth(self):
        server = FakeServer(self.clock, raises=('sweep', ConnectionError('down')))
        report = run(server, self.clock)
        self.assertEqual((report['status'], report['swept']), ('probe_ok', 0))

    def test_ctrl_c_in_the_middle_ends_with_the_note_retired_and_success_zero(self):
        for stage in ('write', 'status', 'search'):
            with self.subTest(stage):
                clock = Clock()
                server = FakeServer(clock, raises=(stage, KeyboardInterrupt()))
                report = probe.Probe(server, timeout=60.0, poll=1.0, clock=clock, sleep=clock.sleep).run()
                self.assertEqual((report['status'], report['code'], report['kairos_probe_success']), ('probe_failed', 'interrupted', 0))
                self.assertEqual(report['error_type'], 'KeyboardInterrupt')
                if stage != 'write':
                    self.assertIs(report['retired'], True)
                    self.assertIn('delete', server.kinds())

    def test_an_unexpected_exception_is_an_internal_error_with_the_retirement_tried(self):
        def break_the_probe(self_, started, state):
            raise ZeroDivisionError('secret mp_token in a message')
        with patch.object(probe.Probe, 'index', break_the_probe):
            server = FakeServer(self.clock)
            report = run(server, self.clock)
        self.assertEqual((report['stage'], report['code'], report['error_type']), ('index', 'internal_error', 'ZeroDivisionError'))
        self.assertIs(report['retired'], True)
        self.assertNotIn('secret', json.dumps(report))

    def test_a_failed_run_lasts_at_most_the_budget_plus_the_retirement_budget(self):
        """Item 12: every request of the retirement may hang up to its limit; all of them share RETIRE_BUDGET seconds."""
        extra = FakeServer.COSTS['sweep'] + FakeServer.COSTS['write'] + FakeServer.COSTS['status']
        server = FakeServer(self.clock, hang_deletes=True, write_status=503, delete_statuses=[409, 409, 409])
        report = run(server, self.clock, timeout=10.0)
        self.assertEqual((report['stage'], report['code']), ('write', 'server_error'))
        self.assertLessEqual(report['total_seconds'], 10.0 + probe.RETIRE_BUDGET + extra)
        self.assertLessEqual(sum(timeout for kind, _, timeout in server.requests if kind == 'delete'), probe.RETIRE_BUDGET)
        self.assertIs(report['retired'], False)
        slow = FakeServer(self.clock, polls_before_done=None, hang_deletes=True)
        report = run(slow, self.clock, timeout=10.0)
        self.assertEqual((report['stage'], report['code']), ('index', 'timeout'))
        self.assertLessEqual(report['total_seconds'], 10.0 + probe.RETIRE_BUDGET + extra)

    def test_ctrl_c_with_the_write_in_flight_still_retires_the_note_by_its_marker(self):
        """fix2 item 5: the write may have landed when the signal arrives; the run does not know it, so the retirement is tried (version 2, then 1) and `retired` says so."""
        server = FakeServer(self.clock, raises=('write', KeyboardInterrupt()))
        report = run(server, self.clock)
        self.assertEqual((report['stage'], report['code'], report['retired']), ('write', 'interrupted', True))
        self.assertIn('delete', server.kinds())

    def test_a_refused_write_is_still_not_retired(self):
        report = run(FakeServer(self.clock, write_status=400), self.clock)
        self.assertEqual((report['stage'], report['retired']), ('write', None))

    def test_a_second_signal_inside_the_cleanup_does_not_lose_the_report(self):
        """fix2 item 5: a KeyboardInterrupt in `clean_up` used to leave the run (and the command's report) at stage `setup`; now the first failure is reported and `retired` is False."""
        server = FakeServer(self.clock, status_code=500, raises=('delete', KeyboardInterrupt()))
        report = run(server, self.clock)
        self.assertEqual((report['stage'], report['code'], report['retired']), ('index', 'server_error', False))

    def test_the_retirement_after_a_signal_fits_in_the_stop_grace_period_of_a_container(self):
        """fix2 item 5: `docker stop` gives 10 s; the retirement after a signal has a budget of its own below that, and the manual states the grace period to configure."""
        self.assertLess(probe.INTERRUPT_RETIRE_BUDGET, 10.0)
        server = FakeServer(self.clock, raises=('status', KeyboardInterrupt()), hang_deletes=True)
        report = run(server, self.clock)
        self.assertEqual(report['code'], 'interrupted')
        self.assertLessEqual(report['stages']['retire'], probe.INTERRUPT_RETIRE_BUDGET + 1e-6)
        self.assertLessEqual(sum(timeout for kind, _, timeout in server.requests if kind == 'delete'), probe.INTERRUPT_RETIRE_BUDGET)
        failed = FakeServer(self.clock, status_code=500, hang_deletes=True)  # a failure that is no signal keeps the whole budget
        run(failed, self.clock)
        self.assertEqual(max(timeout for kind, _, timeout in failed.requests if kind == 'delete'), probe.RETIRE_CALL_TIMEOUT)


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

    def command(self, *arguments, api=None, environ=None, queue=False):
        out, err = io.StringIO(), io.StringIO()
        factory = (lambda url, token: api) if api is not None else probe.HttpApi
        with patch.dict(os.environ, environ or {}, clear=False), patch.object(probe, 'HttpApi', factory), patch.object(probe, 'purge_after', lambda *arguments: None), patch.object(probe, 'queue_check', probe.queue_check if queue else (lambda *arguments: None)),                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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

    # -- fix1 of the review of phase 11 (items 4, 5, 9, 1) ----------------------------------------------------------------------------

    def metric(self, name):
        for family in text_string_to_metric_families(self.metrics.read_text(encoding='utf-8')):
            for sample in family.samples:
                if sample.name == name and not sample.labels:
                    return sample.value
        return None

    def test_ctrl_c_ends_with_a_report_the_note_retired_and_success_zero_in_the_file(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        server = FakeServer(clock, raises=('status', KeyboardInterrupt()))
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):
            code, out, _ = self.command(api=server)
        self.assertEqual(code, 'probe_failed: stage=index code=interrupted')
        self.assertEqual(json.loads(out)['retired'], True)
        self.assertIn('delete', server.kinds())
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)

    @unittest.skipUnless(hasattr(signal, 'SIGTERM') and os.name == 'posix', 'SIGTERM is a POSIX signal')
    def test_sigterm_is_handled_like_ctrl_c_and_the_handler_is_put_back(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()

        class Terminated(FakeServer):
            def call(self_, method, path, body=None, timeout=None):
                if path.endswith('/status'):
                    os.kill(os.getpid(), signal.SIGTERM)
                return super().call(method, path, body, timeout)
        server = Terminated(clock)
        before = signal.getsignal(signal.SIGTERM)
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):
            code, out, _ = self.command(api=server)
        self.assertEqual(code, 'probe_failed: stage=index code=interrupted')
        self.assertEqual(json.loads(out)['retired'], True)
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_a_transport_that_cannot_be_built_still_writes_success_zero(self):
        """Item 4: the construction of `HttpApi` is inside the same net as the run."""
        self.key.write_text('mp_token\n', encoding='utf-8')

        def refuse(url, token):
            raise UnicodeEncodeError('ascii', 'x', 0, 1, 'secret mp_token in a message')
        out_before = self.metrics.exists()
        with patch.object(probe, 'HttpApi', refuse):
            code, out, err = self.command()
        self.assertFalse(out_before)
        self.assertEqual(code, 'probe_failed: stage=setup code=internal_error')
        self.assertNotIn('secret', out + err)
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)

    def test_a_key_that_is_not_ascii_is_an_unreadable_key_not_a_trace(self):
        self.key.write_text('mp_tóken\n', encoding='utf-8')
        code, out, _ = self.command(api=object())
        self.assertEqual(code, 'probe_failed: stage=setup code=key_unreadable')
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)

    def test_a_metrics_file_that_cannot_be_written_is_logged_and_fails_the_command(self):
        """Item 5: the probe may have worked, but the file a monitor reads did not change: exit non-zero, a log event, `metrics_written` false in the report."""
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch('memory_platform.probe.write_atomic', side_effect=OSError('read-only file system')):
            code, out, err = self.command(api=FakeServer(clock))
        self.assertEqual(code, 'probe_metrics_failed: the metrics file could not be written')
        report = json.loads(out)
        self.assertEqual((report['status'], report['metrics_written']), ('probe_ok', False))
        lines = [json.loads(line) for line in err.splitlines() if line.startswith('{')]
        self.assertEqual([(line['event'], line['exc_type'], line['code']) for line in lines], [('probe_metrics_failed', 'OSError', 'metrics_unwritable')])
        self.assertNotIn('read-only', err)

    def test_the_last_success_timestamp_is_kept_by_a_failed_run_and_moves_with_a_good_one(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch('memory_platform.observability.time.time', return_value=1000.0):
            self.command(api=FakeServer(clock))
        self.assertEqual((self.metric('kairos_probe_last_success_timestamp_seconds'), self.metric('kairos_probe_last_run_timestamp_seconds')), (1000.0, 1000.0))
        observability.PROBE_LAST_SUCCESS.set(0)  # a new process starts from nothing: what the next run knows is only what the file says
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch('memory_platform.observability.time.time', return_value=2000.0):
            code, _, _ = self.command(api=FakeServer(clock, write_status=500))
        self.assertTrue(code.startswith('probe_failed'))
        self.assertEqual((self.metric('kairos_probe_last_success_timestamp_seconds'), self.metric('kairos_probe_last_run_timestamp_seconds')), (1000.0, 2000.0))
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)
        observability.PROBE_LAST_SUCCESS.set(0)
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch('memory_platform.observability.time.time', return_value=3000.0):
            self.command(api=FakeServer(clock))
        self.assertEqual(self.metric('kairos_probe_last_success_timestamp_seconds'), 3000.0)

    @unittest.skipUnless(os.name == 'posix', 'the run lock is a POSIX file lock')
    def test_a_second_run_at_once_waits_for_the_lock_and_then_refuses_with_busy_without_a_request(self):
        import fcntl
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        server = FakeServer(clock)
        with open(str(self.key) + probe.LOCK_SUFFIX, 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):
                code, out, _ = self.command(api=server)
        self.assertEqual(code, 'probe_failed: stage=setup code=busy')
        self.assertEqual(server.requests, [])
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)
        self.assertGreater(clock.now, 1000.0)  # it did wait (on the injected clock) before it gave up
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):  # the lock is gone with the other run
            code, _, _ = self.command(api=FakeServer(clock))
        self.assertEqual(code, 0)

    def probe_command(self, server, clock, store_factory=None):
        out, err = io.StringIO(), io.StringIO()
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            observability.configure_logging()
            report = probe.probe_command(None, str(self.key), str(self.metrics), environ={}, api_factory=lambda url, token: server, store_factory=store_factory)
        return report, [json.loads(line) for line in err.getvalue().splitlines() if line.startswith('{')]

    def test_no_purge_after_a_key_the_server_refuses_or_after_a_signal(self):
        """fix2 items 1 and 5: with a 401 nothing is known about who owns the project, and after a SIGTERM there is no time for a purge of its own."""
        self.key.write_text('mp_token\n', encoding='utf-8')
        opened = []

        def factory():
            opened.append(1)
            raise AssertionError('the database must not be opened')
        for label, options in (('401', {'write_status': 401}), ('interrupt', {'raises': ('status', KeyboardInterrupt())})):
            with self.subTest(label):
                clock = Clock()
                report, _ = self.probe_command(FakeServer(clock, **options), clock, factory)
                self.assertEqual((report['status'], report['purged']), ('probe_failed', None))
        self.assertEqual(opened, [])

    def test_the_last_success_is_read_inside_the_lock_so_an_older_run_never_overwrites_a_newer_one(self):
        """fix2 item 6: the run that waited for the lock reads the file AFTER the other run wrote it; the metrics are written before the lock is released."""
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch('memory_platform.observability.time.time', return_value=1000.0):
            self.command(api=FakeServer(clock))
        self.assertEqual(self.metric('kairos_probe_last_success_timestamp_seconds'), 1000.0)
        real = probe.run_lock

        @contextlib.contextmanager
        def lock_after_a_newer_run(*arguments, **options):
            with real(*arguments, **options):
                observability.PROBE_LAST_SUCCESS.set(0)  # a new process
                with patch('memory_platform.observability.time.time', return_value=5000.0):
                    observability.record_probe(True, {}, last_success=None)
                probe.write_metrics(str(self.metrics))  # the other run finished while this one waited for the lock
                observability.PROBE_LAST_SUCCESS.set(0)
                yield
        observability.PROBE_LAST_SUCCESS.set(0)
        with patch.object(probe, 'run_lock', lock_after_a_newer_run), patch('memory_platform.observability.time.time', return_value=2000.0):
            code, _, _ = self.command(api=FakeServer(clock, write_status=500))
        self.assertTrue(code.startswith('probe_failed'))
        self.assertEqual(self.metric('kairos_probe_last_success_timestamp_seconds'), 5000.0)
        self.assertEqual(self.metric('kairos_probe_success'), 0.0)

    def test_the_metrics_are_written_before_the_lock_is_released(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        seen = []
        real = probe.run_lock

        @contextlib.contextmanager
        def watching(*arguments, **options):
            with real(*arguments, **options):
                yield
            seen.append(self.metrics.exists())  # on release the file of this run is already there
        with patch.object(probe, 'run_lock', watching):
            self.command(api=FakeServer(clock), environ={})
        self.assertEqual(seen, [True])

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() != 0, 'permissions of a directory are enforced for a user that is not root')
    def test_a_key_in_a_read_only_directory_does_not_break_the_probe_and_the_lock_moves_next_to_the_metrics(self):
        """fix2 item 7: a key mounted read-only used to end every run in `internal_error`; the lock then goes next to the metrics file."""
        locked = self.directory / 'ro'
        locked.mkdir()
        key = locked / 'kairos-probe.key'
        key.write_text('mp_token\n', encoding='utf-8')
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        clock = Clock()
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), contextlib.redirect_stderr(io.StringIO()):
            report = probe.probe_command(None, str(key), str(self.metrics), environ={}, api_factory=lambda url, token: FakeServer(clock))
        self.assertEqual((report['status'], report['metrics_written']), ('probe_ok', True))
        self.assertFalse(Path(str(key) + probe.LOCK_SUFFIX).exists())
        self.assertTrue(Path(str(self.metrics) + probe.LOCK_SUFFIX).exists())
        self.assertEqual(self.metric('kairos_probe_success'), 1.0)

    @unittest.skipUnless(os.name == 'posix', 'the run lock is a POSIX file lock')
    def test_without_any_place_for_the_lock_the_run_goes_on_with_a_warning_never_internal_error(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()

        real = os.open

        def refuse(path, *arguments, **options):
            if str(path).endswith(probe.LOCK_SUFFIX):
                raise OSError(30, 'Read-only file system')
            return real(path, *arguments, **options)
        with patch.object(probe.os, 'open', refuse):
            report, lines = self.probe_command(FakeServer(clock), clock)
        self.assertEqual(report['status'], 'probe_ok')
        self.assertEqual([(line['event'], line['code']) for line in lines if line['event'] == 'probe_lock_unavailable'], [('probe_lock_unavailable', 'lock_unavailable')])
        self.assertTrue(self.metrics.exists())

    @unittest.skipUnless(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'O_NOFOLLOW')
    def test_a_link_in_place_of_the_lock_file_is_never_followed(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        target = self.directory / 'elsewhere'
        target.write_text('keep', encoding='utf-8')
        os.symlink(target, str(self.key) + probe.LOCK_SUFFIX)
        clock = Clock()
        report, _ = self.probe_command(FakeServer(clock), clock)
        self.assertEqual(report['status'], 'probe_ok')
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep')

    # -- T-74: a queue that does not drain -------------------------------------------------------------------------------------------

    def queue_store(self, clock, enqueued=None):
        """A store whose queue holds one job enqueued at `enqueued` on the injected clock (None: an empty queue), so its age is what the clock says."""
        from unittest.mock import MagicMock
        connection = MagicMock()

        def execute(sql, *arguments):
            result = MagicMock()
            result.fetchall.return_value = [] if enqueued is None else [{'state': 'pending', 'destination': 'embed', 'n': 1, 'oldest': clock.now-enqueued}]
            return result
        connection.execute.side_effect = execute
        store = MagicMock()
        store.transaction.return_value.__enter__.return_value = connection
        return store

    def test_t74_a_queue_older_than_the_threshold_is_queue_stuck_with_the_event_and_the_default_900_seconds(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        enqueued = clock.now-901
        with patch.object(probe, 'purge_after', lambda *arguments: None):
            report, lines = self.probe_command(FakeServer(clock), clock, lambda: self.queue_store(clock, enqueued))
        self.assertEqual(report['status'], 'probe_ok')  # the round trip worked: the stuck queue is its own alert
        self.assertTrue(report['queue']['stuck'])
        self.assertEqual((report['queue']['threshold_seconds'], report['queue']['oldest_pending_seconds'] > 900), (900.0, True))
        self.assertEqual([(line['event'], line['level'], line['code']) for line in lines if line['event'] == 'queue_stuck'], [('queue_stuck', 'warning', 'queue_stuck')])

    def test_t74_the_threshold_is_the_setting_and_a_queue_below_it_or_empty_is_not_stuck(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        for label, enqueued_ago, environ, stuck in (('below', 600, {}, False), ('empty', None, {}, False), ('custom', 100, {'MEMORY_QUEUE_STUCK_SECONDS': '60'}, True),
                                                    ('custom-below', 100, {'MEMORY_QUEUE_STUCK_SECONDS': '120'}, False), ('invalid', 1000, {'MEMORY_QUEUE_STUCK_SECONDS': 'soon'}, True)):
            with self.subTest(label):
                clock = Clock()
                enqueued = None if enqueued_ago is None else clock.now-enqueued_ago
                out, err = io.StringIO(), io.StringIO()
                with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)), patch.object(probe, 'purge_after', lambda *arguments: None),                         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    observability.configure_logging()
                    report = probe.probe_command(None, str(self.key), str(self.metrics), environ=environ, api_factory=lambda url, token: FakeServer(clock), store_factory=lambda: self.queue_store(clock, enqueued))
                self.assertEqual(report['queue']['stuck'], stuck)
                events = [json.loads(line)['event'] for line in err.getvalue().splitlines() if line.startswith('{')]
                self.assertEqual('queue_stuck' in events, stuck)

    def test_t74_admin_probe_exits_non_zero_with_queue_stuck_and_keeps_the_probe_result_in_the_report(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()
        stuck = clock.now-5000
        with patch.object(probe, 'purge_after', lambda *arguments: None), patch('memory_platform.admin.Store', lambda *arguments, **options: self.queue_store(clock, stuck)),                 patch('memory_platform.admin.guarded_dsn', lambda dsn: dsn), patch('memory_platform.admin.Settings') as settings:
            settings.from_env.return_value = SimpleNamespace(dsn='postgresql://fixture', project_maps={})
            code, out, _ = self.command(api=FakeServer(clock), environ={'MEMORY_PROBE_TIMEOUT': '120'}, queue=True)
        self.assertTrue(str(code).startswith('queue_stuck: oldest_pending_seconds='), code)
        self.assertEqual(json.loads(out)['status'], 'probe_ok')

    def test_t74_no_check_without_a_database_after_401_or_after_a_signal(self):
        self.key.write_text('mp_token\n', encoding='utf-8')

        def factory():
            raise AssertionError('the database must not be opened')
        for label, options in (('401', {'write_status': 401}), ('interrupt', {'raises': ('status', KeyboardInterrupt())})):
            with self.subTest(label):
                clock = Clock()
                report, _ = self.probe_command(FakeServer(clock, **options), clock, factory)
                self.assertIsNone(report['queue'])
        clock = Clock()
        report, _ = self.probe_command(FakeServer(clock), clock, None)
        self.assertIsNone(report['queue'])  # no database settings: nothing to read, and no failure of the probe
        self.assertEqual(report['status'], 'probe_ok')

    def test_a_purge_that_fails_is_logged_and_does_not_change_the_result_of_the_probe(self):
        self.key.write_text('mp_token\n', encoding='utf-8')
        clock = Clock()

        def no_store():
            raise ConnectionError('postgresql://user:secret@host/db')
        with patch('memory_platform.probe.time', SimpleNamespace(monotonic=clock, sleep=clock.sleep)):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                observability.configure_logging()
                report = probe.probe_command(None, str(self.key), str(self.metrics), environ={}, api_factory=lambda url, token: FakeServer(clock), store_factory=no_store)
        self.assertEqual((report['status'], report['purged']), ('probe_ok', None))
        lines = [json.loads(line) for line in err.getvalue().splitlines() if line.startswith('{')]
        self.assertEqual([(line['event'], line['exc_type']) for line in lines], [('probe_queue_failed', 'ConnectionError'), ('probe_purge_failed', 'ConnectionError')])  # the factory failed once, each check says so
        self.assertNotIn('secret', err.getvalue())


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
        self.assertEqual((report['stage'], report['code']), ('search', 'semantic_unavailable'), report)  # its only vector went with the note: the layer answers `off` (`no_vectors`)
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

    # -- fix1 of the review of phase 11 (items 1, 3, 10) ------------------------------------------------------------------------------

    TABLES = ('memory_items', 'item_versions', 'events', 'jobs', 'projection_receipts', 'embeddings', 'embedding_chunks')

    def footprint(self, project):
        """Rows per table of the project (the receipts and the vectors are keyed by project too)."""
        return {table: self.rows(f'SELECT count(*) AS n FROM memory.{table} WHERE project_id=%s', project)[0]['n'] for table in self.TABLES}

    def test_the_note_of_this_run_must_come_back_through_the_vectors_not_any_semantic_hit(self):
        """The false green of the review, on the real server: a note of an earlier run is still ACTIVE with a good vector (so the semantic layer answers `ok` with a hit), and the vector of
        this run's note is gone. The sweep is taken out to leave the leftover in place: the probe must still fail, because the hit is not its own."""
        leftover = self.stale_note(1)[0]
        self.drain()  # indexed: it has a current vector, so the semantic layer has something to answer with
        seen = {}
        original = probe.Probe.event

        def remember(probe_, event_type, item_id, version, title, content):
            if event_type == 'note':
                seen['item'] = item_id
            return original(probe_, event_type, item_id, version, title, content)

        class LosesTheVector(ClientApi):
            def call(inner, method, path, body=None, timeout=None):
                answer = ClientApi.call(inner, method, path, body, timeout)
                if method == 'GET' and path.endswith('/status') and answer[1] and answer[1].get('complete') and 'deleted' not in seen:
                    with self.store.transaction() as c:
                        seen['deleted'] = sum(len(c.execute(f'DELETE FROM memory.{table} WHERE project_id=%s AND item_id=%s RETURNING 1', (probe.PROBE_PROJECT, seen['item'])).fetchall())
                                              for table in ('embeddings', 'embedding_chunks'))
                return answer
        with patch.object(probe.Probe, 'sweep', lambda probe_, started: 0), patch.object(probe.Probe, 'event', remember):
            report = self.probe(self.sleep_while_the_worker_runs, api=LosesTheVector(self.client, self.token))
        self.assertGreater(seen.get('deleted', 0), 0)
        self.assertEqual((report['status'], report['stage'], report['code']), ('probe_failed', 'search', 'no_result'), report)
        self.assertEqual(report['kairos_probe_success'], 0)

    def stale_note(self, count):
        """Notes of an earlier run that was cut: written through the API, still active; returns their item ids."""
        stale = [{'event_id': str(uuid.uuid4()), 'project_id': probe.PROBE_PROJECT, 'session_id': 'kairos-probe', 'agent_id': 'kairos-probe', 'event_type': 'note', 'occurred_at': '2026-11-17T10:00:00Z',
                  'item_id': str(uuid.uuid4()), 'version': 1, 'generate': False,
                  'payload': {'title': 'Probe probe-stale%d' % number, 'content': 'Synthetic probe memory probe-stale%d. A run that was cut left it.' % number, 'source': {'uri': 'fixture://kairos-probe'}}}
                 for number in range(count)]
        for event in stale:
            self.assertEqual(self.api.call('POST', '/v1/events', event)[0], 202)
        return [event['item_id'] for event in stale]

    def test_a_note_an_earlier_run_left_active_is_retired_by_the_sweep_at_the_start(self):
        self.stale_note(2)
        self.assertEqual(self.memories(), (2, 0))
        report = self.probe(self.sleep_while_the_worker_runs)
        self.assertEqual((report['status'], report['swept']), ('probe_ok', 2), report)
        self.assertEqual(self.memories(), (0, 3))  # nothing active survives a run: the two leftovers and this run's note, all retired

    def test_the_purge_deletes_the_rows_of_the_retired_notes_of_the_probe_and_nothing_of_any_other_project(self):
        user = 'user-notes'
        self.store.create_project(self.actor, {'id': user, 'title': 'A user project'})
        self.store.set_policy(self.actor, user, {'capture_mode': 'summary', 'temporal_projection': False})
        item = str(uuid.uuid4())
        note = {'event_id': str(uuid.uuid4()), 'project_id': user, 'session_id': 's', 'agent_id': 'a', 'event_type': 'note', 'occurred_at': '2026-11-17T10:00:00Z', 'item_id': item, 'version': 1,
                'generate': False, 'payload': {'title': 'User note', 'content': 'A note of a user project', 'source': {'uri': 'fixture://user'}}}
        self.store.ingest_event(self.actor, note)
        self.drain()
        self.store.ingest_event(self.actor, dict(note, event_id=str(uuid.uuid4()), event_type='delete', version=2))  # a RETIRED note of a user, with vectors and jobs like the probe's
        self.drain()
        before = self.footprint(user)
        self.assertEqual(before['memory_items'], 1)
        self.assertGreater(before['embeddings'] + before['embedding_chunks'], 0)
        reports = [self.probe(self.sleep_while_the_worker_runs) for _ in range(3)]
        mine = self.footprint(probe.PROBE_PROJECT)
        self.assertGreater(mine['memory_items'], 0)
        self.assertGreater(mine['embeddings'] + mine['embedding_chunks'], 0)
        self.assertEqual(probe.purge_retired(self.store, older_than=3600), 0)  # none is older than the hour: nothing goes by age...
        self.assertEqual(probe.purge_retired(self.store, [reports[0]['item_id']]), 1)  # ...and an item named goes at once
        self.assertEqual(probe.purge_retired(self.store, [item]), 0)  # a retired note of ANOTHER project is not reachable through this one
        self.assertEqual(probe.purge_retired(self.store, older_than=0), 2)  # the older ones, by age
        self.assertEqual(self.footprint(probe.PROBE_PROJECT), {table: 0 for table in self.TABLES})
        self.assertEqual(self.footprint(user), before)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM memory.projects')[0]['n'], 2)  # no table, no project, no key went

    def test_the_purge_shares_one_budget_among_its_statements_and_a_slow_database_rolls_it_back(self):
        """fix2 item 4: eight statements of 15 s each made 130 s; now every statement gets what is left of PURGE_BUDGET and, once it is spent, the transaction is rolled back."""
        report = self.probe(self.sleep_while_the_worker_runs)
        ticks = iter([0.0, 0.0])

        def slow():
            return next(ticks, 1000.0)  # the first two readings are at 0 s (start, select); after them the budget is gone
        with self.assertRaises(probe.ProbeError) as raised:
            probe.purge_retired(self.store, [report['item_id']], older_than=0, clock=slow)
        self.assertEqual(raised.exception.code, 'purge_timeout')
        self.assertEqual(self.memories(), (0, 1))  # nothing was deleted: one transaction
        self.assertEqual(probe.purge_retired(self.store, [report['item_id']]), 1)

    def test_every_statement_of_the_purge_is_limited_by_what_is_left_of_the_budget(self):
        report = self.probe(self.sleep_while_the_worker_runs)
        limits = []

        class Spy:
            def __init__(self, store):
                self.store = store

            def transaction(self):
                manager = self.store.transaction()

                class Wrapped:
                    def __enter__(wrapped):
                        wrapped.connection = manager.__enter__()

                        def execute(sql, parameters=None):
                            if sql.startswith('SET LOCAL statement_timeout'):
                                limits.append(sql)
                            return wrapped.connection.execute(sql, parameters)
                        return SimpleNamespace(execute=execute)

                    def __exit__(wrapped, *exc):
                        return manager.__exit__(*exc)
                return Wrapped()
        self.assertEqual(probe.purge_retired(Spy(self.store), [report['item_id']], older_than=0, clock=lambda: 0.0, budget=9.0), 1)
        self.assertGreater(len(limits), 5)
        self.assertEqual(set(limits), {"SET LOCAL statement_timeout = '9000ms'"})

    def test_the_rows_of_the_probe_project_do_not_grow_over_many_runs_when_each_purges_its_note(self):
        counts = []
        for _ in range(4):
            report = self.probe(self.sleep_while_the_worker_runs)
            self.assertEqual(report['status'], 'probe_ok')
            self.assertEqual(probe.purge_retired(self.store, [report['item_id']]), 1)
            counts.append(self.footprint(probe.PROBE_PROJECT))
        self.assertEqual(counts, [{table: 0 for table in self.TABLES}] * 4)

    def test_a_retired_note_whose_embed_job_is_still_waiting_is_not_purged_under_the_worker(self):
        report = self.probe(self.clock.sleep, timeout=20.0)  # the worker never runs: the embed job stays pending, the note is retired
        self.assertEqual((report['stage'], report['retired']), ('index', True))
        self.assertEqual(probe.purge_retired(self.store, [report['item_id']], older_than=0), 0)
        self.assertEqual(self.memories(), (0, 1))
        self.drain()
        self.assertEqual(probe.purge_retired(self.store, [report['item_id']]), 1)

    def test_the_command_purges_through_the_database_of_the_operator(self):
        metrics = Path(self.key_file.parent) / 'kairos-probe.prom'
        out, err = io.StringIO(), io.StringIO()
        self.addCleanup(observability.remove_logging)
        with patch('memory_platform.admin.Settings.from_env', return_value=Settings(self.store.dsn)), patch('memory_platform.admin.Store', return_value=self.store),                 patch.object(probe, 'HttpApi', lambda url, token: self.api), patch('memory_platform.probe.time', SimpleNamespace(monotonic=self.clock, sleep=self.sleep_while_the_worker_runs)),                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            admin.main(['probe', '--metrics-file', str(metrics), '--key-file', str(self.key_file)])
        report = json.loads(out.getvalue())
        self.assertEqual((report['status'], report['purged'], report['metrics_written']), ('probe_ok', 1, True))
        self.assertEqual(self.footprint(probe.PROBE_PROJECT), {table: 0 for table in self.TABLES})
        self.assertIn('kairos_probe_last_success_timestamp_seconds', metrics.read_text(encoding='utf-8'))


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


class DocumentationTests(unittest.TestCase):
    """T-71: the manuals say what the code does (names, defaults, stages, codes, exit codes)."""

    @classmethod
    def setUpClass(cls):
        cls.operations = (ROOT / 'docs' / 'operations.md').read_text(encoding='utf-8')
        cls.configuration = (ROOT / 'docs' / 'configuration.md').read_text(encoding='utf-8')
        cls.section = cls.operations[cls.operations.index('## Sonda de ida y vuelta'):]
        cls.section = cls.section[:cls.section.index('\n## ', 5)]

    def test_configuration_lists_every_variable_with_the_default_of_the_code(self):
        defaults = {'MEMORY_PROBE_TIMEOUT': '`%d`' % probe.DEFAULT_TIMEOUT, 'MEMORY_PROBE_URL': '`%s`' % probe.DEFAULT_URL,
                    'MEMORY_PROBE_KEY_FILE': '`%s`' % probe.DEFAULT_KEY_FILE, 'MEMORY_PROBE_METRICS_FILE': '`%s`' % probe.DEFAULT_METRICS_FILE}
        for name, default in defaults.items():
            row = next((line for line in self.configuration.splitlines() if line.startswith('| `%s`' % name)), None)
            with self.subTest(name):
                self.assertIsNotNone(row, name + ' is not in docs/configuration.md')
                self.assertIn(default, row)
        self.assertIn('de 1 a %d' % probe.TIMEOUT_RANGE[1], self.configuration)
        self.assertEqual(probe.TIMEOUT_RANGE[0], 1.0)

    def test_the_manual_names_every_stage_code_variable_option_and_metric(self):
        for stage in probe.STAGES + (probe.SETUP,):
            with self.subTest(stage=stage):
                self.assertIn('`%s`' % stage, self.section)
        for code in probe.CODES:
            with self.subTest(code=code):
                self.assertIn('`%s`' % code, self.section)
        for name in ('probe_failed', 'probe_ok', 'kairos-probe', 'probe-provision', 'MEMORY_PROBE_TIMEOUT', 'MEMORY_PROBE_URL', 'MEMORY_PROBE_KEY_FILE', 'MEMORY_PROBE_METRICS_FILE',
                     '--url', '--key-file', '--metrics-file', 'kairos_probe_success', 'kairos_probe_stage_seconds', 'kairos_probe_last_run_timestamp_seconds', 'key_file_unsafe', 'retired',
                     'kairos_probe_last_success_timestamp_seconds', 'probe_metrics_failed', 'metrics_written', 'metrics_unwritable', 'probe_sweep_failed', 'probe_purge_failed', 'swept', 'purged',
                     '--as', 'project_foreign', 'actor_foreign', 'actor_disabled', 'operator_unknown', 'no_admin', '<MEMORY_PROBE_KEY_FILE>' + probe.LOCK_SUFFIX,
                     probe.SERVICE_USERNAME, probe.PROBE_TITLE):
            with self.subTest(name=name):
                self.assertIn(name, self.section)

    def test_the_manual_agrees_with_the_code_on_the_defaults_scopes_and_exit_codes(self):
        for value in (probe.DEFAULT_KEY_FILE, probe.DEFAULT_METRICS_FILE, probe.DEFAULT_URL, str(int(probe.DEFAULT_TIMEOUT)) + ' s', '`%s`' % probe.PROBE_POLICY['capture_mode']):
            with self.subTest(value=value):
                self.assertIn(value, self.section)
        self.assertEqual(probe.PROBE_SCOPES, ('read', 'write'))
        self.assertIn('`read` y `write`', self.section)
        self.assertIn('sale con **0**', self.section)
        self.assertIn('sale con **1**', self.section)
        self.assertEqual(probe.RETIRE_CALL_TIMEOUT, 10.0)
        self.assertIn('(10 s)', self.section)
        self.assertEqual((probe.RETIRE_BUDGET, probe.SWEEP_LIMIT, probe.PURGE_AFTER_SECONDS), (20.0, 20, 600))
        self.assertIn('presupuesto propio de **20 s**', self.section)
        self.assertIn('`MEMORY_PROBE_TIMEOUT` + 20 s', self.section)
        self.assertIn('como mucho 20 por ejecución', self.section)
        self.assertIn('hace más de 10 minutos', self.section)
        self.assertIn('`MEMORY_PROBE_TIMEOUT` + 20 s', self.configuration)

    def test_the_manual_gives_the_budgets_of_the_purge_and_of_the_stop_and_the_figure_for_the_container(self):
        """fix2: the total bound (retirement + purge + connection), the budget after a signal and the `stop_grace_period` that T-75 copies into the compose service."""
        self.assertEqual((probe.PURGE_BUDGET, probe.INTERRUPT_RETIRE_BUDGET), (15.0, 8.0))
        self.assertLess(probe.INTERRUPT_RETIRE_BUDGET, 10.0)
        for text in ('**15 s para toda la purga**', 'tope total propio de **25 s**', '**8 s**', '`stop_grace_period: 15s`', '`purge_timeout`', '`probe_lock_unavailable`', '`lock_unavailable`',
                     '`probe.key_issued`', '`user.created`', '`grant.created`'):
            with self.subTest(text=text):
                self.assertIn(text, self.section)
        self.assertIn('como mucho 25 s en total', self.configuration)
        plan = (ROOT / 'docs' / 'roadmap' / '2026-11-15-reliable-operations' / 'improvement-plan.md')
        if plan.exists():  # the image of the tests does not carry the plan
            self.assertIn('como mucho 25 s más', plan.read_text(encoding='utf-8'))

    def test_the_log_field_of_the_event_is_documented_and_real(self):
        self.assertIn('`exc_type`, `stage`', self.operations)
        self.assertIn('stage', observability.FIELDS)


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
        with patch.object(probe.Probe, 'retire', lambda self, started, state, versions=(2,), budget=None: None):
            report = probe.Probe(self.api, timeout=60.0, poll=2.0, clock=self.clock, sleep=self.drain_and_advance).run()
        self.assertEqual(report['status'], 'probe_ok')  # the probe itself cannot tell...
        self.assertEqual(self.active(), 1)  # ...and `ChainTests.test_healthy_*` asserts (0, 1): it would be red

    def test_mutant_without_the_cleanup_after_a_failure_leaves_the_note_the_stopped_worker_check_reports(self):
        with patch.object(probe.Probe, 'clean_up', lambda self, state, stage, interrupted=False: None):
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
