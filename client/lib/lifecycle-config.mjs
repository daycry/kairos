import os from 'node:os';
import path from 'node:path';
import { checked, within, readBytes, text } from './files.mjs';
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
