import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { Writable, Readable } from 'node:stream';
import { planInstall, applyInstall, preview, recover, loadInstallation, PACKAGE_ROOT } from '../lib/install.mjs';
import { atomicWrite, checked, hash } from '../lib/files.mjs';
import { objectJSON, mergeTOML, CLIENT_PATHS, RUNTIME_FILES, VERSION } from '../lib/config.mjs';
import { doctor, REQUIRED_TOOLS } from '../lib/mcp.mjs';
import { main } from '../lib/cli.mjs';

function fixture(t) {
  const temporary = fs.realpathSync.native(os.tmpdir());
  const base = path.join(temporary, 'kairos-node-test-' + randomUUID());
  fs.mkdirSync(base); const root = path.join(base, 'project'); fs.mkdirSync(root);
  const keyFile = path.join(base, 'private.key'); fs.writeFileSync(keyFile, 'synthetic-kairos-credential-for-tests');
  t.after(() => {
    const target = path.resolve(base);
    assert.equal(path.dirname(target), temporary); assert.ok(path.basename(target).startsWith('kairos-node-test-'));
    assert.equal(fs.lstatSync(target).isSymbolicLink(), false);
    fs.rmSync(target, { recursive: true, force: true });
  });
  const options = { root, url: 'http://127.0.0.1:5173', project: 'synthetic-project', keyFile,
    clients: ['claude','codex','opencode'], openCodeVersion: 2 };
  return { base, root, keyFile, options, plan: changes => planInstall({ ...options, ...changes }) };
}

function stream() {
  let content = '';
  const value = new Writable({ write(chunk, encoding, done) { content += chunk.toString(); done(); } });
  return { value, get content() { return content; } };
}

test('preview makes no writes and copies no secret into its result', t => {
  const f = fixture(t), plan = f.plan();
  assert.equal(preview(plan).status, 'preview'); assert.deepEqual(fs.readdirSync(f.root), []);
  assert.equal(plan.changes.length, RUNTIME_FILES.length + 4);
  assert.equal(JSON.stringify(preview(plan)).includes(fs.readFileSync(f.keyFile,'utf8')), false);
});

test('all clients use a stable Node stdio runtime, without Python, env export or inline secrets', async t => {
  const f = fixture(t);
  assert.equal(applyInstall(f.plan()).status, 'installed');
  assert.equal(applyInstall(f.plan()).status, 'unchanged');
  const secret = fs.readFileSync(f.keyFile, 'utf8');
  for (const relative of Object.values(CLIENT_PATHS)) {
    const value = fs.readFileSync(path.join(f.root,relative),'utf8');
    assert.equal(value.includes(secret),false); assert.equal(value.includes('KAIROS_API_KEY'),false);
    assert.equal(value.includes('python'),false); assert.equal(value.includes('kairos.mjs'),true);
  }
  const claude = JSON.parse(fs.readFileSync(path.join(f.root,'.mcp.json'))).mcpServers.kairos;
  assert.equal(claude.type,'stdio'); assert.equal(claude.command,fs.realpathSync.native(process.execPath));
  assert.equal(claude.args[0],path.join(f.root,'.kairos/runtime',VERSION,'bin/kairos.mjs'));
  const openCode = JSON.parse(fs.readFileSync(path.join(f.root,'opencode.json'))).mcp.servers.kairos;
  assert.equal(openCode.type,'local'); assert.equal(openCode.disabled,false);
  assert.equal((await doctor(f.root)).status,'configured');
  for (const relative of RUNTIME_FILES) assert.equal(hash(fs.readFileSync(path.join(f.root,'.kairos/runtime',VERSION,relative))),hash(fs.readFileSync(path.join(PACKAGE_ROOT,relative))));
});

test('JSON settings, other MCPs and unrelated TOML bytes survive', t => {
  const f = fixture(t);
  const old = { mcpServers:{ other:{ command:'other-command' } }, extra:{ keep:true } };
  fs.writeFileSync(path.join(f.root,'.mcp.json'),JSON.stringify(old));
  fs.mkdirSync(path.join(f.root,'.codex'));
  const before = '# Preserve comments\nmodel = "existing-model"\n[mcp_servers.other]\ncommand = "other-command"\nargs = [\n  "kept", # keep comment\n]\n';
  fs.writeFileSync(path.join(f.root,'.codex/config.toml'),before);
  applyInstall(f.plan());
  const actual = JSON.parse(fs.readFileSync(path.join(f.root,'.mcp.json')));
  assert.deepEqual(actual.extra,old.extra); assert.deepEqual(actual.mcpServers.other,old.mcpServers.other);
  assert.ok(fs.readFileSync(path.join(f.root,'.codex/config.toml'),'utf8').startsWith(before));
});

