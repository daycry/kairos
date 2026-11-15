"""A loopback stand-in for Ollama that FAILS on any language-model call (CA-18).

`/api/embed` answers with a fixed vector so the embedding worker can run; `/api/chat` and `/api/generate` answer 500 and are
counted, so a test (or the whole suite, see `run_postgres.py`) ends by asserting that the count is zero. It listens on 127.0.0.1
only and belongs to the process that started it; it never forwards anything.

Run as `python -m memory_platform.tests.llm_spy --serve 0.0.0.0:11434 --dimensions 768` it is the simulated embedding provider of an isolated rehearsal
(`scripts/deploy-memory.py --embed-stub`, T-71/T-72): the same answers, deterministic vectors of the dimension of the vector index (equal texts give equal
vectors) and `GET /__spy`, which reports what was asked of it: `{"chat_calls": n, "embed_calls": n, "requests": n}`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LANGUAGE_MODEL_PATHS = ('/api/chat', '/api/generate')


def text_vector(text: str, dimensions: int) -> list[float]:
    """A deterministic unit vector of `dimensions` numbers for a text: the simulated embedding of the rehearsal."""
    values, counter = [], 0
    while len(values) < dimensions:
        digest = hashlib.sha256(('%d:%s' % (counter, text)).encode('utf-8')).digest()
        values.extend(byte / 127.5 - 1.0 for byte in digest)
        counter += 1
    values = values[:dimensions]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


class ChatSpy:
    def __init__(self, host: str = '127.0.0.1', port: int = 0, dimensions: int | None = None):
        self.requests: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        spy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length) or b'{}') if length else {}
                if self.path != '/__spy':  # asking the spy what it saw is not something it was asked
                    with spy._lock:
                        spy.requests.append((self.command, self.path))
                if self.path in LANGUAGE_MODEL_PATHS:
                    status, answer = 500, {'error': 'the server must not call a language model'}
                elif self.path == '/api/embed':
                    inputs = body.get('input', [''])
                    inputs = [inputs] if isinstance(inputs, str) else inputs
                    status, answer = 200, {'embeddings': [text_vector(str(text), dimensions) if dimensions else [1.0, 0.5, 0.25, 0.125] for text in inputs]}
                elif self.path == '/__spy':
                    status, answer = 200, {'chat_calls': len(spy.chat_calls), 'embed_calls': spy.embed_calls, 'requests': len(spy.requests)}
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

        self._server = ThreadingHTTPServer((host, port), Handler)
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', required=True, metavar='HOST:PORT')
    parser.add_argument('--dimensions', type=int, default=768)
    args = parser.parse_args(argv)
    host, _, port = args.serve.rpartition(':')
    spy = ChatSpy(host, int(port), args.dimensions)
    print('embedding stub listening on %s' % args.serve, flush=True)
    try:
        spy._server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
