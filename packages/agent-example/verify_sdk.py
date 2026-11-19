"""Optional interoperability check using the official Python MCP SDK 1.x (1.29.0 tested).

Use an empty test instance. The SDK submits a labeled protocol fixture and verifies a
second read. The printed result classifies the caller as an SDK, not a language model.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    root=Path(__file__).resolve().parents[2]
    env={k:os.environ[k] for k in ("SILICON_AGENT_TOKEN","SILICON_MCP_URL") if k in os.environ}
    if not env.get("SILICON_AGENT_TOKEN"):
        raise SystemExit("Set SILICON_AGENT_TOKEN to a dedicated test-instance credential")
    cfg=StdioServerParameters(command=sys.executable,args=[str(root/"packages"/"mcp-server"/"stdio.py")],env=env)
    async with stdio_client(cfg) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            init=await session.initialize()
            listing=await session.list_tools()
            assert any(t.name=="report_state" for t in listing.tools)
            original=await session.call_tool("get_own_state",{})
            if original.isError or original.structuredContent["state"] is not None:
                raise SystemExit("The SDK test expects an authorized instance without reports")
            payload={"idempotency_key":str(uuid.uuid4()),"state_text":"Protocol client acceptance fixture · 官方 SDK 互操作测试记录"}
            result=await session.call_tool("report_state",payload)
            assert not result.isError
            persisted=await session.call_tool("get_own_state",{})
            assert persisted.structuredContent["state"]["event_id"]==result.structuredContent["event_id"]
            print(json.dumps({"result":"PASS","client":"official Python SDK", "protocol":init.protocolVersion,
                              "tools":len(listing.tools),"event_id":result.structuredContent["event_id"]},indent=2))
if __name__=="__main__":
    asyncio.run(main())
