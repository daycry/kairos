// Privacy runs before disk, IPC capture persistence and remote retrieval queries.
import { fail } from './errors.mjs';

export const secretName = key => /(?:^|_)(?:password|passwd|pwd|passphrase|secret|token|credentials?|api_?key|access_?key(?:_id)?|secret_access_key|access_token|client_secret|private_key|connection_string|authorization|cookie|dsn)$|^pgpassword$/i.test(key.replace(/\\+u([0-9a-f]{4})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16))).replace(/([a-z0-9])([A-Z])/g,'$1_$2').replace(/[.-]/g,'_'));
const placeholder = value => /^(?:\[(?:REDACTED|REDACTADO)\]|REDACTED|REDACTADO|changeme|replace[_ -]?me|example-placeholder-value|<(?:REDACTED|SECRET|PASSWORD|TOKEN|API_KEY|YOUR_[A-Z_]+)>|\$\{[A-Za-z_][A-Za-z0-9_]*\})$/i.test(value);

function assignments(value) {
  const names = /(?<![A-Za-z0-9_.-])((?:\\*["'])?((?:[A-Za-z_]|\\+u[0-9a-fA-F]{4})(?:[A-Za-z0-9_.-]|\\+u[0-9a-fA-F]{4}){0,127})(?:\\*["'])?\s*[:=]\s*)/g;
  let position = 0, output = '', changed = false;
  for (const match of value.matchAll(names)) {
    if (match.index < position || !secretName(match[2])) continue;
    const start = match.index + match[0].length;
    if (/^(?:\[(?:REDACTED|REDACTADO)\]|\$\{[A-Za-z_][A-Za-z0-9_]*\})(?=$|[\s,;&}\]"'])/i.test(value.slice(start))) continue;
    const quote = /^(\\*)(["'])/.exec(value.slice(start));
    let begin = start, end = start;
    if (quote) {
      begin += quote[0].length; end = begin;
      for (; end < value.length; end++) {
        if (value[end] !== quote[2]) continue;
        let slashes = 0; for (let at = end-1; at >= begin && value[at] === '\\'; at--) slashes++;
        if (slashes >= quote[1].length && (slashes-quote[1].length) % (2*(quote[1].length+1)) === 0) break;
      }
      if (end === value.length) fail('invalid_secret_assignment');
      end -= quote[1].length;
    } else { while (end < value.length && !/[\r\n&}\]"']/.test(value[end])) end++; }
    if (end <= begin || placeholder(value.slice(begin,end))) continue;
    output += value.slice(position,begin)+'[REDACTED]'; position = end; changed = true;
  }
  return { value: output + value.slice(position), redacted: changed };
}

export function sanitizeText(value, maximum = 262144, nesting = 0) {
  if(nesting>8) fail('capture_tree_too_large');
  if (typeof value !== 'string' || Buffer.byteLength(value) > maximum || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) fail('invalid_capture_text');
  if(/^\s*[{[\"]/.test(value)) {
    let decoded,parsed=false; try { decoded=JSON.parse(value); parsed=true; } catch { /* plain text uses bounded scanning below */ }
    if(parsed) { const clean=sanitizeTree(decoded,nesting+1,true); if(clean.redacted) return {value:JSON.stringify(clean.value),redacted:true}; }
  }
  let depth = 0, position = 0, output = '', changed = false;
  for (const candidate of value.matchAll(/<\s*\/?\s*private\b/gi)) {
    const tag = /^<\s*(\/?)\s*private\s*>/i.exec(value.slice(candidate.index));
    if (!tag) fail('invalid_private_block');
    if (!tag[1]) { if (depth++ === 0) output += value.slice(position, candidate.index); }
    else {
      if (!depth) fail('invalid_private_block');
      if (--depth === 0) { output += '[PRIVATE]'; position = candidate.index + tag[0].length; changed = true; }
    }
  }
  if (depth) fail('invalid_private_block');
  output += value.slice(position);
  const patterns = [
    /-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----/g,
    /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}/g,
    /\bAKIA[A-Z0-9]{16}\b/g,
    /\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{16,}|AIza[A-Za-z0-9_-]{30,})/g,
    /\bBearer[ \t]+[A-Za-z0-9._~+/=-]{16,}/gi,
    /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g,
    /\b[A-Za-z][A-Za-z0-9+.-]*:\/\/[^\s/@"'<>]*:[^\s/@"'<>]*@[^\s"'<>]+/g,
  ];
  for (const pattern of patterns) output = output.replace(pattern, () => { changed = true; return '[REDACTED]'; });
  const assigned = assignments(output); output = assigned.value; changed ||= assigned.redacted;
  if (/-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----/.test(output)) fail('invalid_private_key_block');
  return { value: output, redacted: changed };
}

export function sanitizeTree(value, nesting = 0, structuredText = false) {
  let nodes = 0, redacted = false;
  function visit(item, depth) {
    if (++nodes > 10000 || depth > 12) fail('capture_tree_too_large');
    if (typeof item === 'string') { const result = sanitizeText(item,262144,nesting); redacted ||= result.redacted; return result.value; }
    if (item === null || typeof item === 'boolean') return item;
    if (typeof item === 'number' && Number.isFinite(item)) return item;
    if (Array.isArray(item)) return item.map(child => visit(child, depth + 1));
    if (item && typeof item === 'object') {
      const result = Object.create(null);
      for (const [key, child] of Object.entries(item)) {
        if (!structuredText && ['__proto__','constructor','prototype'].includes(key)) fail('invalid_capture_key');
        const safe = sanitizeText(key, 500); redacted ||= safe.redacted;
        if (secretName(key) && child !== null && child !== '' && !(typeof child === 'string' && placeholder(child))) { result[safe.value] = '[REDACTED]'; redacted = true; }
        else result[safe.value] = visit(child, depth + 1);
      }
      return result;
    }
    fail('invalid_capture_value');
  }
  const result = visit(value, 0);
  if (Buffer.byteLength(JSON.stringify(result)) > 120000) fail('capture_body_too_large');
  return { value: result, redacted };
}
