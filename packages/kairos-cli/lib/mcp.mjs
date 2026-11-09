import { once } from 'node:events';
import { baseURL, VERSION } from './config.mjs';
import { checked, readKey, text } from './files.mjs';
import { KairosError, fail, diagnostic } from './errors.mjs';
import { loadInstallation } from './install.mjs';

export const REQUIRED_TOOLS = new Set(['projects','search','details','context','timeline','remember','event_status',
  'publish_document','document_status','document_manifest','revoke_document']);
export const MAX_REQUEST = 262144;
export const MAX_RESPONSE = 2 * 1024 * 1024;
const own = (value, name) => Object.hasOwn(value, name);
const validID = id => id === null || typeof id === 'string' || typeof id === 'number' && Number.isFinite(id);
const keyFor = id => JSON.stringify([typeof id, id]);

async function responseText(response, maximum) {
  if (!response.body) return '';
  const chunks = []; let count = 0;
  try {
    for await (const chunk of response.body) {
      count += chunk.length;
      if (count > maximum) fail('mcp_response_too_large');
      chunks.push(chunk);
    }
  } catch (error) {
    if (error instanceof KairosError) throw error;
    fail('mcp_unavailable');
  }
  return text(Buffer.concat(chunks));
}

export class MCPTransport {
  constructor(url, keyFile, { fetcher = globalThis.fetch, timeout = 30000 } = {}) {
    this.endpoint = baseURL(url) + '/mcp/';
    this.keyFile = checked(keyFile);
    this.fetcher = fetcher;
    this.timeout = timeout;
    this.sessionID = null;
    this.protocolVersion = null;
  }

  async request(message, { signal } = {}) {
    if (!message || Array.isArray(message) || typeof message !== 'object' || message.jsonrpc !== '2.0' ||
        typeof message.method !== 'string' || !message.method || own(message, 'id') && !validID(message.id)) fail('invalid_mcp_request');
    const body = JSON.stringify(message);
    if (Buffer.byteLength(body) > MAX_REQUEST) fail('mcp_request_too_large');
    const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
      Authorization: 'Bearer ' + readKey(this.keyFile) };
    if (this.sessionID) headers['Mcp-Session-Id'] = this.sessionID;
    if (this.protocolVersion) headers['MCP-Protocol-Version'] = this.protocolVersion;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    const aborted = () => controller.abort();
    signal?.addEventListener('abort', aborted, { once: true });
    if (signal?.aborted) controller.abort();
    try {
      let response;
      try { response = await this.fetcher(this.endpoint, { method: 'POST', headers, body, redirect: 'manual', signal: controller.signal }); }
      catch { fail(signal?.aborted ? 'mcp_request_cancelled' : controller.signal.aborted ? 'mcp_timeout' : 'mcp_unavailable'); }
      if (response.status >= 300 || response.status < 200) {
        await response.body?.cancel().catch(() => {});
        fail(response.status >= 300 && response.status < 400 ? 'mcp_redirect_rejected' : response.status === 401 || response.status === 403 ? 'mcp_unauthorized' : 'mcp_http_error');
      }
      const raw = await responseText(response, MAX_RESPONSE);
      if (!own(message, 'id')) return null; // a notification never acquires a fabricated response id
      if (!raw.trim()) fail('mcp_missing_result');
      let packets;
      try {
        if ((response.headers.get('content-type') || '').startsWith('text/event-stream')) {
          const events = raw.replaceAll('\r\n','\n').split('\n\n');
          packets = events.map(event => event.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n'))
            .filter(Boolean).map(data => JSON.parse(data));
        } else packets = [JSON.parse(raw)];
      } catch { fail('mcp_invalid_response'); }
      const matches = packets.filter(packet => packet && packet.jsonrpc === '2.0' && own(packet, 'id') && packet.id === message.id);
      if (matches.length !== 1 || !own(matches[0], 'result') && !own(matches[0], 'error')) fail('mcp_response_id_mismatch');
      const result = matches[0];
      if (message.method === 'initialize' && result.result) {
        const session = response.headers.get('mcp-session-id');
        if (session && /^[\x21-\x7e]{1,400}$/.test(session)) this.sessionID = session;
        const version = result.result.protocolVersion;
        if (typeof version === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(version)) this.protocolVersion = version;
      }
      return result;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', aborted);
    }
  }

  async call(id, method, params = {}) {
    const packet = await this.request({ jsonrpc: '2.0', id, method, params });
    if (packet.error || !packet.result || typeof packet.result !== 'object' || packet.result.isError) fail('mcp_tool_rejected');
    return packet.result;
  }
}

