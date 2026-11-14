"""Atomic current-run receipts and immutable historical evidence pairs."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')


def paths(directory, prefix):
    if prefix not in {'frozen', 'focused'}:
        raise ValueError('Unknown evidence prefix')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory, directory/(prefix+'-postgres-source.json'), directory/(prefix+'-postgres-result.json')


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def atomic(path, value):
    temporary = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        temporary.write_bytes(encoded(value))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def archive(directory, prefix, source, result, matching):
    previous_hash = source.get('source_sha256')
    if not isinstance(previous_hash, str) or not re.fullmatch('[a-f0-9]{64}', previous_hash):
        raise ValueError('Historical source evidence requires an exact SHA-256')
    pair_hash = hashlib.sha256(encoded({'source': source, 'result': result})).hexdigest()
    kind = 'history' if matching else 'incomplete'
    stem = prefix+'-'+kind+'-'+previous_hash[:16]+'-'+pair_hash[:16]
    saved = []
    for name, value in (('source', source), ('result', result)):
        path = directory/(stem+'-'+name+'.json')
        payload = encoded(value)
        try:
            with path.open('xb') as handle:
                handle.write(payload)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError('Historical evidence is immutable') from None
        saved.append(path.name)
    return saved


def begin_evidence(directory, prefix, source):
    directory, source_path, result_path = paths(directory, prefix)
    current_hash = source.get('source_sha256')
    if not isinstance(current_hash, str) or not re.fullmatch('[a-f0-9]{64}', current_hash):
        raise ValueError('Source evidence requires an exact SHA-256')
    previous_source, previous_result = read(source_path), read(result_path)
    saved = []
    if previous_source is not None and previous_result is not None:
        matching = previous_source.get('source_sha256') == previous_result.get('source_sha256')
        if not matching and not (previous_result.get('status') == 'running' and previous_result.get('passed') is False):
            raise ValueError('Previous source/result pair is inconsistent; inspect it before starting')
        saved = archive(directory, prefix, previous_source, previous_result, matching)
    elif previous_source is not None or previous_result is not None:
        raise ValueError('Previous evidence pair is incomplete; inspect it before starting')
    running = {key: value for key, value in source.items() if key != 'files'}
    running.update(status='running', passed=False, tests=0, failures=0, errors=0, skipped=0,
                   historical_pair=saved)
    # Result first: even between the two atomic replacements, no old success
    # can be mistaken for acceptance of the incoming source generation.
    atomic(result_path, running)
    atomic(source_path, source)
    return running


def finish_evidence(directory, prefix, result):
    _, source_path, result_path = paths(directory, prefix)
    source, running = read(source_path), read(result_path)
    expected = result.get('source_sha256')
    if (not source or not running or source.get('source_sha256') != expected
            or running.get('source_sha256') != expected or running.get('status') != 'running'
            or running.get('passed') is not False):
        raise ValueError('Finishing result does not match the active source generation')
    completed = dict(result, status='completed', historical_pair=running.get('historical_pair', []))
    atomic(result_path, completed)
    return completed
