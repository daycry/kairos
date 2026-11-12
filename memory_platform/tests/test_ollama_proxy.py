"""Ollama proxy allow-list (CA-17, S-09, P-10), checked without Docker; the live behaviour is `ollama_proxy_probe.py`.

The suite runs in a container without a Docker daemon, so these tests read the nginx template and the Compose service. The probe
(`python -m memory_platform.tests.ollama_proxy_probe`) starts the same template behind a recording stub in an isolated Compose
project and asks it for every allowed and forbidden path with raw HTTP.
"""
import re
import tempfile
import unittest
from pathlib import Path

import yaml

from memory_platform.tests import ollama_proxy_probe as probe

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'ollama-proxy' / 'default.conf.template'
COMPOSE = ROOT / 'docker-compose.yml'
DENIED_ENDPOINTS = ('generate', 'pull', 'delete', 'create', 'push', 'copy', 'tags', 'show')


def template_text():
    return TEMPLATE.read_text(encoding='utf-8')


def directives(text):
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))


def locations(text):
    """{modifier+path: body} of the `location` blocks of the template (they do not nest; `if` and `limit_except` do)."""
    found = {}
    for match in re.finditer(r'location\s+(=\s+)?(\S+)\s*\{', text):
        depth, index = 1, match.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(text[index], 0)
            index += 1
        found[('= ' if match.group(1) else '') + match.group(2)] = text[match.end():index - 1]
    return found


class TemplateTests(unittest.TestCase):
    def test_only_embed_version_and_guarded_chat_reach_the_upstream(self):
        blocks = locations(directives(template_text()))
        self.assertEqual(set(blocks), {'= /api/embed', '= /api/version', '= /api/chat', '/'})
        for path, body in blocks.items():
            self.assertEqual('proxy_pass' in body, path != '/', path)

    def test_the_catch_all_answers_403_and_never_proxies(self):
        body = locations(directives(template_text()))['/']
        self.assertIn('return 403', body)
        self.assertNotIn('proxy_pass', body)

    def test_each_allowed_location_proxies_its_own_constant_path(self):
        """The upstream gets the path written in the template, whatever the client sent (`//`, `..`, `%2e`)."""
        for path, body in locations(directives(template_text())).items():
            if path != '/':
                self.assertIn('proxy_pass http://${OLLAMA_UPSTREAM}' + path.removeprefix('= ') + ';', body, path)

    def test_no_proxy_pass_forwards_the_request_uri(self):
        text = directives(template_text())
        self.assertNotRegex(text, r'proxy_pass\s+http://\$\{OLLAMA_UPSTREAM\}\s*;')
        self.assertNotRegex(text, r'proxy_pass[^;]*\$(request_uri|uri|1)')

    def test_chat_is_denied_unless_the_operator_sets_the_flag_to_exactly_1(self):
        text = directives(template_text())
        mapping = re.search(r'map\s+"\$\{OLLAMA_ALLOW_CHAT\}"\s+\$kairos_chat_denied\s*\{(.*?)\}', text, re.S).group(1)
        self.assertRegex(mapping, r'default\s+1;')
        self.assertRegex(mapping, r'"1"\s+0;')
        self.assertIn('if ($kairos_chat_denied) { return 403; }', locations(text)['= /api/chat'])

    def test_generate_pull_delete_and_the_rest_have_no_directive_of_their_own(self):
        text = directives(template_text())
        for name in DENIED_ENDPOINTS:
            self.assertNotIn('/api/' + name, text, name)

    def test_methods_are_limited_and_the_template_has_no_unrendered_placeholder(self):
        blocks = locations(directives(template_text()))
        self.assertIn('limit_except POST', blocks['= /api/embed'])
        self.assertIn('limit_except GET', blocks['= /api/version'])
        rendered = directives(template_text()).replace('${OLLAMA_UPSTREAM}', 'stub:11434').replace('${OLLAMA_ALLOW_CHAT}', '0')
        self.assertNotIn('${', rendered)

    def test_the_host_header_is_still_rewritten_for_a_loopback_ollama(self):
        self.assertIn('proxy_set_header Host localhost;', template_text())


class ComposeServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))['services']['ollama']

    def test_the_flag_defaults_to_off_and_the_service_publishes_nothing(self):
        self.assertEqual(self.service['environment']['OLLAMA_ALLOW_CHAT'], '${OLLAMA_ALLOW_CHAT:-0}')
        self.assertNotIn('ports', self.service)

    def test_the_proxy_runs_without_root_and_without_capabilities(self):
        self.assertEqual(self.service['user'], '101:101')
        self.assertIs(self.service['read_only'], True)
        self.assertEqual(self.service['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges:true', self.service['security_opt'])
        writable = {entry.split(':')[0] for entry in self.service['tmpfs']}
        self.assertEqual(writable, {'/etc/nginx/conf.d', '/run', '/var/cache/nginx', '/tmp'})
        self.assertTrue(all('uid=101' in entry for entry in self.service['tmpfs'] if not entry.startswith('/tmp')))

    def test_the_listening_port_is_unprivileged(self):
        self.assertRegex(template_text(), r'listen\s+11434;')


class ProbeIsolationTests(unittest.TestCase):
    """The probe may only ever run in a Compose project of its own."""

    def test_project_names(self):
        self.assertEqual(probe.project_name('kairos-proxy-t13'), 'kairos-proxy-t13')
        for name in ('knowledge-graphs', 'knowledge-graphs-two', 'kairos-proxy-knowledge-graphs', 'kairos-rehearsal', 'KAIROS-PROXY-X', '', 'kairos-proxy-' + 'a' * 40):
            with self.assertRaises(ValueError, msg=name):
                probe.project_name(name)

    def test_override_renames_every_fixed_name_resource_of_the_compose_file(self):
        base = yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as secrets:
            override = probe.override('kairos-proxy-t13', secrets)
        for kind in ('networks', 'volumes'):
            for key, value in base[kind].items():
                if isinstance(value, dict) and 'name' in value:
                    self.assertTrue(override[kind][key]['name'].startswith('kairos-proxy-t13_'), (kind, key))
        self.assertNotIn('knowledge-graphs', str(override))
        self.assertEqual(override['services']['ollama']['environment']['OLLAMA_UPSTREAM'], 'stub:11434')

    def test_the_probe_starts_only_the_proxy_and_its_stub(self):
        source = Path(probe.__file__).read_text(encoding='utf-8')
        self.assertIn("'up', '-d', '--force-recreate', '--wait', 'ollama', 'stub'", source)


if __name__ == '__main__':
    unittest.main()
