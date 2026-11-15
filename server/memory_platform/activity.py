"""Short authenticated activity streams backed by durable project events."""
import asyncio
import base64
import json
import time
from .errors import MemoryError
from .observability import log_failure


def page_cursor(kind, project_id, last_id):
    value = {'v': 1, 'kind': kind, 'project_id': project_id, 'last_id': last_id}
    return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')


def page_anchor(cursor, kind, project_id):
    if not cursor:
        return None
    try:
        if len(cursor) > 4000:
            raise ValueError()
        value = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor) % 4)))
        if value.get('v') != 1 or value.get('kind') != kind or value.get('project_id') != project_id:
            raise ValueError()
        last = value['last_id']
        if not isinstance(last, str) or not 1 <= len(last) <= 200:
            raise ValueError()
        return last
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError) as exc:
        raise MemoryError('invalid_cursor', 'Cursor does not match this project and collection', 422) from exc


def frame(event, value, cursor=None):
    identifier = 'id: '+cursor+'\n' if cursor else ''
    return identifier+'event: '+event+'\ndata: '+json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n\n'


async def stream_activity(request, store, actor, project_id, first_page, *, duration=25.0, poll_interval=2.0, initial_cursor=None):
    deadline = time.monotonic()+min(max(duration, 0.01), 25.0)
    next_ping = time.monotonic()+10.0
    page = first_page
    cursor = initial_cursor
    yield ': connected\n\n'
    while True:
        if await request.is_disconnected():
            return
        for item in page['items']:
            # No source text, captured body, credentials, or global statistics enter the feed.
            value = {key: item[key] for key in ('event_id', 'project_id', 'event_type', 'ref', 'created_at') if key in item}
            cursor = item.get('cursor', page.get('next_cursor'))
            yield frame('activity', value, cursor)
        cursor = page.get('next_cursor') or cursor
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            yield frame('end', {'reason': 'reconnect'})
            return
        if time.monotonic() >= next_ping:
            yield ': keep-alive\n\n'
            next_ping = time.monotonic()+10.0
        if not page.get('has_more'):
            await asyncio.sleep(min(max(poll_interval, 0.005), remaining))
        try:
            # The store checks live credentials and project grants again on every poll.
            page = await asyncio.to_thread(store.list_activity, actor, project_id, cursor=cursor, limit=50)
        except MemoryError as exc:
            yield frame('error', {'error': {'code': exc.code, 'message': exc.message}})
            return
        except Exception as exc:
            log_failure('activity_stream_failed', exc, 'warning')
            yield frame('error', {'error': {'code': 'activity_unavailable', 'message': 'Activity is temporarily unavailable'}})
            return
