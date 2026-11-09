import path from 'node:path';
import net from 'node:net';
import { isDeepStrictEqual } from 'node:util';
import { text, jsonBytes } from './files.mjs';
import { fail } from './errors.mjs';

export const CLIENT_PATHS = { claude: '.mcp.json', codex: '.codex/config.toml', opencode: 'opencode.json' };
export const MANIFEST = '.kairos/installation.json';
export const VERSION = '0.2.0';
export const COMPATIBLE_VERSIONS = ['0.1.0', '0.1.1', '0.1.2', '0.1.3', '0.1.4', '0.1.5', '0.1.6', VERSION];
export const RUNTIME_FILES = ['package.json','bin/kairos.mjs','lib/errors.mjs','lib/files.mjs','lib/config.mjs','lib/install.mjs','lib/mcp.mjs','lib/cli.mjs',
  'lib/privacy.mjs','lib/capture.mjs','lib/outbox.mjs','lib/dispatcher.mjs','lib/lifecycle-config.mjs','lib/lifecycle.mjs','lib/hooks.mjs','lib/opencode.mjs',
  'lib/code-analysis.mjs','lib/code-worker.mjs',
  ...['tree-sitter.js','tree-sitter.wasm','tree-sitter-javascript.wasm','tree-sitter-typescript.wasm','tree-sitter-tsx.wasm','tree-sitter-python.wasm','tree-sitter-php.wasm',
    'LICENSE','LICENSE-tree-sitter','LICENSE-tree-sitter-javascript','LICENSE-tree-sitter-typescript','LICENSE-tree-sitter-python','LICENSE-tree-sitter-php','provenance.json'].map(name=>'lib/vendor/tree-sitter/'+name)];

// JSON.parse silently accepts duplicate properties; installation must not.
export function objectJSON(bytes) {
  if (!bytes) return {};
  const source = text(bytes);
  let at = 0, nodes = 0;
  const whitespace = () => { while (/\s/.test(source[at] || '') && at < source.length) at++; };
  function string() {
    if (source[at] !== '"') fail('invalid_json_or_jsonc');
    const start = at++;
    while (at < source.length) {
      if (source[at] === '\\') { at += 2; continue; }
      if (source[at++] === '"') {
        try { return JSON.parse(source.slice(start, at)); } catch { fail('invalid_json_or_jsonc'); }
      }
    }
    fail('invalid_json_or_jsonc');
  }
  function value(depth = 0) {
    if (++nodes > 100000 || depth > 64) fail('config_too_complex');
    whitespace();
    if (source[at] === '"') return string();
    if (source[at] === '{') {
      at++; whitespace(); const result = {}, seen = new Set();
      if (source[at] === '}') { at++; return result; }
      while (at < source.length) {
        whitespace(); const key = string(); whitespace();
        if (seen.has(key)) fail('duplicate_config_key');
        seen.add(key);
        if (source[at++] !== ':') fail('invalid_json_or_jsonc');
        Object.defineProperty(result, key, { value: value(depth + 1), enumerable: true, writable: true, configurable: true });
        whitespace(); const end = source[at++];
        if (end === '}') return result;
        if (end !== ',') fail('invalid_json_or_jsonc');
      }
    } else if (source[at] === '[') {
      at++; whitespace(); const result = [];
      if (source[at] === ']') { at++; return result; }
      while (at < source.length) {
        result.push(value(depth + 1)); whitespace(); const end = source[at++];
        if (end === ']') return result;
        if (end !== ',') fail('invalid_json_or_jsonc');
      }
    } else {
      const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(source.slice(at));
      if (match) { at += match[0].length; return JSON.parse(match[0]); }
    }
    fail('invalid_json_or_jsonc');
  }
  const result = value(); whitespace();
  if (at !== source.length || result === null || Array.isArray(result) || typeof result !== 'object') fail('invalid_json_config');
  return result;
}

