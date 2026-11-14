import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { checked, projectRoot, privateKey, readBytes, sameBytes, hash, jsonBytes, atomicWrite, withLock } from './files.mjs';
import { CLIENT_PATHS, MANIFEST, VERSION, COMPATIBLE_VERSIONS, RUNTIME_FILES, baseURL, clientEntry, objectJSON, openCodeVersion, mergeJSON, mergeTOML } from './config.mjs';
import { fail } from './errors.mjs';
import { automationConfig, assertDispatcherStopped } from './lifecycle-config.mjs';
import { HOOK_PATHS, planHooks } from './hooks.mjs';

export const PACKAGE_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PENDING = '.kairos/install.pending.json';
const shaOrNull = value => value === null ? null : hash(value);
const runtimePath = name => `.kairos/runtime/${VERSION}/${name}`;
const managedLimit=name=>name.includes('lib/vendor/tree-sitter/')?3*1024*1024:undefined;
const allowed = name => typeof name === 'string' && ([...Object.values(CLIENT_PATHS), ...HOOK_PATHS, MANIFEST].includes(name) ||
  COMPATIBLE_VERSIONS.some(version => RUNTIME_FILES.some(file => name === `.kairos/runtime/${version}/${file}`)));

export function planInstall(options) {
  const root = projectRoot(options.root), url = baseURL(options.url);
  const project = options.project;
  if (typeof project !== 'string' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(project)) fail('invalid_project_id');
  const keyFile = privateKey(options.keyFile, root);
  const clients = [...new Set(options.clients)].sort();
  if (!clients.length || clients.some(name => !Object.hasOwn(CLIENT_PATHS, name))) fail('invalid_client');
  const previousBytes = readBytes(checked(path.join(root, MANIFEST), root));
  const previous = objectJSON(previousBytes);
  const previousClients = previous.clients ?? [];
  if (!Array.isArray(previousClients) || previousClients.some(name => !Object.hasOwn(CLIENT_PATHS, name))) fail('invalid_installation_manifest');
  if (Object.keys(previous).length && (previous.schema_version !== 2 || !COMPATIBLE_VERSIONS.includes(previous.runtime?.version))) fail('incompatible_installation_manifest');
  if (previous.runtime && previous.runtime.version !== VERSION &&
      (!options.replace || !previousClients.every(name => clients.includes(name)))) fail('installation_upgrade_requires_all_clients_and_replace');
  if(previous.runtime && previous.runtime.version!==VERSION) assertDispatcherStopped(root,previous);
  const selectedNode=options.nodeExecutable ?? process.execPath;
  if (typeof selectedNode!=='string'||!path.isAbsolute(selectedNode)||selectedNode.includes('\0')||selectedNode.split(/[\\/]/).includes('..')) fail('invalid_node_executable');
  // Resolve the explicitly selected executable once; version-manager junctions
  // are valid here, unlike data/config paths. Persist the physical executable.
  const node = checked(fs.realpathSync.native(selectedNode));
  if (!fs.statSync(node).isFile()) fail('invalid_node_executable');
  const codeAnalysis=options.codeAnalysis??previous.code_analysis??'off';
  if(!['off','on'].includes(codeAnalysis)) fail('invalid_code_analysis_option');
  const binding = { url, project_id: project, key_file: keyFile, node, code_analysis:codeAnalysis };
  const automation = automationConfig(root, binding, { ...(previous.automation ?? {}), ...(options.automation ?? {}) });
  if (Object.keys(previous).length && Object.entries(binding).some(([key, value]) => previous[key] !== value)) {
    if (!options.replace || !previousClients.every(name => clients.includes(name))) fail('installation_binding_conflict');
  }
  if (previous.automation && JSON.stringify(previous.automation) !== JSON.stringify(automation) &&
      (!options.replace || !previousClients.every(name => clients.includes(name)))) fail('automation_change_requires_all_clients_and_replace');
  const changes = [], versions = {};
  const sourceRoot = checked(options.packageRoot || PACKAGE_ROOT);
  const runtimeHashes = {};
  for (const name of RUNTIME_FILES) {
    const limit=managedLimit(name);
    const after = readBytes(checked(path.join(sourceRoot, name), sourceRoot),limit);
    if (!after) fail('incomplete_package');
    const relative = runtimePath(name), target = checked(path.join(root, relative), root), before = readBytes(target,limit);
    runtimeHashes[name] = hash(after);
    if (before && !sameBytes(before, after) && !options.replace) fail('managed_runtime_conflict');
    changes.push({ path: relative, before, after });
  }
  // Validate every client before any target file or directory is created.
  for (const client of clients) {
    if (client === 'opencode' && readBytes(checked(path.join(root, 'opencode.jsonc'), root)) !== null) fail('jsonc_manual_merge_required');
    const name = CLIENT_PATHS[client], before = readBytes(checked(path.join(root, name), root));
    const version = client === 'opencode' ? openCodeVersion(objectJSON(before), options.openCodeVersion) : undefined;
    if (version) versions.opencode = version;
    const entry = clientEntry(client, root, url, keyFile, version, node,codeAnalysis);
    const after = client === 'codex' ? mergeTOML(before, entry, options.replace) : mergeJSON(before, client, entry, options.replace, version);
    changes.push({ path: name, before, after });
  }
  const hooks = planHooks({ root, clients, automation, previous, bin: path.join(root,runtimePath('bin/kairos.mjs')),
    replace: options.replace, openCodeVersion: versions.opencode ?? previous.opencode_version, node });
  changes.push(...hooks.changes);
  const manifest = { schema_version: 2, product: 'Kairos', ...binding, automation, managed_hooks: hooks.managed,
    clients: [...new Set([...previousClients, ...clients])].sort(),
    opencode_version: versions.opencode ?? previous.opencode_version ?? null,
    runtime: { version: VERSION, files: runtimeHashes } };
  changes.push({ path: MANIFEST, before: previousBytes,
    after: previousBytes && JSON.stringify(previous) === JSON.stringify(manifest) ? previousBytes : jsonBytes(manifest) });
  for (const relative of ['.kairos', '.kairos/backups', PENDING, '.kairos/install.lock', '.kairos/.gitignore']) checked(path.join(root, relative), root);
  if (readBytes(path.join(root, PENDING))) fail('recovery_required');
  const ignore = readBytes(path.join(root, '.kairos/.gitignore'));
  if (ignore && ignore.toString('utf8').trim() !== '*') fail('private_state_ignore_conflict');
  return { root, manifest, changes };
}

