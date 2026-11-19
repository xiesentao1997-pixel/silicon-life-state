"""Manual-duration expiry test. Leave the original service running for over ten minutes."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from acceptance_support import Local, fresh


def run():
    with tempfile.TemporaryDirectory(prefix="sls-slow-install-") as temp:
        local = Local(Path(temp)).start()
        try:
            started = time.monotonic()
            old = local.ready["extension_code"]
            # Normal elapsed wall time. This test changes neither the DB nor any clock.
            deadline = started + 602
            while time.monotonic() < deadline:
                time.sleep(min(20, deadline - time.monotonic()))
            extension = {"Origin": "chrome-extension://" + "b" * 32, "X-SLS-Extension": "b" * 32}
            status, original = local.raw("/api/pair", {"code": old}, headers=extension)
            assert status == 410 and original["error"]["code"] == "PAIR_EXPIRED"
            status, denied = local.raw("/api/pair/code", {"target": "extension", "idempotency_key": fresh()})
            assert status == 401
            grant = local.api("pair/code", {"target": "extension"})
            assert 0 < grant["expires_in"] <= 600
            status, pair = local.raw("/api/pair", {"code": grant["code"]}, headers=extension)
            assert status == 200
            assert local.raw("/api/snapshot", token=pair["token"], headers=extension)[0] == 200
            status, consumed = local.raw("/api/pair", {"code": grant["code"]}, headers=extension)
            assert status == 409 and consumed["error"]["code"] == "PAIR_USED"
            return {"case": "slow-first-extension-pairing", "elapsed_seconds": round(time.monotonic()-started, 1),
                    "clock": "unmodified real elapsed time", "service_restarts": 0,
                    "expired_original": original["error"]["code"], "anonymous_code_issuance": "denied",
                    "owner_generated_new_code": True, "new_extension_read": "PASS",
                    "second_exchange": consumed["error"]["code"], "result": "PASS"}
        finally:
            local.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run(), ensure_ascii=False, indent=2)
    print(report)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
