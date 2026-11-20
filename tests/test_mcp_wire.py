"""Protocol contract checks; these clients do not impersonate a model in acceptance reporting."""
import base64
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
WIRE=ROOT/"packages"/"mcp-server"
sys.path.insert(0,str(WIRE))
from mcp_wire import BY_NAME, LEGACY, LEGACY_VERSIONS, PREFIX, STDIO_VERSIONS, VERSION, handle_http
from local_client import as_header, message

def headers(req):
    result={"MCP-Protocol-Version":VERSION,"Mcp-Method":req["method"],"Accept":"application/json, text/event-stream"}
    if req["method"]=="tools/call":
        result["Mcp-Name"]=as_header(req["params"]["name"])
    return result

class WireTests(unittest.TestCase):
    def evaluate(self,msg,h=None):
        return handle_http(msg,headers(msg) if h is None else h,lambda name,args: {"echo":name})

    def test_modern_discovery_without_initialization(self):
        status,_,reply=self.evaluate(message("server/discover"))
        self.assertEqual(status,200)
        self.assertEqual(reply["result"]["supportedVersions"],[VERSION])
        self.assertEqual(reply["result"]["resultType"],"complete")

    def test_cache_hints_apply_to_complete_cacheable_results_only(self):
        for method in ("server/discover", "tools/list"):
            with self.subTest(method=method):
                result = self.evaluate(message(method))[2]["result"]
                self.assertEqual((result["ttlMs"], result["cacheScope"]), (0, "private"))
        call = self.evaluate(message("tools/call", {"name":"get_own_state"}))[2]["result"]
        self.assertNotIn("ttlMs", call)
        self.assertNotIn("cacheScope", call)

    def test_modern_missing_metadata(self):
        req=message("tools/list")
        del req["params"]["_meta"][PREFIX+"clientCapabilities"]
        self.assertEqual(self.evaluate(req)[2]["error"]["code"],-32602)

    def test_unknown_version(self):
        req=message("tools/list")
        h=headers(req)
        h["MCP-Protocol-Version"]=req["params"]["_meta"][PREFIX+"protocolVersion"]="2099-01-01"
        status,_,out=self.evaluate(req,h)
        self.assertEqual((status,out["error"]["code"]),(400,-32022))

    def test_mismatched_header(self):
        req=message("tools/call",{"name":"get_own_state","arguments":{}})
        h=headers(req)
        h["Mcp-Name"]="read_event_history"
        self.assertEqual(self.evaluate(req,h)[2]["error"]["code"],-32020)

    def test_encoded_name_matches_equivalent_ascii(self):
        req=message("tools/call",{"name":"get_own_state","arguments":{}})
        h=headers(req)
        h["Mcp-Name"]="=?base64?"+base64.b64encode(b"get_own_state").decode()+"?="
        self.assertFalse(self.evaluate(req,h)[2]["result"]["isError"])

    def test_reject_unknown_fields(self):
        req=message("tools/call",{"name":"report_state","arguments":{"state_text":"Private","source":"runtime_observed","idempotency_key":"unique-word"}})
        self.assertTrue(self.evaluate(req)[2]["result"]["isError"])

    def test_reject_nonfinite_dimension(self):
        req=message("tools/call",{"name":"report_state","arguments":{"load":float("nan"),"idempotency_key":"unique-word"}})
        self.assertTrue(self.evaluate(req)[2]["result"]["isError"])

    def test_no_owner_tool_exposed(self):
        out=self.evaluate(message("tools/list"))[2]["result"]
        names={v["name"] for v in out["tools"]}
        self.assertNotIn("respond",names)
        self.assertTrue({"express_boundary","record_strategy","report_state"}.issubset(names))

    def test_unknown_method_and_tool(self):
        self.assertEqual(self.evaluate(message("sls/unknown"))[0],404)
        out=self.evaluate(message("tools/call",{"name":"respond","arguments":{}}))[2]
        self.assertEqual(out["error"]["code"],-32602)

    def test_bad_id_and_notification(self):
        req=message("tools/list")
        req["id"]=True
        self.assertEqual(self.evaluate(req)[0],400)
        del req["id"]
        self.assertIsNone(self.evaluate(req)[2])

    def test_same_domain_schemas(self):
        sys.path.insert(0,str(ROOT))
        from packages.core.validation import TOOLS as domain, READS
        self.assertEqual(set(domain),set(BY_NAME))
        for name,(allowed,required) in domain.items():
            extra=set() if name in READS else {"idempotency_key"}
            schema=BY_NAME[name]["inputSchema"]
            self.assertEqual(set(schema["properties"]),allowed|extra,name)
            self.assertEqual(set(schema.get("required",[])),required|extra,name)

class StdioTests(unittest.TestCase):
    def test_dual_era_bridge(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.headers["Authorization"] != "Bearer test-transport-only":
                    self.send_error(401)
                    return
                msg=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                status,_,reply=handle_http(msg,self.headers,lambda n,a: {})
                self.send_response(status)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps(reply).encode())
            def log_message(self,*_):
                pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env={**os.environ,"SILICON_AGENT_TOKEN":"test-transport-only",
             "SILICON_MCP_URL":f"http://127.0.0.1:{server.server_port}/mcp"}
        init={"id":1,"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":LEGACY,"clientInfo":{"name":"test","version":"1"},"capabilities":{}}}
        old={"id":2,"jsonrpc":"2.0","method":"tools/list"}
        modern=message("server/discover")
        def exchange(messages):
            data = "".join(json.dumps(msg)+"\n" for msg in messages)
            proc = subprocess.run([sys.executable, "-I", str(WIRE/"stdio.py")], input=data,
                                  text=True, capture_output=True, env=env, timeout=5)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return {obj["id"]:obj for obj in map(json.loads, proc.stdout.splitlines())}

        result = exchange([modern])[modern["id"]]["result"]
        self.assertEqual(result["supportedVersions"], list(STDIO_VERSIONS))
        self.assertEqual((result["ttlMs"], result["cacheScope"]), (0, "private"))
        # A new client process and one real initialize negotiation for each revision.
        for revision in LEGACY_VERSIONS:
            with self.subTest(revision=revision):
                replies = exchange((
                    {**init, "params":{**init["params"], "protocolVersion":revision}},
                    {"jsonrpc":"2.0","method":"notifications/initialized"},
                    old,
                    {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_own_state"}},
                    {"jsonrpc":"2.0","id":4,"method":"server/discover"},
                ))
                self.assertEqual(replies[1]["result"]["protocolVersion"], revision)
                listed = replies[2]["result"]
                self.assertTrue({"ttlMs","cacheScope","resultType"}.isdisjoint(listed))
                tool = listed["tools"][0]
                self.assertEqual("annotations" in tool, revision >= "2025-03-26")
                self.assertEqual("outputSchema" in tool, revision >= "2025-06-18")
                self.assertEqual("structuredContent" in replies[3]["result"], revision >= "2025-06-18")
                self.assertEqual(replies[4]["error"]["code"], -32601)

if __name__=="__main__":
    unittest.main()
