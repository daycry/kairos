"""Structure of .github/workflows/ci.yml, checked as text so the test needs no YAML library (CA-01)."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
# Evasions of the gate: weakening a failure into a pass, or reaching the runner host (all matched without regard to case).
WEAKENING = {'|| true': r'\|\|\s*true\b'}
HOST_ACCESS = {'--privileged': r'--privileged\b', 'docker.sock': r'docker\.sock', '--cap-add': r'--cap-add\b', '--pid=host': r'--pid(?:=|\s+)host\b'}
# Inside a run: script, an exit code swallowed (`|| :`, `|| exit 0`, `set +e`).
SWALLOWED_IN_RUN = {'|| : in run:': r'\|\|\s*:', '|| exit 0 in run:': r'\|\|\s*exit\s+0\b', '|| true in run:': r'\|\|\s*true\b',
                    'set +e in run:': r'\bset\s+\+e\b', 'set +o errexit in run:': r'\bset\s+\+o\s+errexit\b'}
# `${{ github.* }}` and `${{ inputs.* }}` in a run: script are shell injection (head_ref, titles, branch names): hand them over through `env:`
# and read the variable. Whitelist of exact expressions (lower case, trimmed) allowed there; none is needed today.
RUN_EXPRESSIONS_ALLOWED = ()


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


def disabled_or_forced(text):
    """`if:` that is false in any form and `continue-on-error` with anything but a literal false (workflow, job or step)."""
    found = []
    for value in re.findall(r'(?mi)^\s*(?:- )?if:[ \t]*(.*)$', text):
        if re.search(r'(?<![\w.])false(?![\w.])', value, re.I) or re.search(r'!\s*true\b', value, re.I):
            found.append('if: ' + value.strip())
    for value in re.findall(r'(?mi)^\s*(?:- )?continue-on-error:[ \t]*(.*)$', text):
        if clean_value(value).lower() != 'false':
            found.append('continue-on-error: ' + value.strip())
    return found


def hygiene_violations(text):
    """What a workflow text does that CA-02/CA-30 forbid: foreign secrets, publishing, deployed-installation resources,
    wider token permissions, event data in scripts, host access and failures turned into passes."""
    found = []
    for name in re.findall(r'\bsecrets\.([A-Za-z0-9_]+)', text, re.I):
        if name.upper() != 'GITHUB_TOKEN':
            found.append('secret ' + name)
    if re.search(r'\bsecrets\s*\[', text, re.I):
        found.append('secret by index')
    if re.search(r'\bsecrets:\s*inherit\b', text, re.I):
        found.append('secrets: inherit')
    if re.search(r'\btoJSON\(\s*secrets\s*\)', text, re.I):
        found.append('toJSON(secrets)')
    for pattern in PUBLISHING:
        if re.search(pattern, text, re.I):
            found.append('publishing: ' + pattern)
    if re.search(DEPLOYED, text, re.I):
        found.append('deployed installation resource')
    found.extend(permission_violations(text))
    for body in run_blocks(text):
        for expression in re.findall(r'\$\{\{(.*?)\}\}', body, re.S):
            if re.search(r'\b(?:github|inputs)\b', expression, re.I) and expression.strip().lower() not in RUN_EXPRESSIONS_ALLOWED:
                found.append('github/inputs expression inside run: ' + expression.strip())
        for label, pattern in SWALLOWED_IN_RUN.items():
            if re.search(pattern, body, re.I):
                found.append(label)
    for label, pattern in {**HOST_ACCESS, **WEAKENING}.items():
        if re.search(pattern, text, re.I):
            found.append(label)
    found.extend(disabled_or_forced(text))
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
        self.assertIn('docker build --target test -f server/memory_platform/Dockerfile', block)

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
        self.assertIn('docker build --target retrieval-eval -f server/memory_platform/Dockerfile', block)
        self.assertNotIn('MEMORY_LLM', block)  # simulated provider only: no model, no external service
        # The gate really ran and passed: its report line is read back from the build log.
        self.assertIn('RETRIEVAL_EVAL_RESULT', block)
        self.assertIn('"passed": true', block)

    def test_client_job_runs_tests_and_release_check_in_the_package(self):
        self.assertIn('client', self.jobs)
        block = self.jobs['client']
        self.assertIn('working-directory: client', block)
        self.assertIn('npm test', block)
        self.assertIn('npm run release:check', block)

    def test_web_job_runs_typecheck_test_build_and_the_web_image_test_target(self):
        self.assertIn('web', self.jobs)
        block = self.jobs['web']
        self.assertIn('working-directory: web', block)
        for command in ('npm ci', 'npm run typecheck', 'npm test', 'npm run build'):
            self.assertIn(command, block)
        self.assertIn('docker build --target test -f web/Dockerfile', block)


class McpJobTests(unittest.TestCase):
    """T-36: kairos-mcp has its own job: the image without a database driver is built and its tests run inside it."""

    def setUp(self):
        self.jobs = jobs(read())

    def test_mcp_job_builds_the_component_image_and_runs_its_tests(self):
        self.assertIn('mcp', self.jobs)
        block = self.jobs['mcp']
        self.assertIn('docker build -f mcp/Dockerfile -t kairos-mcp:ci mcp/', block)
        self.assertIn('python -m unittest discover -s tests', block)
        self.assertRegex(block, r'runs-on:\s*ubuntu-latest')

    def test_mcp_job_proves_the_image_has_no_database_driver(self):
        block = self.jobs['mcp']
        self.assertIn('pip list', block)
        self.assertIn('psycopg', block)

    def test_mcp_job_needs_no_service_secret_or_network_beyond_the_build(self):
        block = self.jobs['mcp']
        for forbidden in ('docker compose', 'curl ', 'MEMORY_DSN', 'MEMORY_TEST_DSN', 'memory_platform'):
            self.assertNotIn(forbidden, block)


class ComponentTests(unittest.TestCase):
    """CA-24 (C-06): each component has its image or Dockerfile and the command the CI runs for its tests."""
    ROOT = WORKFLOW.parents[2]
    COMPONENTS = {
        'server': ('server/memory_platform/Dockerfile', 'server', 'docker build --target test -f server/memory_platform/Dockerfile'),
        'mcp': ('mcp/Dockerfile', 'mcp', 'docker run --rm kairos-mcp:ci python -m unittest discover -s tests'),
        'client': ('client/Dockerfile.test', 'client', 'npm test'),
        'web': ('web/Dockerfile', 'web', 'docker build --target test -f web/Dockerfile'),
    }

    def test_every_component_has_a_dockerfile_and_its_test_command_in_the_ci(self):
        job_blocks = jobs(read())
        for component, (dockerfile, job, command) in self.COMPONENTS.items():
            with self.subTest(component=component):
                self.assertTrue((self.ROOT / dockerfile).is_file(), dockerfile)
                self.assertIn(command, job_blocks[job])

    def test_the_old_locations_are_gone(self):
        for old in ('memory_platform', 'packages/kairos-cli'):
            with self.subTest(path=old):
                self.assertFalse((self.ROOT / old).exists(), old)


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
        self.assertIn('server/memory_platform/tests/contracts_base', block)  # T-26 reassigns this base

    def test_contracts_job_needs_no_service_or_network_beyond_dependencies(self):
        block = self.jobs['contracts']
        for forbidden in ('docker compose', 'curl ', 'MEMORY_DSN', 'MEMORY_TEST_DSN'):
            self.assertNotIn(forbidden, block)


GATE_STEP = 'The suite really ran and nothing was skipped'
MIN_FLOOR = 917  # the suite with the kairos-mcp chain tests, the review corrections and the C-07 tests and the initiative 3 phase 1 tests (T-01 began at 483, 639 when kairos-mcp started, 727 with the chain tests, 743 after phase 5, 756 with the MCP legacy and route tests, 759 with the phase 7 version tests, 764 with the phase 8 rehearsal tests, 801 with the fault-injection harness and the limit, schema and lease tests of initiative 3 phase 1, 806 with the corrections of its review, 852 with the database-down worker tests of initiative 3 phase 2, 870 with the corrections of its review, 884 with the corrections of its second review, 917 with the queue-index and table-pruning tests of phase 3); raise it when the suite grows, never lower it
GOOD = 'MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0, "tests": %d}' % MIN_FLOOR


def find_bash():
    """bash for the behavioural check; on Windows prefer Git for Windows (the WSL launcher in System32 is not a usable bash here)."""
    candidates = []
    if sys.platform == 'win32':
        for root in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LOCALAPPDATA')):
            if root:
                candidates += [Path(root) / 'Git' / 'bin' / 'bash.exe', Path(root) / 'Programs' / 'Git' / 'bin' / 'bash.exe']
    found = [str(c) for c in candidates if c.is_file()]
    which = shutil.which('bash')
    if which and 'system32' not in which.lower():
        found.append(which)
    return found[0] if found else None


BASH = find_bash()


def clean_value(raw):
    raw = raw.strip()
    if raw[:1] in ('"', "'"):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.sub(r'\s+#.*$', '', raw).strip()


def env_dict(lines, indent):
    """Entries of the `env:` mapping that sits at exactly `indent` spaces (workflow 0, job 4, step 8)."""
    found = {}
    for number, line in enumerate(lines):
        if not re.match(r'^ {%d}env:\s*(?:#.*)?$' % indent, line):
            continue
        for following in lines[number + 1:]:
            if not following.strip() or following.lstrip().startswith('#'):
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            match = re.match(r'^\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$', following)
            if match:
                found[match.group(1)] = clean_value(match.group(2))
    return found


def gate_parts(text):
    """(job block, step lines, run script) of the gate step, or None when the step is missing."""
    for block in jobs(text).values():
        match = re.search(r'(?ms)^      - name: ' + re.escape(GATE_STEP) + r'\s*\n(.*?)(?=^      - |\Z)', block)
        if not match:
            continue
        step = match.group(1).splitlines()
        script = None
        for number, line in enumerate(step):
            run = re.match(r'^        run:\s*(.*)$', line)
            if not run:
                continue
            if run.group(1) and not run.group(1).startswith(('|', '>')):
                script = run.group(1)
                break
            body = []
            for following in step[number + 1:]:
                if following.strip() and len(following) - len(following.lstrip()) < 10:
                    break
                body.append(following[10:])
            script = '\n'.join(body) + '\n'
            break
        return block, step, script
    return None


def effective_minimum(text, job_block, step_lines):
    """KAIROS_MIN_TESTS as GitHub resolves it: step `env:` over job `env:` over workflow `env:`; returns (value, problems)."""
    problems = []
    layers = [env_dict(step_lines, 8), env_dict(job_block.splitlines(), 4), env_dict(text.splitlines(), 0)]
    if 'KAIROS_MIN_TESTS' in layers[0]:
        problems.append('KAIROS_MIN_TESTS redefined in the step')
    if 'KAIROS_MIN_TESTS' in layers[1]:
        problems.append('KAIROS_MIN_TESTS redefined in the job')
    if re.search(r'\benv:\s*\{[^}\n]*KAIROS_MIN_TESTS', text):
        problems.append('KAIROS_MIN_TESTS in an inline env')
    if len(re.findall(r'(?m)^\s*KAIROS_MIN_TESTS:', text)) != 1:
        problems.append('KAIROS_MIN_TESTS must be declared exactly once')
    value = next((layer['KAIROS_MIN_TESTS'] for layer in layers if 'KAIROS_MIN_TESTS' in layer), None)
    if value is None or not re.fullmatch(r'\d+', value):
        return None, problems + ['KAIROS_MIN_TESTS is not a plain number: %r' % value]
    if int(value) < MIN_FLOOR:
        problems.append('KAIROS_MIN_TESTS %s is below the baseline %d' % (value, MIN_FLOOR))
    return int(value), problems


def log_line(tests=MIN_FLOOR, failures=0, errors=0, skipped=0, passed='true'):
    return 'MEMORY_TEST_RESULT {"errors": %s, "failures": %s, "passed": %s, "skipped": %s, "tests": %s}' % (errors, failures, passed, skipped, tests)


# (name, simulated build log, must the step succeed)
GATE_CASES = (
    ('baseline, nothing wrong', 'noise\n' + GOOD + '\nmore noise\n', True),
    ('more tests than the baseline', log_line(tests=MIN_FLOOR + 16) + '\n', True),
    ('one below the minimum', log_line(tests=MIN_FLOOR - 1) + '\n', False),
    ('1 failure', log_line(failures=1) + '\n', False),
    ('1 error', log_line(errors=1) + '\n', False),
    ('1 skipped', log_line(skipped=1) + '\n', False),
    ('passed false', log_line(passed='false') + '\n', False),
    ('no result line', 'Ran %d tests\nOK\n' % MIN_FLOOR, False),
    ('empty log', '', False),
    ('tests not numeric', log_line(tests='"many"') + '\n', False),
    ('tests null', log_line(tests='null') + '\n', False),
    ('tests missing', 'MEMORY_TEST_RESULT {"errors": 0, "failures": 0, "passed": true, "skipped": 0}\n', False),
    ('a good line followed by a bad one', GOOD + '\n' + log_line(tests=MIN_FLOOR - 1) + '\n', False),
)


def run_gate(script, minimum, log_text, workdir):
    """Run the step script the way GitHub does (`bash -e -o pipefail`) over a simulated build log; returns its exit code."""
    log = Path(workdir) / 'server.log'
    log.write_text(log_text, encoding='utf-8', newline='\n')
    paths = set(re.findall(r'/tmp/[\w.-]+\.log', script))
    if not paths:
        return None
    for path in paths:
        script = script.replace(path, log.as_posix())
    file = Path(workdir) / 'step.sh'
    file.write_text(script, encoding='utf-8', newline='\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GITHUB_', 'KAIROS_'))}
    env.update({'GITHUB_ACTIONS': 'true', 'GITHUB_WORKSPACE': Path(workdir).as_posix(), 'GITHUB_REPOSITORY': 'owner/repo',
                'GITHUB_REF': 'refs/heads/x', 'GITHUB_ENV': (Path(workdir) / 'env').as_posix(),
                'GITHUB_OUTPUT': (Path(workdir) / 'out').as_posix(), 'GITHUB_STEP_SUMMARY': (Path(workdir) / 'summary').as_posix(),
                'KAIROS_MIN_TESTS': str(minimum)})
    result = subprocess.run([BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail', file.as_posix()], env=env, cwd=workdir,
                            capture_output=True, text=True, timeout=60)
    return result.returncode


def gate_problems(text, execute=True):
    """Everything wrong with the suite-gate step: its structure, the effective minimum and (with bash) what it does on synthetic logs."""
    parts = gate_parts(text)
    if parts is None:
        return ['step missing']
    block, step, script = parts
    minimum, problems = effective_minimum(text, block, step)
    if script is None:
        return problems + ['step has no run script']
    for line in step:
        if re.match(r'^        (?:if|continue-on-error|shell|working-directory):', line):
            problems.append('step key that can disable or change the gate: ' + line.strip())
    for line in block.splitlines():
        if re.match(r'^    (?:if|continue-on-error):', line):
            problems.append('job key that can disable the gate: ' + line.strip())
    for body in run_blocks(text):
        if 'GITHUB_ENV' in body:
            problems.append('a step writes GITHUB_ENV')
    if execute and minimum is not None and not problems:  # a mutant already caught by the analysis needs no execution
        with tempfile.TemporaryDirectory() as workdir:
            def one(item):
                number, (name, log_text, must_pass) = item
                folder = Path(workdir) / str(number)
                folder.mkdir()
                return name, must_pass, run_gate(script, minimum, log_text, folder)
            with ThreadPoolExecutor(max_workers=8) as pool:  # each case is an independent bash process
                results = list(pool.map(one, enumerate(GATE_CASES)))
        for name, must_pass, code in results:
            if code is None:
                problems.append('the script does not read a /tmp/*.log file')
                break
            if (code == 0) != must_pass:
                problems.append('%s: exit %s, expected %s' % (name, code, 'success' if must_pass else 'failure'))
    return problems


def comment_line(fragment):
    return lambda text: re.sub(r'(?m)^(\s*)(.*' + re.escape(fragment) + r'.*)$', r'\1# \2', text, count=1)


def append_to_line(fragment, suffix):
    return lambda text: re.sub(r'(?m)^(.*' + re.escape(fragment) + r'.*)$', lambda m: m.group(1) + suffix, text, count=1)


def after_step_name(extra):
    return lambda text: text.replace('      - name: ' + GATE_STEP + '\n', '      - name: ' + GATE_STEP + '\n' + extra, 1)


COMPARISON = '-ge "$KAIROS_MIN_TESTS"'
# Each mutation is applied to the text of the workflow and must make the analysis or the execution of the gate fail.
MUTANTS = (
    ('delete the comparison', lambda t: re.sub(r'(?m)^.*' + re.escape(COMPARISON) + r'.*\n', '', t)),
    ('compare with -ge 0', lambda t: t.replace(COMPARISON, '-ge 0')),
    ('compare with -ge 1', lambda t: t.replace(COMPARISON, '-ge 1')),
    ('comparison || :', append_to_line(COMPARISON, ' || :')),
    ('comparison || exit 0', append_to_line(COMPARISON, ' || exit 0')),
    ('comparison || true', append_to_line(COMPARISON, ' || true')),
    ('comment the skipped grep', comment_line("grep -q '\"skipped\": 0'")),
    ('comment the failures grep', comment_line("grep -q '\"failures\": 0'")),
    ('comment the errors grep', comment_line("grep -q '\"errors\": 0'")),
    ('comment the passed grep', comment_line("grep -q '\"passed\": true'")),
    ('failures grep || true', append_to_line("grep -q '\"failures\": 0'", ' || true')),
    ('weaken skipped to any value', lambda t: t.replace('"skipped": 0', '"skipped"')),
    ('first result line instead of the last', lambda t: t.replace('| tail -1)', '| head -1)')),
    ('set +e before the checks', lambda t: t.replace('        run: |\n          line="$(grep', '        run: |\n          set +e\n          line="$(grep', 1)),
    ('KAIROS_MIN_TESTS 0 at workflow level', lambda t: re.sub(r"KAIROS_MIN_TESTS: '\d+'", "KAIROS_MIN_TESTS: '0'", t)),
    ('KAIROS_MIN_TESTS one below the floor at workflow level', lambda t: re.sub(r"KAIROS_MIN_TESTS: '\d+'", "KAIROS_MIN_TESTS: '%d'" % (MIN_FLOOR - 1), t)),
    ('KAIROS_MIN_TESTS not a number', lambda t: re.sub(r"KAIROS_MIN_TESTS: '\d+'", "KAIROS_MIN_TESTS: 'lots'", t)),
    ('KAIROS_MIN_TESTS 0 in the job env', lambda t: t.replace('    timeout-minutes: 45\n', "    timeout-minutes: 45\n    env:\n      KAIROS_MIN_TESTS: '0'\n", 1)),
    ('KAIROS_MIN_TESTS 0 in the step env', after_step_name("        env:\n          KAIROS_MIN_TESTS: '0'\n")),
    ('KAIROS_MIN_TESTS 0 in an inline env', after_step_name('        env: {KAIROS_MIN_TESTS: 0}\n')),
    ('KAIROS_MIN_TESTS assigned in the script', lambda t: t.replace('          line="$(grep', '          KAIROS_MIN_TESTS=0\n          line="$(grep', 1)),
    ('KAIROS_MIN_TESTS written to GITHUB_ENV earlier',
     lambda t: t.replace('          set -euo pipefail\n          # No layer', '          set -euo pipefail\n          echo "KAIROS_MIN_TESTS=0" >> "$GITHUB_ENV"\n          # No layer', 1)),
    ('step continue-on-error', after_step_name('        continue-on-error: true\n')),
    ('step if false', after_step_name('        if: ${{ false }}\n')),
    ('step with another shell', after_step_name('        shell: sh\n')),
    ('job continue-on-error', lambda t: t.replace('    timeout-minutes: 45\n', '    timeout-minutes: 45\n    continue-on-error: true\n', 1)),
    ('delete the step', lambda t: re.sub(r'(?s)      - name: ' + GATE_STEP + r'.*?(?=\n  retrieval-eval:)', '', t)),
)


class SuiteGateStepTests(unittest.TestCase):
    """The step that reads MEMORY_TEST_RESULT back makes `server` fail on skipped or missing tests. It is protected by running its own
    script over synthetic logs (behaviour), not by looking for text in it."""

    def need_bash(self):
        if BASH is None:
            if sys.platform == 'win32':
                self.skipTest('bash (Git for Windows) not found on Windows: the behavioural check of the suite gate cannot run here; it runs in CI')
            self.fail('bash is required to run the suite-gate behaviour test')

    def test_the_step_belongs_to_the_server_job(self):
        self.assertIn(GATE_STEP, jobs(read())['server'])

    def test_current_step_structure_and_effective_minimum(self):
        parts = gate_parts(read())
        self.assertIsNotNone(parts)
        minimum, problems = effective_minimum(read(), parts[0], parts[1])
        self.assertEqual(problems, [])
        self.assertGreaterEqual(minimum, MIN_FLOOR)
        comment = re.search(r'((?:^#.*\n)+)env:\s*\n  KAIROS_MIN_TESTS', read(), re.M)
        self.assertTrue(comment and 'baseline' in comment.group(1).lower())

    def test_the_minimum_resolves_in_github_precedence_order(self):
        text = "env:\n  KAIROS_MIN_TESTS: '10'\njobs:\n  a:\n    env:\n      KAIROS_MIN_TESTS: 20 # job\n    steps:\n      - name: s\n"
        job = jobs(text)['a']
        step = ['        env:', '          KAIROS_MIN_TESTS: "30"']
        self.assertEqual(env_dict(text.splitlines(), 0), {'KAIROS_MIN_TESTS': '10'})
        self.assertEqual(env_dict(job.splitlines(), 4), {'KAIROS_MIN_TESTS': '20'})
        self.assertEqual(env_dict(step, 8), {'KAIROS_MIN_TESTS': '30'})
        self.assertEqual(effective_minimum(text, job, step)[0], 30)
        self.assertEqual(effective_minimum(text, job, [])[0], 20)
        self.assertEqual(effective_minimum(text, '', [])[0], 10)

    def test_the_current_script_passes_the_good_log_and_fails_every_bad_one(self):
        self.need_bash()
        self.assertEqual(gate_problems(read()), [])

    def test_the_synthetic_cases_cover_the_required_failures(self):
        names = [name for name, _, _ in GATE_CASES]
        for required in ('one below the minimum', '1 failure', '1 error', '1 skipped', 'no result line', 'tests not numeric'):
            self.assertIn(required, names)
        self.assertEqual([name for name, _, ok in GATE_CASES if ok][0], 'baseline, nothing wrong')

    def test_every_mutant_of_the_workflow_is_detected(self):
        self.need_bash()
        original = read()
        for name, mutate in MUTANTS:
            with self.subTest(mutant=name):
                mutant = mutate(original)
                self.assertNotEqual(mutant, original, 'the mutation changed nothing')
                self.assertTrue(gate_problems(mutant), 'mutant survived: ' + name)

    def test_a_job_of_the_workflow_runs_this_test_file(self):
        # Without this the protection above would only run on a laptop: the CI must execute it on Linux, where bash is always there.
        pattern = r'python -m unittest discover -s scripts/tests -p test_ci_workflow\.py'
        runners = [name for name, block in jobs(read()).items() if re.search(pattern, block)]
        self.assertTrue(runners, 'no job runs scripts/tests/test_ci_workflow.py')


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

    def test_expression_rules_ignore_case(self):
        for text in ('env:\n  ALL: ${{ toJson(secrets) }}\n', 'env:\n  ALL: ${{ TOJSON(SECRETS) }}\n', 'env:\n  T: ${{ SECRETS.REGISTRY_PASSWORD }}\n',
                     'env:\n  T: ${{ Secrets.npm_token }}\n', "env:\n  T: ${{ SECRETS['NPM_TOKEN'] }}\n", 'SECRETS: INHERIT\n',
                     'steps:\n  - run: echo "${{ GitHub.Event.pull_request.title }}"\n', 'steps:\n  - run: echo "${{ GITHUB.EVENT.head_commit.message }}"\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))
        self.assertEqual(hygiene_violations('env:\n  T: ${{ Secrets.GitHub_Token }}\n'), [])

    def test_more_ways_to_swallow_a_failure_in_a_run_are_rejected(self):
        for body in ('npm test || :', 'npm test || exit 0', 'npm test ||exit 0', 'npm test || true', 'set +e', 'set  +e', 'set +o errexit', 'npm test ||:',
                     'npm test || :;', 'npm test || exit 0 # never red'):
            for text in ('steps:\n  - run: ' + body + '\n', 'steps:\n  - name: x\n    run: |\n      npm ci\n      ' + body + '\n      npm run x\n'):
                with self.subTest(text=text):
                    self.assertTrue(hygiene_violations(text))
        clean = 'steps:\n  - run: |\n      set -euo pipefail\n      npm test || exit 1\n      grep -q x f || { echo no >&2; exit 2; }\n'
        self.assertEqual(hygiene_violations(clean), [])

    def test_a_disabled_step_or_job_is_rejected_in_any_form(self):
        for value in ('false', '"false"', "'false'", '${{ false }}', '${{false}}', '${{ !true }}', 'False', 'FALSE', '${{ false && github.ref == 1 }}', '!true',
                      '${{ github.ref == 1 && false }}'):
            with self.subTest(value=value):
                self.assertTrue(hygiene_violations('jobs:\n  a:\n    if: ' + value + '\n'))
                self.assertTrue(hygiene_violations('steps:\n  - name: x\n    if: ' + value + '\n    run: echo\n'))
        self.assertEqual(hygiene_violations("steps:\n  - name: x\n    if: github.event_name == 'push'\n    run: echo ok\n"), [])
        self.assertEqual(hygiene_violations('steps:\n  - name: x\n    if: ${{ always() }}\n    run: echo ok\n'), [])

    def test_continue_on_error_with_any_value_but_false_is_rejected(self):
        for value in ('true', "'true'", '"True"', 'TRUE', '${{ true }}', '${{ matrix.experimental }}', '1', 'yes', '${{ github.event_name == 1 }}'):
            with self.subTest(value=value):
                self.assertTrue(hygiene_violations('jobs:\n  a:\n    continue-on-error: ' + value + '\n'))
                self.assertTrue(hygiene_violations('steps:\n  - name: x\n    continue-on-error: ' + value + '\n'))
        for value in ('false', "'false'", 'False'):
            self.assertEqual(hygiene_violations('steps:\n  - name: x\n    continue-on-error: ' + value + '\n'), [])

    def test_github_or_inputs_expressions_inside_run_are_rejected(self):
        for expression in ('github.head_ref', 'github.event.pull_request.title', 'inputs.name', 'github.ref_name', 'GitHub.Head_Ref', "github['head_ref']",
                           "format('{0}', github.head_ref)", 'toJSON(github)', 'inputs'):
            with self.subTest(expression=expression):
                self.assertTrue(hygiene_violations('steps:\n  - run: echo "${{ ' + expression + ' }}"\n'))
                self.assertTrue(hygiene_violations('steps:\n  - name: x\n    run: |\n      echo ${{' + expression + '}}\n'))
        # outside run: the same expressions are fine (a concurrency group, an if:, an env: value handed to the script as a variable)
        self.assertEqual(hygiene_violations('concurrency:\n  group: ci-${{ github.ref }}\n'), [])
        self.assertEqual(hygiene_violations('steps:\n  - name: x\n    env:\n      REF: ${{ github.head_ref }}\n    run: echo "$REF"\n'), [])
        self.assertEqual(hygiene_violations('steps:\n  - name: x\n    run: echo "${{ env.KAIROS_MIN_TESTS }}"\n'), [])

    def test_more_host_access_is_rejected(self):
        for text in ('run: docker run --cap-add SYS_ADMIN x\n', 'run: docker run --cap-add=NET_ADMIN x\n', 'run: docker run --pid=host x\n',
                     'run: docker run --pid host x\n', 'run: docker run --PID=HOST x\n', 'run: docker run --cap-add ALL x\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))
        self.assertEqual(hygiene_violations('run: docker run --cap-drop ALL --pid=container:x y\n'), [])

    def test_deployed_installation_resources_are_rejected(self):
        for text in ('run: docker exec knowledge-graphs-memory-api-1 ls\n', 'run: docker volume rm knowledge-graphs_pgdata\n'):
            with self.subTest(text=text):
                self.assertTrue(hygiene_violations(text))


class ComposeLimitsTests(unittest.TestCase):
    def test_memory_mcp_has_a_memory_limit(self):
        """A response of tens of MB is held several times over while it is parsed and cut (review of phase 5, N2): the container is bounded."""
        compose = (WORKFLOW.parents[2] / 'docker-compose.yml').read_text(encoding='utf-8')
        block = re.search(r'^  memory-mcp:\n((?:    .*\n|\s*\n)+)', compose, re.M)
        self.assertIsNotNone(block)
        self.assertRegex(block.group(1), r'(?m)^    mem_limit: \d+[mg]\b')


if __name__ == '__main__':
    unittest.main()
