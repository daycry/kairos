import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { Readable, Writable } from 'node:stream';
import { planInstall, applyInstall, loadInstallation, recover } from '../lib/install.mjs';
import { hash, atomicWrite } from '../lib/files.mjs';
import { lifecycleConfig } from '../lib/lifecycle-config.mjs';
import { startDispatcher, ipc, boundedInput, runHook, ensureDispatcher } from '../lib/lifecycle.mjs';
import { hookHandler } from '../lib/hooks.mjs';
import { adapterV1, adapterV2 } from '../lib/opencode.mjs';
import { doctor, REQUIRED_TOOLS } from '../lib/mcp.mjs';
import { VERSION } from '../lib/config.mjs';
import { Outbox } from '../lib/outbox.mjs';
import { normalizeHook } from '../lib/capture.mjs';
import { main } from '../lib/cli.mjs';

function fixture(t, automation = { capture: 'summary', context: 'auto' }) {
  const parent = fs.realpathSync.native(os.tmpdir()), base = path.join(parent,'kairos-lifecycle-test-'+randomUUID()); fs.mkdirSync(base);
  const root = path.join(base,"project é 'one', 🌳"); fs.mkdirSync(root);
  const keyFile = path.join(base,'private.key'); fs.writeFileSync(keyFile,'synthetic-private-kairos-token');
  const options = { root, keyFile, project: 'alpha', url: 'http://127.0.0.1:5173', clients: ['claude','codex','opencode'], openCodeVersion: 2,
    automation: { ...automation, state_directory: path.join(base,'private-state') } };
  t.after(() => { assert.equal(path.dirname(base),parent); assert.ok(path.basename(base).startsWith('kairos-lifecycle-test-')); fs.rmSync(base,{ recursive: true }); });
  return { root, base, options };
}

test('a stale-port impersonator receives no raw hook data and cannot inject context', async t => {
  const f=fixture(t); applyInstall(planInstall(f.options));
  const {root,data}=loadInstallation(f.root),config=lifecycleConfig(root,data);
  let observed='';
  const rogue=http.createServer(async(req,res)=>{observed+=JSON.stringify(req.headers);for await(const part of req) observed+=part; res.setHeader('Content-Type','application/json'); res.end(JSON.stringify({context:'UNTRUSTED FORGERY'}));});
  await new Promise(resolve=>rogue.listen(0,'127.0.0.1',resolve)); t.after(()=>new Promise(resolve=>rogue.close(resolve)));
  const endpoint={schema:2,version:data.runtime.version,pid:process.pid,port:rogue.address().port,nonce:'a'.repeat(64),binding:config.binding};
  for(const route of ['/status','/capture','/context','/sync','/retry','/retire'])
    await assert.rejects(ipc(config,route,{input:{prompt:'SYNTHETIC_PRIVATE_PROMPT'}},{endpoint}),/ipc_not_authenticated/);
  assert.ok(!observed.includes('SYNTHETIC_PRIVATE_PROMPT'));
  assert.ok(!observed.includes(endpoint.nonce));
});

test('opt-in hook installation previews, preserves unrelated handlers and converges without duplicates', t => {
  const f = fixture(t); fs.mkdirSync(path.join(f.root,'.claude'));
  const unrelated = { matcher: 'Read', hooks: [{ type: 'command', command: 'company-review' }] };
  fs.writeFileSync(path.join(f.root,'.claude/settings.json'), JSON.stringify({ permissions: { deny: ['Read(.env)'] }, hooks: { PostToolUse: [unrelated] } }));
  const plan = planInstall(f.options); assert.ok(!fs.existsSync(path.join(f.base,'private-state')));
  assert.equal(plan.manifest.automation.capture,'summary'); applyInstall(plan);
  const settings = JSON.parse(fs.readFileSync(path.join(f.root,'.claude/settings.json'),'utf8'));
  assert.deepEqual(settings.hooks.PostToolUse[0],unrelated); assert.deepEqual(settings.permissions,{ deny: ['Read(.env)'] });
  assert.equal(settings.hooks.PostToolUse.length,2); assert.equal(settings.hooks.SessionStart[0].hooks[0].async,undefined);
  assert.equal(settings.hooks.PostToolUse[1].hooks[0].async,true);
  assert.equal(applyInstall(planInstall(f.options)).status,'unchanged'); assert.ok(loadInstallation(f.root).data.automation);
  assert.ok(!JSON.stringify(settings).includes('synthetic-private-kairos-token'));
});

