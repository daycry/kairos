import os from 'node:os';
import path from 'node:path';
import { checked, within, readBytes, text, atomicWrite, jsonBytes } from './files.mjs';
import { digest } from './capture.mjs';
import { fail } from './errors.mjs';

export function automationConfig(root, binding, options = {}) {
  const capture = options.capture ?? 'off', context = options.context ?? 'off';
  if (!['off','summary','full'].includes(capture) || !['off','auto'].includes(context)) fail('invalid_automation_options');
  const identity = digest({ root, url: binding.url, project_id: binding.project_id, key_file: binding.key_file });
  const base = options.state_directory ?? path.join(process.platform === 'win32' ? process.env.LOCALAPPDATA || os.homedir() : path.join(os.homedir(), '.local', 'state'), 'Kairos', 'memory');
  const directory = checked(base);
  if (within(root, directory) || within(directory, root)) fail('capture_state_must_be_outside_project');
  // The selected base cannot be an ancestor of the project. Each binding gets
  // its own queue: moving projects or switching accounts never mixes delivery.
  return { capture, context, state_directory: directory, binding: identity };
}

export function lifecycleConfig(root, data) {
  const automation = automationConfig(root, data, data.automation);
  return { root, url: data.url, key_file: data.key_file, project_id: data.project_id, ...automation,
    directory: checked(path.join(automation.state_directory, automation.binding)) };
}

export function assertDispatcherStopped(root,data) {
  if(!data?.automation) return;
  const config=lifecycleConfig(root,data);
  for(const name of ['endpoint.json','queue.lock','queue.recovery.lock']) {
    const raw=readBytes(checked(path.join(config.directory,name),config.directory),8192);
    if(!raw) continue;
    let owner; try { owner=JSON.parse(text(raw)); } catch { fail('invalid_capture_lock'); }
    if(!Number.isSafeInteger(owner.pid)||owner.pid<1) fail('invalid_capture_lock');
    try { process.kill(owner.pid,0); } catch(error) { if(error.code==='ESRCH') continue; throw error; }
    fail('dispatcher_upgrade_requires_stop');
  }
}

// What `kairos doctor --online` learnt of the key the last time `/v1/auth/me` accepted it (CA-08, DC-7): `credential.json` in the state directory of this binding, with
// `key_id`, `prefix`, `expires_at` and `checked_at`, never the key. The record is only worth something for the key whose first ten characters are `prefix` (the prefix the
// server keeps and lists): another key file, or the same file with another key in it, does not inherit the expiry of the previous one.
export const CREDENTIAL_PREFIX_LENGTH = 10;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const validTime = value => typeof value === 'string' && ISO.test(value) && Number.isFinite(Date.parse(value));

export function credentialFile(root, data) {
  const directory = lifecycleConfig(root, data).directory;
  return checked(path.join(directory, 'credential.json'), directory);
}

export function readCredential(file, key) {
  const raw = readBytes(file, 8192);
  if (!raw) return null;
  let record; try { record = JSON.parse(text(raw)); } catch { return null; }  // a damaged record is no record: the next online check writes it again
  if (!record || typeof record !== 'object' || typeof record.key_id !== 'string' || typeof record.prefix !== 'string' || !validTime(record.checked_at) ||
      !(record.expires_at === null || validTime(record.expires_at))) return null;
  return record.prefix === key.slice(0, CREDENTIAL_PREFIX_LENGTH) ? { key_id: record.key_id, prefix: record.prefix, expires_at: record.expires_at, checked_at: record.checked_at } : null;
}

export function writeCredential(file, key, seen, checkedAt) {
  // `seen` is the `key` object of `/v1/auth/me`; it is kept only when it describes this key (its prefix), and only its four fields
  if (!seen || typeof seen.id !== 'string' || !seen.id || seen.id.length > 200 || seen.prefix !== key.slice(0, CREDENTIAL_PREFIX_LENGTH) ||
      !(seen.expires_at === null || validTime(seen.expires_at))) return null;
  const record = { key_id: seen.id, prefix: seen.prefix, expires_at: seen.expires_at, checked_at: checkedAt };
  atomicWrite(file, jsonBytes(record));
  return record;
}
