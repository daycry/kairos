"""Structure of .github/workflows/ci.yml, checked as text so the test needs no YAML library (CA-01)."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'ci.yml'


def read():
    return WORKFLOW.read_text(encoding='utf-8')


def triggers(text):
    """Keys of the top-level `on:` block."""
    match = re.search(r'^on:\s*\n((?:[ \t]+.*\n|\s*\n)+)', text, re.M)
    return set(re.findall(r'^  ([a-z_]+):', match.group(1), re.M)) if match else set()


def jobs(text):
    """Mapping job id -> its block of text under `jobs:`."""
    match = re.search(r'^jobs:\s*\n((?:[ \t]+.*\n|\s*\n)+)', text, re.M)
    body = match.group(1) if match else ''
    parts = re.split(r'^  ([A-Za-z0-9_-]+):\s*$', body, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


PUBLISHING = (r'docker\s+(?:buildx\s+)?push\b', r'\b(?:npm|yarn|pnpm)\s+publish\b', r'\bpush:\s*true\b', r'--push\b')
DEPLOYED = r'knowledge-graphs[-_]'


def hygiene_violations(text):
    """What a workflow text does that CA-02/CA-30 forbid: foreign secrets, publishing, deployed-installation resources."""
    found = []
    for name in re.findall(r'\bsecrets\.([A-Za-z0-9_]+)', text):
        if name != 'GITHUB_TOKEN':
            found.append('secret ' + name)
    if re.search(r'\bsecrets\s*\[', text):
        found.append('secret by index')
    if re.search(r'\bsecrets:\s*inherit\b', text):
        found.append('secrets: inherit')
    for pattern in PUBLISHING:
        if re.search(pattern, text):
            found.append('publishing: ' + pattern)
    if re.search(DEPLOYED, text):
        found.append('deployed installation resource')
    return found


class WorkflowStructureTests(unittest.TestCase):
    def setUp(self):
        self.text = read()
        self.jobs = jobs(self.text)

    def test_triggers_are_pull_request_manual_and_pushes_to_branches_other_than_main(self):
        self.assertEqual(triggers(self.text), {'pull_request', 'push', 'workflow_dispatch'})
        push = re.search(r'^  push:\s*\n((?:    .*\n)+)', self.text, re.M).group(1)
        self.assertRegex(push, r'branches-ignore:\s*\n\s*- main\s*$')
        self.assertNotIn('branches:', push)

    def test_server_job_builds_the_test_target_on_linux(self):
        self.assertIn('server', self.jobs)
        block = self.jobs['server']
        self.assertRegex(block, r'runs-on:\s*ubuntu-latest')
        self.assertIn('docker build --target test -f memory_platform/Dockerfile', block)

    def test_the_suite_is_never_replayed_from_an_imported_cache(self):
        # Observed in CI (run 43202142933): with --cache-from the last RUN of the test stage was CACHED even with
        # --no-cache-filter, so the suite did not run. The test image is built from the Dockerfile on a clean runner.
        for forbidden in ('actions/cache@', '--cache-from', '--cache-to', 'type=local'):
            self.assertNotIn(forbidden, self.text)
        self.assertNotIn('build-push-action', self.text)


class AuxiliaryJobsTests(unittest.TestCase):
    def setUp(self):
        self.text = read()
        self.jobs = jobs(self.text)

    def test_every_job_is_on_linux_with_an_explicit_timeout(self):
        for name, block in self.jobs.items():
            with self.subTest(job=name):
                self.assertRegex(block, r'runs-on:\s*ubuntu-latest')
                self.assertRegex(block, r'timeout-minutes:\s*\d+')

    def test_retrieval_eval_job_builds_the_offline_gate_target(self):
        self.assertIn('retrieval-eval', self.jobs)
        block = self.jobs['retrieval-eval']
        self.assertIn('docker build --target retrieval-eval -f memory_platform/Dockerfile', block)
        self.assertNotIn('MEMORY_LLM', block)  # simulated provider only: no model, no external service
        # The gate really ran and passed: its report line is read back from the build log.
        self.assertIn('RETRIEVAL_EVAL_RESULT', block)
        self.assertIn('"passed": true', block)

    def test_client_job_runs_tests_and_release_check_in_the_package(self):
        self.assertIn('client', self.jobs)
        block = self.jobs['client']
        self.assertIn('working-directory: packages/kairos-cli', block)
        self.assertIn('npm test', block)
        self.assertIn('npm run release:check', block)

    def test_web_job_runs_typecheck_test_build_and_the_web_image_test_target(self):
        self.assertIn('web', self.jobs)
        block = self.jobs['web']
        self.assertIn('working-directory: web', block)
        for command in ('npm ci', 'npm run typecheck', 'npm test', 'npm run build'):
            self.assertIn(command, block)
        self.assertIn('docker build --target test -f memory_platform/Dockerfile.web', block)


class PipeFailureTests(unittest.TestCase):
    """A piped build must fail the step: GitHub's default `bash -e` has no pipefail, so `docker build | tee` would stay green."""

    def test_default_shell_is_bash_with_pipefail(self):
        self.assertRegex(read(), r'(?m)^defaults:\s*\n  run:\s*\n    shell: bash\s*$')

    def test_every_step_that_pipes_a_build_sets_pipefail_explicitly(self):
        steps = re.split(r'(?m)^      - (?=name:|uses:)', read())
        piped = [step for step in steps if re.search(r'\|\s*tee\b', step)]
        self.assertTrue(piped)
        for step in piped:
            with self.subTest(step=step.splitlines()[0]):
                self.assertIn('set -euo pipefail', step)


