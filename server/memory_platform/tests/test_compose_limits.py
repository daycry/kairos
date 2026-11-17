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


def mebibytes(size):
    found = re.fullmatch(r'(\d+(?:\.\d+)?)([mg])', size)
    return float(found[1])*(1024 if found[2] == 'g' else 1)


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

    def test_no_default_cpus_can_stop_the_stack_from_starting_on_a_one_vcpu_host(self):
        """Docker refuses a container whose `cpus` is above the CPUs of the host (`NanoCPUs > NumCPU`): the defaults are 0 (no quota) or at most 1."""
        for name, service in self.services.items():
            default = float(LIMIT.match(str(service['cpus']))['default'])
            self.assertTrue(default == 0 or default <= 1, f'{name}: cpus default {default} may not start on a host with one CPU')

    def test_memory_api_has_room_for_its_largest_answers(self):
        """One answer of 200 observations of ~300 KB (`context` repeats the content) is a ~120 MB JSON and a ~360 MB peak while it is rendered (tracemalloc); the base is
        ~100 MB. The pool does not bound the answers held in memory (the connection is released before the answer is built), so the floor is a count of answers, not the pool."""
        text = CONFIGURATION.read_text(encoding='utf-8')
        row = next(l for l in text.splitlines() if l.startswith('| `MEMORY_API_MEM_LIMIT`'))
        default, vps = [c.strip().strip('`') for c in row.split('|')[2:4]]
        self.assertEqual(default, '2g')
        base, peak, held = 100, 360, 120
        self.assertGreaterEqual(mebibytes(LIMIT.match(self.services['memory-api']['mem_limit'])['default']), base+peak+13*held, 'one answer rendering and 13 held at once (~14)')
        self.assertGreaterEqual(mebibytes(vps), base+peak+4*held, 'one answer rendering and 4 held at once (~5)')
        section = text.split('**Memoria de `memory-api`.**', 1)[1].split(chr(10)+chr(10), 1)[0]
        self.assertIn('no acota', section, 'the pool does not bound the answers in memory')
        self.assertNotIn('puede bajar con él', section, 'the false advice: a smaller pool does not allow a smaller limit')

    def test_the_documentation_says_that_the_limits_are_caps_and_not_reservations_and_what_to_do_in_four_gigabytes(self):
        text = CONFIGURATION.read_text(encoding='utf-8')
        section = text.split('**Los límites son topes, no reservas.**', 1)[1].split(chr(10)+chr(10), 1)[0]
        self.assertIn('swap', section)
        self.assertIn('4,25 GB', section)

    def test_the_vps_column_asks_for_no_more_cpus_than_the_vps_has_and_memory_mcp_gets_a_whole_one(self):
        rows = {m['name']: m['vps'].strip().strip('`') for m in (re.match(r'\| `(?P<name>MEMORY_[A-Z]+_CPUS)` \| `[^`]*` \| (?P<vps>[^|]*)\|', l) for l in CONFIGURATION.read_text(encoding='utf-8').splitlines()) if m}
        self.assertEqual(len(rows), 11, 'one per service')
        for name, value in rows.items():
            self.assertLessEqual(float(value), 2, f'{name}: the VPS column assumes 2 vCPU')
        self.assertGreaterEqual(float(rows['MEMORY_MCP_CPUS']), 1, 'memory-mcp reserializes up to 64 MiB in its event loop: half a CPU doubles the stall')

    def test_the_documentation_warns_that_cpus_above_the_host_make_docker_refuse_the_container(self):
        text = CONFIGURATION.read_text(encoding='utf-8')
        self.assertRegex(text, r'(?s)`cpus`[^.]*(mayor|superior|por encima)[^.]*(CPU|núcleos)[^.]*(rechaza|no arranca)')

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

    def test_the_documentation_does_not_claim_that_listening_on_a_gateway_protects_ollama(self):
        """An Ollama without authentication is reachable from every bridge network through the INPUT chain of the host, whatever host IP it listens on (`host-gateway` is the
        gateway of docker0, not of `egress`, and DOCKER-USER only filters FORWARD): `/api/pull` and `/api/delete` would skip the allow list of the proxy. The manual must give
        the INPUT rule (iptables and ufw) that admits only loopback and the subnet of `egress`, how to read that subnet and that it must be persisted and re-applied."""
        text = OPERATIONS.read_text(encoding='utf-8')
        section = text.split('**Linux (el VPS).**', 1)[1].split(chr(10)+chr(10), 1)[0]
        self.assertNotIn('OLLAMA_HOST=0.0.0.0', section)
        self.assertNotIn('Haz que escuche solo en la IP de la pasarela', section)
        self.assertNotIn('pasarela de `egress` (la que usa `host-gateway`)', section)
        self.assertIn('`INPUT`', section)
        self.assertIn('DOCKER-USER', section)
        self.assertIn('FORWARD', section)
        self.assertIn('iptables -I INPUT', section)
        self.assertIn('--dport 11434', section)
        self.assertIn('ufw allow from', section)
        self.assertIn('ufw deny 11434', section)
        self.assertIn('docker network inspect <proyecto>_egress', section)
        self.assertIn("(index .IPAM.Config 0).Subnet", section)
        self.assertIn('netfilter-persistent', section)
        self.assertIn('otra subred', section)
        self.assertIn('/api/pull', section)
        self.assertIn('/api/delete', section)


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


def healthcheck_section():
    text = OPERATIONS.read_text(encoding='utf-8')
    return text.split('## Healthchecks de los servicios', 1)[1].split(chr(10) + '## ', 1)[0]


class DocumentedHealthchecksTests(unittest.TestCase):
    def test_the_table_of_docs_operations_repeats_every_healthcheck_of_the_compose_file(self):
        rows = {m['name']: m['rest'] for m in (re.match(r'\| `(?P<name>[\w-]+)` \|(?P<rest>.*)', line) for line in healthcheck_section().splitlines()) if m}
        checked = 0
        for name, service in compose()['services'].items():
            check = service.get('healthcheck')
            if not check:
                continue
            checked += 1
            self.assertIn(name, rows, f'docs/operations.md has no row for {name}')
            cells = [c.strip() for c in rows[name].split('|')]
            self.assertIn(str(check['interval']).replace('s', ' s'), cells[1:], (name, 'interval'))
            self.assertIn(str(check['timeout']).replace('s', ' s'), cells[1:], (name, 'timeout'))
            self.assertIn(str(check['retries']), cells[1:], (name, 'retries'))
        self.assertEqual(checked, 6, 'ollama, memory-postgres, memory-api, memory-mcp, memory-web and memory-worker')

    def test_the_unhealthy_time_is_interval_times_retries(self):
        for name, service in compose()['services'].items():
            check = service.get('healthcheck')
            if check:
                seconds = int(check['interval'].rstrip('s'))*check['retries']
                line = next(l for l in healthcheck_section().splitlines() if l.startswith(f'| `{name}` |'))
                self.assertIn(f'{seconds} s', line, name)
