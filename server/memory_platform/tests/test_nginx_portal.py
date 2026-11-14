"""The portal's nginx configuration (T-22), checked as text (no Docker): `/memory-api/` forwards the raw URI.

`proxy_pass http://host/;` (a URI) makes nginx decode `%2F` and resolve `//` and `..` before forwarding, so a corpus named `a/../b` would reach
the API as `b`. The location now rewrites the request URI itself and passes it unchanged, as `/v1/` does. `nginx_portal_probe.py` shows the
behaviour with a real nginx and a stub; this test keeps the rules from being edited away where Docker is not available.
"""
import re
from pathlib import Path
import unittest

CONF = (Path(__file__).parents[3] / 'web' / 'nginx.conf').read_text(encoding='utf-8')


def block(header):
    start = CONF.index(header)
    opened = CONF.index('{', start)
    depth, end = 0, opened
    for end in range(opened, len(CONF)):
        depth += {'{': 1, '}': -1}.get(CONF[end], 0)
        if depth == 0:
            break
    return CONF[opened + 1:end]


class PortalNginxTests(unittest.TestCase):
    def test_memory_api_forwards_the_uri_without_normalizing_it(self):
        location = block('location /memory-api/ {')
        directives = [line.strip() for line in location.splitlines() if line.strip() and not line.strip().startswith('#')]
        self.assertEqual(directives[:4], ['rewrite ^ $request_uri;', 'rewrite ^/memory-api/(.*)$ /$1 break;', 'return 400;', 'proxy_pass http://memory_api$uri;'])
        proxy = [line for line in directives if line.startswith('proxy_pass')]
        self.assertEqual(len(proxy), 1)
        self.assertNotRegex(proxy[0], r'proxy_pass http://[^$;]+/;', 'a proxy_pass with a literal URI normalizes the path')

    def test_the_access_log_leaves_the_query_string_out(self):
        self.assertIn("log_format safe '$request_method $safe_path $status';", CONF)
        self.assertIn('map $request_uri $safe_path { ~^(?<path>[^?]*) $path;', CONF)
        self.assertNotRegex(CONF, r"log_format[^;]*\$(uri|request_uri|args|query_string)[ ';]")

    def test_the_named_group_points_at_the_api(self):
        self.assertRegex(CONF, r'upstream memory_api \{ server memory-api:8790; \}')

    def test_metrics_stays_closed_under_every_prefix_and_comes_first(self):
        self.assertRegex(CONF, r'location ~\* \^\(/memory-api\)\?/\+metrics \{ return 404; \}')
        self.assertLess(CONF.index('+metrics'), CONF.index('location /memory-api/ {'))

    def test_the_other_routes_are_unchanged(self):
        self.assertIn('proxy_pass http://memory-api:8790;', block('location /v1/ {'))  # `/mcp` goes to kairos-mcp since T-52: see test_nginx_routes
        self.assertIn('location = /health/ready { proxy_pass http://memory-api:8790/health/ready; }', CONF)
        self.assertIn('location /api/ { return 404; }', CONF)
        self.assertEqual(len(re.findall(r'proxy_pass http', CONF)), 4)


if __name__ == '__main__':
    unittest.main()
