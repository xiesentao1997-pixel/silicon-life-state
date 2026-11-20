"""Real panel, SQLite and HTTP with fixture Chrome tab/storage APIs in Chromium.

The test profile is disposable. An 11-minute backdate of one code's expiration
exercises expiry deterministically; no system clock or live user record is changed.
Run SILICON_CHROMIUM=/usr/bin/chromium python tests/extension_pair_recovery.py
"""
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import re
import tempfile
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from acceptance_support import Local, ROOT


def exercise(browser, local):
    context = browser.new_context()
    panel = context.new_page()
    ext = ROOT / "apps" / "extension"
    fixture = "/__extension_pair_fixture__/"
    def asset(route):
        file = (ext / urlsplit(route.request.url).path.removeprefix(fixture)).resolve()
        if ext not in file.parents or not file.is_file():
            route.abort()
            return
        route.fulfill(path=file, content_type=mimetypes.guess_type(str(file))[0])
    panel.route(local.base + fixture + "**", asset)
    identity = "a" * 32
    headers = {"X-SLS-Extension": identity, "Origin": "chrome-extension://" + identity}
    calls = []
    def server(route):
        request = route.request
        path = urlsplit(request.url).path
        calls.append((request.method, path))
        token = request.headers.get("authorization", "").removeprefix("Bearer ") or None
        data = json.loads(request.post_data) if request.post_data else None
        status, payload = local.raw(path, data, token, headers)
        route.fulfill(status=status, json=payload)
    panel.route(local.base + "/api/**", server)

    panel.add_init_script("""
       const listener = {addListener(){}}, local = {}, tab = {id:20,windowId:1,url:location.origin+'/'};
       window.nav = []; window.dashboardTabs=[{id:2,windowId:1,url:'http://127.0.0.1:1/'},tab];
       Object.assign(window.chrome,{
         runtime:{id:'a'.repeat(32)},storage:{
           local:{get:async()=>({...local}),set:async o=>Object.assign(local,o),setAccessLevel:async()=>{}},
           session:{get:async()=>({})},onChanged:listener},
         windows:{getCurrent:async()=>({id:1}),update:async()=>{}},
         tabs:{query:async q=>q.url?window.dashboardTabs:[tab],get:async()=>tab,
           update:async(id,conf)=>window.nav.push({id,...conf}),create:async conf=>window.nav.push(conf),
           onActivated:listener,onUpdated:listener},
         permissions:{contains:async()=>false,onAdded:listener,onRemoved:listener}
       });
    """)
    panel.goto(local.base + fixture + "panel.html")
    expect(panel.locator("#connection")).to_have_text("等待配对")
    panel.locator("#pair-form summary").click()
    panel.locator("#port").fill(str(urlsplit(local.base).port))

    stale = local.ready["extension_code"]
    with sqlite3.connect(local.directory / "browser-access.sqlite3") as db:
        count = db.execute("UPDATE codes SET expires=expires-660 WHERE hash=?",
                           (hashlib.sha256(stale.encode()).hexdigest(),)).rowcount
        assert count == 1
    def submit(code):
        panel.locator("#code").fill(code)
        panel.locator("#pair-form button").click()
    submit(stale)
    expect(panel.locator("#feedback")).to_contain_text("配对码已过期")
    expect(panel.locator("#code")).to_have_value("")
    other = local.api("pair/code", {"target":"dashboard"})["code"]
    submit(other)
    expect(panel.locator("#feedback")).to_contain_text("插件专用配对码")
    used = local.api("pair/code", {"target":"extension"})["code"]
    assert local.raw("/api/pair", {"code":used}, headers=headers)[0] == 200
    submit(used)
    expect(panel.locator("#feedback")).to_contain_text("配对码已使用")

    # Window lookup is simulated. The resulting link is navigated in an actual
    # browser; this click must never use an authenticated API from the extension.
    before = list(calls)
    panel.locator("#recover-pair").click()
    panel.wait_for_function("nav.length===1")
    nav = panel.evaluate("nav[0]")
    assert nav["id"] == 20 and nav["active"]
    assert nav["url"] == local.base + "/#view=settings&action=pair-extension"
    panel.evaluate("dashboardTabs=[]")
    panel.locator("#recover-pair").click()
    panel.wait_for_function("nav.length===2")
    assert panel.evaluate("nav[1]") == {"url":nav["url"]}
    assert calls == before

    owner = context.new_page()
    grant = local.api("pair/code", {"target":"dashboard"})["code"]
    owner.goto(local.base + "/#pair=" + grant)
    owner.wait_for_function("!!localStorage.getItem('sls-dashboard-binding')")
    issued = []
    owner.on("request", lambda req: issued.append(req.url) if req.url == local.base + "/api/pair/code" else None)
    owner.goto(nav["url"])
    new_code_button = owner.locator("#dialog [data-act=pair-extension]")
    expect(new_code_button).to_be_visible()
    assert not issued
    new_code_button.click()
    code = owner.locator("[data-pair-code]").inner_text()
    assert len(issued) == 1
    owner.bring_to_front()
    countdown = owner.locator("[data-pair-countdown]")
    initial_time = countdown.inner_text()
    assert re.fullmatch(r"(10:00|09:[0-5][0-9])", initial_time), initial_time
    expect(countdown).not_to_have_text(initial_time, timeout=5000)
    # Independent deterministic browser expiry case. The separate elapsed-time
    # acceptance test keeps the original service up for its real ten-minute TTL.
    with sqlite3.connect(local.directory / "browser-access.sqlite3") as db:
        db.execute("UPDATE codes SET expires=expires-601 WHERE hash=?",
                   (hashlib.sha256(code.strip().encode()).hexdigest(),))
    expect(countdown).to_have_text("00:00", timeout=12000)
    expect(owner.locator("[data-pair-state]")).to_contain_text("已过期")
    expect(owner.locator("#dialog [data-act=copy]")).to_be_disabled()
    expect(owner.locator("[data-pair-code]")).to_be_hidden()
    owner.locator("#dialog [data-act=regenerate-pair-code]").click()
    expect(owner.locator("[data-pair-code]")).to_be_visible()
    new_code = owner.locator("[data-pair-code]").inner_text().strip()
    assert new_code and new_code != code.strip()
    assert len(issued) == 2
    submit(new_code)
    expect(panel.locator("#connection")).to_have_text("本地已连接")
    print("PASS · Chromium", browser.version, "real side-panel and dashboard, SQLite and authenticated HTTP; fixture tab/storage APIs")
    print("PASS · expired/used/wrong-target messages; no credential request from unpaired extension; existing tab and fresh tab recovery; owner issue and new pairing")
    print("PASS · service-timed countdown ticked, expired display and copy cleared, authenticated regenerate issued a working replacement")
    context.close()


def main():
    with tempfile.TemporaryDirectory(prefix="sls-extension-pair-") as directory:
        local = Local(Path(directory)).start()
        try:
            with sync_playwright() as pw:
                launch = {"channel": "chromium", "headless": True}
                if os.getenv("SILICON_CHROMIUM"):
                    launch["executable_path"] = os.environ["SILICON_CHROMIUM"]
                browser = pw.chromium.launch(**launch)
                try:
                    exercise(browser,local)
                finally:
                    browser.close()
        finally:
            local.stop()


if __name__ == "__main__":
    main()
