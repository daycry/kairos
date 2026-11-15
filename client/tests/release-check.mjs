// Preparation only: never calls npm publish or modifies native clients.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { PACKAGE_ROOT } from '../lib/install.mjs';
import { verifyArtifact } from './artifact-report.mjs';
import { packageManager } from './package-manager.mjs';
const parent=fs.realpathSync(os.tmpdir()),directory=fs.mkdtempSync(path.join(parent,'kairos-release-check-'));
function run(command,args) {
  const result=spawnSync(command,args,{cwd:PACKAGE_ROOT,encoding:'utf8',timeout:360000,env:{...process.env,npm_config_cache:path.join(directory,'cache'),npm_config_ignore_scripts:'true'}});
  if(result.status!==0) throw Error('release_gate_failed:'+path.basename(command));return result.stdout;
}
try {
  run(process.execPath,['tests/run.mjs']);
  run(process.execPath,['tests/npx-smoke.mjs']);
  const npm=packageManager('npm',['pack','--ignore-scripts','--offline','--json','--pack-destination',directory]);
  const result=JSON.parse(run(npm.command,npm.args));
  const report=verifyArtifact(path.join(directory,result[0].filename));
  console.log(JSON.stringify({...report,tests:'passed',fresh_cache_offline_npx:'passed',publication:'not-attempted'},null,2));
} finally {
  const target=fs.realpathSync(directory);if(path.dirname(target)!==parent||!path.basename(target).startsWith('kairos-release-check-')) throw Error('unsafe_fixture_cleanup');
  fs.rmSync(target,{recursive:true});
}
