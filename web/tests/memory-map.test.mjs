import { test } from 'node:test';
import assert from 'node:assert/strict';
import { graphSnapshot, mapColors, graphNodeLabel, mountMemoryMap } from '../src/memory-map.ts';
import { readFile } from 'node:fs/promises';

const fixture = () => ({ nodes: [
  { id: 'a', name: 'Guía <img src=x onerror=alert(1)> 🚀', type: 'document', project_id: 'alpha', category: 'API', ref: 'doc-ref', validation_status: 'validated' },
  { id: 'b', name: 'Lección "sí",no', type: 'memory', project_id: 'alpha', category: 'Operaciones', ref: 'memory-ref', tags: ['uno,dos', 'dijo:"sí"'] },
  { id: 'c', name: 'Entidad', type: 'entity', project_id: 'alpha' },
], links: [{ source: 'a', target: 'b', label: 'documenta', project_id: 'alpha', evidence_refs: ['evidence-ref'] }, { source: 'b', target: 'c', label: 'menciona', project_id: 'alpha' }], stats: { nodes: 3, links: 2, memories: 1, documents: 1, entities: 1 }, partial: false });
const scope = { project_ids: ['alpha'], q: '', categories: ['API'], tags: ['uno,dos'], layers: ['episodic', 'documental', 'temporal'], limit: 20 };
const all = node => [node, ...node.children.flatMap(all)];
const tick = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };
function dom(t) {
  class Element extends EventTarget {
    constructor(tag = 'div') { super(); this.tagName = tag; this.children = []; this.style = {}; this.attributes = {}; this.text = ''; this.value = ''; this.clientWidth = 900; this.clientHeight = 440; }
    set textContent(text) { this.text = String(text); this.children = []; }
    get textContent() { return this.text + this.children.map(c => c.textContent).join(' '); }
    set innerHTML(_) { throw new Error('unsafe HTML'); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.text = ''; this.children = nodes; }
    setAttribute(key, value) { this.attributes[key] = value; }
  }
  const globals = ['document', 'window', 'ResizeObserver'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  const doc = new EventTarget(); doc.createElement = tag => new Element(tag); doc.hidden = false;
  Object.defineProperty(globalThis, 'document', { configurable: true, value: doc }); Object.defineProperty(globalThis, 'window', { configurable: true, value: { matchMedia: () => ({ matches: false }) } });
  const observations = [];
  Object.defineProperty(globalThis, 'ResizeObserver', { configurable: true, value: class { constructor(callback) { this.callback = callback; observations.push(this); } observe() {} disconnect() { this.disconnected = true; } } });
  t.after(() => { for (const [key, descriptor] of globals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  return { target: new Element(), doc, observations };
}
function renderer() {
  const states = [];
  function Constructor() {
    const state = { destroyed: 0, paused: 0, calls: {} }; states.push(state);
    return new Proxy({}, { get(_target, name) {
      if (name === '_destructor') return () => state.destroyed++;
      return (...args) => { if (name === 'pauseAnimation') state.paused++; state.calls[name] = args; return state.instance; };
    }, set() { return true; } });
  }
  // Keep a stable fluent instance for every constructor invocation.
  function Runtime() { const value = new Constructor(); states.at(-1).instance = value; return value; }
  return { states, module: { default: Runtime } };
}

test('snapshot preserves Unicode and refs, rejects cross-project edges, and remains immutable under renderer mutations', () => {
  const source = fixture(); source.nodes.push({ id: 'foreign', name: 'Foreign', type: 'entity', project_id: 'beta' });
  source.links.push({ source: 'a', target: 'foreign', project_id: 'alpha', label: 'must not join' });
  const result = graphSnapshot(source); assert.equal(result.links.length, 2); assert.equal(result.partial, true); assert.equal(result.stats.nodes, 4);
  result.links[0].source = result.nodes[0]; result.nodes[1].tags.push('changed');
  assert.equal(source.links[0].source, 'a'); assert.deepEqual(source.nodes[1].tags, ['uno,dos', 'dijo:"sí"']);
  assert.throws(() => graphSnapshot({ ...fixture(), nodes: [fixture().nodes[0], fixture().nodes[0]] }), /solicitud/);
});

test('project/category colors are stable and distinguish categories; node labels use safe DOM', t => {
  dom(t); const nodes = fixture().nodes; const colors = mapColors(nodes); const reversed = mapColors([...nodes].reverse());
  assert.equal(colors.get('a'), reversed.get('a')); assert.notEqual(colors.get('a'), colors.get('b'));
  const label = graphNodeLabel(nodes[0]); assert.match(label.textContent, /<img src=x onerror=alert\(1\)> 🚀/);
  assert.equal(all(label).some(n => n.tagName === 'img'), false);
});

test('map requests one gateway scope, renders labeled counts/list, and opens authorized source/evidence refs', async t => {
  const { target } = dom(t); const runtime = renderer(); const calls = []; const opened = []; const controller = new AbortController();
  const map = mountMemoryMap({ target, signal: controller.signal, input: scope, api: { async request(...args) { calls.push(args); return fixture(); } }, openSource: node => opened.push(node), announce() {}, loadRenderer: async () => runtime.module });
  await tick(); assert.equal(calls[0][0], '/v1/graph'); assert.deepEqual(calls[0][2], { ...scope, limit: 100 });
  assert.match(target.textContent, /Memorias/); assert.match(target.textContent, /Documentos/); assert.match(target.textContent, /Entidades/); assert.match(target.textContent, /Relaciones/);
  all(target).find(n => n.tagName === 'button' && n.textContent === fixture().nodes[0].name).dispatchEvent(new Event('click'));
  all(target).find(n => n.tagName === 'button' && n.textContent === 'Abrir evidencia 1').dispatchEvent(new Event('click'));
  assert.deepEqual(opened.map(n => n.ref), ['doc-ref', 'evidence-ref']);
  assert.equal(runtime.states.length, 1); assert.equal(runtime.states[0].calls.graphData[0].nodes.length, 3);
  map.dispose();
});

test('renderer import is skipped on empty maps and fallback list stays functional after WebGL error', async t => {
  const { target } = dom(t); let rendererLoads = 0; let response = { ...fixture(), nodes: [], links: [] };
  const map = mountMemoryMap({ target, signal: new AbortController().signal, input: scope, api: { async request() { return response; } }, openSource() {}, announce() {}, loadRenderer: async () => { rendererLoads++; throw new Error('WebGL unavailable'); } });
  await tick(); assert.equal(rendererLoads, 0); assert.match(target.textContent, /No hay elementos/);
  response = fixture(); await map.refresh(); await tick(); assert.equal(rendererLoads, 1); assert.match(target.textContent, /vista 3D no está disponible/);
  assert.match(target.textContent, /Guía <img/); assert.ok(all(target).find(n => n.textContent === 'Reintentar vista 3D')); map.dispose();
});

test('refresh and navigation dispose GPU loops and observers; delayed renderer import cannot resurrect a closed map', async t => {
  const { target, observations } = dom(t); const runtime = renderer(); const controller = new AbortController();
  let release; let imports = 0;
  const map = mountMemoryMap({ target, signal: controller.signal, input: scope, api: { async request() { return fixture(); } }, openSource() {}, announce() {}, loadRenderer: () => { imports++; return imports === 2 ? new Promise(resolve => release = () => resolve(runtime.module)) : Promise.resolve(runtime.module); } });
  await tick(); assert.equal(runtime.states.length, 1); await map.refresh(); await tick();
  assert.equal(runtime.states[0].destroyed, 1); assert.equal(observations[0].disconnected, true);
  controller.abort(); release(); await tick(); assert.equal(runtime.states.length, 1); map.dispose(); assert.equal(runtime.states[0].destroyed, 1);
});

test('late aborted graph response cannot replace newer map even when network ignores cancellation', async t => {
  const { target } = dom(t); let first; let second; let requests = 0; const runtime = renderer();
  const map = mountMemoryMap({ target, signal: new AbortController().signal, input: scope, api: { request() { return new Promise(resolve => { if (++requests === 1) first = resolve; else second = resolve; }); } }, openSource() {}, announce() {}, loadRenderer: async () => runtime.module });
  const newer = map.refresh(); const current = fixture(); current.nodes[0].name = 'CURRENT'; second(current); await newer; await tick(); first(fixture()); await tick();
  assert.match(target.textContent, /CURRENT/); assert.equal(runtime.states.length, 1); map.dispose();
});

test('initial portal entry only imports map and renderer dynamically', async () => {
  const portal = await readFile(new URL('../src/memory-portal.ts', import.meta.url), 'utf8'); const map = await readFile(new URL('../src/memory-map.ts', import.meta.url), 'utf8');
  assert.match(portal, /await import\('\.\/memory-map\.ts'\)/); assert.doesNotMatch(portal, /import\s+[^\n]+from\s+['"]3d-force-graph/);
  assert.match(map, /import\('3d-force-graph'\)/); assert.doesNotMatch(map, /from\s+['"]3d-force-graph/);
});