test('entry conflict requires replace and preserves other client entries', t => {
  const f = fixture(t), existing = { mcpServers:{ kairos:{ command:'old' }, other:{ command:'keep' } } };
  fs.writeFileSync(path.join(f.root,'.mcp.json'),JSON.stringify(existing));
  assert.throws(() => f.plan(), /kairos_config_conflict/);
  assert.equal(fs.existsSync(path.join(f.root,'.kairos')),false);
  applyInstall(f.plan({ replace:true }));
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.root,'.mcp.json'))).mcpServers.other,existing.mcpServers.other);
});

test('TOML replace updates only the conventional Kairos table and preserves comments elsewhere', t => {
  const f = fixture(t); fs.mkdirSync(path.join(f.root,'.codex'));
  const before = '# outside\nmodel = "keep"\n[mcp_servers.kairos]\nurl="https://old.example/mcp"\n# inside replaced table\n[mcp_servers.other]\ncommand="keep"\n';
  fs.writeFileSync(path.join(f.root,'.codex/config.toml'),before);
  applyInstall(f.plan({ replace:true,clients:['codex'] }));
  const actual = fs.readFileSync(path.join(f.root,'.codex/config.toml'),'utf8');
  assert.ok(actual.startsWith('# outside\nmodel = "keep"\n[mcp_servers.other]\ncommand="keep"\n'));
  assert.equal(applyInstall(f.plan({ clients:['codex'] })).status,'unchanged');
  assert.throws(() => mergeTOML(Buffer.from('mcp_servers={kairos={command="old"}}\n'),{command:'new',args:[]},true), /unsupported_toml_layout/);
});

test('JSONC, duplicate keys and invalid TOML fail before any mutation', t => {
  const f = fixture(t);
  fs.writeFileSync(path.join(f.root,'opencode.jsonc'),'// original comments\n{}');
  assert.throws(() => f.plan(), /jsonc_manual_merge_required/);
  assert.deepEqual(fs.readdirSync(f.root),['opencode.jsonc']);
  assert.throws(() => objectJSON(Buffer.from('{"x":{},"x":{}}')), /duplicate_config_key/);
  for (const source of ['model = "unclosed\n','model = ???\n','model = 01\n','model = "a"\nmodel = "b"\n','[mcp_servers.other]\n[ mcp_servers.other ]\n']) {
    assert.throws(() => mergeTOML(Buffer.from(source),{command:'node',args:[]}), /toml/);
  }
});

test('OpenCode generation is explicit and existing layouts are preserved', t => {
  const f = fixture(t);
  assert.throws(() => f.plan({ clients:['opencode'],openCodeVersion:undefined }), /opencode_version_required/);
  applyInstall(f.plan({ clients:['opencode'],openCodeVersion:1 }));
  const data = JSON.parse(fs.readFileSync(path.join(f.root,'opencode.json')));
  assert.equal(data.mcp.kairos.enabled,true);
  f.plan({ clients:['opencode'],openCodeVersion:undefined });
  assert.throws(() => f.plan({ clients:['opencode'],openCodeVersion:2 }), /opencode_version_conflict/);
});

test('unsafe URLs, project IDs, traversal and in-project keys are rejected', t => {
  const f = fixture(t);
  for (const url of ['http://remote.example','https://name:password@example.com','https://example.com/?token=x','https://example.com/../x','https://example.com/%2e%2e/x','http://localhost:5173/mcp/']) assert.throws(() => f.plan({url}));
  assert.throws(() => f.plan({ project:'../foreign' }), /invalid_project_id/);
  assert.throws(() => checked(path.join(f.root,'a')+path.sep+'..'+path.sep+'outside'), /unsafe_path/);
  const key = path.join(f.root,'private.key');fs.writeFileSync(key,'synthetic-private-key');
  assert.throws(() => f.plan({ keyFile:key }), /key_must_be_outside_project/);
});

test('directory junctions and symlinks are rejected before writing external files', t => {
  const f = fixture(t), outside = path.join(f.base,'other'); fs.mkdirSync(outside);
  try { fs.symlinkSync(outside,path.join(f.root,'.codex'),process.platform==='win32'?'junction':'dir'); }
  catch (error) { if (error.code==='EPERM') { t.skip('Host denies fixture link creation');return; } throw error; }
  assert.throws(() => f.plan(),/linked_path/); assert.deepEqual(fs.readdirSync(outside),[]);
});

test('config changes after preview reject before target or runtime writes', t => {
  const f = fixture(t), plan = f.plan();
  fs.writeFileSync(path.join(f.root,'.mcp.json'),'{"changed":true}');
  assert.throws(() => applyInstall(plan), /config_changed_during_install/);
  assert.equal(fs.existsSync(path.join(f.root,'.kairos/runtime')),false);
});

