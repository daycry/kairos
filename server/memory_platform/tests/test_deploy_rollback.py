"""C-04 / CA-24 (O-06, P-08): the images of a deployment are tagged before the build (`<repository>:<version>-<mark>`), the two newest tags are kept, the tags are recorded in
`deployment-status.json`, and `--rollback` goes back to them without migrating. Docker is a double that keeps a table of images; nothing here needs Docker or the network."""
import contextlib
import copy
import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import re
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_platform.tests.test_admin import workspace
from memory_platform.tests.test_deploy_lock import Holder

spec = importlib.util.spec_from_file_location('kairos_deploy_rollback', Path(__file__).parents[3] / 'scripts/deploy-memory.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

COMPOSE = Path(__file__).parents[3] / 'docker-compose.yml'
PROJECT = 'kairos-ops-rb'
VERSION = '0.4.0'
NAMES = ('api', 'worker', 'mcp', 'web', 'operator')
SERVICE_OF = {'api': 'memory-api', 'worker': 'memory-worker', 'mcp': 'memory-mcp', 'web': 'memory-web'}
MANIFEST = '{"sha256":"s","documents":[],"projects":[]}'


def repo(name):
    return f'rehearsal-{PROJECT}-{name}'


def sid(label):
    """An image id as Docker writes it (`sha256:` and 64 hexadecimal digits; fix3, gap 6) that stands for `label`."""
    return 'sha256:' + hashlib.sha256(label.encode('utf-8')).hexdigest()


class Docker:
    """The commands of a deployment answered from a table of images (`ref -> id`): `image inspect`, `tag`, `image ls`, `image rm` and the build, which gives every `:latest` a new id."""

    def __init__(self, secrets, volumes, images=None, manifests=None, served=None):
        self.images = dict(images or {})
        self.commands, self.secrets, self.volumes = [], secrets, volumes
        self.running_extra = []  # `memory-probe` / `memory-backup` the double reports as running
        self.default_files = ''  # what the label `com.docker.compose.project.config_files` of those containers says unless `config_files` names the service
        self.config_files = {}  # `service -> label` ('' is a container without the label, an Exception is a question that fails)
        self.builds = 0
        self.manifests = list(manifests or [])
        # The image each container runs (`service -> id`): by default the ids in `:latest` of an installation that is up. A build changes `:latest`, never the containers.
        self.served = dict(served) if served is not None else {svc: self.images[f'{repo(name)}:latest'] for name, svc in SERVICE_OF.items() if f'{repo(name)}:latest' in self.images}
        self.alive = set(self.images.values()) | set(self.served.values())  # an image that loses its last tag stays by id while a container runs it (or nobody removed it): Docker keeps it as <none>

    def resolve(self, ref):
        return self.images.get(ref) or (ref if ref in self.alive else None)

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        if command[:2] == ['docker', 'ps'] and any('config_files' in part for part in command):  # the Compose files a running operator service was created with
            assert 'label=com.docker.compose.project=' + PROJECT in command and 'label=com.docker.compose.oneoff=False' in command, command  # only the question of this project is answered
            answer = self.config_files.get(next(part.rsplit('=', 1)[1] for part in command if part.startswith('label=com.docker.compose.service=')), self.default_files)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if command[:2] == ['docker', 'ps']:
            service = next(part.rsplit('=', 1)[1] for part in command if part.startswith('label=com.docker.compose.service='))
            return f'cid-{service}' if service in self.served else ''
        if command[:2] == ['docker', 'inspect']:
            return self.served[command[-1][len('cid-'):]]
        if command[-1:] == ['--services']:  # `compose ps --status running --services`
            return chr(10).join(self.running_extra)
        if 'up' in command:  # a service that is (re)created runs what `:latest` is now
            for name, service in SERVICE_OF.items():
                if service in command:
                    self.served[service] = self.images[f'{repo(name)}:latest']
            return ''
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
            self.alive.add(found)
            return ''
        if command[:3] == ['docker', 'image', 'ls']:
            return '\n'.join(key.split(':', 1)[1] for key in self.images if key.startswith(command[3] + ':'))
        if command[:3] == ['docker', 'image', 'rm']:
            gone = self.images.pop(command[3], None)
            if gone and gone not in self.images.values() and gone not in self.served.values():
                self.alive.discard(gone)
            return ''
        if 'build' in command:
            self.builds += 1
            for name in NAMES + ('postgres',):
                self.images[f'{repo(name)}:latest'] = sid(f'build{self.builds}-{name}')
                self.alive.add(self.images[f'{repo(name)}:latest'])
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

    def __init__(self, images=None, status=None, manifests=None, served=None, **changes):
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
        self.args = SimpleNamespace(**values)
        self.instance = deploy.Deployment(self.args, self.root)
        self.docker = Docker(self.secrets, self.instance.volumes, images, manifests, served)
        self.docker.default_files = ','.join(str(path) for path in (self.root / 'docker-compose.yml', self.private / 'compose.override.yml'))

    def again(self):
        """A new run of the script on the same project: a new `Deployment`, the same Docker and the same status file."""
        self.instance = deploy.Deployment(self.args, self.root)
        return self

    def apply_failing_at(self, verb):
        """An `apply` that stops when the operator command `verb` runs, leaving the status file as `main` does (`failed`)."""
        real = self.docker

        def failing(command, **kwargs):
            if 'memory-admin' in command and verb in command:
                real.commands.append(list(command))
                raise deploy.DeploymentError('Command failed during migrate.')
            return real(command, **kwargs)
        with self.patches(), patch.object(self.instance, 'run', side_effect=failing):
            try:
                self.instance.apply()
            except deploy.DeploymentError:
                pass
            else:
                raise AssertionError('the deployment was meant to stop')
        self.instance.report.update(status='failed', failed_phase=self.instance.phase)
        self.instance.save_report()

    def apply_failing_after(self, phase):
        """An `apply` that fails in `phase` AFTER the containers moved: `start` runs its `up` (the services are recreated with what `:latest` is) and then fails; `verify` fails reading the manifest."""
        real = self.docker

        def failing(command, **kwargs):
            if phase == 'start' and 'up' in command and self.instance.phase == 'start':
                real(command, **kwargs)
                raise deploy.DeploymentError('Command failed during start.')
            if phase == 'verify' and 'content-manifest' in command and self.instance.phase == 'verify':
                raise deploy.DeploymentError('Command failed during verify.')
            return real(command, **kwargs)
        with self.patches(), patch.object(self.instance, 'run', side_effect=failing):
            try:
                self.instance.apply()
            except deploy.DeploymentError:
                pass
            else:
                raise AssertionError('the deployment was meant to stop')
        self.instance.report.update(status='failed', failed_phase=self.instance.phase)
        self.instance.save_report()

    def served_ids(self):
        return {name: self.docker.served.get(service) for name, service in SERVICE_OF.items()}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self.workspace.__exit__(*exc)

    def patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(self.instance, 'run', side_effect=self.docker))
        stack.enter_context(patch.object(deploy, 'verify_runtime', return_value={}))
        stack.enter_context(patch.object(deploy.time, 'sleep'))
        stack.enter_context(patch.object(deploy.subprocess, 'run', side_effect=lambda command, **kwargs: SimpleNamespace(returncode=0, stderr=b'')))  # `docker stop/rm` of a reaped container: no docker here
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        return stack

    def apply(self):
        with self.patches():
            self.instance.apply()
        return self.docker.commands

    def rollback(self):
        with self.patches():
            self.instance.rollback()
        return self.docker.commands

    def status(self):
        return json.loads((self.private / 'deployment-status.json').read_text(encoding='utf-8'))


def in_use(release):
    """The five images of a deployment already running: `:latest` of each at the ids of `release`."""
    return {f'{repo(name)}:latest': sid(f'{release}-{name}') for name in NAMES}


def older_tags(marks, version=VERSION):
    table = {}
    for mark in marks:
        for name in NAMES:
            table[f'{repo(name)}:{version}-{mark}'] = sid(f'old{mark}-{name}')
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
                self.assertEqual(harness.docker.images[tag], sid(f'running-{name}'), 'the tag is the image that was running, not the new one')
            images = harness.status()['images']
            self.assertEqual(images['version'], VERSION)
            self.assertEqual(set(images['previous']), set(NAMES))
            self.assertEqual(images['previous']['api'], next(c[3] for c in tags if c[3].startswith(repo('api') + ':')))
            self.assertEqual(images['current'], {name: sid(f'build1-{name}') for name in NAMES}, 'the current ids are what the build left in :latest')
            self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], sid('build1-api'))

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
        table.update({f'{repo(name)}:latest': sid(f'old20261103T100000Z-{name}') for name in NAMES})
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


class RetryTests(unittest.TestCase):
    """Fix1 of the review of phase 10 (gap 1): the tags are made from the images the CONTAINERS run, not from `:latest`, which a deployment that fails after its build has already replaced."""

    def test_the_tags_are_made_from_the_images_the_containers_run_and_not_from_latest(self):
        table = in_use('built-but-never-served')
        served = {svc: sid(f'served-{name}') for name, svc in SERVICE_OF.items()}
        table.update({f'{repo(name)}:v1-image': sid(f'served-{name}') for name in SERVICE_OF})
        with Harness(table, served=served) as harness:
            commands = harness.apply()
            tags = [c[3] for c in commands if c[:2] == ['docker', 'tag']]
            for name in SERVICE_OF:
                tag = next(key for key in tags if key.startswith(repo(name) + ':0.4.0-'))
                self.assertEqual(harness.docker.images[tag], sid(f'served-{name}'))
            self.assertNotIn(sid('built-but-never-served-api'), [harness.docker.images[key] for key in tags])

    def test_a_deployment_that_fails_after_the_build_and_is_retried_still_rolls_back_to_the_release_that_ran(self):
        with Harness(in_use('v1')) as harness:
            harness.apply_failing_at('migrate')
            first = harness.status()['images']['previous']
            self.assertEqual({harness.docker.images[tag] for name, tag in first.items() if name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})
            self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], sid('build1-api'), 'the build replaced :latest and the containers did not move')
            harness.again().apply_failing_at('migrate')
            harness.again().apply_failing_at('migrate')  # a third attempt must not use up the kept tags on a release that never ran
            for name in SERVICE_OF:
                self.assertEqual(harness.docker.images[first[name]], sid(f'v1-{name}'), 'the tag of the release that ran still holds it')
            self.assertEqual(harness.status()['images']['previous']['api'], first['api'])
            harness.again().apply()
            self.assertEqual(harness.status()['images']['previous']['api'], first['api'], 'v1 is still what the rollback goes back to')
            harness.again().rollback()
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})
            self.assertEqual(harness.status()['status'], 'rolled_back')

    def test_the_operator_image_has_no_container_so_it_is_tagged_only_when_its_state_is_reliable(self):
        with Harness(in_use('v1')) as harness:
            harness.apply()
            self.assertIn('operator', harness.status()['images']['previous'], 'no earlier status: :latest is what it is')
        with Harness(in_use('v1')) as harness:
            harness.apply_failing_at('migrate')
            harness.again().apply()
            previous = harness.status()['images']['previous']
            self.assertEqual(harness.docker.images[previous['operator']], sid('v1-operator'), 'fix2: the image of the last good release is tagged by its id, not whatever :latest is by now')
            self.assertEqual(set(previous), set(NAMES))
        with Harness(in_use('v1'), status={'status': 'failed', 'images': {'previous': {}}}) as harness:
            harness.apply()
            self.assertNotIn('operator', harness.status()['images']['previous'], 'a failed report without a record of a good release: :latest of the operator is not trusted')

    def test_a_service_without_a_container_makes_the_release_incomplete_and_nothing_is_tagged(self):
        served = {'memory-api': sid('v1-api')}
        with Harness(in_use('v1'), served=served) as harness:
            harness.apply()
            self.assertEqual(harness.status()['images']['previous'], {}, 'fix5: a release that lacks a service is incomplete: nothing of it is tagged (it ends well, so `good` is then the complete build)')


