"""Isolated current-source browser gate using an existing test image.

Mount current backend at /candidate/memory_platform, compiled web at
/candidate-dist, freshly generated handbook at /candidate-handbook and an owned
empty evidence directory at /candidate-evidence. No production service is used.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile

web = Path(tempfile.mkdtemp(prefix='kairos-current-web-')).resolve()
shutil.copytree('/web', web, dirs_exist_ok=True)
shutil.copytree('/candidate-dist', web, dirs_exist_ok=True)
handbook = web / 'handbook'
assert handbook.resolve().is_relative_to(web)
if handbook.is_dir():
    shutil.rmtree(handbook)
shutil.copytree('/candidate-handbook', handbook)
os.environ['KAIROS_E2E_WEB_ROOT'] = str(web)
os.environ['HANDBOOK_ROOT'] = str(handbook)

from memory_platform.tests import e2e_portal

try:
    e2e_portal.main()
    from memory_platform.tests import check_handbook  # executes 1280/375 checks
finally:
    target = Path('/candidate-evidence')
    target.mkdir(exist_ok=True)
    allowed = {item.name for item in Path('/qa').iterdir()
               if item.is_file() and item.suffix in {'.json', '.jpg', '.zip'} and item.stat().st_size <= 16_777_216}
    hashes = {}
    total = 0
    for name in sorted(allowed):
        source = Path('/qa') / name
        total += source.stat().st_size
        if total > 67_108_864:
            raise RuntimeError('Bounded synthetic browser evidence exceeds 64 MiB')
        destination = target / name
        shutil.copyfile(source, destination)  # do not chmod OneDrive host directories
        hashes[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {'environment': 'isolated Chromium/PostgreSQL/FastAPI',
                'generation_provider': 'synthetic_fixture_no_external_calls',
                'production_data': False, 'evidence_bytes': total, 'sha256': hashes,
                'handbook_sha256': {str(file.relative_to(handbook)): hashlib.sha256(file.read_bytes()).hexdigest()
                                   for file in sorted(handbook.rglob('*')) if file.is_file()},
                'backend_source_sha256': {str(file.relative_to('/candidate/memory_platform')): hashlib.sha256(file.read_bytes()).hexdigest()
                                          for file in sorted(Path('/candidate/memory_platform').rglob('*'))
                                          if file.is_file() and file.suffix in {'.py', '.sql'}},
                'build_receipt': json.loads(Path('/candidate-dist/web-build-receipt.json').read_text())}
    (target / 'evidence-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
