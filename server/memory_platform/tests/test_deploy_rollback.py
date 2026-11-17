"""C-04 / CA-24 (O-06, P-08): the images of a deployment are tagged before the build (`<repository>:<version>-<mark>`), the two newest tags are kept, the tags are recorded in
`deployment-status.json`, and `--rollback` goes back to them without migrating. Docker is a double that keeps a table of images; nothing here needs Docker or the network."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_platform.tests.test_admin import workspace

spec = importlib.util.spec_from_file_location('kairos_deploy_rollback', Path(__file__).parents[3] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

COMPOSE = Path(__file__).parents[3] / 'docker-compose.yml'
PROJECT = 'kairos-ops-rb'
VERSION = '0.4.0'
NAMES = ('api', 'worker', 'mcp', 'web', 'operator')
MANIFEST = '{"sha256":"s","documents":[],"projects":[]}'


def repo(name):
    return f'rehearsal-{PROJECT}-{name}'


class Docker:
    """The commands of a deployment answered from a table of images (`ref -> id`): `image inspect`, `tag`, `image ls`, `image rm` and the build, which gives every `:latest` a new id."""

    def __init__(self, secrets, volumes, images=None, manifests=None):
        self.images = dict(images or {})
        self.commands, self.secrets, self.volumes = [], secrets, volumes
        self.builds = 0
        self.manifests = list(manifests or [])

    def resolve(self, ref):
        return self.images.get(ref) or next((value for key, value in self.images.items() if value == ref), None)

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        if command[:3] == ['docker', 'image', 'inspect']:
            found = self.resolve(command[-1])
            if not found:
                raise deploy.DeploymentError('No such image')
            return found
        if command[:2] == ['docker', 'tag']:
            found = self.resolve(command[2])
            if not found:
                raise deploy.DeploymentError('No such image')
            self.images[command[3]] = found
            return ''
        if command[:3] == ['docker', 'image', 'ls']:
            return '\n'.join(key.split(':', 1)[1] for key in self.images if key.startswith(command[3] + ':'))
        if command[:3] == ['docker', 'image', 'rm']:
            self.images.pop(command[3], None)
            return ''
        if 'build' in command:
            self.builds += 1
            for name in NAMES + ('postgres',):
                self.images[f'{repo(name)}:latest'] = f'sha256:build{self.builds}-{name}'
            return ''
        if command[-3:] == ['config', '--format', 'json']:
            return json.dumps({'secrets': {'memory_postgres': {'file': str(self.secrets / 'postgres_password')}}, 'volumes': {str(i): {'name': n} for i, n in enumerate(self.volumes)}})
        if 'memory-admin' in command:
            answers = {'inspect': '{"tables":{"actors":1}}', 'content-manifest': None,
                       'backup': '{"status":"backed_up","path":"/backups/kairos-before-20261116T090000000000Z.dump","bytes":1}', 'migrate': '{"status":"migrated"}',
                       'verify-backup': '{"status":"verified","encrypted":false,"bytes":1}',
                       'backfill-chunks': '{"status":"backfilled","enqueued":0,"remaining":0,"batches":1,"embedding_filled":0}'}
            verb = next((part for part in command[command.index('memory-admin'):] if part in answers), None)
            if verb == 'content-manifest':
                return self.manifests.pop(0) if self.manifests else MANIFEST
            return answers.get(verb, '{}')
        return ''


class Harness:
    """An isolated project in a temporary root, with the version of the components and the double of Docker."""

    def __init__(self, images=None, status=None, manifests=None, **changes):
        self.workspace = workspace()
        self.root = self.workspace.__enter__()
        (self.root / 'client').mkdir()
        (self.root / 'client' / 'package.json').write_text(json.dumps({'version': VERSION}), encoding='utf-8')
        (self.root / 'docker-compose.yml').write_text(COMPOSE.read_text(encoding='utf-8'), encoding='utf-8')
        self.secrets = self.root / 'private-secrets'
        self.secrets.mkdir()
        for name in ('postgres_password', 'dsn', 'bootstrap_password'):
            (self.secrets / name).write_text('synthetic-only', encoding='utf-8')
        self.private = self.root / '.private' / ('rehearsal-' + PROJECT)
        self.private.mkdir(parents=True)
        (self.private / 'memory-platform.env').write_text('MEMORY_SECRETS_DIR=' + self.secrets.as_posix() + '\n', encoding='utf-8')
        if status is not None:
            (self.private / 'deployment-status.json').write_text(json.dumps(status), encoding='utf-8')
        values = dict(apply=True, fresh=False, secret_dir=str(self.secrets), verify_key_file=None, project_name=PROJECT, api_port=18790, web_port=15173, verify_backup=False)
        values.update(changes)
        self.instance = deploy.Deployment(SimpleNamespace(**values), self.root)
        self.docker = Docker(self.secrets, self.instance.volumes, images, manifests)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self.workspace.__exit__(*exc)

    def patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(self.instance, 'run', side_effect=self.docker))
        stack.enter_context(patch.object(deploy, 'verify_runtime', return_value={}))
        stack.enter_context(patch.object(deploy.time, 'sleep'))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        return stack

    def apply(self):
        with self.patches():
            self.instance.apply()
        return self.docker.commands

    def status(self):
        return json.loads((self.private / 'deployment-status.json').read_text(encoding='utf-8'))


def in_use(release):
    """The five images of a deployment already running: `:latest` of each at the ids of `release`."""
    return {f'{repo(name)}:latest': f'sha256:{release}-{name}' for name in NAMES}


def older_tags(marks, version=VERSION):
    table = {}
    for mark in marks:
        for name in NAMES:
            table[f'{repo(name)}:{version}-{mark}'] = f'sha256:old{mark}-{name}'
    return table


class TaggingTests(unittest.TestCase):
    def test_the_images_in_use_are_tagged_before_the_build_and_the_tags_are_recorded(self):
        with Harness(in_use('running')) as harness:
            commands = harness.apply()
            tags = [c for c in commands if c[:2] == ['docker', 'tag']]
            build = next(n for n, c in enumerate(commands) if 'build' in c)
            self.assertEqual(len(tags), len(NAMES))
            self.assertTrue(all(commands.index(t) < build for t in tags), 'every image is tagged before the build replaces :latest')
            for name in NAMES:
                tag = next(c[3] for c in tags if c[3].startswith(repo(name) + ':'))
                self.assertRegex(tag, r'^' + re.escape(repo(name)) + r':0\.4\.0-\d{8}T\d{6}Z$')
                self.assertEqual(harness.docker.images[tag], f'sha256:running-{name}', 'the tag is the image that was running, not the new one')
            images = harness.status()['images']
            self.assertEqual(images['version'], VERSION)
            self.assertEqual(set(images['previous']), set(NAMES))
            self.assertEqual(images['previous']['api'], next(c[3] for c in tags if c[3].startswith(repo('api') + ':')))
            self.assertEqual(images['current'], {name: f'sha256:build1-{name}' for name in NAMES}, 'the current ids are what the build left in :latest')
            self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], 'sha256:build1-api')

    def test_a_first_deployment_has_nothing_to_tag(self):
        with Harness() as harness:
            commands = harness.apply()
            self.assertFalse([c for c in commands if c[:2] == ['docker', 'tag']])
            self.assertEqual(harness.status()['images']['previous'], {})
            self.assertEqual(set(harness.status()['images']['current']), set(NAMES))

    def test_the_two_newest_tags_are_kept_and_the_older_ones_are_removed(self):
        table = in_use('running')
        table.update(older_tags(['20261101T100000Z', '20261102T100000Z', '20261103T100000Z']))
        with Harness(table) as harness:
            commands = harness.apply()
            removed = sorted(c[3] for c in commands if c[:3] == ['docker', 'image', 'rm'])
            self.assertEqual(removed, sorted(f'{repo(name)}:0.4.0-{mark}' for name in NAMES for mark in ('20261101T100000Z', '20261102T100000Z')))
            kept = sorted(key for key in harness.docker.images if re.search(r':0\.4\.0-\d{8}T\d{6}Z$', key) and key.startswith(repo('api')))
            self.assertEqual(len(kept), 2, 'the newest old tag and the tag of this deployment')
            self.assertIn(f'{repo("api")}:0.4.0-20261103T100000Z', kept)
            self.assertIn(f'{repo("api")}:latest', harness.docker.images, ':latest is never removed')
            self.assertEqual(sorted(harness.status()['images']['kept']['api']), kept)

    def test_an_image_that_is_the_newest_tag_already_is_not_tagged_again(self):
        """A deployment that stopped half way and is run again must not spend the kept tags on one release."""
        table = older_tags(['20261103T100000Z'])
        table.update({f'{repo(name)}:latest': f'sha256:old20261103T100000Z-{name}' for name in NAMES})
        with Harness(table) as harness:
            commands = harness.apply()
            self.assertFalse([c for c in commands if c[:2] == ['docker', 'tag']])
            self.assertEqual(harness.status()['images']['previous']['api'], f'{repo("api")}:0.4.0-20261103T100000Z')

    def test_a_tag_that_cannot_be_made_stops_before_the_build(self):
        with Harness(in_use('running')) as harness:
            real = harness.docker.__call__

            def failing(command, **kwargs):
                if command[:2] == ['docker', 'tag']:
                    harness.docker.commands.append(list(command))
                    raise deploy.DeploymentError('Command failed during build.')
                return real(command, **kwargs)
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=failing), self.assertRaises(deploy.DeploymentError):
                harness.instance.apply()
            self.assertEqual(harness.docker.builds, 0, 'no image is replaced without its tag')

    def test_a_deployment_that_stops_before_it_tags_keeps_the_record_of_the_earlier_one(self):
        record = {'version': VERSION, 'mark': '20261101T100000Z', 'previous': {'api': f'{repo("api")}:0.4.0-20261101T100000Z'}, 'kept': {}, 'current': {}}
        with Harness(status={'status': 'complete', 'images': record}) as harness:
            self.assertEqual(harness.instance.report['images'], record)
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=deploy.DeploymentError('engine denied')), self.assertRaises(deploy.DeploymentError):
                harness.instance.apply()
            self.assertEqual(harness.instance.report['images'], record)


class NamesTests(unittest.TestCase):
    def test_the_tags_of_an_isolated_project_never_coincide_with_the_installed_ones(self):
        with workspace() as root:
            installed = deploy.Deployment(SimpleNamespace(fresh=False, secret_dir=None, verify_key_file=None), root)
            isolated = deploy.Deployment(SimpleNamespace(fresh=False, secret_dir=None, verify_key_file=None, project_name=PROJECT, api_port=18790, web_port=15173), root)
            for name in NAMES:
                self.assertEqual(installed.image_repo(name), f'kairos-{name}')
                self.assertEqual(isolated.image_repo(name), f'rehearsal-{PROJECT}-{name}')
                self.assertNotEqual(installed.image_repo(name), isolated.image_repo(name))
                self.assertFalse(isolated.image_repo(name).startswith(('kairos-', 'knowledge-graphs')))

    def test_the_version_comes_from_the_components_and_is_safe_for_a_tag(self):
        with workspace() as root:
            self.assertEqual(deploy.release_version(root), 'unversioned')
            (root / 'client').mkdir()
            for text, expected in (('{"version": "0.4.0"}', '0.4.0'), ('{"version": "0.5.0-rc.1+b"}', '0.5.0_rc.1_b'), ('{"version": 4}', 'unversioned'), ('nope', 'unversioned')):
                (root / 'client' / 'package.json').write_text(text, encoding='utf-8')
                self.assertEqual(deploy.release_version(root), expected)


if __name__ == '__main__':
    unittest.main()
