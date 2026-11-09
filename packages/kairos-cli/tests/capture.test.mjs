import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { randomUUID } from 'node:crypto';
import { normalizeHook, digest, effectiveMode, contextQuery } from '../lib/capture.mjs';
import { sanitizeText, sanitizeTree } from '../lib/privacy.mjs';
import { Outbox } from '../lib/outbox.mjs';

function fixture(t) {
  const parent = fs.realpathSync.native(os.tmpdir()), root = path.join(parent, 'kairos-capture-test-'+randomUUID()); fs.mkdirSync(root);
  const project = path.join(root, 'project'); fs.mkdirSync(project);
  t.after(() => { assert.equal(path.dirname(root), parent); assert.ok(path.basename(root).startsWith('kairos-capture-test-')); fs.rmSync(root, { recursive: true }); });
  const options = { root: project, project: 'alpha', mode: 'summary', deliveryID: 'native-delivery-1' };
  const input = { cwd: project, session_id: 'session-1', hook_event_name: 'PostToolUse', tool_name: 'Bash', tool_use_id: 'call-1', tool_input: { command: 'echo SECRET_RAW_COMMAND' }, tool_response: { output: 'RAW_RESULT', exit_code: 0 } };
  return { root, project, options, input, state: path.join(root, 'private-state'), binding: digest({ project }) };
}

test('capture ceiling requires both opt-ins; summary never copies raw prompts/tool bodies or final answers', t => {
  const f = fixture(t);
  for (const client of ['off','summary','full']) for (const server of ['off','summary','full']) {
    const value = effectiveMode(client, server);
    assert.equal(value, client === 'off' || server === 'off' ? 'off' : client === 'full' && server === 'full' ? 'full' : 'summary');
  }
  const spec = normalizeHook('claude', f.input, f.options);
  assert.ok(!JSON.stringify(spec).includes('SECRET_RAW_COMMAND'));
  assert.ok(!JSON.stringify(spec).includes('RAW_RESULT'));
  const stop = normalizeHook('codex', { ...f.input, hook_event_name: 'Stop', last_assistant_message: 'PRIVATE_FINAL_ANSWER' }, f.options);
  assert.ok(!JSON.stringify(stop).includes('PRIVATE_FINAL_ANSWER'));
  assert.equal(stop.event.generate, false);
  assert.equal(normalizeHook('claude', f.input, { ...f.options, mode: 'off' }).ignored, 'capture_off');
});

test('nested private blocks, credential fields, DSNs, tokens and malformed privacy markers are handled before persistence', () => {
  assert.equal(sanitizeText('public <private>A<private>B</private>C</private> end').value, 'public [PRIVATE] end');
  const secret = 'sk-'+ 'a'.repeat(40);
  const value = sanitizeTree({ title: 'Índice: "Árbol" 🌳', tags: ['nota:uno,dos'], password: 'arbitrary-password', result: `Bearer ${'x'.repeat(40)} ${secret} postgresql://user:pass@host/db` });
  assert.equal(value.value.tags[0], 'nota:uno,dos'); assert.equal(value.value.password, '[REDACTED]');
  assert.ok(!JSON.stringify(value).includes(secret)); assert.ok(!JSON.stringify(value).includes('user:pass'));
  for (const input of ['<private>unclosed','</private>bad','<private attr=x>bad</private>','-----BEGIN PRIVATE KEY-----missing end']) assert.throws(() => sanitizeText(input));
  assert.throws(() => sanitizeTree(JSON.parse('{"__proto__":{"admin":true}}')), /invalid_capture_key/);
  assert.throws(() => sanitizeText('\ud800'), /invalid_capture_text/);
});

