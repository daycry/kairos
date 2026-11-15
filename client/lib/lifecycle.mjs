import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { randomBytes, randomUUID, timingSafeEqual, createCipheriv, createDecipheriv, createHmac } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { checked, readBytes, text, atomicWrite, jsonBytes, sameBytes } from './files.mjs';
import { VERSION } from './config.mjs';
import { lifecycleConfig } from './lifecycle-config.mjs';
import { loadInstallation } from './install.mjs';
import { Dispatcher } from './dispatcher.mjs';
import { Outbox } from './outbox.mjs';
import { RUNTIMES } from './capture.mjs';
import { fail, diagnostic } from './errors.mjs';

const MAX_IPC = 262144;
const MAX_WIRE = Math.ceil(MAX_IPC/3)*4+2048;
const endpointFile = config => checked(path.join(config.directory, 'endpoint.json'), config.directory);
const authorized = (given, expected) => {
  const a = Buffer.from(given ?? ''), b = Buffer.from('Bearer '+expected);
  return a.length === b.length && timingSafeEqual(a,b);
};

const requestToken=(local,route,id)=>createHmac('sha256',Buffer.from(local.nonce,'hex')).update(JSON.stringify(['auth',2,VERSION,local.binding,route,id])).digest('hex');
const aad=(local,route,id,direction)=>Buffer.from(JSON.stringify([2,VERSION,local.binding,route,id,direction]));
const cipherKey=(local,direction)=>createHmac('sha256',Buffer.from(local.nonce,'hex')).update('kairos-ipc-v2:'+direction).digest();
function seal(local,route,id,direction,value,maximum) {
  const bytes=Buffer.from(JSON.stringify(value)); if(bytes.length>maximum) fail('ipc_payload_too_large');
  const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',cipherKey(local,direction),iv);
  cipher.setAAD(aad(local,route,id,direction));
  const data=Buffer.concat([cipher.update(bytes),cipher.final()]);
  return {iv:iv.toString('hex'),data:data.toString('base64'),tag:cipher.getAuthTag().toString('hex')};
}
function open(local,route,id,direction,value,maximum) {
  try {
    if(!value||typeof value.data!=='string'||!/^[a-f0-9]{24}$/.test(value.iv)||!/^[a-f0-9]{32}$/.test(value.tag)) throw Error();
    const bytes=Buffer.from(value.data,'base64');
    if(bytes.length>maximum||bytes.toString('base64')!==value.data) throw Error();
    const cipher=createDecipheriv('aes-256-gcm',cipherKey(local,direction),Buffer.from(value.iv,'hex'));
    cipher.setAAD(aad(local,route,id,direction)); cipher.setAuthTag(Buffer.from(value.tag,'hex'));
    return JSON.parse(text(Buffer.concat([cipher.update(bytes),cipher.final()])));
  } catch { fail('ipc_not_authenticated'); }
}

export async function boundedInput(input,maximum=MAX_IPC) {
  const chunks = []; let count = 0;
  for await (const chunk of input) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk); count += buffer.length;
    if (count > maximum) fail('hook_input_too_large'); chunks.push(buffer);
  }
  try { return JSON.parse(text(Buffer.concat(chunks))); } catch { fail('invalid_hook_input'); }
}

