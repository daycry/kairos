// Execute from the read-only /candidate mount in a disposable networkless container.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
const parent=fs.realpathSync(os.tmpdir()),target=fs.mkdtempSync(path.join(parent,'kairos-cli-release-'));
try {
  for(const name of ['bin','lib','tests','package.json','README.md','LICENSE']) fs.cpSync('/candidate/'+name,path.join(target,name),{recursive:true});
  const result=spawnSync(process.execPath,['tests/release-check.mjs'],{cwd:target,encoding:'utf8',timeout:600000});
  if(result.stdout) process.stdout.write(result.stdout);if(result.stderr)process.stderr.write(result.stderr);
  if(result.error)console.error(result.error.code);process.exitCode=result.status??1;
}finally {
  const absolute=fs.realpathSync(target);if(path.dirname(absolute)!==parent||!path.basename(absolute).startsWith('kairos-cli-release-'))throw Error('unsafe_fixture_cleanup');fs.rmSync(absolute,{recursive:true});
}
