// Verify actual release bytes; never invent test or publication results.
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { PACKAGE_ROOT } from '../lib/install.mjs';
import { VERSION, RUNTIME_FILES } from '../lib/config.mjs';

export function verifyArtifact(archive,sourceRoot=PACKAGE_ROOT) {
  const bytes=fs.readFileSync(archive);if(bytes.length>16*1024*1024) throw Error('artifact_too_large');
  const tar=gunzipSync(bytes,{maxOutputLength:32*1024*1024}),allowed=new Set([...RUNTIME_FILES,'README.md','LICENSE']);
  const files=[],seen=new Set();let at=0;
  while(at+512<=tar.length) {
    const header=tar.subarray(at,at+512);if(header.every(value=>value===0)) break;
    const string=(start,end)=>header.subarray(start,end).toString('utf8').replace(/\0.*$/s,'');
    const name=string(0,100),prefix=string(345,500),full=prefix?prefix+'/'+name:name;
    const size=parseInt(string(124,136).trim(),8),checksum=parseInt(string(148,156).trim(),8);
    const sum=[...header].reduce((total,value,index)=>total+(index>=148&&index<156?32:value),0);
    if(checksum!==sum||!Number.isSafeInteger(size)||size<0||at+512+size>tar.length) throw Error('invalid_artifact_tar');
    if(!full.startsWith('package/')||full.includes('\\')||full.split('/').some(part=>part==='..'||part==='')) throw Error('unsafe_artifact_path');
    const relative=full.slice(8),type=header[156];
    if(![0,48].includes(type)||seen.has(relative)||!allowed.has(relative)) throw Error('unexpected_artifact_file');
    const content=tar.subarray(at+512,at+512+size),original=fs.readFileSync(path.join(sourceRoot,relative));
    if(!content.equals(original)) throw Error('artifact_source_mismatch');
    if(relative==='package.json') {const pkg=JSON.parse(content);if(pkg.name!=='@daycry/kairos'||pkg.version!==VERSION) throw Error('artifact_identity_mismatch');}
    seen.add(relative);files.push({path:relative,bytes:size,sha256:createHash('sha256').update(content).digest('hex')});
    at+=512+Math.ceil(size/512)*512;
  }
  if(seen.size!==allowed.size||[...allowed].some(file=>!seen.has(file))) throw Error('incomplete_artifact');
  return {product:'Kairos',package:'@daycry/kairos',version:VERSION,published:null,verification_scope:'local-artifact-source-equivalence',bytes:bytes.length,
    sha256:createHash('sha256').update(bytes).digest('hex'),integrity:'sha512-'+createHash('sha512').update(bytes).digest('base64'),files:files.sort((a,b)=>a.path.localeCompare(b.path)),
    tests:'not-run-by-this-verifier',registry:'not-checked',credentials_inspected:false};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href) {
  if(process.argv.length>3) throw Error('usage: node tests/artifact-report.mjs [archive]');
  const archive=process.argv[2]??path.join(PACKAGE_ROOT,'artifacts',`daycry-kairos-${VERSION}.tgz`);
  console.log(JSON.stringify(verifyArtifact(archive),null,2));
}
