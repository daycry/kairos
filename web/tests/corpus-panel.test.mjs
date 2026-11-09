import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import {webcrypto} from 'node:crypto';

const tree = n => [n,...n.children.flatMap(tree)];
const tick = async () => {for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));};
const saved = (primed=true) => ({name:'Árbol: "uno,dos" 🌳',version:2,count:3,primed,session_id:primed?'session-real':null,hash:'source-generation-hash'});
const answer = (id,status='completed') => ({request_id:id,status,session_id:'session-real',generation:2,model:'configured-model',reserved_token_units:240,
  result:{answer:'Respuesta: <img src=x onerror=alert(1)> "sí", árbol 🌳',citations:[{ref:'episodic:alpha:source:2',quote:'Cita: <script>texto</script>, "área" 🌳'}]}});
async function panel({projects=[{id:'alpha',title:'Proyecto Ágil'}],writable=true,category='',handler}={}){
  class Element extends EventTarget{
    constructor(tag){super();this.tagName=tag;this.children=[];this.attributes={};this.value='';this.text='';this.disabled=false;this.hidden=false;}
    append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);if(this.tagName==='select'&&this.children.length===1)this.value=n.value;}}
    replaceChildren(...nodes){this.children=[];this.text='';if(this.tagName==='select')this.value='';this.append(...nodes);}
    set textContent(v){this.text=String(v);this.children=[];}get textContent(){return this.text+this.children.map(n=>n.textContent).join(' ');}
    set innerHTML(_){throw Error('Untrusted corpus text cannot become HTML');}
    setAttribute(k,v){this.attributes[k]=v;}
    focus(options){this.focused=true;this.focusOptions=options;}
    scrollIntoView(options){this.scrolled=true;this.scrollOptions=options;}
  }
  const document={createElement:tag=>new Element(tag)};const context=vm.createContext({document,crypto:webcrypto,AbortController,console});const cache=new Map();
  async function load(url){if(cache.has(String(url)))return cache.get(String(url));const code=stripTypeScriptTypes(await readFile(url,'utf8'),{mode:'strip'});
    const m=new vm.SourceTextModule(code,{context,identifier:String(url)});cache.set(String(url),m);await m.link(s=>load(new URL(s,url)));return m;}
  const m=await load(new URL('../src/corpus-panel.ts',import.meta.url));await m.evaluate();const target=new Element('main');const controller=new AbortController();const calls=[];
  const api={async request(path,method='GET',body,signal){calls.push({path,method,body:body&&JSON.parse(JSON.stringify(body)),signal});const custom=await handler?.(path,method,body);return custom===undefined?{items:[saved()]}:custom;}};
  m.namespace.mountCorpusPanel({target,api,projects,signal:controller.signal,writable,category});await tick();
  const find=fn=>tree(target).find(fn);const named=name=>find(n=>n.name===name);
  const click=async label=>{const n=find(n=>n.tagName==='button'&&n.textContent===label);assert.ok(n,'missing '+label);n.dispatchEvent(new Event('click'));await tick();return n;};
  const submit=async name=>{let n=named(name);assert.ok(n,'missing '+name);while(n.tagName!=='form')n=n.parent;n.dispatchEvent(new Event('submit',{cancelable:true}));await tick();};
  return{target,calls,controller,find,named,click,submit};
}

test('opening a saved corpus reads metadata without invoking generation or priming',async()=>{
  const app=await panel();assert.equal(app.calls.length,1);assert.equal(app.calls[0].path,'/v1/projects/alpha/corpora');assert.equal(app.calls[0].method,'GET');
  assert.match(app.target.textContent,/Generación 2/);assert.match(app.target.textContent,/3 memorias/);
  assert.equal(app.find(n=>n.className==='corpus-builder').open,false);
});

test('all-project or empty scope requires selecting exactly one project and sends nothing',async()=>{
  for(const projects of [[],[{id:'alpha',title:'A'},{id:'beta',title:'B'}]]){const app=await panel({projects});assert.equal(app.calls.length,0);assert.match(app.target.textContent,/Selecciona un proyecto/);}
});

test('selection preserves exact tags and category; preparation is explicit before generation',async()=>{
  let corpus=[];const app=await panel({category:'Diseño: API',handler(path,method,body){if(method==='GET')return{items:corpus};if(path.endsWith('/prime')){corpus=[saved()];return{}};if(method==='POST'){corpus=[saved(false)];return{}}}});
  app.named('corpus-name').value='Árbol: "uno,dos" 🌳';app.named('corpus-query').value='fencing';app.named('corpus-tags').value='nota:uno,dos\ndijo:"sí"\nárea 🌳';await app.submit('corpus-name');
  const create=app.calls.find(c=>c.method==='POST');assert.deepEqual(create.body.concepts,['nota:uno,dos','dijo:"sí"','área 🌳']);assert.deepEqual(create.body.types,['Diseño: API']);assert.equal(create.body.limit,500);
  assert.equal(app.find(n=>n.textContent==='Enviar al modelo').disabled,true);await app.click('Preparar corpus');assert.deepEqual(app.calls.find(c=>c.path.endsWith('/prime')).body,{fresh:false});
  assert.equal(app.calls.some(c=>c.path.endsWith('/answers')),false);assert.equal(app.find(n=>n.textContent==='Enviar al modelo').disabled,false);
});

