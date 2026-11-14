import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import unittest
import urllib.error
import uuid

PATH = Path(__file__).resolve().parents[3] / 'scripts' / 'memory-client.py'
spec = importlib.util.spec_from_file_location('platform_remote_client_tests', PATH)
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)
MemoryClient, ClientError = client_module.MemoryClient, client_module.ClientError


class OutboxTests(unittest.TestCase):
    def setUp(self):
        fixture_root = (Path(__file__).resolve().parents[3] / '.pytest_cache' / 'memory-client-tests') if os.name == 'nt' else Path('/tmp/memory-client-tests')
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.root = fixture_root / ('case-' + uuid.uuid4().hex)
        self.root.mkdir()
        def cleanup():
            if self.root.resolve().parent != fixture_root.resolve() or not self.root.name.startswith('case-'):
                raise RuntimeError('Invalid test cleanup path')
            shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        self.key = self.root / 'key'
        self.key.write_text('synthetic-test-credential', encoding='utf-8')
        self.event = {'event_id': str(uuid.uuid4()), 'item_id': str(uuid.uuid4()), 'version': 1,
                      'project_id': 'test-project', 'session_id': 'synthetic-session', 'agent_id': 'fixture',
                      'event_type': 'learning', 'occurred_at': '2026-11-04T10:00:00Z',
                      'payload': {'title': 'Citas: "áé" 🧠', 'content': 'Conservar etiquetas con comas.', 'tags': ['nota:uno,dos', 'equipo:"A"']}}

    def client(self, **changes):
        return MemoryClient('http://127.0.0.1:8790', 'test-project', self.key, self.root / 'outbox', capture_mode='summary', **changes)

    def test_off_is_default_and_remote_http_or_project_traversal_rejected(self):
        client = MemoryClient('http://127.0.0.1:8790', 'test-project', self.key, self.root / 'off')
        with self.assertRaises(ClientError):
            client.enqueue(self.event)
        self.assertFalse((self.root / 'off').exists())
        for url, project in [('http://remote.example', 'valid'), ('http://127.0.0.1', '../foreign')]:
            with self.assertRaises(ClientError):
                MemoryClient(url, project, self.key, self.root / 'unsafe')

    def test_lost_response_reload_and_retry_keep_exact_event_and_unicode(self):
        calls = []
        event = self.event
        class Transport:
            def open(self, request, timeout):
                calls.append(json.loads(request.data))
                if len(calls) == 1:
                    raise urllib.error.URLError('Synthetic accepted-but-response-lost')
                return io.BytesIO(json.dumps({key: event[key] for key in ('event_id', 'item_id', 'version')} | {'status': 'accepted', 'jobs': []}).encode())
        self.client().enqueue(event)
        with self.assertRaises(ClientError):
            self.client(opener=Transport()).flush()
        self.assertEqual(self.client().status()['pending'], 1)
        self.assertEqual(self.client(opener=Transport()).flush()['pending'], 0)
        self.assertEqual(calls, [event, event])
        self.assertTrue((self.root / 'outbox' / 'receipts' / (event['event_id'] + '.json')).is_file())

    def test_duplicate_content_conflict_and_foreign_project_do_not_overwrite(self):
        client = self.client()
        client.enqueue(self.event)
        self.assertEqual(client.enqueue(self.event)['status'], 'already_queued')
        changed = dict(self.event, payload={'title': 'changed', 'content': 'changed'})
        with self.assertRaises(ClientError):
            client.enqueue(changed)
        with self.assertRaises(ClientError):
            client.enqueue(dict(self.event, project_id='foreign'))
        stored = json.loads((self.root / 'outbox' / (self.event['event_id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(stored['event'], self.event)

    def test_corruption_and_unconfirmed_receipt_are_not_discarded(self):
        client = self.client()
        client.enqueue(self.event)
        class WrongReceipt:
            def open(self, request, timeout):
                return io.BytesIO(b'{"event_id":"foreign","status":"accepted"}')
        with self.assertRaises(ClientError):
            self.client(opener=WrongReceipt()).flush()
        self.assertEqual(client.status()['pending'], 1)
        path = self.root / 'outbox' / (self.event['event_id'] + '.json')
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ClientError):
            client.status()
        self.assertTrue(path.exists())

    def test_symlink_outbox_is_rejected_before_writing(self):
        target = self.root / 'actual'
        target.mkdir()
        link = self.root / 'linked'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable for this host identity')
        with self.assertRaises(ClientError):
            MemoryClient('http://127.0.0.1:8790', 'test-project', self.key, link, capture_mode='summary').enqueue(self.event)
        self.assertEqual(list(target.iterdir()), [])

    def test_private_capture_is_redacted_before_any_outbox_write(self):
        event = dict(self.event, payload={'title': 'Privacidad', 'content': 'Guardar contexto. <private>NOT_FOR_STORAGE_123</private> Reutilizar evidencia.'})
        result = self.client().enqueue(event)
        self.assertTrue(result['redacted_locally'])
        record = (self.root / 'outbox' / (event['event_id'] + '.json')).read_text(encoding='utf-8')
        self.assertNotIn('NOT_FOR_STORAGE_123', record)
        self.assertIn('[PRIVADO]', record)
        with self.assertRaises(ClientError):
            self.client().enqueue(dict(self.event, payload={'title': 'broken', 'content': '<private>Never transmit'}))


if __name__ == '__main__':
    unittest.main()
