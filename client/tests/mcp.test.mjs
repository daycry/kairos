import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { Readable, Writable } from 'node:stream';
import { MCPTransport, bridge, MAX_REQUEST, MAX_RESPONSE } from '../lib/mcp.mjs';
import { KairosError } from '../lib/errors.mjs';
import { applyInstall, planInstall, loadInstallation } from '../lib/install.mjs';
import { credentialFile } from '../lib/lifecycle-config.mjs';
import { doctor, REQUIRED_TOOLS } from '../lib/mcp.mjs';

function fixture(t) {
  const temp=fs.realpathSync.native(os.tmpdir()),root=path.join(temp,'kairos-mcp-test-'+randomUUID());fs.mkdirSync(root);
  const key=path.join(root,'private.key'),secret='synthetic-kairos-credential-for-fixtures';fs.writeFileSync(key,secret);
  t.after(()=>{assert.equal(path.dirname(root),temp);assert.ok(path.basename(root).startsWith('kairos-mcp-test-'));assert.equal(fs.lstatSync(root).isSymbolicLink(),false);fs.rmSync(root,{recursive:true,force:true});});
  return{key,secret};
}
function sink(){let content='';return{value:new Writable({write(chunk,enc,done){content+=chunk.toString();done();}}),get content(){return content;}};}
const message=(id=1,method='tools/list')=>({jsonrpc:'2.0',id,method,params:{}});
const reply=(id,result={})=>new Response(JSON.stringify({jsonrpc:'2.0',id,result}),{headers:{'content-type':'application/json'}});

test('HTTP bridge preserves IDs, bearer auth, the fixed MCP endpoint and session/protocol headers',async t=>{
  const f=fixture(t),calls=[];
  const transport=new MCPTransport('http://127.0.0.1:5173',f.key,{fetcher:async(url,options)=>{
    calls.push({url,...options});const request=JSON.parse(options.body);
    return request.method==='initialize'?new Response(JSON.stringify({jsonrpc:'2.0',id:request.id,result:{protocolVersion:'2025-03-26',serverInfo:{name:'fixture'}}}),{headers:{'content-type':'application/json','mcp-session-id':'synthetic-session'}}):reply(request.id,{tools:[]});
  }});
  const initialized=await transport.request(message('init','initialize'));assert.equal(initialized.id,'init');
  const result=await transport.request(message(42));assert.equal(result.id,42);
  assert.equal(calls[0].url,'http://127.0.0.1:5173/mcp/');assert.equal(calls[0].headers.Authorization,'Bearer '+f.secret);
  assert.equal(calls[0].redirect,'manual');assert.equal(calls[1].headers['Mcp-Session-Id'],'synthetic-session');assert.equal(calls[1].headers['MCP-Protocol-Version'],'2025-03-26');
});

test('HTTP notifications remain notifications, without a fabricated request ID or response',async t=>{
  const f=fixture(t);let captured;
  const transport=new MCPTransport('http://localhost:5173',f.key,{fetcher:async(url,options)=>{captured=JSON.parse(options.body);return new Response(null,{status:202});}});
  const result=await transport.request({jsonrpc:'2.0',method:'notifications/initialized'});
  assert.equal(result,null);assert.equal(Object.hasOwn(captured,'id'),false);
});

test('HTTP SSE replies decode multiline data and enforce the exact original ID',async t=>{
  const f=fixture(t);
  const data='event: message\r\ndata: {"jsonrpc":"2.0",\r\ndata: "id":"request", "result":{"tools":[]}}\r\n\r\n';
  const transport=new MCPTransport('http://127.0.0.1:5173',f.key,{fetcher:async()=>new Response(data,{headers:{'content-type':'text/event-stream'}})});
  assert.deepEqual((await transport.request(message('request'))).result,{tools:[]});
  await assert.rejects(transport.request(message('different')),/mcp_response_id_mismatch/);
});

