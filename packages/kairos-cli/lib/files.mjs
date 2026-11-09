import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { randomUUID, createHash } from 'node:crypto';
import { fail } from './errors.mjs';

export const MAX_FILE = 1024 * 1024;
export const hash = value => createHash('sha256').update(value).digest('hex');
export const jsonBytes = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
export const sameBytes = (a, b) => a === null || b === null ? a === b : a.equals(b);
export const within = (root, target) => {
  const relative = path.relative(root, target);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
};

export function checked(value, root) {
  if (typeof value !== 'string' || !value || value.includes('\0') || value.split(/[\\/]/).includes('..')) fail('unsafe_path');
  const expanded = value === '~' ? os.homedir() : value.startsWith('~/') || value.startsWith('~\\') ? path.join(os.homedir(), value.slice(2)) : value;
  const target = path.resolve(expanded);
  for (let part = target; ; part = path.dirname(part)) {
    try {
      const info = fs.lstatSync(part);
      if (info.isSymbolicLink()) fail('linked_path'); // includes Windows junctions
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (part === path.dirname(part)) break;
  }
  if (root && !within(root, target)) fail('path_outside_project');
  return target;
}

export function projectRoot(value = '.') {
  const target = checked(value);
  if (!fs.statSync(target).isDirectory()) fail('invalid_project_root');
  return fs.realpathSync.native(target);
}

export function readBytes(value, limit = MAX_FILE) {
  const target = checked(value);
  let fd;
  try {
    fd = fs.openSync(target, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
    const info = fs.fstatSync(fd);
    if (!info.isFile() || info.size > limit) fail('invalid_regular_file');
    const buffer = Buffer.alloc(limit + 1);
    let count = 0;
    while (count < buffer.length) {
      const size = fs.readSync(fd, buffer, count, buffer.length - count, null);
      if (!size) break;
      count += size;
    }
    if (count > limit) fail('file_too_large');
    return buffer.subarray(0, count);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  } finally { if (fd !== undefined) fs.closeSync(fd); }
}

export function text(bytes) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes).replace(/^\uFEFF/, ''); }
  catch { fail('invalid_utf8'); }
}

export function privateKey(value, root) {
  const target = checked(value);
  if (root && within(root, target)) fail('key_must_be_outside_project');
  const info = fs.statSync(target);
  if (!info.isFile() || info.size < 1 || info.size > 8192) fail('invalid_key_file');
  return target;
}

export function readKey(value) {
  const bytes = readBytes(checked(value), 8192);
  if (!bytes) fail('invalid_key_file');
  const key = text(bytes).trim();
  if (!/^[\x21-\x7e]{16,4096}$/.test(key)) fail('invalid_key_file');
  return key;
}

export function atomicWrite(value, content) {
  const target = checked(value);
  checked(path.dirname(target));
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: process.platform === 'win32' ? 0o777 : 0o700 });
  checked(target);
  const temporary = path.join(path.dirname(target), '.kairos-' + randomUUID());
  let fd;
  try {
    fd = fs.openSync(temporary, 'wx', 0o600);
    fs.writeFileSync(fd, content);
    fs.fsyncSync(fd);
    fs.closeSync(fd); fd = undefined;
    checked(target);
    fs.renameSync(temporary, target);
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

export function withLock(root, operation, { unlock = false } = {}) {
  const directory = checked(path.join(root, '.kairos'), root);
  fs.mkdirSync(directory, { recursive: true, mode: process.platform === 'win32' ? 0o777 : 0o700 });
  const target = checked(path.join(directory, 'install.lock'), root);
  if (unlock) {
    const old = readBytes(target, 8192);
    if (old) {
      let record;
      try { record = JSON.parse(text(old)); } catch { fail('invalid_installation_lock'); }
      if (!Number.isSafeInteger(record.pid) || record.pid < 1 || typeof record.nonce !== 'string') fail('invalid_installation_lock');
      let alive = true;
      try { process.kill(record.pid, 0); } catch (error) { if (error.code === 'ESRCH') alive = false; }
      if (alive) fail('installation_busy');
      if (!sameBytes(readBytes(target, 8192), old)) fail('installation_lock_changed');
      fs.unlinkSync(target); // explicit stale-lock recovery; never an active owner's lock
    }
  }
  const own = jsonBytes({ pid: process.pid, nonce: randomUUID() });
  let fd;
  try { fd = fs.openSync(target, 'wx', 0o600); }
  catch (error) { if (error.code === 'EEXIST') fail('installation_busy'); throw error; }
  try {
    fs.writeFileSync(fd, own); fs.fsyncSync(fd);
    return operation();
  } finally {
    fs.closeSync(fd);
    if (sameBytes(readBytes(target, 8192), own)) fs.unlinkSync(target);
  }
}