test('prefixed assignments, provider tokens, nested and serialized JSON are redacted before the queue', t => {
  const f=fixture(t), secret='V7m9R2t5N8q3C6b1K4w0Z9s2D5h8J6p3';
  const texts=['DB_PASSWORD='+secret,'export AWS_SECRET_ACCESS_KEY="'+secret+'"', 'https://host/?GITHUB_TOKEN='+secret,
    JSON.stringify({ DB_PASSWORD: secret }),JSON.stringify({ text: JSON.stringify({ dbPassword: secret }) }),
    'prefix '+JSON.stringify({ text: JSON.stringify({ GITHUB_TOKEN: secret }) })+' suffix',
    'ghp_'+secret,'xoxb-'+secret,'AIza'+secret,
    '{"APP_\\u0054OKEN":"'+secret+'"}', 'prefix {"APP_\\u0054OKEN":"'+secret+'"} suffix',
    'APP_PASSWORD=alpha,beta;gamma','PGPASSWORD='+secret,'MYSQL_PWD='+secret,
    ...['https','mongodb','mongodb+srv','amqp'].map(scheme=>scheme+'://user:'+secret+'@example.invalid/path'),
    JSON.stringify({PGPASSWORD:secret,result:[{MYSQL_PWD:secret}]}),'https://:'+secret+'@example.invalid/path'];
  for (const value of texts) {
    const clean=sanitizeText(value); assert.ok(clean.redacted); assert.ok(!clean.value.includes(secret));
    assert.equal(sanitizeText(clean.value).value,clean.value);
    const spec=normalizeHook('claude',{ ...f.input,tool_response:{ output: value } },{ ...f.options,mode:'full' });
    assert.ok(!JSON.stringify(spec).includes(secret));
    if(value.includes('alpha,beta')) assert.ok(!clean.value.includes('beta')&&!clean.value.includes('gamma'));
  }
  assert.ok(!JSON.stringify(sanitizeTree({ result: [{ DB_PASSWORD:secret,dbPassword:secret }] })).includes(secret));
  assert.equal(sanitizeText('https://example.invalid/path user@example.invalid').redacted,false);
  for (const text of ['password="REDACTED"','secret="example-placeholder-value"','nonsecret="ordinary prose"','Título: "Árbol" 🌳','{"constructor":"plain","__proto__":"data only"}']) assert.equal(sanitizeText(text).value,text);
});

test('foreign roots, unknown tools, every MCP tool and recursive stop cannot create captures', t => {
  const f = fixture(t);
  assert.equal(normalizeHook('claude', { ...f.input, cwd: f.root }, f.options).ignored, 'foreign_project');
  for (const tool_name of ['mcp__kairos__remember','mcp__other__Read','functions.exec','unknown']) assert.equal(normalizeHook('claude', { ...f.input, tool_name }, f.options).ignored, 'excluded_tool');
  assert.equal(normalizeHook('codex', { ...f.input, stop_hook_active: true }, f.options).ignored, 'recursive_stop');
  assert.throws(() => normalizeHook('claude', { ...f.input, session_id: '../other' }, f.options), /invalid_capture_session/);
});

test('durable admission preserves Unicode, original timestamp, identity and exact body after a restart', t => {
  const f = fixture(t); const spec = normalizeHook('claude', { ...f.input, tool_response: { output: 'Título: "Árbol" 🌳, nota:uno,dos' } }, { ...f.options, mode: 'full' });
  let queue = new Outbox(f.state, f.binding, { now: () => '2026-11-05T10:00:00Z' });
  const first = queue.admit(spec); const body = queue.pending()[0].event;
  queue.close(); queue = new Outbox(f.state, f.binding); t.after(() => queue.close());
  assert.equal(queue.admit(spec).event_id, first.event_id); assert.equal(queue.admit(spec).duplicate, true);
  assert.deepEqual(queue.pending()[0].event, body); assert.match(body.payload.content, /Árbol/);
  const changed = normalizeHook('claude', { ...f.input, tool_response: { output: 'changed' } }, { ...f.options, mode: 'full' });
  assert.throws(() => queue.admit(changed), /capture_identity_conflict/); assert.equal(queue.status().records, 1);
});

test('accepted source bodies are removed locally while original durable receipt identity survives replay', t => {
  const f = fixture(t); const queue = new Outbox(f.state, f.binding); t.after(() => queue.close());
  const spec = normalizeHook('claude', f.input, { ...f.options, mode: 'full' }); queue.admit(spec);
  queue.update(spec.key, { phase: 'accepted', receipt: { event_id: spec.event.event_id }, attempts: 1 });
  assert.equal(queue.pending()[0].event, undefined);
  for (const name of ['queue.json','queue.jsonl']) assert.ok(!fs.readFileSync(path.join(f.state,name),'utf8').includes('SECRET_RAW_COMMAND'));
  queue.update(spec.key, { phase: 'complete' }); queue.checkpoint();
  assert.deepEqual(queue.pending(), []); assert.equal(queue.admit(spec).status, 'complete');
});