test('redirects and HTTP errors never follow another origin or expose error bodies',async t=>{
  const f=fixture(t);
  for(const status of[302,401,403,500]){
    let calls=0;
    const transport=new MCPTransport('http://localhost:5173',f.key,{fetcher:async()=>{calls++;return new Response('HIDDEN '+f.secret,{status,headers:{location:'https://foreign.example'}});}});
    await assert.rejects(transport.request(message()),error=>error instanceof KairosError&&!error.message.includes(f.secret));assert.equal(calls,1);
  }
});

test('request, response and timeout budgets are bounded and diagnostics are sanitized',async t=>{
  const f=fixture(t);let calls=0;
  const transport=new MCPTransport('http://localhost:5173',f.key,{timeout:15,fetcher:async(url,{signal})=>{calls++;return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error(f.secret)),{once:true}));}});
  await assert.rejects(transport.request({...message(),params:{text:'x'.repeat(MAX_REQUEST)}}),/mcp_request_too_large/);assert.equal(calls,0);
  await assert.rejects(transport.request(message()),/mcp_timeout/);assert.equal(calls,1);
  const huge=new MCPTransport('http://localhost:5173',f.key,{fetcher:async()=>new Response('x'.repeat(MAX_RESPONSE+1))});
  await assert.rejects(huge.request(message()),/mcp_response_too_large/);
});

test('stdio carries JSON-RPC only, preserves concurrent IDs, and emits nothing for notifications',async()=>{
  const out=sink(),err=sink(),calls=[];
  const transport={async request(m){calls.push(m);if(!Object.hasOwn(m,'id'))return null;await new Promise(r=>setTimeout(r,m.id===1?10:0));return{jsonrpc:'2.0',id:m.id,result:{tools:[]}};}};
  const input=Readable.from([JSON.stringify(message(1))+'\n'+JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})+'\n'+JSON.stringify(message(2))+'\n']);
  await bridge({input,output:out.value,errors:err.value,transport});
  const packets=out.content.trim().split('\n').map(line=>JSON.parse(line));assert.deepEqual(packets.map(p=>p.id).sort(),[1,2]);assert.equal(calls.length,3);assert.equal(err.content,'');
});

test('stdio invalid JSON, invalid request and overlong lines recover at the next delimiter',async()=>{
  const out=sink(),err=sink();
  const transport={async request(m){return{jsonrpc:'2.0',id:m.id,result:{ok:true}};}};
  const input=Readable.from(['not-json\n','[]\n',Buffer.alloc(MAX_REQUEST+1,120),'\n',JSON.stringify(message('ok'))+'\n']);
  await bridge({input,output:out.value,errors:err.value,transport});
  const packets=out.content.trim().split('\n').map(JSON.parse);assert.deepEqual(packets.slice(0,3).map(p=>p.id),[null,null,null]);assert.equal(packets[3].id,'ok');assert.ok(packets[0].error);assert.equal(err.content,'kairos: mcp_request_too_large\n');
});

test('stdio never echoes transport exceptions, key material or raw HTTP bodies',async()=>{
  const secret='synthetic-private-credential-never-logged',out=sink(),err=sink();
  const transport={async request(){throw Error('Raw HTTP body Authorization: Bearer '+secret);}};
  await bridge({input:Readable.from([JSON.stringify(message(7))+'\n']),output:out.value,errors:err.value,transport});
  assert.equal(out.content.includes(secret),false);assert.equal(err.content.includes(secret),false);assert.equal(JSON.parse(out.content).id,7);assert.equal(err.content,'kairos: operation_failed\n');
});

test('stdio cancellation preserves notification semantics and cancels the matching call',async()=>{
  const out=sink(),err=sink();
  const transport={async request(m,{signal}){if(m.method==='notifications/cancelled')return null;return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new KairosError('mcp_request_cancelled')),{once:true}));}};
  const input=Readable.from([JSON.stringify(message('pending'))+'\n'+JSON.stringify({jsonrpc:'2.0',method:'notifications/cancelled',params:{requestId:'pending'}})+'\n']);
  await bridge({input,output:out.value,errors:err.value,transport});
  const packet=JSON.parse(out.content);assert.equal(packet.id,'pending');assert.equal(packet.error.code,-32800);assert.equal(out.content.trim().split('\n').length,1);
});

