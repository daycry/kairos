"""C-01 / CA-06, CA-08: the optional Compose service `memory-backup` (profile `backup`) runs `backup-cycle` and no service mounts a private key."""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / 'docker-compose.yml'
DOCKERFILE = ROOT / 'server/memory_platform/Dockerfile'
# What names a private key or its holder: a volume, a variable value, a secret or a file of any service that matches is a key on a server (P-01).
PRIVATE_KEY = re.compile(r'identit|private|secret[-_ ]?key|age[-_]?key|\.key\b|keygen|id_rsa|id_ed25519|AGE-SECRET', re.I)


def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))


def key_references(document):
    """(service, what) for every volume, environment value, secret reference and secret file of `document` that looks like a private key."""
    found = []
    for name, service in document['services'].items():
        for volume in service.get('volumes') or []:
            text = volume if isinstance(volume, str) else ' '.join(str(v) for v in volume.values())
            if PRIVATE_KEY.search(text):
                found.append((name, text))
        environment = service.get('environment') or {}
        for key, value in (environment.items() if isinstance(environment, dict) else (e.partition('=')[::2] for e in environment)):
            if PRIVATE_KEY.search(str(key)) or PRIVATE_KEY.search(str(value)):
                found.append((name, f'{key}={value}'))
        for secret in service.get('secrets') or []:
            reference = secret if isinstance(secret, str) else secret.get('source', '')
            declared = (document.get('secrets') or {}).get(reference) or {}
            if PRIVATE_KEY.search(reference) or PRIVATE_KEY.search(str(declared.get('file', ''))):
                found.append((name, 'secret ' + reference))
    for name, declared in (document.get('secrets') or {}).items():
        if PRIVATE_KEY.search(name) or PRIVATE_KEY.search(str(declared.get('file', ''))):
            found.append(('secrets', name))
    return found


class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.document = compose()
        self.service = self.document['services']['memory-backup']

    def test_the_service_is_optional_has_no_ports_and_runs_the_cycle_in_a_loop(self):
        self.assertEqual(self.service['profiles'], ['backup'], 'only the profile `backup` starts it: `memory` and `memory-admin` never do')
        self.assertNotIn('ports', self.service)
        self.assertEqual(self.service['image'], 'kairos-operator:latest')
        self.assertEqual(self.service['build']['target'], 'operator')
        self.assertEqual(self.service['entrypoint'], ['python', '-m', 'memory_platform.admin'])
        self.assertEqual(self.service['command'], ['backup-cycle', '--loop'])
        self.assertEqual(self.service['secrets'], ['memory_dsn'], 'the database credential and nothing else')
        self.assertTrue(self.service['read_only'])
        self.assertEqual(self.service['cap_drop'], ['ALL'])
        self.assertTrue(self.service['init'], 'python is not PID 1: a stop reaches the cycle as SIGTERM')

    def test_the_settings_have_the_documented_defaults(self):
        environment = self.service['environment']
        self.assertEqual(environment['MEMORY_BACKUP_INTERVAL'], '${MEMORY_BACKUP_INTERVAL:-24h}')
        self.assertEqual(environment['MEMORY_BACKUP_DESTINATION'], '${MEMORY_BACKUP_DESTINATION:-}', 'no destination by default: the service refuses to run until one is set')
        self.assertEqual(environment['MEMORY_BACKUP_REQUIRE_ENCRYPTION'], '${MEMORY_BACKUP_REQUIRE_ENCRYPTION:-1}')
        self.assertEqual(environment['MEMORY_BACKUP_REMOTE_KEEP'], '${MEMORY_BACKUP_REMOTE_KEEP:-30}')
        self.assertEqual(environment['MEMORY_BACKUP_KEEP'], '${MEMORY_BACKUP_KEEP:-7}')
        self.assertEqual(environment['MEMORY_DSN_FILE'], '/run/secrets/memory_dsn')

    def test_it_reaches_the_database_and_the_outside_and_mounts_only_the_copies_the_public_recipients_and_the_destination(self):
        self.assertEqual(sorted(self.service['networks']), ['egress', 'memory-data'])
        targets = sorted(re.search(r':(/\w+)(?::\w+)?$', v).group(1) for v in self.service['volumes'])
        self.assertEqual(targets, ['/backups', '/config', '/offsite'])
        config_mount = next(v for v in self.service['volumes'] if ':/config' in v)
        self.assertTrue(config_mount.endswith(':ro'), 'recipients and the rclone configuration are read, never written')
        self.assertFalse([v for v in self.service['volumes'] if 'ollama-proxy' in v or 'web/' in v], 'the files the installed project mounts are not this service\'s')

    def test_no_service_mounts_or_names_a_private_key(self):
        self.assertEqual(key_references(self.document), [])
        for service in self.document['services'].values():
            self.assertFalse([v for v in service.get('volumes') or [] if re.search(r'\bage\b', str(v))], 'no `age` directory or identity is mounted')

    def test_the_key_detector_does_see_a_key_when_there_is_one(self):
        """Mutant control: the same document with a private key mounted, a variable pointing at it and a secret for it."""
        document = compose()
        document['services']['memory-backup']['volumes'].append('./keys/age-identity.txt:/keys/identity.txt:ro')
        found = key_references(document)
        self.assertEqual([name for name, what in found if name == 'memory-backup'], ['memory-backup'])
        for change in ({'environment': {'AGE_IDENTITY_FILE': '/run/secrets/x'}}, {'environment': {'X': '/keys/backup.key'}}, {'secrets': ['memory_dsn', 'age_private']}):
            document = compose()
            document['secrets']['age_private'] = {'file': './secrets/age_private'}
            document['services']['memory-backup'].update(change)
            self.assertTrue(key_references(document), change)
        document = compose()
        document['secrets']['backup_key'] = {'file': './secrets/backup.key'}
        self.assertTrue(key_references(document))

    def test_the_operator_image_pins_rclone_by_version_and_the_service_adds_no_key_to_any_stage(self):
        text = DOCKERFILE.read_text(encoding='utf-8')
        operator = text.split('FROM api AS operator', 1)[1].split('FROM api AS worker', 1)[0]
        test = text.split('FROM postgres-pgvector AS test', 1)[1].split('FROM test AS live-probe', 1)[0]
        for stage in (operator, test):
            self.assertRegex(stage, r'ARG RCLONE_VERSION=\d[\w.+~:-]*')
            self.assertIn('rclone=${RCLONE_VERSION}', stage)
        self.assertNotRegex(operator, r'(?i)age-keygen|identity|COPY .*\.key', 'the image of the service carries `age` to encrypt and no way to decrypt')
