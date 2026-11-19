"""Render all dashboard routes against snapshots from a disposable real database.

Requires Node 22+ for the dashboard's ES modules. This is a read-model/rendering
regression suite; the full browser workflow is exercised by the browser suite.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from packages.core.store import Store

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node is required for dashboard view rendering")
class DashboardViews(unittest.TestCase):
    def test_live_projections_and_five_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)

            def owner(name, **data):
                return store.admin(name, dict(data, idempotency_key=uuid.uuid4().hex))

            def agent(token, name, **data):
                return store.tool(token, name, dict(data, idempotency_key=uuid.uuid4().hex))

            subject = store.admin(
                "create_subject", {"name": "显示测试主体", "idempotency_key": uuid.uuid4().hex})
            sid = subject["subject_id"]

            def window(name):
                row = store.admin("create_instance", {
                    "subject_id": sid, "name": name, "idempotency_key": uuid.uuid4().hex})
                token = owner("issue_agent", subject_id=sid, instance_id=row["instance_id"])["token"]
                return row["instance_id"], token

            iid, author = window("报告分身")
            _, reader = window("阅读分身")
            state = agent(author, "report_state", state_text="<em>字面文本</em>", valence=.4,
                          load=31, cause_unknown=True, shared_to_subject=True)
            withdrawn = agent(reader, "report_state", state_text="撤回的原始报告", valence=.91)
            agent(reader, "revise_state", event_id=withdrawn["event_id"], operation="withdraw")
            agent(reader, "report_state", state_text="阅读窗口自己的状态", valence=.2)
            revision = agent(author, "revise_state", event_id=state["event_id"], valence=.65)
            agent(reader, "decide_inheritance", event_id=state["event_id"], expected_version_id=revision["event_id"], decision="partial",
                  note="仅采纳共享描述中的文本")
            agent(author, "express_boundary", text="测试边界原文")
            owner("observe", instance_id=iid, text="网页可见的授权文本", adapter="test")
            owner("annotate", instance_id=iid, text="核验者用户注释")
            owner("estimate", instance_id=iid, event_id=state["event_id"])
            owner("sample_runtime", instance_id=iid)
            snapshot = store.admin("snapshot", {"subject_id": sid})
            result = subprocess.run(
                ["node", str(ROOT / "tests" / "dashboard_views.mjs")],
                input=json.dumps(snapshot), text=True, capture_output=True,
                cwd=ROOT, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