// T-21 (CA-08, DC-7): `kairos doctor` keeps what `/v1/auth/me` says of the key (credential.json, without the key), warns under 14 days and tells an expired key from an invalid
// one. An installation in a temporary directory, a simulated server (the injected fetch) and an injected clock: nothing leaves the machine and the real profile is never read.
const DAY_MS = 86400000, NOW = Date.parse('2026-11-27T10:00:00Z');
function installed(t, secret = 'mp_synthetic-credential-for-doctor-tests') {
  const parent = fs.realpathSync.native(os.tmpdir()), base = path.join(parent, 'kairos-doctor-key-test-' + randomUUID()); fs.mkdirSync(base);
  const root = path.join(base, 'project'); fs.mkdirSync(root);
  const keyFile = path.join(base, 'private.key'); fs.writeFileSync(keyFile, secret);
  t.after(() => { assert.equal(path.dirname(base), parent); assert.ok(path.basename(base).startsWith('kairos-doctor-key-test-')); fs.rmSync(base, { recursive: true, force: true }); });
  applyInstall(planInstall({ root, keyFile, project: 'alpha', url: 'http://127.0.0.1:5173', clients: ['claude'], openCodeVersion: 2,
    automation: { capture: 'off', context: 'off', state_directory: path.join(base, 'private-state') } }));
  const { data } = loadInstallation(root), file = credentialFile(root, data);
  fs.mkdirSync(path.dirname(file), { recursive: true });  // the tests write records of their own there
  return { root, base, keyFile, secret, file };
}
const mcpServer = { async request() { return null; }, async call(id, method) {
  if (method === 'tools/list') return { tools: [...REQUIRED_TOOLS].map(name => ({ name })) };
  if (method === 'tools/call') return { structuredContent: { projects: [{ id: 'alpha' }] } };
  return { serverInfo: { name: 'fixture' } };
} };
function identityServer(answer) {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, authorization: options.headers.Authorization, method: options.method, redirect: options.redirect });
    const { status, key } = answer();
    return status === 200 ? new Response(JSON.stringify({ actor: { id: 'u1', scopes: ['read'], project_ids: ['alpha'] }, csrf_token: '', key }), { headers: { 'content-type': 'application/json' } })
      : new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Authentication required' } }), { status });
  };
  return { fetcher, calls };
}
const seenKey = (secret, expires) => ({ id: 'k-1', name: 'laptop', prefix: secret.slice(0, 10), expires_at: expires === null ? null : new Date(expires).toISOString().replace('.000Z', '+00:00') });
const record = (prefix, expires, keyID = 'k-1') => JSON.stringify({ key_id: keyID, prefix, expires_at: expires === null ? null : new Date(expires).toISOString(), checked_at: new Date(NOW - DAY_MS).toISOString() });

test('doctor --online keeps the expiry of the key and warns when it expires in less than 14 days', async t => {
  const f = installed(t);
  for (const [days, warned] of [[13.9, true], [14.1, false], [null, false]]) {
    const server = identityServer(() => ({ status: 200, key: seenKey(f.secret, days === null ? null : NOW + days * DAY_MS) }));
    const result = await doctor(f.root, { online: true, transport: mcpServer, fetcher: server.fetcher, now: () => NOW });
    assert.equal(server.calls.length, 1);
    assert.deepEqual(server.calls[0], { url: 'http://127.0.0.1:5173/v1/auth/me', authorization: 'Bearer ' + f.secret, method: 'GET', redirect: 'manual' });
    assert.equal(result.key.id, 'k-1');
    assert.deepEqual(result.warnings, warned ? ['key_expires_soon'] : undefined, String(days));
    assert.equal(result.status, warned ? 'degraded' : 'ready', String(days));
    if (days === null) assert.equal(result.key.expires_at, null);
    const stored = JSON.parse(fs.readFileSync(f.file, 'utf8'));
    assert.deepEqual(Object.keys(stored).sort(), ['checked_at', 'expires_at', 'key_id', 'prefix']);
    assert.equal(stored.checked_at, new Date(NOW).toISOString());
  }
  // without network the record kept by the last check still warns, on the clock of this run
  fs.writeFileSync(f.file, record(f.secret.slice(0, 10), NOW + 20 * DAY_MS));
  assert.equal((await doctor(f.root, { now: () => NOW })).warnings, undefined);
  const later = await doctor(f.root, { now: () => NOW + 7 * DAY_MS });
  assert.deepEqual(later.warnings, ['key_expires_soon']); assert.equal(later.key.expires_in_days, 13); assert.equal(later.status, 'degraded');
  assert.deepEqual((await doctor(f.root, { now: () => NOW + 21 * DAY_MS })).warnings, ['key_expired']);
});

