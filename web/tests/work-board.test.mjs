import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import { webcrypto } from 'node:crypto';

const tree = node => [node, ...node.children.flatMap(tree)];
const tick = async () => { for (let n = 0; n < 8; n++) await new Promise(resolve => setImmediate(resolve)); };
const sample = () => ({ project: 'alpha', lists: [{ list: 'Revisión: "Árbol" 🌳', version: 3, hash: 'verified-fixture', updated_at: '2026-11-04T10:00:00Z',
  state: { fields: { description: '<img src=x onerror=alert(1)>', needs_input: false }, tasks: { 'Conservar nota:uno,dos': { status: 'doing' }, 'Comprobar persistencia': { status: 'done' } } } }] });

async function fixture({ writable = true, handler, category = '' } = {}) {
  class Element extends EventTarget {
    constructor(tag) { super(); this.tagName = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.value = ''; this.text = ''; }
    append(...children) { this.children.push(...children); if (this.tagName === 'select' && children.length && !this.value) this.value = children[0].value; }
    replaceChildren(...children) { this.children = []; this.text = ''; this.append(...children); }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return this.text + this.children.map(child => child.textContent).join(' '); }
    get childNodes() { return this.children; }
    set innerHTML(_) { throw new Error('Untrusted work state must remain text'); }
    setAttribute(key, value) { this.attributes[key] = value; }
  }
  const document = { createElement: tag => new Element(tag) };
  const context = vm.createContext({ document, Intl, Date, crypto: webcrypto, AbortController, console });
  const cache = new Map();
  async function load(url) {
    if (cache.has(String(url))) return cache.get(String(url));
    const code = stripTypeScriptTypes(await readFile(url, 'utf8'), { mode: 'strip' });
    const module = new vm.SourceTextModule(code, { context, identifier: String(url) }); cache.set(String(url), module);
    await module.link(specifier => load(new URL(specifier, url))); return module;
  }
  const module = await load(new URL('../src/work-board.ts', import.meta.url)); await module.evaluate();
  const target = new Element('main'); const controller = new AbortController(); const calls = []; const messages = [];
  const api = { async request(path, method, body, signal) { calls.push({path, method, body: body && JSON.parse(JSON.stringify(body)), signal});
    const result = await handler?.(path, method, body); return result === undefined ? sample() : result; } };
  module.namespace.mountWorkBoard({ target, api, projects: [{ id: 'alpha', title: 'Proyecto Ágil', capture_mode: 'summary' }], signal: controller.signal, writable, category, announce: message => messages.push(message) });
  await tick();
  const find = predicate => tree(target).find(predicate);
  return { target, calls, messages, controller, find, async click(text) { const button = find(node => node.tagName === 'button' && node.textContent === text); assert.ok(button, 'Missing '+text); button.dispatchEvent(new Event('click')); await tick(); return button; } };
}

