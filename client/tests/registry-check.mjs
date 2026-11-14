// Anonymous public registry verification. No npm configuration or tokens read.
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { VERSION } from '../lib/config.mjs';
const args=process.argv.slice(2),version=args[0]??VERSION,archive=args[1];
if(args.length>2||!/^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$/.test(version)) throw Error('usage: node tests/registry-check.mjs [version] [local-archive]');
async function bytes(url,maximum) {
  const response=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(12000),headers:{Accept:'application/json'}});
  if(response.status===404) return null;if(!response.ok) throw Error('registry_http_error');
  const chunks=[];let count=0;for await(const chunk of response.body){count+=chunk.length;if(count>maximum)throw Error('registry_response_too_large');chunks.push(chunk);}return Buffer.concat(chunks);
}
try {
  const metadataBytes=await bytes(`https://registry.npmjs.org/@daycry%2Fkairos/${version}`,262144);
  if(!metadataBytes){console.log(JSON.stringify({package:'@daycry/kairos',version,published:false,registry_checked:true,ownership:'not-established',credentials_inspected:false}));process.exitCode=2;}
  else {
    const metadata=JSON.parse(metadataBytes),dist=metadata.dist,url=new URL(dist?.tarball);
    if(metadata.name!=='@daycry/kairos'||metadata.version!==version||url.protocol!=='https:'||url.host!=='registry.npmjs.org'||url.username||url.password||url.search||url.hash||!/^sha512-[A-Za-z0-9+/]+={0,2}$/.test(dist.integrity)) throw Error('registry_identity_mismatch');
    const tarball=await bytes(url,16*1024*1024);if(!tarball)throw Error('registry_tarball_missing');
    const integrity='sha512-'+createHash('sha512').update(tarball).digest('base64');if(integrity!==dist.integrity)throw Error('registry_integrity_mismatch');
    if(archive&&!tarball.equals(fs.readFileSync(archive)))throw Error('registry_local_artifact_mismatch');
    console.log(JSON.stringify({package:metadata.name,version,published:true,registry_checked:true,integrity,local_artifact_identical:archive?true:null,ownership:'not-established',credentials_inspected:false},null,2));
  }
}catch {console.error('kairos: registry_verification_unavailable_or_failed');process.exitCode=1;}