class GoodReleaseTests(unittest.TestCase):
    """Fix2 of the review of phase 10 (gaps 1, 2 and the example of the manual): the target of a rollback has ONE source of truth, the images of the last deployment that ended well (`images.good`: ids
    and versions, recorded when it ended `complete` or `rolled_back`). It is tagged by id before a build; a deployment that fails never promotes or prunes that tag, and the images the containers
    run now are never the ones tagged. `already_at_previous` compares with what the CONTAINERS run."""

    def test_a_failure_before_start_then_a_retry_that_moves_the_containers_still_rolls_back_to_v1(self):
        with Harness(in_use('v1')) as harness:
            harness.apply_failing_at('migrate')
            self.assertEqual(harness.served_ids(), {name: sid(f'v1-{name}') for name in SERVICE_OF}, 'nothing moved yet')
            harness.again().apply_failing_after('start')
            self.assertEqual(set(harness.served_ids().values()), {sid(f'build2-{name}') for name in SERVICE_OF}, 'the retry recreated the containers with the build that then failed')
            harness.again().rollback()
            self.assertEqual(harness.served_ids(), {name: sid(f'v1-{name}') for name in SERVICE_OF})
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})
            self.assertEqual(harness.status()['status'], 'rolled_back')

    def test_a_deployment_that_fails_after_the_containers_moved_and_is_retried_keeps_v1_as_the_target_and_its_tag(self):
        for phase in ('start', 'verify'):
            with self.subTest(phase), Harness(in_use('v1')) as harness:
                harness.apply_failing_after(phase)
                first = harness.status()['images']['previous']
                self.assertEqual({harness.docker.images[tag] for name, tag in first.items() if name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})
                for _ in range(3):  # a retry used to tag what the containers ran by then: the failed release
                    harness.again().apply_failing_after(phase)
                    self.assertEqual(harness.status()['images']['previous'], first, 'the target is still v1')
                    for name, tag in first.items():
                        self.assertEqual(harness.docker.images[tag], sid(f'v1-{name}'), 'the tag of the last good release is never pruned nor moved')
                harness.again().rollback()
                self.assertEqual(harness.served_ids(), {name: sid(f'v1-{name}') for name in SERVICE_OF})
                self.assertEqual(harness.status()['status'], 'rolled_back')

    def test_a_failure_then_a_good_deployment_promotes_it_and_the_next_one_tags_it(self):
        with Harness(in_use('v1')) as harness:
            harness.apply_failing_at('migrate')
            harness.again().apply()
            status = harness.status()
            self.assertEqual(status['status'], 'complete')
            self.assertEqual(status['images']['good']['ids'], {name: sid(f'build2-{name}') for name in NAMES}, 'what ended well is what is in :latest now')
            self.assertEqual(set(status['images']['good']['versions']), set(NAMES))
            self.assertEqual(harness.docker.images[status['images']['previous']['api']], sid('v1-api'), 'a rollback of this deployment goes to v1')
            harness.again().apply_failing_at('migrate')
            self.assertEqual(harness.docker.images[harness.status()['images']['previous']['api']], sid('build2-api'), 'the next one tags the release that ended well, by id')
            self.assertEqual(harness.status()['images']['good']['ids']['api'], sid('build2-api'), 'a failed deployment does not change it')

    def test_a_failed_deployment_never_prunes_the_tag_of_the_last_good_release(self):
        table = older_tags(['20261101T100000Z', '20261102T100000Z', '20261103T100000Z'])
        table.update({f'{repo(name)}:latest': sid(f'later-{name}') for name in NAMES})
        record = {'previous': {}, 'kept': {}, 'current': {}, 'good': {'ids': {name: sid(f'old20261101T100000Z-{name}') for name in NAMES}, 'versions': {name: VERSION for name in NAMES}}}
        with Harness(table, {'status': 'failed', 'images': record}) as harness:
            harness.apply_failing_at('migrate')
            for name in NAMES:
                self.assertIn(f'{repo(name)}:{VERSION}-20261101T100000Z', harness.docker.images, 'the oldest tag is the good one: it is protected')
                self.assertEqual(harness.status()['images']['previous'][name], f'{repo(name)}:{VERSION}-20261101T100000Z')
            self.assertFalse([c for c in harness.docker.commands if c[:2] == ['docker', 'tag']], 'the good image is already tagged: nothing is made')

    def test_without_a_record_a_failed_status_is_not_trusted_and_the_recorded_tags_stay_the_target(self):
        recorded = {'previous': {'api': f'{repo("api")}:0.4.0-20261101T100000Z'}, 'kept': {'api': [f'{repo("api")}:0.4.0-20261101T100000Z']}, 'current': {}}
        table = in_use('built-never-served')
        table[f'{repo("api")}:0.4.0-20261101T100000Z'] = sid('the-old-api')
        with Harness(table, {'status': 'failed', 'images': recorded}) as harness:
            harness.apply_failing_at('migrate')
            self.assertEqual(harness.status()['images']['previous'], recorded['previous'])
            self.assertFalse([c for c in harness.docker.commands if c[:2] == ['docker', 'tag']], 'nothing is tagged from images whose state cannot be judged')
            self.assertNotIn('good', harness.status()['images'])

    def test_a_good_image_that_is_gone_is_not_tagged_and_the_rest_are(self):
        table = in_use('v1')
        record = {'previous': {}, 'good': {'ids': {name: sid(f'v1-{name}') for name in NAMES}, 'versions': {name: VERSION for name in NAMES}}}
        table[f'{repo("web")}:latest'] = sid('somebody-else')
        with Harness(table, {'status': 'complete', 'images': record}) as harness:
            harness.apply_failing_at('migrate')
            self.assertNotIn('web', harness.status()['images']['previous'])
            self.assertIn('api', harness.status()['images']['previous'])

    def test_a_good_id_in_the_report_that_is_not_an_id_is_not_passed_to_docker(self):
        record = {'previous': {}, 'good': {'ids': {'api': '--rm', 'worker': 'x y', 'mcp': 7}, 'versions': {}}}
        with Harness(in_use('v1'), {'status': 'complete', 'images': record}) as harness:
            harness.apply_failing_at('migrate')
            self.assertEqual(harness.status()['images']['previous'], {})
            self.assertFalse([c for c in harness.docker.commands if c[:2] == ['docker', 'tag']])

    def test_an_interrupted_rollback_between_tag_and_up_is_finished_by_repeating_it(self):
        """`repro_rb2.py` case A: the first `--rollback` retagged `:latest` and was interrupted before the services were recreated; the containers still run the new version."""
        for saved in (True, False):
            table, status = after_two_deployments()
            with self.subTest(report_saved=saved), Harness(table, status) as harness:
                real = harness.docker

                def interrupted(command, **kwargs):
                    if 'up' in command:
                        real.commands.append(list(command))
                        raise KeyboardInterrupt
                    return real(command, **kwargs)
                with harness.patches(), patch.object(harness.instance, 'run', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                    harness.instance.rollback()
                if saved:
                    harness.instance.report.update(status='failed', failed_phase=harness.instance.phase)
                    harness.instance.save_report()
                self.assertEqual(set(harness.served_ids().values()), {sid(f'new-{name}') for name in SERVICE_OF}, 'the containers still run the new version')
                self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], sid('old-api'), ':latest was retagged')
                harness.again().rollback()
                self.assertEqual(harness.served_ids(), {name: sid(f'old-{name}') for name in SERVICE_OF}, 'repeating it finished the rollback')
                self.assertEqual(harness.status()['status'], 'rolled_back')

    def test_fix3_a_rollback_when_the_containers_run_the_target_but_latest_does_not_retags_latest_and_recreates_nothing(self):
        """Fix3 (gap 1): a deployment that failed before `start` built new images but moved no container. `already_at_previous` would leave `:latest` (and the operator image) on that failed build, and
        the `up -d` that the message and the manual give would start it. The state of a rollback is complete when the containers AND `:latest` of every image are at the target."""
        with Harness(in_use('v1')) as harness:
            harness.apply_failing_at('migrate')
            self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], sid('build1-api'))
            served = dict(harness.docker.served)
            before = len(harness.docker.commands)
            harness.again().rollback()
            new = harness.docker.commands[before:]
            self.assertFalse([c for c in new if 'up' in c], 'the containers are right: none is recreated')
            self.assertEqual(harness.docker.served, served)
            self.assertEqual({c[3] for c in new if c[:2] == ['docker', 'tag']}, {f'{repo(name)}:latest' for name in NAMES}, 'every :latest, the operator image included, is put back')
            self.assertEqual({name: harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {name: sid(f'v1-{name}') for name in NAMES})
            status = harness.status()
            self.assertEqual(status['status'], 'rolled_back')
            self.assertEqual(status['rollback']['recreated'], [])
            self.assertEqual(status['images']['good']['ids'], {name: sid(f'v1-{name}') for name in NAMES})
            with harness.again().patches(), self.assertRaises(deploy.AlreadyAtPrevious):
                harness.instance.rollback()

    def test_fix3_a_stray_latest_of_the_operator_image_alone_is_put_back_and_nothing_is_recreated(self):
        with Harness(in_use('v1')) as harness:
            harness.apply()
            harness.again().rollback()
            harness.docker.images[f'{repo("operator")}:latest'] = sid('stray-operator')
            harness.docker.alive.add(sid('stray-operator'))
            before = len(harness.docker.commands)
            harness.again().rollback()
            new = harness.docker.commands[before:]
            self.assertEqual([c[3] for c in new if c[:2] == ['docker', 'tag']], [f'{repo("operator")}:latest'])
            self.assertFalse([c for c in new if 'up' in c])
            self.assertEqual(harness.docker.images[f'{repo("operator")}:latest'], sid('v1-operator'))

    def test_fix3_only_the_services_whose_container_differs_are_recreated(self):
        with Harness(in_use('v1')) as harness:
            harness.apply()
            harness.again().rollback()
            harness.docker.served['memory-web'] = sid('stray-web')
            harness.docker.alive.add(sid('stray-web'))
            before = len(harness.docker.commands)
            harness.again().rollback()
            new = harness.docker.commands[before:]
            up = [c for c in new if 'up' in c]
            self.assertEqual(len(up), 1)
            self.assertEqual(up[0][up[0].index('--wait-timeout') + 2:], ['memory-web'])
            self.assertFalse([c for c in new if c[:2] == ['docker', 'tag']], ':latest was right: nothing is retagged')
            self.assertEqual(harness.docker.served['memory-web'], sid('v1-web'))
            self.assertEqual(harness.status()['rollback']['recreated'], ['memory-web'])

    def test_fix3_the_message_of_already_at_previous_only_exists_when_latest_is_the_target_too(self):
        """Whatever `up -d --no-build` the message gives starts the target images only if `:latest` is the target: already_at_previous needs both."""
        with Harness(in_use('v1')) as harness:
            harness.apply()
            harness.again().rollback()
            with harness.again().patches(), self.assertRaises(deploy.AlreadyAtPrevious) as raised:
                harness.instance.rollback()
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {sid(f'v1-{name}') for name in NAMES}, 'what `up` would start is the target')
            self.assertIn('up -d --no-build', str(raised.exception))

    def test_a_rollback_after_a_rollback_is_already_at_previous_after_a_failed_retry_too(self):
        with Harness(in_use('v1')) as harness:
            harness.apply()
            harness.again().apply_failing_after('start')
            harness.again().rollback()
            self.assertEqual(harness.status()['images']['good']['ids']['api'], sid('build1-api'), 'the last good release is the one that ended well first, again')
            with harness.again().patches(), self.assertRaises(deploy.AlreadyAtPrevious):
                harness.instance.rollback()

    def test_after_a_rollback_the_next_deployment_tags_the_release_it_went_back_to_by_id(self):
        with Harness(in_use('v1')) as harness:
            harness.apply()
            harness.again().rollback()
            harness.again().apply_failing_at('migrate')
            self.assertEqual({harness.docker.images[tag] for name, tag in harness.status()['images']['previous'].items() if name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})


