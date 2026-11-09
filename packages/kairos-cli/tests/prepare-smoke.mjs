// Produces only synthetic, package-owned fixtures for the real npx smoke check.
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { PACKAGE_ROOT } from '../lib/install.mjs';
import { checked } from '../lib/files.mjs';

const directory = checked(path.join(PACKAGE_ROOT, '.smoke', randomUUID()), PACKAGE_ROOT);
fs.mkdirSync(directory, { recursive: true });
const root = checked(path.join(directory, 'project'), PACKAGE_ROOT);
fs.mkdirSync(root);
const keyFile = checked(path.join(directory, 'private.key'), PACKAGE_ROOT);
fs.writeFileSync(keyFile, 'synthetic-kairos-npx-fixture-credential\n', { mode: 0o600 });
console.log(JSON.stringify({ directory, root, keyFile }));
