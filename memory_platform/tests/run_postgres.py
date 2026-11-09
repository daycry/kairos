"""Run domain/API tests against a fresh real PostgreSQL inside a build container.

This harness owns only its temporary directory and test database. It never
connects to configured user services or reads their environment files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def main():
    if os.name == 'nt' or os.geteuid() == 0:
        raise SystemExit('Run this isolated harness as the container postgres user.')
    root = Path(tempfile.mkdtemp(prefix='memory-platform-pg-')).resolve()
    data = root / 'data'
    port = '55432'
    pg = shutil.which('pg_ctl')
    init = shutil.which('initdb')
    if not pg or not init:
        raise SystemExit('PostgreSQL binaries are required; use the Docker test target.')
    subprocess.run([init, '-D', str(data), '-A', 'trust', '--encoding=UTF8', '--no-locale'], check=True, stdout=subprocess.DEVNULL)
    started = False
    try:
        subprocess.run([pg, '-D', str(data), '-l', str(root / 'postgres.log'), '-o', f'-h 127.0.0.1 -p {port} -k {root}', '-w', 'start'], check=True, stdout=subprocess.DEVNULL)
        started = True
        subprocess.run(['createdb', '-h', '127.0.0.1', '-p', port, '-U', 'postgres', 'memory_test'], check=True)
        os.environ['MEMORY_TEST_DSN'] = f'postgresql://postgres@127.0.0.1:{port}/memory_test'
        os.environ['MEMORY_DSN'] = os.environ['MEMORY_TEST_DSN']
        if os.environ.get('MEMORY_CLIENT_PROBE') == '1':
            from memory_platform.tests.lifecycle_probe import run
            run()
            return
        if os.environ.get('MEMORY_LIVE_PROBE') == '1':
            from memory_platform.tests.live_probe import run
            run(os.environ['MEMORY_TEST_DSN'])
            return
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_*.py', top_level_dir=str(Path(__file__).parents[2]))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if result.testsRun == 0:
            raise SystemExit('No tests were discovered; refusing an empty green build.')
        report = {'database': 'PostgreSQL', 'database_version': subprocess.check_output(['postgres', '--version'], text=True).strip(),
                  'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                  'skipped': len(result.skipped), 'passed': result.wasSuccessful(), 'environment': 'isolated-container-build'}
        print('MEMORY_TEST_RESULT ' + json.dumps(report, sort_keys=True), flush=True)
        if not result.wasSuccessful():
            raise SystemExit(1)
    finally:
        if started:
            subprocess.run([pg, '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True, stdout=subprocess.DEVNULL)
        # tempfile resides under /tmp in the owned test container. Verify before recursion.
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if root.parent != temporary_root or not root.name.startswith('memory-platform-pg-'):
            raise RuntimeError('Refusing cleanup outside the owned temporary test directory')
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
