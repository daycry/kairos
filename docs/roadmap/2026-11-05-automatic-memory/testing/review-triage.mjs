import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { planInstall, applyInstall, loadInstallation } from '../../../../packages/kairos-cli/lib/install.mjs';
import { Outbox } from '../../../../packages/kairos-cli/lib/outbox.mjs';
import { normalizeHook, digest } from '../../../../packages/kairos-cli/lib/capture.mjs';
import { sanitizeText } from '../../../../packages/kairos-cli/lib/privacy.mjs';
import { Dispatcher } from '../../../../packages/kairos-cli/lib/dispatcher.mjs';

const parent = fs.realpathSync.native(os.tmpdir()), base = fs.mkdtempSync(path.join(parent,'kairos-review-triage-'));
const results = [];
const result = (id,evidence) => results.push({ id, confirmed: true, evidence });
function fixture(name,clients=['claude']) {
  const root = path.join(base,name); fs.mkdirSync(root);
  const keyFile = path.join(base,name+'.key'); fs.writeFileSync(keyFile,'synthetic-triage-credential-only');
  const options = { root,clients,keyFile,url: 'http://127.0.0.1:5173',project: 'fixture', openCodeVersion: 2,
    automation: { capture: 'summary',context: 'auto',state_directory: path.join(base,name+'-state') } };
  applyInstall(planInstall(options)); return { root,options };
}
let queue;
try {
  const first = fixture('runtime',['opencode']), original = process.execPath;
  try {
    process.execPath = path.join(base,'opencode.exe');
    assert.throws(() => loadInstallation(first.root), /installation_binding_conflict/);
  } finally { process.execPath = original; }
  result('I-1','Changing the host runtime executable prevents loadInstallation before any daemon launch. Native OpenCode execution remains a separate acceptance test.');

  const second = fixture('foreign-hook');
  const settingsPath = path.join(second.root,'.claude/settings.json');
  const settings = JSON.parse(fs.readFileSync(settingsPath,'utf8'));
  settings.hooks.PostToolUse.push({ matcher: 'Read',hooks: [{ type: 'command',command: 'unrelated-hook' }] });
  fs.writeFileSync(settingsPath,JSON.stringify(settings));
  assert.throws(() => loadInstallation(second.root), /configuration_drift/);
  result('I-5','Appending an unrelated hook after the managed group makes loadInstallation reject the complete installation.');

  const third = fixture('version');
  const manifestPath = path.join(third.root,'.kairos/installation.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath,'utf8')); manifest.runtime.version = '0.0.9';
  fs.writeFileSync(manifestPath,JSON.stringify(manifest));
  assert.throws(() => planInstall({ ...third.options,replace: true }), /incompatible_installation_manifest/);
  result('I-8','A simulated prior manifest version is rejected before --replace can perform an upgrade. No future package was assumed to exist.');

  const root = path.join(base,'queue-project'); fs.mkdirSync(root);
  const binding = digest({ root }); queue = new Outbox(path.join(base,'queue'),binding,{ maxRecords: 2 });
  const input = { cwd: root,session_id: 'fixture-session',tool_name: 'Read',hook_event_name: 'PostToolUse' };
  const spec = id => normalizeHook('codex',{ ...input,tool_use_id: id },{ root,project: 'fixture',mode: 'summary' });
  for (const id of ['first','second']) { const item = spec(id); queue.admit(item); queue.update(item.key,{ phase: 'complete' }); }
  queue.close(); queue = new Outbox(path.join(base,'queue'),binding,{ maxRecords: 2 });
  assert.equal(queue.status().phases.complete,2);
  assert.throws(() => queue.admit(spec('third')), /capture_queue_full/);
  queue.close(); queue = null;
  result('I-3','Two completed records exhaust maxRecords=2; checkpoint/restart does not permit a third admission.');

  const synthetic = 'V7m9R2t5N8q3C6b1K4w0Z9s2D5h8J6p3';
  for (const label of ['DB_PASSWORD','AWS_SECRET_ACCESS_KEY','GITHUB_TOKEN']) {
    assert.ok(sanitizeText(label+'='+synthetic).value.includes(synthetic));
  }
  result('I-9-client','Synthetic prefixed .env assignments survive sanitizeText; no real credentials were used.');

  const state = path.join(base,'stalled'), clock = { now: 10000 }, calls = [];
  queue = new Outbox(state,digest('stalled'));
  const item = spec('stalled'); queue.admit(item);
  const job = randomUUID();
  queue.update(item.key,{ phase: 'accepted',receipt: { event_id: item.event.event_id,item_id: item.event.item_id,version: 1,status: 'accepted',jobs: [job] } });
  const connection = { async tool(name) { calls.push(name); return { receipt: queue.pending()[0].receipt,jobs: [{ id: job,state: 'failed' }],complete: false }; } };
  const dispatcher = new Dispatcher({ root,project_id: 'fixture',capture: 'summary' },queue,{ connection,now: () => clock.now });
  for (let i=0;i<3;i++) { await dispatcher.tick(); clock.now += 4000; }
  assert.equal(calls.filter(name => name === 'event_status').length,3);
  assert.equal(queue.pending()[0].phase,'accepted');
  result('I-4','The same failed job is polled in all three eligible ticks and stays in the active queue. Large-scale latency was not benchmarked.');
} finally {
  queue?.close();
  assert.equal(path.dirname(base),parent); assert.ok(path.basename(base).startsWith('kairos-review-triage-'));
  assert.equal(fs.lstatSync(base).isSymbolicLink(),false); fs.rmSync(base,{ recursive: true });
}
console.log(JSON.stringify({ source: 'synthetic local reproduction; no servers or providers',results },null,2));
