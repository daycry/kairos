"""HTTP and MCP exercise the same observation and shared-work transactions."""
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.auth import Auth
from memory_platform import schemas
from memory_platform.config import Settings
from memory_platform.errors import MemoryError
from memory_platform.extended_store import validated_event
from memory_platform.store import digest
from memory_platform.tests.test_store import create_core, event
from memory_platform.tests.test_work_gateway import unpack
from memory_platform.tests.chain_harness import ChainMode, chain_variant


class ExtendedGatewayTests(ChainMode, unittest.TestCase):
    def test_mcp_http_observation_and_team_retry_share_receipts(self):
        store, actor, project = create_core()
        key = store.create_key(actor, {'name': 'extended-fixture', 'project_ids': [project], 'scopes': ['read', 'write']})['token']
        headers = {'Authorization': 'Bearer '+key, 'Accept': 'application/json, text/event-stream'}
        app = create_app(Settings('unused'), store=store, auth=Auth(store))
        with self.open(app) as client:
            def tool(name, arguments):
                response = client.post('/mcp/', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
                self.assertEqual(response.status_code, 200)
                return unpack(response.json()['result'])
            data = event(project, generate=False)
            receipt = tool('observation_add', {'event': data})
            self.assertEqual(client.post('/v1/observations', headers=headers, json=data).json(), receipt)
            change = {'list': 'shared', 'fields': {'task': 'Conservar t\u00edtulos, tags', 'status': 'doing'}, 'request_id': 'shared-retry', 'expected_version': 0}
            first = tool('team_work_write', {'project': project, **change})
            response = client.post('/v1/projects/'+project+'/team-work', headers=headers, json=change)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), first)
            result = client.get('/v1/projects/'+project+'/team-work', headers=headers)
            self.assertEqual(result.json()['lists'][0]['state'], first['state'])
            reader = store.create_key(actor, {'name': 'extended-reader', 'project_ids': [project], 'scopes': ['read']})['token']
            read_headers = {**headers, 'Authorization': 'Bearer '+reader}
            self.assertEqual(client.post('/v1/observations', headers=read_headers, json=data).status_code, 403)
            self.assertEqual(client.post('/v1/projects/'+project+'/team-work', headers=read_headers, json={**change, 'request_id': 'denied'}).status_code, 403)
            self.assertEqual(client.get('/v1/projects/'+project+'/team-work', headers=read_headers).status_code, 200)



if __name__ == '__main__':
    unittest.main()


