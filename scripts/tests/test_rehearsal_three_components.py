"""T-71, T-72 (CA-18, CA-31): the isolated rehearsal of the three components keeps its own names, uses a simulated embedding provider, and verifies `/mcp/` with a Bearer.

The rehearsal itself (`scripts/deploy-memory.py --apply --fresh --embed-stub --roundtrip`) needs Docker and runs by hand; its evidence is in the ledger
(`docs/roadmap/2026-11-12-three-components/tasks.md`, T-72). These tests pin what that run relies on, with no Docker and no network beyond loopback.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('kairos_deploy_rehearsal', ROOT / 'scripts' / 'deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

sys.path.insert(0, str(ROOT / 'server'))
from memory_platform.tests.llm_spy import ChatSpy  # noqa: E402  (a loopback stand-in: nothing here needs the server's dependencies)

PROJECT = 'kairos-three-t72'


def arguments(**changes):
    values = dict(apply=True, fresh=True, secret_dir=None, verify_key_file=None, project_name=PROJECT, api_port=18790, web_port=15173, embed_stub=False, roundtrip=False)
    values.update(changes)
    return SimpleNamespace(**values)


class OverrideTests(unittest.TestCase):
    def test_without_the_stub_the_override_is_the_one_of_every_rehearsal(self):
        text = deploy.isolation_override(PROJECT, 18790, 15173)
        self.assertNotIn(deploy.STUB_SERVICE, text)
        self.assertEqual(text, deploy.isolation_override(PROJECT, 18790, 15173, embed_stub=False))

    def test_the_stub_service_uses_the_isolated_api_image_and_only_the_inference_and_egress_networks(self):
        text = deploy.isolation_override(PROJECT, 18790, 15173, embed_stub=True)
        self.assertIn('embed-stub:', text)
        self.assertIn('image: rehearsal-%s-api:latest' % PROJECT, text)
        self.assertIn('networks: [inference, egress]', text)
        self.assertNotIn('knowledge-graphs', text)
        self.assertNotIn('host.docker.internal', text)
        self.assertIn("--dimensions, '768'", text)
        # the allow-list proxy waits for the stub: nginx resolves its upstream when it starts
        self.assertRegex(text, r'ollama:\n    depends_on:\n      embed-stub: \{condition: service_healthy\}')
        # the networks and volumes stay renamed after the project
        self.assertIn('inference: {name: %s_inference}' % PROJECT, text)

    def test_the_stub_is_never_part_of_the_default_names_check(self):
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        deploy.check_isolation_names(PROJECT, compose)  # does not raise


class DeploymentOptionTests(unittest.TestCase):
    def test_the_installed_project_cannot_use_the_stub_or_the_round_trip(self):
        for options in ({'embed_stub': True}, {'roundtrip': True, 'embed_stub': True}):
            with self.assertRaises(deploy.DeploymentError, msg=str(options)):
                deploy.Deployment(arguments(project_name='knowledge-graphs', api_port=8790, web_port=5173, **options))

    def test_the_round_trip_needs_the_stub(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.Deployment(arguments(roundtrip=True))

    def test_the_stub_points_the_proxy_at_the_stub_and_lets_chat_through_to_be_counted(self):
        instance = deploy.Deployment(arguments(embed_stub=True, roundtrip=True))
        self.assertEqual(instance.environment['OLLAMA_UPSTREAM'], 'embed-stub:11434')
        self.assertEqual(instance.environment['OLLAMA_ALLOW_CHAT'], '1')
        self.assertNotIn('host.docker.internal', json.dumps(instance.environment))

    def test_a_rehearsal_without_the_stub_leaves_the_proxy_settings_alone(self):
        instance = deploy.Deployment(arguments())
        self.assertNotIn('OLLAMA_UPSTREAM', instance.environment)

    def test_the_command_line_refuses_the_flags_on_the_installed_project(self):
        for argv in (['--roundtrip'], ['--embed-stub'], ['--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--roundtrip']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                deploy.main(argv)
            self.assertEqual(caught.exception.code, 2, argv)

    def test_the_dry_run_names_the_stub_and_the_round_trip_phase_and_changes_nothing(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = deploy.main(['--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--embed-stub', '--roundtrip', '--dry-run'])
        plan = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((plan['mode'], plan['phases'][-1], plan['services'][-1], plan['data_removed']), ('dry-run', 'roundtrip', 'embed-stub', False))
        self.assertTrue(all(name.startswith(PROJECT + '_') for name in plan['volumes']))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            deploy.main(['--apply', '--dry-run'])


class FakePortal:
    """Records every request of `verify_runtime`; answers like a stack whose `/mcp/` takes a Bearer and never the session."""
    instances = []

    def __init__(self, origin):
        self.calls, self.headers = [], {}
        FakePortal.instances.append(self)

    def login(self, password):
        self.calls.append(('login', None))

    def logout(self):
        self.calls.append(('logout', None))

    def request(self, path, value=None, method=None, bearer=None, host=None):
        self.calls.append((method or 'POST', path, bearer))
        if path == '/v1/keys':
            return {'id': 'key-1', 'token': 'synthetic-token'}
        if path.startswith('/v1/keys/'):
            return {}
        if path == '/mcp/':
            if bearer != 'synthetic-token':
                raise deploy.DeploymentError('401')
            return {'result': self.rpc(value['method'], value['params'])}
        raise AssertionError(path)

    @staticmethod
    def rpc(method, params):
        if method == 'initialize':
            return {}
        if method == 'tools/list':
            names = ['projects', 'document_manifest', 'search', 'remember', 'capture_policy', 'event_status', 'list_corpora', 'observation_add', 'observation_record_event',
                     'get_tool_uses', 'team_work_write', 'team_work_read', 'team_search', 'team_brief', 'corpus_answer', 'corpus_answer_status', 'context']
            tools = [{'name': name, 'inputSchema': {}} for name in names]
            tools[names.index('event_status')]['inputSchema'] = {'properties': {'project_id': {}}}
            tools[names.index('remember')]['inputSchema'] = {'$defs': {'AutomaticCapture': {}}}
            tools[names.index('context')]['inputSchema'] = {'properties': {'match_mode': {}}}
            return {'tools': tools}
        if params['name'] == 'projects':
            return {'structuredContent': {'projects': [{'id': 'p1'}]}}
        return {'structuredContent': {'items': [], 'has_more': False}}


class VerifyRuntimeTests(unittest.TestCase):
    def test_with_a_session_login_the_mcp_calls_carry_a_temporary_read_key_that_is_revoked(self):
        import tempfile
        FakePortal.instances.clear()
        manifest = {'projects': [{'id': 'p1'}], 'documents': []}
        with tempfile.TemporaryDirectory() as directory, patch.object(deploy, 'Portal', FakePortal):
            (Path(directory) / 'bootstrap_password').write_text('synthetic-password\n', encoding='utf-8')
            report = deploy.verify_runtime(manifest, Path(directory))
        calls = FakePortal.instances[0].calls
        self.assertEqual(report['projects'], 1)
        order = [call[0] if call[0] in ('login', 'logout') else call[1] for call in calls]
        self.assertEqual(order[:2], ['login', '/v1/keys'])
        self.assertEqual(order[-2:], ['/v1/keys/key-1', 'logout'])  # the key is revoked while the session is still valid, then the session closes
        self.assertTrue(all(call[2] == 'synthetic-token' for call in calls if len(call) == 3 and call[1] == '/mcp/'))
        self.assertTrue(any(call[1] == '/mcp/' for call in calls))


    def test_an_installation_without_projects_reports_that_the_mcp_check_was_not_possible(self):
        import tempfile
        FakePortal.instances.clear()
        with tempfile.TemporaryDirectory() as directory, patch.object(deploy, 'Portal', FakePortal):
            (Path(directory) / 'bootstrap_password').write_text('synthetic-password' + chr(10), encoding='utf-8')
            report = deploy.verify_runtime({'projects': [], 'documents': []}, Path(directory))
        self.assertIs(report['mcp_checked'], False)
        self.assertEqual([call[0] if call[0] in ('login', 'logout') else call[1] for call in FakePortal.instances[0].calls], ['login', 'logout'])


class EmbeddingStubTests(unittest.TestCase):
    def test_the_stub_serves_deterministic_vectors_of_the_index_dimension_and_reports_without_counting_the_report(self):
        with ChatSpy('127.0.0.1', 0, 768) as spy:
            def call(path, body=None):
                request = urllib.request.Request(spy.url + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST')
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read())
            vectors = call('/api/embed', {'input': ['same', 'same', 'other']})['embeddings']
            self.assertEqual([len(vector) for vector in vectors], [768, 768, 768])
            self.assertEqual(vectors[0], vectors[1])
            self.assertNotEqual(vectors[0], vectors[2])
            self.assertAlmostEqual(sum(value * value for value in vectors[0]), 1.0, places=6)
            self.assertEqual(call('/__spy'), {'chat_calls': 0, 'embed_calls': 1, 'requests': 1})
            self.assertEqual(call('/__spy')['requests'], 1)
        self.assertEqual(spy.chat_calls, [])


if __name__ == '__main__':
    unittest.main()
