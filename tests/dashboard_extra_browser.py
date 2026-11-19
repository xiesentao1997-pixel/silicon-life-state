"""Optional real-browser owner-operation tests. Uses a fresh temporary service."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from acceptance_support import Local


def main():
    from playwright.sync_api import expect, sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    passed = []
    with tempfile.TemporaryDirectory(prefix="sls-owner-ui-") as directory, sync_playwright() as pw:
        service = Local(directory).start()
        try:
            launch = {"executable_path": os.environ["SILICON_CHROMIUM"]} if os.getenv("SILICON_CHROMIUM") else {}
            browser = pw.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="zh-CN")
            js_errors = []
            page.on("pageerror", lambda exc: js_errors.append(str(exc)))
            code = service.api("pair/code", {"target": "dashboard"})["code"]
            page.goto(service.base + "/#pair=" + code)
            page.locator(".hero [data-act=make-subject]").click()
            form = page.locator("dialog form")
            form.locator("[name=name]").fill("本机界面验收")
            form.locator("button[type=submit]").click()
            expect(page.locator(".hero h2")).to_have_text("本机界面验收")
            sid = service.api("subjects")["subjects"][0]["subject_id"]
            page.locator(".nav-item[data-val=instances]").click()
            page.locator("[data-act=make-instance]").click()
            form.locator("[name=name]").fill("界面窗口")
            form.locator("button[type=submit]").click()
            expect(page.locator("#content [data-act=issue]")).to_be_visible()
            snap = service.api("snapshot?subject_id=" + sid)
            assert len(snap["instances"]) == 1
            iid = snap["instances"][0]["instance_id"]
            passed.append("UI created a subject and independent instance; verified through owner API")

            page.locator("[data-act=issue]").click()
            form.locator("button[type=submit]").click()
            expect(page.locator("#dialog-title")).to_have_text("MCP 分身凭据")
            config = json.loads(page.locator("dialog pre").text_content())["mcpServers"]["silicon-life-state"]
            assert Path(config["command"]).is_absolute() and Path(config["args"][0]).is_absolute()
            assert config["env"]["SILICON_MCP_URL"] == service.base + "/mcp"
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "clientInfo": {"name":"dashboard-qa","version":"1"}, "capabilities":{}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name":"get_own_state","arguments":{}}},
            ]
            child = subprocess.run([config["command"], *config["args"]], env={**os.environ, **config["env"]},
                                   input="".join(json.dumps(message)+"\n" for message in requests),
                                   text=True, encoding="utf-8", capture_output=True, check=True, timeout=20)
            answer = next(row for row in map(json.loads, child.stdout.splitlines()) if row["id"] == 2)
            assert answer["result"]["structuredContent"]["instance_id"] == iid
            page.locator("dialog [data-act=close]").first.click()
            page.locator(".nav-item[data-val=settings]").click()
            page.locator("[data-act=revoke-agent]").click()
            form.locator("button[type=submit]").click()
            expect(page.get_by_text("暂无分身凭据")).to_be_visible()
            assert not service.api("credentials")["grants"]
            passed.append("UI issued and revoked a real scoped credential")

            page.locator("[data-act=issue]").click()
            form.locator("[name=transport]").select_option("http")
            form.locator("button[type=submit]").click()
            expect(page.locator("#dialog-title")).to_have_text("MCP 分身凭据")
            config = json.loads(page.locator("dialog pre").text_content())["mcpServers"]["silicon-life-state"]
            assert config["url"] == service.base + "/mcp" and config["headers"]["Authorization"].startswith("Bearer ")
            grant = config["headers"]["Authorization"].removeprefix("Bearer ")
            page.locator("dialog [data-act=close]").first.click()
            service.tool(grant, "report_state", state_text="用于检查窄屏呈现的自主报告。", valence=.25, load=20)
            passed.append("Generated stdio config started its exact command and read same instance; generated HTTP config wrote a report")
            page.locator(".nav-item[data-val=overview]").click()
            expect(page.locator(".big-quote").first).to_have_text("用于检查窄屏呈现的自主报告。", timeout=10000)
            page.locator("[data-act=theme]").click()
            expect(page.locator("html")).to_have_attribute("data-theme", "cream")
            if args.output:
                page.screenshot(path=str(args.output/"dashboard-cream.jpg"), type="jpeg", quality=86)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator(".mobile-menu").click()
            page.locator(".nav-item[data-val=backup]").click()
            expect(page.locator("h1")).to_have_text("导出与备份")
            passed.append("Cream theme and 390px layout with keyboard-accessible mobile navigation")

            page.locator("[data-act=backup]").click()
            expect(page.locator("[data-act=restore]")).to_have_count(1)
            page.locator('[data-act=delete][data-val=session]').click()
            form.locator("[name=confirm]").fill("删除")
            form.locator("button[type=submit]").click()
            expect(page.get_by_text("暂无受管备份")).to_be_visible()
            snap = service.api("snapshot?subject_id=" + sid)
            assert not snap["events"] and not snap["sessions"]
            assert not service.api("backups")["backups"]
            passed.append("UI created managed backup and deleted a session, verified record and backup removal")
            assert not js_errors, js_errors
            data = {"browser": browser.version, "passed": passed, "page_errors": js_errors}
            if args.output:
                (args.output/"dashboard-extra-acceptance.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            browser.close()
        finally:
            service.stop()


if __name__ == "__main__":
    main()
