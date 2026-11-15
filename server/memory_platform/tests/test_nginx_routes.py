"""T-52 (CA-27, CA-28, P-07): the proxy routes `/mcp` to kairos-mcp (`memory-mcp:8791`) and Compose orders and connects the services for it.

Checked as text, without Docker; `nginx -t` runs in the `test` target of `web/Dockerfile`. The internal MCP stays reachable at `memory-api:8790/mcp` for
the compatibility version and, through the generic `/memory-api/` prefix of the proxy, at `/memory-api/mcp/` while `MEMORY_MOUNT_MCP=1`.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
CONF = (ROOT / 'web' / 'nginx.conf').read_text(encoding='utf-8')
WEB = (ROOT / 'web' / 'Dockerfile').read_text(encoding='utf-8')


def block(header, text=CONF):
    start = text.index(header)
    opened = text.index('{', start)
    depth, end = 0, opened
    for end in range(opened, len(text)):
        depth += {'{': 1, '}': -1}.get(text[end], 0)
        if depth == 0:
            break
    return text[opened + 1:end]


def directives(location):
    return [line.strip() for line in location.splitlines() if line.strip() and not line.strip().startswith('#')]


class McpRouteTests(unittest.TestCase):
    def test_mcp_goes_to_kairos_mcp_not_to_the_api(self):
        mcp = directives(block('location /mcp {'))
        self.assertIn('proxy_pass http://memory-mcp:8791;', mcp)
        self.assertFalse([line for line in mcp if '8790' in line or 'memory-api' in line])

    def test_mcp_keeps_its_timeouts_buffers_and_host(self):
        mcp = directives(block('location /mcp {'))
        for line in ('proxy_set_header Host $http_host;', 'proxy_read_timeout 45s;', 'proxy_buffering off;'):
            self.assertIn(line, mcp)

    def test_the_portal_session_cookie_is_not_forwarded_to_kairos_mcp(self):
        self.assertIn('proxy_set_header Cookie "";', directives(block('location /mcp {')))

    def test_the_rest_of_the_routes_still_reach_the_api(self):
        self.assertIn('proxy_pass http://memory-api:8790;', directives(block('location /v1/ {')))
        self.assertIn('upstream memory_api { server memory-api:8790; }', CONF)

    def test_the_test_target_replaces_both_upstreams_for_nginx_t(self):
        self.assertIn('memory-api:8790/127.0.0.1:8790', WEB)
        self.assertIn('memory-mcp:8791/127.0.0.1:8791', WEB)


class ComposeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml
        cls.compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
        cls.web = cls.compose['services']['memory-web']

    def test_web_waits_for_kairos_mcp_and_the_api(self):
        self.assertEqual(self.web['depends_on']['memory-mcp']['condition'], 'service_healthy')
        self.assertEqual(self.web['depends_on']['memory-api']['condition'], 'service_healthy')

    def test_web_reaches_kairos_mcp_over_the_internal_network_and_keeps_its_own(self):
        self.assertEqual(list(self.web['networks']), ['webui', 'mcp'])
        self.assertIs(self.compose['networks']['mcp']['internal'], True)
        self.assertNotIn('ports', self.compose['services']['memory-mcp'])  # still not published: the proxy is the only way in

    def test_the_published_port_of_the_proxy_is_unchanged(self):
        self.assertEqual(self.web['ports'], ['127.0.0.1:5173:8080'])
