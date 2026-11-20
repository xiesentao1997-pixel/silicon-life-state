"""Real Chromium process/profile and service restart, preserving a one-time dashboard pairing."""
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from acceptance_support import Local


def main():
    with tempfile.TemporaryDirectory() as temp, sync_playwright() as pw:
        profile = Path(temp) / 'chromium-profile'
        service = Local(Path(temp) / 'state').start()
        try:
            launch = {'executable_path':os.environ['SILICON_CHROMIUM']} if os.getenv('SILICON_CHROMIUM') else {}
            port = urlsplit(service.base).port
            sid = service.subject('档案恢复验收')
            code = service.api('pair/code', {'target':'dashboard'})['code']
            context = pw.chromium.launch_persistent_context(str(profile), **launch)
            try:
                page = context.new_page()
                page.goto(service.base + '/#pair=' + code)
                expect(page.locator('.hero h2')).to_have_text('档案恢复验收')
                assert not page.evaluate("document.cookie.includes('sls_dashboard_')")
            finally:
                context.close()
            service.stop()
            service.start(port=port)
            context = pw.chromium.launch_persistent_context(str(profile), **launch)
            try:
                page = context.new_page()
                page.goto(service.base)
                expect(page.locator('.hero h2')).to_have_text('档案恢复验收')
                assert sid in page.url
                page.locator('.nav-item[data-val=settings]').click()
                page.locator('[data-act=rotate-local]').click()
                expect(page.locator('#toast')).to_contain_text('已轮换')
                other = context.new_page()
                other.goto(service.base)
                expect(other.locator('.hero h2')).to_have_text('档案恢复验收')
                page.locator('[data-act=revoke-local]').click()
                expect(other.locator('.local')).to_contain_text('等待配对')
                print('PASS · Same profile reopened in a new Chromium process after service restart, rotation, second tab, revocation')
            finally:
                context.close()
        finally:
            service.stop()


if __name__ == '__main__':
    main()
