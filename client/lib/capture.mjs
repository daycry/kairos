import path from 'node:path';
import { createHash } from 'node:crypto';
import { checked, projectRoot, within } from './files.mjs';
import { sanitizeText, sanitizeTree } from './privacy.mjs';
import { fail } from './errors.mjs';

export const RUNTIMES = new Set(['claude','codex','opencode-v1','opencode-v2']);
const TOOLS = new Set(['bash','read','write','edit','multiedit','glob','grep','task','webfetch','websearch','todowrite','exec_command','shell_command','apply_patch','read_file','list_dir','update_plan']);
const IDS = /^[A-Za-z0-9_.:-]{1,200}$/;

export function canonical(value) {
  function ordered(item) {
    if (Array.isArray(item)) return item.map(ordered);
    if (item && typeof item === 'object') return Object.fromEntries(Object.keys(item).sort().map(key => [key, ordered(item[key])]));
    return item;
  }
  return JSON.stringify(ordered(value));
}
export const digest = value => createHash('sha256').update(canonical(value)).digest('hex');
export function uuid(value) {
  const buffer = createHash('sha256').update(value).digest().subarray(0, 16);
  buffer[6] = (buffer[6] & 15) | 80; buffer[8] = (buffer[8] & 63) | 128;
  const hex = buffer.toString('hex');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function effectiveMode(client, server) {
  if (!['off','summary','full'].includes(client) || !['off','summary','full'].includes(server)) fail('invalid_capture_policy');
  return client === 'off' || server === 'off' ? 'off' : client === 'full' && server === 'full' ? 'full' : 'summary';
}
function identity(value, label) {
  if (typeof value !== 'string' || !IDS.test(value) || sanitizeText(value).redacted) fail(label);
  return value;
}

export function normalizeHook(runtime, input, { root, project, mode, event: selectedEvent, deliveryID }) {
  if (!RUNTIMES.has(runtime)) fail('unsupported_capture_runtime');
  if (!['summary','full'].includes(mode)) return { ignored: 'capture_off' };
  if (!input || Array.isArray(input) || typeof input !== 'object') fail('invalid_hook_event');
  const base = projectRoot(root);
  if (typeof input.cwd !== 'string' || !path.isAbsolute(input.cwd) || !within(base, projectRoot(checked(input.cwd)))) return { ignored: 'foreign_project' };
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(project)) fail('invalid_project_id');
  const session = identity(input.session_id ?? input.sessionID, 'invalid_capture_session');
  const event = selectedEvent ?? input.hook_event_name;
  if (input.stop_hook_active === true) return { ignored: 'recursive_stop' };
  let kind, title, content, nativeID, tool;
  if (['PostToolUse','PostToolUseFailure'].includes(event)) {
    tool = (input.tool_name ?? '').replace(/^functions\./, '').toLowerCase();
    if (!TOOLS.has(tool) || input.mcp_server) return { ignored: 'excluded_tool' };
    nativeID = input.tool_use_id ?? input.callID ?? input.id;
    if (nativeID !== undefined) identity(nativeID, 'invalid_capture_identity');
    const exit = input.tool_response?.exit_code ?? input.tool_response?.metadata?.exit ?? input.tool_response?.metadata?.exit_code;
    const failed = event === 'PostToolUseFailure' || input.status === 'error' || input.status === 'failed' || Number.isSafeInteger(exit) && exit !== 0;
    kind = 'note'; title = `${tool}: ${failed ? 'failed' : 'completed'}`;
    const metadata = { tool, status: failed ? 'failed' : 'completed' };
    if (Number.isSafeInteger(exit)) metadata.exit_code = exit;
    content = mode === 'full' ? { ...metadata, input: input.tool_input ?? null, result: input.tool_response ?? input.error ?? null } : metadata;
  } else if (event === 'SessionStart') {
    kind = 'session_start'; title = 'Agent session started'; content = { event: 'session_start', source: ['startup','resume','clear','compact','fork'].includes(input.source) ? input.source : 'startup' };
    nativeID = input.event_id;
  } else if (event === 'SessionEnd') {
    kind = 'session_end'; title = 'Agent session ended'; content = { event: 'session_end' }; nativeID = input.event_id;
  } else if (event === 'UserPromptSubmit') {
    kind = 'note'; title = 'Task prompt admitted'; content = mode === 'full' ? { prompt: input.prompt ?? '' } : { event: 'prompt_admitted' }; nativeID = input.event_id;
  } else if (['Stop','SubagentStop','PreCompact','PostCompact'].includes(event)) {
    kind = 'summary'; title = event === 'Stop' ? 'Agent turn completed' : `Agent event: ${event}`;
    // An assistant's final answer is not assumed to be a summary. Only an
    // explicitly supplied summary enters summary mode; full is separate.
    content = typeof input.summary === 'string' ? { summary: input.summary } : mode === 'full' && typeof input.last_assistant_message === 'string'
      ? { assistant_response: input.last_assistant_message } : { event: event.toLowerCase(), detail: 'Technical lifecycle metadata only; no transcript captured.' };
    nativeID = input.event_id ?? input.turn_id;
  } else return { ignored: 'unsupported_event' };
  if (nativeID !== undefined) identity(nativeID, 'invalid_capture_identity');
  if (!nativeID) identity(deliveryID, 'capture_delivery_id_required');
  const sanitized = sanitizeTree(content);
  const body = canonical(sanitized.value);
  if ([...body].length > 100000) fail('capture_body_too_large');
  const key = digest({ root: base, project, runtime, session, event, native_id: nativeID ?? deliveryID });
  const payload = { title, content: body, category: 'agent-activity', tags: [`runtime:${runtime}`, `capture:${mode}`, ...(tool ? [`tool:${tool}`] : [])],
    source: { uri: `agent://${runtime}/${encodeURIComponent(session)}/${key}`, sha256: createHash('sha256').update(body).digest('hex') }, validation_status: 'observed' };
  const fingerprint = digest({ project, runtime, session, event, payload });
  return { key, semantic_hash: fingerprint, redacted: sanitized.redacted,
    event: { event_id: uuid('kairos:event:'+key), item_id: uuid('kairos:item:'+key), project_id: project, session_id: session,
      capture: { mode, hook_event: event, fingerprint },
      agent_id: runtime, event_type: kind, version: 1, generate: kind === 'summary' && (typeof sanitized.value.summary === 'string' || typeof sanitized.value.assistant_response === 'string'), payload } };
}

export function contextQuery(input) {
  const source = typeof input.prompt === 'string' ? input.prompt : '';
  const safe = sanitizeText(source, 262144).value.replace(/\[(?:PRIVATE|REDACTED)\]/g, ' ');
  return [...new Set(safe.match(/[\p{L}][\p{L}\p{N}_-]{2,40}/gu) ?? [])].slice(0,12).join(' ').slice(0,300);
}
