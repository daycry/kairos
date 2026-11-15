// Real offline npx installation in an owned synthetic environment. No server,
// native client configuration, real credential or provider is contacted.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { PACKAGE_ROOT } from '../lib/install.mjs';
import { VERSION } from '../lib/config.mjs';
import { packageManager } from './package-manager.mjs';

const parent = fs.realpathSync(os.tmpdir());
const temporary = fs.mkdtempSync(path.join(parent, 'kairos-npx-test-'));
function run(command, args) {
  if(['npm','npx'].includes(command)) ({command,args}=packageManager(command,args));
  const result = spawnSync(command, args, { cwd: PACKAGE_ROOT, encoding: 'utf8', timeout: 60_000,
    env: { ...process.env, npm_config_cache: path.join(temporary, 'cache'), npm_config_offline: 'true', npm_config_ignore_scripts: 'true' } });
  assert.equal(result.status, 0, `${command} failed in the owned synthetic fixture: ${result.error?.code??result.stderr}`);
  return result.stdout;
}
try {
  const project = path.join(temporary, 'project'); fs.mkdirSync(project);
  const artifacts = path.join(temporary, 'artifacts'); fs.mkdirSync(artifacts);
  const key = path.join(temporary, 'fixture.key'); fs.writeFileSync(key, 'synthetic-test-only-no-real-credential', { mode: 0o600 });
  const packaged = JSON.parse(run('npm', ['pack', '--ignore-scripts', '--json', '--pack-destination', artifacts]));
  const tarball = path.join(artifacts, packaged[0].filename);
  const npx = ['--offline', '--yes', '--package', tarball, 'kairos'];
  assert.equal(run('npx', [...npx, '--version']).trim(),VERSION);
  const install = [...npx, 'install', '--client', 'all', '--root', project, '--url', 'http://127.0.0.1:5173',
    '--project', 'synthetic-project', '--key-file', key, '--opencode-version', '2'];
  run('npx', [...install, '--dry-run']);
  assert.deepEqual(fs.readdirSync(project), []);
  run('npx', [...install, '--yes']);
  for (const name of ['.mcp.json', '.codex/config.toml', 'opencode.json']) {
    const value = fs.readFileSync(path.join(project, name), 'utf8');
    assert.match(value, /kairos/); assert.ok(!value.includes('synthetic-test-only-no-real-credential'));
  }
  const runtime = path.join(project, '.kairos/runtime',VERSION,'bin/kairos.mjs');
  assert.equal(run(process.execPath, [runtime, '--version']).trim(),VERSION);
  run(process.execPath, [runtime, 'doctor', '--root', project]);
  const before = fs.readFileSync(path.join(project, '.mcp.json'));
  run('npx', [...install, '--yes']);
  assert.deepEqual(fs.readFileSync(path.join(project, '.mcp.json')), before);
  const automatic = [...install, '--capture', 'summary', '--context', 'auto', '--state-dir', path.join(temporary,'private-state'), '--replace'];
  run('npx',[...automatic,'--dry-run']); assert.ok(!fs.existsSync(path.join(project,'.codex/hooks.json')));
  run('npx',[...automatic,'--yes']); run(process.execPath,[runtime,'doctor','--root',project]);
  assert.ok(fs.existsSync(path.join(project,'.codex/hooks.json')));
  assert.ok(fs.existsSync(path.join(project,'.opencode/plugins/kairos-memory/index.js')));
  run('npx',[...automatic,'--yes']);
  console.log('KAIROS_NPX_RESULT '+JSON.stringify({ package: '@daycry/kairos', offline: true, clients: 3,
    dryRun: true, stableRuntime: true, idempotentInstall: true, optionalHooks: true, realCredentials: false, passed: true }));
} finally {
  const absolute = fs.realpathSync(temporary);
  assert.equal(path.dirname(absolute), parent);
  assert.ok(path.basename(absolute).startsWith('kairos-npx-test-'));
  fs.rmSync(absolute, { recursive: true });
}
