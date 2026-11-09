import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { gzipSync } from 'node:zlib';
import { verifyArtifact } from './artifact-report.mjs';
import { PACKAGE_ROOT } from '../lib/install.mjs';
import { RUNTIME_FILES,VERSION } from '../lib/config.mjs';
function tar(files) {
  const chunks=[];for(const [name,value] of files){const bytes=Buffer.from(value),header=Buffer.alloc(512);header.write(name);header.write('0000644\0',100);header.write('0000000\0',108);header.write('0000000\0',116);header.write(bytes.length.toString(8).padStart(11,'0')+'\0',124);header.write('00000000000\0',136);header.fill(32,148,156);header[156]=48;header.write('ustar\0',257);header.write('00',263);const sum=[...header].reduce((a,b)=>a+b,0);header.write(sum.toString(8).padStart(6,'0')+'\0 ',148);chunks.push(header,bytes,Buffer.alloc((512-bytes.length%512)%512));}chunks.push(Buffer.alloc(1024));return gzipSync(Buffer.concat(chunks));
}
function fixture(t) {const parent=fs.realpathSync(os.tmpdir()),root=fs.mkdtempSync(path.join(parent,'kairos-artifact-test-'));t.after(()=>{assert.equal(path.dirname(fs.realpathSync(root)),parent);fs.rmSync(root,{recursive:true});});const archive=path.join(root,'fixture.tgz');return {archive,write:files=>fs.writeFileSync(archive,tar(files))};}
test('artifact verifier derives current version and exact source/grammar/license allowlist without inventing test results',t=>{
  const f=fixture(t);const files=[...new Set([...RUNTIME_FILES,'README.md','LICENSE'])].map(name=>['package/'+name,fs.readFileSync(path.join(PACKAGE_ROOT,name))]);f.write(files);const result=verifyArtifact(f.archive);assert.equal(result.version,VERSION);assert.equal(result.files.length,files.length);assert.equal(result.tests,'not-run-by-this-verifier');assert.equal(result.published,null);assert.match(result.integrity,/^sha512-/);assert.ok(result.files.some(file=>file.path.endsWith('tree-sitter-php.wasm')));
});
test('artifact verifier rejects traversal, duplicates, unexpected members and mismatched source bytes',t=>{
  const f=fixture(t);for(const files of [[['package/../outside','x']],[['package/.env','x']],[['package/LICENSE','tampered']],[['package/LICENSE',fs.readFileSync(path.join(PACKAGE_ROOT,'LICENSE'))],['package/LICENSE','x']]]){f.write(files);assert.throws(()=>verifyArtifact(f.archive));}
});