test('unrelated hooks added after installation preserve order and do not disable the runtime', t => {
  const f=fixture(t); applyInstall(planInstall(f.options));
  const file=path.join(f.root,'.claude/settings.json'),data=JSON.parse(fs.readFileSync(file,'utf8'));
  const own=data.hooks.PostToolUse[0],other={hooks:[{type:'command',command:'company-review'}]};
  data.hooks.PostToolUse.push(other); fs.writeFileSync(file,JSON.stringify(data));
  assert.ok(loadInstallation(f.root)); assert.equal(applyInstall(planInstall(f.options)).status,'unchanged');
  assert.deepEqual(JSON.parse(fs.readFileSync(file,'utf8')).hooks.PostToolUse,[own,other]);
});

test('plugin host executable differs from Node while validation and daemon launch use the registered runtime', async t => {
  const f=fixture(t); applyInstall(planInstall(f.options));
  const original=process.execPath; let handlePromise,launched=false;
  const fake={running:false,async tick(){},status(){return {records:0};},async capture(){return {status:'pending'};},async context(){return {context:'fixture memory'};}};
  try {
    process.execPath=path.join(f.base,'opencode.exe');
    const {data}=loadInstallation(f.root); assert.equal(data.node,fs.realpathSync.native(original));
    await ensureDispatcher(f.root,data,{launcher(command,args,options){
      launched=true; assert.equal(command,data.node); assert.ok(options.windowsHide); assert.equal(args[1],'daemon');
      handlePromise=startDispatcher(lifecycleConfig(f.root,data),{dispatcher:fake,tickMs:60000});
      return {on(){},unref(){}};
    }});
    assert.ok(launched);
    const hooks=await adapterV1(f.root)({directory:f.root,client:{session:{async get(){return {data:{directory:f.root}};}}}});
    const output={system:[]}; await hooks['experimental.chat.system.transform']({sessionID:'native-fixture'},output);
    assert.deepEqual(output.system,['fixture memory']);
  } finally { process.execPath=original; if(handlePromise) await (await handlePromise).close(); }
});

