"""CA-32: JSON logs with redaction and request_id, and a log line for every `except Exception` that hides a failure (audit B-01)."""
import ast
import asyncio
import inspect
import io
import json
import logging
import pathlib
import unittest
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient
from memory_platform import observability
from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.retrieval import Retrieval

SECRET = 'sk-' + 'a1B2c3D4' * 5
QUERY = 'SYNTHETIC-QUERY-TEXT-0001'
PACKAGE = pathlib.Path(__file__).resolve().parents[1]


class LogCase(unittest.TestCase):
    def capture(self):
        stream = io.StringIO()
        observability.configure_logging(stream)
        self.addCleanup(observability.remove_logging)
        return stream

    def events(self, stream):
        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]  # every line is one JSON document


def fake_app(**settings):
    store, auth = Mock(), Mock()
    auth.authenticate_bearer.return_value = {'id': 'actor', 'credential_type': 'bearer', 'is_admin': False}
    retrieval = Retrieval(store, Settings('unused', request_timeout=5, **settings), Mock(embed=AsyncMock()))
    store.search_items.return_value = []
    store.search_documents.return_value = []
    store.search_native_facts.return_value = []
    app = create_app(Settings('unused', **settings), store, auth, retrieval)
    return app, store, auth, retrieval


class FormatTests(LogCase):
    def test_a_log_line_is_one_json_document_with_ts_level_event(self):
        stream = self.capture()
        observability.log_event('probe', 'warning', layer='episodic', duration_ms=12)
        text = stream.getvalue()
        self.assertEqual(len(text.splitlines()), 1)
        entry = json.loads(text)
        self.assertEqual((entry['level'], entry['event'], entry['layer'], entry['duration_ms']), ('warning', 'probe', 'episodic', 12))
        self.assertRegex(entry['ts'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_secrets_are_redacted_and_unknown_fields_never_travel(self):
        stream = self.capture()
        observability.log_event('probe', reason='failed with Bearer ' + 'x' * 40 + ' and ' + SECRET, query=QUERY, content='body text')
        text = stream.getvalue()
        self.assertNotIn(SECRET, text)
        self.assertNotIn('x' * 40, text)
        self.assertNotIn(QUERY, text)
        self.assertNotIn('body text', text)
        self.assertIn('[REDACTADO]', text)

    def test_a_failure_records_the_exception_type_never_its_message(self):
        stream = self.capture()
        observability.log_failure('probe_failed', RuntimeError('connect postgresql://user:' + SECRET + '@db/x'), 'warning', layer='semantic')
        entry = self.events(stream)[0]
        self.assertEqual((entry['level'], entry['exc_type']), ('warning', 'RuntimeError'))
        self.assertNotIn(SECRET, json.dumps(entry))
        self.assertNotIn('postgresql://', json.dumps(entry))

    def test_records_of_other_loggers_are_json_and_redacted_too(self):
        import logging
        stream = self.capture()
        logging.getLogger('uvicorn.error').warning('Invalid request from %s', SECRET)
        entry = self.events(stream)[0]
        self.assertEqual(entry['level'], 'warning')
        self.assertNotIn(SECRET, json.dumps(entry))

    def test_a_token_that_crosses_the_field_limit_is_still_redacted(self):
        stream = self.capture()
        token = 'sk-' + 'Z9' * 20
        observability.log_event('probe', reason='a' * 184 + ' ' + token)  # the 200-character cut falls inside the token
        logging.getLogger('some.library').warning('b' * 284 + ' ' + token)  # same for the 300 characters of a foreign message
        text = stream.getvalue()
        self.assertNotIn('sk-Z9', text)
        self.assertEqual(text.count('[REDACTADO]'), 2)

    def test_every_logger_of_the_process_ends_in_one_json_line_with_no_secret(self):
        """CA-32 for third parties: httpx, mcp, asyncio, psycopg... Their text, tracebacks and exception messages never reach the output as they are."""
        stream = self.capture()
        names = ('httpx', 'mcp.server.lowlevel', 'asyncio', 'psycopg', 'some.library')
        for name in names:
            try:
                raise RuntimeError('connect postgresql://user:' + SECRET + '@db/x\nsecond line ' + SECRET)
            except RuntimeError:
                logging.getLogger(name).error('failed: postgresql://user:%s@db/x', SECRET, exc_info=True)
        logging.getLogger('httpx').info('HTTP Request: POST http://ollama/api/embed "200 OK"')  # httpx is kept at WARNING
        text = stream.getvalue()
        self.assertEqual(len(text.splitlines()), len(names))
        entries = self.events(stream)
        self.assertEqual([entry['event'] for entry in entries], list(names))
        for entry in entries:
            self.assertEqual((entry['level'], entry['exc_type']), ('error', 'RuntimeError'))
            self.assertIn('msg', entry)
        for leaked in (SECRET, 'postgresql://', 'Traceback', 'second line', 'HTTP Request'):
            self.assertNotIn(leaked, text)

    def test_the_root_logger_keeps_only_the_json_handler_even_after_fastmcp_is_created(self):
        fake_app()  # FastMCP installs its text handler on the root when nobody did it before
        stream = self.capture()
        root = logging.getLogger()
        marked = [h for h in root.handlers if getattr(h, observability._MARK, False)]
        self.assertEqual(root.handlers, marked)
        self.assertEqual(len(marked), 1)
        fake_app()  # created after the logging was configured: create_mcp re-asserts it
        self.assertEqual(root.handlers, marked)
        logging.getLogger('mcp.server').warning('x ' + SECRET)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        observability.remove_logging()
        self.assertEqual([h for h in root.handlers if getattr(h, observability._MARK, False)], [])

    def test_both_processes_install_the_json_logging(self):
        from memory_platform import app, worker
        self.assertIn('configure_logging', inspect.getsource(app.main))
        self.assertIn('configure_logging', inspect.getsource(worker.serve))


class RequestLogTests(LogCase):
    def test_the_request_id_reaches_the_log_of_every_layer_and_the_response(self):
        app, store, auth, retrieval = fake_app()
        stream = self.capture()
        with TestClient(app) as client:
            response = client.post('/v1/search', headers={'Authorization': 'Bearer fixture-token'},
                                   json={'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic', 'documental'], 'semantic': False})
        self.assertEqual(response.status_code, 200, response.text)
        request_id = response.headers['X-Request-ID']
        entries = self.events(stream)
        layers = {entry['layer']: entry for entry in entries if entry['event'] == 'retrieval_layer'}
        self.assertEqual(set(layers), {'episodic', 'documental'})
        for entry in layers.values():
            self.assertEqual(entry['request_id'], request_id)
            self.assertIsInstance(entry['duration_ms'], (int, float))
        access = [entry for entry in entries if entry['event'] == 'http_request']
        self.assertEqual(len(access), 1)
        self.assertEqual((access[0]['request_id'], access[0]['status'], access[0]['method']), (request_id, 200, 'POST'))
        self.assertNotIn(QUERY, stream.getvalue())
        self.assertNotIn('fixture-token', stream.getvalue())

    def test_mcp_requests_are_logged_with_the_closed_route_mcp(self):
        app, store, auth, retrieval = fake_app()
        stream = self.capture()
        with TestClient(app, base_url='http://localhost:8790') as client:
            client.post('/mcp/', headers={'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'},
                        json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
            client.get('/no-such-route-with-an-id-7f3a')
        access = [entry for entry in self.events(stream) if entry['event'] == 'http_request']
        self.assertEqual([entry['route'] for entry in access], ['mcp', 'unmatched'])
        self.assertNotIn('7f3a', stream.getvalue())

    def test_two_requests_never_share_a_request_id(self):
        app, *_ = fake_app()
        stream = self.capture()
        with TestClient(app) as client:
            ids = {client.post('/v1/search', headers={'Authorization': 'Bearer fixture'}, json={'project_ids': ['a'], 'q': 'x', 'layers': ['episodic'], 'semantic': False}).headers['X-Request-ID'] for _ in range(3)}
        self.assertEqual(len(ids), 3)
        self.assertEqual({entry['request_id'] for entry in self.events(stream) if entry['event'] in ('http_request', 'retrieval_layer')}, ids)


class SwallowedFailureTests(LogCase):
    """Every place that turned an exception into 503/`unavailable`/a retry now leaves a trace."""

    def test_unhandled_exception_is_logged_with_the_request_id(self):
        app, store, *_ = fake_app()
        store.list_projects.side_effect = RuntimeError(SECRET)
        stream = self.capture()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get('/v1/projects', headers={'Authorization': 'Bearer fixture'})
        self.assertEqual(response.status_code, 503)
        failed = [entry for entry in self.events(stream) if entry['event'] == 'unhandled_exception']
        self.assertEqual(len(failed), 1)
        self.assertEqual((failed[0]['level'], failed[0]['exc_type'], failed[0]['request_id']), ('error', 'RuntimeError', response.headers['X-Request-ID']))
        self.assertNotIn(SECRET, stream.getvalue())

    def test_readiness_failure_is_logged(self):
        app, store, *_ = fake_app()
        store.transaction.side_effect = RuntimeError('database down')
        stream = self.capture()
        with TestClient(app) as client:
            self.assertEqual(client.get('/health/ready').status_code, 503)
        failed = [entry for entry in self.events(stream) if entry['event'] == 'readiness_failed']
        self.assertEqual([(entry['level'], entry['exc_type']) for entry in failed], [('warning', 'RuntimeError')])

    def test_a_failing_layer_is_logged_and_still_unavailable(self):
        app, store, *_ = fake_app()
        store.search_items.side_effect = RuntimeError(SECRET)
        stream = self.capture()
        with TestClient(app) as client:
            response = client.post('/v1/search', headers={'Authorization': 'Bearer fixture'},
                                   json={'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic'], 'semantic': False})
        self.assertEqual(response.json()['backends']['episodic']['status'], 'unavailable')
        failed = [entry for entry in self.events(stream) if entry['event'] == 'layer_failed']
        self.assertEqual([(entry['layer'], entry['exc_type'], entry['request_id']) for entry in failed], [('episodic', 'RuntimeError', response.headers['X-Request-ID'])])
        self.assertNotIn(SECRET, stream.getvalue())
        self.assertNotIn(QUERY, stream.getvalue())

    def test_a_failing_semantic_layer_is_logged_with_its_reason(self):
        app, store, auth, retrieval = fake_app()
        store.has_vectors.return_value = True
        retrieval.embeddings.embed.side_effect = RuntimeError(SECRET)
        stream = self.capture()
        with TestClient(app) as client:
            response = client.post('/v1/search', headers={'Authorization': 'Bearer fixture'},
                                   json={'project_ids': ['a'], 'q': QUERY, 'layers': ['episodic']})
        self.assertEqual(response.json()['degraded']['reason'], 'provider_error')
        failed = [entry for entry in self.events(stream) if entry['event'] == 'layer_failed']
        self.assertEqual([(entry['layer'], entry['exc_type'], entry['reason']) for entry in failed], [('semantic', 'RuntimeError', 'provider_error')])
        self.assertNotIn(SECRET, stream.getvalue())

    def test_a_failing_mcp_tool_is_logged_with_the_request_id(self):
        app, store, auth, retrieval = fake_app()
        retrieval.search = AsyncMock(side_effect=RuntimeError(SECRET))
        stream = self.capture()
        with TestClient(app, base_url='http://localhost:8790') as client:
            response = client.post('/mcp/', headers={'Authorization': 'Bearer fixture', 'Accept': 'application/json, text/event-stream'},
                                   json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'search', 'arguments': {'project_ids': ['a'], 'q': QUERY}}})
        self.assertTrue(response.json()['result']['isError'])
        failed = [entry for entry in self.events(stream) if entry['event'] == 'mcp_tool_failed']
        self.assertEqual([(entry['level'], entry['exc_type'], entry['request_id']) for entry in failed], [('error', 'RuntimeError', response.headers['X-Request-ID'])])
        self.assertNotIn(SECRET, stream.getvalue())

    def test_a_failing_activity_poll_is_logged(self):
        from memory_platform.activity import stream_activity
        store = Mock()
        store.list_activity.side_effect = RuntimeError(SECRET)
        request = Mock(is_disconnected=AsyncMock(return_value=False))
        stream = self.capture()

        async def drain():
            return [frame async for frame in stream_activity(request, store, {}, 'a', {'items': [], 'has_more': False}, duration=1, poll_interval=0.005)]
        frames = asyncio.run(drain())
        self.assertIn('activity_unavailable', ''.join(frames))
        failed = [entry for entry in self.events(stream) if entry['event'] == 'activity_stream_failed']
        self.assertEqual([(entry['level'], entry['exc_type']) for entry in failed], [('warning', 'RuntimeError')])
        self.assertNotIn(SECRET, stream.getvalue())

    def test_no_except_exception_in_the_package_hides_a_failure_without_a_trace(self):
        """Static rule (B-01): a handler of `Exception` re-raises or logs. `admin.py` is the CLI that exits naming the exception type."""
        offenders = []
        for path in sorted(PACKAGE.glob('*.py')):
            if path.name == 'admin.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name) and node.type.id in ('Exception', 'BaseException') or (isinstance(node, ast.ExceptHandler) and node.type is None):
                    body = ast.Module(body=node.body, type_ignores=[])
                    calls = {getattr(call.func, 'id', getattr(call.func, 'attr', None)) for call in ast.walk(body) if isinstance(call, ast.Call)}
                    if not (calls & {'log_event', 'log_failure'}) and not any(isinstance(inner, ast.Raise) for inner in ast.walk(body)):
                        offenders.append('%s:%d' % (path.name, node.lineno))
        self.assertEqual(offenders, [])


