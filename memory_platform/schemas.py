"""Versioned JSON Schemas for structured observations (C-05, CA-20, CA-21).

The schemas are the files in docs/contracts/ (`<name>.schema.json`); this module only loads them and reports the first
violation as a domain error. The message carries the JSON path of the violation and the kind of rule that failed, never a
value or a property name taken from the content (a hostile client must not be able to read its own payload back in an error).
"""
import json
import os
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import MemoryError

VERSIONS = ('observation.v1', 'session-summary.v1')
# Where the event carries the document; the paths in errors are relative to the request body of POST /v1/observations.
BASE = '/payload/structured'
# Hostile nesting: the schemas are shallow (3 levels) and `additionalProperties: false` stops the descent at unknown keys, but
# the check below also bounds what is handed to the validator.
MAX_DEPTH = 8


def contracts_dir():
    """`MEMORY_SCHEMA_DIR` if set, otherwise docs/contracts next to the package (the images copy it to /app/docs/contracts)."""
    override = os.environ.get('MEMORY_SCHEMA_DIR')
    return Path(override) if override else Path(__file__).resolve().parent.parent / 'docs' / 'contracts'


@lru_cache(maxsize=None)
def _validator(version):
    document = json.loads((contracts_dir() / (version + '.schema.json')).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def _fail(path, rule):
    raise MemoryError('invalid_observation', f'Structured observation does not match its schema: {rule} at {path}', 422)


def _too_deep(value):
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if isinstance(current, (dict, list)):
            if depth >= MAX_DEPTH:
                return True
            pending.extend((child, depth + 1) for child in (current.values() if isinstance(current, dict) else current))
    return False


def validate_structured(document):
    """Raise `invalid_observation` (422) unless `document` is valid for the version it declares."""
    if not isinstance(document, dict):
        _fail(BASE, 'type')
    if _too_deep(document):
        _fail(BASE, 'maxDepth')
    version = document.get('schema_version')
    if 'schema_version' not in document:
        _fail(BASE + '/schema_version', 'required')
    if not isinstance(version, str) or version not in VERSIONS:
        _fail(BASE + '/schema_version', 'const')
    errors = list(_validator(version).iter_errors(document))
    if not errors:
        return
    # Deterministic choice: the shallowest path first, then lexicographic.
    error = min(errors, key=lambda e: (len(e.absolute_path), [str(part) for part in e.absolute_path]))
    path = BASE + ''.join('/' + str(part) for part in error.absolute_path)
    if error.validator == 'required':
        # The names come from the schema, not from the content.
        missing = [name for name in error.validator_value if name not in error.instance]
        path += '/' + missing[0]
    _fail(path, error.validator)


def validate_event_structured(payload):
    """Validate `structured` when the payload carries it; without it nothing is checked (P-11)."""
    structured = getattr(payload, 'structured', None)
    if structured is None:
        return
    validate_structured(structured)