class TagGrammarTests(unittest.TestCase):
    """Fix2 (gap 6): the version in a tag obeys Docker's grammar `[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}`, mark included; otherwise the version of the code is used."""
    GRAMMAR = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}')

    def test_a_recorded_version_docker_would_refuse_falls_back_to_the_version_of_the_code(self):
        for bad in ('.x', '-x', 'x/y', 'a' * 200, 'a' * 112, '', 'v 1', 7, None):
            record = {'previous': {}, 'kept': {}, 'current': {name: sid(f'running-{name}') for name in NAMES}, 'current_versions': {name: bad for name in NAMES}}
            with self.subTest(bad=str(bad)[:12]), Harness(in_use('running'), {'status': 'complete', 'images': record}) as harness:
                harness.apply()
                for name, tag in harness.status()['images']['previous'].items():
                    reference = tag.split(':', 1)[1]
                    self.assertTrue(self.GRAMMAR.fullmatch(reference), reference)
                    self.assertTrue(reference.startswith(VERSION + '-'), 'the version of the code')

    def test_the_longest_recorded_version_that_fits_is_kept(self):
        version = 'a' * 111
        record = {'previous': {}, 'kept': {}, 'current': {name: sid(f'running-{name}') for name in NAMES}, 'current_versions': {name: version for name in NAMES}}
        with Harness(in_use('running'), {'status': 'complete', 'images': record}) as harness:
            harness.apply()
            reference = harness.status()['images']['previous']['api'].split(':', 1)[1]
            self.assertTrue(self.GRAMMAR.fullmatch(reference))
            self.assertTrue(reference.startswith(version + '-'))

    def test_the_version_of_the_code_is_a_valid_tag_whatever_package_json_says(self):
        with workspace() as root:
            (root / 'client').mkdir()
            for text in ('.x', '...', '-x', '_.', 'x' * 300, '{{}}', '.', 'é'):
                (root / 'client' / 'package.json').write_text(json.dumps({'version': text}), encoding='utf-8')
                version = deploy.release_version(root)
                self.assertTrue(self.GRAMMAR.fullmatch(version + '-20261117T000000Z'), (text, version))

    def test_a_recorded_tag_with_unicode_digits_a_newline_or_a_leading_dot_is_not_one_of_ours(self):
        for tag in (f'{repo("api")}:0.4.0-٢٠٢٦١١١٧T000000Z', f'{repo("api")}:0.4.0-20261117T000000Z\n', f'{repo("api")}:.x-20261117T000000Z'):
            with self.subTest(tag=tag), workspace() as root:
                instance = deploy.Deployment(SimpleNamespace(fresh=False, secret_dir=None, verify_key_file=None, project_name=PROJECT, api_port=18790, web_port=15173), root)
                self.assertTrue(instance.invalid_previous({'api': tag}))


class OperatorServicesTests(unittest.TestCase):
    """Review of milestone B: the services that share the `operator` image (`memory-probe`, `memory-backup`) go back with it."""

    def test_milestone_b_review_a_rollback_recreates_the_running_services_of_the_operator_image(self):
        table, status = after_two_deployments()
        with Harness(table, status) as harness:
            harness.docker.running_extra = ['memory-probe', 'memory-backup']
            commands = harness.rollback()
            main_up = max(n for n, command in enumerate(commands) if 'up' in command and 'memory-api' in command)
            for service, profile in (('memory-probe', 'probe'), ('memory-backup', 'backup')):
                recreate = [n for n, command in enumerate(commands) if 'up' in command and command[-1] == service]
                self.assertEqual(len(recreate), 1, service)
                self.assertGreater(recreate[0], main_up)
                self.assertTrue({'--profile', profile, '--force-recreate', '--no-deps', '-d'} <= set(commands[recreate[0]]))
                self.assertNotIn('--wait', commands[recreate[0]])
            self.assertEqual({key: harness.instance.report.get(key) for key in ('probe_recreated', 'backup_recreated')}, {'probe_recreated': True, 'backup_recreated': True})

    def test_milestone_b_review_a_rollback_starts_nothing_that_was_not_running(self):
        table, status = after_two_deployments()
        with Harness(table, status) as harness:
            commands = harness.rollback()
            self.assertFalse([c for c in commands if 'up' in c and ('memory-probe' in c or 'memory-backup' in c)])
            self.assertFalse(harness.instance.report.get('probe_recreated') or harness.instance.report.get('backup_recreated'))

    def recreated(self, commands, service):
        found = [c for c in commands if 'up' in c and c[-1] == service]
        return found[0] if found else None

    def test_milestone_b_review_n1_a_rollback_recreates_memory_backup_with_the_rclone_override_it_was_created_with(self):
        table, status = after_two_deployments()
        with Harness(table, status) as harness:
            harness.docker.running_extra = ['memory-backup']
            rclone = harness.root / 'docker-compose.backup-rclone.yml'
            harness.docker.config_files['memory-backup'] = ','.join(str(p) for p in (harness.root / 'docker-compose.yml', rclone, harness.private / 'compose.override.yml'))
            command = self.recreated(harness.rollback(), 'memory-backup')
            self.assertEqual([command[n + 1] for n, part in enumerate(command) if part == '-f'], [str(harness.root / 'docker-compose.yml'), str(rclone), str(harness.private / 'compose.override.yml')], command)
            self.assertTrue(harness.instance.report.get('backup_recreated'))

    def test_milestone_b_review_n1_a_rollback_does_not_recreate_a_service_made_with_other_files_or_with_an_unreadable_label(self):
        wrong = {'foreign file': lambda root: str(root / 'docker-compose.yml') + ',' + str(root / 'elsewhere.yml'), 'no label': lambda root: '',
                 'question fails': lambda root: deploy.DeploymentError('boom')}
        for name, answer in wrong.items():
            table, status = after_two_deployments()
            with self.subTest(name), Harness(table, status) as harness:
                harness.docker.running_extra = ['memory-probe', 'memory-backup']
                harness.docker.config_files['memory-backup'] = answer(harness.root)
                commands = harness.rollback()
                self.assertIsNone(self.recreated(commands, 'memory-backup'))
                self.assertTrue(harness.instance.report.get('backup_recreate_skipped'))
                self.assertFalse(harness.instance.report.get('backup_recreated'))
                self.assertIsNotNone(self.recreated(commands, 'memory-probe'), 'the other service is still recreated')
                self.assertTrue(harness.instance.report.get('probe_recreated'))
                self.assertNotIn('command_failure', harness.instance.report)


class VersionOfTheTagTests(unittest.TestCase):
    def test_the_tag_carries_the_version_that_built_the_image_when_the_record_says_so(self):
        record = {'version': '0.3.0', 'mark': '20261101T100000Z', 'previous': {}, 'kept': {}, 'current': {name: sid(f'running-{name}') for name in NAMES},
                  'current_versions': {name: '0.3.0' for name in NAMES}}
        with Harness(in_use('running'), {'status': 'complete', 'images': record}) as harness:
            harness.apply()
            for name in NAMES:
                self.assertRegex(harness.status()['images']['previous'][name], r':0\.3\.0-\d{8}T\d{6}Z$', 'the image is traced to the deployment that built it')
            self.assertEqual(harness.status()['images']['current_versions'], {name: VERSION for name in NAMES})

    def test_an_image_that_cannot_be_traced_gets_the_version_of_the_code_that_tags_it(self):
        record = {'version': '0.3.0', 'previous': {}, 'kept': {}, 'current': {name: sid(f'something-else-{name}') for name in NAMES}, 'current_versions': {name: '0.3.0' for name in NAMES}}
        with Harness(in_use('running'), {'status': 'complete', 'images': record}) as harness:
            harness.apply()
            self.assertRegex(harness.status()['images']['previous']['api'], r':0\.4\.0-\d{8}T\d{6}Z$')

    def test_after_a_rollback_the_versions_come_from_the_tags_it_went_back_to(self):
        table, status = after_two_deployments()
        status['images']['previous'] = {name: f'{repo(name)}:0.3.1-20261103T100000Z' for name in NAMES}
        table = {key.replace('0.4.0-', '0.3.1-'): value for key, value in table.items()}
        with Harness(table, status) as harness:
            harness.rollback()
            self.assertEqual(harness.status()['images']['current_versions'], {name: '0.3.1' for name in NAMES})


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


def after_two_deployments():
    """What Docker holds after a second deployment: `:latest` is the new release and the tags of the first one (the previous) are there."""
    table = {f'{repo(name)}:latest': sid(f'new-{name}') for name in NAMES}
    table.update({f'{repo(name)}:0.4.0-20261103T100000Z': sid(f'old-{name}') for name in NAMES})
    record = {'version': VERSION, 'mark': '20261103T100000Z', 'previous': {name: f'{repo(name)}:0.4.0-20261103T100000Z' for name in NAMES}, 'kept': {},
              'current': {name: sid(f'new-{name}') for name in NAMES}}
    return table, {'status': 'complete', 'images': record}


