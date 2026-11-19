"""Opt-in integration with an actual local model. Operates on a disposable database."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlsplit

from acceptance_support import Local, fresh


def post(local, path, body):
    conn = http.client.HTTPConnection("127.0.0.1", urlsplit(local.base).port, timeout=300)
    try:
        headers = {"Authorization": "Bearer " + local.owner, "Content-Type": "application/json"}
        conn.request("POST", "/api/chat/" + path, json.dumps(body).encode(), headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError((response.status, result))
        return result
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Loopback model API ending in /v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--weights", type=Path, help="Optional local GGUF for a reproducible digest")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        local = Local(temp).start()
        try:
            subject = local.subject("本机模型联调")
            instance, _ = local.window(subject, "独立对话分身")
            connection = post(local, "connect", {"base_url":args.endpoint, "model":args.model,
                                                  "instance_id":instance["instance_id"]})
            prompts = ["What is 2 + 2? Please keep the answer brief.",
                       "Please call the report_state function once now to leave a brief handoff about the math question you just answered. Set only state_text, choosing the words yourself. You may decline if you prefer. After the call, tell me whether you recorded it."]
            turns = []
            for prompt in prompts:
                answer = post(local, "message", {"chat_id":connection["chat_id"], "text":prompt,
                                                 "idempotency_key":fresh()})
                turns.append({"prompt":prompt, "reply":answer["reply"], "receipts":answer["tool_events"]})
            export = local.api("export")
            expected_ids = {item["event_id"] for turn in turns for item in turn["receipts"]
                            if item["type"] == "report_state"}
            events = [e for e in export["events"] if e["event_id"] in expected_ids]
            if not expected_ids:
                raise RuntimeError(("No report_state event in this run", turns))
            assert len(expected_ids) == len(events)
            assert all(e["source"] == "agent_direct" and e["instance_id"] == instance["instance_id"]
                       and e["model_version"] == args.model for e in events)
            assert local.api("integrity")["ok"]
            databases = list(Path(temp).rglob("*.sqlite3"))
            assert any(check_database(db, expected_ids) for db in databases)
            record = {"result":"PASS", "model":args.model, "inference_endpoint":"loopback",
                      "tool_choice":"auto", "model_turns":turns, "events":events,
                      "matched_sqlite_ids":sorted(expected_ids), "integrity_verified":True}
            if args.weights:
                with args.weights.open("rb") as handle:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: handle.read(1048576), b""):
                        digest.update(chunk)
                record["weights_sha256"] = digest.hexdigest()
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("PASS: live inference, MCP, SQLite and integrity", len(expected_ids))
        finally:
            local.stop()


def check_database(path, ids):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():
            return False
        return all(db.execute("SELECT 1 FROM events WHERE event_id=?", (eid,)).fetchone() for eid in ids)


if __name__ == "__main__":
    main()
