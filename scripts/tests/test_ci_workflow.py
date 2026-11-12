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


PUBLISHING = (r'docker\s+(?:buildx\s+)?push\b', r'\b(?:npm|yarn|pnpm)\s+publish\b', r'\bpush:\s*true\b', r'--push\b',
              r'\bgh\s+release\b', r'\btwine\s+upload\b')
DEPLOYED = r'knowledge-graphs[-_]'
# Evasions of the gate: weakening a failure into a pass, or reaching the runner host.
WEAKENING = {'continue-on-error: true': r'continue-on-error:\s*[\'"]?true', '|| true': r'\|\|\s*true\b', 'if: false': r'\bif:\s*[\'"]?false\b'}
HOST_ACCESS = {'--privileged': r'--privileged\b', 'docker.sock': r'docker\.sock'}


def run_blocks(text):
    """Bodies of every `run:` (inline or block scalar)."""
    blocks = []
    lines = text.splitlines()
    for number, line in enumerate(lines):
        match = re.match(r'^(\s*)(?:- )?run:\s*(.*)$', line)
        if not match:
            continue
        indent, rest = len(match.group(1)), match.group(2)
        if rest and not rest.startswith(('|', '>')):
            blocks.append(rest)
            continue
        body = []
        for following in lines[number + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent + 1:
                break
            body.append(following)
        blocks.append('\n'.join(body))
    return blocks


def permission_violations(text):
    """`permissions:` may only grant `contents: read`, at workflow level or in a job."""
    found = []
    lines = text.splitlines()
    for number, line in enumerate(lines):
        match = re.match(r'^(\s*)permissions:\s*(.*)$', line)
        if not match:
            continue
        indent, inline = len(match.group(1)), match.group(2).strip()
        if inline:
            found.append('permissions: ' + inline)
            continue
        for following in lines[number + 1:]:
            if not following.strip():
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            if following.strip() != 'contents: read':
                found.append('permissions: ' + following.strip())
    return found


def hygiene_violations(text):
    """What a workflow text does that CA-02/CA-30 forbid: foreign secrets, publishing, deployed-installation resources,
    wider token permissions, event data in scripts, host access and failures turned into passes."""
    found = []
    for name in re.findall(r'\bsecrets\.([A-Za-z0-9_]+)', text):
        if name != 'GITHUB_TOKEN':
            found.append('secret ' + name)
    if re.search(r'\bsecrets\s*\[', text):
        found.append('secret by index')
    if re.search(r'\bsecrets:\s*inherit\b', text):
        found.append('secrets: inherit')
    if re.search(r'\btoJSON\(\s*secrets\s*\)', text):
        found.append('toJSON(secrets)')
    for pattern in PUBLISHING:
        if re.search(pattern, text):
            found.append('publishing: ' + pattern)
    if re.search(DEPLOYED, text):
        found.append('deployed installation resource')
    found.extend(permission_violations(text))
    for body in run_blocks(text):
        if re.search(r'\$\{\{\s*github\.event\.', body):
            found.append('github.event data inside run:')
    for label, pattern in {**HOST_ACCESS, **WEAKENING}.items():
        if re.search(pattern, text):
            found.append(label)
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

    def test_contracts_job_fails_on_untracked_or_deleted_contract_files(self):
        # `git diff` does not see a new, untracked contract or a deleted one: the step also reads `git status` for `??` and `D`.
        block = self.jobs['contracts']
        self.assertIn('--untracked-files=all', block)
        self.assertRegex(block, r'git status --porcelain[^\n]*-- docs/contracts')
        self.assertIn("grep -E '^(\\?\\?|.D|D.)'", block)

    def test_the_initiative_base_step_names_the_base_it_really_compares_with(self):
        block = self.jobs['contracts']
        self.assertNotIn('initiative base', block)
        self.assertIn('memory_platform/tests/contracts_base', block)  # T-26 reassigns this base

    def test_contracts_job_needs_no_service_or_network_beyond_dependencies(self):
        block = self.jobs['contracts']
        for forbidden in ('docker compose', 'curl ', 'MEMORY_DSN', 'MEMORY_TEST_DSN'):
            self.assertNotIn(forbidden, block)


class SuiteGateStepTests(unittest.TestCase):
    """The step that reads MEMORY_TEST_RESULT back is what makes `server` fail on skipped or missing tests: it is protected here."""
    STEP = 'The suite really ran and nothing was skipped'

    def step(self, text):
        match = re.search(r'(?m)^      - name: ' + self.STEP + r'\s*\n((?:        .*\n|\s*\n)+)', text)
        return match.group(1) if match else ''

    def violations(self, text):
        step = self.step(text)
        if not step:
            return ['step missing']
        found = [key + ' not required to be 0' for key in ('failures', 'errors', 'skipped') if ('grep -q \'"' + key + '": 0\'') not in step]
        if 'grep -q \'"passed": true\'' not in step:
            found.append('passed not required')
        if 'KAIROS_MIN_TESTS' not in step or '"tests"' not in step:
            found.append('tests not compared with the minimum')
        return found

    def test_current_step_is_complete(self):
        self.assertEqual(self.violations(read()), [])

    def test_the_step_belongs_to_the_server_job(self):
        self.assertIn(self.STEP, jobs(read())['server'])

    def test_deleting_the_step_is_detected(self):
        mutant = re.sub(r'(?s)      - name: ' + self.STEP + r'.*?(?=\n  retrieval-eval:)', '', read())
        self.assertNotEqual(mutant, read())
        self.assertEqual(self.violations(mutant), ['step missing'])

    def test_weakening_a_counter_is_detected(self):
        for key in ('failures', 'errors', 'skipped'):
            with self.subTest(key=key):
                mutant = read().replace('"' + key + '": 0', '"' + key + '"')
                self.assertNotEqual(mutant, read())
                self.assertTrue(self.violations(mutant))
        self.assertTrue(self.violations(read().replace('"passed": true', '"passed"')))

    def test_dropping_the_minimum_comparison_is_detected(self):
        mutant = read().replace('KAIROS_MIN_TESTS', 'KAIROS_X')
        self.assertTrue(self.violations(mutant))

    def test_minimum_has_one_documented_source_at_the_baseline(self):
        text = read()
        declared = re.findall(r"(?m)^  KAIROS_MIN_TESTS:\s*'?(\d+)'?", text)
        self.assertEqual(len(declared), 1)
        self.assertGreaterEqual(int(declared[0]), 483)  # baseline of T-01; raise it when the suite grows, never lower it
        comment = re.search(r'((?:^#.*\n)+)env:\s*\n  KAIROS_MIN_TESTS', text, re.M)
        self.assertTrue(comment and 'baseline' in comment.group(1).lower())


class SupplyChainTests(unittest.TestCase):
    def test_every_checkout_drops_the_token_from_git_config(self):
        steps = re.split(r'(?m)^      - (?=name:|uses:)', read())
        checkouts = [s for s in steps if s.startswith('uses: actions/checkout@')]
        self.assertEqual(len(checkouts), len(jobs(read())))
        for step in checkouts:
            self.assertRegex(step, r'persist-credentials:\s*false')

    def test_every_action_is_pinned_to_a_full_sha_with_its_tag_in_a_comment(self):
        uses = re.findall(r'(?m)^\s*(?:- )?uses:\s*(\S+)(.*)$', read())
        self.assertTrue(uses)
        for ref, tail in uses:
            with self.subTest(ref=ref):
                self.assertRegex(ref, r'@[0-9a-f]{40}$')
                self.assertRegex(tail, r'#\s*v\d')


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

    def test_secret_dump_is_rejected(self):
        self.assertTrue(hygiene_violations('env:\n  ALL: ${{ toJSON(secrets) }}\n'))
        self.assertTrue(hygiene_violations('env:\n  ALL: ${{toJSON( secrets )}}\n'))

    def test_release_and_upload_tools_are_rejected(self):
        for text in ('run: gh release create v1\n', 'run: gh  release upload v1 x\n', 'run: twine upload dist/*\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))

    def test_wider_permissions_are_rejected_at_any_level(self):
        for text in ('permissions:\n  contents: write\n', 'permissions: write-all\n', 'permissions:\n  contents: read\n  packages: write\n',
                     'jobs:\n  a:\n    permissions:\n      id-token: write\n    runs-on: x\n',
                     'jobs:\n  a:\n    permissions: read-all\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))
        self.assertEqual(hygiene_violations('permissions:\n  contents: read\n\njobs:\n  a:\n    permissions:\n      contents: read\n'), [])

    def test_event_data_inside_run_is_rejected_but_not_outside(self):
        self.assertTrue(hygiene_violations('steps:\n  - run: echo "${{ github.event.pull_request.title }}"\n'))
        self.assertTrue(hygiene_violations('steps:\n  - name: x\n    run: |\n      echo ${{ github.event.head_commit.message }}\n'))
        self.assertEqual(hygiene_violations('steps:\n  - name: x\n    if: github.event.action == 1\n    run: echo ok\n'), [])

    def test_host_access_is_rejected(self):
        for text in ('run: docker run --privileged x\n', 'run: docker run -v /var/run/docker.sock:/s x\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))

    def test_failures_turned_into_passes_are_rejected(self):
        for text in ('continue-on-error: true\n', "continue-on-error: 'true'\n", 'run: npm test || true\n', 'if: false\n', 'if: "false"\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))

    def test_deployed_installation_resources_are_rejected(self):
        for text in ('run: docker exec knowledge-graphs-memory-api-1 ls\n', 'run: docker volume rm knowledge-graphs_pgdata\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))


if __name__ == '__main__':
    unittest.main()
