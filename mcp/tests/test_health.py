"""T-36: the kairos-mcp skeleton answers its liveness probe and carries nothing of the server (CA-08, CA-09)."""
from pathlib import Path
import re
import unittest

from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = 'memory' + '_platform'  # split on purpose: this very file must not match the scan below


class HealthTests(unittest.TestCase):
    def test_liveness_answers_200_without_any_credential_or_upstream(self):
        from kairos_mcp.app import create_app
        with TestClient(create_app(api_url='http://127.0.0.1:9')) as client:  # nothing listens there: liveness never calls /v1
            response = client.get('/health/live')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'live'})

    def test_the_version_is_0_4_1_in_the_file_and_in_the_package(self):
        import kairos_mcp
        self.assertEqual((ROOT / 'VERSION').read_text(encoding='utf-8').strip(), '0.4.1')
        self.assertEqual(kairos_mcp.__version__, '0.4.1')


class IsolationTests(unittest.TestCase):
    """CA-08: the component does not reach the database nor import server code."""

    def test_requirements_carry_no_database_driver(self):
        text = (ROOT / 'requirements.txt').read_text(encoding='utf-8').lower()
        self.assertNotIn('psycopg', text)
        self.assertNotIn('asyncpg', text)
        self.assertIn('mcp==', text)
        self.assertIn('httpx==', text)

    def test_the_dockerfile_has_no_dsn_secret_or_server_code_and_drops_privileges(self):
        text = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'MEMORY_DSN|MEMORY_TEST_DSN|secret', text, re.I))
        self.assertNotIn(SERVER_PACKAGE, text)
        self.assertRegex(text, r'(?m)^USER 10001:10001$')

    def test_no_source_file_imports_or_mentions_the_server_package(self):
        offenders = [str(path.relative_to(ROOT)) for path in ROOT.rglob('*.py') if SERVER_PACKAGE in path.read_text(encoding='utf-8')]
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