class RollbackTests(unittest.TestCase):
    def harness(self, **changes):
        table, status = after_two_deployments()
        return Harness(table, status, **changes)

    def test_the_services_go_back_to_the_recorded_tags_and_nothing_is_migrated_backed_up_or_removed(self):
        with self.harness() as harness:
            commands = harness.rollback()
            text = [' '.join(c) for c in commands]
            for forbidden in ('migrate', 'bootstrap', 'backfill', ' backup', 'verify-backup', ' down', ' rm ', '--volumes', ' stop', 'prune', ' build', 'volume', 'network create'):
                self.assertFalse([t for t in text if forbidden in t and 'content-manifest' not in t and 'config' not in t and 'image inspect' not in t and not t.endswith('ps --status running --services')], forbidden)  # the listing of the opt-in services names the profile `backup`
            self.assertFalse([t for t in text if 'memory-migrate' in t or 'memory-bootstrap' in t or 'memory-postgres' in t])
            tags = [c for c in commands if c[:2] == ['docker', 'tag']]
            self.assertEqual({c[2]: c[3] for c in tags}, {f'{repo(name)}:0.4.0-20261103T100000Z': f'{repo(name)}:latest' for name in NAMES})
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {sid(f'old-{name}') for name in NAMES})
            up = [c for c in commands if 'up' in c]
            self.assertEqual(len(up), 1)
            self.assertIn('--no-build', up[0])
            self.assertIn('--no-deps', up[0])
            self.assertEqual(up[0][up[0].index('--wait-timeout') + 2:], ['memory-api', 'memory-worker', 'memory-mcp', 'memory-web'])
            manifests = [n for n, c in enumerate(commands) if 'content-manifest' in c]
            self.assertEqual(len(manifests), 2)
            self.assertLess(manifests[0], commands.index(tags[0]))
            self.assertLess(commands.index(up[0]), manifests[1])

    def test_the_report_keeps_the_tags_and_says_what_was_rolled_back_from(self):
        with self.harness() as harness:
            harness.rollback()
            status = harness.status()
            self.assertEqual(status['status'], 'rolled_back')
            self.assertEqual(status['images']['previous'], after_two_deployments()[1]['images']['previous'])
            self.assertEqual(status['images']['current'], {name: sid(f'old-{name}') for name in NAMES})
            self.assertEqual(status['rollback']['from'], {name: sid(f'new-{name}') for name in NAMES})
            self.assertEqual(status['phases'], ['engine', 'configuration', 'rollback', 'verify'])
            self.assertIs(status['data_removed'], False)

    def test_without_previous_images_it_fails_with_no_previous_images_and_runs_nothing(self):
        for status in (None, {'status': 'complete'}, {'images': {'previous': {}}}, {'images': 'broken'}):
            with self.subTest(status=status), Harness(status=status) as harness:
                with harness.patches(), self.assertRaises(deploy.NoPreviousImages) as raised:
                    harness.instance.rollback()
                self.assertEqual(raised.exception.code, 'no_previous_images')
                self.assertEqual(harness.docker.commands, [], 'no command at all: no service, image or volume was touched')

    def test_a_recorded_tag_that_is_gone_fails_before_any_service_changes(self):
        table, status = after_two_deployments()
        del table[f'{repo("worker")}:0.4.0-20261103T100000Z']
        with Harness(table, status) as harness:
            with harness.patches(), self.assertRaises(deploy.NoPreviousImages) as raised:
                harness.instance.rollback()
            self.assertIn(f'{repo("worker")}:0.4.0-20261103T100000Z', str(raised.exception))
            self.assertFalse([c for c in harness.docker.commands if c[:2] == ['docker', 'tag'] or 'up' in c or 'content-manifest' in c])
            self.assertEqual(harness.docker.images[f'{repo("api")}:latest'], sid('new-api'), ':latest was not moved')

    def test_a_content_that_differs_after_the_rollback_fails_it(self):
        with self.harness() as harness:
            harness.docker.manifests = ['{"sha256":"before","documents":[],"projects":[]}', '{"sha256":"after","documents":[],"projects":[]}']
            with harness.patches(), self.assertRaises(deploy.DeploymentError) as raised:
                harness.instance.rollback()
            self.assertIn('Canonical content changed', str(raised.exception))

    def test_fix1_a_recorded_tag_that_is_not_one_of_ours_is_refused_before_anything_is_touched(self):
        """Fix1 (gap 2, CWE-20/345): the status file is data on disk: keys and tags are checked against `<repository of that image>:<version>-<mark>` before any docker command."""
        good = f'{repo("api")}:0.4.0-20261103T100000Z'
        cases = {'postgres is never retagged': {'postgres': f'{repo("postgres")}:0.4.0-20261103T100000Z'},
                 'an unknown service': {'nginx': good},
                 'another repository': {'api': 'alpine:3.20'},
                 'the repository of another image': {'api': f'{repo("worker")}:0.4.0-20261103T100000Z'},
                 'latest is not a release tag': {'api': f'{repo("api")}:latest'},
                 'a tag with an extra part': {'api': good + '-x'},
                 'not a string': {'api': 7}}
        for label, extra in cases.items():
            table, status = after_two_deployments()
            status['images']['previous'].update(extra)
            with self.subTest(label), Harness(table, status) as harness:
                with harness.patches(), self.assertRaises(deploy.NoPreviousImages):
                    harness.instance.rollback()
                self.assertEqual(harness.docker.commands, [], 'no docker command at all')

    def test_fix1_a_rollback_whose_target_is_what_runs_fails_with_already_at_previous_and_touches_nothing(self):
        """Fix1 (gap 1): the target of the rollback is the image `:latest` already is for every service (the first attempt after a failed deployment, or a second `--rollback`)."""
        table, status = after_two_deployments()
        for name in NAMES:
            table[f'{repo(name)}:latest'] = table[f'{repo(name)}:0.4.0-20261103T100000Z']
        with Harness(table, status) as harness:
            before = (harness.private / 'deployment-status.json').read_text(encoding='utf-8')
            with harness.patches(), self.assertRaises(deploy.AlreadyAtPrevious) as raised:
                harness.instance.rollback()
            self.assertEqual(raised.exception.code, 'already_at_previous')
            self.assertFalse([c for c in harness.docker.commands if c[:2] == ['docker', 'tag'] or 'up' in c or 'content-manifest' in c])
            self.assertEqual((harness.private / 'deployment-status.json').read_text(encoding='utf-8'), before, 'the status file is left as it was')

    def test_fix1_a_second_rollback_after_a_rollback_is_already_at_previous(self):
        with self.harness() as harness:
            harness.rollback()
            with harness.again().patches(), self.assertRaises(deploy.AlreadyAtPrevious):
                harness.instance.rollback()
            self.assertEqual(harness.status()['status'], 'rolled_back')


class RollbackCommandLineTests(unittest.TestCase):
    ARGV = ['--apply', '--rollback', '--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--secret-dir', 'unused']

    def run_main(self, root, argv):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(deploy.subprocess, 'run', side_effect=AssertionError('no command may run')), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = deploy.main(argv, root=root)
        return code, out.getvalue(), err.getvalue()

    def test_without_previous_images_the_command_ends_with_no_previous_images_and_keeps_the_status_file(self):
        with Harness(status={'status': 'complete', 'documents': 3}) as harness:
            before = (harness.private / 'deployment-status.json').read_text(encoding='utf-8')
            code, out, err = self.run_main(harness.root, self.ARGV)
            self.assertEqual(code, 4)
            self.assertIn('no_previous_images', err)
            self.assertEqual((harness.private / 'deployment-status.json').read_text(encoding='utf-8'), before)
            self.assertEqual((harness.private / 'deployment.lock').read_text(encoding='utf-8') if (harness.private / 'deployment.lock').exists() else '', '', 'the lock is released')

    def test_fix1_already_at_previous_is_its_own_exit_code_and_message(self):
        with Harness() as harness, patch.object(deploy.Deployment, 'rollback', side_effect=deploy.AlreadyAtPrevious('the images are already the previous ones')):
            code, out, err = self.run_main(harness.root, self.ARGV)
            self.assertEqual(code, 5)
            self.assertIn('already_at_previous', err)
            self.assertEqual((harness.private / 'deployment.lock').read_text(encoding='utf-8') if (harness.private / 'deployment.lock').exists() else '', '', 'the lock is released')

    def test_a_rollback_takes_the_deployment_lock(self):
        table, status = after_two_deployments()
        with Harness(table, status) as harness:
            with Holder(harness.private, PROJECT):
                code, out, err = self.run_main(harness.root, self.ARGV)
            self.assertEqual(code, 3)
            self.assertIn('deployment_locked', err)

    def test_the_plan_of_a_rollback_has_no_backup_migrate_or_start_and_the_flags_that_make_no_sense_are_refused(self):
        with Harness() as harness:
            code, out, err = self.run_main(harness.root, ['--rollback', '--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173'])
            self.assertEqual(code, 0)
            plan = json.loads(out)
            self.assertEqual(plan['phases'], list(deploy.ROLLBACK_PHASES))
            self.assertEqual(plan['mode'], 'dry-run')
            for phase in ('backup', 'migrate', 'bootstrap', 'backfill', 'build'):
                self.assertNotIn(phase, plan['phases'])
            for extra in (['--fresh'], ['--stop-services-before-migrate'], ['--verify-backup']):
                with self.subTest(extra=extra), self.assertRaises(SystemExit) as raised:
                    self.run_main(harness.root, self.ARGV + extra)
                self.assertEqual(raised.exception.code, 2)


class Killed(BaseException):
    """A process that dies without running any `finally` (SIGKILL, a power cut): nothing in the script catches it."""


def cli(harness, wrap=None, rollback=False):
    """`main()` for the project of `harness` with every command answered by its double of Docker (or by `wrap(instance, command, **kwargs)`): returns (exit code, stderr)."""
    argv = ['--apply'] + (['--rollback'] if rollback else ['--no-verify-backup']) + ['--project-name', PROJECT, '--api-port', '18790', '--web-port', '15173', '--secret-dir', str(harness.secrets)]

    def run(instance, command, **kwargs):
        return wrap(instance, command, **kwargs) if wrap else harness.docker(command, **kwargs)
    err = io.StringIO()
    reaping = contextlib.nullcontext() if hasattr(deploy.subprocess.run, 'assert_called') else patch.object(deploy.subprocess, 'run', side_effect=lambda command, **kwargs: SimpleNamespace(returncode=0, stderr=b''))  # `docker stop/rm` of a reaped container
    with patch.object(deploy.Deployment, 'run', autospec=True, side_effect=run), patch.object(deploy, 'verify_runtime', return_value={}), patch.object(deploy.time, 'sleep'), reaping, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            code = deploy.main(argv, root=harness.root)
        except (KeyboardInterrupt, SystemExit, deploy.Interrupted) as exc:  # `main` must return a code: an exception that escapes it is a traceback and no saved report
            code = f'{type(exc).__name__} escaped main()'
    return code, err.getvalue()


def raising_at_verify(harness, error):
    def wrap(*arguments, **kwargs):  # (instance, command) through `cli`, (command) when it replaces `run` of the instance of the harness
        command = arguments[-1]
        instance = arguments[0] if len(arguments) > 1 else harness.instance
        if instance.phase == 'verify' and 'content-manifest' in command:
            raise error
        return harness.docker(command, **kwargs)
    return wrap


