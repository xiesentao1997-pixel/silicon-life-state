"""Real unpacked MV3 + real service. All data, browser profile and page fixtures are disposable.

Run: python -m pip install playwright && python -m playwright install chromium
     python tests/extension_browser.py
Set SILICON_CHROMIUM to use an installed Chromium executable. No live AI provider is used.
"""
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps" / "extension"
sys.path.insert(0, str(ROOT / "packages" / "mcp-server"))
from local_client import message, send


def verify_adapters(context):
    """Run the released selection readers inside a real renderer on narrowly scoped fixtures."""
    for platform, host, assistant in [
          ("chatgpt","chatgpt.com",'<div data-message-author-role="assistant"><p class="markdown">'),
          ("claude","claude.ai",'<div data-testid="assistant-message"><p>'),
          ("gemini","gemini.google.com",'<model-response><message-content><p>')]:
        page=context.new_page()
        body = assistant + '<span id="selected">可见原文</span><span hidden>私密</span>。' + (
            '</p></message-content></model-response></div><aside id="other">用户输入</aside>')
        page.route("https://"+host+"/**",lambda route: route.fulfill(content_type="text/html; charset=utf-8",body=body))
        page.goto("https://"+host+"/fixture")
        def read(selector):
            page.locator(selector).evaluate("""e=>{const r=document.createRange();r.selectNodeContents(e);
                getSelection().removeAllRanges();getSelection().addRange(r)}""")
            page.evaluate((EXT / "adapters" / (platform + ".js")).read_text())
            return page.evaluate((EXT / "adapters/read.js").read_text())
        result=read("p")
        assert result["text"]=="可见原文。" and result["adapter"]==platform
        assert "error" in read("#other")
        page.close()


def adapter_only():
    from playwright.sync_api import sync_playwright

    options = {"channel":"chromium", "headless":True}
    if os.getenv("SILICON_CHROMIUM"):
        options["executable_path"] = os.environ["SILICON_CHROMIUM"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**options)
        try:
            context = browser.new_context()
            verify_adapters(context)
            print("PASS · Chromium " + browser.version + " · ChatGPT / Claude / Gemini visible-only DOM fixtures, assistant and non-assistant selections")
        finally:
            browser.close()


