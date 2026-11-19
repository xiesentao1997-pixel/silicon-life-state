"""Exercise the extracted Windows release using only its bundled interpreter.

Run runtime\\python.exe -I tests\\windows_portable_smoke.py on a Windows QA desktop.
The normal Windows path uses ShellExecute through Start-Process, the same file
association as Explorer. It opens the default browser; DOM rendering is tested
by the separate browser suite. --wine is a distinct compatibility-only check.
"""
import argparse
from contextlib import closing
import ctypes
import http.client
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid


def request(port, route, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        conn.request("GET" if payload is None else "POST", route,
                     None if payload is None else json.dumps(payload).encode(), headers)
        response = conn.getresponse()
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"{route} returned HTTP {response.status}")
        return json.loads(body) if route.startswith("/api/") else body
    finally:
        conn.close()


def owner_write(port, route, owner, **args):
    return request(port, route, owner, {"idempotency_key": uuid.uuid4().hex, **args})


def mcp_call(config, env, method, params):
    params = {**params, "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
              "io.modelcontextprotocol/clientCapabilities": {},
              "io.modelcontextprotocol/clientInfo": {"name": "windows-acceptance", "version": "1"}}}
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    run = subprocess.run([config["command"], *config["args"]], cwd=env["SILICON_DATA_DIR"],
                         env=env, input=json.dumps(msg) + "\n", capture_output=True,
                         encoding="utf-8", timeout=35, check=True)
    doc = json.loads(run.stdout)
    if doc.get("error") or doc["result"].get("isError"):
        raise RuntimeError(f"Failed MCP probe: {method}")
    return doc["result"]


def check(root, wine):
    runtime = (root / "runtime" / "python.exe").resolve()
    if Path(sys.executable).resolve() != runtime or sys.platform != "win32":
        raise SystemExit("Run with the exact runtime\\python.exe from the extracted release")
    is_wine = hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")
    if is_wine != wine:
        raise SystemExit("Select --wine only on Wine. A Wine run cannot certify Windows.")
    native_dir = Path(os.environ["SystemRoot"]) / "System32"
    cmd = str(native_dir / "cmd.exe")
    powershell = str(native_dir / "WindowsPowerShell/v1.0/powershell.exe")
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="sls portable QA ") as temp:
        env = {**os.environ, "PATH": str(native_dir), "SILICON_DATA_DIR": temp, "SLS_QA_PORT": str(port)}
        if any(shutil.which(name, path=env["PATH"]) for name in ("py.exe", "python.exe", "python3.exe")):
            raise RuntimeError("A system Python is present on the restricted QA PATH")
        # Poison public proxies even if the underlying Windows QA machine has networking.
        # For a physical offline acceptance run, disconnect the network before launching.
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            env[key] = "http://127.0.0.1:1"
        handle = None
        if wine:
            handle = subprocess.Popen([cmd, "/d", "/c", "Start-Windows.cmd", "--port", str(port), "--no-browser"],
                                      cwd=root, env=env, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pid = handle.pid
        else:
            # No service-specific binary is launched here; the desktop opens the
            # ordinary distributed .cmd via the user's shell association.
            shell_command = ("$ErrorActionPreference='Stop'; "
                             "$p=Start-Process -FilePath (Resolve-Path './Start-Windows.cmd').Path "
                             "-ArgumentList @('--port', $env:SLS_QA_PORT) -PassThru; $p.Id")
            launch = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", shell_command],
                                    cwd=root, env=env, capture_output=True, text=True, check=True, timeout=20)
            pid = int(launch.stdout.strip())
        try:
            deadline = time.monotonic() + 42
            while True:
                try:
                    health = request(port, "/api/health")
                    break
                except (ConnectionError, OSError, http.client.HTTPException):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("The desktop launcher did not start its local service")
                    time.sleep(0.25)
            assert health["ok"] and health["version"] == (root / "VERSION").read_text().strip()
            assert b"app.js" in request(port, "/")
            cmdline = [cmd, "/d", "/c", "Reconnect-Windows.cmd", "--no-browser", "--json-ready"]
            pairing = subprocess.run(cmdline, cwd=root, env=env, capture_output=True,
                                     text=True, encoding="utf-8", timeout=30, check=True)
            ready = json.loads(pairing.stdout)
            assert ready["existing_service"] and ready["base_url"] == f"http://127.0.0.1:{port}"
            assert ready["extension_code"] and "pair-extension" in ready["dashboard_url"]
            owner = request(port, "/api/pair", payload={"code": ready["code"]})["token"]
            subject = owner_write(port, "/api/subjects", owner, name="Windows release QA")
            instance = owner_write(port, "/api/instances", owner, subject_id=subject["subject_id"], name="Portable")
            grant = owner_write(port, "/api/credentials", owner, instance_id=instance["instance_id"],
                                subject_id=subject["subject_id"])
            assert Path(grant["stdio"]["command"]).resolve() == runtime
            agent_env = {**env, "SILICON_AGENT_TOKEN": grant["token"],
                         "SILICON_MCP_URL": f"http://127.0.0.1:{port}/mcp"}
            tools = mcp_call(grant["stdio"], agent_env, "tools/list", {})["tools"]
            assert any(t["name"] == "report_state" for t in tools)
            payload = {"name": "report_state", "arguments": {"state_text": "Windows binary protocol fixture.",
                       "idempotency_key": uuid.uuid4().hex}}
            saved = mcp_call(grant["stdio"], agent_env, "tools/call", payload)["structuredContent"]
            assert saved["source"] == "agent_direct"
            with closing(sqlite3.connect(Path(temp) / "state.sqlite3")) as db:
                assert db.execute("SELECT hash FROM events WHERE event_id=?", (saved["event_id"],)).fetchone() == (saved["hash"],)
            result = {"outcome": "PASS", "os": "Wine compatibility" if wine else platform.platform(),
                              "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                              "system_python_on_launcher_path": False,
                              "launcher": "cmd.exe" if wine else "Windows ShellExecute / .cmd shell association",
                              "public_proxies": "disabled for this test process",
                              "dashboard_http": 200, "reconnect_launcher": "Reconnect-Windows.cmd",
                              "paired": True, "mcp_stdio_tools": len(tools),
                              "sqlite_event_matches_mcp": True}
        finally:
            subprocess.run([str(native_dir / "taskkill.exe"), "/PID", str(pid), "/T", "/F"],
                           cwd=root, env=env, capture_output=True, timeout=20)
            if handle is not None:
                handle.wait(timeout=15)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wine", action="store_true")
    opts = parser.parse_args()
    check(Path(__file__).resolve().parents[1], opts.wine)