class InterruptedDeploymentTests(unittest.TestCase):
    """Fix3 (gap 2): the record of the tags is durable. As soon as a deployment tags it writes `in_progress` with `images` (`previous`, `good`) BEFORE the build; `good` changes only when it ends
    `complete` or `rolled_back`; Ctrl-C and the signals save `interrupted`; and after a SIGKILL the next run reads the `in_progress` and still points to the last good release. An `in_progress`
    or `interrupted` status is never taken as good, not even when there is no earlier report (the first installation)."""

    def test_the_tags_are_written_as_in_progress_before_the_build(self):
        with Harness(in_use('v1')) as harness:
            seen = []
            real = harness.docker

            def watch(command, **kwargs):
                if 'build' in command:
                    seen.append(harness.status())
                return real(command, **kwargs)
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=watch):
                harness.instance.apply()
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0]['status'], 'in_progress')
            self.assertEqual({real.images[tag] for name, tag in seen[0]['images']['previous'].items() if name in SERVICE_OF}, {sid(f'v1-{name}') for name in SERVICE_OF})
            self.assertEqual(seen[0]['images']['good']['ids'], {name: sid(f'v1-{name}') for name in NAMES}, 'the good release is what was tagged')
            self.assertEqual(harness.status()['status'], 'complete')

    def test_ctrl_c_in_verify_saves_interrupted_and_the_rollback_goes_to_v1(self):
        with Harness(in_use('v0')) as harness:
            harness.apply()  # v0 -> v1, complete
            code, err = cli(harness, raising_at_verify(harness, KeyboardInterrupt()))
            self.assertEqual(code, 130)
            status = harness.status()
            self.assertEqual((status['status'], status['failed_phase']), ('interrupted', 'verify'))
            self.assertIn('interrupted', err)
            self.assertEqual(status['images']['good']['ids']['api'], sid('build1-api'), 'the interrupted build is never the good one')
            self.assertEqual(harness.docker.images[status['images']['previous']['api']], sid('build1-api'))
            code, err = cli(harness, rollback=True)
            self.assertEqual(code, 0, err)
            self.assertEqual(harness.served_ids(), {name: sid(f'build1-{name}') for name in SERVICE_OF})
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {sid(f'build1-{name}') for name in NAMES})
            self.assertEqual(harness.status()['status'], 'rolled_back')

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM'), 'needs signals')
    def test_sigterm_in_verify_saves_interrupted_exits_with_a_code_and_the_rollback_goes_to_v1(self):
        with Harness(in_use('v0')) as harness:
            harness.apply()
            before = signal.getsignal(signal.SIGTERM)

            def wrap(instance, command, **kwargs):
                if instance.phase == 'verify' and 'content-manifest' in command:
                    signal.raise_signal(signal.SIGTERM)
                return harness.docker(command, **kwargs)
            code, err = cli(harness, wrap)
            self.assertEqual(code, 128 + signal.SIGTERM)
            self.assertEqual((harness.status()['status'], harness.status()['interrupted_by']), ('interrupted', 'SIGTERM'))
            self.assertIs(signal.getsignal(signal.SIGTERM), before)
            self.assertEqual(harness.docker.images[harness.status()['images']['previous']['api']], sid('build1-api'))
            self.assertEqual(cli(harness, rollback=True)[0], 0)
            self.assertEqual(harness.served_ids(), {name: sid(f'build1-{name}') for name in SERVICE_OF})

    def test_a_process_killed_in_verify_leaves_in_progress_and_the_rollback_goes_to_v1(self):
        """SIGKILL: nothing after the tagging runs, not even a `finally`; the record written before the build is what the next run reads."""
        with Harness(in_use('v0')) as harness:
            harness.apply()
            harness.again()
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=raising_at_verify(harness, Killed())), self.assertRaises(Killed):
                harness.instance.apply()
            self.assertEqual(harness.status()['status'], 'in_progress')
            self.assertEqual(set(harness.served_ids().values()), {sid(f'build2-{name}') for name in SERVICE_OF}, 'the containers run the build that was never verified')
            harness.again().rollback()
            self.assertEqual(harness.served_ids(), {name: sid(f'build1-{name}') for name in SERVICE_OF})
            self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {sid(f'build1-{name}') for name in NAMES})

    def test_a_process_killed_in_verify_then_a_new_deployment_keeps_v1_as_the_target(self):
        with Harness(in_use('v0')) as harness:
            harness.apply()
            harness.again()
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=raising_at_verify(harness, Killed())), self.assertRaises(Killed):
                harness.instance.apply()
            first = harness.status()['images']['previous']
            harness.again().apply_failing_at('migrate')
            self.assertEqual(harness.status()['images']['previous'], first)
            self.assertEqual(harness.status()['images']['good']['ids']['api'], sid('build1-api'))
            harness.again().apply()
            self.assertEqual(harness.docker.images[harness.status()['images']['previous']['api']], sid('build1-api'), 'the interrupted build never became the release a rollback goes to')

    def test_a_first_installation_that_is_killed_does_not_make_its_build_the_good_one(self):
        """No earlier report: the interrupted build sits in `:latest` (the operator image has no container to compare with) and the retry must not tag it as the release to go back to."""
        with Harness() as harness:
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=raising_at_verify(harness, Killed())), self.assertRaises(Killed):
                harness.instance.apply()
            self.assertEqual(harness.status()['status'], 'in_progress')
            with harness.again().patches(), self.assertRaises(deploy.NoPreviousImages):
                harness.instance.rollback()
            before = len(harness.docker.commands)
            harness.again().apply()
            self.assertFalse([c for c in harness.docker.commands[before:] if c[:2] == ['docker', 'tag']], 'the interrupted build is not tagged')
            self.assertEqual(harness.status()['images']['previous'], {})
            self.assertEqual(harness.status()['images']['good']['ids']['api'], sid('build2-api'), 'only the deployment that ended well is good')

    def test_a_first_installation_interrupted_by_ctrl_c_is_the_same(self):
        with Harness() as harness:
            code, err = cli(harness, raising_at_verify(harness, KeyboardInterrupt()))
            self.assertEqual((code, harness.status()['status']), (130, 'interrupted'))
            self.assertNotIn('good', harness.status()['images'])
            before = len(harness.docker.commands)
            cli(harness)
            self.assertFalse([c for c in harness.docker.commands[before:] if c[:2] == ['docker', 'tag']])

    def test_an_in_progress_or_interrupted_status_is_never_trusted_to_say_what_is_good(self):
        for status in ('in_progress', 'interrupted', 'failed'):
            with self.subTest(status), Harness(in_use('v1'), status={'status': status, 'images': {'previous': {}}}) as harness:
                harness.apply()
                self.assertNotIn('operator', harness.status()['images']['previous'], ':latest of the operator is not trusted after ' + status)

    def test_the_report_is_written_atomically_and_durably(self):
        with Harness() as harness:
            fsynced = []
            real = deploy.os.fsync
            with patch.object(deploy.os, 'fsync', side_effect=lambda descriptor: fsynced.append(descriptor) or real(descriptor)):
                harness.instance.save_report()
            self.assertTrue(fsynced, 'the file is flushed to disk before it replaces the old one')
            self.assertFalse((harness.private / 'deployment-status.tmp').exists())


class LegacyInstallationTests(unittest.TestCase):
    """Fix4 of the review of phase 10 (gap 1, the class): an installation with no `images.good` (no report, or an old `complete` report: the real state of the installed project) has its running
    release recorded as good at the START of a deployment, after the lock and before any phase, so that no interruption or failure afterwards (in `configuration`, half way through the tagging)
    can lose it. When the last status cannot be trusted and there is no record, nothing is invented and the script says exactly why `--rollback` cannot go back."""

    @staticmethod
    def stop_in(harness, where, error):
        state = {'n': 0}

        def run(instance, command, **kwargs):
            if where == 'configuration' and instance.phase == 'configuration' and command[-3:] == ['config', '--format', 'json']:
                raise error
            if where == 'tag' and instance.phase == 'build' and command[:2] == ['docker', 'tag']:
                state['n'] += 1
                if state['n'] == 2:
                    raise error
            return harness.docker(command, **kwargs)
        return run

    def test_a_stop_in_configuration_or_in_the_tagging_of_a_legacy_installation_still_rolls_back_to_the_release_that_ran(self):
        """The cases of the review (`legacy.py`): report `complete` without `good`, or no report; Ctrl-C or a failure in `configuration` or at the second `docker tag`, and the plain
        run; then a deployment that moves the containers and fails after `start`, then `--rollback`: the containers go back to v1."""
        for status in ({'status': 'complete'}, None):
            for where, error in (('none', None), ('configuration', KeyboardInterrupt()), ('configuration', deploy.DeploymentError('x')), ('tag', KeyboardInterrupt()), ('tag', deploy.DeploymentError('x'))):
                with self.subTest(report=status, stop=where, error=type(error).__name__), Harness(in_use('v1'), status=status) as harness:
                    if where != 'none':
                        code, err = cli(harness, self.stop_in(harness, where, error))
                        self.assertEqual(code, 130 if isinstance(error, KeyboardInterrupt) else 1, err)
                        self.assertEqual(harness.status()['images']['good']['ids'], {name: sid(f'v1-{name}') for name in NAMES}, 'the release that runs was recorded before the stop')
                    harness.again().apply_failing_after('start')
                    code, err = cli(harness, rollback=True)
                    self.assertEqual(code, 0, err)
                    self.assertEqual(harness.served_ids(), {name: sid(f'v1-{name}') for name in SERVICE_OF})
                    self.assertEqual({harness.docker.images[f'{repo(name)}:latest'] for name in NAMES}, {sid(f'v1-{name}') for name in NAMES})

    def test_the_running_release_is_saved_as_good_before_configuration_and_after_the_engine_check(self):
        for status in ({'status': 'complete'}, {'status': 'rolled_back', 'images': {'previous': {}}}, None):
            with self.subTest(report=status), Harness(in_use('v1'), status=status) as harness:
                real = harness.docker

                def stop(command, **kwargs):
                    if command[-3:] == ['config', '--format', 'json']:  # the first thing `configuration` runs
                        raise KeyboardInterrupt()
                    return real(command, **kwargs)
                with harness.patches(), patch.object(harness.instance, 'run', side_effect=stop), self.assertRaises(KeyboardInterrupt):
                    harness.instance.apply()
                saved = harness.status()
                self.assertEqual(saved['status'], 'in_progress')
                self.assertEqual(saved['images']['good']['ids'], {name: sid(f'v1-{name}') for name in NAMES}, 'the containers, and :latest for operator')

    def test_a_release_that_is_already_recorded_is_not_saved_again_and_a_first_installation_saves_nothing(self):
        record = {'previous': {}, 'good': {'ids': {name: sid(f'v1-{name}') for name in NAMES}, 'versions': {name: VERSION for name in NAMES}}}
        with Harness(in_use('v1'), status={'status': 'complete', 'images': record}) as harness:
            before = (harness.private / 'deployment-status.json').read_text(encoding='utf-8')
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=deploy.DeploymentError('engine denied')), self.assertRaises(deploy.DeploymentError):
                harness.instance.apply()
            self.assertEqual((harness.private / 'deployment-status.json').read_text(encoding='utf-8'), before)
        with Harness() as harness:
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=deploy.DeploymentError('engine denied')), self.assertRaises(deploy.DeploymentError):
                harness.instance.apply()
            self.assertFalse((harness.private / 'deployment-status.json').exists(), 'nothing runs, so there is nothing to record')
        with Harness(in_use('v1'), status={'status': 'complete'}) as harness:  # a legacy installation: a denied engine is refused before docker is asked for anything else and before any write
            before = (harness.private / 'deployment-status.json').read_text(encoding='utf-8')
            with harness.patches(), patch.object(harness.instance, 'run', side_effect=deploy.DeploymentError('engine denied')) as run, self.assertRaises(deploy.DeploymentError):
                harness.instance.apply()
            self.assertEqual(run.call_args_list[0].args[0][:2], ['docker', 'version'])
            self.assertEqual(run.call_count, 1)
            self.assertEqual((harness.private / 'deployment-status.json').read_text(encoding='utf-8'), before)

    def test_without_a_record_and_after_a_status_that_cannot_be_trusted_nothing_is_invented_and_the_script_says_why_rollback_cannot_go_back(self):
        for status in ('failed', 'interrupted', 'in_progress'):
            with self.subTest(status), Harness(in_use('v1'), status={'status': status, 'images': {'previous': {}}}) as harness:
                real = harness.docker

                def stop(instance, command, **kwargs):
                    if instance.phase == 'configuration' and command[-3:] == ['config', '--format', 'json']:
                        raise KeyboardInterrupt()
                    return real(command, **kwargs)
                code, err = cli(harness, stop)
                self.assertEqual(code, 130)
                self.assertNotIn('good', harness.status()['images'], 'no release is made up')
                self.assertTrue([w for w in harness.status()['warnings'] if 'images.good' in w and status in w], harness.status().get('warnings'))
                self.assertIn('images.good', err)
                self.assertNotIn('still goes back to it', err, 'the message of an interruption promises no rollback that does not exist')
                self.assertIn('no release is recorded as good', err)
                code, err = cli(harness, rollback=True)
                self.assertEqual(code, 4)
                self.assertIn('no_previous_images', err)
                self.assertIn('images.good', err, 'the message says why: there is no record of a good release')

    def test_an_interruption_with_a_record_says_that_rollback_goes_back(self):
        with Harness(in_use('v0')) as harness:
            harness.apply()
            code, err = cli(harness, raising_at_verify(harness, KeyboardInterrupt()))
            self.assertEqual(code, 130)
            self.assertIn('--rollback still goes back to it', err)