export async function doctor(root, { online = false, transport } = {}) {
  const { data } = loadInstallation(root);
  const result = { status: 'configured', network_checked: false, clients: data.clients, project_id: data.project_id };
  if(data.automation&&(data.automation.capture!=='off'||data.automation.context!=='off')) {
    const {readEndpoint}=await import('./lifecycle.mjs');
    const {lifecycleConfig}=await import('./lifecycle-config.mjs');
    try { const endpoint=readEndpoint(lifecycleConfig(root,data)); result.dispatcher=endpoint?'compatible':'not_running'; }
    catch(error) { if(error.message!=='dispatcher_version_mismatch') throw error; result.status='degraded';result.dispatcher='version_mismatch'; }
  }
  if (!online) return result;
  const connection = transport || new MCPTransport(data.url, data.key_file, { timeout: 12000 });
  await connection.call(1, 'initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'kairos-doctor', version: VERSION } });
  await connection.request({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });
  const listed = await connection.call(2, 'tools/list');
  if (!Array.isArray(listed.tools) || listed.tools.length > 1000) fail('invalid_tools_response');
  const names = [...new Set(listed.tools.filter(t => t && typeof t.name === 'string').map(t => t.name))].sort();
  const required = new Set(REQUIRED_TOOLS);
  if (data.automation?.capture && data.automation.capture !== 'off') required.add('capture_policy');
  const missing = [...required].filter(name => !names.includes(name)).sort();
  if (required.has('capture_policy') && names.includes('event_status') &&
      !listed.tools.find(tool => tool.name === 'event_status')?.inputSchema?.properties?.project_id) missing.push('event_status_project_reconciliation');
  if(required.has('capture_policy') && !listed.tools.find(tool=>tool.name==='remember')?.inputSchema?.$defs?.AutomaticCapture) missing.push('automatic_capture_fingerprint');
  if(data.automation?.context==='auto' && !listed.tools.find(tool=>tool.name==='context')?.inputSchema?.properties?.match_mode) missing.push('automatic_context_filters');
  Object.assign(result, { status: missing.length||result.dispatcher==='version_mismatch' ? 'degraded' : 'ready', network_checked: true, tools: names,
    missing_tools: missing, project_authorized: false });
  if (names.includes('projects')) {
    const found = await connection.call(3, 'tools/call', { name: 'projects', arguments: {} });
    let payload = found.structuredContent;
    if (!payload) {
      try { payload = JSON.parse(found.content.find(block => block.type === 'text').text); }
      catch { fail('invalid_project_response'); }
    }
    if (!Array.isArray(payload)) payload = payload?.projects ?? payload?.result;
    if (!Array.isArray(payload)) fail('invalid_project_response');
    result.project_authorized = payload.some(project => project?.id === data.project_id);
    if (!result.project_authorized) fail('project_not_authorized');
  }
  return result;
}

async function* lines(input) {
  let pending = Buffer.alloc(0), discarding = false;
  for await (const incoming of input) {
    const chunk = Buffer.isBuffer(incoming) ? incoming : Buffer.from(incoming);
    let start = 0;
    while (start < chunk.length) {
      const newline = chunk.indexOf(10, start), end = newline < 0 ? chunk.length : newline;
      const piece = chunk.subarray(start, end);
      if (!discarding) {
        if (pending.length + piece.length > MAX_REQUEST) { yield { error: 'mcp_request_too_large' }; discarding = true; pending = Buffer.alloc(0); }
        else pending = pending.length ? Buffer.concat([pending, piece]) : piece;
      }
      if (newline < 0) break;
      if (!discarding && pending.length) yield { bytes: pending };
      pending = Buffer.alloc(0); discarding = false; start = end + 1;
    }
  }
  if (pending.length && !discarding) yield { bytes: pending };
}

export async function bridge({ input = process.stdin, output = process.stdout, errors = process.stderr, transport, concurrency = 8 } = {}) {
  if (!transport) fail('mcp_transport_required');
  const tasks = new Set(), active = new Map();
  let closed = false, writeQueue = Promise.resolve();
  const emit = packet => {
    const row = JSON.stringify(packet) + '\n';
    writeQueue = writeQueue.then(async () => {
      if (closed || output.destroyed) return;
      if (!output.write(row)) await once(output, 'drain');
    }).catch(() => { closed = true; });
    return writeQueue;
  };
  const errorPacket = (id, code, message) => ({ jsonrpc: '2.0', id, error: { code, message } });
  const sendError = (id, code) => emit(errorPacket(id, code === 'mcp_request_cancelled' ? -32800 : -32000,
    code === 'mcp_unauthorized' ? 'Kairos authentication or authorization failed' :
    code === 'mcp_timeout' ? 'Kairos request timed out; reconcile uncertain writes before retrying' :
    code === 'mcp_request_cancelled' ? 'Request cancelled' : 'Kairos request failed; inspect the sanitized local diagnostic'));
  const stop = () => { closed = true; for (const controller of active.values()) controller.abort(); };
  output.on('error', stop);
  try {
    for await (const line of lines(input)) {
      if (closed) break;
      if (line.error) { errors.write('kairos: ' + line.error + '\n'); await emit(errorPacket(null, -32600, 'MCP message exceeds the supported limit')); continue; }
      let message;
      try { message = JSON.parse(text(line.bytes)); }
      catch { await emit(errorPacket(null, -32700, 'Parse error')); continue; }
      if (!message || Array.isArray(message) || message.jsonrpc !== '2.0' || typeof message.method !== 'string' || !message.method ||
          own(message,'id') && !validID(message.id)) { await emit(errorPacket(null, -32600, 'Invalid request')); continue; }
      const notification = !own(message, 'id');
      if (notification && message.method === 'notifications/cancelled') active.get(keyFor(message.params?.requestId))?.abort();
      const key = notification ? Symbol() : keyFor(message.id);
      if (active.has(key)) { await emit(errorPacket(message.id, -32600, 'Duplicate active request id')); continue; }
      const controller = new AbortController(); active.set(key, controller);
      const job = (async () => {
        try {
          const result = await transport.request(message, { signal: controller.signal });
          if (!notification && result !== null) await emit(result);
        } catch (error) {
          const code = diagnostic(error); errors.write('kairos: ' + code + '\n');
          if (!notification) await sendError(message.id, code);
        } finally { active.delete(key); }
      })();
      tasks.add(job); job.finally(() => tasks.delete(job));
      if (tasks.size >= concurrency) await Promise.race(tasks);
    }
    await Promise.allSettled([...tasks]);
    await writeQueue;
  } finally { output.removeListener('error', stop); }
}