class StructuredObservationTests(ChainMode, unittest.TestCase):
    """C-05 (CA-20, CA-21, P-11): `payload.structured` is validated against its schema; events without it behave as before."""

    def setUp(self):
        self.store, actor, self.project = create_core()
        self.key = self.store.create_key(actor, {'name': 'structured-fixture', 'project_ids': [self.project], 'scopes': ['read', 'write']})['token']
        self.headers = {'Authorization': 'Bearer '+self.key, 'Accept': 'application/json, text/event-stream'}
        app = create_app(Settings('unused'), store=self.store, auth=Auth(self.store))
        self.http = self.open(app)
        self.http.__enter__()
        self.addCleanup(self.http.__exit__, None, None, None)

    def examples(self, schema, kind):
        return sorted((schemas.contracts_dir() / 'examples' / schema / kind).glob('*.json'))

    def post(self, document, path='/v1/observations'):
        data = event(self.project, generate=False)
        data['payload']['structured'] = document
        return data, self.http.post(path, headers=self.headers, json=data)

    def valid(self):
        return self.named('valid-bugfix')

    def named(self, name, schema='observation.v1'):
        return json.loads((schemas.contracts_dir() / 'examples' / schema / 'valid' / (name + '.json')).read_text(encoding='utf-8'))

    def test_a_valid_observation_is_accepted_over_both_routes(self):
        for path in ('/v1/observations', '/v1/observations/events'):
            data, response = self.post(self.valid(), path)
            self.assertEqual(response.status_code, 202, response.text)
        data, response = self.post(self.valid())
        self.assertEqual(response.json()['status'], 'accepted')

    def test_an_invalid_observation_is_422_with_the_path_and_without_the_content(self):
        sentinel = 'SENTINEL-77aa-do-not-echo'
        base = self.valid()
        missing = {key: value for key, value in base.items() if key != 'facts'}
        cases = [(missing, '/payload/structured/facts'),
                 ({**base, 'mood': sentinel}, '/payload/structured'),
                 ({**base, 'title': sentinel * 20}, '/payload/structured/title'),
                 ({**base, 'schema_version': 'observation.v9'}, '/payload/structured/schema_version')]
        for document, path in cases:
            data, response = self.post(document)
            self.assertEqual(response.status_code, 422, response.text)
            body = response.json()
            self.assertEqual(body['error']['code'], 'invalid_observation')
            self.assertIn(path, body['error']['message'])
            self.assertNotIn(sentinel, response.text)

    def test_the_same_invalid_observation_is_the_same_error_over_mcp(self):
        data = event(self.project, generate=False)
        data['payload']['structured'] = {**self.valid(), 'extra': 1}
        response = self.http.post('/mcp/', headers=self.headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'observation_add', 'arguments': {'event': data}}})
        result = response.json()['result']
        self.assertTrue(result['isError'])
        # The MCP error text is the domain message (as for every tool): the code is a REST concept.
        self.assertIn('does not match its schema: additionalProperties at /payload/structured', json.dumps(result))

    def test_an_event_without_structured_is_accepted_as_before(self):
        data = event(self.project, generate=False)
        self.assertNotIn('structured', data['payload'])
        self.assertEqual(self.http.post('/v1/observations', headers=self.headers, json=data).status_code, 202)

    def test_the_server_agrees_with_the_examples_the_independent_validator_checks(self):
        for schema in ('observation.v1', 'session-summary.v1'):
            for kind, status in (('valid', 202), ('invalid', 422)):
                for path in self.examples(schema, kind):
                    data, response = self.post(json.loads(path.read_text(encoding='utf-8')))
                    self.assertEqual(response.status_code, status, f'{schema}/{path.name}: {response.text[:200]}')
                    if status == 422:
                        self.assertEqual(response.json()['error']['code'], 'invalid_observation', path.name)

    def test_the_422_never_echoes_any_value_of_the_content(self):
        sentinel = 'SENTINEL-c01d-do-not-echo'
        bad = {**self.valid(), 'title': sentinel * 30, 'narrative': sentinel, 'concepts': [sentinel, sentinel],
               'facts': [{'statement': sentinel, 'evidence_quote': sentinel, 'note': sentinel}], sentinel: sentinel}
        data, response = self.post(bad)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(sentinel, response.text)
        self.assertNotIn(sentinel, json.dumps(list(response.headers.items())))

    def test_the_payload_the_cli_0_3_0_sends_is_accepted_without_schema_version(self):
        # Shape of the event built in packages/kairos-cli/lib/capture.mjs (summary with generate: true, capture block, no structured).
        sha = 'a' * 64
        payload = {'title': 'Session summary', 'content': '{"summary":"done"}', 'category': 'agent-activity',
                   'tags': ['runtime:claude', 'capture:summary'], 'source': {'uri': 'agent://claude/s1/' + sha, 'sha256': sha},
                   'validation_status': 'observed'}
        data = event(self.project, generate=True, agent_id='claude', event_type='summary', payload=payload)
        data['capture'] = {'mode': 'summary', 'hook_event': 'Stop', 'fingerprint': digest(
            {'project': self.project, 'runtime': 'claude', 'session': data['session_id'], 'event': 'Stop', 'payload': payload})}
        response = self.http.post('/v1/observations', headers=self.headers, json=data)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertNotIn('schema_version', json.dumps(data))

    def test_a_secret_inside_the_structured_document_is_refused_like_one_in_the_content(self):
        document = {**self.valid(), 'narrative': 'The key is sk-' + 'a' * 40 + ' and it worked.'}
        data, response = self.post(document)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()['error']['code'], 'sensitive_source_requires_review')

    def test_a_maximal_valid_document_fits_the_event_limit_and_a_larger_event_is_still_refused(self):
        maximal = self.named('valid-at-every-limit')
        self.assertEqual(self.post(maximal)[1].status_code, 202)
        data = event(self.project, generate=False)
        data['payload'].update(content='x' * 100000, problem='y' * 10000, correction='z' * 10000, evidence=['e' * 4000] * 20, structured=maximal)
        response = self.http.post('/v1/observations', headers=self.headers, json=data)
        self.assertEqual(response.status_code, 413, response.text)  # the request-body limit answers before the 256 KiB event check


class ValidatedEventTests(unittest.TestCase):
    """The validation step itself, without a database."""

    def example(self, schema='observation.v1'):
        name = 'valid-bugfix' if schema == 'observation.v1' else 'valid-complete'
        return json.loads((schemas.contracts_dir() / 'examples' / schema / 'valid' / (name + '.json')).read_text(encoding='utf-8'))

    def test_structured_is_validated_when_present_and_only_then(self):
        data = event('p1', generate=False)
        self.assertEqual(validated_event(data).payload.structured, None)
        data['payload']['structured'] = self.example()
        self.assertEqual(validated_event(data).payload.structured['schema_version'], 'observation.v1')
        data['payload']['structured'] = {**self.example(), 'extra': 1}
        with self.assertRaises(MemoryError) as caught:
            validated_event(data)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ('invalid_observation', 422))

    def test_a_summary_document_is_validated_with_its_own_schema(self):
        data = event('p1', generate=False)
        data['payload']['structured'] = self.example('session-summary.v1')
        validated_event(data)
        data['payload']['structured'] = {**self.example('session-summary.v1'), 'schema_version': 'observation.v1'}
        with self.assertRaises(MemoryError):
            validated_event(data)


