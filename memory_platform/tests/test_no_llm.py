"""The server runs, ingests and indexes with no language model configured, and the spy proves it never asks for one (CA-18, D-2)."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from memory_platform.app import create_app
from memory_platform.config import Settings
from memory_platform.tests.llm_spy import ChatSpy
from memory_platform.tests.test_store import create_core, event
from memory_platform.worker import Worker

MODEL_VARIABLES = ('MEMORY_LLM_MODEL', 'MEMORY_EXTRACT_ENABLED', 'MEMORY_CORPUS_ANSWER')


def unconfigured_environment(url):
    """The process environment of a default install: no model, no extraction, no generated answers, Ollama = the spy."""
    base = {key: value for key, value in os.environ.items() if key not in MODEL_VARIABLES}
    base.update(MEMORY_DSN=os.environ['MEMORY_TEST_DSN'], MEMORY_OLLAMA_URL=url, MEMORY_EMBED_ENABLED='1')
    return base


def drain(worker):
    processed = 0
    while asyncio.run(worker.run_once()):
        processed += 1
    return processed


class NoLanguageModelTests(unittest.TestCase):
    def setUp(self):
        self.spy = ChatSpy().start()
        self.addCleanup(self.spy.stop)
        self.core, self.actor, self.pid = create_core()
        patcher = patch.dict(os.environ, unconfigured_environment(self.spy.url), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = Settings.from_env()

    def headers(self):
        token = self.core.create_key(self.actor, {'name': 'writer', 'project_ids': [self.pid], 'scopes': ['read', 'write']})['token']
        return {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}

    def test_the_spy_itself_fails_on_a_chat_call(self):
        """The oracle works: a call to /api/chat is answered 500 and counted."""
        reply = httpx.post(self.spy.url + '/api/chat', json={'model': 'any'})
        self.assertEqual(reply.status_code, 500)
        self.assertEqual(self.spy.chat_calls, [('POST', '/api/chat')])

    def test_the_default_environment_needs_no_model(self):
        self.assertEqual(self.settings.llm_model, '')
        self.assertIs(self.settings.extract_enabled, False)
        self.assertIs(self.settings.corpus_answer_enabled, False)

    def test_starting_the_api_and_the_worker_opens_no_connection(self):
        app = create_app(self.settings)
        worker = Worker(app.state.store if hasattr(app.state, 'store') else self.core, self.settings)
        self.assertEqual(set(worker.providers), {'embed'})
        with TestClient(app, base_url='http://localhost:8790') as client:
            self.assertEqual(client.get('/health/live').status_code, 200)
        self.assertEqual(self.spy.requests, [])

    def test_summary_with_generate_is_ingested_and_indexed_without_a_chat_call(self):
        headers = self.headers()
        value = event(self.pid, event_type='summary', payload={'title': 'Session summary', 'content': 'Fencing token checked before publication.'})
        self.assertTrue(value['generate'])
        with TestClient(create_app(self.settings), base_url='http://localhost:8790') as client:
            reply = client.post('/v1/events', json=value, headers=headers)
            self.assertEqual(reply.status_code, 202, reply.text)
            receipt = reply.json()
            self.assertEqual(receipt['extraction'], 'disabled')
            store = self.core.__class__(self.core.dsn, embedding_enabled=True)
            worker = Worker(store, self.settings, worker_id='no-llm')
            self.assertGreaterEqual(drain(worker), 1)
        with self.core.transaction() as c:
            rows = c.execute('SELECT destination, state FROM memory.jobs WHERE item_id=%s', (value['item_id'],)).fetchall()
        self.assertEqual({row['destination'] for row in rows}, {'embed'})
        self.assertEqual({row['state'] for row in rows}, {'succeeded'})
        self.assertGreaterEqual(self.spy.embed_calls, 1)  # the worker really ran, against the spy
        self.assertEqual(self.spy.chat_calls, [])

    def test_an_inherited_extract_job_is_not_run_and_stays_recorded(self):
        value = event(self.pid, event_type='summary')
        self.core.ingest_event(self.actor, value)
        job_id = str(uuid.uuid4())
        with self.core.transaction() as c:
            version = c.execute('SELECT version, canonical_hash FROM memory.memory_items WHERE project_id=%s AND id=%s', (self.pid, value['item_id'])).fetchone()
            c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation) VALUES(%s,%s,%s,%s,%s,'item','extract','upsert')",
                      (job_id, self.pid, value['item_id'], version['version'], version['canonical_hash']))
        drain(Worker(self.core.__class__(self.core.dsn, embedding_enabled=True), self.settings, worker_id='no-llm'))
        with self.core.transaction() as c:
            row = c.execute('SELECT state, error_code FROM memory.jobs WHERE id=%s', (job_id,)).fetchone()
        self.assertEqual((row['state'], row['error_code']), ('failed', 'extraction_disabled'))
        self.assertEqual(self.spy.chat_calls, [])

    def test_an_unknown_extract_job_that_is_retried_is_closed_as_extraction_disabled(self):
        """`retry_job` keeps an `unknown` job in `unknown` (it must be reconciled first); with extraction off the worker still closes it."""
        value = event(self.pid, event_type='summary')
        self.core.ingest_event(self.actor, value)
        job_id = str(uuid.uuid4())
        with self.core.transaction() as c:
            version = c.execute('SELECT version, canonical_hash FROM memory.memory_items WHERE project_id=%s AND id=%s', (self.pid, value['item_id'])).fetchone()
            c.execute("INSERT INTO memory.jobs(id,project_id,item_id,version,canonical_hash,resource_type,destination,operation,state) VALUES(%s,%s,%s,%s,%s,'item','extract','upsert','unknown')",
                      (job_id, self.pid, value['item_id'], version['version'], version['canonical_hash']))
        self.assertEqual(self.core.retry_job(self.actor, job_id)['state'], 'unknown')
        drain(Worker(self.core.__class__(self.core.dsn, embedding_enabled=True), self.settings, worker_id='no-llm'))
        with self.core.transaction() as c:
            row = c.execute('SELECT state, error_code FROM memory.jobs WHERE id=%s', (job_id,)).fetchone()
        self.assertEqual((row['state'], row['error_code']), ('failed', 'extraction_disabled'))
        self.assertEqual(self.spy.chat_calls, [])

    def test_corpus_answer_is_refused_without_a_chat_call(self):
        headers = self.headers()
        self.core.ingest_event(self.actor, event(self.pid, generate=False, payload={'title': 'Fencing', 'content': 'Check the fencing token before publication.'}))
        base = '/v1/projects/' + self.pid + '/corpora'
        with TestClient(create_app(self.settings), base_url='http://localhost:8790') as client:
            self.assertEqual(client.post(base, headers=headers, json={'name': 'selected', 'query': 'fencing'}).status_code, 200)
            primed = client.post(base + '/selected/prime', headers=headers, json={'fresh': False}).json()
            answer = client.post(base + '/selected/answers', headers=headers, json={
                'question': 'fencing', 'request_id': 'no-llm', 'expected_session_id': primed['session_id'], 'expected_generation': primed['version']})
        self.assertEqual(answer.status_code, 403, answer.text)
        self.assertEqual(answer.json()['error']['code'], 'corpus_answer_disabled')
        self.assertEqual(self.spy.chat_calls, [])


if __name__ == '__main__':
    unittest.main()
