"""Real Chromium dashboard E2E. Uses isolated data, a fresh browser and ordinary pairing.

python -m pip install playwright && python -m playwright install chromium
python tests/dashboard_browser.py --output /tmp/sls-browser-evidence
Optional --read-agent-db and --event-id verify an already authorized test subject's
actual report. Make a disposable QA clone. No existing database is changed.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from acceptance_support import Local


def main():
    from playwright.sync_api import expect, sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--read-agent-db', type=Path)
    parser.add_argument('--event-id')
    opt = parser.parse_args()
    output = opt.output
    if output:
        output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix='sls-dashboard-') as tmp, sync_playwright() as pw:
        dbdir = Path(tmp) / 'qa'
        dbdir.mkdir()
        event = None
        if opt.read_agent_db:
            if not opt.event_id:
                parser.error('--read-agent-db requires --event-id')
            with closing(sqlite3.connect(opt.read_agent_db.resolve().as_uri() + '?mode=ro', uri=True)) as orig, \
                    closing(sqlite3.connect(dbdir/'state.sqlite3')) as clone:
                orig.backup(clone)
                # Transfer display data only, without user or agent credentials.
                clone.execute('DELETE FROM grants')
                clone.execute('DELETE FROM receipts')
                clone.commit()
                row = clone.execute('SELECT subject_id,payload,hash FROM events WHERE event_id=? AND source="agent_direct" AND type="report_state"',
                                    (opt.event_id,)).fetchone()
                assert row, 'Agent report is missing'
                event = (row[0],json.loads(row[1])['state_text'],row[2])
        service = Local(dbdir).start()
        launch = {'executable_path':os.environ['SILICON_CHROMIUM']} if os.getenv('SILICON_CHROMIUM') else {}
        def open_page(browser, subject):
            page = browser.new_page(viewport={'width':1440,'height':1040}, locale='zh-CN')
            code = service.api('pair/code', {'target':'dashboard'})['code']
            page.goto(service.base + '/#pair=' + code + '&subject=' + subject)
            return page
        def capture(page, filename):
            if output:
                page.screenshot(path=str(output/filename), animations='disabled', type='jpeg', quality=90)
        try:
            browser = pw.chromium.launch(**launch)
            browser_version = browser.version
            if event:
                page = open_page(browser,event[0])
                expect(page.locator('.big-quote').first).to_have_text(event[1])
                expect(page.get_by_text('AI 通过 MCP 自主填写', exact=True).first).to_be_visible()
                capture(page,'dashboard-live-agent.jpg')
                page.get_by_role('button',name='查看记录',exact=True).first.click()
                expect(page.locator('dialog')).to_contain_text(opt.event_id)
                expect(page.locator('dialog')).to_contain_text(event[2])
                capture(page,'live-agent-evidence.jpg')
                page.close()
                checks.append('A: existing actual agent event in UI; original text, event ID and hash matched DB')
            subject = service.subject('分身协议验收')
            a, ta = service.window(subject, '窗口 A')
            b, tb = service.window(subject, '窗口 B')
            c, tc = service.window(subject, '窗口 C')
            own = service.tool(ta, 'report_state', state_text='我希望先核对这条记录的来源。',valence=.4,load=12)
            service.tool(tb, 'report_state',state_text='本次先保留自己的判断。',cause_unknown=True)
            service.tool(tc, 'report_state',state_text='希望保留清晰的互动记录。')
            service.tool(ta,'propose_shared_memory',event_id=own['event_id'])
            service.tool(tb,'decide_inheritance',event_id=own['event_id'],decision='partial',note='采纳核对来源的建议')
            service.tool(tc,'decide_inheritance',event_id=own['event_id'],decision='defer')
            req = service.tool(tb,'express_boundary',text='我想先暂停这个话题。',reason='浏览器验收用例')
            service.api('settings',{'observation_enabled':True})
            service.observation({'source':'agent_visible_text','instance_id':a['instance_id'],'text':'网页观察测试原文'})
            service.api('observations',{'source':'user_annotation','instance_id':a['instance_id'],'text':'用户批注测试原文'})
            service.api('observations',{'source':'model_estimated','instance_id':a['instance_id'],'event_id':own['event_id']})
            service.api('runtime/sample',{'instance_id':a['instance_id']})
            page = open_page(browser,subject)
            expect(page.locator('.hero')).to_contain_text('分身协议验收')
            expect(page.locator('.hero')).to_contain_text('已收到 AI 自主写入')
            capture(page,'dashboard-fixture.jpg')
            page.locator('[data-act=go][data-val=requests]').first.click()
            page.locator('[data-act=request]').first.click()
            expect(page.locator('dialog')).to_contain_text('我想先暂停这个话题。')
            expect(page.locator('dialog')).to_contain_text('AI 通过 MCP 自主填写')
            page.locator('[data-act=request-stage][data-val$="|DECLINED"]').click()
            page.locator('dialog button[type=submit]').click()
            expect(page.locator('body')).to_contain_text('用户不同意')
            status = service.tool(tb,'get_request_status',request_id=req['event_id'])
            assert status['stage']=='DECLINED' and status['original']['payload']['text']=='我想先暂停这个话题。'
            checks.append('G/H: original text, source, presented and declined through UI, confirmed by independent MCP read')
            if page.locator('dialog').is_visible():
                page.locator('dialog [data-act=close]').first.click()
            page.locator('[data-act=go][data-val=events]').first.click()
            for source in ['AI 通过 MCP 自主填写','网页可见陈述','实际运行观测','模拟状态模型','用户注释']:
                expect(page.locator('.event-head .badge').filter(has_text=source).first).to_be_visible()
            capture(page,'dashboard-sources.jpg')
            checks.append('Q: five real API sources rendered as distinct event badges')
            page.locator('[data-act=go][data-val=settings]').first.click()
            expect(page.locator('h1')).to_contain_text('设置')
            page.locator('[data-act=go][data-val=about]').first.click()
            expect(page.locator('#content')).to_contain_text('网页观察需获得站点权限和窗口绑定')
            checks.append('O: actual browser loaded the dashboard and displayed observation permission and binding rules; extension separately tested')
            page.close()
            browser.close()
            service.stop()
            service.start()
            browser = pw.chromium.launch(**launch)
            page = open_page(browser,subject)
            page.locator('[data-act=go][data-val=requests]').first.click()
            expect(page.locator('.item')).to_contain_text('用户不同意')
            expect(page.locator('.item')).to_contain_text('我想先暂停这个话题。')
            checks.append('J: all test browser windows closed; service and browser restarted; same request + durable reply rendered')
            browser.close()
            result = {'browser':browser_version,'passed':checks}
            if output: (output/'browser-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:
            service.stop()


if __name__=='__main__':
    main()