test('generated answer carries exact session generation and safe text-only source quotations',async()=>{
  const app=await panel({handler(path,method,body){if(path.endsWith('/answers'))return answer(body.request_id)}});
  app.named('corpus-question').value='¿Qué sabemos: "área", árbol 🌳?';await app.submit('corpus-question');
  const request=app.calls.find(c=>c.method==='POST');assert.equal(request.body.expected_session_id,'session-real');assert.equal(request.body.expected_generation,2);assert.match(request.body.request_id,/^[a-f0-9-]{36}$/);
  assert.match(app.target.textContent,/<img src=x onerror=alert\(1\)>/);assert.match(app.target.textContent,/<script>texto<\/script>/);assert.match(app.target.textContent,/episodic:alpha:source:2/);
  assert.equal(app.find(n=>n.tagName==='img'||n.tagName==='script'),undefined);assert.match(app.target.textContent,/Sin validar/);
  const card=app.find(n=>n.tagName==='article');assert.equal(card.tabIndex,-1);assert.equal(card.focused,true);assert.equal(card.scrolled,true);
});

test('lost generation response preserves request identity and only GET status can reconcile it',async()=>{
  let id;const app=await panel({handler(path,method,body){if(path.endsWith('/answers')&&method==='POST'){id=body.request_id;throw Error('Uncertain response');}if(path.includes('/answers/'))return answer(id)}});
  app.named('corpus-question').value='fencing';await app.submit('corpus-question');assert.ok(id);assert.match(app.target.textContent,new RegExp(id));
  await app.submit('corpus-question');assert.equal(app.calls.filter(c=>c.method==='POST').length,1);
  await app.click('Comprobar consulta pendiente');const status=app.calls.find(c=>c.path.includes('/answers/'));assert.equal(status.method,'GET');assert.ok(status.path.endsWith('/'+id));
  assert.equal(app.calls.filter(c=>c.method==='POST').length,1);assert.equal(app.find(n=>n.textContent==='Enviar al modelo').disabled,false);
});

test('read-only users cannot create prepare or generate even through keyboard submission',async()=>{
  const app=await panel({writable:false});app.named('corpus-name').value='new';await app.submit('corpus-name');app.named('corpus-question').value='question';await app.submit('corpus-question');
  assert.ok(app.calls.every(c=>c.method==='GET'));for(const name of ['Crear selección','Preparar corpus','Nueva conversación','Enviar al modelo'])assert.equal(app.find(n=>n.textContent===name).disabled,true);
});

test('aborted navigation cannot publish a late answer into a replaced view',async()=>{
  let resolve;const app=await panel({handler(path,method,body){if(path.endsWith('/answers'))return new Promise(done=>{resolve=()=>done(answer(body.request_id));});}});
  app.named('corpus-question').value='fencing';await app.submit('corpus-question');app.controller.abort();app.target.replaceChildren();resolve();await tick();assert.equal(app.target.textContent,'');
});

test('pending and unknown responses remain status-only while failed terminal response unlocks explicit new question',async()=>{
  for(const status of ['pending','unknown','failed']){
    const app=await panel({handler(path,method,body){if(path.endsWith('/answers'))return {...answer(body.request_id,status),error_code:'corpus_answer_truncated'};}});
    app.named('corpus-question').value='fencing';await app.submit('corpus-question');
    assert.equal(app.find(n=>n.textContent==='Enviar al modelo').disabled,status!=='failed');
    assert.equal(app.calls.filter(c=>c.method==='POST').length,1);assert.equal(app.calls.filter(c=>c.path.includes('/answers/')).length,0);
    if(status==='failed')assert.match(app.target.textContent,/corpus_answer_truncated/);
  }
});

test('source rebuild uses expected generation and blocks questions until explicit reprime',async()=>{
  let corpus=saved();const app=await panel({handler(path,method){if(path.endsWith('/rebuild')){corpus={...corpus,version:3,primed:false,session_id:null};return corpus;}if(method==='GET')return{items:[corpus]};}});
  await app.click('Actualizar selección de fuentes');const rebuild=app.calls.find(c=>c.path.endsWith('/rebuild'));assert.equal(rebuild.method,'POST');assert.deepEqual(rebuild.body,{force:false,expected_version:2});
  assert.match(app.target.textContent,/Generación 3/);assert.equal(app.find(n=>n.textContent==='Enviar al modelo').disabled,true);assert.equal(app.calls.some(c=>c.path.endsWith('/prime')||c.path.endsWith('/answers')),false);
});

test('empty corpus scope opens the creation disclosure and closes it after saving a selection',async()=>{
  let items=[];const app=await panel({handler(path,method){if(method==='POST'){items=[saved(false)];return{}}return{items};}});
  assert.equal(app.find(n=>n.className==='corpus-builder').open,true);app.named('corpus-name').value='Árbol: "uno,dos" 🌳';await app.submit('corpus-name');
  assert.equal(app.find(n=>n.className==='corpus-builder').open,false);assert.equal(app.calls.some(c=>c.path.endsWith('/answers')),false);
});
