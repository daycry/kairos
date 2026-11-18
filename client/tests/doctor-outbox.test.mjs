import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import { applyInstall, planInstall, loadInstallation } from '../lib/install.mjs';
import { lifecycleConfig } from '../lib/lifecycle-config.mjs';
import { normalizeHook } from '../lib/capture.mjs';
import { Outbox } from '../lib/outbox.mjs';
import { doctor, REQUIRED_TOOLS } from '../lib/mcp.mjs';

// T-76 (CA-32, P-07): `kairos doctor` warns when the capture queue on this disk holds captures that have waited too long. Everything runs in a temporary directory with an injected
// clock: the real profile is never read and nothing leaves the machine.
const T0 = Date.parse('2026-11-18T10:00:00Z');
const iso = ms => new Date(ms).toISOString();

function fixture(t, automation = { capture: 'summary', context: 'auto' }) {
  const parent = fs.realpathSync.native(os.tmpdir()), base = path.join(parent, 'kairos-doctor-outbox-test-' + randomUUID()); fs.mkdirSync(base);
  const root = path.join(base, 'project'); fs.mkdirSync(root);
  const keyFile = path.join(base, 'private.key'); fs.writeFileSync(keyFile, 'synthetic-private-kairos-token');
  const options = { root, keyFile, project: 'alpha', url: 'http://127.0.0.1:5173', clients: ['claude'], openCodeVersion: 2, automation: { ...automation, state_directory: path.join(base, 'private-state') } };
  t.after(() => { assert.equal(path.dirname(base), parent); assert.ok(path.basename(base).startsWith('kairos-doctor-outbox-test-')); fs.rmSync(base, { recursive: true }); });
  applyInstall(planInstall(options));
  const { data } = loadInstallation(root);
  return { root, base, config: lifecycleConfig(root, data) };
}

function admit(f, at, id = 'call-1') {
  const spec = normalizeHook('claude', { cwd: f.root, session_id: 'session-1', hook_event_name: 'PostToolUse', tool_name: 'Bash', tool_use_id: id, tool_input: { command: 'echo ' + id }, tool_response: { output: 'out', exit_code: 0 } },
    { root: f.root, project: 'alpha', mode: 'summary', deliveryID: 'native-' + id });
  const queue = new Outbox(f.config.directory, f.config.binding, { now: () => iso(at) });
  try { return queue.admit(spec); } finally { queue.close(); }
}

const snapshot = directory => {
  const files = [];
  const walk = dir => { for (const entry of fs.readdirSync(dir, { withFileTypes: true })) { const file = path.join(dir, entry.name); entry.isDirectory() ? walk(file) : files.push([path.relative(directory, file), createHash('sha256').update(fs.readFileSync(file)).digest('hex')]); } };
  walk(directory); return JSON.stringify(files.sort());
};

test('doctor reports the age of the oldest pending capture and warns above the threshold', async t => {
  const f = fixture(t); admit(f, T0 - 120_000, 'call-old'); admit(f, T0 - 30_000, 'call-new');
  const fresh = await doctor(f.root, { now: () => T0 - 120_000 + 600_000, queueStaleSeconds: 900 });
  assert.equal(fresh.status, 'configured');
  assert.deepEqual(fresh.capture_queue, { pending: 2, oldest_pending_seconds: 600, threshold_seconds: 900, stale: false });
  assert.equal(fresh.warnings, undefined);
  const stale = await doctor(f.root, { now: () => T0 - 120_000 + 901_000, queueStaleSeconds: 900 });
  assert.equal(stale.capture_queue.stale, true); assert.equal(stale.capture_queue.oldest_pending_seconds, 901);
  assert.deepEqual(stale.warnings, ['capture_queue_stale']); assert.equal(stale.status, 'degraded');
});

