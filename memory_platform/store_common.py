"""Helpers shared by the Store domain mixins (re-exported by store.py)."""
import hashlib
import json
import uuid
import re
from datetime import datetime

from .errors import MemoryError


def as_dict(value):
    return value.model_dump(mode='json', exclude_none=True) if hasattr(value, 'model_dump') else dict(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def new_id():
    return str(uuid.uuid4())

def lexical_query(q, match_mode):
    if match_mode == 'all':
        return 'plainto_tsquery',q
    if match_mode != 'any':
        raise MemoryError('invalid_query_mode','Unsupported lexical query mode',422)
    return 'websearch_to_tsquery',' OR '.join(re.findall(r'\w+',q,flags=re.UNICODE)[:64])


def clean(value):
    """Convert database UUID/datetime values without leaking internal row objects."""
    return json.loads(json.dumps(value, default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)))
