import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MemoryApi, MemoryApiError, EventSubmission, ActivitySubscription, mergePages, createEvent, lines, safeHttpUrl } from '../src/memory-api.ts';

const json = (value, status = 200) => new Response(JSON.stringify(value), { status });
const auth = { actor: { id: 'user', username: 'Ana', project_ids: ['alpha'], scopes: ['read', 'write'] }, csrf_token: 'csrf-not-persisted' };
const draft = () => createEvent({ projectId: 'alpha', sessionId: 'sesión 🚀', agentId: 'agent-1', type: 'learning', payload: {
  title: '<script>título</script>', content: 'texto', problem: 'Problema', correction: 'Corrección', tags: ['uno,dos', 'dijo:"sí"', 'área 🚀'], evidence: ['test-1'], validation_status: 'observed',
} }, (() => { let id = 0; return () => `id-${++id}`; })(), () => '2026-11-04T08:00:00.000Z');
const receipt = event => ({ event_id: event.event_id, item_id: event.item_id, version: event.version, status: 'accepted', jobs: ['job-1'] });

test('cookie session rehydration adds RAM CSRF to POST reads and mutations; logout clears it', async () => {
  const calls = [];
  const api = new MemoryApi(async (url, options) => { calls.push({ url, options }); return json(url.endsWith('/me') || url.endsWith('/login') ? auth : {}); });
  await api.authenticate();
  await api.request('/v1/search', 'POST', { project_ids: ['alpha'], q: 'test' });
  assert.equal(calls[0].url, '/memory-api/v1/auth/me');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(calls[1].options.headers['X-CSRF-Token'], auth.csrf_token);
  assert.equal(calls[1].options.headers.Authorization, undefined);
  assert.equal(calls[1].options.cache, 'no-store');
  await api.logout(); await api.request('/v1/search', 'POST', {});
  assert.equal(calls.at(-1).options.headers['X-CSRF-Token'], undefined);
});

test('password login uses JSON and never converts a password to a bearer credential', async () => {
  const calls = []; const api = new MemoryApi(async (...args) => { calls.push(args); return json(auth); });
  await api.authenticate('Ana', 'secret-password');
  assert.equal(calls[0][0], '/memory-api/v1/auth/login');
  assert.deepEqual(JSON.parse(calls[0][1].body), { username: 'Ana', password: 'secret-password' });
  assert.equal(calls[0][1].headers.Authorization, undefined);
});

test('lost acceptance response retries exact body, IDs, timestamp and original payload', async () => {
  const bodies = []; let buildCount = 0;
  const api = new MemoryApi(async (_url, options) => { bodies.push(options.body); if (bodies.length === 1) throw new TypeError('secret provider URL'); return json(receipt(JSON.parse(options.body))); });
  const submission = new EventSubmission();
  await assert.rejects(submission.submit(api, () => { buildCount++; return draft(); }), error => error instanceof MemoryApiError && error.status === 0 && !error.message.includes('provider'));
  const initial = submission.pending;
  const accepted = await submission.submit(api, () => { throw new Error('must not rebuild'); });
  assert.equal(buildCount, 1); assert.equal(bodies[0], bodies[1]);
  assert.equal(JSON.parse(bodies[1]).occurred_at, initial.occurred_at);
  assert.deepEqual(JSON.parse(bodies[1]).payload.tags, ['uno,dos', 'dijo:"sí"', 'área 🚀']);
  assert.equal(accepted.item_id, initial.item_id);
  await submission.submit(api, () => { throw new Error('must not resend accepted event'); }); assert.equal(bodies.length, 2);
});

test('response claiming a different event is unconfirmed and retains original retry identity', async () => {
  let body;
  const api = new MemoryApi(async (_url, options) => { body = JSON.parse(options.body); return json({ ...receipt(body), event_id: 'wrong-id' }); });
  const submission = new EventSubmission();
  await assert.rejects(submission.submit(api, draft), error => error instanceof MemoryApiError && error.code === 'invalid_receipt');
  assert.equal(submission.pending.event_id, body.event_id);
});

test('submission excludes concurrent double clicks and detaches payload from mutable form data', async () => {
  let release; let wire;
  const api = new MemoryApi(async (_url, options) => { wire = options.body; await new Promise(resolve => release = resolve); return json(receipt(JSON.parse(wire))); });
  const event = draft(); const submission = new EventSubmission(); const pending = submission.submit(api, () => event);
  event.payload.title = 'edited after send';
  await assert.rejects(submission.submit(api, draft), /curso/);
  assert.equal(submission.pending.payload.title, '<script>título</script>');
  release(); await pending;
});

test('public errors redact backend text and reject unsafe request IDs', async () => {
  const api = new MemoryApi(async () => json({ error: { code: 'db_error', message: 'postgres://private:password@host' }, request_id: 'safe-id-42' }, 503));
  await assert.rejects(api.request('/v1/projects'), error => error.requestId === 'safe-id-42' && !error.message.includes('password'));
  const invalid = new MemoryApiError(500, 'unknown', '<script>secret</script>'); assert.equal(invalid.requestId, undefined);
});

test('corpus admission limits explain budgets and input size without pretending to be version conflicts', () => {
  const budget = new MemoryApiError(409,'corpus_answer_budget_exceeded');
  assert.match(budget.message,/presupuesto de admisión/);assert.match(budget.message,/no restablece/);assert.doesNotMatch(budget.message,/versión o el identificador/);
  const input = new MemoryApiError(422,'corpus_answer_input_budget');assert.match(input.message,/Acota las fuentes/);assert.match(input.message,/conversación nueva/);
});