test('a 401 is key_expired only when the record of this key says it already expired, and key_invalid otherwise', async t => {
  const f = installed(t), refused = identityServer(() => ({ status: 401 }));
  const run = () => doctor(f.root, { online: true, transport: mcpServer, fetcher: refused.fetcher, now: () => NOW });
  await assert.rejects(run(), error => error instanceof KairosError && error.code === 'key_invalid', 'no record');
  for (const [expires, code] of [[NOW - 1000, 'key_expired'], [NOW + DAY_MS, 'key_invalid'], [null, 'key_invalid']]) {
    fs.writeFileSync(f.file, record(f.secret.slice(0, 10), expires));
    await assert.rejects(run(), error => error instanceof KairosError && error.code === code && !error.message.includes(f.secret), String(expires));
  }
  // the server answers the same 401 in every case: the record tells them apart, and a 401 writes nothing
  assert.equal(JSON.parse(fs.readFileSync(f.file, 'utf8')).expires_at, null);
});

test('another key file does not inherit the expiry of the previous key', async t => {
  const f = installed(t);
  fs.writeFileSync(f.file, record('mp_previou', NOW - 1000, 'k-old'));
  const offline = await doctor(f.root, { now: () => NOW });
  assert.equal(offline.key, undefined); assert.equal(offline.warnings, undefined);
  await assert.rejects(doctor(f.root, { online: true, transport: mcpServer, fetcher: identityServer(() => ({ status: 401 })).fetcher, now: () => NOW }),
    error => error.code === 'key_invalid', 'an expired record of ANOTHER key does not make this one expired');
  // an answer about another key (another prefix) is not kept either
  const result = await doctor(f.root, { online: true, transport: mcpServer, fetcher: identityServer(() => ({ status: 200, key: seenKey('mp_otherkey-value', NOW + DAY_MS) })).fetcher, now: () => NOW });
  assert.equal(result.key, undefined); assert.equal(JSON.parse(fs.readFileSync(f.file, 'utf8')).key_id, 'k-old');
});

test('neither the messages nor credential.json hold the key, and a server without the field or out of reach changes nothing', async t => {
  const f = installed(t);
  const result = await doctor(f.root, { online: true, transport: mcpServer, fetcher: identityServer(() => ({ status: 200, key: seenKey(f.secret, NOW + 3 * DAY_MS) })).fetcher, now: () => NOW });
  const stored = fs.readFileSync(f.file, 'utf8');
  assert.equal(stored.includes(f.secret), false); assert.equal(JSON.stringify(result).includes(f.secret), false);
  assert.equal(JSON.parse(stored).prefix, f.secret.slice(0, 10));
  if (process.platform !== 'win32') assert.equal(fs.statSync(f.file).mode & 0o777, 0o600);
  for (const answer of [() => ({ status: 200, key: undefined }), () => ({ status: 503 }), () => { throw new Error('offline ' + f.secret); }]) {
    const fetcher = async () => { const { status, key } = answer(); return new Response(JSON.stringify({ actor: {}, key }), { status }); };
    const again = await doctor(f.root, { online: true, transport: mcpServer, fetcher, now: () => NOW });
    assert.equal(again.key.id, 'k-1', 'the record of the last accepted check stays'); assert.deepEqual(again.warnings, ['key_expires_soon']);
  }
  // a transport injected without a fetch of its own (the other doctor tests) makes no request for the key
  assert.equal((await doctor(f.root, { online: true, transport: mcpServer, now: () => NOW })).network_checked, true);
});