class StructuredIngestRouteTests(ChainMode, unittest.TestCase):
    """Gaps 1-3 and 5 of the phase 4 review: every route that ingests an event validates `structured` at the one shared point."""

    def setUp(self):
        self.store, actor, self.project = create_core()
        self.key = self.store.create_key(actor, {'name': 'route-fixture', 'project_ids': [self.project], 'scopes': ['read', 'write']})['token']
        self.headers = {'Authorization': 'Bearer '+self.key, 'Accept': 'application/json, text/event-stream'}
        self.app = create_app(Settings('unused'), store=self.store, auth=Auth(self.store))
        self.http = self.open(self.app)
        self.http.__enter__()
        self.addCleanup(self.http.__exit__, None, None, None)

    def valid(self):
        return json.loads((schemas.contracts_dir() / 'examples' / 'observation.v1' / 'valid' / 'valid-bugfix.json').read_text(encoding='utf-8'))

    def post(self, document, path='/v1/events'):
        data = event(self.project, generate=False)
        data['payload']['structured'] = document
        return data, self.http.post(path, headers=self.headers, json=data)

    def remember(self, data):
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'remember', 'arguments': {'event': data}}}
        return self.http.post('/mcp/', headers=self.headers, json=body).json()['result']

    def stored_count(self):
        with self.store.transaction() as c:
            return c.execute('SELECT count(*) AS n FROM memory.events WHERE project_id=%s', (self.project,)).fetchone()['n']

    def test_events_and_remember_validate_structured_too_and_store_nothing_when_invalid(self):
        sentinel = 'SENTINEL-9d2e-do-not-echo'
        before = self.stored_count()
        bad = {**self.valid(), 'extra': sentinel}
        data, response = self.post(bad)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()['error']['code'], 'invalid_observation')
        self.assertIn('additionalProperties at /payload/structured', response.json()['error']['message'])
        self.assertNotIn(sentinel, response.text)
        data = event(self.project, generate=False)
        data['payload']['structured'] = bad
        result = self.remember(data)
        self.assertTrue(result['isError'])
        self.assertIn('does not match its schema: additionalProperties at /payload/structured', json.dumps(result))
        self.assertNotIn(sentinel, json.dumps(result))
        self.assertEqual(self.stored_count(), before)
        data, response = self.post(self.valid())
        self.assertEqual(response.status_code, 202, response.text)
        data = event(self.project, generate=False)
        data['payload']['structured'] = self.valid()
        self.assertFalse(self.remember(data).get('isError'))

    def test_a_huge_array_over_events_is_422_in_under_a_second(self):
        import time
        started = time.monotonic()
        data, response = self.post({**self.valid(), 'concepts': ['x'] + list(range(8000))})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'invalid_observation')
        self.assertIn('maxItems', response.json()['error']['message'])
        self.assertLess(time.monotonic() - started, 1.0)

    def test_the_api_loads_the_schemas_at_startup_and_fails_when_they_are_missing(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as empty, patch.dict('os.environ', {'MEMORY_SCHEMA_DIR': empty}):
            schemas._validator.cache_clear()
            try:
                with self.assertRaises(FileNotFoundError):
                    create_app(Settings('unused'), store=self.store, auth=Auth(self.store))
            finally:
                schemas._validator.cache_clear()
        create_app(Settings('unused'), store=self.store, auth=Auth(self.store))

    def test_structured_is_dropped_from_what_the_extraction_model_returns(self):
        from memory_platform.tests.test_store import extraction_receipt
        store, actor, pid = create_core(extraction=True)
        receipt = store.ingest_event(actor, event(pid, generate=True))
        jid = receipt['jobs'][0]
        with store.transaction() as c:
            c.execute("UPDATE memory.jobs SET state='running',fence=1,lease_until=clock_timestamp()+interval '1 minute' WHERE id=%s", (jid,))
        generated = extraction_receipt()
        generated['payload']['structured'] = {'schema_version': 'observation.v1', 'bogus': True}
        self.assertTrue(store.complete_job(jid, 1, generated))
        with store.transaction() as c:
            saved = c.execute('SELECT receipt FROM memory.projection_receipts WHERE job_id=%s', (jid,)).fetchone()
        derived = store.get_item(actor, pid, saved['receipt']['derived_item_id'])
        self.assertNotIn('structured', derived)

    def test_sensitive_data_inside_structured_rejects_the_event_and_is_not_redacted(self):
        # Gap 4: docs/integration.md says so; `structured` is never rewritten, so its shape stays the one that was validated.
        data, response = self.post({**self.valid(), 'narrative': 'visto <private>token interno</private> aqui'})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()['error']['code'], 'sensitive_source_requires_review')
        self.assertNotIn('token interno', response.text)


# Every class above runs a second time through kairos-mcp (T-48, CA-11): the same tests, the same results, the envelope of S-05 aside.
ExtendedGatewayChainTests = chain_variant(ExtendedGatewayTests)
StructuredObservationChainTests = chain_variant(StructuredObservationTests)
StructuredIngestRouteChainTests = chain_variant(StructuredIngestRouteTests)
