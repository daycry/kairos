"""Small remote client with an explicitly enabled, durable per-project outbox.

No repository scan, transcript discovery or plugin-cache modification occurs.
Only the JSON file explicitly selected by the caller can become an event.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

# The distributed SDK uses the same pure redaction policy as the server.
_SDK_ROOT = Path(__file__).resolve().parents[1]
for _sdk_path in (_SDK_ROOT, _SDK_ROOT / 'server'):  # a checkout keeps the package under server/; a distribution keeps it beside scripts/
    if str(_sdk_path) not in sys.path:
        sys.path.insert(0, str(_sdk_path))

MAX_EVENT_BYTES = 262144
MAX_PENDING_BYTES = 10 * 1024 * 1024
MAX_PENDING_EVENTS = 1000


class ClientError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # Never forward a Bearer credential to another origin or route.
        return None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def safe_directory(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ClientError('Client state must not traverse a symlink or junction')
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def atomic_json(path, value):
    if path.is_symlink():
        raise ClientError('Refusing to replace a linked client-state file')
    encoded = canonical(value)
    fd, temporary = tempfile.mkstemp(prefix='.memory-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def outbox_lock(root):
    path = root / '.outbox.lock'
    if path.is_symlink():
        raise ClientError('Invalid outbox lock')
    with path.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ClientError('Another client is updating this outbox') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class MemoryClient:
    def __init__(self, url, project_id, key_file, outbox, *, capture_mode='off', timeout=35, opener=None):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ClientError('The server URL must be HTTP(S), without credentials or query')
        if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ClientError('Remote memory servers require HTTPS')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', project_id):
            raise ClientError('Project ID is invalid; it cannot be a filesystem path')
        self.url = url.rstrip('/')
        self.project_id = project_id
        self.key_file = Path(key_file)
        self.outbox = Path(outbox)
        self.capture_mode = capture_mode
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, payload):
        if self.key_file.stat().st_size > 1024:
            raise ClientError('The API credential file is invalid')
        key = self.key_file.read_text(encoding='utf-8').strip()
        if not key or len(key) > 512 or '\r' in key or '\n' in key:
            raise ClientError('The API credential file is empty or invalid')
        request = urllib.request.Request(self.url + path, data=canonical(payload), method='POST', headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ClientError('Server response exceeded the client limit')
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ClientError('Server returned an invalid result')
                return value
        except urllib.error.HTTPError as exc:
            raise ClientError(f'Server rejected the operation (HTTP {exc.code}); the pending event was kept') from None
        except (OSError, ValueError, urllib.error.URLError):
            raise ClientError('The response could not be confirmed; the pending event was kept with its original identity') from None

    def preflight(self, query, *, max_chars=16000):
        return self.request('/v1/context', {'project_ids': [self.project_id], 'q': query, 'layers': ['episodic', 'documental', 'temporal'], 'max_chars': max_chars, 'limit': 20})

    def _records(self, root):
        records = []
        for path in sorted(root.glob('*.json')):
            if path.is_symlink() or path.parent.resolve() != root:
                raise ClientError('Invalid outbox record path')
            if path.stat().st_size > MAX_EVENT_BYTES * 2:
                raise ClientError('An outbox record is oversized')
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                event = record['event']
                identity = str(uuid.UUID(event['event_id']))
                if path.name != identity + '.json' or event.get('project_id') != self.project_id or record.get('sha256') != hashlib.sha256(canonical(event)).hexdigest():
                    raise ValueError('identity or hash')
            except (ValueError, KeyError, TypeError):
                raise ClientError('An outbox record is corrupt; it was not discarded') from None
            records.append((path, record))
        return records

    def enqueue(self, event):
        if self.capture_mode not in ('summary', 'full'):
            raise ClientError('Capture is off; enable it for this client and project before queuing an event')
        if not isinstance(event, dict) or event.get('project_id') != self.project_id:
            raise ClientError('The event belongs to another project')
        try:
            event_id = str(uuid.UUID(event['event_id']))
            item_id = str(uuid.UUID(event['item_id']))
        except (ValueError, KeyError, TypeError):
            raise ClientError('An event and item UUID are required; identities are never regenerated on retry') from None
        event = json.loads(canonical(event))
        event['event_id'], event['item_id'] = event_id, item_id
        if not isinstance(event.get('payload'), dict):
            raise ClientError('The event must contain a structured payload')
        try:
            from memory_platform.privacy import sanitize_payload, has_sensitive
            from memory_platform.errors import MemoryError as PrivacyError
        except ImportError:
            raise ClientError('The SDK privacy module is required; install the complete client distribution') from None
        try:
            cleaned, redacted = sanitize_payload(event['payload'])
            if redacted and event['payload'].get('validation_status') == 'validated':
                raise ClientError('A validated source contains private data and needs review before publication')
            event['payload'] = cleaned
            if has_sensitive(event):
                raise ClientError('Sensitive event metadata needs review before it can enter the outbox')
        except PrivacyError:
            raise ClientError('Private blocks or sensitive metadata are invalid; no event was queued') from None
        if self.capture_mode == 'summary' and any(key in event.get('payload', {}) for key in ('transcript', 'conversation', 'messages', 'raw_activity')):
            raise ClientError('Summary capture does not accept a transcript payload')
        encoded = canonical(event)
        if len(encoded) > MAX_EVENT_BYTES:
            raise ClientError('Event exceeds the 256 KiB limit')
        root = safe_directory(self.outbox)
        with outbox_lock(root):
            records = self._records(root)
            target = root / (event_id + '.json')
            body_hash = hashlib.sha256(encoded).hexdigest()
            existing = next((record for path, record in records if path == target), None)
            if existing:
                if existing['sha256'] != body_hash:
                    raise ClientError('An event with this ID has different content; the original was kept')
                return {'event_id': event_id, 'status': 'already_queued'}
            if len(records) >= MAX_PENDING_EVENTS or sum(path.stat().st_size for path, _ in records) + len(encoded) > MAX_PENDING_BYTES:
                raise ClientError('Outbox is full; no pending event was discarded')
            atomic_json(target, {'schema_version': 1, 'event': event, 'sha256': body_hash, 'state': 'pending', 'redacted_locally': redacted})
            return {'event_id': event_id, 'status': 'queued', 'redacted_locally': redacted}

    def status(self):
        if not self.outbox.exists():
            return {'project_id': self.project_id, 'pending': 0, 'events': []}
        root = safe_directory(self.outbox)
        with outbox_lock(root):
            records = self._records(root)
            return {'project_id': self.project_id, 'pending': len(records), 'events': [{'event_id': record['event']['event_id'], 'state': record.get('state', 'pending')} for _, record in records]}

    def flush(self):
        if self.capture_mode not in ('summary', 'full'):
            raise ClientError('Capture is off; pending events were kept')
        root = safe_directory(self.outbox)
        confirmed = []
        with outbox_lock(root):
            for path, record in self._records(root):
                try:
                    receipt = self.request('/v1/events', record['event'])
                    event = record['event']
                    if receipt.get('event_id') != event['event_id'] or receipt.get('item_id') != event['item_id'] or receipt.get('version') != event['version'] or receipt.get('status') not in ('accepted', 'duplicate', 'superseded'):
                        raise ClientError('The acceptance receipt does not match the queued event')
                except ClientError:
                    record['state'] = 'unconfirmed'
                    atomic_json(path, record)
                    raise
                receipts = safe_directory(root / 'receipts')
                atomic_json(receipts / path.name, receipt)
                path.unlink()  # Exact managed UUID record; no recursive operation.
                confirmed.append(event['event_id'])
        return {'confirmed': confirmed, 'pending': self.status()['pending']}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Remote memory preflight and explicit event delivery')
    parser.add_argument('--config', default='.claude/knowledge-services/memory-client.json')
    sub = parser.add_subparsers(dest='command', required=True)
    configure = sub.add_parser('configure')
    configure.add_argument('--url', required=True)
    configure.add_argument('--project', required=True)
    configure.add_argument('--key-file', required=True)
    configure.add_argument('--capture-mode', choices=['off', 'summary', 'full'], default='off')
    preflight = sub.add_parser('preflight')
    preflight.add_argument('--query', required=True)
    preflight.add_argument('--max-chars', type=int, default=16000)
    for command in ('enqueue', 'capture'):
        child = sub.add_parser(command)
        child.add_argument('--event-file', required=True)
    sub.add_parser('flush')
    sub.add_parser('status')
    args = parser.parse_args(argv)
    config_path = Path(args.config).absolute()
    if args.command == 'configure':
        folder = safe_directory(config_path.parent)
        MemoryClient(args.url, args.project, args.key_file, folder / 'memory-outbox', capture_mode=args.capture_mode)
        atomic_json(config_path, {'url': args.url, 'project_id': args.project, 'key_file': str(Path(args.key_file).resolve()), 'capture_mode': args.capture_mode})
        print(json.dumps({'configured': str(config_path), 'capture_mode': args.capture_mode}))
        return
    config = json.loads(config_path.read_text(encoding='utf-8'))
    client = MemoryClient(config['url'], config['project_id'], config['key_file'], config_path.parent / 'memory-outbox' / config['project_id'], capture_mode=config.get('capture_mode', 'off'))
    if args.command == 'preflight':
        result = client.preflight(args.query, max_chars=args.max_chars)
    elif args.command in ('enqueue', 'capture'):
        event_path = Path(args.event_file)
        if event_path.stat().st_size > MAX_EVENT_BYTES:
            raise ClientError('Selected event file is oversized')
        result = client.enqueue(json.loads(event_path.read_text(encoding='utf-8')))
        if args.command == 'capture':
            result = client.flush()
    else:
        result = getattr(client, args.command)()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ClientError, OSError, ValueError, KeyError) as exc:
        # Print bounded, local diagnostics; URLs, credentials and payloads are omitted.
        raise SystemExit(str(exc) if isinstance(exc, ClientError) else 'Client configuration or input file is invalid; no pending event was discarded.') from None