class WorkerLogTests(LogCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.job = {'id': 'job', 'fence': 4, 'attempts': 1, 'destination': 'extract', 'policy': {}, 'project_id': 'p', 'payload': {'title': 'Source', 'content': QUERY}}
        self.store = Mock()
        self.store.claim_job.return_value = self.job
        self.provider = Mock(extract=AsyncMock())

    def worker(self, **settings):
        from memory_platform.worker import Worker
        return Worker(self.store, Settings('unused', lease_seconds=0.3, **settings), {'extract': self.provider})

    async def test_an_unexpected_failure_of_a_job_is_logged_with_its_destination(self):
        self.provider.extract.side_effect = RuntimeError(SECRET)
        stream = self.capture()
        await self.worker().run_once()
        failed = [entry for entry in self.events(stream) if entry['event'] == 'job_failed']
        self.assertEqual([(entry['level'], entry['exc_type'], entry['destination']) for entry in failed], [('error', 'RuntimeError', 'extract')])
        self.assertIn('duration_ms', failed[0])
        self.assertNotIn(SECRET, stream.getvalue())
        self.assertNotIn(QUERY, stream.getvalue())

    async def test_a_provider_error_and_a_success_are_logged_with_duration_and_code(self):
        from memory_platform.providers import ProviderError
        self.provider.extract.side_effect = ProviderError('provider_rejected')
        stream = self.capture()
        await self.worker().run_once()
        self.provider.extract.side_effect = None
        self.provider.extract.return_value = {'payload': {}, 'status': 'extracted'}
        await self.worker().run_once()
        entries = {entry['event']: entry for entry in self.events(stream) if entry['event'].startswith('job_')}
        self.assertEqual((entries['job_failed']['code'], entries['job_failed']['level']), ('provider_rejected', 'warning'))
        self.assertEqual(entries['job_completed']['destination'], 'extract')
        self.assertIn('duration_ms', entries['job_completed'])

    async def test_a_failing_heartbeat_is_logged(self):
        async def slow(source):
            await asyncio.sleep(0.25)
            return {'payload': {}, 'status': 'extracted'}
        self.provider.extract.side_effect = slow
        self.store.renew_lease.side_effect = RuntimeError(SECRET)
        stream = self.capture()
        await self.worker().run_once()
        failed = [entry for entry in self.events(stream) if entry['event'] == 'heartbeat_failed']
        self.assertEqual([(entry['level'], entry['exc_type']) for entry in failed], [('warning', 'RuntimeError')])
        self.assertNotIn(SECRET, stream.getvalue())


if __name__ == '__main__':
    unittest.main()
