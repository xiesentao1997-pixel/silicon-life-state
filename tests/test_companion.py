import tempfile
import unittest

from acceptance_support import Local


class Companion(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = Local(directory.name).start()
        self.addCleanup(self.service.stop)
        self.sid = self.service.subject()
        self.code = self.service.api("pair/code", {"target":"pet"})["code"]
        self.token = self.service.raw("/api/pet/pair", {"code":self.code})[1]["token"]

    def test_reader_cannot_write_or_pair_and_revocation_keeps_history(self):
        service = self.service
        for route, body in [("/api/pair/code", {"target":"dashboard"}), ("/api/export", None),
                            ("/api/subjects", {"name":"blocked"}), ("/api/chat/connect", {})]:
            self.assertEqual(service.raw(route, body, self.token)[0], 403, route)
        self.assertEqual(service.raw("/api/pet/pair", {"code":self.code})[0], 409)
        self.assertEqual(service.raw("/api/pet/feed", token=self.token, headers={"Origin":service.base})[0], 403)
        self.assertEqual(service.raw("/api/pet/feed", token=self.token)[1]["states"], [])
        _, agent = service.window(self.sid,"A")
        event = service.tool(agent,"report_state",state_text="原文")
        service.api("revoke-pets",{})
        self.assertEqual(service.raw("/api/pet/feed", token=self.token)[0],401)
        self.assertEqual(service.tool(agent,"get_own_state")["state"]["event_id"], event["event_id"])

    def test_independent_states_requests_sources_revisions_and_restart(self):
        service = self.service
        records = []
        windows = [service.window(self.sid,n) for n in "ABC"]
        for (_, token), msg in zip(windows, ["有些难过", "很开心", "不确定"]):
            records.append(service.tool(token,"report_state",state_text=msg,shared_to_subject=msg=="很开心"))
        a, author = windows[0]
        revised = service.tool(author,"revise_state",event_id=records[0]["event_id"],state_text="修订原文")
        request = service.tool(author,"express_boundary",text="请保留原话",reason="核对来源")
        obs = service.observation({"instance_id":a["instance_id"],"text":"授权选段","source":"agent_visible_text","adapter":"fixture"})
        other = service.subject("另一个主体")
        _, stranger = service.window(other,"D")
        service.tool(stranger,"report_state",state_text="另一主体")
        service.stop()
        service.start()
        code, result = service.raw("/api/pet/feed?subject_id="+self.sid,token=self.token)
        self.assertEqual(code,200)
        self.assertEqual([r["event_id"] for r in result["states"]],[r["event_id"] for r in records])
        self.assertEqual(result["states"][0]["revision_id"],revised["event_id"])
        self.assertEqual(result["states"][0]["text"],"修订原文")
        self.assertEqual(result["requests"][0]["event_id"],request["event_id"])
        self.assertEqual(result["requests"][0]["text"],"请保留原话")
        self.assertEqual(result["observations"][0]["source"],"agent_visible_text")
        self.assertEqual(result["observations"][0]["event_id"],obs["event_id"])
        self.assertEqual([r["event_id"] for r in result["shared"]],[records[1]["event_id"]])
        single = service.raw("/api/pet/feed?subject_id="+self.sid+"&instance_id="+a["instance_id"],token=self.token)[1]
        self.assertEqual(len(single["states"]),1)
        service.tool(author,"revise_state",event_id=records[0]["event_id"],operation="withdraw")
        self.assertEqual(service.raw("/api/pet/feed?instance_id="+a["instance_id"],token=self.token)[1]["states"],[])
        self.assertTrue(service.api("integrity")["ok"])