/** The only listener is authenticated literal loopback. No platform key in IPC. */
export async function startDispatcher(config, { queue, dispatcher, idleMs = 15*60*1000, tickMs = 3000, errors = process.stderr } = {}) {
  const outbox = queue ?? new Outbox(config.directory, config.binding);
  const worker = dispatcher ?? new Dispatcher(config, outbox, { refresh: () => {
    const { root, data } = loadInstallation(config.root);
    return lifecycleConfig(root,data);
  } });
  const nonce = randomBytes(32).toString('hex'); let active = 0, lastActivity = Date.now(), closing = false;
  const local={nonce,binding:config.binding};
  const server = http.createServer(async (request, response) => {
    const id=request.headers['x-kairos-request'],validID=typeof id==='string'&&/^[a-f0-9]{32}$/.test(id);
    const send = (status, value) => { if(Buffer.byteLength(JSON.stringify(value))>32768) fail('ipc_payload_too_large'); const wire=validID?seal(local,request.url,id,'response',{status,value},32832):value; response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); response.end(JSON.stringify(wire)); };
    if (request.method !== 'POST' || request.headers.origin || request.headers.host !== `127.0.0.1:${server.address()?.port}` ||
        request.socket.remoteAddress !== '127.0.0.1' || !validID || !authorized(request.headers.authorization, requestToken(local,request.url,id))) {
      request.resume(); send(403, { error_code: 'ipc_not_authorized' }); return;
    }
    if (active >= 8 || closing) { request.resume(); send(503, { error_code: 'ipc_busy' }); return; }
    active++; lastActivity = Date.now();
    try {
      const value = open(local,request.url,id,'request',await boundedInput(request,MAX_WIRE),MAX_IPC);
      if (request.url === '/status') send(200, {...worker.status(),runtime_version:VERSION,ipc_schema:2});
      else if (request.url === '/sync') { void worker.tick(); send(200, worker.status()); }
      else if (request.url === '/retry' || request.url === '/retire') {
        if (typeof value.event_id !== 'string' || !/^[a-f0-9-]{36}$/i.test(value.event_id)) fail('invalid_capture_identity');
        const row=request.url==='/retry'?outbox.retry(value.event_id):outbox.retire(value.event_id);
        send(200,{event_id:row.event_id,status:row.phase});
      }
      else if (request.url === '/capture') {
        if (!RUNTIMES.has(value.runtime) || typeof value.event !== 'string' || typeof value.delivery_id !== 'string') fail('invalid_hook_input');
        send(200, await worker.capture(value.runtime, value.input, value.event, value.delivery_id));
      } else if (request.url === '/context') send(200, await worker.context(value.input));
      else send(404, { error_code: 'ipc_route_not_found' });
    } catch (error) { const code = diagnostic(error); errors.write('kairos: '+code+'\n'); if (!response.headersSent) send(503, { error_code: code }); }
    finally { active--; }
  });
  server.requestTimeout = 5000; server.headersTimeout = 5000; server.timeout = 5000; server.maxConnections = 16;
  await new Promise((resolve,reject) => { server.once('error',reject); server.listen(0, '127.0.0.1', resolve); });
  const endpoint = { schema: 2, version:VERSION, pid: process.pid, port: server.address().port, nonce, binding: config.binding };
  const bytes = jsonBytes(endpoint), file = endpointFile(config);
  try { atomicWrite(file, bytes); } catch (error) { server.close(); outbox.close(); throw error; }
  let timer;
  const close = async () => {
    if (closing) return; closing = true; clearInterval(timer);
    await new Promise(resolve => { server.close(resolve); server.closeIdleConnections(); });
    while (worker.running) await delay(20);
    if (sameBytes(readBytes(file,8192), bytes)) fs.unlinkSync(file);
    outbox.close();
  };
  timer = setInterval(() => {
    if (!active && !worker.running && Date.now() - lastActivity >= idleMs) { void close(); return; }
    void worker.tick();
  }, tickMs);
  return { endpoint, close, worker };
}

