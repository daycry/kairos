import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';

// Execute the actual portal and API. This boundary DOM verifies wiring, data
// safety and asynchronous transitions; browser layout/keyboard QA is separate.
const all = node => [node, ...(node.children ?? []).flatMap(all)];
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
async function waitFor(check) {
  const deadline = Date.now() + 3000;
  while (!check()) { if (Date.now() > deadline) throw new Error('Expected asynchronous UI state was not reached'); await new Promise(resolve => setTimeout(resolve, 10)); }
}
async function portal({ loggedIn = true, scopes = ['read', 'write', 'admin', 'publish', 'validate'], route = '?view=search', handler } = {}) {
  let document;
  class Element extends EventTarget {
    constructor(tag = 'div') {
      super(); this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.value = ''; this.text = ''; this.checked = false;
      this.className = ''; this.disabled = false; this.hidden = false;
      this.classList = { toggle: name => { const parts = new Set(this.className.split(' ')); const active = !parts.has(name); if (active) parts.add(name); else parts.delete(name); this.className = [...parts].join(' '); return active; }, remove: name => { this.className = this.className.split(' ').filter(p => p !== name).join(' '); } };
    }
    set innerHTML(_) { throw new Error('Captured HTML must never be inserted'); }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return this.text + this.children.map(c => c.textContent).join(' '); }
    get childNodes() { return this.children; }
    get firstElementChild() { return this.children[0]; }
    get isConnected() { return this === document?.body || !!this.parent?.isConnected; }
    append(...nodes) { nodes.forEach(n => { n.parent = this; this.children.push(n); if (this.tagName === 'select' && this.children.length === 1) this.value = n.value; }); }
    prepend(...nodes) { nodes.forEach(n => n.parent = this); this.children.unshift(...nodes); }
    insertBefore(node, reference) { node.parent = this; const index = this.children.indexOf(reference); if (index < 0) this.children.push(node); else this.children.splice(index, 0, node); }
    replaceChildren(...nodes) { this.children.forEach(n => n.parent = undefined); this.children = []; this.text = ''; this.append(...nodes); }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name]; }
    focus() { document.activeElement = this; }
    select() { this.focus(); }
    showModal() { this.open = true; this.focus(); }
    close() { this.open = false; this.dispatchEvent(new Event('close')); }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); this.parent = undefined; }
    reportValidity() { return true; }
    querySelectorAll(selector) { return all(this).slice(1).filter(node => selector === 'button' ? node.tagName === 'button' : selector === '[data-view]' ? !!node.dataset.view : selector === 'dialog' ? node.tagName === 'dialog' : false); }
  }
  class Input extends Element { constructor() { super('input'); } }
  class Textarea extends Element { constructor() { super('textarea'); } }
  class Select extends Element { constructor() { super('select'); } }
  const body = new Element('body'); const mount = new Element(); mount.id = 'memory-app'; body.append(mount);
  document = { body, activeElement: null, createElement: tag => tag === 'input' ? new Input() : tag === 'textarea' ? new Textarea() : tag === 'select' ? new Select() : new Element(tag),
    querySelector: selector => selector === '#memory-app' ? mount : selector === '.layout' ? all(body).find(n => n.className === 'layout') : null,
    querySelectorAll: selector => all(body).filter(n => selector === 'dialog' && n.tagName === 'dialog') };
  const calls = []; const location = { search: route, pathname: '/portal.html', origin: 'http://localhost:5173' };
  const streams = [];
  class ActivitySource extends EventTarget {
    constructor(url, init) { super(); this.url = url; this.init = init; this.closed = 0; streams.push(this); }
    close() { this.closed++; }
    emit(type, data, cursor = '') { const event = new Event(type); if (data !== undefined) Object.defineProperty(event, 'data', { value: JSON.stringify(data) }); Object.defineProperty(event, 'lastEventId', { value: cursor }); this.dispatchEvent(event); }
  }
  const actor = { id: 'ana-id', username: 'Ana', scopes, project_ids: ['alpha'] };
  const fetch = async (url, options) => {
    const path = url.replace('/memory-api', ''); const body = options.body ? JSON.parse(options.body) : undefined; calls.push({ path, options, body });
    const custom = await handler?.(path, body, options); if (custom !== undefined) return custom instanceof Response ? custom : new Response(JSON.stringify(custom));
    if (path === '/v1/auth/me' || path === '/v1/auth/login') return new Response(JSON.stringify(loggedIn || path.endsWith('login') ? { actor, csrf_token: 'csrf' } : { error: { code: 'unauthorized' } }), { status: loggedIn || path.endsWith('login') ? 200 : 401 });
    if (path === '/v1/projects') return new Response(JSON.stringify({ projects: [{ id: 'alpha', title: 'Proyecto Ágil 🚀', categories: ['Diseño / API'], capture_mode: 'summary' }] }));
    if (path.endsWith('/policy')) return new Response(JSON.stringify({ capture_mode: 'summary', temporal_projection: false }));
    return new Response(JSON.stringify({ items: [] }));
  };
  const context = vm.createContext({ document, window: { addEventListener() {} }, location, history: { pushState(_a, _b, url) { location.search = url.includes('?') ? `?${url.split('?')[1]}` : ''; } },
    HTMLElement: Element, HTMLInputElement: Input, HTMLTextAreaElement: Textarea, HTMLSelectElement: Select,
    Event, EventTarget, EventSource: ActivitySource, setTimeout, clearTimeout, fetch, Response, URL, URLSearchParams, AbortController, DOMException, Intl, crypto: webcrypto, TextEncoder,
    navigator: { clipboard: { async writeText() {} } }, confirm: () => true, console });
  const cache = new Map();
  async function load(url) {
    if (cache.has(String(url))) return cache.get(String(url));
    const code = String(url).endsWith('.css') ? '' : stripTypeScriptTypes(await readFile(url, 'utf8'), { mode: 'strip' });
    const mod = new vm.SourceTextModule(code, { context, identifier: String(url) }); cache.set(String(url), mod);
    await mod.link(specifier => load(new URL(specifier, url))); return mod;
  }
  await (await load(new URL('../src/memory-portal.ts', import.meta.url))).evaluate(); await tick();
  const find = predicate => all(body).find(predicate);
  const named = name => find(node => node.name === name);
  const click = async label => { const b = find(n => n.tagName === 'button' && n.textContent === label); assert.ok(b, `missing button ${label}`); b.dispatchEvent(new Event('click')); if (b.type === 'submit') { let form = b.parent; while (form && form.tagName !== 'form') form = form.parent; form?.dispatchEvent(new Event('submit', { cancelable: true })); } await tick(); return b; };
  const submit = async fieldName => { const input = named(fieldName); assert.ok(input); let form = input.parent; while (form.tagName !== 'form') form = form.parent; form.dispatchEvent(new Event('submit', { cancelable: true })); await tick(); };
  return { body, mount, calls, named, find, click, submit, context, document, streams };
}