for (const previous of ['0.1.0','0.1.2','0.1.3','0.1.4','0.1.5','0.3.0','0.4.0']) test(`upgrade from ${previous} preserves old files and recovers a partial switch`, t => {
  const f=fixture(t); applyInstall(planInstall(f.options));
  const manifestFile=path.join(f.root,'.kairos/installation.json'),old=JSON.parse(fs.readFileSync(manifestFile,'utf8'));
  // Build the previous distribution in the fixture, including its hook and MCP
  // paths. No real client configuration is changed.
  for(const [name,sha] of Object.entries(old.runtime.files)) {
    const from=path.join(f.root,'.kairos/runtime',VERSION,name),to=path.join(f.root,`.kairos/runtime/${previous}`,name);
    fs.mkdirSync(path.dirname(to),{recursive:true}); fs.copyFileSync(from,to);
  }
  for(const file of ['.mcp.json','.codex/config.toml','opencode.json','.claude/settings.json','.codex/hooks.json','.opencode/plugins/kairos-memory/index.js']) {
    const target=path.join(f.root,file); fs.writeFileSync(target,fs.readFileSync(target,'utf8').replaceAll(VERSION,previous));
  }
  old.runtime.version=previous;
  old.managed_hooks=JSON.parse(JSON.stringify(old.managed_hooks).replaceAll(VERSION,previous));
  // Plugin ownership is a content hash, not an executable-path string.
  const plugin='.opencode/plugins/kairos-memory/index.js';
  old.managed_hooks[plugin].sha256=hash(fs.readFileSync(path.join(f.root,plugin)));
  fs.writeFileSync(manifestFile,JSON.stringify(old));
  assert.throws(()=>planInstall(f.options),/upgrade_requires/);
  assert.throws(()=>planInstall({...f.options,clients:['claude'],replace:true}),/upgrade_requires/);
  let writes=0;
  assert.throws(()=>applyInstall(planInstall({...f.options,replace:true}),{writer(file,bytes){ if(++writes===3) throw new Error('synthetic interruption'); atomicWrite(file,bytes); }}),/recovery_required/);
  recover(f.root,{apply:true});
  assert.equal(JSON.parse(fs.readFileSync(manifestFile,'utf8')).runtime.version,previous);
  applyInstall(planInstall({...f.options,replace:true}));
  assert.equal(loadInstallation(f.root).data.runtime.version,VERSION);
  assert.ok(fs.existsSync(path.join(f.root,`.kairos/runtime/${previous}/bin/kairos.mjs`)));
});

test('turning automation off removes only owned handlers and disables the owned plugin', t => {
  const f = fixture(t); applyInstall(planInstall(f.options));
  assert.throws(() => planInstall({ ...f.options, clients: ['claude'], replace: true, automation: { ...f.options.automation, capture: 'off', context: 'off' } }), /all_clients/);
  applyInstall(planInstall({ ...f.options, replace: true, automation: { ...f.options.automation, capture: 'off', context: 'off' } }));
  const settings = JSON.parse(fs.readFileSync(path.join(f.root,'.claude/settings.json'),'utf8'));
  assert.deepEqual(settings.hooks,{});
  assert.match(fs.readFileSync(path.join(f.root,'.opencode/plugins/kairos-memory/index.js'),'utf8'), /disabled/);
  assert.equal(applyInstall(planInstall({ ...f.options, automation: { ...f.options.automation, capture: 'off', context: 'off' } })).status,'unchanged');
});

test('inline Codex hooks, linked paths and altered owned handlers fail before mutation', t => {
  const f = fixture(t); fs.mkdirSync(path.join(f.root,'.codex'));
  fs.writeFileSync(path.join(f.root,'.codex/config.toml'),'[hooks]\n');
  assert.throws(() => planInstall(f.options), /inline_hooks/); assert.ok(!fs.existsSync(path.join(f.root,'.kairos')));
  fs.writeFileSync(path.join(f.root,'.codex/config.toml'),''); applyInstall(planInstall(f.options));
  const name = path.join(f.root,'.claude/settings.json'), settings = JSON.parse(fs.readFileSync(name,'utf8'));
  settings.hooks.Stop[0].hooks[0].command = 'changed-by-user'; fs.writeFileSync(name,JSON.stringify(settings));
  assert.throws(() => planInstall({ ...f.options, replace: true }), /managed_hook_changed/);
  const linked = path.join(f.base,'linked'); fs.symlinkSync(f.root,linked,process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => planInstall({ ...f.options, automation: { ...f.options.automation, state_directory: linked } }), /linked_path/);
});

test('Windows shell override preserves Unicode and metacharacter paths without variable interpolation', () => {
  const root = 'C:\\project é & 100% ! $ (one) \'quote\'', bin = root+'\\runtime\\bin\\kairos.mjs';
  const handler = hookHandler('codex',bin,root,'SessionStart',true);
  assert.match(handler.commandWindows,/^-?powershell\.exe .* -EncodedCommand [A-Za-z0-9+/=]+$/);
  const source = Buffer.from(handler.commandWindows.split(' ').at(-1),'base64').toString('utf16le');
  assert.ok(source.includes(root.replaceAll("'","''"))); assert.match(source,/InputEncoding/); assert.equal(handler.additionalContextLimit,2000);
});