test('journal commits survive a torn tail; corrupted committed records fail closed', t => {
  const f = fixture(t); let queue = new Outbox(f.state, f.binding); const spec = normalizeHook('codex', f.input, f.options);
  queue.admit(spec); queue.close(); fs.appendFileSync(path.join(f.state, 'queue.jsonl'), '{"partial":');
  queue = new Outbox(f.state, f.binding); assert.equal(queue.status().records, 1); queue.close();
  assert.ok(fs.readFileSync(path.join(f.state, 'queue.jsonl'),'utf8').endsWith('\n'));
  fs.appendFileSync(path.join(f.state, 'queue.jsonl'), '{"seq":2,"sha256":"bad"}\n');
  assert.throws(() => new Outbox(f.state, f.binding), /capture_journal_corrupt/);
});

test('active ownership, source budget, binding mismatch and linked state paths are rejected', t => {
  const f = fixture(t); let queue = new Outbox(f.state, f.binding, { maxRecords: 1 });
  assert.throws(() => new Outbox(f.state, f.binding), /capture_state_busy/);
  queue.admit(normalizeHook('claude', f.input, f.options));
  assert.throws(() => queue.admit(normalizeHook('claude', { ...f.input, tool_use_id: 'different' }, f.options)), /capture_queue_full/);
  queue.checkpoint(); queue.close();
  assert.throws(() => new Outbox(f.state, digest('another-binding')), /capture_state_corrupt/);
});

test('completed receipts are compacted, active sources are preserved and stale recovery is serialized', t => {
  const f=fixture(t); let queue=new Outbox(f.state,f.binding,{maxRecords:2});
  for(const tool_use_id of ['one','two','three','four']) {
    const spec=normalizeHook('codex',{...f.input,tool_use_id},f.options);
    queue.admit(spec); queue.update(spec.key,{phase:'complete'});
  }
  assert.equal(queue.status().records,2); queue.close();
  queue=new Outbox(f.state,f.binding,{maxRecords:2}); assert.equal(queue.status().records,2); queue.close();
  fs.writeFileSync(path.join(f.state,'queue.lock'),JSON.stringify({pid:123456789,nonce:'stale'}));
  let contested=false;
  queue=new Outbox(f.state,f.binding,{isAlive(){ contested=true; assert.throws(()=>new Outbox(f.state,f.binding),/capture_state_busy/); return false; }});
  assert.ok(contested); queue.close();
});

test('migration removes legacy journal bodies and retains the exact original pending event', t => {
  const f=fixture(t),spec=normalizeHook('codex',f.input,f.options),now='2026-11-05T10:00:00Z';
  fs.mkdirSync(f.state);
  const event={...spec.event,occurred_at:now};
  const body={schema:1,binding:f.binding,seq:1,rows:[{key:spec.key,semantic_hash:spec.semantic_hash,phase:'unknown',attempts:1,
    admitted_at:now,updated_at:now,event_id:event.event_id,item_id:event.item_id,event}]};
  fs.writeFileSync(path.join(f.state,'queue.json'),JSON.stringify({...body,sha256:digest(body)}));
  const queue=new Outbox(f.state,f.binding); t.after(()=>queue.close());
  assert.deepEqual(queue.pending()[0].event,event);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.state,'queue.json'),'utf8')).schema,2);
  assert.ok(!fs.readFileSync(path.join(f.state,'queue.json'),'utf8').includes('tool_input'));
  assert.ok(!JSON.parse(fs.readFileSync(path.join(f.state,'queue.json'),'utf8')).rows[0].event);
});

test('context keywords exclude private content and credentials without storing prompts', () => {
  const query = contextQuery({ prompt: 'Investigar locks <private>SecretPrivateProject</private> Bearer '+ 'z'.repeat(40) });
  assert.match(query, /Investigar locks/); assert.ok(!query.includes('SecretPrivateProject')); assert.ok(!query.includes('zzzz'));
});

test('OpenCode shell exit metadata and Codex negative termination codes are recorded as failures', t => {
  const f = fixture(t);
  for (const tool_response of [{ metadata: { exit: 2 } },{ exit_code: -1 }]) {
    const spec = normalizeHook('opencode-v2',{ ...f.input, tool_response },f.options);
    assert.equal(JSON.parse(spec.event.payload.content).status,'failed');
  }
});
