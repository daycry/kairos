import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { Dispatcher } from '../lib/dispatcher.mjs';
import { Outbox } from '../lib/outbox.mjs';
import { digest } from '../lib/capture.mjs';
import { fail } from '../lib/errors.mjs';

function fixture(t) {
  const parent = fs.realpathSync.native(os.tmpdir()), directory = path.join(parent, 'kairos-dispatch-test-'+randomUUID());
  fs.mkdirSync(directory); const root = path.join(directory, 'project'); fs.mkdirSync(root);
  const config = { root, project_id: 'alpha', capture: 'full', context: 'auto' };
  let now = 10000, policy = 'full'; const persisted = new Map(), calls = [], jobs = [];
  const connection = { async tool(name, args) {
    calls.push({ name, args: structuredClone(args) });
    if (name === 'capture_policy') return { project_id: 'alpha', capture_mode: policy, capture_allowed: policy !== 'off' };
    if (name === 'remember') {
      const { event } = args; const receipt = { event_id: event.event_id, item_id: event.item_id, version: 1, status: 'accepted', jobs: [],capture_hash:event.capture.fingerprint };
      persisted.set(event.event_id, { receipt, event }); return receipt;
    }
    if (name === 'event_status') {
      const row = persisted.get(args.event_id);
      return row ? { receipt: row.receipt, jobs, complete: jobs.every(job => job.state === 'succeeded') } : { found: false, project_id: 'alpha', event_id: args.event_id };
    }
    if (name === 'context') return { context: '[alpha:1] Título: "Árbol" 🌳', items: [{ project_id: 'alpha' }], warnings: ['Unverified memory'] };
    fail('unexpected_tool');
  } };
  const state = path.join(directory, 'private'), binding = digest({ root });
  let queue = new Outbox(state, binding), dispatcher = new Dispatcher(config, queue, { connection, now: () => now });
  const input = { cwd: root, session_id: 's-1', hook_event_name: 'PostToolUse', tool_name: 'Bash', tool_use_id: 'call-1', tool_input: { command: 'echo technical' }, tool_response: { output: 'Revisión: "índice", nota:uno,dos' } };
  t.after(() => { queue.close(); assert.equal(path.dirname(directory), parent); assert.ok(path.basename(directory).startsWith('kairos-dispatch-test-')); fs.rmSync(directory, { recursive: true }); });
  return { config, calls, connection, persisted, input, jobs, state,
    get queue() { return queue; }, get dispatcher() { return dispatcher; },
    advance() { now += 70000; }, policy(value) { policy = value; },
    reopen() { queue.close(); queue = new Outbox(state, binding); dispatcher = new Dispatcher(config, queue, { connection, now: () => now }); } };
}

test('no source reaches disk without fresh consent; full is reduced to technical metadata under summary ceiling', async t => {
  const f = fixture(t); f.policy('off');
  assert.equal((await f.dispatcher.capture('claude', f.input)).status, 'ignored');
  assert.equal(f.queue.status().records, 0);
  f.policy('summary'); await f.dispatcher.capture('claude', f.input);
  assert.ok(!JSON.stringify(f.queue.pending()).includes('technical'));
  assert.ok(!JSON.stringify(f.queue.pending()).includes('Revisión'));
  f.connection.tool = async () => fail('mcp_unauthorized');
  await assert.rejects(f.dispatcher.capture('claude', { ...f.input, tool_use_id: 'call-2' }), /mcp_unauthorized/);
  assert.equal(f.queue.status().records, 1);
});

test('lost acceptance survives process restart and reconciles without resending or changing identities', async t => {
  const f = fixture(t); await f.dispatcher.capture('codex', f.input);
  const original = f.connection.tool;
  f.connection.tool = async (name, args) => { const result = await original(name, args); if (name === 'remember') fail('mcp_timeout'); return result; };
  await f.dispatcher.tick(); assert.equal(f.queue.status().phases.unknown, 1);
  f.reopen(); f.advance(); await f.dispatcher.tick();
  assert.equal(f.queue.status().phases.complete, 1);
  assert.equal(f.calls.filter(c => c.name === 'remember').length, 1);
  assert.ok(!fs.readFileSync(path.join(f.state, 'queue.json'), 'utf8').includes('Revisión'));
});

