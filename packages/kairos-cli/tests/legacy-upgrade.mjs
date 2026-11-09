import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const legacy=path.resolve(process.argv[2]||'missing-explicit-legacy-package');
const original=name=>import(pathToFileURL(path.join(legacy,'lib',name+'.mjs')).href);
const oldInstall=await original('install');
const {startDispatcher:oldStart}=await original('lifecycle');
const {lifecycleConfig:oldConfig}=await original('lifecycle-config');
const {Outbox:OldOutbox}=await original('outbox');
const {normalizeHook:oldNormalize}=await original('capture');
import {planInstall,applyInstall,loadInstallation} from '../lib/install.mjs';
import {ensureDispatcher} from '../lib/lifecycle.mjs';
import {lifecycleConfig} from '../lib/lifecycle-config.mjs';
import {Outbox} from '../lib/outbox.mjs';
import {VERSION} from '../lib/config.mjs';

const parent=fs.realpathSync.native(os.tmpdir()),base=path.join(parent,'kairos-original-upgrade-'+randomUUID());fs.mkdirSync(base);
const root=path.join(base,'project');fs.mkdirSync(root);
const keyFile=path.join(base,'synthetic.key');fs.writeFileSync(keyFile,'synthetic-private-fixture-key');
const options={root,keyFile,url:'http://127.0.0.1:1',project:'synthetic',clients:['claude','codex','opencode'],openCodeVersion:2,
  automation:{capture:'summary',context:'auto',state_directory:path.join(base,'state')}};
let handle,queue;
try{
  oldInstall.applyInstall(oldInstall.planInstall(options));
  const old=oldInstall.loadInstallation(root).data,configuration=oldConfig(root,old);
  assert.equal(old.runtime.version,'0.1.0');
  handle=await oldStart(configuration,{tickMs:60000,errors:{write(){}}});
  const before=fs.readFileSync(path.join(root,'.kairos/installation.json'));
  assert.throws(()=>planInstall({...options,replace:true}),/dispatcher_upgrade_requires_stop/);
  assert.deepEqual(fs.readFileSync(path.join(root,'.kairos/installation.json')),before);
  let launched=false;await assert.rejects(ensureDispatcher(root,old,{launcher(){launched=true;}}),/dispatcher_version_mismatch/);assert.equal(launched,false);
  await handle.close();handle=null;
  const oldQueue=new OldOutbox(configuration.directory,configuration.binding);
  const spec=oldNormalize('claude',{cwd:root,hook_event_name:'PostToolUse',session_id:'original',tool_name:'Bash',tool_use_id:'one'},
    {root,project:'synthetic',mode:'summary'});
  oldQueue.admit(spec);const event=oldQueue.pending()[0].event;oldQueue.close();
  applyInstall(planInstall({...options,replace:true}));
  const data=loadInstallation(root).data;assert.equal(data.runtime.version,VERSION);
  const current=lifecycleConfig(root,data);queue=new Outbox(current.directory,current.binding);
  assert.deepEqual(queue.pending()[0].event,event);queue.close();queue=null;
  console.log(JSON.stringify({artifact:'original-0.1.0',live_dispatcher_upgrade_rejected:true,manifest_preserved:true,legacy_endpoint_not_contacted:true,
    pending_event_exact_after_migration:true,current_version:VERSION,provider_calls:0,passed:true}));
}finally{
  await handle?.close();queue?.close();
  assert.equal(path.dirname(base),parent);assert.ok(path.basename(base).startsWith('kairos-original-upgrade-'));fs.rmSync(base,{recursive:true});
}
