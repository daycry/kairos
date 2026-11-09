import path from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { checked, readBytes, jsonBytes, hash } from './files.mjs';
import { objectJSON } from './config.mjs';
import { fail } from './errors.mjs';

export const HOOK_PATHS = ['.claude/settings.json','.codex/hooks.json','.opencode/plugins/kairos-memory.js','.opencode/plugins/kairos-memory/index.js'];
const posix = value => "'"+value.replaceAll("'", "'\"'\"'")+"'";
const ps = value => "'"+value.replaceAll("'", "''")+"'";

export function hookHandler(client, bin, root, event, context, node = process.execPath) {
  const args = [bin,'hook','--root',root,'--runtime',client,'--event',event];
  const command = [node,...args].map(posix).join(' ');
  // No interpolated shell variables or user data. Encoded UTF-16LE keeps
  // quotes, %, !, ampersands and non-ASCII Windows paths literal.
  const source = "[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Text.UTF8Encoding]::new($false); & "+
    [node,...args].map(ps).join(' ')+"; exit $LASTEXITCODE";
  const windows = 'powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand '+Buffer.from(source,'utf16le').toString('base64');
  // Print-mode Claude cancels unfinished background hooks during teardown.
  // Keep terminal admission synchronous; model work stays in the dispatcher.
  const closing = ['Stop','SessionEnd'].includes(event);
  if (client === 'claude') return { type: 'command', command: node, args, timeout: 8, ...(context || closing ? {} : { async: true }) };
  // A native CLI can tear down its async hook children at exit. Admission of
  // the two terminal events must finish before that teardown, without waiting
  // for model work. Codex also explicitly forces SessionEnd to be synchronous.
  const terminal = client === 'codex' && ['Stop','SessionEnd'].includes(event);
  return { type: 'command', command, commandWindows: windows, timeout: event === 'SessionEnd' ? 3 : 8,
    ...(context ? { additionalContextLimit: 2000 } : terminal ? {} : { async: true }) };
}

export function planHooks({ root, clients, automation, previous = {}, bin, replace, openCodeVersion, node }) {
  const changes = [], managed = { ...(previous.managed_hooks ?? {}) };
  const enabled = automation.capture !== 'off' || automation.context === 'auto';
  for (const client of clients) {
    if (client === 'opencode') {
      const relative = openCodeVersion === 2 ? HOOK_PATHS[3] : HOOK_PATHS[2];
      if (!enabled && !managed[relative]) continue;
      const before = readBytes(checked(path.join(root,relative),root));
      const module = path.relative(path.dirname(path.join(root,relative)), path.join(path.dirname(bin),'..','lib','opencode.mjs')).split(path.sep).join('/');
      const source = enabled ? `// Kairos managed memory adapter. No credentials in this file.\nimport { adapterV${openCodeVersion} } from ${JSON.stringify(module.startsWith('.') ? module : './'+module)};\nexport default adapterV${openCodeVersion}(${JSON.stringify(root)});\n` :
        openCodeVersion === 2 ? "// Kairos automatic memory disabled.\nexport default { id: 'kairos-memory', setup() {} };\n" : "// Kairos automatic memory disabled.\nexport default async function () { return {}; }\n";
      const after = Buffer.from(source);
      if (before && !before.equals(after) && !replace) fail('kairos_hook_conflict');
      if (managed[relative] && (!before || hash(before) !== managed[relative].sha256)) fail('managed_hook_changed');
      changes.push({ path: relative, before, after });
      managed[relative] = { kind: 'plugin', sha256: hash(after) };
      continue;
    }
    const relative = client === 'claude' ? HOOK_PATHS[0] : HOOK_PATHS[1];
    const before = readBytes(checked(path.join(root,relative),root));
    if (!enabled && !managed[relative]) continue;
    if (client === 'codex') {
      const toml = readBytes(checked(path.join(root,'.codex/config.toml'),root));
      if (toml && /(?:^|\n)\s*(?:\[\[?\s*["']?hooks\b|["']?hooks["']?\s*=)/m.test(toml.toString('utf8'))) fail('codex_inline_hooks_manual_merge_required');
    }
    const data = objectJSON(before), original = structuredClone(data);
    data.hooks ??= {};
    if (!data.hooks || Array.isArray(data.hooks) || typeof data.hooks !== 'object') fail('invalid_hooks_config');
    const positions = {};
    for (const [event, group] of Object.entries(managed[relative] ?? {})) {
      const groups = data.hooks[event];
      if (!Array.isArray(groups) || groups.filter(value => isDeepStrictEqual(value,group)).length !== 1) fail('managed_hook_changed');
      positions[event] = groups.findIndex(value => isDeepStrictEqual(value,group));
      data.hooks[event] = groups.filter(value => !isDeepStrictEqual(value,group));
      if (!data.hooks[event].length) delete data.hooks[event];
    }
    const desired = {};
    if (enabled) for (const event of ['SessionStart','UserPromptSubmit','PostToolUse','PostToolUseFailure','Stop','SubagentStop','PreCompact','SessionEnd']) {
      const context = ['SessionStart','UserPromptSubmit'].includes(event) && automation.context === 'auto';
      if (automation.capture === 'off' && !context) continue;
      // Codex reports failed shell results through PostToolUse.
      if (client === 'codex' && event === 'PostToolUseFailure') continue;
      const group = { hooks: [hookHandler(client,bin,root,event,context,node)] };
      const groups = data.hooks[event] ?? [];
      if (!Array.isArray(groups)) fail('invalid_hooks_config');
      if (groups.some(value => isDeepStrictEqual(value,group))) fail('unmanaged_duplicate_hook');
      const inserted = [...groups]; inserted.splice(positions[event] ?? groups.length,0,group);
      data.hooks[event] = inserted; desired[event] = group;
    }
    managed[relative] = desired;
    const after = before && isDeepStrictEqual(original,data) ? before : jsonBytes(data);
    changes.push({ path: relative, before, after });
  }
  return { changes, managed };
}
