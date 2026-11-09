import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { Readable, Writable } from 'node:stream';
import { MCPTransport, bridge, MAX_REQUEST, MAX_RESPONSE } from '../lib/mcp.mjs';
import { KairosError } from '../lib/errors.mjs';

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