test('work cards use persisted Unicode state, explicit counters and safe text', async () => {
  const app = await fixture();
  assert.match(app.target.textContent, /Revisión: "Árbol" 🌳/);
  assert.match(app.target.textContent, /1 de 2 tareas finalizadas/);
  assert.match(app.target.textContent, /1 de 1 listas · 2 tareas guardadas/);
  assert.match(app.target.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(app.find(node => node.tagName === 'img'), undefined);
  assert.equal(app.calls[0].path, '/v1/projects/alpha/work-state?include_closed=true');
});

test('search and status filter the loaded work without another API request', async () => {
  const app = await fixture(); const query = app.find(node => node.tagName === 'input');
  query.value = 'no-existe'; query.dispatchEvent(new Event('input')); assert.match(app.target.textContent, /Sin coincidencias/);
  query.value = 'ÁRBOL'; query.dispatchEvent(new Event('input')); assert.match(app.target.textContent, /Ver tareas y detalles/);
  const state = app.find(node => node.tagName === 'select'); state.value = 'done'; state.dispatchEvent(new Event('change'));
  assert.match(app.target.textContent, /Sin coincidencias/); assert.equal(app.calls.length, 1);
});

test('uncertain completion retries the exact request ID, fields and revision', async () => {
  let writes = 0;
  const app = await fixture({ handler(path, method) { if (method === 'POST' && ++writes === 1) throw new Error('Uncertain fixture response'); } });
  await app.click('Completar'); assert.match(app.target.textContent, /Reintentar confirmación/);
  await app.click('Reintentar confirmación');
  const requests = app.calls.filter(call => call.method === 'POST');
  assert.equal(requests.length, 2); assert.deepEqual(requests[0].body, requests[1].body);
  assert.equal(requests[0].body.expected_version, 3);
  assert.equal(requests[0].body.fields.task, 'Conservar nota:uno,dos');
  assert.match(requests[0].body.request_id, /^[a-f0-9-]{36}$/);
});

test('read-only work stays readable without offering mutation controls', async () => {
  const app = await fixture({ writable: false });
  assert.match(app.target.textContent, /Conservar nota:uno,dos/);
  assert.equal(app.find(node => node.textContent === 'Completar'), undefined);
  assert.ok(app.calls.every(call => call.method === 'GET'));
});

test('leaving a view prevents a late response from rendering its cards', async () => {
  let resolve;
  const app = await fixture({ handler() { return new Promise(done => { resolve = done; }); } });
  app.controller.abort(); app.target.replaceChildren(); resolve(sample()); await tick();
  assert.equal(app.target.textContent, '');
});

test('team work uses its own read and write endpoint and shows attribution as text', async () => {
  const app=await fixture({handler(path){if(path.includes('/team-work'))return{...sample(),lists:sample().lists.map(row=>({...row,updated_by:'Ana: <img src=x> 🌳'}))};}});
  const visibility=app.find(n=>n.attributes['aria-label']==='Visibilidad del trabajo');visibility.value='team';visibility.dispatchEvent(new Event('change'));await tick();
  assert.ok(app.calls.some(c=>c.path==='/v1/projects/alpha/team-work?include_closed=true'));assert.match(app.target.textContent,/Última edición: Ana: <img src=x> 🌳/);assert.equal(app.find(n=>n.tagName==='img'),undefined);
  await app.click('Completar');const write=app.calls.find(c=>c.method==='POST');assert.equal(write.path,'/v1/projects/alpha/team-work');assert.equal(write.body.expected_version,3);
});

test('selected category only shows work explicitly categorized on list or task', async () => {
  const unrelated=await fixture({category:'Diseño'});assert.match(unrelated.target.textContent,/Sin coincidencias/);
  const explicit=await fixture({category:'Diseño',handler(){const value=sample();value.lists[0].state.tasks['Conservar nota:uno,dos'].category='Diseño';return value;}});
  assert.match(explicit.target.textContent,/Ver tareas y detalles/);assert.match(explicit.target.textContent,/category: Diseño/);
});

test('manual tasks fence existing and new list versions and preserve Unicode assignment/category', async () => {
  for(const [name,version] of [['Revisión: "Árbol" 🌳',3],['Lista nueva',0]]){
    const app=await fixture({category:'Diseño'});app.find(n=>n.name==='work-list').value=name;app.find(n=>n.name==='work-task').value='Tarea: "sí", árbol 🌳';app.find(n=>n.name==='work-owner').value='Inés';
    app.find(n=>n.tagName==='form').dispatchEvent(new Event('submit',{cancelable:true}));await tick();
    const sent=app.calls.find(c=>c.method==='POST');assert.equal(sent.path,'/v1/projects/alpha/work-state');assert.equal(sent.body.expected_version,version);assert.equal(sent.body.fields.category,'Diseño');assert.equal(sent.body.fields.assignee,'Inés');assert.equal(sent.body.fields.task,'Tarea: "sí", árbol 🌳');
  }
});

test('uncertain manual task freezes visibility and retries the exact destination and request body', async () => {
  let writes=0;const app=await fixture({handler(path,method){if(method==='POST'&&++writes===1)throw Error('uncertain');}});
  app.find(n=>n.name==='work-list').value='New';app.find(n=>n.name==='work-task').value='Original';const form=app.find(n=>n.tagName==='form');form.dispatchEvent(new Event('submit',{cancelable:true}));await tick();
  const visibility=app.find(n=>n.attributes['aria-label']==='Visibilidad del trabajo');assert.equal(visibility.disabled,true);assert.match(app.target.textContent,/Reintentar la misma tarea/);
  visibility.value='team';app.find(n=>n.name==='work-task').value='Changed';form.dispatchEvent(new Event('submit',{cancelable:true}));await tick();
  const sent=app.calls.filter(c=>c.method==='POST');assert.equal(sent.length,2);assert.equal(sent[0].path,sent[1].path);assert.deepEqual(sent[0].body,sent[1].body);assert.equal(sent[1].body.fields.task,'Original');assert.equal(visibility.disabled,false);
});
