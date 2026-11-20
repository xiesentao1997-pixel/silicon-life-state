"""Exercise real clients against an isolated, temporary database.

Run with the test extra, Codex CLI, and the official MCP 2026-07-28 schema.json:
    python tests/verify_mcp_clients.py --schema /path/to/schema.json
No personal host configuration, provider login or model invocation is required.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import version

from acceptance_support import Local, PROTOCOL, ROOT, fresh

SERVER = "silicon_life_state"


def modern_http(local, token, schema_path):
    from jsonschema import Draft202012Validator
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    prefix = "io.modelcontextprotocol/"

    def rpc(method, result_type, params=None):
        meta = {prefix+"protocolVersion":PROTOCOL, prefix+"clientCapabilities":{}}
        request = {"jsonrpc":"2.0", "id":fresh(), "method":method, "params":{"_meta":meta, **(params or {})}}
        headers = {"MCP-Protocol-Version":PROTOCOL, "Mcp-Method":method, "Accept":"application/json, text/event-stream"}
        if method == "tools/call":
            headers["Mcp-Name"] = params["name"]
        status, response = local.raw("/mcp", request, token, headers)
        assert status == 200 and response["id"] == request["id"], (method, status)
        validator = Draft202012Validator({"$defs":schema["$defs"], "$ref":"#/$defs/"+result_type})
        result = response["result"]
        validator.validate(result)
        if method != "tools/call":
            assert (result["ttlMs"], result["cacheScope"]) == (0, "private")
        else:
            assert not result.get("isError"), result
        return result

    discovery = rpc("server/discover", "DiscoverResult")
    assert PROTOCOL in discovery["supportedVersions"]
    tools = rpc("tools/list", "ListToolsResult")["tools"]
    assert "report_state" in {entry["name"] for entry in tools}
    payload = {"idempotency_key":fresh(), "state_text":"Modern HTTP protocol-client acceptance fixture"}
    report = rpc("tools/call", "CallToolResult", {"name":"report_state", "arguments":payload})
    read = rpc("tools/call", "CallToolResult", {"name":"get_own_state", "arguments":{}})
    event_id = report["structuredContent"]["event_id"]
    assert read["structuredContent"]["state"]["event_id"] == event_id
    return {"result":"PASS", "protocol":PROTOCOL, "tools":len(tools), "event_id":event_id,
            "schema":"modelcontextprotocol/modelcontextprotocol schema/2026-07-28/schema.json"}


def native_codex(local, subject, temporary_home):
    codex = shutil.which("codex")
    if not codex:
        return {"result":"NOT_RUN", "reason":"Codex CLI is unavailable"}
    cli = subprocess.check_output([codex, "--version"], text=True).strip()
    plan = local.api("hosts/preview", {"subject_id":subject, "host":"codex", "transport":"stdio"})
    assert Path(plan["target"]) == temporary_home / "config.toml"
    applied = local.api("hosts/apply", {"plan_id":plan["plan_id"], "confirm":True})
    assert Path(applied["target"]).is_file()
    grants = local.api("installations")["installations"]
    assert len(grants) == 1 and grants[0]["subject_id"] == subject
    env = {key:value for key,value in os.environ.items() if key in
           ("PATH","LANG","TMPDIR","TEMP","TMP","SYSTEMROOT","WINDIR","PATHEXT","USER")}
    env.update(HOME=str(temporary_home), CODEX_HOME=str(temporary_home))
    proc = subprocess.Popen([codex, "app-server", "--stdio"], cwd=temporary_home, env=env,
                            text=True, encoding="utf-8", bufsize=1, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    inbox = queue.Queue()

    def read_messages():
        for line in proc.stdout:
            inbox.put(json.loads(line))
        inbox.put(None)

    reader = threading.Thread(target=read_messages, daemon=True)
    reader.start()

    awaiting = {}

    def receive(rid):
        deadline = time.monotonic()+45
        while rid not in awaiting:
            message = inbox.get(timeout=max(0, deadline-time.monotonic()))
            if message is None:
                raise RuntimeError("Codex app-server ended before receiving response "+str(rid))
            if "id" in message:
                awaiting[message["id"]] = message
        reply = awaiting.pop(rid)
        if "error" in reply:
            raise RuntimeError(f"Codex request {rid}: {reply['error'].get('message')}")
        return reply["result"]

    def request(method, params, rid=None, *, defer=False):
        msg = {"method":method, "params":params}
        if rid is not None:
            msg["id"] = rid
        proc.stdin.write(json.dumps(msg)+"\n")
        proc.stdin.flush()
        if rid is not None and not defer:
            return receive(rid)

    try:
        request("initialize", {"clientInfo":{"name":"silicon-life-acceptance","version":"1.0.2"},
                               "capabilities":{"experimentalApi":True}}, 1)
        request("initialized", {})
        def call(thread_id, name, args, rid):
            endpoint = {"threadId":thread_id, "server":SERVER, "tool":name, "arguments":args}
            reply = request("mcpServer/tool/call", endpoint, rid)
            assert not reply.get("isError"), reply
            return json.loads(reply["content"][0]["text"])

        threads, records = [], []
        texts = ("有些难过", "很开心", "不确定")
        for index in range(len(texts)):
            base = 10+index*10
            thread = request("thread/start", {"environments":[], "cwd":str(temporary_home)}, base)
            tid = thread["thread"]["id"]
            threads.append(tid)
            inventory = request("mcpServerStatus/list", {"threadId":tid,"serverName":SERVER}, base+1)
            tool_names = inventory["data"][0]["tools"]
            assert {"report_state", "open_conversation"}.issubset(tool_names)
        # Queue all three original writes before consuming any responses.
        for index, (tid, text) in enumerate(zip(threads,texts)):
            args = {"state_text":text, "shared_to_subject":True, "idempotency_key":fresh()}
            request("mcpServer/tool/call", {"threadId":tid, "server":SERVER, "tool":"report_state",
                                            "arguments":args}, 40+index, defer=True)
        for index, (tid, text) in enumerate(zip(threads,texts)):
            reply = receive(40+index)
            assert not reply.get("isError"), reply
            report = json.loads(reply["content"][0]["text"])
            assert report["subject_id"] == subject and report["payload"]["state_text"] == text
            records.append({key:report[key] for key in ("instance_id", "event_id")})
            assert call(tid, "get_own_state", {}, 43+index)["state"]["event_id"] == report["event_id"]
        assert len({r["instance_id"] for r in records}) == 3
        memory = call(threads[2], "read_subject_memory", {}, 60)
        assert {row["state_text"]:row["count"] for row in memory["summary"]["distribution"]} == dict.fromkeys(texts,1)
        assert call(threads[1], "rename_instance", {"name":"B 新名", "idempotency_key":fresh()}, 61)["name"] == "B 新名"
        assert records[1]["event_id"] in {e["event_id"] for e in call(threads[1], "read_event_history", {}, 62)["events"]}
        decision = call(threads[2], "decide_inheritance", {"decision":"disagree", "event_id":records[0]["event_id"],
                                                          "note":"保留独立判断", "idempotency_key":fresh()}, 63)
        assert decision["instance_id"] == records[2]["instance_id"]
        assert call(threads[2], "get_own_state", {}, 64)["state"]["event_id"] == records[2]["event_id"]
        # Give the isolated test thread a local conversation history so Codex can resume it.
        # No provider call or model-generated state is involved.
        tid = threads[0]
        request("thread/inject_items", {"threadId":tid, "items":[
            {"type":"message", "role":"user", "content":[{"type":"input_text","text":"Local acceptance fixture"}]}]}, 50)
        request("thread/unsubscribe", {"threadId":tid}, 51)
        resumed = request("thread/resume", {"threadId":tid}, 52)["thread"]["id"]
        assert resumed == tid
        reread = call(resumed, "get_own_state", {}, 53)
        assert reread["instance_id"] == records[0]["instance_id"]
        assert reread["state"]["event_id"] == records[0]["event_id"]
        return {"result":"PASS", "client":cli, "entry":"app-server stdio", "tools":len(tool_names),
                "installation_grants":len(grants), "configuration":"dashboard wizard", "threads":len(threads), "records":records, "resume_thread_A":"PASS",
                "concurrent_reports":"PASS", "distribution":"PASS", "rename_B":"PASS", "dissent_C":"PASS",
                "model_turn":"NOT_RUN", "report_origin":"test operator"}
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        reader.join(timeout=2)
        proc.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        temporary_home = work/"codex"
        temporary_home.mkdir(mode=0o700)
        local = Local(work/"db", env={"CODEX_HOME":str(temporary_home)}).start()
        try:
            subject = local.subject()
            _, modern_token = local.window(subject, "Modern HTTP")
            _, sdk_token = local.window(subject, "Python SDK")
            modern = modern_http(local, modern_token, args.schema)
            sdk = subprocess.run([sys.executable, str(ROOT/"packages/agent-example/verify_sdk.py")],
                                 env={**os.environ, "SILICON_MCP_URL":local.base+"/mcp",
                                      "SILICON_AGENT_TOKEN":sdk_token}, capture_output=True, text=True, timeout=30)
            if sdk.returncode:
                raise RuntimeError(sdk.stderr)
            sdk_result = {**json.loads(sdk.stdout), "sdk_version":version("mcp")}
            native = native_codex(local, subject, temporary_home)
            print(json.dumps({"modern_http":modern, "python_sdk":sdk_result, "native_codex":native,
                              "claude_desktop":"NOT_RUN", "cursor":"NOT_RUN"}, indent=2))
        finally:
            local.stop()


if __name__ == "__main__":
    main()
