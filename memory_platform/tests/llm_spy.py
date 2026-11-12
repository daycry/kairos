"""A loopback stand-in for Ollama that FAILS on any language-model call (CA-18).

`/api/embed` answers with a fixed vector so the embedding worker can run; `/api/chat` and `/api/generate` answer 500 and are
counted, so a test (or the whole suite, see `run_postgres.py`) ends by asserting that the count is zero. It listens on 127.0.0.1
only and belongs to the process that started it; it never forwards anything.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LANGUAGE_MODEL_PATHS = ('/api/chat', '/api/generate')


class ChatSpy:
    def __init__(self):
        self.requests: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        spy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length) or b'{}') if length else {}
                with spy._lock:
                    spy.requests.append((self.command, self.path))
                if self.path in LANGUAGE_MODEL_PATHS:
                    status, answer = 500, {'error': 'the server must not call a language model'}
                elif self.path == '/api/embed':
                    status, answer = 200, {'embeddings': [[1.0, 0.5, 0.25, 0.125] for _ in body.get('input', [''])]}
                elif self.path == '/api/version':
                    status, answer = 200, {'version': 'spy'}
                else:
                    status, answer = 404, {'error': 'not found'}
                payload = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_DELETE = handle_any

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return 'http://127.0.0.1:%d' % self._server.server_address[1]

    def start(self) -> 'ChatSpy':
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def chat_calls(self) -> list[tuple[str, str]]:
        with self._lock:
            return [item for item in self.requests if item[1] in LANGUAGE_MODEL_PATHS]

    @property
    def embed_calls(self) -> int:
        with self._lock:
            return sum(1 for item in self.requests if item[1] == '/api/embed')

    def __enter__(self) -> 'ChatSpy':
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