test('real loopback IPC rejects foreign Origin, Host and nonce; status never returns captured content', async t => {
  const f = fixture(t); applyInstall(planInstall(f.options)); const { data } = loadInstallation(f.root);
  const config = lifecycleConfig(f.root,data), calls = [];
  const dispatcher = { running: false, async tick() {}, status() { return { records: 0 }; },
    async capture(...args) { calls.push(args); return { status: 'pending' }; }, async context() { return { context: 'authorized evidence' }; } };
  const handle = await startDispatcher(config,{ dispatcher, tickMs: 60000, errors: { write() {} } });
  t.after(() => handle.close());
  assert.deepEqual(await ipc(config,'/status'),{ records: 0,runtime_version:VERSION,ipc_schema:2 });
  const response = headers => new Promise((resolve,reject) => {
    const req = http.request({ hostname: '127.0.0.1', port: handle.endpoint.port, path: '/capture', method: 'POST', headers }, res => { res.resume(); res.on('end',() => resolve(res.statusCode)); });
    req.on('error',reject); req.end('{}');
  });
  assert.equal(await response({}),403);
  const auth = { Authorization: 'Bearer '+handle.endpoint.nonce };
  assert.equal(await response({ ...auth, Origin: 'https://untrusted.example' }),403);
  assert.equal(await response({ ...auth, Host: 'untrusted.example' }),403);
  assert.equal(calls.length,0);
  const admitted = await ipc(config,'/capture',{ runtime: 'claude', event: 'Stop', input: { cwd: f.root, session_id: 's1' }, delivery_id: 'delivery1' });
  assert.equal(admitted.status,'pending'); assert.equal(calls.length,1);
  assert.equal((await ipc(config,'/context',{ input: {} })).context,'authorized evidence');
  await handle.close(); assert.ok(!fs.existsSync(path.join(config.directory,'endpoint.json')));
});

test('oversized and malformed native input is rejected without log or source files', async () => {
  await assert.rejects(boundedInput(Readable.from(['x'.repeat(262145)])),/hook_input_too_large/);
  await assert.rejects(boundedInput(Readable.from(['{bad}'])),/invalid_hook_input/);
});

test('legacy live endpoints are rejected without IPC contact and doctor diagnoses the runtime', async t => {
  const f=fixture(t); applyInstall(planInstall(f.options)); const {data}=loadInstallation(f.root),config=lifecycleConfig(f.root,data);
  fs.mkdirSync(config.directory,{recursive:true});
  fs.writeFileSync(path.join(config.directory,'endpoint.json'),JSON.stringify({schema:1,pid:process.pid,port:12345,nonce:'a'.repeat(64),binding:config.binding}));
  let launches=0;
  await assert.rejects(ensureDispatcher(f.root,data,{launcher(){launches++;}}),/dispatcher_version_mismatch/);
  assert.equal(launches,0); assert.equal((await doctor(f.root)).dispatcher,'version_mismatch');
  const file=path.join(f.root,'.kairos/installation.json'),old={...data,runtime:{...data.runtime,version:'0.1.0'}};
  fs.writeFileSync(file,JSON.stringify(old));
  assert.throws(()=>planInstall({...f.options,replace:true}),/dispatcher_upgrade_requires_stop/);
  assert.deepEqual(JSON.parse(fs.readFileSync(file,'utf8')),old);
});