test('authenticated portal rehydrates cookie without loading graph, querying sources, or storing secrets', async () => {
  const app = await portal();
  assert.match(app.mount.textContent, /Buscar y preparar contexto/);
  assert.match(app.mount.textContent, /Proyecto Ágil 🚀/); assert.match(app.mount.textContent, /Diseño \/ API/);
  assert.deepEqual(app.calls.map(c => c.path), ['/v1/auth/me', '/v1/projects']);
  assert.ok(app.find(n => n.href === '/'), 'brand returns to the public home');
  assert.ok(app.find(n => n.dataset.view === 'map'));
  assert.equal(app.named('q').type, 'search');
});

test('expired cookie leads to password login and successful login populates the portal', async () => {
  const app = await portal({ loggedIn: false });
  assert.match(app.mount.textContent, /Entra a tu memoria/);
  app.named('username').value = 'Ana'; app.named('password').value = 'secret-password'; await app.submit('username');
  assert.match(app.mount.textContent, /Buscar y preparar contexto/);
  assert.deepEqual(app.calls.find(c => c.path === '/v1/auth/login').body, { username: 'Ana', password: 'secret-password' });
  assert.doesNotMatch(app.body.textContent, /secret-password/);
});

test('private app without a view opens memory rather than a graph or search', async () => {
  const app = await portal({ route: '' });
  assert.match(app.document.title, /Memoria y aprendizajes/);
  assert.ok(app.calls.some(c => c.path.startsWith('/v1/notes?')));
  assert.equal(app.calls.some(c => ['/v1/search', '/v1/graph', '/v1/context'].includes(c.path)), false);
});