export function preview(plan) {
  return { status: 'preview', clients: plan.manifest.clients, project_id: plan.manifest.project_id,code_analysis:plan.manifest.code_analysis,
    automation: { capture: plan.manifest.automation.capture, context: plan.manifest.automation.context, state_directory: plan.manifest.automation.state_directory },
    changes: plan.changes.map(change => ({ path: change.path,
      action: sameBytes(change.before, change.after) ? 'unchanged' : change.before === null ? 'create' : 'update' })) };
}

export function applyInstall(plan, { writer = atomicWrite } = {}) {
  const { root, changes } = plan;
  const active = changes.filter(change => !sameBytes(change.before, change.after));
  if (!active.length) return { status: 'unchanged', changed: [] };
  return withLock(root, () => {
    const pending = checked(path.join(root, PENDING), root);
    if (readBytes(pending)) fail('recovery_required');
    for (const change of changes) {
      if (!allowed(change.path) || !sameBytes(readBytes(checked(path.join(root, change.path), root),managedLimit(change.path)), change.before)) fail('config_changed_during_install');
    }
    const prior=objectJSON(changes.find(change=>change.path===MANIFEST)?.before??null);
    if(prior.runtime&&prior.runtime.version!==VERSION) assertDispatcherStopped(root,prior);
    const ignore = checked(path.join(root, '.kairos/.gitignore'), root);
    const ignoreBytes = readBytes(ignore);
    if (!ignoreBytes) atomicWrite(ignore, Buffer.from('*\n'));
    else if (ignoreBytes.toString('utf8').trim() !== '*') fail('private_state_ignore_conflict');
    const transaction = randomUUID().replaceAll('-', ''), records = [];
    for (const [index, change] of active.entries()) {
      const backup = `.kairos/backups/${transaction}/${index}.bak`;
      if (change.before !== null) atomicWrite(checked(path.join(root, backup), root), change.before);
      records.push({ path: change.path, before_sha256: shaOrNull(change.before), after_sha256: hash(change.after), backup });
    }
    atomicWrite(pending, jsonBytes({ schema_version: 2, transaction, records }));
    try {
      for (const change of active) writer(checked(path.join(root, change.path), root), change.after);
    } catch { fail('partial_installation_recovery_required'); }
    fs.unlinkSync(pending);
    return { status: 'installed', clients: plan.manifest.clients, project_id: plan.manifest.project_id,
      changed: active.map(change => change.path), backup_transaction: transaction };
  });
}