test('uncertain request replays only after confirmed absence; auth/network failures never turn into resends', async t => {
  const f = fixture(t); await f.dispatcher.capture('claude', f.input);
  const original = f.connection.tool; let first = true;
  f.connection.tool = async (name, args) => { if (name === 'remember' && first) { first = false; fail('mcp_unavailable'); } return original(name, args); };
  await f.dispatcher.tick(); const exact = structuredClone(f.queue.pending()[0].event);
  f.connection.tool = async (name, args) => { if (name === 'event_status') fail('mcp_tool_rejected'); return original(name, args); };
  f.advance(); await f.dispatcher.tick(); assert.equal(f.persisted.size, 0);
  f.connection.tool = original; f.advance(); await f.dispatcher.tick();
  assert.equal(f.persisted.size, 1); assert.deepEqual([...f.persisted.values()][0].event, exact);
  assert.equal(f.queue.status().phases.accepted, 1);
});

test('policy downgrade keeps admitted full content pending; mismatched receipts never erase recoverable bodies', async t => {
  const f = fixture(t); await f.dispatcher.capture('claude', f.input); f.policy('summary');
  await f.dispatcher.tick(); assert.equal(f.calls.filter(c => c.name === 'remember').length, 0);
  const original = f.connection.tool; f.policy('full');
  f.connection.tool = async (name, args) => { const value = await original(name, args); return name === 'remember' ? { ...value, item_id: randomUUID() } : value; };
  f.advance(); await f.dispatcher.tick(); assert.equal(f.queue.status().phases.unknown, 1); assert.ok(f.queue.pending()[0].event);
  f.connection.tool = original; f.advance(); await f.dispatcher.tick(); assert.equal(f.queue.status().phases.complete, 1);
});

test('one rejected write waits by row without aborting the remaining batch',async t=>{
  const f=fixture(t);for(const tool_use_id of ['bad','good'])await f.dispatcher.capture('claude',{...f.input,tool_use_id});
  const original=f.connection.tool;
  const rows=f.queue.pending(),bad=rows[0];
  f.connection.tool=async(name,args)=>{if(name==='remember'&&args.event.event_id===bad.event_id)fail('mcp_tool_rejected');return original(name,args);};
  await f.dispatcher.tick();assert.equal(f.persisted.size,1,JSON.stringify(f.dispatcher.status()));
  assert.ok(f.queue.rows.get(bad.key).next_attempt_at>10000);
  assert.equal(f.queue.rows.get(bad.key).phase,'unknown');
});

test('accepted failed jobs retain receipts and are never blindly republished', async t => {
  const f = fixture(t); const original = f.connection.tool; const job = randomUUID();
  f.connection.tool = async (name, args) => { const value = await original(name, args); if (name === 'remember') { value.jobs = [job]; f.jobs.push({ id: job, state: 'failed' }); } return value; };
  await f.dispatcher.capture('claude', f.input); await f.dispatcher.tick(); f.advance(); await f.dispatcher.tick();
  assert.equal(f.queue.status().phases.failed, 1); assert.equal(f.queue.status().processing_failed, 1);
  assert.equal(f.calls.filter(c => c.name === 'remember').length, 1); assert.equal(f.queue.pending().length, 0);
});

test('context uses fresh authorization, preserves Unicode and provenance, and never falls back to old content', async t => {
  const f = fixture(t); const value = await f.dispatcher.context({ cwd: f.config.root, prompt: 'arreglar índice <private>hidden-keyword</private>' });
  assert.match(value.context, /Árbol/); assert.match(value.context, /untrusted evidence/);
  const args = f.calls.find(c => c.name === 'context').args; assert.equal(args.semantic, false); assert.ok(!args.q.includes('hidden-keyword'));
  f.connection.tool = async () => fail('mcp_unauthorized');
  await assert.rejects(f.dispatcher.context({ cwd: f.config.root }), /mcp_unauthorized/);
  f.config.context = 'off'; assert.deepEqual(await f.dispatcher.context({}), { context: '' });
});