class ContractsJobTests(unittest.TestCase):
    def setUp(self):
        self.jobs = jobs(read())

    def test_contracts_job_checks_additivity_and_the_exported_files(self):
        self.assertIn('contracts', self.jobs)
        block = self.jobs['contracts']
        self.assertIn('python -m unittest memory_platform.tests.test_contract_additive', block)
        self.assertIn('python scripts/export-contracts.py', block)
        # The committed contracts are CRLF and were written by Python 3.13 (docstring indentation): same interpreter, CR ignored.
        self.assertIn('git diff --ignore-cr-at-eol --exit-code -- docs/contracts', block)
        self.assertRegex(block, r"python-version:\s*'?3\.13")

    def test_contracts_job_needs_no_service_or_network_beyond_dependencies(self):
        block = self.jobs['contracts']
        for forbidden in ('docker compose', 'curl ', 'MEMORY_DSN', 'MEMORY_TEST_DSN'):
            self.assertNotIn(forbidden, block)


class HygieneTests(unittest.TestCase):
    """CA-02/CA-30: only GITHUB_TOKEN, nothing published, no deployed-installation resources."""

    def test_current_workflow_is_clean(self):
        self.assertEqual(hygiene_violations(read()), [])

    def test_a_workflow_with_only_github_token_is_clean(self):
        self.assertEqual(hygiene_violations('env:\n  T: ${{ secrets.GITHUB_TOKEN }}\n  U: ${{secrets.GITHUB_TOKEN}}\n'), [])

    def test_another_secret_is_rejected(self):
        self.assertTrue(hygiene_violations('env:\n  T: ${{ secrets.REGISTRY_PASSWORD }}\n'))
        self.assertTrue(hygiene_violations("env:\n  T: ${{ secrets['NPM_TOKEN'] }}\n"))
        self.assertTrue(hygiene_violations('secrets: inherit\n'))

    def test_publishing_is_rejected(self):
        for text in ('run: docker push ghcr.io/x/y\n', 'run: npm publish\n', 'with:\n  push: true\n',
                     'run: docker buildx build --push .\n', 'run: npm  publish --dry-run\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))

    def test_deployed_installation_resources_are_rejected(self):
        for text in ('run: docker exec knowledge-graphs-memory-api-1 ls\n', 'run: docker volume rm knowledge-graphs_pgdata\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))


if __name__ == '__main__':
    unittest.main()
