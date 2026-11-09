"""Export the owned vector brand assets to PNG with an isolated browser."""
import base64
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright


def main():
    variants = [('kairos-logo.svg', 'kairos-logo.png', 1080, 256),
                ('kairos-logo-dark.svg', 'kairos-logo-dark.png', 1080, 256),
                ('kairos-mark.svg', 'kairos-symbol.png', 512, 512)]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page()
        for source, destination, width, height in variants:
            svg = (Path('/app/brand') / source).read_text(encoding='utf-8')
            svg = svg.replace('<svg ', f'<svg width="{width}" height="{height}" ', 1)
            page.set_viewport_size({'width': width, 'height': height})
            page.set_content('<!doctype html><html><body style="margin:0;background:transparent">'+svg+'</body></html>')
            page.evaluate('document.fonts.ready')
            assert page.locator('svg').count() == 1
            path = Path('/qa') / destination
            page.screenshot(path=str(path), omit_background=True)
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            parts = [encoded[i:i+4000] for i in range(0, len(encoded), 4000)]
            print('BRAND_RESULT '+json.dumps({'file':destination,'width':width,'height':height,'bytes':path.stat().st_size}), flush=True)
            for index, part in enumerate(parts):
                print('BRAND_BLOB '+json.dumps({'file':destination,'part':index,'total':len(parts),'data':part}), flush=True)
                time.sleep(1)
        browser.close()


if __name__ == '__main__':
    main()
