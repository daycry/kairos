"""Copy allowlisted source into the isolated container before PostgreSQL testing.

Updated copy of docs/roadmap/2026-11-06-functional-parity/testing/frozen-source-gate.py for the server/ layout (three-components T-60).
The original sits under testing/ (owned by qa, closed initiative) and stays untouched as the historical gate.

Run inside the existing test image as its postgres user. The candidate mount is
read-only; /test-output is a dedicated evidence directory, never product storage.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
# frozen_evidence.py lives in docs/roadmap/2026-11-06-functional-parity/testing/ (qa-owned); run with that directory on PYTHONPATH.
from frozen_evidence import begin_evidence, finish_evidence


candidate = Path('/candidate').resolve()
snapshot = Path(tempfile.mkdtemp(prefix='kairos-functional-source-')).resolve()
output = Path('/test-output')
excluded = {'node_modules', '__pycache__', '.git', '.pytest_cache', '.cache', 'dist', '.private', '.npmrc', '.env'}
manifest = {}
selected_modules = [value for value in os.getenv('KAIROS_TEST_MODULES', '').split(',') if value]
if any(not re.fullmatch(r'memory_platform\.tests\.test_[a-z_]+', value) for value in selected_modules):
    raise RuntimeError('Focused tests must name local memory_platform test modules')
prefix = 'focused' if selected_modules else 'frozen'


def copy(source, destination):
    if source.is_symlink() or not source.resolve().is_relative_to(candidate):
        raise RuntimeError('Source snapshot rejects symlinks and paths outside candidate')
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            if child.name not in excluded and not child.name.startswith('.env.') and child.suffix not in {'.tgz', '.pyc'}:
                copy(child, destination/child.name)
    else:
        body = source.read_bytes()
        destination.write_bytes(body)
        manifest[destination.relative_to(snapshot).as_posix()] = hashlib.sha256(body).hexdigest()


# Layout of the three components (C-06): server/ (package `memory_platform`), mcp/, client/, the web portal is built by its own image.
# docs/contracts and ollama-proxy are read by tests since phases 2-5; the original gate predates them and lacks them.
for name in ('server', 'scripts', 'client', 'docker-compose.yml', 'docs/contracts', 'mcp', 'ollama-proxy'):
    copy(candidate/name, snapshot/name)
encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
receipt = {'schema': 1, 'mode': 'frozen-container-source', 'source_sha256': hashlib.sha256(encoded).hexdigest(),
           'files': manifest, 'file_count': len(manifest), 'network': 'none', 'product_database_accessed': False,
           'selected_modules': selected_modules, 'full_backend_suite': not selected_modules}
begin_evidence(output, prefix, receipt)
print('KAIROS_FROZEN_SOURCE '+json.dumps({key: value for key, value in receipt.items() if key != 'files'}), flush=True)
os.chdir(snapshot)
sys.path.insert(0, str(snapshot/'server'))
original_runner = unittest.TextTestRunner


class EvidenceRunner(original_runner):
    def run(self, suite):
        started = time.perf_counter()
        result = super().run(suite)
        evidence = {'schema': 1, 'source_sha256': receipt['source_sha256'],
                    'mode': receipt['mode'], 'network': 'none', 'product_database_accessed': False,
                    'database': 'PostgreSQL', 'database_version': subprocess.check_output(['postgres', '--version'], text=True).strip(),
                    'selected_modules': selected_modules, 'full_backend_suite': not selected_modules,
                    'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                    'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
                    'elapsed_seconds': round(time.perf_counter()-started, 3),
                    'failed_tests': [str(test) for test, _ in result.failures+result.errors]}
        finish_evidence(output, prefix, evidence)
        return result


unittest.TextTestRunner = EvidenceRunner
if selected_modules:
    unittest.defaultTestLoader.discover = lambda *args, **kwargs: unittest.defaultTestLoader.loadTestsFromNames(selected_modules)
from memory_platform.tests.run_postgres import main
main()
