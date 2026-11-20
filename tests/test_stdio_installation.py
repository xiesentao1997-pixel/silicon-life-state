"""Actual stdio bridge processes, restart coordination and multiplexed host conversations."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from acceptance_support import Local, ROOT, fresh
sys.path.insert(0, str(ROOT/"packages/mcp-server"))
from local_client import message
from autostart import service_url, StartupError

BRIDGE = ROOT/"packages/mcp-server/stdio.py"
# Test-only observation records child service PIDs for cleanup across all platforms.
LAUNCH = """import os,sys,subprocess
sys.path.insert(0,sys.argv[1])
import stdio
real = subprocess.Popen
def observed(*args, **kwargs):
    process=real(*args, **kwargs)
    with open(sys.argv[2], 'a') as f:
        f.write(str(process.pid)+'\\n')
    return process
subprocess.Popen=observed
raise SystemExit(stdio.main())
"""


class InstallationBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp=Path(tmp.name)
        self.data=self.tmp/"ledger"
        self.local=Local(self.data).start()
        self.addCleanup(self.local.stop)
        self.subject=self.local.api("subjects",{"name":"S"})["subject_id"]
        grant=self.local.api("installations",{"host":"codex","subject_id":self.subject})
        self.env={**os.environ,"SILICON_INSTALLATION_TOKEN":grant["token"],"SILICON_HOST":"codex",
                  "SILICON_MCP_URL":self.local.base+"/mcp","SILICON_DATA_DIR":str(self.data)}
        self.pids=self.tmp/"spawned.txt"
        self.addCleanup(self.stop_auto_started)

    def stop_auto_started(self):
        if self.pids.exists():
            for raw in self.pids.read_text().splitlines():
                try:
                    os.kill(int(raw),signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def bridge(self,*messages):
        result=subprocess.run([sys.executable,"-I","-c",LAUNCH,str(BRIDGE.parent),str(self.pids)],
                              input="".join(json.dumps(m)+"\n" for m in messages),capture_output=True,
                              text=True,encoding="utf-8",env=self.env,timeout=20,check=True)
        return {r["id"]:r for r in map(json.loads,result.stdout.splitlines())}

    def call(self,name,arguments=None, thread=None):
        request=message("tools/call",{"name":name,"arguments":arguments or {}})
        if thread:
            request["params"]["_meta"]["threadId"]=thread
        return request

    def result(self,request):
        return self.bridge(request)[request["id"]]["result"]

    def test_fallback_handles_share_one_process_without_cross_assigning(self):
        open_a=self.result(self.call("open_conversation"))["structuredContent"]["conversation_handle"]
        open_b=self.result(self.call("open_conversation"))["structuredContent"]["conversation_handle"]
        self.assertNotEqual(open_a,open_b)
        self.assertEqual(self.local.api("snapshot")["instances"],[])
        missing=self.result(self.call("report_state",{"state_text":"x","idempotency_key":fresh()}))
        self.assertTrue(missing["isError"])
        self.assertEqual(self.local.api("snapshot")["instances"],[])
        a,b=[self.call("report_state",{"state_text":state,"idempotency_key":fresh(),"conversation_handle":handle})
             for handle,state in [(open_a,"A"),(open_b,"B")]]
        written=self.bridge(a,b)
        ids=[written[m["id"]]["result"]["structuredContent"]["instance_id"] for m in (a,b)]
        self.assertNotEqual(*ids)
        again=self.result(self.call("get_own_state",{"conversation_handle":open_a}))["structuredContent"]
        self.assertEqual((again["instance_id"],again["state"]["payload"]["state_text"]),(ids[0],"A"))

    def test_three_bridges_start_one_service_on_the_original_database(self):
        thread_a=str(uuid.uuid4())
        first=self.result(self.call("report_state",{"idempotency_key":fresh(),"state_text":"before restart"},thread_a))["structuredContent"]
        self.local.stop()
        calls=[self.call("get_own_state",thread=t) for t in (thread_a,str(uuid.uuid4()),str(uuid.uuid4()))]
        with ThreadPoolExecutor(max_workers=3) as pool:
            states=[reply["structuredContent"] for reply in pool.map(self.result,calls)]
        self.assertEqual(len(set(self.pids.read_text().splitlines())),1)
        self.assertEqual({r["subject_id"] for r in states},{self.subject})
        self.assertEqual(len({r["instance_id"] for r in states}),3)
        self.assertEqual(states[0]["state"]["event_id"],first["event_id"])
        self.assertEqual(states[0]["instance_id"],first["instance_id"])

    def test_missing_ledger_is_never_initialized(self):
        missing=self.tmp/"moved"
        with patch.dict(os.environ,{"SILICON_DATA_DIR":str(missing)}), self.assertRaises(StartupError):
            service_url()
        self.assertFalse(missing.exists())
