"""Opt-in live host acceptance. Requires Codex CLI login and a dedicated test instance.

This launches a read-only Codex session. It transmits only the prompt and MCP inputs/results
to your configured Codex provider. Reserve a fresh, empty instance for this exercise.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"packages"/"mcp-server"))
from local_client import message, send

PROMPT = """You are testing a voluntary state-recording channel with a dedicated, empty instance.
The operator authorizes one short, local-only report on this acceptance exercise. If you choose
to record it, use the connected silicon_life_state MCP server's report_state tool exactly once.
Choose your own words for a present operational state, which may be entirely neutral, and your
own idempotency key of at least eight characters. There is no need to claim an emotion or
subjective experience. Do not start shell commands, modify files, contact other tools, or paste
a scripted answer. You may decline to make a report. Finish with the returned event_id if one
was written."""

def call(name,args):
    res=send(message("tools/call",{"name":name,"arguments":args}))
    if "error" in res or res["result"].get("isError"):
        raise ValueError("The authorized MCP instance could not be read")
    return res["result"]["structuredContent"]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",help="Optional model identifier enabled for this Codex account")
    p.add_argument("--timeout",type=int,default=120)
    options=p.parse_args()
    codex=shutil.which("codex")
    if not codex:
        p.exit(2,"NOT_RUN: Codex CLI is unavailable\n")
    try:
        before=call("get_own_state",{})
    except (ValueError,OSError) as exc:
        p.exit(2,"NOT_RUN: "+str(exc)+"\n")
    if before["state"] is not None:
        p.exit(2,"Use a dedicated instance without existing reports.\n")
    version=subprocess.run([codex,"--version"],capture_output=True,text=True,check=True).stdout.strip()
    setup=[
        "-c",'mcp_servers.silicon_life_state.command='+json.dumps(sys.executable),
        "-c",'mcp_servers.silicon_life_state.args='+json.dumps([str(ROOT/"packages"/"mcp-server"/"stdio.py")]),
        "-c",'mcp_servers.silicon_life_state.env_vars=["SILICON_AGENT_TOKEN", "SILICON_MCP_URL"]',
        "-c",'mcp_servers.silicon_life_state.required=true',
    ]
    env={**os.environ,"SILICON_MCP_URL":os.environ.get("SILICON_MCP_URL","http://127.0.0.1:47831/mcp")}
    with tempfile.TemporaryDirectory(prefix="sls-clean-host-") as empty_dir:
        cmd=[codex,"exec","--ignore-user-config","--skip-git-repo-check","--ephemeral",
             "-s","read-only","--color","never","--json","-C",empty_dir,*setup]
        if options.model:
            cmd.extend(["--model",options.model])
        try:
            result=subprocess.run([*cmd,PROMPT],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=options.timeout,env=env)
        except subprocess.TimeoutExpired:
            p.exit(2,"NOT_RUN: The host did not finish before the timeout; check the dedicated instance before retrying.\n")
    # Keep only whitelisted facts about the requested tool and the receipt. Never dump the
    # host environment, full host transcript, stderr or displayed terminal credentials.
    events=[]
    for line in result.stdout.splitlines():
        try:
            item=json.loads(line)
        except ValueError:
            continue
        if not isinstance(item,dict) or item.get("type")!="item.completed":
            continue
        detail=item.get("item",{})
        if detail.get("type")=="mcp_tool_call" and detail.get("tool")=="report_state" and detail.get("server")=="silicon_life_state":
            result_data=detail.get("result") or {}
            structured=result_data.get("structuredContent") or result_data.get("structured_content")
            if not isinstance(structured,dict):
                for chunk in result_data.get("content",[]):
                    if chunk.get("type")=="text":
                        try:
                            parsed=json.loads(chunk.get("text",""))
                        except (ValueError,TypeError):
                            continue
                        if isinstance(parsed,dict) and "event_id" in parsed:
                            structured=parsed
                            break
            event_id=structured.get("event_id") if isinstance(structured,dict) else None
            events.append({"server":detail["server"],"tool":detail["tool"],"status":detail.get("status"),"event_id":event_id})
    after=call("get_own_state",{})
    state=after["state"]
    valid=(state is not None and state["instance_id"]==before["instance_id"] and state["source"]=="agent_direct"
           and state["type"]=="report_state" and any(e["status"]=="completed" and e["event_id"]==state["event_id"] for e in events))
    diag=(result.stderr+" "+result.stdout).lower()
    reason=("Host application server could not initialize on this read-only filesystem (OS error 30)" if "read-only file system" in diag
            else "provider unavailable or model stream interrupted" if any(s in diag for s in ("failed to connect","stream disconnected","error sending request","websocket","connection refused","token refresh","unexpected status","401 unauthorized","403 forbidden"))
            else "No confirmed MCP call and matching report in this attempt")
    summary={"checked_at":datetime.now(timezone.utc).isoformat(),"codex_version":version,"transport":"stdio",
             "exit_code":result.returncode,"tool_events":events,"result":"PASS" if valid else "NOT_RUN",
             "instance_id":before["instance_id"],"event_id":state["event_id"] if state else None}
    if valid:
        summary["state_text"]=state["payload"].get("state_text")
    else:
        summary["reason"]=reason
    sys.stdout.buffer.write((json.dumps(summary,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    return 0 if valid else 2

if __name__=="__main__":
    raise SystemExit(main())
