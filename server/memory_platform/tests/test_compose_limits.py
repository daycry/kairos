"""C-04 / CA-20..CA-22, CA-25: what `docker-compose.yml` declares for every service (limits, log rotation, healthchecks, `extra_hosts`), read from the YAML
and from the documentation, never from a running Docker. The deployed installation picks any of it up only at its next `up`."""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / 'docker-compose.yml'
RCLONE_OVERRIDE = ROOT / 'docker-compose.backup-rclone.yml'
CONFIGURATION = ROOT / 'docs/configuration.md'
OPERATIONS = ROOT / 'docs/operations.md'
LIMIT = re.compile(r'^\$\{(?P<name>MEMORY_[A-Z]+_(?:MEM_LIMIT|CPUS)):-(?P<default>[0-9][0-9.]*[mg]?)\}$')


def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))


def prefix(service):
    """`memory-worker` -> `MEMORY_WORKER`; `ollama` -> `MEMORY_OLLAMA`."""
    return 'MEMORY_' + service.removeprefix('memory-').upper()


class LimitTests(unittest.TestCase):
    def setUp(self):
        self.services = compose()['services']

    def test_every_service_declares_mem_limit_and_cpus_with_its_own_variable_and_a_default(self):
        for name, service in self.services.items():
            for key, suffix in (('mem_limit', 'MEM_LIMIT'), ('cpus', 'CPUS')):
                value = service.get(key)
                self.assertIsNotNone(value, f'{name} has no {key}')
                found = LIMIT.match(str(value))
                self.assertTrue(found, f'{name}.{key} = {value!r} is not ${{MEMORY_<SERVICE>_{suffix}:-default}}')
                self.assertEqual(found['name'], f'{prefix(name)}_{suffix}', name)

    def test_the_variables_are_unique_per_service(self):
        names = [LIMIT.match(str(s[k]))['name'] for s in self.services.values() for k in ('mem_limit', 'cpus')]
        self.assertEqual(len(names), len(set(names)))

    def test_the_database_and_the_worker_have_room_for_the_backfill(self):
        """A kill during the backfill would repeat it for ever: PostgreSQL builds the HNSW indexes with 256 MB per worker of `maintenance_work_mem` on top of
        its buffers and sessions, and the worker holds the vectors of the 200 fragments of one resource several times over (docs/configuration.md)."""
        def megabytes(name):
            found = re.match(r'^(\d+(?:\.\d+)?)([mg])$', LIMIT.match(str(self.services[name]['mem_limit']))['default'])
            return float(found[1])*(1024 if found[2] == 'g' else 1)
        self.assertGreaterEqual(megabytes('memory-postgres'), 2048)
        self.assertGreaterEqual(megabytes('memory-worker'), 1024)

    def test_the_documentation_lists_every_variable_with_the_default_of_the_compose_file(self):
        text = CONFIGURATION.read_text(encoding='utf-8')
        for name, service in self.services.items():
            for key in ('mem_limit', 'cpus'):
                found = LIMIT.match(str(service[key]))
                row = next((line for line in text.splitlines() if f'`{found["name"]}`' in line and line.lstrip().startswith('|')), None)
                self.assertIsNotNone(row, f'docs/configuration.md has no row for {found["name"]}')
                self.assertIn(f'`{found["default"]}`', row, f'{found["name"]}: the documented default is not {found["default"]}')


class BackupEgressTests(unittest.TestCase):
    """The scheduled copy reaches the outside only when the destination needs it (`rclone:`): with `dir:` it has no network but the database's."""

    def test_memory_backup_is_only_on_the_database_network_by_default(self):
        self.assertEqual(compose()['services']['memory-backup']['networks'], ['memory-data'])

    def test_the_rclone_override_adds_egress_and_nothing_else_to_memory_backup(self):
        self.assertTrue(RCLONE_OVERRIDE.is_file(), 'docker-compose.backup-rclone.yml is missing')
        override = yaml.safe_load(RCLONE_OVERRIDE.read_text(encoding='utf-8'))
        self.assertEqual(list(override['services']), ['memory-backup'])
        self.assertEqual(override['services']['memory-backup'], {'networks': ['egress']})
        self.assertEqual(set(override), {'services'}, 'the override declares no network, volume or secret of its own')
        self.assertIn('egress', compose()['networks'])

    def test_the_documentation_explains_the_choice(self):
        for path in (CONFIGURATION, OPERATIONS):
            self.assertIn('docker-compose.backup-rclone.yml', path.read_text(encoding='utf-8'), path.name)


class LoggingAndHostsTests(unittest.TestCase):
    def setUp(self):
        self.services = compose()['services']

    def test_every_service_rotates_its_logs(self):
        for name, service in self.services.items():
            logging = service.get('logging')
            self.assertIsNotNone(logging, f'{name} has no logging')
            self.assertEqual(logging['driver'], 'json-file', name)
            self.assertTrue(re.fullmatch(r'\d+[kmg]', str(logging['options'].get('max-size'))), f'{name}: no max-size')
            self.assertTrue(str(logging['options'].get('max-file', '')).isdigit(), f'{name}: no max-file')

    def test_ollama_reaches_host_docker_internal_on_linux_too(self):
        self.assertEqual(self.services['ollama']['extra_hosts'], ['host.docker.internal:host-gateway'])
        self.assertIn('host.docker.internal', self.services['ollama']['environment']['OLLAMA_UPSTREAM'], 'the default upstream is the one that name resolves')

    def test_only_ollama_gets_extra_hosts(self):
        self.assertEqual([n for n, s in self.services.items() if 'extra_hosts' in s], ['ollama'])

    def test_the_documentation_explains_the_linux_case(self):
        text = OPERATIONS.read_text(encoding='utf-8')
        self.assertIn('host-gateway', text)
        self.assertIn('extra_hosts', text)


class WebHealthcheckTests(unittest.TestCase):
    def test_memory_web_asks_the_proxy_for_its_own_live_route(self):
        check = compose()['services']['memory-web']['healthcheck']
        command = ' '.join(check['test'])
        self.assertIn('http://127.0.0.1:8080/health/live', command)
        self.assertTrue(check['test'][0] == 'CMD-SHELL' or check['test'][0] == 'CMD')
        for key in ('interval', 'timeout', 'retries'):
            self.assertIn(key, check)

    def test_the_route_is_served_by_the_existing_proxy_configuration(self):
        nginx = (ROOT / 'web/nginx.conf').read_text(encoding='utf-8')
        self.assertIn('location = /health/live { access_log off; return 200', nginx)
        self.assertRegex(nginx, r'listen 8080;')