class ExitOfTheHandlersTests(unittest.TestCase):
    """Fix4 (gaps 2 and 3): the handlers of a failure or an interruption are not themselves interrupted (a signal during them is held off, and `main` returns the code of the first cause), and every
    container a deployment starts has a name its `reap` can stop and remove."""

    @staticmethod
    def hostile(harness, first, second, where):
        """`main` with `first` raised in verify and `second` raised while the report is saved (`save`), while the hints are made (`hints`) or in the release of the lock (`release`)."""
        real_save, real_hints, real_release = deploy.Deployment.save_report, deploy.failure_hints, deploy.DeployLock.release

        def fire():
            signal.raise_signal({'sigterm': signal.SIGTERM, 'sigint': signal.SIGINT}[second])

        def save(self):
            if where == 'save' and self.report.get('status') in ('interrupted', 'failed'):
                fire()
            return real_save(self)

        def hints(report, phase):
            if where == 'hints':
                fire()
            return real_hints(report, phase)

        def release(self):
            if where == 'release':
                fire()
            return real_release(self)

        def wrap(instance, command, **kwargs):
            if instance.phase == 'verify' and 'content-manifest' in command:
                if first == 'sigterm':
                    signal.raise_signal(signal.SIGTERM)
                elif first == 'ctrlc':
                    raise KeyboardInterrupt()
                else:
                    raise deploy.DeploymentError('x')
            return harness.docker(command, **kwargs)
        with patch.object(deploy.Deployment, 'save_report', save), patch.object(deploy, 'failure_hints', hints), patch.object(deploy.DeployLock, 'release', release):
            return cli(harness, wrap)

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM') and hasattr(signal, 'SIGINT'), 'needs signals')
    def test_a_signal_during_the_failure_or_interruption_handlers_does_not_escape_main(self):
        """`signals2.py` of the review: a second SIGTERM (or SIGINT) while the report is saved, while the hints are printed or while the lock is released used to leave `main` with a traceback."""
        cases = (('SIGTERM then SIGTERM while saving', 'sigterm', 'sigterm', 'save', 128 + signal.SIGTERM, 'interrupted'),
                 ('SIGTERM then SIGTERM in the hints', 'sigterm', 'sigterm', 'hints', 128 + signal.SIGTERM, 'interrupted'),
                 ('failure then SIGTERM while saving', 'fail', 'sigterm', 'save', 1, 'failed'),
                 ('failure then SIGINT while saving', 'fail', 'sigint', 'save', 1, 'failed'),
                 ('failure then SIGTERM in the hints', 'fail', 'sigterm', 'hints', 1, 'failed'),
                 ('Ctrl-C then SIGINT while saving', 'ctrlc', 'sigint', 'save', 130, 'interrupted'),
                 ('Ctrl-C then SIGTERM in the release of the lock', 'ctrlc', 'sigterm', 'release', 130, 'interrupted'),
                 ('failure then SIGTERM in the release of the lock', 'fail', 'sigterm', 'release', 1, 'failed'))
        before = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
        for label, first, second, where, code, status in cases:
            with self.subTest(label), Harness(in_use('v0')) as harness:
                harness.apply()
                result = self.hostile(harness, first, second, where)
                self.assertEqual(result[0], code, result[1][-300:])
                self.assertEqual(harness.status()['status'], status)
                self.assertEqual((signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)), before, 'the handlers are put back')
                self.assertEqual((harness.private / deploy.LOCK_FILE).read_text(encoding='utf-8'), '', 'the lock was released')

    def test_the_containers_of_every_compose_run_have_a_name_and_an_interruption_stops_and_removes_it(self):
        for verb in ('inspect', 'migrate', 'backfill-chunks', 'memory-files'):
            with self.subTest(verb), Harness(in_use('v1')) as harness:
                seen, stops = {}, []

                def wrap(instance, command, **kwargs):
                    if 'run' in command and (verb in command[command.index('memory-admin'):] if 'memory-admin' in command else verb in command):
                        seen['name'] = command[command.index('--name') + 1]  # ValueError: a container with no name cannot be reaped
                        raise KeyboardInterrupt()
                    return harness.docker(command, **kwargs)
                with patch.object(deploy.subprocess, 'run', side_effect=lambda command, **kwargs: stops.append(list(command)) or SimpleNamespace(returncode=0, stderr=b'')):
                    code, err = cli(harness, wrap)
                self.assertEqual(code, 130, err)
                name = seen['name']
                self.assertEqual(stops, [['docker', 'stop', '--time', '20', name], ['docker', 'rm', '--force', '--volumes', name]])
                self.assertEqual(harness.status()['reaped_containers'], [name])
                self.assertNotIn('unreaped_containers', harness.status())

    def test_a_container_that_could_not_be_stopped_is_said_not_hidden_behind_no_later_phase_was_run(self):
        with Harness(in_use('v1')) as harness:
            seen = {}

            def wrap(instance, command, **kwargs):
                if 'run' in command and 'memory-admin' in command and 'migrate' in command:
                    seen['name'] = command[command.index('--name') + 1]
                    raise KeyboardInterrupt()
                return harness.docker(command, **kwargs)
            with patch.object(deploy.subprocess, 'run', side_effect=OSError('docker is gone')):
                code, err = cli(harness, wrap)
            self.assertEqual(code, 130)
            name = seen['name']
            self.assertEqual(harness.status()['unreaped_containers'], [name])
            self.assertIn('may still be running', err)
            self.assertIn(name, err)
            self.assertIn('docker rm --force ' + name, err)
            self.assertNotIn('reaped_containers', harness.status())


class GoodIdTests(unittest.TestCase):
    """Fix3 (gap 6): an id read from `deployment-status.json` is passed to docker only as `sha256:` and 64 lowercase hexadecimal digits; anything else is ignored with a warning."""
    BAD = ('alpine:3', 'busybox', 'sha256:' + 'A' * 64, 'sha256:' + 'a' * 63, 'sha256:' + 'a' * 65, 'sha256:' + 'a' * 64 + '\n', 'sha256:' + 'g' * 64, 'sha256:abc', 'sha256:v1-api', '', ' ' + sid('x'), 7)

    def test_an_id_that_is_not_a_full_sha256_is_ignored_with_a_warning_and_the_rest_are_tagged(self):
        for bad in self.BAD:
            ids = {name: sid(f'v1-{name}') for name in NAMES}
            ids['api'] = bad
            record = {'previous': {}, 'good': {'ids': ids, 'versions': {name: VERSION for name in NAMES}}}
            with self.subTest(bad=str(bad)[:20]), Harness(in_use('v1'), {'status': 'complete', 'images': record}) as harness:
                harness.apply_failing_at('migrate')
                status = harness.status()
                self.assertNotIn('api', status['images']['previous'])
                self.assertEqual(set(status['images']['previous']), set(NAMES) - {'api'})
                self.assertTrue([w for w in status.get('warnings', []) if 'api' in w and 'images.good' in w], status.get('warnings'))
                self.assertFalse([c for c in harness.docker.commands if isinstance(bad, str) and bad and bad in c], 'it never reached docker')

    def test_a_valid_id_is_accepted(self):
        record = {'previous': {}, 'good': {'ids': {name: sid(f'v1-{name}') for name in NAMES}, 'versions': {name: VERSION for name in NAMES}}}
        with Harness(in_use('v1'), {'status': 'complete', 'images': record}) as harness:
            harness.apply_failing_at('migrate')
            self.assertEqual(set(harness.status()['images']['previous']), set(NAMES))
            self.assertNotIn('warnings', harness.status())

    def test_the_pattern_is_exactly_sha256_and_64_lowercase_hex_digits(self):
        self.assertTrue(deploy.IMAGE_ID.fullmatch(sid('x')))
        for bad in self.BAD:
            self.assertFalse(isinstance(bad, str) and deploy.IMAGE_ID.fullmatch(bad), bad)


class TagMarkTests(unittest.TestCase):
    """Fix3 (gap 7): a tag the script made is exactly `<version>-<mark>`; a manual tag that merely starts like one is nobody's to prune."""

    def test_the_pattern_is_anchored(self):
        self.assertTrue(deploy.TAG_MARK.fullmatch('0.4.0-20261117T000000Z'))
        for tag in ('1.0-20261117T000000Z-manual', '1.0-20261117T000000Z.bak', 'x-20261117T000000Z\n', '-20261117T000000Z', '1.0-20261117T000000', 'latest'):
            self.assertFalse(deploy.TAG_MARK.fullmatch(tag), tag)

    def test_a_manual_tag_with_a_suffix_is_neither_listed_nor_pruned_nor_counted(self):
        table = in_use('running')
        table.update(older_tags(['20261101T100000Z', '20261102T100000Z', '20261103T100000Z']))
        manual = [f'{repo(name)}:1.0-20261117T000000Z-manual' for name in NAMES] + [f'{repo("api")}:0.4.0-20261117T000000Z.bak']
        table.update({tag: sid('somebody-' + tag) for tag in manual})
        with Harness(table) as harness:
            with harness.patches():
                self.assertEqual(harness.instance.tags_of('api'), [f'0.4.0-{mark}' for mark in ('20261103T100000Z', '20261102T100000Z', '20261101T100000Z')])
            commands = harness.apply()
            removed = sorted(c[3] for c in commands if c[:3] == ['docker', 'image', 'rm'])
            self.assertEqual(removed, sorted(f'{repo(name)}:0.4.0-{mark}' for name in NAMES for mark in ('20261101T100000Z', '20261102T100000Z')), 'the same tags as without the manual ones')
            for tag in manual:
                self.assertIn(tag, harness.docker.images, 'a manual tag is never pruned')