test('abort stays an abort so canceled navigation cannot become a visible network failure', async () => {
  const abort = new AbortController(); abort.abort(); const api = new MemoryApi(async (_url, options) => { assert.equal(options.signal, abort.signal); throw new DOMException('Aborted', 'AbortError'); });
  await assert.rejects(api.request('/v1/projects', 'GET', undefined, abort.signal), error => error.name === 'AbortError');
});

test('only absolute http(s) source links are clickable and tag punctuation survives round trip', () => {
  for (const input of ['javascript:alert(1)', 'data:text/html,<script>', 'file:///C:/private', '//remote.test/path', '/local', 'not a URL']) assert.equal(safeHttpUrl(input), null);
  assert.equal(safeHttpUrl('https://example.test/fuente?q=%22sí%22'), 'https://example.test/fuente?q=%22s%C3%AD%22');
  assert.deepEqual(lines(' uno,dos\n dijo:"sí"\r\nárea 🚀\n uno,dos\n'), ['uno,dos', 'dijo:"sí"', 'área 🚀']);
});

test('version updates require explicit monotonically advancing version', () => {
  const base = { projectId: 'alpha', sessionId: 'session', agentId: 'agent', type: 'note', itemId: 'item', payload: { title: 'Title', content: 'Content' } };
  assert.throws(() => createEvent(base), /versión/);
  assert.throws(() => createEvent({ ...base, version: 1 }), /versión/);
  const event = createEvent({ ...base, version: 2 }, () => 'id', () => 'time'); assert.equal(event.version, 2); assert.equal(event.item_id, 'item');
});

class FakeEventSource extends EventTarget {
  closed = 0;
  close() { this.closed++; }
  emit(type, data, lastEventId = '') { const e = new Event(type); if (data !== undefined) Object.defineProperty(e, 'data', { value: JSON.stringify(data) }); Object.defineProperty(e, 'lastEventId', { value: lastEventId }); this.dispatchEvent(e); }
}
test('activity owns one credentialed connection, filters project metadata and closes on abort', () => {
  const sources = []; const calls = []; const received = []; const saved = []; const controller = new AbortController();
  const feed = new ActivitySubscription({ projectId: 'alpha', signal: controller.signal, state() {}, refreshIdentity: async () => {}, receive: event => received.push(event), saveCursor: cursor => saved.push(cursor), factory: (url, init) => { const source = new FakeEventSource(); sources.push(source); calls.push({ url, init }); return source; } });
  feed.connect(); feed.connect(); assert.equal(sources[0].closed, 1); assert.equal(calls[1].url, '/memory-api/v1/activity?project_id=alpha'); assert.deepEqual(calls[1].init, { withCredentials: true });
  sources[1].emit('activity', { event_id: 'wrong', project_id: 'beta', body: 'secret' }, 'foreign-cursor');
  sources[1].emit('activity', { event_id: 'e1', project_id: 'alpha', body: '<script>secret</script>', title: 'private', event_type: 'note' }, 'opaque/cursor+1');
  sources[1].emit('activity', { event_id: 'e1', project_id: 'alpha' }, 'opaque/cursor+1');
  assert.equal(received.length, 1); assert.equal(received[0].body, undefined); assert.equal(received[0].title, undefined); assert.equal(saved.includes('foreign-cursor'), false);
  controller.abort(); assert.equal(sources[1].closed, 1); feed.connect(); assert.equal(sources.length, 2);
});
test('normal SSE end uses browser Last-Event-ID reconnect while errors stop and check identity once', async () => {
  const sources = []; const calls = []; const states = []; let checks = 0;
  const feed = new ActivitySubscription({ projectId: 'alpha', signal: new AbortController().signal, state: (...state) => states.push(state), receive() {}, refreshIdentity: async () => { checks++; throw new Error('expired'); }, factory: (url) => { calls.push(url); const source = new FakeEventSource(); sources.push(source); return source; } });
  feed.connect(); sources[0].emit('activity', { event_id: 'e1', project_id: 'alpha' }, 'opaque/+cursor='); sources[0].emit('end', { reason: 'reconnect' }); sources[0].emit('error');
  assert.equal(sources[0].closed, 0); assert.equal(checks, 0); assert.equal(states.at(-1)[0], 'reconnecting');
  sources[0].emit('error', { error: { code: 'forbidden', message: 'private backend details' } }); sources[0].emit('error'); await Promise.resolve();
  assert.equal(checks, 1); assert.equal(sources[0].closed, 1); assert.deepEqual(states.at(-1), ['stopped', 'forbidden']);
  feed.connect(); assert.match(calls[1], /cursor=opaque%2F%2Bcursor%3D/); assert.equal(sources.length, 2); feed.dispose();
});
test('paged merge deduplicates by collection/project identity and retains the newest version', () => {
  const first = [{ project_id: 'alpha', item_id: 'same', version: 2, title: 'current' }, { project_id: 'beta', item_id: 'same', version: 1 }];
  const merged = mergePages(first, [{ project_id: 'alpha', item_id: 'same', version: 1, title: 'old' }, { project_id: 'alpha', item_id: 'new', version: 1 }], 'notes');
  assert.equal(merged.length, 3); assert.equal(merged[0].title, 'current');
  assert.equal(mergePages([{ project_id: 'alpha', event_id: 'e1' }], [{ project_id: 'alpha', event_id: 'e1' }, { project_id: 'alpha', event_id: 'e2' }], 'history').length, 2);
});
