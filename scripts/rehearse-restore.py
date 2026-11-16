#!/usr/bin/env python3
"""Rehearsal of the restore runbook of docs/operations.md (C-01, CA-07), in an isolated project that is removed at the end.

It follows the runbook step by step with a SIMULATED destination (a directory):

  1. deploy      an isolated project `kairos-ops-*` (scripts/deploy-memory.py --fresh --embed-stub --roundtrip): own volumes, networks, images, ports and secrets
  2. keys        an `age` key pair generated here, in a throw-away container with no network: the PUBLIC key becomes the recipients file of the service
  3. cycle       the service `memory-backup` (its own definition: only the database secret and the public recipients) runs one `backup-cycle` into the destination
  4. download    the copy and its manifest are taken from the destination directory
  5. verify      the sha256 of the downloaded ciphertext against its manifest (`verify-backup`, no key needed)
  6. decrypt     with the private key, in a throw-away container with no network that is NOT a container of the project's services
  7. content     the decrypted dump against the `content_sha256` of the manifest (`verify-backup --manifest`)
  8. restore     `restore-check --from-manifest` into an empty `memory_restore_*` database of the isolated project: the tables must equal the manifest

and ends with `restored_and_content_verified`. The private key exists only in step 2 to 6 inside a temporary directory, is mounted only in the two throw-away containers
that generate and use it (never in a container of the project: `compose run`/`exec` commands never name its directory) and is overwritten and deleted at the end, with
the isolated project, its images, its secrets and its private files, whatever the result. Nothing touches `knowledge-graphs-*` or the Ollama of the host.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT = re.compile(r'kairos-ops-[a-z0-9][a-z0-9-]{0,24}')
DEFAULT_API_PORT, DEFAULT_WEB_PORT = 28792, 25175
IMAGES = ('postgres', 'api', 'worker', 'web', 'operator', 'mcp')
PRIVATE_FILES = ('memory-platform.env', 'compose.override.yml', 'deployment-status.json', 'deployment-status.tmp')
DEPLOY_TIMEOUT, STEP_TIMEOUT = 3600, 1800
COPY_NAME = re.compile(r'kairos-[a-z][a-z0-9]*-\d{8}T\d{6}(?:\d{6})?Z\.dump\.age')


class RehearsalError(Exception):
    pass


class Rehearsal:
    def __init__(self, args, root=ROOT, run=None):
        if not PROJECT.fullmatch(args.project_name or ''):
            raise RehearsalError('--project-name must be kairos-ops-<name> (lower case letters, digits and hyphens): a rehearsal never runs in any other project')
        if not args.embed_stub:
            raise RehearsalError('--embed-stub is required: the rehearsal never uses the Ollama of the host')
        self.args, self.root, self.project = args, Path(root), args.project_name
        self.run_command = run or self.subprocess_run
        self.work = None
        self.private = self.root / '.private' / ('rehearsal-' + self.project)
        self.steps, self.report, self.names = [], {}, []

    # -- commands ---------------------------------------------------------------------------------------------------------------

    def subprocess_run(self, command, timeout=STEP_TIMEOUT, environment=None):
        try:
            result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, env=environment)
        except (OSError, subprocess.TimeoutExpired):
            raise RehearsalError('A command could not run or timed out') from None
        return result.returncode, result.stdout, result.stderr

    def run(self, command, timeout=STEP_TIMEOUT, environment=None, check=True):
        code, out, err = self.run_command(command, timeout=timeout, environment=environment)
        if check and code:
            raise RehearsalError(f'Step {self.steps[-1] if self.steps else "-"} failed: {" ".join(str(c) for c in command[:3])} exited {code}: {(err or out).strip()[-600:]}')
        return out

    def step(self, name):
        self.steps.append(name)
        print(f'Kairos rehearsal: {name}', flush=True)

    def json(self, text):
        try:
            return json.loads(text)
        except ValueError:
            raise RehearsalError(f'Step {self.steps[-1]} returned no JSON') from None

    def image(self, name='operator'):
        return f'rehearsal-{self.project}-{name}:latest'

    def container(self, label):
        name = f'{self.project}-{label}-{uuid.uuid4().hex[:8]}'
        self.names.append(name)
        return name

    def compose(self):
        """The compose command of the isolated project: its own env file and override (written by the deployment), the `backup` profile included."""
        return ['docker', 'compose', '-p', self.project, '--project-directory', str(self.root), '--env-file', str(self.private / 'memory-platform.env'),
                '-f', str(self.root / 'docker-compose.yml'), '-f', str(self.private / 'compose.override.yml'), '--profile', 'memory', '--profile', 'memory-admin', '--profile', 'backup']

    def compose_environment(self):
        clean = {k: v for k, v in os.environ.items() if not k.upper().startswith(('MEMORY_', 'COMPOSE_', 'KAIROS'))}
        return dict(clean, MEMORY_BACKUP_DESTINATION='dir:/offsite', MEMORY_BACKUP_CONFIG_DIR=str(self.work / 'config'), MEMORY_BACKUP_OFFSITE_DIR=str(self.work / 'offsite'))

    def tool(self, label, mounts, entrypoint, *arguments):
        """A throw-away container of the project's operator image, with no network: `age`, `age-keygen` or the offline `verify-backup`. It is not a service of the project."""
        name = self.container(label)
        command = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--entrypoint', entrypoint]
        for source, target, mode in mounts:
            command += ['-v', f'{source}:{target}:{mode}']
        return self.run(command + [self.image(), *arguments])

    # -- the rehearsal ----------------------------------------------------------------------------------------------------------

    def refuse_existing(self):
        found = self.run(['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.project=' + self.project, '--format', '{{.Names}}']).split()
        if found:
            raise RehearsalError(f'The project {self.project} already has containers; remove them first (docker compose -p {self.project} down -v)')

    def deploy(self):
        self.step('deploy')
        self.run([sys.executable, str(self.root / 'scripts/deploy-memory.py'), '--apply', '--fresh', '--project-name', self.project, '--secret-dir', str(self.work / 'secrets'),
                  '--api-port', str(self.args.api_port), '--web-port', str(self.args.web_port), '--embed-stub', '--roundtrip'], timeout=DEPLOY_TIMEOUT)

    def make_keys(self):
        self.step('keys')
        for folder in ('keys', 'config', 'offsite', 'download', 'restore'):
            (self.work / folder).mkdir(mode=0o777, exist_ok=True)
            os.chmod(self.work / folder, 0o777)  # the container's user (10001) writes here; the directory holds only what this rehearsal creates
        self.tool('keygen', [(self.work / 'keys', '/keys', 'rw')], 'age-keygen', '-o', '/keys/identity.txt')
        identity = (self.work / 'keys' / 'identity.txt').read_text(encoding='utf-8')
        public = re.search(r'^# public key: (age1[0-9a-z]+)$', identity, re.M)
        if not public:
            raise RehearsalError('age-keygen did not write a public key')
        (self.work / 'config' / 'recipients.txt').write_text('# public recipient of the rehearsal\n' + public.group(1) + '\n', encoding='utf-8')
        os.chmod(self.work / 'keys' / 'identity.txt', 0o644)

    def cycle(self):
        self.step('cycle')
        out = self.run(self.compose() + ['run', '--rm', '--no-deps', '-T', '--name', self.container('cycle'), 'memory-backup', 'backup-cycle', '--output-dir', '/backups'],
                       timeout=DEPLOY_TIMEOUT, environment=self.compose_environment())
        report = self.json(out)
        if report.get('status') != 'backed_up' or report.get('offsite', {}).get('status') != 'verified' or not report.get('encrypted'):
            raise RehearsalError('The cycle did not leave a verified, encrypted copy at the destination')
        self.copy = Path(report['path']).name
        if not COPY_NAME.fullmatch(self.copy):
            raise RehearsalError('The copy has an unexpected name')
        self.report['cycle'] = {'copy': self.copy, 'bytes': report['bytes'], 'destination': report['offsite']['destination']}

    def download(self):
        self.step('download')
        for name in (self.copy, self.copy + '.json'):
            shutil.copyfile(self.work / 'offsite' / name, self.work / 'download' / name)

    def verify(self):
        self.step('verify')
        manifest = json.loads((self.work / 'download' / (self.copy + '.json')).read_text(encoding='utf-8'))
        import hashlib
        if hashlib.sha256((self.work / 'download' / self.copy).read_bytes()).hexdigest() != manifest['sha256']:
            raise RehearsalError('The downloaded copy does not match the sha256 of its manifest')
        result = self.json(self.tool('verify', [(self.work / 'download', '/work', 'ro')], 'python', '-m', 'memory_platform.admin', 'verify-backup', '--backup', '/work/' + self.copy))
        if result.get('status') != 'verified' or not result.get('encrypted'):
            raise RehearsalError('verify-backup did not verify the downloaded ciphertext')
        self.report['verify'] = {'sha256': manifest['sha256']}

    def decrypt(self):
        self.step('decrypt')
        self.tool('decrypt', [(self.work / 'keys', '/keys', 'ro'), (self.work / 'download', '/work', 'ro'), (self.work / 'restore', '/restore', 'rw')],
                  'age', '--decrypt', '-i', '/keys/identity.txt', '-o', '/restore/plain.dump', '/work/' + self.copy)
        shutil.copyfile(self.work / 'download' / (self.copy + '.json'), self.work / 'restore' / (self.copy + '.json'))
        result = self.json(self.tool('content', [(self.work / 'restore', '/restore', 'ro')], 'python', '-m', 'memory_platform.admin', 'verify-backup', '--backup', '/restore/plain.dump',
                                     '--manifest', f'/restore/{self.copy}.json'))
        if result.get('status') != 'verified' or result.get('verified') != 'content':
            raise RehearsalError('The decrypted dump does not match the content_sha256 of the manifest')

    def restore(self):
        self.step('restore')
        database = 'memory_restore_' + uuid.uuid4().hex[:12]
        self.run(self.compose() + ['exec', '-T', 'memory-postgres', 'psql', '-U', 'memory', '-d', 'agent_memory', '-v', 'ON_ERROR_STOP=1', '-c', f'CREATE DATABASE {database}'])
        dsn = (self.work / 'secrets' / 'dsn').read_text(encoding='utf-8').strip()
        (self.work / 'restore' / 'target.dsn').write_text(dsn.rsplit('/', 1)[0] + '/' + database + '\n', encoding='utf-8')
        os.chmod(self.work / 'restore' / 'target.dsn', 0o644)
        out = self.run(self.compose() + ['run', '--rm', '--no-deps', '-T', '--name', self.container('restore'), '-v', f'{self.work / "restore"}:/restore:ro', 'memory-admin',
                                         'restore-check', '--backup', '/restore/plain.dump', '--target-dsn-file', '/restore/target.dsn', '--from-manifest', f'/restore/{self.copy}.json'],
                       timeout=DEPLOY_TIMEOUT)
        result = self.json(out)
        if result.get('status') != 'restored_and_content_verified':
            raise RehearsalError('The copy did not restore to the content its manifest records')
        self.report['restore'] = {'status': result['status'], 'tables': len(result.get('tables', {})), 'database': database}

    def shred(self):
        """The private key is overwritten before it is deleted."""
        identity = self.work / 'keys' / 'identity.txt'
        try:
            if identity.is_file():
                identity.write_bytes(b'\0' * max(identity.stat().st_size, 1))
                identity.unlink()
        except OSError:
            pass

    def remove_by_label(self):
        """Containers, then volumes and networks that carry THIS project's compose label, by the names docker lists for it."""
        label = 'label=com.docker.compose.project=' + self.project
        for kind, command, remover in (('containers', ['docker', 'ps', '-a', '--filter', label, '--format', '{{.Names}}'], ['docker', 'rm', '--force', '--volumes']),
                                       ('volumes', ['docker', 'volume', 'ls', '--filter', label, '--format', '{{.Name}}'], ['docker', 'volume', 'rm']),
                                       ('networks', ['docker', 'network', 'ls', '--filter', label, '--format', '{{.Name}}'], ['docker', 'network', 'rm'])):
            for name in self.run(command, check=False).split():
                if name.startswith(self.project):
                    self.run(remover + [name], check=False)

    def cleanup(self):
        """Everything this rehearsal created, by exact name, whatever happened; returns 'complete' or what is left."""
        left = []
        self.shred()
        for name in self.names:
            self.run(['docker', 'rm', '--force', '--volumes', name], check=False)
        self.run(self.compose() + ['down', '--volumes', '--remove-orphans', '--timeout', '30'], timeout=STEP_TIMEOUT, environment=self.compose_environment(), check=False)
        self.remove_by_label()  # what a deployment that stopped half way left and `down` could not name (its files may not exist yet)
        for image in IMAGES:
            self.run(['docker', 'image', 'rm', self.image(image)], check=False)
        if self.private.is_dir() and all(child.name in PRIVATE_FILES for child in self.private.iterdir()):
            shutil.rmtree(self.private, ignore_errors=True)
        if self.work and self.work.is_dir():
            shutil.rmtree(self.work, ignore_errors=True)
        remaining = [line for line in self.run(['docker', 'ps', '-a', '--filter', 'name=' + self.project, '--format', '{{.Names}}'], check=False).split() if line]
        remaining += [line for line in self.run(['docker', 'volume', 'ls', '--filter', 'name=' + self.project, '--format', '{{.Name}}'], check=False).split() if line]
        remaining += [line for line in self.run(['docker', 'network', 'ls', '--filter', 'name=' + self.project, '--format', '{{.Name}}'], check=False).split() if line]
        left += remaining
        return 'complete' if not left else 'incomplete: ' + ', '.join(left)

    def apply(self):
        failure = None
        self.work = Path(tempfile.mkdtemp(prefix='kairos-rehearse-'))
        try:
            self.refuse_existing()
        except BaseException:  # nothing was created: the resources of a project that already exists are not ours to remove
            shutil.rmtree(self.work, ignore_errors=True)
            raise
        try:
            self.deploy()
            self.make_keys()
            self.cycle()
            self.download()
            self.verify()
            self.decrypt()
            self.restore()
        except BaseException as error:
            failure = error
        cleanup = self.cleanup()
        if failure is not None:
            raise failure
        if cleanup != 'complete':
            raise RehearsalError('The rehearsal succeeded but its cleanup is ' + cleanup)
        return dict(status='restored_and_content_verified', project=self.project, steps=self.steps, cleanup=cleanup, **self.report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project-name', required=True, help='kairos-ops-<name>: the isolated project of the rehearsal (created and removed here)')
    parser.add_argument('--embed-stub', action='store_true', help='Required: the simulated embedding provider; the Ollama of the host is never used')
    parser.add_argument('--api-port', type=int, default=DEFAULT_API_PORT)
    parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT)
    args = parser.parse_args(argv)
    try:
        report = Rehearsal(args).apply()
    except RehearsalError as error:
        print(f'rehearsal_failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