test('queue retirement works offline after capture is disabled and corrupt sources do not disable context', async t => {
  const f=fixture(t,{capture:'off',context:'auto'}); applyInstall(planInstall(f.options));
  const {data}=loadInstallation(f.root),config=lifecycleConfig(f.root,data);
  let queue=new Outbox(config.directory,config.binding);
  const spec=normalizeHook('claude',{cwd:f.root,session_id:'retire',hook_event_name:'PostToolUse',tool_name:'Bash',tool_use_id:'one',tool_input:{command:'echo synthetic'}},{root:f.root,project:'alpha',mode:'full'});
  queue.admit(spec);queue.admit(normalizeHook('claude',{cwd:f.root,session_id:'retire',hook_event_name:'PostToolUse',tool_name:'Bash',tool_use_id:'two'}, {root:f.root,project:'alpha',mode:'full'}));
  const [row,large]=queue.pending(); queue.close();
  fs.unlinkSync(path.join(config.directory,'sources',row.key+'.json'));
  fs.writeFileSync(path.join(config.directory,'sources',large.key+'.json'),'x'.repeat(262145));
  queue=new Outbox(config.directory,config.binding);
  assert.equal(queue.status().phases.failed,2);
  assert.equal(queue.rows.get(row.key).error_code,'capture_source_corrupt');
  const worker={running:false,async tick(){},status(){return queue.status();},async context(){return {context:'independent authorized context'};}};
  const handle=await startDispatcher(config,{queue,dispatcher:worker,errors:{write(){}},tickMs:60000});
  assert.equal((await ipc(config,'/context',{input:{}})).context,'independent authorized context');
  await handle.close();
  applyInstall(planInstall({...f.options,replace:true,automation:{...f.options.automation,capture:'off',context:'off'}}));
  let output=''; await main(['queue-retire','--root',f.root,'--event-id',row.event_id,'--yes'],{output:{write(value){output+=value;}}});
  assert.equal(JSON.parse(output).status,'retired');
  await main(['queue-retire','--root',f.root,'--event-id',large.event_id,'--yes'],{output:{write(){}}});
  queue=new Outbox(config.directory,config.binding); t.after(()=>queue.close());
  assert.equal(queue.status().phases.retired,2);
});

test('IPC authenticates responses against request identity and preserves plaintext size budgets',async t=>{
  const f=fixture(t);applyInstall(planInstall(f.options));const {data}=loadInstallation(f.root),config=lifecycleConfig(f.root,data);
  let calls=0;
  const handle=await startDispatcher(config,{tickMs:60000,errors:{write(){}},dispatcher:{running:false,async tick(){},status(){return {};},async context(){calls++;return {context:'x'.repeat(32700)};}}});
  t.after(()=>handle.close());
  assert.equal((await ipc(config,'/context',{input:{blob:'x'.repeat(262100)}})).context.length,32700);
  await assert.rejects(ipc(config,'/context',{input:'x'.repeat(262144)}),/ipc_payload_too_large/);
  let cached,tamper=false;
  const proxy=http.createServer(async(req,res)=>{
    const chunks=[];for await(const part of req)chunks.push(part);
    if(cached){res.end(cached);return;}
    const forward=http.request({hostname:'127.0.0.1',port:handle.endpoint.port,path:req.url,method:'POST',headers:{...req.headers,host:`127.0.0.1:${handle.endpoint.port}`}},reply=>{
      const result=[];reply.on('data',part=>result.push(part));reply.on('end',()=>{cached=Buffer.concat(result);res.end(cached);});
    });
    let body=Buffer.concat(chunks);
    if(tamper){const envelope=JSON.parse(body);envelope.tag=envelope.tag==='0'.repeat(32)?'1'.repeat(32):'0'.repeat(32);body=Buffer.from(JSON.stringify(envelope));}
    forward.end(body);
  });await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>proxy.close(resolve)));
  const endpoint={...handle.endpoint,port:proxy.address().port};
  await ipc(config,'/context',{input:{}},{endpoint});
  await assert.rejects(ipc(config,'/context',{input:{}},{endpoint}),/ipc_not_authenticated/);
  await assert.rejects(ipc(config,'/status',{}, {endpoint}),/ipc_not_authenticated/);
  assert.equal(calls,2);
  cached=null;tamper=true;
  await assert.rejects(ipc(config,'/context',{input:{}},{endpoint}),/dispatcher_request_failed/);
  assert.equal(calls,2);
  await assert.rejects(ipc(config,'/status',{}, {endpoint:{...endpoint,schema:1}}),/dispatcher_version_mismatch/);
});