export function baseURL(value) {
  if (typeof value !== 'string' || /\s/.test(value)) fail('invalid_url');
  let url;
  try {
    const rawPath = value.replace(/^[a-z][\w+.-]*:\/\/[^/]+/i, '');
    if (decodeURIComponent(rawPath).split(/[\\/]/).includes('..') || decodeURIComponent(rawPath).includes('\\')) fail('invalid_url');
    url = new URL(value);
  } catch { fail('invalid_url'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) fail('invalid_url');
  const host = url.hostname.replace(/^\[|\]$/g, '');
  const local = host === 'localhost' || host === '::1' || net.isIP(host) === 4 && host.startsWith('127.');
  if (url.protocol === 'http:' && !local) fail('remote_requires_https');
  if (/\/(?:mcp|app|v1)\/?$/.test(url.pathname)) fail('use_base_url_not_route');
  return url.href.replace(/\/+$/, '');
}

export function clientEntry(client, root, url, keyFile, version, node = process.execPath, codeAnalysis = 'off') {
  const bin = path.join(root, '.kairos', 'runtime', VERSION, 'bin', 'kairos.mjs');
  const args = [bin, 'mcp', '--url', url, '--key-file', keyFile];
  if(codeAnalysis==='on') args.push('--code-analysis','on','--root',root);
  if (client === 'claude') return { type: 'stdio', command: node, args };
  if (client === 'codex') return { command: node, args };
  if (client !== 'opencode' || ![1, 2].includes(version)) fail('invalid_client');
  return { type: 'local', command: [node, ...args], [version === 2 ? 'disabled' : 'enabled']: version !== 2 };
}

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export function openCodeVersion(data, requested) {
  const mcp = data.mcp ?? {};
  if (!isObject(mcp)) fail('invalid_mcp_config');
  const existing = Object.hasOwn(mcp, 'servers') ? 2 : Object.keys(mcp).length ? 1 : null;
  if (requested && existing && requested !== existing) fail('opencode_version_conflict');
  const version = requested || existing;
  if (![1, 2].includes(version)) fail('opencode_version_required');
  return version;
}

export function mergeJSON(bytes, client, desired, replace = false, version) {
  const original = objectJSON(bytes), result = structuredClone(original);
  const field = client === 'claude' ? 'mcpServers' : 'mcp';
  if (!Object.hasOwn(result, field)) result[field] = {};
  let container = result[field];
  if (!isObject(container)) fail('invalid_mcp_config');
  if (client === 'opencode' && version === 2) {
    if (!Object.hasOwn(container, 'servers')) container.servers = {};
    container = container.servers;
    if (!isObject(container)) fail('invalid_mcp_config');
  }
  if (Object.hasOwn(container, 'kairos') && !isDeepStrictEqual(container.kairos, desired) && !replace) fail('kairos_config_conflict');
  container.kairos = desired;
  return isDeepStrictEqual(result, original) && bytes ? bytes : jsonBytes(result);
}

// Deliberately conservative TOML editing: only a conventional Kairos table is
// managed. All unrelated bytes are retained. Inline/dotted Kairos definitions
// and unsupported syntax fail closed rather than rewriting a whole document.
function tomlStatements(source) {
  const statements = [];
  let start = 0, quote = null, triple = false, escape = false, comment = false;
  const brackets = [];
  for (let at = 0; at < source.length; at++) {
    const c = source[at];
    if (comment) { if (c !== '\n') continue; comment = false; }
    if (quote) {
      if (quote === '"' && escape) { escape = false; continue; }
      if (quote === '"' && c === '\\') { escape = true; continue; }
      if (triple && source.slice(at, at + 3) === quote.repeat(3)) { at += 2; quote = null; triple = false; }
      else if (!triple && c === quote) quote = null;
      else if (!triple && (c === '\n' || c === '\r')) fail('invalid_toml');
      continue;
    }
    if (c === '#') { comment = true; continue; }
    if (c === '"' || c === "'") {
      quote = c; triple = source.slice(at, at + 3) === c.repeat(3);
      if (triple) at += 2;
    } else if (c === '[' || c === '{') brackets.push(c);
    else if (c === ']' || c === '}') { if (brackets.pop() !== (c === ']' ? '[' : '{')) fail('invalid_toml'); }
    if (c === '\n' && brackets.length === 0) { statements.push({ start, end: at + 1, text: source.slice(start, at + 1) }); start = at + 1; }
  }
  if (quote || brackets.length) fail('invalid_toml');
  if (start < source.length) statements.push({ start, end: source.length, text: source.slice(start) });
  return statements;
}

function headerPath(line) {
  const match = /^\s*\[([^\n]+)\]\s*(?:#[^\n]*)?$/.exec(line.trim());
  if (!match) return null;
  // Unrelated array tables are preserved but never edited.
  if (match[1].startsWith('[')) return { array: true, parts: [] };
  const raw = match[1]; const parts = []; let at = 0;
  while (at < raw.length) {
    while (/\s/.test(raw[at] || '') && at < raw.length) at++;
    let part;
    if (raw[at] === '"' || raw[at] === "'") {
      const q = raw[at++], start = at;
      while (at < raw.length && raw[at] !== q) { if (raw[at] === '\\') fail('unsupported_toml_layout'); at++; }
      if (raw[at++] !== q) fail('invalid_toml');
      part = raw.slice(start, at - 1);
    } else {
      const key = /^[A-Za-z0-9_-]+/.exec(raw.slice(at));
      if (!key) fail('invalid_toml'); part = key[0]; at += part.length;
    }
    parts.push(part);
    while (/\s/.test(raw[at] || '') && at < raw.length) at++;
    if (at < raw.length && raw[at++] !== '.') fail('invalid_toml');
  }
  return { array: false, parts };
}

function withoutComment(value) {
  let quote = null, escape = false;
  for (let at = 0; at < value.length; at++) {
    const c = value[at];
    if (quote) {
      if (quote === '"' && escape) { escape = false; continue; }
      if (quote === '"' && c === '\\') { escape = true; continue; }
      if (c === quote) quote = null;
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '#') return value.slice(0, at).trim();
  }
  return value.trim();
}

// This validates the value grammar needed for conservative edits. Unsupported
// TOML extensions are rejected; no attempt is made to rewrite unrelated values.
function tomlValue(source) {
  let at = 0, nodes = 0;
  function whitespace() {
    while (at < source.length) {
      if (/\s/.test(source[at])) at++;
      else if (source[at] === '#') { while (at < source.length && source[at] !== '\n') at++; }
      else break;
    }
  }
  function string() {
    const quote = source[at++], triple = source.slice(at - 1, at + 2) === quote.repeat(3);
    if (triple) at += 2;
    let out = '';
    if (triple && source[at] === '\n') at++;
    while (at < source.length) {
      if (triple && source.slice(at, at + 3) === quote.repeat(3)) { at += 3; return out; }
      const c = source[at++];
      if (!triple && c === quote) return out;
      if (!triple && (c === '\n' || c === '\r')) fail('invalid_toml');
      if (quote === '"' && c === '\\') {
        const escape = source[at++], map = { b:'\b', t:'\t', n:'\n', f:'\f', r:'\r', '"':'"', '\\':'\\' };
        if (Object.hasOwn(map, escape)) out += map[escape];
        else if (escape === 'u' || escape === 'U') {
          const width = escape === 'u' ? 4 : 8, code = source.slice(at, at + width);
          if (!new RegExp('^[0-9a-fA-F]{'+width+'}$').test(code)) fail('invalid_toml');
          const point = Number.parseInt(code, 16);
          if (point > 0x10ffff || point >= 0xd800 && point <= 0xdfff) fail('invalid_toml');
          out += String.fromCodePoint(point); at += width;
        } else if (triple && /\s/.test(escape || '')) { while (/\s/.test(source[at] || '') && at < source.length) at++; }
        else fail('invalid_toml');
      } else out += c;
    }
    fail('invalid_toml');
  }
  function value(depth = 0) {
    if (++nodes > 100000 || depth > 64) fail('config_too_complex');
    whitespace(); const first = source[at];
    if (first === '"' || first === "'") return string();
    if (first === '[') {
      at++; whitespace(); const values = [];
      while (source[at] !== ']') {
        if (at >= source.length) fail('invalid_toml');
        values.push(value(depth + 1)); whitespace();
        if (source[at] === ']') break;
        if (source[at++] !== ',') fail('invalid_toml');
        whitespace();
      }
      at++; return values;
    }
    if (first === '{') {
      at++; whitespace(); const values = {}, keys = new Set();
      while (source[at] !== '}') {
        let key;
        if (source[at] === '"' || source[at] === "'") key = string();
        else { const match = /^[A-Za-z0-9_.-]+/.exec(source.slice(at)); if (!match) fail('invalid_toml'); key = match[0]; at += key.length; }
        whitespace(); if (source[at++] !== '=' || keys.has(key)) fail('invalid_toml');
        keys.add(key); Object.defineProperty(values, key, { value:value(depth + 1), enumerable:true });
        whitespace(); if (source[at] === '}') break;
        if (source[at++] !== ',') fail('invalid_toml');
        whitespace(); if (source[at] === '}') fail('unsupported_toml_layout');
      }
      at++; return values;
    }
    const start = at;
    while (at < source.length && !/[\s,#\]}]/.test(source[at])) at++;
    const token = source.slice(start, at);
    if (token === 'true') return true;
    if (token === 'false') return false;
    if (/^[+-]?(?:inf|nan)$/.test(token)) return token;
    if (/^[+-]?(?:0|[1-9](?:_?\d)*)(?:\.\d(?:_?\d)*)?(?:[eE][+-]?\d(?:_?\d)*)?$/.test(token) || /^0(?:x[\da-fA-F](?:_?[\da-fA-F])*|o[0-7](?:_?[0-7])*|b[01](?:_?[01])*)$/.test(token)) return Number(token.replaceAll('_',''));
    if (/^\d{4}-\d{2}-\d{2}(?:[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?$/.test(token) || /^\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(token)) return token;
    fail('invalid_or_unsupported_toml');
  }
  const parsed = value(); whitespace();
  if (at !== source.length) fail('invalid_or_unsupported_toml');
  return parsed;
}

export function mergeTOML(bytes, desired, replace = false) {
  const source = bytes ? text(bytes) : '';
  const statements = tomlStatements(source);
  let current = [], dropping = false, found = false, target = {}, kept = '', duplicate = new Set(), scope = '', arrayIndex = 0;
  const tables = new Set(), keys = new Set();
  for (const statement of statements) {
    const line = statement.text.trim();
    const header = line.startsWith('[') ? headerPath(line) : null;
    if (line && !line.startsWith('#') && !header && !line.includes('=')) fail('invalid_toml');
    if (header) {
      current = header.parts;
      scope = JSON.stringify(current);
      if (header.array) scope = 'array:' + (++arrayIndex);
      else if (tables.has(scope)) fail('duplicate_toml_table');
      else tables.add(scope);
      dropping = current[0] === 'mcp_servers' && current[1] === 'kairos';
      if (dropping) {
        if (header.array || current.length !== 2 || found) fail('unsupported_toml_layout');
        found = true;
      }
    } else if (line && !line.startsWith('#')) {
      const equals = line.indexOf('=');
      const key = line.slice(0, equals).trim();
      if (!/^(?:[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*')(?:\s*\.\s*(?:[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*'))*$/.test(key)) fail('unsupported_toml_layout');
      const keyIdentity = scope + ':' + key;
      if (keys.has(keyIdentity)) fail('duplicate_toml_key');
      keys.add(keyIdentity);
      const parsed = tomlValue(statement.text.slice(statement.text.indexOf('=') + 1));
      if ((current.length === 0 && /^(?:mcp_servers|["']mcp_servers["'])(?:\s|\.|$)/.test(key)) ||
          current.length === 1 && current[0] === 'mcp_servers' && /^(?:kairos|["']kairos["'])(?:\s|\.|$)/.test(key)) fail('unsupported_toml_layout');
      if (dropping) {
        if (!/^[A-Za-z0-9_-]+$/.test(key) || duplicate.has(key)) fail('invalid_toml');
        duplicate.add(key);
        target[key] = parsed;
      }
    }
    if (!dropping) kept += statement.text;
  }
  if (found && Object.keys(target).length === Object.keys(desired).length && Object.keys(desired).every(k => JSON.stringify(target[k]) === JSON.stringify(desired[k]))) return bytes;
  if (found && !replace) fail('kairos_config_conflict');
  const entry = '[mcp_servers.kairos]\n' + Object.entries(desired).map(([k,v]) => `${k} = ${JSON.stringify(v)}\n`).join('');
  return Buffer.from(kept.replace(/[\r\n]+$/, '') + (kept.trim() ? '\n\n' : '') + entry);
}