test('the default threshold is 900 seconds and KAIROS_QUEUE_STALE_SECONDS replaces it', async t => {
  const f = fixture(t); admit(f, T0);
  assert.equal((await doctor(f.root, { now: () => T0 + 899_000 })).capture_queue.threshold_seconds, 900);
  assert.equal((await doctor(f.root, { now: () => T0 + 899_000 })).capture_queue.stale, false);
  assert.equal((await doctor(f.root, { now: () => T0 + 901_000 })).capture_queue.stale, true);
  const before = process.env.KAIROS_QUEUE_STALE_SECONDS; process.env.KAIROS_QUEUE_STALE_SECONDS = '60';
  t.after(() => { before === undefined ? delete process.env.KAIROS_QUEUE_STALE_SECONDS : process.env.KAIROS_QUEUE_STALE_SECONDS = before; });
  const custom = await doctor(f.root, { now: () => T0 + 61_000 });
  assert.deepEqual([custom.capture_queue.threshold_seconds, custom.capture_queue.stale], [60, true]);
  process.env.KAIROS_QUEUE_STALE_SECONDS = 'soon';  // a value that is no positive number never switches the warning off
  assert.equal((await doctor(f.root, { now: () => T0 + 901_000 })).capture_queue.threshold_seconds, 900);
});

test('the output of doctor does not change when no capture is pending', async t => {
  const none = fixture(t);
  const without = await doctor(none.root); assert.deepEqual(Object.keys(without).sort(), ['clients', 'dispatcher', 'network_checked', 'project_id', 'status']); assert.equal(without.status, 'configured');
  const spec = admit(none, T0); assert.equal(spec.status, 'pending');
  const queue = new Outbox(none.config.directory, none.config.binding); const row = queue.pending(5, Infinity, false)[0];
  queue.update(row.key, { phase: 'complete' }); queue.close();  // delivered: nothing waits any more
  const done = await doctor(none.root, { now: () => T0 + 86_400_000 });
  assert.deepEqual(done, without);
  const off = fixture(t, { capture: 'off', context: 'off' });
  assert.deepEqual(Object.keys(await doctor(off.root)).sort(), ['clients', 'network_checked', 'project_id', 'status']);
});

test('doctor sends nothing to the server, takes no lock and writes nothing in the queue directory', async t => {
  const f = fixture(t); admit(f, T0 - 5_000_000);
  const realFetch = globalThis.fetch; let calls = 0; globalThis.fetch = async () => { calls++; throw new Error('network_forbidden'); };
  t.after(() => { globalThis.fetch = realFetch; });
  const holder = new Outbox(f.config.directory, f.config.binding); t.after(() => holder.close());  // the dispatcher holds the lock while doctor reads
  const before = snapshot(f.config.directory);
  const result = await doctor(f.root, { now: () => T0 });
  assert.equal(result.capture_queue.stale, true); assert.equal(result.network_checked, false); assert.equal(calls, 0);
  assert.equal(snapshot(f.config.directory), before);
});

test('an unreadable queue is reported as such and never makes doctor fail', async t => {
  const f = fixture(t); admit(f, T0); fs.writeFileSync(path.join(f.config.directory, 'queue.jsonl'), '{"seq":1,"binding":"x","sha256":"bad"}\n');
  const result = await doctor(f.root, { now: () => T0 });
  assert.deepEqual(result.capture_queue, { status: 'unreadable' }); assert.equal(result.status, 'configured');
});

test('an online doctor keeps the stale warning in its status', async t => {
  const f = fixture(t); admit(f, T0 - 5_000_000);
  const transport = { async request() {}, async call(id, method) {
    if (method === 'initialize') return {};
    if (method === 'tools/list') return { tools: [...REQUIRED_TOOLS, 'capture_policy'].map(name => ({ name,
      inputSchema: name === 'event_status' ? { properties: { project_id: {} } } : name === 'remember' ? { $defs: { AutomaticCapture: {} } } : name === 'context' ? { properties: { match_mode: {} } } : {} })) };
    return { structuredContent: { projects: [{ id: 'alpha' }] } };
  } };
  const fresh = await doctor(f.root, { online: true, transport, now: () => T0 - 5_000_000 + 1000 });
  assert.equal(fresh.status, 'ready');
  const result = await doctor(f.root, { online: true, transport, now: () => T0 });
  assert.equal(result.status, 'degraded'); assert.deepEqual(result.warnings, ['capture_queue_stale']); assert.equal(result.project_authorized, true);
});
