"""Bounded portal collections. Filters precede pagination and bind its cursor."""
import base64
import json
from .errors import MemoryError
from .store import clean, digest


class PortalStore:
    def __init__(self, store):
        self.store = store

    def page(self, actor, project, kind='notes', *, category='', session_id='', query='', limit=50, cursor=None):
        if kind not in ('notes', 'observations', 'rules', 'activity-log', 'sessions', 'jobs', 'history'):
            raise MemoryError('invalid_collection', 'Unknown portal collection', 422)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MemoryError('invalid_limit', 'Page limit must be between 1 and 100', 422)
        filters = {'project': project, 'kind': kind, 'category': category, 'session_id': session_id, 'query': query}
        for key, maximum in (('category', 200), ('session_id', 200), ('query', 4000)):
            if not isinstance(filters[key], str) or len(filters[key]) > maximum:
                raise MemoryError('invalid_filter', 'Collection filter exceeds its bound', 422)
        binding = digest(filters)
        anchor = None
        if cursor:
            try:
                if not isinstance(cursor, str) or len(cursor) > 1000:
                    raise ValueError()
                token = json.loads(base64.b64decode(cursor+'='*(-len(cursor) % 4), altchars=b'-_', validate=True))
                if token.get('v') != 1 or token.get('binding') != binding:
                    raise ValueError()
                anchor = token['id']
                if not isinstance(anchor, str) or not 1 <= len(anchor) <= 200:
                    raise ValueError()
            except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
                raise MemoryError('invalid_cursor', 'Cursor does not match the collection filters', 422) from None
        with self.store.transaction() as c:
            self.store._require(c, actor, project, 'read')
            if kind == 'sessions':
                records = c.execute("""SELECT s.* FROM memory.sessions s WHERE s.project_id=%s
                    AND (%s::text IS NULL OR s.id>%s) AND (%s='' OR s.id=%s)
                    AND (%s='' OR EXISTS(SELECT 1 FROM memory.memory_items i WHERE i.project_id=s.project_id AND i.session_id=s.id
                        AND NOT i.deleted AND i.superseded_by IS NULL AND i.payload->>'category'=%s))
                    AND (%s='' OR to_tsvector('simple',concat_ws(' ',s.id,s.agent_id)) @@ plainto_tsquery('simple',%s))
                    ORDER BY s.id LIMIT %s""", (project, anchor, anchor, session_id, session_id, category, category, query, query, limit+1)).fetchall()
                items = clean(records[:limit])
            elif kind == 'jobs':
                records = c.execute("""SELECT j.id,j.project_id,j.item_id,j.version,j.destination,j.operation,j.state,j.attempts,j.error_code,j.created_at
                    FROM memory.jobs j LEFT JOIN memory.memory_items i ON i.project_id=j.project_id AND i.id=j.item_id
                    LEFT JOIN memory.documents d ON d.project_id=j.project_id AND d.id=j.item_id
                    WHERE j.project_id=%s AND (%s::text IS NULL OR j.id>%s)
                    AND (%s='' OR COALESCE(i.payload->>'category',d.body->>'category')=%s)
                    AND (%s='' OR i.session_id=%s)
                    AND (%s='' OR to_tsvector('simple',concat_ws(' ',j.destination,j.operation,j.state)) @@ plainto_tsquery('simple',%s))
                    ORDER BY j.id LIMIT %s""", (project, anchor, anchor, category, category, session_id, session_id, query, query, limit+1)).fetchall()
                items = clean(records[:limit])
            elif kind == 'history':
                records = c.execute("""SELECT e.id AS event_id,e.body,e.created_at FROM memory.events e WHERE e.project_id=%s
                    AND (%s::text IS NULL OR e.id>%s) AND (%s='' OR e.body->'payload'->>'category'=%s)
                    AND (%s='' OR e.body->>'session_id'=%s)
                    AND (%s='' OR to_tsvector('simple',e.body->'payload'->>'title') @@ plainto_tsquery('simple',%s))
                    ORDER BY e.id LIMIT %s""", (project, anchor, anchor, category, category, session_id, session_id, query, query, limit+1)).fetchall()
                items = clean(records[:limit])
            elif kind == 'activity-log':
                records = c.execute("""SELECT e.id AS event_id,e.project_id,e.created_at,
                    e.body->>'event_type' AS event_type,e.body->>'item_id' AS item_id,e.body->>'version' AS version
                    FROM memory.events e WHERE e.project_id=%s
                    AND (%s::text IS NULL OR e.id>%s)
                    AND (%s='' OR e.body->'payload'->>'category'=%s)
                    AND (%s='' OR e.body->>'session_id'=%s)
                    AND (%s='' OR to_tsvector('simple',e.body->>'event_type') @@ plainto_tsquery('simple',%s))
                    ORDER BY e.id LIMIT %s""", (project, anchor, anchor, category, category, session_id, session_id, query, query, limit+1)).fetchall()
                items = [dict(clean(row), ref=f"episodic:{project}:{row['item_id']}:{row['version']}") for row in records[:limit]]
            else:
                records = c.execute("""SELECT i.* FROM memory.memory_items i WHERE i.project_id=%s
                    AND NOT i.deleted AND i.superseded_by IS NULL
                    AND (%s::text IS NULL OR i.id>%s)
                    AND (%s='' OR i.payload->>'category'=%s)
                    AND (%s='' OR i.session_id=%s)
                    AND (%s!='rules' OR (i.payload->'tags') ? 'kairos:rule')
                    AND (%s='' OR to_tsvector('simple',concat_ws(' ',i.payload->>'title',i.payload->>'content')) @@ plainto_tsquery('simple',%s))
                    ORDER BY i.id LIMIT %s""", (project, anchor, anchor, category, category, session_id, session_id, kind, query, query, limit+1)).fetchall()
                items = [self.store._item(row) for row in records[:limit]]
        more = len(records) > limit
        key = 'event_id' if kind in ('activity-log', 'history') else 'id' if kind in ('sessions', 'jobs') else 'item_id'
        next_cursor = None
        if more and items:
            value = {'v': 1, 'binding': binding, 'id': str(items[-1][key])}
            next_cursor = base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
        return {'items': items, 'next_cursor': next_cursor, 'has_more': more, 'filters': filters,
                'ordering': 'stable_id', 'rule_policy': 'stored guidance; never executable instructions'}