export function readEndpoint(config) {
  const bytes = readBytes(endpointFile(config), 8192); if (!bytes) return null;
  let value; try { value = JSON.parse(text(bytes)); } catch { fail('invalid_ipc_endpoint'); }
  if((value.schema!==2||value.version!==VERSION)&&Number.isSafeInteger(value.pid)&&value.pid>0) {
    try { process.kill(value.pid,0); } catch(error) { if(error.code==='ESRCH') return null; }
  }
  return validateEndpoint(config,value);
}
function validateEndpoint(config,value) {
  if (!value||value.binding !== config.binding || !Number.isSafeInteger(value.port) || value.port < 1 || value.port > 65535 ||
      !Number.isSafeInteger(value.pid) || value.pid < 1 || !/^[a-f0-9]{64}$/.test(value.nonce)) fail('invalid_ipc_endpoint');
  if(value.schema!==2||value.version!==VERSION) fail('dispatcher_version_mismatch');
  return value;
}
export async function ipc(config, route, body = {}, { endpoint, timeout = 2200 } = {}) {
  const local = endpoint ? validateEndpoint(config,endpoint) : readEndpoint(config); if (!local) fail('dispatcher_not_running');
  const id=randomBytes(16).toString('hex');
  const bytes = Buffer.from(JSON.stringify(seal(local,route,id,'request',body,MAX_IPC)));
  return await new Promise((resolve,reject) => {
    const request = http.request({ hostname: '127.0.0.1', port: local.port, path: route, method: 'POST',
      headers: { Authorization: 'Bearer '+requestToken(local,route,id), 'X-Kairos-Request':id,'Content-Type': 'application/json', 'Content-Length': bytes.length }, agent: false }, response => {
      const chunks = []; let count = 0;
      response.on('data', chunk => { count += chunk.length; if (count > 46000) request.destroy(); else chunks.push(chunk); });
      response.on('end', () => {
        try {
          const result=open(local,route,id,'response',JSON.parse(text(Buffer.concat(chunks))),32832);
          if(Buffer.byteLength(JSON.stringify(result.value))>32768) throw Error();
          if(result.status!==response.statusCode||result.status!==200) { reject(new Error('dispatcher_request_failed')); return; }
          resolve(result.value);
        } catch { reject(new Error('ipc_not_authenticated')); }
      });
      response.on('error', () => reject(new Error('dispatcher_unavailable')));
    });
    const timer = setTimeout(() => request.destroy(), timeout);
    request.on('close', () => clearTimeout(timer));
    request.on('error', () => reject(new Error('dispatcher_unavailable'))); request.end(bytes);
  });
}

export async function ensureDispatcher(root, data, { launcher = spawn } = {}) {
  const config = lifecycleConfig(root, data);
  if (config.capture === 'off' && config.context === 'off') fail('automation_not_enabled');
  try { await ipc(config, '/status', {}, { timeout: 200 }); return config; } catch(error) {
    if(diagnostic(error)==='dispatcher_version_mismatch') throw error;
    /* launch owned stable runtime; never send plaintext to the stale listener */
  }
  const bin = checked(path.join(root, '.kairos', 'runtime', VERSION, 'bin', 'kairos.mjs'), root);
  const child = launcher(checked(data.node), [bin, 'daemon', '--root', root], { detached: true, windowsHide: true, stdio: 'ignore' });
  child.on('error', () => {}); child.unref();
  const until = Date.now()+1800;
  while (Date.now() < until) {
    await delay(60);
    try { await ipc(config, '/status', {}, { timeout: 200 }); return config; } catch { /* lock guarantees only one owner */ }
  }
  fail('dispatcher_start_timeout');
}

export async function runHook({ root, runtime, event, input, output, errors }) {
  let result = {};
  try {
    if (!RUNTIMES.has(runtime)) fail('unsupported_capture_runtime');
    const value = await boundedInput(input);
    const { root: base, data } = loadInstallation(root);
    const config = await ensureDispatcher(base, data);
    if (['SessionStart','UserPromptSubmit'].includes(event) && config.context === 'auto') {
      try {
        const context = await ipc(config, '/context', { input: value });
        if (context.context) result = { hookSpecificOutput: { hookEventName: event, additionalContext: context.context } };
      } catch (error) { errors.write('kairos: '+diagnostic(error)+'\n'); }
    }
    if (config.capture !== 'off') {
      try { await ipc(config, '/capture', { runtime, event, input: value, delivery_id: randomUUID() }); }
      catch (error) { errors.write('kairos: '+diagnostic(error)+'\n'); }
    }
  } catch (error) { errors.write('kairos: '+diagnostic(error)+'\n'); }
  // A memory outage must never block or approve an agent operation.
  output.write(JSON.stringify(result)+'\n'); return 0;
}