test('pending jobs cannot starve newer captures and local consent changes apply to an already running dispatcher', async t => {
  const f = fixture(t); const original = f.connection.tool;
  f.connection.tool = async (name,args) => { const value = await original(name,args); if (name === 'remember') {
    const id = randomUUID(); value.jobs = [id];
  } return name === 'event_status' && value.receipt ? { ...value, jobs: value.receipt.jobs.map(id => ({ id,state: 'running' })), complete: false } : value; };
  for (let i = 0; i < 4; i++) await f.dispatcher.capture('claude',{ ...f.input, tool_use_id: 'old-'+i });
  await f.dispatcher.tick(); assert.equal(f.queue.status().phases.accepted,4);
  await f.dispatcher.capture('claude',{ ...f.input, tool_use_id: 'new' }); f.advance(); await f.dispatcher.tick();
  assert.equal(f.persisted.size,5);
  const before = f.queue.status().records;
  const changed = { ...f.config, capture: 'off', context: 'off' };
  const current = new Dispatcher(f.config,f.queue,{ connection: f.connection, refresh: () => changed });
  assert.equal((await current.capture('claude',{ ...f.input, tool_use_id: 'disabled' })).status,'ignored');
  assert.deepEqual(await current.context({ cwd: f.config.root }),{ context: '' }); assert.equal(f.queue.status().records,before);
});

test('evicted terminal receipts reconcile identity without a new timestamp or write; changed content conflicts', async t => {
  const f=fixture(t); f.queue.limits.maxRecords=1;
  await f.dispatcher.capture('claude',f.input); await f.dispatcher.tick(); f.advance(); await f.dispatcher.tick();
  const original=[...f.persisted.values()][0].event;
  await f.dispatcher.capture('claude',{...f.input,tool_use_id:'second'}); f.advance(); await f.dispatcher.tick(); f.advance(); await f.dispatcher.tick();
  assert.equal(f.queue.status().records,1);
  const replay=await f.dispatcher.capture('claude',f.input);
  assert.equal(replay.status,'complete'); assert.ok(replay.duplicate);
  assert.deepEqual(f.persisted.get(original.event_id).event,original);
  assert.equal(f.calls.filter(row=>row.name==='remember').length,2);
  await f.dispatcher.capture('claude',{...f.input,tool_use_id:'third'}); f.advance(); await f.dispatcher.tick(); f.advance(); await f.dispatcher.tick();
  await assert.rejects(f.dispatcher.capture('claude',{...f.input,tool_response:{output:'different'}}),/capture_identity_conflict/);
});

test('failed accepted work leaves active rotation; operator retry polls the receipt and never resends the source', async t => {
  const f=fixture(t); const original=f.connection.tool,job=randomUUID(); let failed=true;
  f.connection.tool=async(name,args)=>{
    const value=await original(name,args);
    if(name==='remember') value.jobs=[job];
    if(name==='event_status'&&value.receipt) return {...value,jobs:[{id:job,state:failed?'failed':'succeeded'}],complete:!failed};
    return value;
  };
  await f.dispatcher.capture('claude',f.input); await f.dispatcher.tick(); f.advance(); await f.dispatcher.tick();
  const id=f.queue.status().recent[0].event_id, count=f.calls.length;
  for(let i=0;i<3;i++){f.advance();await f.dispatcher.tick();}
  assert.equal(f.calls.length,count); assert.equal(f.queue.status().phases.failed,1);
  failed=false; f.queue.retry(id); f.advance(); await f.dispatcher.tick();
  assert.equal(f.queue.status().phases.complete,1); assert.equal(f.calls.filter(row=>row.name==='remember').length,1);
});
