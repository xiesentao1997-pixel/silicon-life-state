"""1.0.0 in-place migration, owner-only reissue, and trusted launcher recovery."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from acceptance_support import Local, ROOT, SERVER, fresh

sys.path.insert(0, str(ROOT / "apps/local-service"))
from access import Access
from reconnect import existing_endpoint


class PairRecovery(unittest.TestCase):
    def test_v100_codes_and_active_browser_token_survive_schema_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "browser-access.sqlite3"
            raw = "legacy-owner-session"
            code = "legacy-first-install-code"
            expires = int(time.time()) + 120
            as_hash = lambda value: hashlib.sha256(value.encode()).hexdigest()
            with sqlite3.connect(path) as db:
                db.executescript("""
                    CREATE TABLE codes (hash TEXT PRIMARY KEY,target TEXT NOT NULL,expires INTEGER NOT NULL);
                    CREATE TABLE clients (hash TEXT PRIMARY KEY,origin TEXT NOT NULL,expires INTEGER NOT NULL);
                """)
                db.execute("INSERT INTO clients VALUES(?,?,?)", (as_hash(raw), "owner-origin", expires))
                db.execute("INSERT INTO codes VALUES(?,?,?)", (as_hash(code), "dashboard", expires))
            access = Access(temp)
            access.check(raw, "owner-origin")
            self.assertEqual("active", access.code_status(code)["state"])
            self.assertEqual("owner", access.exchange(code, "owner-origin")["role"])
            self.assertEqual("used", access.code_status(code)["state"])
            self.assertEqual("used", Access(temp).code_status(code)["state"])
            # Exact INSERT/DELETE shape from the v1.0 release, after the 1.0.1 migration.
            with sqlite3.connect(path) as old_db:
                self.assertEqual(0, old_db.execute("DELETE FROM codes WHERE hash=? AND target=? AND expires>?",
                                                 (as_hash(code), "dashboard", 0)).rowcount)
                old_db.execute("INSERT INTO codes VALUES (?,?,?)", (as_hash("rollback-issued"),"dashboard",expires))
            self.assertEqual("owner",access.exchange("rollback-issued","owner-origin")["role"])

    def test_expiry_replacement_and_scoped_status(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Local(temp).start()
            try:
                header = {"Origin":"chrome-extension://"+"a"*32, "X-SLS-Extension":"a"*32}
                old = local.ready["extension_code"]
                self.assertEqual(401, local.raw("/api/pair/status", {"code":old})[0])
                self.assertEqual(401, local.raw("/api/pair/code", {"target":"extension","idempotency_key":fresh()})[0])
                with sqlite3.connect(Path(temp)/"browser-access.sqlite3") as db:
                    db.execute("UPDATE codes SET expires=expires-601 WHERE hash=?", (hashlib.sha256(old.encode()).hexdigest(),))
                status, detail = local.raw("/api/pair", {"code":old}, headers=header)
                self.assertEqual((410, "PAIR_EXPIRED"), (status, detail["error"]["code"]))
                status, detail = local.raw("/api/pair/status", {"code":old}, token=local.owner)
                self.assertEqual((200,"expired",0), (status,detail["state"],detail["expires_in"]))
                first = local.api("pair/code", {"target":"extension"})
                second = local.api("pair/code", {"target":"extension","replaces":first["code"]})
                status, detail = local.raw("/api/pair", {"code":first["code"]}, headers=header)
                self.assertEqual((409, "PAIR_REPLACED"), (status, detail["error"]["code"]))
                self.assertLessEqual(1,second["expires_in"])
                self.assertIn("T",second["expires_at"])
                self.assertEqual(200, local.raw("/api/pair", {"code":second["code"]},headers=header)[0])
                self.assertEqual("used",local.raw("/api/pair/status",{"code":second["code"]},local.owner)[1]["state"])
            finally:
                local.stop()

    def test_running_installation_reconnect_via_actual_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Local(temp).start()
            try:
                command = [sys.executable, str(SERVER)] if sys.platform == "win32" else ["sh",str(ROOT/"start.sh")]
                result = subprocess.run([*command, "--reconnect","--data-dir",temp,"--json-ready","--no-browser"],
                                        capture_output=True,text=True,timeout=10,check=True)
                ready = json.loads(result.stdout)
                self.assertTrue(ready["existing_service"])
                self.assertEqual(local.base, ready["base_url"])
                params = parse_qs(urlsplit(ready["dashboard_url"]).fragment)
                self.assertEqual(["pair-extension"], params["action"])
                self.assertEqual(ready["extension_code"], params["extension_code"][0])
                self.assertEqual(200, local.raw("/api/pair", {"code":params["pair"][0]})[0])
                self.assertEqual(200, local.raw("/api/subjects", token=local.owner)[0])
                self.assertEqual(local.base, existing_endpoint(temp))
                self.assertNotIn("reconnect_proof", local.raw("/api/health")[1])
                # A matching port or publicly accessible healthy response is insufficient.
                identity = Path(temp)/"service-endpoint.json"
                descriptor = json.loads(identity.read_text())
                descriptor["verifier"] = "00"*32
                identity.write_text(json.dumps(descriptor))
                self.assertIsNone(existing_endpoint(temp))
            finally:
                local.stop()
            self.assertIsNone(existing_endpoint(temp))
