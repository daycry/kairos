"""Chromium verification of the generated public, offline-safe manuals."""
import base64
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(locale='es-ES')
    errors, requests, checks = [], [], []
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.on('request', lambda req: requests.append(req.url) if not req.url.startswith('file:') else None)
    root = Path(os.environ.get('HANDBOOK_ROOT', '/web/handbook'))
    for width in (1280, 375):
        page.set_viewport_size({'width': width, 'height': 900})
        for document in sorted(root.glob('*.html')):
            page.goto(document.as_uri(), wait_until='load')
            assert page.locator('h1').count() == 1, document.name
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), document.name
            assert page.locator('a[href="#contenido"]').count() == 1
            if width == 375:
                menu = page.locator('.mobile-toc')
                assert menu.get_attribute('open') is None
                menu.locator('summary').click()
                assert menu.get_attribute('open') is not None
            checks.append({'page':document.name,'viewport':width,'passed':True})
        if width == 1280:
            page.goto((root/'manual-kairos.html').as_uri())
            screenshot = page.screenshot(type='jpeg', quality=72)
            Path('/qa/handbook-preview.jpg').write_bytes(screenshot)
            if os.environ.get('KAIROS_QA_EXPORT') == '1':
                print('HANDBOOK_PREVIEW '+base64.b64encode(screenshot).decode(),flush=True)
    browser.close()
    assert not errors, errors
    assert not requests, requests
    Path('/qa/handbook-results.json').write_text(json.dumps({'checks':checks,'external_requests':requests,'browser_errors':errors}, indent=2))
    print('HANDBOOK_RESULT '+json.dumps({'browser':'Chromium','checks':checks,'external_requests':requests,'browser_errors':errors}),flush=True)