test('OpenCode V1 resolves session scope and preserves existing system text', async t => {
  const f = fixture(t); const sent = [];
  const plugin = await adapterV1(f.root,{ send: async (route,body) => { sent.push({ route,body }); return { context: 'Kairos evidence' }; } })({ directory: f.root,
    client: { session: { get: async ({ path: value }) => ({ data: { directory: value.id === 'foreign' ? f.base : f.root } }) } } });
  await plugin['tool.execute.after']({ sessionID: 'foreign', tool: 'read', callID: 'call-1' },{ output: 'foreign data' }); assert.equal(sent.length,0);
  await plugin['tool.execute.after']({ sessionID: 's1', tool: 'read', callID: 'call-2', args: { filePath: 'a.md' } },{ output: 'own data' });
  assert.equal(sent[0].body.input.tool_use_id,'call-2');
  const output = { system: ['existing'] }; await plugin['experimental.chat.system.transform']({ sessionID: 's1' },output);
  assert.deepEqual(output.system,['existing','Kairos evidence']);
});

test('OpenCode V2 uses typed result/error hooks, individual locations and disposes registrations', async t => {
  const f = fixture(t); const hooks = {}, sent = []; let disposed = 0;
  const dependencies = { send: async (route,body) => { sent.push({ route,body }); return { context: 'Memory: Árbol 🌳' }; } };
  const ctx = { session: { get: async ({ sessionID }) => ({ location: { directory: sessionID === 'foreign' ? f.base : f.root } }),
    hook: async (name,callback) => { hooks[name] = callback; return { dispose() { disposed++; } }; } },
    tool: { hook: async (name,callback) => { hooks[name] = callback; return { dispose() { disposed++; } }; } },
    event: { async *subscribe() {} } };
  const cleanup = await adapterV2(f.root,dependencies).setup(ctx);
  await hooks['execute.after']({ sessionID: 'foreign', id: 'call-1', tool: 'read', status: 'completed' }); assert.equal(sent.length,0);
  await hooks['execute.after']({ sessionID: 's1', id: 'call-2', tool: 'read', input: {}, status: 'error', error: { message: 'fixture failure' } });
  assert.equal(sent[0].body.event,'PostToolUseFailure'); assert.equal(sent[0].body.input.tool_use_id,'call-2');
  const event = { sessionID: 's1', kind: 'primary', system: [{ type: 'text', text: 'original' }] }; await hooks.context(event);
  assert.deepEqual(event.system.at(-1),{ type: 'text', text: 'Memory: Árbol 🌳' });
  await hooks.context({ ...event, kind: 'title' }); assert.equal(sent.length,2);
  await cleanup(); assert.equal(disposed,2);
});

test('OpenCode V2 unwraps the native session data envelope before scope checks', async t => {
  const f=fixture(t),hooks={},sent=[];
  const ctx={session:{get:async ({sessionID})=>({data:{location:{directory:sessionID==='foreign'?f.base:f.root}}}),
    hook:async (name,handler)=>{hooks[name]=handler;return {dispose(){}};}},
    tool:{hook:async (name,handler)=>{hooks[name]=handler;return {dispose(){}};}},event:{async *subscribe(){}}};
  const cleanup=await adapterV2(f.root,{send:async (route,body)=>{sent.push({route,body});return {context:'Native scoped evidence'};}}).setup(ctx);
  const own={sessionID:'own',kind:'primary',system:[]};await hooks.context(own);
  assert.equal(own.system.at(-1)?.text,'Native scoped evidence');
  await hooks['execute.after']({sessionID:'own',tool:'read',id:'r1',status:'completed',result:'ok'});
  assert.equal(sent.at(-1).body.event,'PostToolUse');
  const count=sent.length;await hooks.context({sessionID:'foreign',kind:'primary',system:[]});
  assert.equal(sent.length,count);await cleanup();
});