class ExplorationTests(unittest.TestCase):
    """Fix3: random sequences (fixed seed) of deployments that end well, fail in each phase, are killed (nothing saved) or interrupted by Ctrl-C (`interrupted` saved), and rollbacks that fail or are
    interrupted, over the double of Docker. The oracle is the model: after every step a `--rollback` must go to (or already be at) the LAST GOOD RELEASE, with its containers AND its `:latest`,
    and the tag of that release must still exist. (The double keeps an image by id after it loses its last tag, as Docker does.)

    Fix4, `legacy` mode (the installed project: no report and no `images.good`): the first step is anything, and the stops also happen in `configuration`, half way through the tagging, around the
    save of `in_progress` and inside the tagging and the verification of a rollback."""
    APPLY_STEPS = ['ok'] + [f'{kind}:{phase}' for kind in ('fail', 'kill', 'ctrlc') for phase in ('build', 'inspect', 'backup', 'migrate', 'backfill', 'start', 'start_partial', 'verify')]
    ROLLBACK_STEPS = ['rb', 'rb_kill_up', 'rb_ctrlc_up', 'rb_fail_up']
    LEGACY_STEPS = (['ok'] + [f'{kind}:{phase}' for kind in ('fail', 'kill', 'ctrlc') for phase in ('configuration', 'build', 'inspect', 'backup', 'migrate', 'backfill', 'start', 'start_partial', 'verify', 'tagcmd')]
                    + [f'{kind}:{phase}' for kind in ('kill', 'ctrlc') for phase in ('save_before', 'save_after')]
                    + ROLLBACK_STEPS + [f'rb_{kind}_{phase}' for kind in ('fail', 'kill', 'ctrlc') for phase in ('tag', 'verify')])
    SEQUENCES, LENGTH, SEED = 24, 6, 20261117
    LEGACY_SEQUENCES, LEGACY_LENGTH, LEGACY_SEED = 60, 8, 9

    class Clock(datetime.datetime):
        tick = 0

        @classmethod
        def now(cls, tz=None):
            ExplorationTests.Clock.tick += 1
            return datetime.datetime(2026, 11, 17, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=ExplorationTests.Clock.tick)

    def wrapped(self, harness, step):
        real = harness.docker
        kind, _, phase = step.partition(':')
        state = {'n': 0, 'k': self.dice.randint(1, 12), 'after': self.dice.random() < 0.5}

        def exception(of=None):
            of = of or kind
            return deploy.DeploymentError('x') if of == 'fail' else KeyboardInterrupt() if of == 'ctrlc' else Killed()

        def run(command, **kwargs):
            now = harness.instance.phase
            if kind in ('fail', 'kill', 'ctrlc'):
                if phase == 'build' and 'build' in command:
                    real(command, **kwargs)
                    raise exception()
                if phase in ('inspect', 'backup', 'migrate') and 'memory-admin' in command and phase in command:
                    raise exception()
                if phase == 'backfill' and 'backfill-chunks' in command:
                    raise exception()
                if phase == 'start' and now == 'start' and 'up' in command:
                    real(command, **kwargs)
                    raise exception()
                if phase == 'start_partial' and now == 'start' and 'up' in command:
                    real([c for c in command if c not in ('memory-mcp', 'memory-web')], **kwargs)
                    raise exception()
                if phase == 'verify' and now == 'verify' and 'content-manifest' in command:
                    raise exception()
                if phase == 'configuration' and now == 'configuration' and command[-3:] == ['config', '--format', 'json']:
                    raise exception()
                if phase == 'tagcmd' and now == 'build' and (command[:2] == ['docker', 'tag'] or command[:3] == ['docker', 'image', 'rm']):
                    state['n'] += 1
                    if state['n'] == state['k']:
                        if state['after']:
                            real(command, **kwargs)
                        raise exception()
            if step in self.ROLLBACK_STEPS[1:] and 'up' in command:
                real([c for c in command if c not in ('memory-mcp', 'memory-web')], **kwargs)
                raise {'rb_kill_up': Killed, 'rb_ctrlc_up': KeyboardInterrupt, 'rb_fail_up': lambda: deploy.DeploymentError('up')}[step]()
            if step.startswith('rb_') and step.endswith('_tag') and now == 'rollback' and command[:2] == ['docker', 'tag']:
                state['n'] += 1
                if state['n'] == min(state['k'], 3):
                    if state['after']:
                        real(command, **kwargs)
                    raise exception(step.split('_')[1])
            if step.startswith('rb_') and step.endswith('_verify') and now == 'verify' and 'content-manifest' in command:
                raise exception(step.split('_')[1])
            return real(command, **kwargs)
        return run

    def do(self, harness, step):
        harness.again()
        instance = harness.instance
        realsave, (kind, _, phase) = instance.save_report, step.partition(':')

        def save():
            if phase in ('save_before', 'save_after') and instance.report.get('status') == 'in_progress' and not getattr(save, 'done', False):
                save.done = True  # the first save of `in_progress`: the process stops right before it (nothing written) or right after it (written)
                if phase == 'save_after':
                    realsave()
                raise KeyboardInterrupt() if kind == 'ctrlc' else Killed()
            return realsave()
        with harness.patches(), patch.object(instance, 'run', side_effect=self.wrapped(harness, step)), patch.object(instance, 'save_report', side_effect=save):
            try:
                instance.rollback() if step.startswith('rb') else instance.apply()
                return 'done'
            except (deploy.NoPreviousImages, deploy.AlreadyAtPrevious) as exc:
                return type(exc).__name__
            except Killed:
                return 'killed'  # nothing else runs: the status file is what the last `save_report` wrote
            except KeyboardInterrupt:
                instance.report.update(status='interrupted', failed_phase=instance.phase)  # what `main` does
                if instance.phase != 'engine':
                    realsave()
                return 'interrupted'
            except Exception:
                instance.report.update(status='failed', failed_phase=instance.phase)
                if instance.phase != 'engine':
                    realsave()
                return 'failed'

    @staticmethod
    def latest(harness):
        return {name: harness.docker.images.get(repo(name) + ':latest') for name in NAMES}

    def trial(self, harness, expected):
        """A `--rollback` from this state, then back to the state: the problems it shows."""
        path = harness.private / 'deployment-status.json'
        docker = harness.docker
        snapshot = (copy.deepcopy(docker.images), copy.deepcopy(docker.served), set(docker.alive), path.read_text(encoding='utf-8') if path.exists() else None)
        outcome = self.do(harness, 'rb')
        served = {name: docker.served.get(SERVICE_OF[name]) for name in SERVICE_OF}
        latest = self.latest(harness)
        docker.images, docker.served, docker.alive = snapshot[0], snapshot[1], snapshot[2]
        if snapshot[3] is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(snapshot[3], encoding='utf-8')
        if expected is None:
            return [] if outcome == 'NoPreviousImages' else [f'expected no_previous_images, got {outcome} (containers {served})']
        if outcome == 'NoPreviousImages' and served == {name: expected[name] for name in SERVICE_OF} and latest == expected:
            return []  # the good release is recorded (images.good) but no deployment has tagged anything since: the containers and :latest already are it, so there is nothing to go back to
        problems = []
        tagged = {name: any(value == expected[name] and not key.endswith(':latest') for key, value in snapshot[0].items() if key.startswith(repo(name) + ':')) for name in NAMES}
        if not all(tagged.values()):
            problems.append(f'the tag of the good release is gone for {[name for name in NAMES if not tagged[name]]}')
        if outcome not in ('done', 'AlreadyAtPrevious'):
            problems.append(f'outcome {outcome}')
        if served != {name: expected[name] for name in SERVICE_OF}:
            problems.append(f'containers {served} are not the good release {expected}')
        if latest != expected:
            problems.append(f'`:latest` {[name for name in NAMES if latest[name] != expected[name]]} is not the good release after {outcome}')
        return problems

    def sequence(self, rng, legacy=False):
        with Harness(in_use('v0')) as harness:
            good, expected, log, issues = self.latest(harness), None, [], []
            for _ in range(self.LEGACY_LENGTH if legacy else self.LENGTH):
                step = rng.choice(self.LEGACY_STEPS if legacy else self.APPLY_STEPS + self.ROLLBACK_STEPS)
                before = dict(good)
                outcome = self.do(harness, step)
                stopped_before_the_save = step.split(':')[-1] in ('configuration', 'tagcmd') or step == 'kill:save_before'  # nothing of this deployment was recorded
                if not step.startswith('rb') and outcome == 'done':  # `ok`, or a stop that never came (a tagging with fewer commands than the one it was meant to stop at)
                    expected, good = before, self.latest(harness)
                elif stopped_before_the_save:
                    pass  # the rollback target is what it was
                elif not step.startswith('rb'):
                    expected = good
                elif outcome == 'done':
                    good = self.latest(harness)
                    expected = good
                log.append(f'{step}->{outcome}')
                issues += [(' | '.join(log), problem) for problem in self.trial(harness, expected)]
            return issues

    def test_after_any_sequence_a_rollback_goes_to_the_last_good_release_with_its_containers_and_its_latest(self):
        rng, self.dice = random.Random(self.SEED), random.Random(self.SEED + 1)
        with patch.object(deploy, 'datetime', self.Clock):
            issues = [issue for _ in range(self.SEQUENCES) for issue in self.sequence(rng)]
        self.assertEqual(issues[:3], [], f'{len(issues)} problems; the first three are shown')

    def test_fix4_legacy_installation_with_stops_in_configuration_and_in_the_tagging_gives_no_problem(self):
        """Lens B of attempt 4 (`explore4.py ... legacy`): 401 problems in 300 sequences of 8 steps at HEAD of fix3, all after a stop in `configuration` or in the tagging of an installation that had no record."""
        rng, self.dice = random.Random(self.LEGACY_SEED), random.Random(self.LEGACY_SEED + 1)
        with patch.object(deploy, 'datetime', self.Clock):
            issues = [issue for _ in range(self.LEGACY_SEQUENCES) for issue in self.sequence(rng, legacy=True)]
        self.assertEqual(issues[:3], [], f'{len(issues)} problems; the first three are shown')


