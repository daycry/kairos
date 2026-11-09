// Launched only by the owned PostgreSQL container probe, never npm test.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { planInstall, applyInstall, loadInstallation } from '../lib/install.mjs';
import { VERSION } from '../lib/config.mjs';
import { lifecycleConfig } from '../lib/lifecycle-config.mjs';
import { startDispatcher } from '../lib/lifecycle.mjs';
import { Dispatcher, MemoryConnection } from '../lib/dispatcher.mjs';
import { Outbox } from '../lib/outbox.mjs';
import { fail } from '../lib/errors.mjs';

const base = process.env.KAIROS_PROBE_BASE;
assert.ok(base && path.isAbsolute(base) && path.basename(base).startsWith('kairos-client-probe-'));
const root = path.join(base,'project é'); fs.mkdirSync(root);
applyInstall(planInstall({ root, url: process.env.KAIROS_PROBE_URL, project: process.env.KAIROS_PROBE_PROJECT,
  keyFile: path.join(base,'fixture.key'), clients: ['codex'], automation: { capture: 'full', context: 'auto', state_directory: path.join(base,'private-state') } }));
const { data } = loadInstallation(root), config = lifecycleConfig(root,data);
const queue = new Outbox(config.directory,config.binding);
const connection = new MemoryConnection(config), original = connection.tool.bind(connection);
let sends = 0, now = 10000;
connection.tool = async (name,args) => { const value = await original(name,args); if (name === 'remember') { sends++; fail('mcp_timeout'); } return value; };
const dispatcher = new Dispatcher(config,queue,{ connection, now: () => now });
let handle = await startDispatcher(config,{ queue, dispatcher, tickMs: 60000 });
try {
  const input = { session_id: 'native-fixture-session', cwd: root, hook_event_name: 'PostToolUse', tool_name: 'Bash', tool_use_id: 'stable-call-1',
    tool_input: { command: 'echo fixture' }, tool_response: { output: 'Árbol: "índice" 🌳, nota:uno,dos <private>PRIVATE-HIDDEN</private>', exit_code: 0 } };
  const bin = path.join(root,'.kairos/runtime',VERSION,'bin/kairos.mjs');
  const hook = () => new Promise((resolve,reject) => {
    const child = spawn(process.execPath,[bin,'hook','--root',root,'--runtime','codex','--event','PostToolUse'],{ stdio: ['pipe','pipe','pipe'] });
    let stdout = '', stderr = ''; child.stdout.on('data', chunk => { stdout += chunk; }); child.stderr.on('data', chunk => { stderr += chunk; });
    child.once('error',reject); child.once('exit',code => { try { assert.equal(code,0); assert.equal(stderr,''); assert.deepEqual(JSON.parse(stdout),{}); resolve(); } catch (error) { reject(error); } });
    child.stdin.end(JSON.stringify(input));
  });
  await hook(); await dispatcher.tick(); assert.equal(queue.status().phases.unknown,1);
  const identity = queue.pending()[0].event;
  await handle.close();
  const restored = new Outbox(config.directory,config.binding);
  assert.deepEqual(restored.pending()[0].event,identity);
  const resumed = new Dispatcher(config,restored,{ connection: new MemoryConnection(config), now: () => now });
  handle = await startDispatcher(config,{ queue: restored, dispatcher: resumed, tickMs: 60000 });
  now += 70000; await resumed.tick(); assert.equal(restored.status().phases.complete,1);
  await hook(); assert.equal(restored.status().records,1); assert.equal(sends,1);
  const context = await resumed.context({ cwd: root, prompt: 'Árbol índice' }); assert.match(context.context,/Árbol/);
  // Technical tool events do not generate extraction/provider jobs. The empty
  // verified job set is complete; summary extraction is tested independently.
  assert.equal(restored.status().phases.complete,1);
} finally { await handle.close(); }