test('Codex terminal hooks await bounded admission while ordinary tool hooks stay async', () => {
  for (const event of ['Stop','SessionEnd']) {
    const handler=hookHandler('codex','/fixture/bin.mjs','/fixture',event,false);
    assert.equal(handler.async,undefined);assert.equal(handler.timeout,event==='SessionEnd'?3:8);
  }
  assert.equal(hookHandler('codex','/fixture/bin.mjs','/fixture','PostToolUse',false).async,true);
  assert.equal(hookHandler('claude','/fixture/bin.mjs','/fixture','Stop',false).async,undefined);
});

test('Claude terminal hooks finish bounded admission before print-mode teardown', () => {
  for (const event of ['Stop','SessionEnd']) {
    const handler=hookHandler('claude','/fixture/bin.mjs','/fixture',event,false);
    assert.equal(handler.async,undefined);
    assert.equal(handler.timeout,8);
    assert.equal(handler.command,process.execPath);
    assert.equal(handler.args.at(-1),event);
  }
  for (const event of ['PostToolUse','PostToolUseFailure','PreCompact']) {
    assert.equal(hookHandler('claude','/fixture/bin.mjs','/fixture',event,false).async,true);
  }
});

test('OpenCode V2 native context has no kind and forwards only the latest user text', async t => {
  const f=fixture(t),hooks={},sent=[];
  const ctx={session:{get:async()=>({location:{directory:f.root}}),
    hook:async(name,handler)=>{hooks[name]=handler;return {dispose(){}};}},
    tool:{hook:async()=>({dispose(){}})},event:{async *subscribe(){}}};
  const cleanup=await adapterV2(f.root,{send:async(route,body)=>{sent.push({route,body});return {context:'Scoped memory'};}}).setup(ctx);
  const event={sessionID:'native',system:[],messages:[
    {role:'user',content:[{type:'text',text:'Old query'}]},
    {role:'assistant',content:[{type:'text',text:'Do not search this'}]},
    {role:'user',content:[{type:'text',text:'Current query'}, {type:'file',uri:'private://ignored'}]}]};
  await hooks.context(event);
  assert.equal(event.system.at(-1)?.text,'Scoped memory');
  assert.equal(sent[0].body.input.prompt,'Current query');
  assert.equal(sent[0].body.input.session_id,'native');
  assert.equal(JSON.stringify(sent).includes('private://ignored'),false);
  await cleanup();
});

test('OpenCode V2 consumes native session.created and successful execution events', async t => {
  const f=fixture(t),sent=[];
  const ctx={session:{get:async({sessionID})=>({location:{directory:sessionID==='foreign'?f.base:f.root}}),hook:async()=>({dispose(){}})},
    tool:{hook:async()=>({dispose(){}})},event:{async *subscribe(){
      yield {type:'session.created',data:{sessionID:'native'}};
      yield {type:'session.created',data:{sessionID:'foreign'}};
      yield {type:'session.execution.succeeded',data:{sessionID:'native'}};
    }}};
  const cleanup=await adapterV2(f.root,{send:async(route,body)=>{sent.push({route,body});return {};}}).setup(ctx);
  await cleanup();
  assert.deepEqual(sent.map(row=>row.body.event),['SessionStart','Stop']);
  assert.ok(sent.every(row=>row.body.input.session_id==='native'));
});