class Fix5Tests(unittest.TestCase):
    """Review of phase 10, attempt 5 (six Minor gaps): a partial `good` is never recorded, `--rollback` never reports `rolled_back` with a service outside the destination, a signal at the edges of the
    held-off windows never leaves `main` without releasing the lock or cancels a `reap`, and what the status file says reaches stderr and the report only escaped."""
    OLD = {'status': 'complete', 'phases': ['engine', 'configuration', 'build', 'database', 'inspect', 'backup', 'migrate', 'bootstrap', 'backfill', 'start', 'verify'], 'backup': None,
           'previous_images': {'memory-api': sid('v0-api')}, 'content_sha256': 's', 'documents': 0, 'projects': 0}

    @staticmethod
    def stop_in_configuration(harness):
        return lambda instance, command, **kw: (_ for _ in ()).throw(KeyboardInterrupt()) if instance.phase == 'configuration' and command[-3:] == ['config', '--format', 'json'] else harness.docker(command, **kw)

    def test_gap1_an_installation_with_services_without_a_container_never_records_a_partial_good_and_rollback_never_reports_success(self):
        """`legacy5.py`: an old `complete` report without `images`, with only memory-api and memory-worker (or no container) running."""
        for label, served in (('api and worker only', {'memory-api': sid('v1-api'), 'memory-worker': sid('v1-worker')}), ('no container', {})):
            with self.subTest(label), Harness(in_use('v1'), status=self.OLD, served=served) as harness:
                code, err = cli(harness, self.stop_in_configuration(harness))
                self.assertEqual(code, 130, err)
                good = (harness.status().get('images') or {}).get('good', {}).get('ids', {})
                self.assertFalse(good, f'a good release that lacks a service is not recorded as complete: {good}')
                harness.again().apply_failing_after('start')
                built = {name: image_id for name, image_id in harness.served_ids().items() if image_id}
                self.assertTrue(built and all(image_id not in {sid(f'v1-{name}') for name in NAMES} for image_id in built.values()), 'the failed build runs')
                code, err = cli(harness.again(), rollback=True)
                self.assertNotEqual(code, 0, err)
                self.assertNotEqual(harness.status()['status'], 'rolled_back')
                self.assertIn('no_previous_images', err)
                harness.again().apply_failing_after('start')  # the next deployment must not tag the failed build as the good one
                images = harness.status()['images']
                tagged = set((images.get('good') or {}).get('ids', {}).values())
                self.assertFalse(tagged & set(built.values()), 'the build that failed is not tagged as good')

    def test_gap1_a_complete_installation_still_records_the_release_that_runs(self):
        with Harness(in_use('v1'), status=self.OLD) as harness:
            cli(harness, self.stop_in_configuration(harness))
            self.assertEqual(harness.status()['images']['good']['ids'], {name: sid(f'v1-{name}') for name in NAMES})

    def test_gap1_a_rollback_whose_recorded_images_leave_a_service_out_is_refused_before_any_service_changes(self):
        for left_out in ('api', 'mcp', 'web'):
            table, status = after_two_deployments()
            status['images']['previous'].pop(left_out)
            with self.subTest(left_out), Harness(table, status) as harness:
                before = (harness.private / 'deployment-status.json').read_text(encoding='utf-8')
                code, err = cli(harness, rollback=True)
                self.assertEqual(code, deploy.EXIT_NO_PREVIOUS_IMAGES, err)
                self.assertIn('memory-' + left_out, err)
                self.assertFalse([c for c in harness.docker.commands if 'up' in c or c[:2] == ['docker', 'tag']], 'nothing was touched')
                self.assertEqual((harness.private / 'deployment-status.json').read_text(encoding='utf-8'), before)

    def test_gap1_only_the_images_that_are_in_the_destination_are_promoted_to_good(self):
        table, status = after_two_deployments()
        status['images']['previous'].pop('operator')  # the operator image is not a service: it is not part of the destination
        with Harness(table, status) as harness:
            code, err = cli(harness, rollback=True)
            self.assertEqual(code, 0, err)
            self.assertEqual(harness.status()['images']['good']['ids'], {name: sid(f'old-{name}') for name in SERVICE_OF})

    @unittest.skipUnless(hasattr(signal, 'raise_signal') and hasattr(signal, 'SIGTERM'), 'needs signals')
    def test_gap2_a_signal_between_the_end_of_settle_or_apply_and_the_disarm_still_releases_the_lock(self):
        """`signals5.py`: a SIGTERM delivered when `disarm()` runs used to escape `main` with the lock held."""
        real_install = deploy.install_signal_handlers

        def late_install():
            put_back = real_install()
            original, sent = put_back.disarm, []

            def disarm():
                if not sent:  # one signal, as in life
                    sent.append(True)
                    signal.raise_signal(signal.SIGTERM)
                original()
            put_back.disarm = disarm
            return put_back
        before = signal.getsignal(signal.SIGTERM)
        for label, failing, code, status in (('failure in verify', True, 1, 'failed'), ('success', False, 0, 'complete')):
            with self.subTest(label), Harness(in_use('v0')) as harness:
                harness.apply()
                wrap = raising_at_verify(harness, deploy.DeploymentError('x')) if failing else None
                with patch.object(deploy, 'install_signal_handlers', late_install):
                    result = cli(harness, wrap)
                self.assertEqual(result[0], code, result[1][-300:])
                self.assertEqual(harness.status()['status'], status)
                self.assertEqual((harness.private / deploy.LOCK_FILE).read_text(encoding='utf-8'), '', 'the lock was released')
                self.assertEqual(signal.getsignal(signal.SIGTERM), before, 'the handlers are put back')

    def test_gap3_a_signal_while_the_signals_are_being_ignored_does_not_cancel_the_reap(self):
        """`signals5.py`: the SIGINT that was pending when `ignoring_signals` set SIG_IGN raised out of it, and the `docker stop/rm` of the container never ran."""
        real_signal, state, calls = signal.signal, {'armed': False, 'fired': False}, []

        def signal_with_pending_sigint(number, handler):
            previous = real_signal(number, handler)
            if state['armed'] and not state['fired'] and number == signal.SIGTERM and handler is signal.SIG_IGN:
                state['fired'] = True
                raise KeyboardInterrupt()
            return previous
        before = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
        with Harness(in_use('v0')) as harness:
            harness.apply()

            def wrap(instance, command, **kw):
                if 'memory-admin' in command and 'migrate' in command:
                    state['armed'] = True
                    raise deploy.DeploymentError('Command failed during migrate.')
                return harness.docker(command, **kw)
            fake = lambda command, **kw: (calls.append(command[:2]), SimpleNamespace(returncode=0, stderr=b''))[1]
            with patch.object(deploy.signal, 'signal', signal_with_pending_sigint), patch.object(deploy.subprocess, 'run', side_effect=fake):
                code, err = cli(harness, wrap)
            saved = harness.status()
            self.assertTrue(state['fired'])
            self.assertEqual(code, 1, err)
            self.assertEqual(calls, [['docker', 'stop'], ['docker', 'rm']])
            self.assertEqual(len(saved.get('reaped_containers', [])), 1, saved)
            self.assertNotIn('unreaped_containers', saved)
        self.assertEqual((signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)), before)

    def test_gap3_a_signal_before_the_reap_holds_the_signals_off_does_not_cancel_it_either(self):
        real, calls, state = deploy.ignoring_signals, [], {'fired': False}

        class Hostile:
            def __enter__(self):
                if not state['fired']:
                    state['fired'] = True
                    raise KeyboardInterrupt()  # a Ctrl-C right before the signals are held off
                self.inner = real()
                return self.inner.__enter__()

            def __exit__(self, *exc):
                return self.inner.__exit__(*exc)
        with Harness(in_use('v0')) as harness:
            harness.apply()

            def wrap(instance, command, **kw):
                if 'memory-admin' in command and 'migrate' in command:
                    raise deploy.DeploymentError('Command failed during migrate.')
                return harness.docker(command, **kw)
            fake = lambda command, **kw: (calls.append(command[:2]), SimpleNamespace(returncode=0, stderr=b''))[1]
            with patch.object(deploy, 'ignoring_signals', Hostile), patch.object(deploy.subprocess, 'run', side_effect=fake):
                cli(harness, wrap)
            self.assertIn(['docker', 'rm'], calls, 'the container was stopped and removed')
            self.assertEqual(len(harness.status().get('reaped_containers', [])), 1)

    def test_gap6_what_the_status_file_says_reaches_stderr_and_the_warnings_only_escaped(self):
        evil = '\x1b]0;PWN\x07‮EVIL'
        with Harness(status={'status': evil}) as harness:
            code, out, err = RollbackCommandLineTests.run_main(None, harness.root, RollbackCommandLineTests.ARGV)
            self.assertEqual(code, 4)
            self.assertNotIn('\x1b', err)
            self.assertNotIn('‮', err)
            self.assertIn('PWN', err)
        table, status = after_two_deployments()
        status['images'].pop('previous')
        status['status'] = evil
        with Harness(table, status) as harness:
            code, err = cli(harness)
            self.assertNotIn('\x1b', err)
            self.assertNotIn('‮', err)
            warnings = harness.status().get('warnings', [])
            self.assertTrue([w for w in warnings if 'PWN' in w], warnings)
            self.assertFalse([w for w in warnings if '\x1b' in w or '‮' in w], warnings)


class DocumentationTests(unittest.TestCase):
    """T-65: the operations manual says what the script does, with the names and codes of the script itself."""

    def test_the_manual_names_the_codes_flags_phases_tags_and_exit_codes_of_the_script(self):
        text = (Path(__file__).parents[3] / 'docs/operations.md').read_text(encoding='utf-8')
        for name in (deploy.DeploymentLocked.code, deploy.NoPreviousImages.code, deploy.AlreadyAtPrevious.code, deploy.LOCK_FILE, '--break-lock', '--rollback', 'kairos-<imagen>:<versión>-<marca>', 'images.previous', 'content-manifest', 'lock broken',
                     f'código de salida **{deploy.EXIT_LOCKED}**', f'código de salida **{deploy.EXIT_NO_PREVIOUS_IMAGES}**', f'código de salida **{deploy.EXIT_ALREADY_AT_PREVIOUS}**'):
            self.assertIn(name, text)
        for phase in deploy.ROLLBACK_PHASES:
            self.assertIn(f'`{phase}`', text)
        for image in deploy.IMAGE_NAMES:
            self.assertIn(f'`{image}`', text)
        self.assertEqual(deploy.TAGS_KEPT, 2)
        self.assertIn('**dos**', text)
        for name in ('images.good', 'flock', 'msvcrt.locking', 'State.Health.Log', 'failed_probe_seconds', '`--break-lock`: solo para un bloqueo de otro equipo'):
            self.assertIn(name, text)
        for stale in ('el primer intento tras un despliegue que falló y nunca sirvió su versión', 'son las que `:latest` ya tiene en todos los servicios', 'lo renombra y comprueba que sigue siendo el que leyó',
                      'Bloqueo de un proceso muerto.** Si el dueño es de este equipo'):
            self.assertNotIn(stale, text, 'a promise the code no longer keeps')
        for name in ('in_progress', 'interrupted', 'previous_run_interrupted', 'O_NOFOLLOW', 'rollback.retagged', 'rollback.recreated', '**130**', '`kill -9`', 'sha256:', 'etiqueta manual', 'did not end',
                     'no borra ni renombra nunca ningún fichero', 'contenedores Y `:latest`'):
            self.assertIn(name, text)
        for stale in ('se borra ese fichero, se toma el bloqueo sobre uno nuevo', 'el segundo `--rollback` seguido, o un despliegue que falló antes de `start` y por tanto no movió ningún contenedor',
                      'Compara la imagen de destino de cada servicio con la que **ejecuta su contenedor** (`docker inspect` de cada contenedor), no con `:latest`'):
            self.assertNotIn(stale, text, 'a promise the code no longer keeps (fix3)')
        for name in ('may still be running', 'puede no propagarse', 'unreaped_containers', 'FILE_FLAG_OPEN_REPARSE_POINT', 'un solo nombre', 'No release is recorded as good', 'cualquier fase salvo `engine`',
                     'caracteres de control escapados', 'antes de la fase `configuration`', '`kairos-deploy-<orden>-<id>`'):
            self.assertIn(name, text, 'fix4: the manual says what the script does')
        self.assertNotIn('(lo mataron o su equipo se perdió)', text, 'a certainty the message no longer claims')
        self.assertNotIn('`--rollback` sigue volviendo a la última versión buena.', text.split('Antes de repetir un despliegue que se interrumpió')[1][:300], 'no unconditional promise of a rollback')
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown), self.assertRaises(SystemExit):
            deploy.main(['--help'])
        self.assertIn('ANOTHER host', ' '.join(shown.getvalue().split()), 'the help of --break-lock says what the manual says')
        self.assertEqual((deploy.EXIT_LOCKED, deploy.EXIT_NO_PREVIOUS_IMAGES, deploy.EXIT_ALREADY_AT_PREVIOUS), (3, 4, 5))


    def test_fix4_the_docstring_and_the_plan_do_not_say_that_break_lock_removes_a_lock(self):
        """Attempt 4, gap 5: `--break-lock` only names the take-over of a FREE lock of another host; the docstring of `DeploymentLocked` and item (19) of the plan said it removes one."""
        self.assertNotIn('only `--break-lock` removes it', deploy.DeploymentLocked.__doc__)
        self.assertIn('ever broken by', deploy.DeploymentLocked.__doc__)
        plan = Path(__file__).parents[3] / 'docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md'
        if plan.exists():  # the roadmap is not part of the test image
            text = plan.read_text(encoding='utf-8')
            self.assertNotIn('que solo `--break-lock` retira', text)
            self.assertIn('ya no retira ni rompe nada', text)

    def test_fix5_the_manual_and_the_plan_say_what_engine_saves_and_when_the_running_release_is_recorded(self):
        """Attempt 5, gaps 4 and 5: in `engine` the report is not saved, except the `in_progress` of the record of the running release; the record is made after the engine check, not before any phase."""
        text = (Path(__file__).parents[3] / 'docs/operations.md').read_text(encoding='utf-8')
        self.assertIn('salvo que ya se hubiera guardado como `in_progress`', text)
        self.assertIn('no se registra nada (un aviso lo dice)', text)
        plan = Path(__file__).parents[3] / 'docs/roadmap/2026-11-15-reliable-operations/improvement-plan.md'
        if plan.exists():
            plan_text = plan.read_text(encoding='utf-8')
            self.assertNotIn('registra al empezar, antes de cualquier fase', plan_text)
            self.assertIn('registra al empezar, tras la comprobación del motor y antes de la fase `configuration`', plan_text)


if __name__ == '__main__':
    unittest.main()
