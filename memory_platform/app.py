"""Private memory HTTP boundary. App construction never migrates or contacts providers."""
from __future__ import annotations

import time
import uuid
from fastapi import FastAPI, Request, Depends, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from . import models as m
from . import observability
from .auth import Auth
from .config import Settings
from .errors import MemoryError, Unauthorized, Forbidden
from .store import Store

COOKIE = 'memory_session'
# Headers a reverse proxy adds: a request that carries any of them did not come from inside the internal network.
PROXY_HEADERS = ('x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-forwarded-port', 'x-real-ip', 'forwarded')


class BodyLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            incoming = event.get('body', b'')
            if len(body)+len(incoming) > self.maximum:
                response = JSONResponse({'error': {'code': 'body_too_large', 'message': 'Request body exceeds limit'}, 'request_id': str(uuid.uuid4())}, status_code=413)
                return await response(scope, receive, send)
            body.extend(incoming)
            if not event.get('more_body'):
                break
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


def public_actor(actor):
    return {k: actor[k] for k in ('id', 'username', 'scopes', 'project_ids') if k in actor}


MOUNT_ROUTES = {'/mcp': 'mcp'}  # closed labels of the mounted sub-applications, for the access log


def mount_label(request):
    path = request.url.path
    for route in request.app.router.routes:
        mount = getattr(route, 'path', '') if route.__class__.__name__ == 'Mount' else ''
        if mount and (path == mount or path.startswith(mount+'/')):
            return MOUNT_ROUTES.get(mount, 'mount')
    return None