export function recover(rootValue, { apply = false, unlock = false, writer = atomicWrite } = {}) {
  const root = projectRoot(rootValue), pending = checked(path.join(root, PENDING), root);
  const raw = readBytes(pending);
  if (!raw) return { status: 'no_recovery_pending' };
  const record = objectJSON(raw);
  if (record.schema_version !== 2 || !/^[a-f0-9]{32}$/.test(record.transaction) ||
      !Array.isArray(record.records) || !record.records.length || record.records.length > 64) fail('invalid_recovery_journal');
  const seen = new Set();
  const restores = record.records.map((entry, index) => {
    if (!allowed(entry.path) || seen.has(entry.path)) fail('invalid_recovery_destination');
    seen.add(entry.path);
    if (!/^[a-f0-9]{64}$/.test(entry.after_sha256) || entry.before_sha256 !== null && !/^[a-f0-9]{64}$/.test(entry.before_sha256)) fail('invalid_recovery_hash');
    const expectedBackup = `.kairos/backups/${record.transaction}/${index}.bak`;
    if (entry.backup !== expectedBackup) fail('invalid_recovery_backup');
    const target = checked(path.join(root, entry.path), root), current = readBytes(target,managedLimit(entry.path));
    if (![entry.before_sha256, entry.after_sha256].includes(shaOrNull(current))) fail('recovery_conflict');
    const original = entry.before_sha256 === null ? null : readBytes(checked(path.join(root, expectedBackup), root),managedLimit(entry.path));
    if (shaOrNull(original) !== entry.before_sha256) fail('recovery_backup_mismatch');
    return { ...entry, target, original };
  });
  if (apply) withLock(root, () => {
    if (!sameBytes(readBytes(pending), raw)) fail('recovery_journal_changed');
    for (const restore of restores) if (![restore.before_sha256, restore.after_sha256].includes(shaOrNull(readBytes(restore.target,managedLimit(restore.path))))) fail('recovery_conflict');
    for (const restore of restores) {
      checked(restore.target, root);
      if (restore.original === null) { if (readBytes(restore.target,managedLimit(restore.path)) !== null) fs.unlinkSync(restore.target); }
      else writer(restore.target, restore.original);
    }
    fs.unlinkSync(pending);
  }, { unlock });
  return { status: apply ? 'recovered' : 'recovery_preview', paths: restores.map(entry => entry.path) };
}

export function loadInstallation(rootValue) {
  const root = projectRoot(rootValue), data = objectJSON(readBytes(checked(path.join(root, MANIFEST), root)));
  if (data.schema_version !== 2 || data.product !== 'Kairos' || !Array.isArray(data.clients) || !data.clients.length ||
      data.clients.some(name => !Object.hasOwn(CLIENT_PATHS, name)) || data.runtime?.version !== VERSION) fail('not_installed');
  const plan = planInstall({ root, clients: data.clients, url: data.url, project: data.project_id,
    keyFile: data.key_file, openCodeVersion: data.opencode_version, automation: data.automation, nodeExecutable: data.node });
  if (plan.changes.some(change => !sameBytes(change.before, change.after))) fail('configuration_drift');
  return { root, data };
}