test('partial writes retain journal and restore exact prior files without deleting foreign files', t => {
  const f = fixture(t), original=Buffer.from('{"keep":true}\n');fs.writeFileSync(path.join(f.root,'.mcp.json'),original);
  const plan=f.plan();
  assert.throws(() => applyInstall(plan,{writer(target,bytes){if(target===path.join(f.root,'.codex/config.toml'))throw new Error('synthetic failure');atomicWrite(target,bytes);}}),/partial_installation_recovery_required/);
  const foreign=path.join(f.root,'.kairos/foreign.txt');fs.writeFileSync(foreign,'keep');
  assert.equal(recover(f.root).status,'recovery_preview');
  assert.equal(recover(f.root,{apply:true}).status,'recovered');
  assert.deepEqual(fs.readFileSync(path.join(f.root,'.mcp.json')),original);
  assert.equal(fs.readFileSync(foreign,'utf8'),'keep');
  assert.equal(fs.existsSync(path.join(f.root,'.kairos/install.pending.json')),false);
  assert.equal(applyInstall(f.plan()).status,'installed');
});

test('recovery refuses changed targets and a tampered destination', t => {
  const f=fixture(t),plan=f.plan();
  assert.throws(() => applyInstall(plan,{writer(target,bytes){if(target===path.join(f.root,'.codex/config.toml'))throw Error();atomicWrite(target,bytes);}}));
  fs.writeFileSync(path.join(f.root,'.mcp.json'),'{"changed":true}');
  assert.throws(() => recover(f.root,{apply:true}),/recovery_conflict/);
  const pending=path.join(f.root,'.kairos/install.pending.json'),data=JSON.parse(fs.readFileSync(pending));data.records[0].path='../outside';fs.writeFileSync(pending,JSON.stringify(data));
  assert.throws(() => recover(f.root,{apply:true}),/invalid_recovery_destination/);
});

test('a partial binding change cannot leave other managed clients on the previous URL/key', t => {
  const f=fixture(t);applyInstall(f.plan());
  assert.throws(() => f.plan({clients:['claude'],url:'https://different.example',replace:true}),/installation_binding_conflict/);
  applyInstall(f.plan({url:'https://different.example',replace:true}));
  assert.equal(loadInstallation(f.root).data.url,'https://different.example');
});

test('the offline CLI previews by default, --yes applies, and reports no secrets', async t => {
  const f=fixture(t), out=stream(),err=stream();
  const argv=['install','--client','all','--root',f.root,'--url',f.options.url,'--project',f.options.project,'--key-file',f.keyFile,'--opencode-version','2'];
  assert.equal(await main(argv,{input:Readable.from([]),output:out.value,errors:err.value}),0);
  assert.equal(fs.existsSync(path.join(f.root,'.kairos')),false);
  assert.equal(await main([...argv,'--yes'],{input:Readable.from([]),output:out.value,errors:err.value}),0);
  assert.equal(fs.existsSync(path.join(f.root,'.mcp.json')),true);
  assert.equal(out.content.includes(fs.readFileSync(f.keyFile,'utf8')),false);assert.equal(err.content,'');
});

test('doctor online uses only initialize/list/projects and tolerates extra server tools', async t => {
  const f=fixture(t);applyInstall(f.plan());const calls=[];
  const transport={async request(m){calls.push(m.method);return null;},async call(id,method,params){calls.push(method);if(method==='initialize')return{serverInfo:{name:'fixture'}};if(method==='tools/list')return{tools:[...REQUIRED_TOOLS,'future_tool'].map(name=>({name}))};assert.equal(params.name,'projects');return{structuredContent:{projects:[{id:f.options.project}]}};}};
  const result=await doctor(f.root,{online:true,transport});assert.equal(result.status,'ready');assert.equal(result.project_authorized,true);
  assert.deepEqual(calls,['initialize','notifications/initialized','tools/list','tools/call']);
});

test('doctor reports an old read-only server and rejects unauthorized project results', async t => {
  const f=fixture(t);applyInstall(f.plan());
  const old={async request(){},async call(id,method){return method==='tools/list'?{tools:[{name:'search'}]}:{serverInfo:{}};}};
  const result=await doctor(f.root,{online:true,transport:old});assert.equal(result.status,'degraded');assert.ok(result.missing_tools.includes('remember'));
  const denied={async request(){},async call(id,method){return method==='tools/list'?{tools:[...REQUIRED_TOOLS].map(name=>({name}))}:method==='tools/call'?{structuredContent:{projects:[{id:'foreign'}]}}:{serverInfo:{}};}};
  await assert.rejects(doctor(f.root,{online:true,transport:denied}),/project_not_authorized/);
});
