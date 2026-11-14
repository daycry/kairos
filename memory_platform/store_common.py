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


# Lexical configurations searched together: the stored `simple` vector (as before) and the Spanish and English
# vectors built over unaccented text. A row matches when any configuration matches; its rank is the best of them.
_LANGUAGES = (('spanish','es'),('english','en'))


def fts_match(function, vector='search_vector'):
    """SQL predicate over the stored vectors of the table; takes three `%s` (the query once per configuration).

    `vector` may carry an alias prefix, e.g. ``i.search_vector``.
    """
    parts=[f"{vector} @@ {function}('simple',%s)"]
    parts+=[f"{vector}_{suffix} @@ {function}('{config}',memory.kairos_unaccent(%s))" for config,suffix in _LANGUAGES]
    return '('+' OR '.join(parts)+')'


def fts_rank(function, vector='search_vector'):
    """SQL rank expression (maximum over the configurations); takes three `%s`, like :func:`fts_match`."""
    parts=[f"ts_rank_cd({vector},{function}('simple',%s))"]
    parts+=[f"ts_rank_cd({vector}_{suffix},{function}('{config}',memory.kairos_unaccent(%s)))" for config,suffix in _LANGUAGES]
    return 'GREATEST('+','.join(parts)+')'


def fts_inline(expression, function='plainto_tsquery', stored=None):
    """Predicate for text matched by the three configurations; takes three `%s`.

    `simple` is always computed in line over `expression` (as before). The Spanish and English vectors are computed
    in line too, unless `stored` names a table alias whose `search_vector_es`/`search_vector_en` columns exist
    (``stored='i.search_vector'`` reads `i.search_vector_es`/`_en`: indexed, nothing recomputed per row; those vectors
    also cover the problem/correction text of the item, not only title and content).
    """
    parts=[f"to_tsvector('simple',{expression}) @@ {function}('simple',%s)"]
    if stored:
        parts+=[f"{stored}_{suffix} @@ {function}('{config}',memory.kairos_unaccent(%s))" for config,suffix in _LANGUAGES]
    else:
        parts+=[f"to_tsvector('{config}',memory.kairos_unaccent({expression})) @@ {function}('{config}',memory.kairos_unaccent(%s))" for config,_suffix in _LANGUAGES]
    return '('+' OR '.join(parts)+')'


# Trigram fallback (pg_trgm): completes a lexical answer shorter than `limit` with titles close to the query.
# `word_similarity` between the query and the title key (see memory.trigram_key in schema.sql); recorded after the
# retrieval-eval run of T-17.
TRIGRAM_THRESHOLD = 0.3
# Own statement_timeout of the fallback (it can scan a large share of the titles); when it runs out the lexical rows are
# returned as they are and the answer says so (`LexicalResults.fuzzy_timed_out`).
TRIGRAM_FALLBACK_MS = 1000
# Smallest word (characters of \w) a query needs for the fallback: shorter words share a trigram with about half of the titles.
TRIGRAM_MIN_WORD = 3


class LexicalResults(list):
    """A list of search hits that also carries whether the trigram fallback ran out of time."""
    fuzzy_timed_out = False


def trigram_wanted(q, found, limit):
    """True when the fallback should run: fewer than `limit` hits and a query with a word of 3 or more characters."""
    return bool(q) and found < limit and any(len(word) >= TRIGRAM_MIN_WORD for word in re.findall(r'\w+',q,flags=re.UNICODE))


# Columns of memory.memory_items that Store._item reads; search paths select these instead of `*` so the three
# tsvector columns (large) never travel to Python. `alias` is a table alias such as 'i.'.
ITEM_COLUMNS = ('project_id','id','version','canonical_hash','event_type','payload','session_id','agent_id','occurred_at','deleted','superseded_by')


def item_columns(alias=''):
    return ','.join(alias+name for name in ITEM_COLUMNS)


def clean(value):
    """Convert database UUID/datetime values without leaking internal row objects."""
    return json.loads(json.dumps(value, default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)))
