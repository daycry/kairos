"""Current generated manuals; real offline Chromium at desktop/mobile widths."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil

root = Path('/candidate-handbook')
os.environ['HANDBOOK_ROOT'] = str(root)
from memory_platform.tests import check_handbook  # executes 1280/375 assertions

target = Path('/candidate-evidence')
for name in ('handbook-results.json', 'handbook-preview.jpg'):
    shutil.copyfile(Path('/qa')/name, target/name.replace('handbook-', 'handbook-latest-'))
files = {str(file.relative_to(root)): hashlib.sha256(file.read_bytes()).hexdigest()
         for file in sorted(root.rglob('*')) if file.is_file()}
report = json.loads((target/'handbook-latest-results.json').read_text())
(target/'handbook-source.json').write_text(json.dumps({
    'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'sha256': files,
    'checks': len(report['checks']), 'external_requests': report['external_requests'],
    'results_file': 'handbook-latest-results.json', 'preview_file': 'handbook-latest-preview.jpg',
    'browser_errors': report['browser_errors'], 'environment': 'isolated Chromium, generated public files only'
}, indent=2)+'\n')