test('public entry and documentation never mount the private client', async () => {
  for (const page of ['index.html', 'docs.html']) {
    const html = await readFile(new URL('../'+page, import.meta.url), 'utf8');
    assert.match(html, /href="\/app\/"/);
    assert.match(html, /href="\/docs\/"/);
    assert.match(html, /src="\/src\/site\.ts"/);
    assert.doesNotMatch(html, /id="memory-app"|src="\/src\/main\.ts|memory-portal\.ts/);
  }
  const entry = await readFile(new URL('../src/site.ts', import.meta.url), 'utf8');
  assert.doesNotMatch(entry, /MemoryApi|fetch\(|import\(.*map/);
});

test('search renders captured content as text, preserves exact tags and sends bounded details', async () => {
  const title = '<img src=x onerror=alert(1)> "Guía" 🚀';
  const app = await portal({ handler: (path) => path === '/v1/search' ? { items: [{ ref: 'opaque-ref', item_id: 'item-1', project_id: 'alpha', layer: 'episodic', title, excerpt: '<script>data</script>', version: 1, validation_status: 'observed', tags: ['uno,dos', 'dijo:"sí"'], source: { uri: 'javascript:alert(1)' } }], partial: false, backends: { episodic: { status: 'succeeded' } } }
    : path === '/v1/details' ? { items: [{ title, content: '<b>raw captured</b>', evidence: ['prueba 1'] }] } : undefined });
  app.named('q').value = 'evitar error'; app.named('tags').value = 'uno,dos\ndijo:"sí"\nárea 🚀'; await app.submit('q');
  assert.deepEqual(app.calls.find(c => c.path === '/v1/search').body.tags, ['uno,dos', 'dijo:"sí"', 'área 🚀']);
  assert.match(app.mount.textContent, /<script>data<\/script>/);
  assert.equal(app.find(n => n.href?.startsWith('javascript:')), undefined);
  await app.click(title); assert.match(app.body.textContent, /<b>raw captured<\/b>/);
  assert.deepEqual(app.calls.find(c => c.path === '/v1/details').body, { refs: ['opaque-ref'], max_chars: 16000 });
});

test('a late search response cannot overwrite the newest results even if transport ignores abort', async () => {
  let releaseFirst; let releaseSecond;
  const response = title => ({ items: [{ ref: title, item_id: title, project_id: 'alpha', layer: 'episodic', title, excerpt: '', validation_status: 'unverified', version: 1 }], backends: {}, partial: false });
  const app = await portal({ handler: (path, body) => path === '/v1/search' ? new Promise(resolve => { if (body.q === 'first') releaseFirst = () => resolve(response('OLD RESULT')); else releaseSecond = () => resolve(response('CURRENT RESULT')); }) : undefined });
  app.named('q').value = 'first'; await app.submit('q'); app.named('q').value = 'second'; await app.submit('q');
  releaseSecond(); await tick(); releaseFirst(); await tick();
  assert.match(app.mount.textContent, /CURRENT RESULT/); assert.doesNotMatch(app.mount.textContent, /OLD RESULT/);
});

test('real job state/destination fields expose unknown reconciliation and real retry endpoint', async () => {
  const app = await portal({ route: '?view=operations', handler: path => path.startsWith('/v1/jobs?') ? { items: [{ id: 'job-1', state: 'unknown', destination: 'embed', project_id: 'alpha', version: 3, attempts: 2 }] } : undefined });
  assert.match(app.mount.textContent, /Por conciliar/); assert.match(app.mount.textContent, /Destino: embed/);
  await app.click('Conciliar resultado'); assert.equal(app.calls.filter(c => c.path === '/v1/jobs/job-1/retry').length, 1);
});

test('lost event response locks the draft and retries the original body with no duplicate IDs', async () => {
  let sends = 0;
  const app = await portal({ handler: (path, event) => { if (path === '/v1/events') { if (++sends === 1) throw new TypeError('lost response'); return { event_id: event.event_id, item_id: event.item_id, version: event.version, status: 'duplicate', jobs: [] }; } } });
  await app.click('＋ Nueva memoria'); app.named('title').value = 'Decisión'; app.named('content').value = '<script>captured</script>'; app.named('session_id').value = 'session-1'; await app.submit('title');
  assert.match(app.body.textContent, /Se conserva el envío/); assert.equal(app.named('title').parent.parent.disabled, true);
  await app.click('Reintentar el mismo envío');
  const sent = app.calls.filter(c => c.path === '/v1/events'); assert.equal(sent.length, 2); assert.deepEqual(sent[0].body, sent[1].body);
  assert.match(app.body.textContent, /Ya recibido/);
});

test('read-only users see no mutation control and cannot open admin settings', async () => {
  const app = await portal({ scopes: ['read'] });
  assert.equal(app.find(n => n.textContent === '＋ Nueva memoria'), undefined);
  await app.click('⚙ Configuración');
  assert.match(app.mount.textContent, /Configuración administrada/); assert.equal(app.calls.some(c => c.path === '/v1/keys'), false);
});

test('history unwraps server event body and preserves evidence and chronology', async () => {
  const app = await portal({ route: '?view=history', handler: path => path.startsWith('/v1/history?') ? { items: [{ event_id: 'e1', body: { project_id: 'alpha', occurred_at: '2026-11-04T08:00:00Z', version: 2, event_type: 'correction', session_id: 's1', agent_id: 'a1', payload: { title: 'Corrección vigente', content: 'Usar versión 2', evidence: ['Prueba #42'], validation_status: 'observed' } } }] } : undefined });
  assert.match(app.mount.textContent, /Corrección vigente/); assert.match(app.mount.textContent, /Prueba #42/); assert.match(app.mount.textContent, /Versión: 2/);
});

test('context preflight sends bounded common scope and makes missing validation explicit', async () => {
  const app = await portal({ handler: path => path === '/v1/context' ? { items: [], context: 'Experiencia observada; comprobar prueba.', warnings: ['Falta evidencia verificable.'], backends: { temporal: { status: 'failed' } }, partial: true } : undefined });
  app.named('q').value = 'preparar tarea'; await app.click('Preparar contexto para la tarea');
  const request = app.calls.find(c => c.path === '/v1/context');
  assert.deepEqual(request.body.project_ids, ['alpha']); assert.equal(request.body.max_chars, 12000);
  assert.match(app.mount.textContent, /Falta evidencia verificable/); assert.match(app.mount.textContent, /Resultados parciales/); assert.match(app.mount.textContent, /no reglas aprobadas/);
});

test('single gateway onboarding creates scoped key once and clears one-time secret on close', async () => {
  const app = await portal({ route: '?view=settings&project=alpha', handler: (path, body, options) => path === '/v1/keys' ? options.method === 'POST' ? { id: 'key-1', token: 'mp_ONE_TIME_SECRET', project_ids: body.project_ids, scopes: body.scopes } : { items: [] } : undefined });
  await app.click('Claves para agentes'); assert.match(app.mount.textContent, /una sola dirección/);
  assert.equal(app.named('agent-endpoint').value, 'http://localhost:5173/memory-api');
  app.named('name').value = 'Agente de pruebas'; await app.submit('name');
  const keyRequest = app.calls.find(c => c.path === '/v1/keys' && c.options.method === 'POST');
  assert.deepEqual(keyRequest.body, { name: 'Agente de pruebas', project_ids: ['alpha'], scopes: ['read'] });
  const secretField = app.named('new-key'); assert.equal(secretField.value, 'mp_ONE_TIME_SECRET');
  await app.click('Cerrar'); assert.equal(secretField.value, ''); assert.equal(app.named('new-key'), undefined);
  assert.doesNotMatch(app.body.textContent, /mp_ONE_TIME_SECRET/);
});

test('document publication computes source hash, attaches validation and preserves scoped destination', async () => {
  const app = await portal({ handler: (path, body) => path.endsWith('/documents') ? { item_id: body.document_id, version: 1, status: 'accepted', jobs: ['publication', 'index'] } : undefined });
  await app.click('Publicar documento'); app.named('document_title').value = 'Fuente'; app.named('document_content').value = 'Contenido aprobado';
  app.named('document_source').value = 'https://example.test/fuente'; app.named('document_evidence').value = 'Revisión humana #1';
  await app.submit('document_title'); await waitFor(() => app.body.textContent.includes('Documento recibido')); const request = app.calls.find(c => c.path.endsWith('/documents'));
  assert.ok(request); assert.equal(request.path, '/v1/projects/alpha/documents');
  const hash = [...new Uint8Array(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode('Contenido aprobado')))].map(byte => byte.toString(16).padStart(2, '0')).join('');
  assert.equal(request.body.source.sha256, hash); assert.deepEqual(request.body.validation, { status: 'validated', evidence: ['Revisión humana #1'], validated_by: 'ana-id' });
  assert.equal(request.body.version, 1); assert.match(app.body.textContent, /Documento recibido/);
});

test('full capture policy requires explicit review and sends only canonical policy fields', async () => {
  const app = await portal({ route: '?view=settings&project=alpha' });
  app.named('capture_mode').value = 'full'; await app.submit('capture_mode');
  assert.match(app.mount.textContent, /Confirma la revisión/); assert.equal(app.calls.some(c => c.options.method === 'PUT'), false);
  app.find(n => n.tagName === 'input' && n.type === 'checkbox' && n.parent.textContent.includes('He revisado')).checked = true;
  await app.submit('capture_mode'); const request = app.calls.find(c => c.options.method === 'PUT');
  assert.deepEqual(request.body, { capture_mode: 'full', temporal_projection: false });
});

test('paged notes append opaque cursor, retain newest versions and preserve filters after append error', async () => {
  let attempts = 0;
  const note = (id, version, title) => ({ project_id: 'alpha', item_id: id, title, content: 'Texto', version, event_type: 'note' });
  const app = await portal({ route: '?view=memory&project=alpha', handler: path => {
    if (!path.startsWith('/v1/notes?')) return;
    if (!path.includes('cursor=')) return { items: [note('one', 2, 'Primera nota')], next_cursor: 'opaque/+page=', has_more: true };
    if (++attempts === 1) return new Response(JSON.stringify({ error: { code: 'unavailable' } }), { status: 503 });
    return { items: [note('one', 1, 'Versión vieja'), note('two', 1, 'Segunda nota')], next_cursor: null, has_more: false };
  } });
  app.named('list-filter').value = 'nota'; app.named('list-filter').dispatchEvent(new Event('input'));
  await app.click('Cargar más'); assert.match(app.mount.textContent, /Primera nota/); assert.equal(app.named('list-filter').value, 'nota');
  await app.click('Reintentar carga'); assert.match(app.mount.textContent, /Segunda nota/); assert.doesNotMatch(app.mount.textContent, /Versión vieja/);
  assert.ok(app.calls.some(c => c.path.includes('cursor=opaque%2F%2Bpage%3D'))); assert.match(app.mount.textContent, /2 cargados/);
});

test('activity uses one selected-project cookie stream, is metadata-only and closes on navigation/logout', async () => {
  const app = await portal({ route: '?view=search&project=alpha', scopes: ['read'] });
  assert.equal(app.streams.length, 1); assert.equal(app.streams[0].init.withCredentials, true);
  app.streams[0].emit('activity', { event_id: 'e1', project_id: 'alpha', body: '<script>PRIVATE</script>', ref: 'https://evil.test' }, 'cursor-one'); await tick();
  assert.match(app.mount.textContent, /Hay actividad nueva/); assert.doesNotMatch(app.mount.textContent, /PRIVATE/); assert.equal(app.calls.some(c => c.path.includes('details')), false);
  await app.click('◎ Sesiones y agentes'); assert.equal(app.streams[0].closed, 1); assert.equal(app.streams.length, 2); assert.match(app.streams[1].url, /cursor=cursor-one/);
  await app.click('Salir'); assert.equal(app.streams[1].closed, 1); assert.match(app.mount.textContent, /Entra a tu memoria/);
});

test('selected-project SSE failure performs one identity check and waits for explicit reconnect', async () => {
  const app = await portal({ route: '?view=search&project=alpha' });
  app.streams[0].emit('error', { error: { code: 'forbidden', message: '<script>private</script>' } }); app.streams[0].emit('error'); await tick();
  assert.equal(app.streams[0].closed, 1);
  assert.equal(app.calls.filter(c => c.path === '/v1/auth/me').length, 1, 'background activity must not rotate the session CSRF token');
  assert.equal(app.calls.filter(c => c.path === '/v1/projects').length, 2, 'recheck authenticated access without renewing a session token');
  assert.equal(app.streams.length, 1);
  assert.match(app.mount.textContent, /Revisa tu sesión/); assert.doesNotMatch(app.mount.textContent, /<script>private/);
  await app.click('Reconectar actividad'); assert.equal(app.streams.length, 2);
});

test('changing scope aborts a late page response and never appends it to the new view', async () => {
  let release;
  const app = await portal({ route: '?view=memory&project=alpha', handler: path => path.startsWith('/v1/notes?') ? path.includes('cursor=') ? new Promise(resolve => release = resolve) : { items: [{ item_id: 'initial', project_id: 'alpha', title: 'Primera nota', version: 1 }], has_more: true, next_cursor: 'opaque' } : undefined });
  await app.click('Cargar más'); await app.click('⌕ Buscar y contexto');
  release({ items: [{ item_id: 'late', project_id: 'alpha', title: 'LATE PRIVATE NOTE', version: 1 }], has_more: false, next_cursor: null }); await tick();
  assert.doesNotMatch(app.mount.textContent, /LATE PRIVATE NOTE/); assert.match(app.mount.textContent, /Buscar y preparar contexto/);
});

test('live memory batches metadata events into one lightweight notes refresh without retrieval or inference', async () => {
  let reads = 0; let fail = false;
  const app = await portal({ route: '?view=memory&project=alpha', handler: path => path.startsWith('/v1/notes?') ? fail ? new Response('{}', { status: 503 }) : { items: [{ item_id: 'note', project_id: 'alpha', title: ++reads > 1 ? 'Memoria nueva' : 'Memoria inicial', version: reads }], has_more: false, next_cursor: null } : undefined });
  app.streams[0].emit('activity', { event_id: 'one', project_id: 'alpha' }, 'cursor-1'); app.streams[0].emit('activity', { event_id: 'two', project_id: 'alpha' }, 'cursor-2');
  await waitFor(() => app.mount.textContent.includes('Memoria actualizada con la actividad recibida'));
  assert.equal(reads, 2); assert.match(app.mount.textContent, /Memoria nueva/);
  assert.equal(app.calls.some(c => ['/v1/search', '/v1/context', '/v1/graph'].includes(c.path)), false);
  fail = true; app.streams[0].emit('activity', { event_id: 'three', project_id: 'alpha' }, 'cursor-3');
  await waitFor(() => app.mount.textContent.includes('Vuelve a actualizar la lista.'));
  assert.match(app.mount.textContent, /Memoria nueva/); assert.doesNotMatch(app.mount.textContent, /Memoria actualizada con la actividad recibida/);
  await app.click('Salir');
});

test('background SSE after a failed read preserves the manual retry and its visible error', async () => {
  let failed = true; let reads = 0;
  const app = await portal({ route: '?view=memory&project=alpha', handler: path => {
    if (!path.startsWith('/v1/notes?')) return;
    reads++;
    return failed ? new Response('{}', { status: 503 }) : { items: [{ item_id: 'recovered', title: 'Recuperada manualmente', version: 1 }], has_more: false };
  } });
  const retry = app.find(node => node.tagName === 'button' && node.textContent === 'Reintentar carga');
  assert.equal(retry.hidden, false);
  failed = false;
  app.streams[0].emit('activity', { event_id: 'history', project_id: 'alpha' }, 'history-cursor');
  await waitFor(() => app.mount.textContent.includes('Vuelve a actualizar la lista.'));
  assert.equal(reads, 1);
  assert.equal(retry.hidden, false);
  await app.click('Reintentar carga');
  assert.equal(reads, 2); assert.match(app.mount.textContent, /Recuperada manualmente/);
  await app.click('Salir');
});

test('private marker guidance remains text and redacted receipt clears sensitive draft fields', async () => {
  const app = await portal({ handler: (path, event) => path === '/v1/events' ? { event_id: event.event_id, item_id: event.item_id, version: event.version, status: 'accepted', jobs: [], redacted: true } : undefined });
  await app.click('＋ Nueva memoria'); assert.match(app.body.textContent, /<private>…<\/private>/);
  app.named('title').value = 'Nota sensible'; app.named('content').value = '<private>MY_PRIVATE_TEXT</private>'; app.named('session_id').value = 'session';
  await app.submit('title'); assert.match(app.body.textContent, /Memoria guardada con datos privados ocultos/);
  assert.equal(app.named('content').value, ''); assert.equal(app.named('title').value, '');
});

test('rules and observations use authorized project and category before pagination', async () => {
  for (const [view, endpoint] of [['rules','rules'],['observations','observations']]) {
    const app = await portal({route:`?view=${view}&project=alpha&category=${encodeURIComponent('Diseño / API')}`,handler:path => path.startsWith(`/v1/${endpoint}?`) ? {items:[{item_id:'safe-id',project_id:'alpha',title:'Guía: "Árbol" 🌳',content:'Texto <script>seguro</script>',version:1}],has_more:false} : undefined});
    const request = app.calls.find(c=>c.path.startsWith(`/v1/${endpoint}?`)); assert.ok(request);
    const query = new URL(request.path,'http://fixture').searchParams;
    assert.equal(query.get('project_id'),'alpha'); assert.equal(query.get('category'),'Diseño / API');
    assert.match(app.body.textContent,/Guía: "Árbol" 🌳/); assert.equal(app.find(n=>n.tagName==='script'),undefined);
  }
});

test('new rule is a scoped unverified note with explicit rule tag and preserved punctuation', async () => {
  const app = await portal({route:'?view=rules&project=alpha',handler:(path,event)=>path==='/v1/events'?{event_id:event.event_id,item_id:event.item_id,version:1,status:'accepted',jobs:[]}:undefined});
  await app.click('＋ Nueva regla');app.named('title').value='Regla: "área", árbol 🌳';app.named('content').value='Verificar evidencia antes de usar.';app.named('session_id').value='rule-session';app.named('tags').value='nota:uno,dos\ndijo:"sí"';await app.submit('title');
  const sent = app.calls.find(c=>c.path==='/v1/events').body;
  assert.equal(sent.project_id,'alpha');assert.deepEqual(sent.payload.tags,['nota:uno,dos','dijo:"sí"','kairos:rule']);assert.equal(sent.payload.validation_status,'unverified');
});

test('session details send session filter before each cursor page and preserve earlier notes', async () => {
  const app = await portal({route:'?view=sessions&project=alpha',handler:path=>{
    if(path.startsWith('/v1/sessions?'))return{items:[{session_id:'session:Árbol 🌳',project_id:'alpha',agent_id:'fixture'}]};
    if(path.startsWith('/v1/notes?'))return path.includes('cursor=')?{items:[{item_id:'second',title:'Segunda nota',version:1}],has_more:false}:{items:[{item_id:'first',title:'Primera nota',version:1}],has_more:true,next_cursor:'opaque:área'};
  }});
  await app.click('Ver memoria de esta sesión');await app.click('Cargar más de esta sesión');
  const pages=app.calls.filter(c=>c.path.startsWith('/v1/notes?'));assert.equal(pages.length,2);
  for(const page of pages){const q=new URL(page.path,'http://fixture').searchParams;assert.equal(q.get('session_id'),'session:Árbol 🌳');assert.equal(q.get('project_id'),'alpha');assert.equal(q.get('limit'),'50');}
  assert.equal(new URL(pages[1].path,'http://fixture').searchParams.get('cursor'),'opaque:área');assert.match(app.body.textContent,/Primera nota/);assert.match(app.body.textContent,/Segunda nota/);
});

test('activity timeline renders only delivery metadata even when server accidentally adds private content', async () => {
  const app=await portal({route:'?view=activity&project=alpha',scopes:['read'],handler:path=>path.startsWith('/v1/activity-log?')?{items:[{event_id:'delivery-1',project_id:'alpha',event_type:'note',ref:'episodic:alpha:<img>:1',created_at:'2026-11-06T10:00:00Z',body:'PRIVATE BODY NEVER DISPLAY',content:'PRIVATE CONTENT NEVER DISPLAY'}]}:undefined});
  assert.match(app.body.textContent,/Entrega delivery-1/);assert.match(app.body.textContent,/no implica extracción terminada/);assert.doesNotMatch(app.body.textContent,/PRIVATE (BODY|CONTENT)/);
  const card=app.find(n=>n.className.includes('activity-card'));assert.ok(card);assert.equal(all(card).some(n=>n.tagName==='img'),false);
  assert.equal(app.find(n=>n.textContent==='＋ Nueva memoria'),undefined);assert.ok(app.calls.every(c=>c.options.method==='GET'));
});

test('a stale project URL cannot query an unauthorized observation scope', async () => {
  const app=await portal({route:'?view=observations&project=unauthorized-project'});
  const reads=app.calls.filter(c=>c.path.startsWith('/v1/observations?'));assert.equal(reads.length,1);
  assert.equal(new URL(reads[0].path,'http://fixture').searchParams.get('project_id'),'alpha');assert.equal(app.calls.some(c=>c.path.includes('unauthorized-project')),false);
});
