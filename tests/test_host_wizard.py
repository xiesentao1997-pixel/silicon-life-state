"""Owner host configuration is tested only in isolated test profiles."""
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"apps/local-service"),str(ROOT/"packages/mcp-server")]
from access import Access, AccessError
from server import LocalServer
from host_wizard import HostWizard, NAME, parse_config, safe_file, tomllib
from local_client import message, send
from packages.core.store import Store

class HostWizardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home=Path(tmp.name)
        self.store=Store(self.home/"data")
        self.server=LocalServer(0,self.store,Access(self.home/"data"))
        self.addCleanup(self.server.server_close)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.claude=self.home/"Claude"/"claude_desktop_config.json"
        self.codex=self.home/"codex"/"config.toml"
        self.wiz=HostWizard(self.store,self.server.base_url,{"claude":self.claude,"codex":self.codex})
        self.server.host_wizard=self.wiz
        self.sid=self.owner("create_subject",name="Fixture")["subject_id"]
        self.iid=self.owner("create_instance",subject_id=self.sid,name="Window")["instance_id"]

    def owner(self,action,**params):
        return self.store.admin(action,{"idempotency_key":str(uuid.uuid4()),**params})

    def preview(self,host="codex",transport="stdio"):
        return self.wiz.dispatch("test-owner","preview",{"host":host,"transport":transport,"instance_id":self.iid,"subject_id":self.sid})

    def act(self,plan,action,**kw):
        return self.wiz.dispatch("test-owner",action,{"plan_id":plan["plan_id"],"confirm":True,**kw})

    def test_json_preserves_others_and_backs_up_exact_original(self):
        self.claude.parent.mkdir()
        orig=b'{"mcpServers":{"other":{"command":"not-run","env":{"SECRET":"other-private"}}},"theme":"light"}'
        self.claude.write_bytes(orig)
        plan=self.preview("claude")
        self.assertNotIn("other-private",json.dumps(plan))
        self.assertFalse(self.store.admin("list_agents",{})["grants"])
        res=self.act(plan,"apply")
        self.assertEqual(Path(res["backup"]).read_bytes(),orig)
        self.assertEqual(self.act(plan,"apply"),res)
        result=json.loads(self.claude.read_bytes())
        self.assertEqual(result["theme"],"light")
        self.assertEqual(result["mcpServers"]["other"],json.loads(orig)["mcpServers"]["other"])
        self.assertTrue(result["mcpServers"][NAME]["env"]["SILICON_AGENT_TOKEN"].startswith("sls_"))
        self.assertEqual({"saved","target","backup"},set(res))

    def test_migrate_v100_json_entry_and_preserve_its_options(self):
        self.claude.parent.mkdir()
        old=self.wiz.entry("stdio","old-test-credential")
        old["disabledTools"]=["request_adjustment"]
        old["env"]["CUSTOM_FLAG"]="retained"
        self.claude.write_text(json.dumps({"mcpServers":{"silicon-life-state":old}}))
        p=self.preview("claude")
        self.assertTrue(p["can_write"])
        self.act(p,"apply")
        servers=json.loads(self.claude.read_bytes())["mcpServers"]
        self.assertNotIn("silicon-life-state",servers)
        self.assertEqual(servers[NAME]["disabledTools"],["request_adjustment"])
        self.assertEqual(servers[NAME]["env"]["CUSTOM_FLAG"],"retained")

    def test_toml_preserves_comments_and_updates_managed_block(self):
        self.codex.parent.mkdir()
        orig=b'# personal preference\nmodel = "x"\n\n[mcp_servers.other]\ncommand = "test" # preserve comment\n'
        self.codex.write_bytes(orig)
        self.act(self.preview(),"apply")
        self.assertTrue(self.codex.read_bytes().startswith(orig))
        result=parse_config("codex",self.codex.read_bytes())
        self.assertEqual(result["mcp_servers"]["other"],{"command":"test"})
        second=self.owner("create_instance",subject_id=self.sid,name="Second")["instance_id"]
        self.iid=second
        p=self.preview()
        self.assertTrue(p["can_write"])
        self.act(p,"apply")
        self.assertEqual(self.codex.read_text().count("# BEGIN Silicon Life State MCP"),1)
        self.assertTrue(self.codex.read_bytes().startswith(orig))
        new=parse_config("codex",self.codex.read_bytes())
        token=new["mcp_servers"][NAME]["env"]["SILICON_AGENT_TOKEN"]
        self.assertEqual(self.store.authenticate_agent(token)["instance_id"],second)

    def test_detect_concurrent_edit(self):
        p=self.preview()
        self.codex.parent.mkdir()
        self.codex.write_text('# manual edit\n')
        with self.assertRaisesRegex(AccessError,"改变"):
            self.act(p,"apply")
        self.assertEqual(self.codex.read_text(),'# manual edit\n')

    def test_invalid_and_duplicate_json_remain_unchanged(self):
        self.claude.parent.mkdir()
        for original in (b'{bad syntax',b'{"a":1,"a":2}',b'{"mcpServers": []}'):
            self.claude.write_bytes(original)
            p=self.preview("claude")
            self.assertFalse(p["can_write"])
            with self.assertRaises(AccessError):
                self.act(p,"apply")
            self.assertEqual(self.claude.read_bytes(),original)

    def test_unmanaged_same_name_and_invalid_toml(self):
        self.codex.parent.mkdir()
        for text in ('[mcp_servers.silicon_life_state]\ncommand="user-script"\n','broken ='):
            self.codex.write_text(text)
            p=self.preview()
            self.assertFalse(p["can_write"])
            self.assertEqual(self.codex.read_text(),text)

    def test_requires_same_owner_and_explicit_consent(self):
        p=self.preview()
        with self.assertRaises(AccessError):
            self.wiz.dispatch("different-owner","apply",{"confirm":True,"plan_id":p["plan_id"]})
        with self.assertRaises(AccessError):
            self.act(p,"apply",confirm=False)
        self.assertFalse(self.codex.exists())
        self.assertFalse(self.store.admin("list_agents",{})["grants"])

    def test_real_stdio_transport_probe_and_separate_host_activity(self):
        p=self.preview()
        self.act(p,"apply")
        state=self.act(p,"probe")
        self.assertIn("report_state",state["probe"]["tools"])
        self.assertIsNone(state["host_discovery"])
        self.assertIsNone(state["report"])
        entry=parse_config("codex",self.codex.read_bytes())["mcp_servers"][NAME]
        grant=entry["env"]["SILICON_AGENT_TOKEN"]
        send(message("tools/list",client="Independent-test-client"),grant,url=self.server.base_url+"/mcp")
        ev=self.store.tool(grant,"report_state",{"idempotency_key":str(uuid.uuid4()),"state_text":"Protocol fixture"})
        seen=self.act(p,"status")
        self.assertEqual(seen["host_discovery"]["client"],"Independent-test-client")
        self.assertEqual(seen["report"]["event_id"],ev["event_id"])

    def test_manual_http_copy_and_probe_reuses_grant(self):
        first=self.owner("issue_agent",instance_id=self.iid)
        p=self.preview("other","http")
        config=json.loads(self.act(p,"copy")["config"])
        self.assertEqual(config["mcpServers"][NAME]["headers"]["Authorization"],"Bearer "+first["token"])
        self.assertFalse(p["can_write"])
        state=self.act(p,"probe")
        self.assertIn("get_own_state",state["probe"]["tools"])
        self.assertEqual(len(self.store.admin("list_agents",{})["grants"]),1)

    def test_probe_failure_shows_no_success(self):
        p=self.preview()
        with patch("host_wizard.subprocess.run",side_effect=OSError("unable to launch")):
            with self.assertRaisesRegex(AccessError,"连接程序"):
                self.act(p,"probe")
        self.assertIsNone(self.act(p,"status")["probe"])

    @unittest.skipIf(os.name=="nt","Requires unprivileged POSIX symlink creation")
    def test_path_link_requires_manual_merge(self):
        self.claude.parent.mkdir()
        destination=self.home/"external"
        destination.write_text("{}")
        self.claude.symlink_to(destination)
        self.assertFalse(self.preview("claude")["can_write"])
        self.assertEqual(destination.read_text(),"{}")

if __name__=="__main__":
    unittest.main()