def verify_sidebar_with_host_fixture(pw, base, owner, subject, instance, request, api):
    """Render released panel files; simulate Chrome APIs but use real same-origin owner REST."""
    from playwright.sync_api import expect
    options = {"channel":"chromium","headless":True}
    if os.getenv("SILICON_CHROMIUM"):
        options["executable_path"] = os.environ["SILICON_CHROMIUM"]
    browser = pw.chromium.launch(**options)
    try:
        page = browser.new_page(viewport={"width":390,"height":885}, color_scheme="dark")
        path_prefix = "/__sls_sidebar_fixture__/"
        def asset(route):
            relative = urlsplit(route.request.url).path.removeprefix(path_prefix)
            path = (EXT / relative).resolve()
            if EXT not in path.parents or not path.is_file():
                route.fulfill(status=404)
                return
            route.fulfill(path=path,content_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        page.route(base + path_prefix + "**", asset)
        binding = {"subject_id":subject["subject_id"],"instance_id":instance["instance_id"],
                   "page":hashlib.sha256(b"https://chatgpt.com/fixture").hexdigest()}
        settings = {"port":int(urlsplit(base).port),"token":owner,"binding":binding}
        shim = """
            const listener = {addListener(){}};
            const tab = {id:71,url:"https://chatgpt.com/fixture"};
            const local = {port:settings.port,token:settings.token};
            Object.assign(window.chrome, {
                runtime:{id:"a".repeat(32)},
                windows:{getCurrent:async()=>({id:1})},
                tabs:{get:async()=>tab,query:async()=>[tab],onActivated:listener,onUpdated:listener},
                storage:{local:{get:async()=>({...local})},
                    session:{get:async()=>({"binding:71":settings.binding})},onChanged:listener},
                permissions:{contains:async()=>false,onAdded:listener,onRemoved:listener}
            });
            // The fixture authenticates as the real dashboard owner in the regular browser
            // origin. Only unpacked extension tests exercise Chrome's actual Origin header.
            const network = window.fetch.bind(window);
            window.fetch = (url,opts={})=>{
                if(new URL(url,location.href).origin !== location.origin) throw new Error("External fixture request");
                const headers = new Headers(opts.headers);
                headers.delete("X-SLS-Extension");
                return network(url,{...opts,headers});
            };
        """
        page.add_init_script(script="(() => { const settings = " + json.dumps(settings) + ";" + shim + " })()")
        page.goto(base + path_prefix + "panel.html?tab=71")
        expect(page.locator("#connection")).to_have_text("本地已连接")
        expect(page.locator("#state-text")).to_have_text("MCP 协议客户端验收记录")
        expect(page.locator("#mode")).to_contain_text("网页观察模式：尚未建立 AI 直接写入连接。")
        expect(page.locator("#channel")).to_contain_text("分身最近一次通过 MCP 成功写入")
        page.locator("#requests summary").click()
        expect(page.locator("#requests blockquote")).to_have_text("本次验收希望调整节奏")
        page.get_by_role("button",name="不同意",exact=True).click()
        expect(page.locator("#requests summary")).to_contain_text("不同意")
        item = next(r for r in api("snapshot", token=owner)["requests"] if r["request_id"] == request["event_id"])
        assert item["stage"]=="DECLINED"
        screenshot = os.getenv("SILICON_EXTENSION_SCREENSHOT")
        if screenshot:
            page.screenshot(path=screenshot,full_page=True)
        print("PASS · Chromium "+browser.version+" · released side-panel UI; simulated Chrome host APIs, real same-origin owner API/SQLite/MCP protocol-client report: direct and observation labels, request presentation and declined response")
    finally:
        browser.close()


def main(sidebar_fixture=False):
    from playwright.sync_api import expect, sync_playwright

    with tempfile.TemporaryDirectory(prefix="sls-ext-") as directory:
        root = Path(directory)
        with subprocess.Popen([sys.executable, str(ROOT / "apps/local-service/server.py"),
                               "--port", "0", "--data-dir", str(root / "db"), "--json-ready",
                               "--no-browser"], stdout=subprocess.PIPE, text=True) as server:
            try:
                ready = json.loads(server.stdout.readline())
                base = ready["base_url"]
                os.environ["SILICON_MCP_URL"] = base + "/mcp"
                def api(path, body=None, token=None):
                    headers = {"Content-Type": "application/json"}
                    if token:
                        headers["Authorization"] = "Bearer " + token
                    req = urllib.request.Request(base + "/api/" + path, headers=headers,
                                                  data=None if body is None else json.dumps(body).encode())
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as res:
                        return json.load(res)
                def write(path, body, owner):
                    return api(path, {**body, "idempotency_key": uuid.uuid4().hex}, owner)
                owner = api("pair", {"code": ready["code"]})["token"]
                subject = write("subjects", {"name": "验收主体"}, owner)
                instance = write("instances", {"name":"窗口 A", "subject_id":subject["subject_id"]}, owner)
                grant = write("credentials", {"instance_id":instance["instance_id"], "subject_id":subject["subject_id"]}, owner)
                def model(name, **args):
                    reply = send(message("tools/call", {"name":name, "arguments":{**args,"idempotency_key":uuid.uuid4().hex}}),
                                 token=grant["token"])
                    assert "result" in reply and not reply["result"]["isError"], "MCP tool failed"
                    return reply["result"]["structuredContent"]
                report = model("report_state", state_text="MCP 协议客户端验收记录")
                request = model("express_boundary", text="本次验收希望调整节奏")
                with sync_playwright() as pw:
                    if sidebar_fixture:
                        verify_sidebar_with_host_fixture(pw,base,owner,subject,instance,request,api)
                        return
                    settings = dict(channel="chromium", headless=True,
                                    ignore_default_args=["--disable-extensions"], args=[
                                        "--enable-unsafe-extension-debugging", "--disable-extensions-except=" + str(EXT), "--load-extension=" + str(EXT)])
                    if os.getenv("SILICON_CHROMIUM"):
                        settings["executable_path"] = os.environ["SILICON_CHROMIUM"]
                    context = pw.chromium.launch_persistent_context(str(root / "profile"), **settings)
                    try:
                        # Recent Chromium builds expose a developer-test API for unpacked
                        # packages. Use it inside this new disposable test profile so
                        # installation failures produce the browser's actual diagnostic.
                        cdp = context.browser.new_browser_cdp_session()
                        try:
                            known = cdp.send("Extensions.getExtensions").get("extensions", [])
                            if not any(row.get("path") == str(EXT) and row.get("enabled", True) for row in known):
                                cdp.send("Extensions.loadUnpacked", {"path":str(EXT)})
                        except Exception as error:
                            print("Chromium unpacked-loader diagnostic:", error, flush=True)
                        worker = next(iter(context.service_workers), None) or context.wait_for_event("serviceworker", timeout=12000)
                        extension_id = worker.url.split("/")[2]
                        setup = worker.evaluate("() => chrome.sidePanel.getOptions({})")
                        assert setup["enabled"] and setup["path"] == "panel.html"
                        site = context.pages[0]
                        site.route("https://chatgpt.com/**", lambda route: route.fulfill(content_type="text/html",body="<p>Fixture</p>"))
                        response = site.goto("https://chatgpt.com/fixture")
                        assert response and response.ok
                        tab_id = worker.evaluate("async () => (await chrome.tabs.query({active:true,currentWindow:true}))[0].id")
                        panel = context.new_page()
                        panel.goto("chrome-extension://" + extension_id + "/panel.html?tab=" + str(tab_id))
                        panel.locator("#pair-form details summary").click()
                        panel.locator("#port").fill(base.rsplit(":",1)[1])
                        panel.locator("#code").fill(ready["extension_code"])
                        panel.locator("#pair-form button").click()
                        expect(panel.locator("#connection")).to_have_text("本地已连接")
                        panel.locator("#bind").click()
                        expect(panel.locator("#state-text")).to_have_text("MCP 协议客户端验收记录")
                        expect(panel.locator("#state-meta")).to_contain_text(report["event_id"])
                        pet_code = write("pair/code", {"target":"pet"}, owner)["code"]
                        reader = api("pet/pair", {"code":pet_code})["token"]
                        same = api("pet/feed", token=reader)["states"][0]
                        assert (same["event_id"], same["source"]) == (report["event_id"], report["source"])
                        expect(panel.locator("#mode")).to_contain_text("网页观察模式：尚未建立 AI 直接写入连接。")
                        assert not worker.evaluate("() => chrome.permissions.contains({origins:['https://chatgpt.com/*']})")
                        panel.locator("#requests summary").click()
                        expect(panel.locator("#requests blockquote")).to_have_text("本次验收希望调整节奏")
                        panel.get_by_role("button",name="不同意",exact=True).click()
                        expect(panel.locator("#requests summary")).to_contain_text("不同意")
                        item = next(r for r in api("snapshot", token=owner)["requests"] if r["request_id"] == request["event_id"])
                        assert item["stage"] == "DECLINED"
                        screenshot = os.environ.get("SILICON_EXTENSION_SCREENSHOT")
                        if screenshot:
                            panel.set_viewport_size({"width":390, "height":885})
                            panel.screenshot(path=screenshot, full_page=True)
                        with context.expect_page() as popup:
                            panel.locator("#open-mini").click()
                        expect(popup.value.locator("#state-text")).to_have_text("MCP 协议客户端验收记录")
                        with context.expect_page() as full:
                            panel.locator("#open-dashboard").click()
                        assert full.value.url.startswith(base + "/")
                        # Fixtures exercise the released DOM parsers in the actual rendering engine.
                        # Native host-permission prompt and signed-in sites require manual testing.
                        verify_adapters(context)
                        print("PASS · unpacked extension, real SQLite/MCP/sidebar pairing, binding, refusal, mini window, dashboard handoff, 3 rendered DOM fixtures")
                    finally:
                        context.close()
                        assert any(e["event_id"] == report["event_id"] for e in api("snapshot",token=owner)["events"])
            finally:
                server.terminate()


if __name__ == "__main__":
    if sys.argv[1:] == ["--adapters-only"]:
        adapter_only()
    else:
        main(sidebar_fixture=sys.argv[1:] == ["--sidebar-fixture"])