def create_app(settings=None, store=None, auth=None, retrieval=None, *, activity_duration=25.0, activity_poll_interval=2.0):
    settings = settings or Settings.from_env()
    if store is None:
        store = Store(settings.dsn, settings.project_maps, embedding_enabled=getattr(settings, 'embed_enabled', True))
        store.extraction_enabled = getattr(settings, 'extract_enabled', False)
    auth = auth or Auth(store, settings.allowed_origins, settings.session_ttl)
    if retrieval is None:
        from .retrieval import Retrieval
        retrieval = Retrieval(store, settings)
    app = FastAPI(title='Kairos', docs_url=None, redoc_url=None)
    app.state.store, app.state.auth, app.state.retrieval = store, auth, retrieval
    app.state.settings = settings
    app.add_middleware(BodyLimit, maximum=settings.max_body_bytes)

    @app.middleware('http')
    async def request_identity(request, call_next):
        request.state.request_id = str(uuid.uuid4())
        token = observability.REQUEST_ID.set(request.state.request_id)
        started = time.monotonic()
        mounted = mount_label(request)  # before routing: the mount rewrites the scope path

        def access(status):
            route = mounted or getattr(request.scope.get('route'), 'path', None) or 'unmatched'  # a mount's own inner routes are not ours; the template, never the concrete path (ids)
            health = route.startswith('/health/') and status < 500
            observability.log_event('http_request', 'debug' if health else 'info', method=request.method, route=route, status=status,
                                    duration_ms=observability.elapsed_ms(started))
        try:
            try:
                response = await call_next(request)
            except Exception:
                access(503)
                raise
            response.headers['X-Request-ID'] = request.state.request_id
            response.headers['Cache-Control'] = 'no-store'
            access(response.status_code)
            return response
        finally:
            observability.REQUEST_ID.reset(token)

    def error(request, code, message, status):
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        return JSONResponse({'error': {'code': code, 'message': message}, 'request_id': request_id}, status_code=status, headers={'X-Request-ID': request_id})

    @app.exception_handler(MemoryError)
    async def domain_error(request, exc):
        return error(request, exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return error(request, 'invalid_request', 'Request does not match the API contract', 422)

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        observability.log_failure('unhandled_exception', exc, 'error', request_id=getattr(request.state, 'request_id', None))
        return error(request, 'service_unavailable', 'Service is temporarily unavailable', 503)

    def identity(request: Request):
        header = request.headers.get('authorization', '')
        if header:
            scheme, _, token = header.partition(' ')
            if scheme.lower() != 'bearer' or not token:
                raise Unauthorized()
            actor = auth.authenticate_bearer(token)
        else:
            actor = auth.authenticate_session(request.cookies.get(COOKIE))
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            auth.require_csrf(actor, request.headers.get('x-csrf-token'), request.headers.get('origin'))
        return actor

    @app.get('/health/live', operation_id='memory_liveness')
    def live():
        return {'status': 'live'}

    @app.get('/health/ready', operation_id='memory_readiness')
    def ready():
        try:
            with store.transaction() as c:
                c.execute('SELECT version FROM memory.schema_versions LIMIT 1')
        except Exception as exc:
            observability.log_failure('readiness_failed', exc, 'warning')
            raise MemoryError('not_ready', 'Database migration is unavailable', 503)
        return {'status': 'ready'}

    def metrics_response():
        observability.refresh_queue_depth(store)
        return Response(observability.render_metrics(), media_type=observability.METRICS_CONTENT_TYPE)

    # Not part of the published API contract (include_in_schema=False). A single uvicorn process serves it, so the default in-process registry is enough.
    if settings.metrics_mode == 'internal':
        @app.get('/metrics', include_in_schema=False)
        def metrics_internal(request: Request):
            # nginx and the host proxy never route /metrics; a request that still carries proxy headers is treated as public.
            if any(header in request.headers for header in PROXY_HEADERS):
                return error(request, 'not_found', 'Not found', 404)
            return metrics_response()
    elif settings.metrics_mode == 'admin':
        @app.get('/metrics', include_in_schema=False)
        def metrics_admin(actor=Depends(identity)):
            if actor.get('is_admin') is not True:
                raise Forbidden()
            return metrics_response()

    @app.post('/v1/auth/login', operation_id='memory_login')
    def login(payload: m.Login, request: Request):
        if request.headers.get('origin') not in settings.allowed_origins:
            raise Forbidden('Invalid login origin')
        result = auth.login(payload.username, payload.password, request.client.host if request.client else '')
        response = JSONResponse({'actor': public_actor(result['actor']), 'csrf_token': result['csrf_token']})
        response.set_cookie(COOKIE, result['session_token'], max_age=settings.session_ttl, httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
        return response

    @app.get('/v1/auth/me', operation_id='memory_identity')
    def me(actor=Depends(identity)):
        return {'actor': public_actor(actor), 'csrf_token': auth.refresh_csrf(actor) if actor.get('credential_type') == 'session' else ''}

    @app.post('/v1/auth/logout', operation_id='memory_logout')
    def logout(request: Request, actor=Depends(identity)):
        auth.logout(request.cookies.get(COOKIE, ''))
        response = JSONResponse({'status': 'logged_out'})
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.get('/v1/projects', operation_id='memory_projects')
    def projects(actor=Depends(identity)):
        return {'projects': store.list_projects(actor)}

    @app.post('/v1/projects', operation_id='memory_create_project')
    def project(payload: m.ProjectInput, actor=Depends(identity)):
        return store.create_project(actor, payload)

    @app.get('/v1/projects/{project_id}/policy', operation_id='memory_get_policy')
    def policy(project_id: str, actor=Depends(identity)):
        return store.get_policy(actor, project_id)

    @app.get('/v1/projects/{project_id}/capture-policy', operation_id='kairos_capture_policy', response_model=m.CapturePolicy)
    def capture_policy(project_id: str, actor=Depends(identity)):
        return store.capture_policy(actor, project_id)

    @app.put('/v1/projects/{project_id}/policy', operation_id='memory_put_policy')
    def put_policy(project_id: str, payload: m.Policy, actor=Depends(identity)):
        return store.set_policy(actor, project_id, payload)

    @app.get('/v1/keys', operation_id='memory_keys')
    def keys(actor=Depends(identity)):
        return {'items': store.list_keys(actor)}

    @app.get('/v1/projects/{project_id}/work-state', operation_id='kairos_work_state_read')
    def work_state(project_id: str, list: str | None = Query(default=None, max_length=200),
                   include_closed: bool = False, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).work_read(actor, project_id, list, include_closed)

    @app.post('/v1/projects/{project_id}/work-state', operation_id='kairos_work_state_write')
    def write_work_state(project_id: str, payload: m.WorkStateChange, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).work_write(actor, project_id, payload.list, payload.fields,
                                           payload.request_id, payload.expected_version)

    @app.post('/v1/keys', operation_id='memory_create_key')
    def key(payload: m.KeyInput, actor=Depends(identity)):
        return store.create_key(actor, payload)

    @app.get('/v1/projects/{project_id}/team-work', operation_id='kairos_team_work_read')
    def team_work(project_id: str, list: str | None = Query(default=None, max_length=200), include_closed: bool = False, actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).team_read(actor, project_id, list, include_closed)

    @app.post('/v1/projects/{project_id}/team-work', operation_id='kairos_team_work_write')
    def write_team_work(project_id: str, payload: m.WorkStateChange, actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).team_write(actor, project_id, payload.list, payload.fields, payload.request_id, payload.expected_version)

    @app.get('/v1/projects/{project_id}/team-brief', operation_id='kairos_team_brief')
    def team_brief(project_id: str, limit: int = Query(default=20, ge=1, le=100), actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).team_brief(actor, project_id, limit)

    @app.post('/v1/observations', status_code=202, operation_id='kairos_observation_add')
    def observation_add(payload: m.Event, actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).observation_add(actor, payload)

    @app.post('/v1/observations/events', status_code=202, operation_id='kairos_observation_event')
    def observation_event(payload: m.Event, actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).observation_record_event(actor, payload)

    @app.get('/v1/tool-uses', operation_id='kairos_tool_uses')
    def tool_uses(project_id: str, session_id: str | None = Query(default=None, max_length=200), tool: str | None = Query(default=None, max_length=200),
                  limit: int = Query(default=20, ge=1, le=100), cursor: str | None = Query(default=None, max_length=1000), actor=Depends(identity)):
        from .extended_store import ExtendedStore
        return ExtendedStore(store).get_tool_uses(actor, project_id, session_id, tool, limit, cursor)

    @app.get('/v1/projects/{project_id}/corpora', operation_id='kairos_corpora')
    def corpora(project_id: str, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).list_corpora(actor, project_id)

    @app.post('/v1/projects/{project_id}/corpora', operation_id='kairos_build_corpus')
    def build_corpus(project_id: str, payload: m.CorpusSelection, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).build_corpus(actor, project_id, payload.name, payload.description, query=payload.query,
                                             types=payload.types, concepts=payload.concepts, files=payload.files,
                                             date_start=payload.date_start, date_end=payload.date_end, limit=payload.limit)

    @app.post('/v1/projects/{project_id}/corpora/{name}/prime', operation_id='kairos_prime_corpus')
    def prime_corpus(project_id: str, name: str, payload: m.CorpusPrime, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).prime_corpus(actor, project_id, name, fresh=payload.fresh)

    @app.post('/v1/projects/{project_id}/corpora/{name}/rebuild', operation_id='kairos_rebuild_corpus')
    def rebuild_corpus(project_id: str, name: str, payload: m.CorpusRebuild, actor=Depends(identity)):
        from .agent_store import AgentStore
        return AgentStore(store).rebuild_corpus(actor, project_id, name, payload.force, payload.expected_version)

    @app.post('/v1/projects/{project_id}/corpora/{name}/answers', operation_id='kairos_corpus_answer')
    async def corpus_answer(project_id: str, name: str, payload: m.CorpusAnswerRequest, actor=Depends(identity)):
        from .corpus_answers import CorpusAnswers
        return await CorpusAnswers(store, settings).answer(actor, project_id, name, payload.question, payload.request_id,
                                                          payload.expected_session_id, payload.expected_generation)

    @app.get('/v1/projects/{project_id}/corpora/{name}/answers/{request_id}', operation_id='kairos_corpus_answer_status')
    def corpus_answer_status(project_id: str, name: str, request_id: str, actor=Depends(identity)):
        from .corpus_answers import CorpusAnswers
        return CorpusAnswers(store, settings).status(actor, project_id, name, request_id)

    @app.delete('/v1/keys/{key_id}', operation_id='memory_revoke_key')
    def revoke(key_id: str, actor=Depends(identity)):
        return store.revoke_key(actor, key_id)

    @app.get('/v1/users', operation_id='memory_users')
    def users(actor=Depends(identity)):
        return {'items': store.list_users(actor)}

    @app.post('/v1/users', operation_id='memory_create_user')
    def user(payload: m.UserInput, actor=Depends(identity)):
        return store.create_user(actor, payload)

    @app.post('/v1/events', status_code=202, operation_id='memory_ingest_event')
    def ingest(payload: m.Event, actor=Depends(identity)):
        return store.ingest_event(actor, payload)

    @app.get('/v1/events/{event_id}', operation_id='memory_event_receipt')
    def event_receipt(event_id: str, actor=Depends(identity)):
        return store.get_event_receipt(actor, event_id)

    @app.get('/v1/projects/{project_id}/events/{event_id}/status', operation_id='kairos_event_status')
    def event_status(project_id: str, event_id: uuid.UUID, actor=Depends(identity)):
        # The reconciliation of the `event_status` tool with a project (`mcp.py`), as one call: the receipt and its jobs, or an explicit absence.
        receipt = store.reconcile_capture(actor, project_id, str(event_id))
        if receipt is None:
            return {'found': False, 'event_id': str(event_id), 'project_id': project_id}
        jobs = [store.get_job(actor, job_id) for job_id in receipt['jobs']]
        return {'receipt': receipt, 'jobs': jobs,
                'complete': receipt['status'] != 'superseded' and all(job['state'] == 'succeeded' for job in jobs)}

    @app.get('/v1/jobs/{job_id}', operation_id='memory_job')
    def job(job_id: str, actor=Depends(identity)):
        return store.get_job(actor, job_id)

    @app.get('/v1/projects/{project_id}/documents/{document_id}', operation_id='memory_document_status')
    def document_status(project_id: str, document_id: str, actor=Depends(identity)):
        return store.document_status(actor, project_id, document_id)

    @app.get('/v1/projects/{project_id}/manifest', operation_id='memory_document_manifest')
    def manifest(project_id: str, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = None, actor=Depends(identity)):
        return store.document_manifest(actor, project_id, limit=limit, cursor=cursor)

    @app.post('/v1/projects/{project_id}/documents', status_code=202, operation_id='memory_publish_document')
    def publish(project_id: str, payload: m.Document, actor=Depends(identity)):
        return store.publish_document(actor, project_id, payload)

    @app.delete('/v1/projects/{project_id}/documents/{document_id}', status_code=202, operation_id='memory_delete_document')
    def remove(project_id: str, document_id: str, version: int = Query(ge=1), actor=Depends(identity)):
        try:
            document_id = str(uuid.UUID(document_id))
        except ValueError:
            raise MemoryError('invalid_id', 'Invalid document ID', 422)
        return store.delete_document(actor, project_id, document_id, version)

    @app.post('/v1/search', operation_id='memory_search')
    async def search(payload: m.Search, actor=Depends(identity)):
        return await retrieval.search(actor, payload)

    @app.post('/v1/details', operation_id='memory_details')
    async def details(payload: m.Details, actor=Depends(identity)):
        return await retrieval.details(actor, payload)

    @app.post('/v1/context', operation_id='memory_context')
    async def context(payload: m.Context, actor=Depends(identity)):
        return await retrieval.context(actor, payload)

    @app.post('/v1/graph', operation_id='memory_graph')
    def graph(payload: m.Search, actor=Depends(identity)):
        return store.graph_data(actor, payload.model_dump(mode='json', exclude_none=True))

    @app.post('/v1/timeline', operation_id='memory_timeline')
    async def timeline(payload: m.Timeline, actor=Depends(identity)):
        return await retrieval.timeline(actor, payload)

    def listing(kind, method):
        from .activity import page_anchor, page_cursor
        def endpoint(project_id: str, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = Query(default=None, max_length=4000),
                     category: str = Query(default='', max_length=200), session_id: str = Query(default='', max_length=200),
                     q: str = Query(default='', max_length=4000), actor=Depends(identity)):
            if kind in ('observations', 'rules', 'activity-log') or (kind in ('notes', 'sessions', 'jobs', 'history') and (category or session_id or q)):
                from .portal_store import PortalStore
                return PortalStore(store).page(actor, project_id, kind, category=category, session_id=session_id, query=q, limit=limit, cursor=cursor)
            if category or session_id or q:
                raise MemoryError('unsupported_filter', 'This collection does not support content filters', 422)
            anchor = page_anchor(cursor, kind, project_id)
            values = method(actor, project_id, limit=min(limit+1, 100), cursor=anchor)
            items, more = values[:limit], len(values) > limit
            def item_id(item):
                return str(item.get('event_id', item.get('id', item.get('item_id', ''))))
            if items and not more and len(items) == limit:
                more = bool(method(actor, project_id, limit=1, cursor=item_id(items[-1])))
            next_cursor = page_cursor(kind, project_id, item_id(items[-1])) if items and more else None
            return {'items': items, 'next_cursor': next_cursor, 'has_more': more}
        return endpoint
    for name in ('sessions', 'notes', 'jobs', 'history'):
        method = getattr(store, 'history' if name == 'history' else 'list_'+name)
        app.add_api_route('/v1/'+name, listing(name, method), methods=['GET'], operation_id='memory_'+name)
    for name in ('observations', 'rules', 'activity-log'):
        app.add_api_route('/v1/'+name, listing(name, None), methods=['GET'], operation_id='kairos_'+name.replace('-', '_'))

    @app.get('/v1/activity', operation_id='memory_activity')
    async def activity(request: Request, project_id: str, cursor: str | None = Query(default=None, max_length=4000), actor=Depends(identity)):
        import asyncio
        from .activity import stream_activity
        origin = request.headers.get('origin')
        if origin is not None and origin not in settings.allowed_origins:
            raise Forbidden('Invalid activity origin')
        # Browser reconnect headers describe the newest delivered event, while
        # the URL can still contain the original, older cursor.
        anchor = request.headers.get('last-event-id') or cursor
        if anchor and len(anchor) > 4000:
            raise MemoryError('invalid_cursor', 'Activity cursor exceeds its supported bound', 400)
        first = await asyncio.to_thread(store.list_activity, actor, project_id, cursor=anchor, limit=50)
        return StreamingResponse(stream_activity(request, store, actor, project_id, first,
                                                 duration=activity_duration, poll_interval=activity_poll_interval, initial_cursor=anchor),
                                 media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.get('/v1/stats', operation_id='memory_stats')
    def stats(project_id: str, actor=Depends(identity)):
        return store.stats(actor, project_id)

    @app.post('/v1/jobs/{job_id}/retry', operation_id='memory_retry_job')
    def retry(job_id: str, actor=Depends(identity)):
        return store.retry_job(actor, job_id)

    from .mcp import mount_mcp
    mount_mcp(app, auth, retrieval, store)
    return app


def main():
    import uvicorn
    observability.configure_logging()
    # One process only: the Prometheus registry lives in it (no multiprocess mode). Our own JSON access line replaces uvicorn's text one.
    uvicorn.run(create_app(), host='0.0.0.0', port=8790, log_config=None, access_log=False)


if __name__ == '__main__':
    main()
