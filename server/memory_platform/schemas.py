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
# Total values (objects, arrays and scalars) a document may hold before it reaches jsonschema. A document at every limit of
# `observation.v1` holds under 200, so 1 000 never rejects a valid one; it bounds the pairwise work of `uniqueItems` on arrays
# of large non-string elements, which the per-array bound alone leaves at about 2 s per 240 KB request (review of phase 4, N1).
MAX_NODES = 1000


def contracts_dir():
    """`MEMORY_SCHEMA_DIR` if set, otherwise docs/contracts next to the package (the runtime images copy it to /app/docs/contracts), otherwise the repository one (server/memory_platform/ is two levels below the repository root)."""
    override = os.environ.get('MEMORY_SCHEMA_DIR')
    if override:
        return Path(override)
    package = Path(__file__).resolve().parent
    beside = package.parent / 'docs' / 'contracts'
    return beside if beside.is_dir() else package.parents[1] / 'docs' / 'contracts'


@lru_cache(maxsize=None)
def _validator(version):
    document = json.loads((contracts_dir() / (version + '.schema.json')).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def load_all():
    """Load every schema now: the API calls this at startup so a missing or broken file stops it there, not on a request."""
    for version in VERSIONS:
        _validator(version)


@lru_cache(maxsize=None)
def _bounds(version):
    """(largest `maxItems`, property names) the schema declares; computed once from the loaded document."""
    largest, names, pending = 0, set(), [_validator(version).schema]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if isinstance(node.get('maxItems'), int):
                largest = max(largest, node['maxItems'])
            if isinstance(node.get('properties'), dict):
                names.update(node['properties'])
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return largest, frozenset(names)


def max_array_items():
    return max(_bounds(version)[0] for version in VERSIONS)


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


def _oversized(document):
    """(path, rule) of the first size violation, or None. Linear in the size of the document.

    `maxNodes` at the document root once it holds more than `MAX_NODES` values; `maxItems` at the first array longer than any
    schema allows.

    `uniqueItems` compares every pair of elements (quadratic with mixed types) and jsonschema evaluates it before it looks at
    `maxItems`, so an array this long never reaches the validator. Keys that are not property names of a schema are shown as `*`.
    """
    limit = max_array_items()
    known = frozenset().union(*(_bounds(version)[1] for version in VERSIONS))
    pending, nodes = [(document, BASE)], 0
    while pending:
        current, path = pending.pop()
        nodes += 1
        if nodes > MAX_NODES:
            return BASE, 'maxNodes'
        if isinstance(current, list):
            if len(current) > limit:
                return path, 'maxItems'
            pending.extend((child, f'{path}/{index}') for index, child in enumerate(current))
        elif isinstance(current, dict):
            pending.extend((child, f'{path}/{key if key in known else "*"}') for key, child in current.items())
    return None


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
    oversized = _oversized(document)
    if oversized is not None:
        _fail(*oversized)
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
    structured = payload.get('structured') if isinstance(payload, dict) else getattr(payload, 'structured', None)
    if structured is None:
        return
    validate_structured(structured)
