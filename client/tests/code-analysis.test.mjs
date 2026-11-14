import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { selectedFiles,localCodeCall,withLocalCode,CODE_TOOLS,CODE_LIMITS } from '../lib/code-analysis.mjs';
import { applyInstall,planInstall,loadInstallation } from '../lib/install.mjs';
import { VERSION } from '../lib/config.mjs';
import { pathToFileURL } from 'node:url';
function fixture(t) {
  const parent=fs.realpathSync.native(os.tmpdir()),base=path.join(parent,'kairos-code-'+randomUUID()),root=path.join(base,'project');fs.mkdirSync(root,{recursive:true});
  const key=path.join(base,'test.key');fs.writeFileSync(key,'synthetic-kairos-code-analysis-test-key');
  t.after(()=>{const target=fs.realpathSync.native(base);assert.equal(path.dirname(target),parent);assert.ok(path.basename(target).startsWith('kairos-code-'));fs.rmSync(target,{recursive:true});});
  const write=(name,content)=>{fs.mkdirSync(path.dirname(path.join(root,name)),{recursive:true});fs.writeFileSync(path.join(root,name),content);};
  return {root,key,base,write};
}
test('explicit selection rejects exclusions and traversal before any source read',t=>{
  const f=fixture(t);for(const name of ['../other.js','.env.js','.git/file.js','node_modules/thing.js','vendor/a.php','dist/a.js','/absolute.js','C:/absolute.js','src\\a.js','src//a.js','secrets/a.py','file.txt']) assert.throws(()=>selectedFiles(f.root,[name]));
  assert.throws(()=>selectedFiles(f.root,['ok.js','ok.js']));assert.throws(()=>selectedFiles(f.root,[]));assert.throws(()=>selectedFiles(f.root,Array(33).fill('a.js')));
  assert.deepEqual(fs.readdirSync(f.root),[]);
});
test('file and parent symlinks or junctions cannot escape the bound root',t=>{
  const f=fixture(t);const outside=path.join(f.base,'outside');fs.mkdirSync(outside);fs.writeFileSync(path.join(outside,'a.js'),'function outside(){}');
  try {fs.symlinkSync(outside,path.join(f.root,'linked'),process.platform==='win32'?'junction':'dir');}catch(error){if(['EPERM','EACCES'].includes(error.code)){t.skip('OS does not permit creating fixture links');return;}throw error;}
  assert.throws(()=>selectedFiles(f.root,['linked/a.js']),/linked_path/);
});
test('nested independently configured projects are excluded before source reads while root markers are allowed',t=>{
  const f=fixture(t);f.write('.git','root marker');f.write('src/a.js','function allowed() {}');assert.equal(selectedFiles(f.root,['src/a.js']).length,1);
  f.write('nested/.git','nested marker');f.write('nested/a.js','function denied() {}');assert.throws(()=>selectedFiles(f.root,['nested/a.js']),/code_nested_project_excluded/);
  f.write('another/.kairos/installation.json','not parsed');f.write('another/src/a.py','def denied(): pass');assert.throws(()=>selectedFiles(f.root,['another/src/a.py']),/code_nested_project_excluded/);
});
test('structural outline supports JS TS Python PHP and labels actual parser limitations',async t=>{
  const f=fixture(t);f.write('a.js','// function bogus(){}\nexport function alpha() { return 1; }');f.write('b.ts','interface Beta { value: string; }\nfunction typed(x: string): string { return x; }');f.write('c.py','class Gamma:\n    def run(self):\n        return 1\n');f.write('d.php','<?php\nclass Delta { public function run() { return 1; } }');
  const result=await localCodeCall(f.root,'code_outline',{paths:['a.js','b.ts','c.py','d.php']});
  assert.equal(result.results.length,4);assert.ok(result.results[0].symbols.some(symbol=>symbol.name==='alpha'));assert.equal(JSON.stringify(result).includes('bogus'),false);
  assert.ok(result.results[1].symbols.some(symbol=>symbol.name==='Beta'));assert.ok(result.results[2].symbols.some(symbol=>symbol.name==='Gamma'));assert.ok(result.results[3].symbols.some(symbol=>symbol.name==='Delta'));
  for(const file of result.results){assert.match(file.sha256,/^[a-f0-9]{64}$/);assert.equal(file.parser,'tree-sitter-wasm');assert.equal(typeof file.syntax_errors,'boolean');}
});
test('unfold preserves Unicode and redacts credentials/private text without persistence',async t=>{
  const f=fixture(t);f.write('a.js','function saludo() {\nconst texto = "á, é, ñ 🌍";\nconst api_key = "synthetic-credential-sensitive";\n// <private>private fixture words</private>\n}\n');
  const result=await localCodeCall(f.root,'code_unfold',{path:'a.js',start_line:1,end_line:5});const value=JSON.stringify(result);assert.ok(value.includes('á, é, ñ 🌍'));assert.ok(value.includes('[REDACTED]'));assert.equal(value.includes('synthetic-credential-sensitive'),false);assert.equal(value.includes('private fixture words'),false);assert.deepEqual(fs.readdirSync(f.root),['a.js']);
});
test('literal search handles punctuation and returns source hash without executing code',async t=>{
  const f=fixture(t);f.write('a.js','function alpha() { return "alpha(x)"; }\nthrow new Error("MUST NOT EXECUTE");');
  const result=await localCodeCall(f.root,'code_smart_search',{paths:['a.js'],query:'alpha(x)'});assert.equal(result.results[0].matches.length,1);assert.equal(result.results[0].matches[0].line,1);
});
test('symbol unfolding uses actual AST names, rejects ambiguity and marks bounded continuation',async t=>{
  const f=fixture(t);f.write('a.ts','// function fake() {}\nconst text = "function fakeToo() {}";\nclass Actual { run(): number { return 1; } }\nfunction large() {\n'+Array(90).fill('  const a = 1;').join('\n')+'\n}\n');
  const outline=await localCodeCall(f.root,'code_outline',{paths:['a.ts']});assert.deepEqual(outline.results[0].symbols.map(symbol=>symbol.name),['Actual','run','large']);
  const small=await localCodeCall(f.root,'code_unfold',{path:'a.ts',symbol_name:'run'});assert.equal(small.results[0].partial,false);assert.ok(small.results[0].text.includes('return 1'));
  const large=await localCodeCall(f.root,'code_unfold',{path:'a.ts',symbol_name:'large'});assert.equal(large.results[0].partial,true);assert.equal(large.results[0].end_line-large.results[0].start_line+1,80);assert.equal(large.results[0].next_start_line,large.results[0].end_line+1);
  await assert.rejects(localCodeCall(f.root,'code_unfold',{path:'a.ts',symbol_name:'fake'}),/code_symbol_not_found/);
  f.write('duplicate.js','class A { run() {} }\nclass B { run() {} }');await assert.rejects(localCodeCall(f.root,'code_unfold',{path:'duplicate.js',symbol_name:'run'}),/code_symbol_ambiguous/);
  await assert.rejects(localCodeCall(f.root,'code_unfold',{path:'a.ts',symbol_name:'run',start_line:1,end_line:3}),/invalid_code_symbol/);
});
test('binary, invalid UTF-8, missing files, per-file and aggregate budgets fail closed',async t=>{
  const f=fixture(t);f.write('binary.js',Buffer.from([0,1]));f.write('utf.js',Buffer.from([255]));f.write('large.js','a'.repeat(CODE_LIMITS.fileBytes+1));
  await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['binary.js']}),/code_binary_file/);await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['utf.js']}),/invalid_utf8/);await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['large.js']}));await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['missing.js']}));
  const paths=[];for(let i=0;i<9;i++){paths.push(`${i}.js`);f.write(`${i}.js`,' '.repeat(CODE_LIMITS.fileBytes));}
  await assert.rejects(localCodeCall(f.root,'code_outline',{paths}),/code_byte_limit/);
});
test('unknown properties, invalid query, line bounds and hard worker deadline are enforced',async t=>{
  const f=fixture(t);f.write('a.js','function sample() {}');
  await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['a.js'],command:'whoami'}),/invalid_code_arguments/);
  await assert.rejects(localCodeCall(f.root,'code_smart_search',{paths:['a.js'],query:''}),/invalid_code_query/);
  await assert.rejects(localCodeCall(f.root,'code_unfold',{path:'a.js',start_line:1,end_line:81}),/code_line_limit/);
  await assert.rejects(localCodeCall(f.root,'code_outline',{paths:['a.js']},{timeout:1}),/code_analysis_timeout/);
});
test('opt-in proxy advertises local tools and never forwards their source or arguments',async t=>{
  const f=fixture(t);f.write('a.js','function localOnly(){}');const messages=[];const transport={async request(message){messages.push(message);return {jsonrpc:'2.0',id:message.id,result:{tools:[{name:'projects'}]}};}};
  const proxy=withLocalCode(transport,f.root),listed=await proxy.request({id:1,method:'tools/list'});assert.deepEqual(listed.result.tools.map(tool=>tool.name),['projects',...CODE_TOOLS.map(tool=>tool.name)]);
  const result=await proxy.request({id:2,method:'tools/call',params:{name:'code_outline',arguments:{paths:['a.js']}}});assert.ok(result.result.structuredContent);assert.equal(messages.length,1);
});
test('installer opt-in is explicit, stable, preserves unrelated MCP and requires all-client replacement to change',t=>{
  const f=fixture(t);f.write('.mcp.json',JSON.stringify({mcpServers:{other:{command:'preserved'}}}));
  const options={root:f.root,url:'http://127.0.0.1:5173',project:'synthetic',keyFile:f.key,clients:['claude']};
  applyInstall(planInstall(options));let config=JSON.parse(fs.readFileSync(path.join(f.root,'.mcp.json')));assert.equal(config.mcpServers.kairos.args.includes('--code-analysis'),false);
  assert.throws(()=>planInstall({...options,codeAnalysis:'on'}),/installation_binding_conflict/);
  applyInstall(planInstall({...options,codeAnalysis:'on',replace:true}));config=JSON.parse(fs.readFileSync(path.join(f.root,'.mcp.json')));
  assert.equal(config.mcpServers.other.command,'preserved');assert.ok(config.mcpServers.kairos.args.includes('--code-analysis'));assert.ok(config.mcpServers.kairos.args.includes(f.root));
  const {data}=loadInstallation(f.root);assert.equal(data.code_analysis,'on');assert.equal(data.runtime.version,VERSION);assert.ok(data.runtime.files['lib/code-analysis.mjs']);
});
test('installed stable runtime parses real TSX and Python independently of source and npx node_modules',async t=>{
  const f=fixture(t);f.write('example.tsx','export const Greet = () => <div>Hola</div>;');f.write('example.py','def alpha():\n    return 2\n');
  applyInstall(planInstall({root:f.root,url:'http://127.0.0.1:5173',project:'synthetic',keyFile:f.key,clients:['claude'],codeAnalysis:'on'}));
  const runtime=path.join(f.root,'.kairos','runtime',VERSION,'lib','code-analysis.mjs'),installed=await import(pathToFileURL(runtime));
  const result=await installed.localCodeCall(f.root,'code_outline',{paths:['example.tsx','example.py']});
  assert.equal(result.results[0].parser,'tree-sitter-wasm');assert.equal(result.results[0].syntax_errors,false);assert.ok(result.results[0].symbols.some(symbol=>symbol.name==='Greet'));assert.ok(result.results[1].symbols.some(symbol=>symbol.name==='alpha'));
});
