"""Actual Chromium UI with local protocol fixture, separate from real-model acceptance."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright
from acceptance_support import Local
from test_model_chat import provider


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp, provider() as (url,_), sync_playwright() as pw:
        local=Local(tmp).start()
        try:
            sid=local.subject('内置对话测试')
            local.window(sid,'QA 对话分身')
            options={"executable_path":os.environ["SILICON_CHROMIUM"]} if os.getenv("SILICON_CHROMIUM") else {}
            browser=pw.chromium.launch(**options)
            page=browser.new_page(locale="zh-CN",viewport={"width":1280,"height":900})
            errors=[]
            page.on("pageerror",lambda err:errors.append(str(err)))
            code=local.api('pair/code',{'target':'dashboard'})['code']
            page.goto(local.base+'/#pair='+code+'&view=chat&subject='+sid)
            page.locator('#chat-url').fill(url)
            page.locator('#chat-model').fill('fixture-model')
            page.locator('#chat-key').fill('private-fixture-credential')
            page.locator('#chat-connect').click()
            expect(page.locator('#chat-text')).to_be_enabled()
            page.locator('#chat-text').fill('normal')
            page.locator('#chat-send').click()
            expect(page.locator('#chat-transcript')).to_contain_text('协议夹具回复')
            expect(page.locator('#chat-send')).to_be_enabled()
            assert not local.api('export')['events']
            page.locator('#chat-text').fill('submit')
            page.locator('#chat-send').click()
            expect(page.locator('.chat-receipt')).to_have_count(3)
            if args.output:
                args.output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(args.output/'chat-provider-fixture.jpg'),type="jpeg",quality=85)
            page.locator('.nav-item[data-val=overview]').click()
            expect(page.locator('.big-quote').first).to_contain_text('可审计的夹具原文')
            assert not errors, errors
            result={"browser":browser.version,"provider":"scripted localhost transport fixture",
                    "checks":["paired chat config","tool-free answer","three tool receipts and actual MCP/SQLite","dashboard report projection"], "page_errors":errors}
            if args.output:
                (args.output/'chat-browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False))
            browser.close()
        finally:
            local.stop()


if __name__=='__main__':
    main()
