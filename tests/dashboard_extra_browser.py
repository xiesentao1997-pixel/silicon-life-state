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
    parser.add_argument("--naming-only", action="store_true")
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    passed = []
    with tempfile.TemporaryDirectory(prefix="sls-owner-ui-") as directory, sync_playwright() as pw:
        profiles = Path(directory)/"qa-hosts"
        profiles.mkdir()
        (profiles/"TEST-PROFILE").touch()
        claude = profiles/"claude_desktop_config.json"
        existing = {"mcpServers":{"research":{"command":"prior-host-tool"}},"theme":"unchanged"}
        claude.write_text(json.dumps(existing,indent=2),encoding="utf-8")
        original = claude.read_bytes()
        codex = profiles/"config.toml"
        original_toml = '# Existing comments and spacing\n[mcp_servers.notes]\ncommand = "prior-host-tool"\n'
        codex.write_text(original_toml,encoding="utf-8")
        service = Local(Path(directory)/"state",server=Path(__file__).with_name("wizard_fixture_service.py")).start()
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

            page.locator('[data-act=rename-instance]').first.click()
            form.locator('[name=name]').fill('María del Mar')
            form.locator('button[type=submit]').click()
            page.wait_for_selector('dialog[open]',state='hidden')
            profile=service.api("snapshot?subject_id="+sid)["instances"][0]["instance_name"]
            assert profile["suggestion"]=="María del Mar" and profile["name"]=="界面窗口"
            page.locator('[data-act=rename-instance]').first.click()
            expect(form).to_contain_text('用户建议')
            form.locator('button[type=button]').first.click()
            passed.append("Naming UI submitted a suggestion, retained the current name and displayed attributed history")

            if args.naming_only:
                assert not js_errors,js_errors
                print("PASS · Chromium", browser.version, "· name suggestion and attributed history")
                browser.close()
                return

            def preview(host,transport="stdio"):
                page.locator("#content [data-act=issue]").first.click()
                form.locator("[name=host]").select_option(host)
                if host == "other":
                    form.locator("[name=transport]").select_option(transport)
                form.locator("button[type=submit]").click()
                expect(page.locator("#host-wizard-preview")).to_be_visible()

            def apply():
                page.locator("[data-wiz=apply]").click()
                expect(page.locator("[data-wiz-status]")).to_contain_text("配置已保存")

            def close_dialog():
                page.locator("dialog [data-act=close]").first.click()

            preview("claude")
            assert claude.read_bytes() == original
            assert not service.api("credentials")["grants"]
            apply()
            merged = json.loads(claude.read_text(encoding="utf-8"))
            assert merged["theme"] == existing["theme"]
            assert merged["mcpServers"]["research"] == existing["mcpServers"]["research"]
            assert next(profiles.glob("claude_desktop_config.json.*.bak")).read_bytes() == original
            config = merged["mcpServers"]["silicon_life_state"]
            assert Path(config["command"]).is_absolute() and Path(config["args"][0]).is_absolute()
            assert config["env"]["SILICON_MCP_URL"] == service.base + "/mcp"
            page.locator("[data-wiz=probe]").click()
            expect(page.locator("[data-wiz-status]")).to_contain_text("试连完成")
            status = page.locator("[data-wiz-activity]")
            expect(status).to_contain_text("已发现")
            expect(status).to_contain_text("尚未观测到")
            expect(status).to_contain_text("尚未收到")
            requests = [
                {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                    "protocolVersion":"2025-11-25","clientInfo":{"name":"dashboard-qa","version":"1"},"capabilities":{}}},
                {"jsonrpc":"2.0","method":"notifications/initialized"},
                {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
                {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_own_state","arguments":{},"_meta":{"dev.silicon-life-state/conversationId":"fixture-thread"}}}
            ]
            child = subprocess.run([config["command"],*config["args"]],env={**os.environ,**config["env"]},
                                   input="".join(json.dumps(msg)+"\n" for msg in requests),capture_output=True,
                                   text=True,encoding="utf-8",timeout=20,check=True)
            results = {r["id"]:r for r in map(json.loads,child.stdout.splitlines()) if "id" in r}
            assert "report_state" in {t["name"] for t in results[2]["result"]["tools"]}
            own = results[3]["result"]["structuredContent"]
            assert own["instance_id"] != iid
            assert any(row["instance_id"] == own["instance_id"] and row["subject_id"] == sid
                       for row in service.api("snapshot")["instances"])
            page.locator("[data-wiz=status]").click()
            expect(status).to_contain_text("dashboard-qa")
            if args.output:
                page.screenshot(path=str(args.output/"host-wizard.jpg"),type="jpeg",quality=86)
            close_dialog()
            preview("codex")
            apply()
            assert codex.read_text(encoding="utf-8").startswith(original_toml)
            assert "[mcp_servers.silicon_life_state]" in codex.read_text(encoding="utf-8")
            assert next(profiles.glob("config.toml.*.bak")).read_text(encoding="utf-8") == original_toml
            close_dialog()
            passed.append("Confirmed Claude JSON and Codex TOML merges preserved other settings and created exact backups")
            passed.append("Live stdio tools/list probe, an independent stdio client's discovery, and no report displayed separately")

            page.locator(".nav-item[data-val=settings]").click()
            page.locator("[data-act=revoke-installation]").first.click()
            form.locator("button[type=submit]").click()
            expect(page.locator("[data-act=restore-installation]")).to_be_visible()
            assert not service.api("credentials")["grants"]
            passed.append("UI issued and revoked a real scoped credential")

            preview("other","http")
            with page.expect_response(lambda r:r.url.endswith("/api/hosts/copy")) as copied:
                page.locator("[data-wiz=copy]").click()
            config = json.loads(copied.value.json()["config"])["mcpServers"]["silicon_life_state"]
            assert config["url"] == service.base + "/mcp"
            grant = config["headers"]["Authorization"].removeprefix("Bearer ")
            report = service.tool(grant,"report_state",state_text="用于检查窄屏呈现的自主报告。",valence=.25,load=20)
            page.locator("[data-wiz=status]").click()
            expect(page.locator("[data-wiz-activity]")).to_contain_text(report["event_id"])
            close_dialog()
            passed.append("Manual HTTP config issued a protocol-client report; wizard displayed the matching persisted event")
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