test('OpenCode V2 admits Stop from the native successful execution event with stable identity', async t => {
  const f=fixture(t),sent=[];let subscribed;
  const ctx={session:{get:async({sessionID})=>({location:{directory:sessionID==='foreign'?f.base:f.root}}),hook:async()=>({dispose(){}})},
    tool:{hook:async()=>({dispose(){}})},event:{async *subscribe(options){subscribed=options.types;
      yield {id:'evt-start',type:'session.created',data:{sessionID:'native'}};
      yield {id:'evt-failed',type:'session.execution.failed',data:{sessionID:'native'}};
      yield {id:'evt-cancelled',type:'session.execution.interrupted',data:{sessionID:'native'}};
      yield {id:'evt-success',type:'session.execution.succeeded',data:{sessionID:'native'}};
      yield {id:'evt-foreign',type:'session.execution.succeeded',data:{sessionID:'foreign'}};
    }}};
  const cleanup=await adapterV2(f.root,{send:async(route,body)=>{sent.push({route,body});return {};}}).setup(ctx);
  await cleanup();
  assert.deepEqual(subscribed,['session.created','session.execution.succeeded']);
  assert.deepEqual(sent.map(row=>[row.body.event,row.body.input.event_id]),[['SessionStart','evt-start'],['Stop','evt-success']]);
  const input=sent[1].body.input;
  const first=normalizeHook('opencode-v2',input,{root:f.root,project:'alpha',mode:'summary',event:'Stop',deliveryID:'delivery-1'});
  const replay=normalizeHook('opencode-v2',input,{root:f.root,project:'alpha',mode:'summary',event:'Stop',deliveryID:'delivery-2'});
  assert.equal(first.event.event_id,replay.event.event_id);
  assert.equal(first.event.generate,false);
});

test('doctor detects missing preflight and project-scoped reconciliation before automation can be considered ready', async t => {
  const f = fixture(t); applyInstall(planInstall(f.options)); let current = false;
  const transport = { async request() {}, async call(id,method) {
    if (method === 'initialize') return {};
    if (method === 'tools/list') return { tools: [...REQUIRED_TOOLS,...(current ? ['capture_policy'] : [])].map(name => ({ name,
      inputSchema: current ? name === 'event_status' ? { properties: { project_id: {} } } :
        name === 'remember' ? {$defs:{AutomaticCapture:{}}} : name==='context' ? {properties:{match_mode:{}}} : {} : {} })) };
    return { structuredContent: { projects: [{ id: 'alpha' }] } };
  } };
  const old = await doctor(f.root,{ online: true, transport }); assert.equal(old.status,'degraded');
  assert.ok(old.missing_tools.includes('capture_policy')); assert.ok(old.missing_tools.includes('event_status_project_reconciliation'));
  current = true; assert.equal((await doctor(f.root,{ online: true, transport })).status,'ready');
});

test('a failed context read cannot block the agent or suppress independently authorized capture', async t => {
  const f = fixture(t); applyInstall(planInstall(f.options)); const { data } = loadInstallation(f.root);
  const config = lifecycleConfig(f.root,data); let captures = 0, output = '', errors = '';
  const dispatcher = { running: false, status() { return { records: 0 }; }, async tick() {},
    async context() { throw new Error('INTERNAL MUST NOT LEAK'); }, async capture() { captures++; return { status: 'pending' }; } };
  const handle = await startDispatcher(config,{ dispatcher, tickMs: 60000, errors: { write() {} } }); t.after(() => handle.close());
  const code = await runHook({ root: f.root, runtime: 'codex', event: 'SessionStart',
    input: Readable.from([JSON.stringify({ cwd: f.root, session_id: 's1' })]),
    output: new Writable({ write(chunk,encoding,done) { output += chunk; done(); } }),
    errors: new Writable({ write(chunk,encoding,done) { errors += chunk; done(); } }) });
  assert.equal(code,0); assert.deepEqual(JSON.parse(output),{}); assert.equal(captures,1);
  assert.match(errors,/kairos:/); assert.ok(!errors.includes('INTERNAL'));
});
