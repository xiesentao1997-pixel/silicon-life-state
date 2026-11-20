"""Start exactly the existing installation selected by the owner, without creating a ledger."""
import os
from pathlib import Path
import subprocess
import sys
import time
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/local-service"))
from reconnect import existing_endpoint


class StartupError(ValueError):
    pass


@contextmanager
def launch_lock(directory):
    # Blocking OS locks disappear on process exit. The server holds its own separate
    # lifetime lock, including when started manually outside this bridge.
    with (directory / "stdio-start.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def service_url():
    selected = os.environ.get("SILICON_DATA_DIR")
    if not selected:
        # Historical/handwritten fixed-instance configs contain only a URL and a
        # token. Without an installation directory we cannot safely start a ledger.
        return os.environ.get("SILICON_MCP_URL", "http://127.0.0.1:47831/mcp")
    directory = Path(selected)
    if not directory.is_absolute() or not all((directory / n).is_file() for n in ("state.sqlite3", "issuance.key")):
        raise StartupError("Existing installation database or issuance key missing at SILICON_DATA_DIR. Restore its original directory or backup.")
    base = existing_endpoint(directory)
    if base:
        return base + "/mcp"
    with launch_lock(directory):
        base = existing_endpoint(directory)
        if base:
            return base + "/mcp"
        from local_client import connection
        configured = connection()
        port = configured.port
        configured.close()
        cmd = [sys.executable, str(ROOT/"apps/local-service/server.py"), "--data-dir", str(directory),
               "--resume-service", "--no-browser", "--port", str(port)]
        options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                   if os.name == "nt" else {"start_new_session": True})
        # Do not pass bridge credentials into the background service.
        env = {k:v for k,v in os.environ.items() if k not in ("SILICON_AGENT_TOKEN", "SILICON_INSTALLATION_TOKEN")}
        with open(os.devnull, "r+b") as null:
            process = subprocess.Popen(cmd, stdin=null, stdout=null, stderr=null, env=env, **options)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            base = existing_endpoint(directory)
            if base:
                return base + "/mcp"
            if process.poll() is not None:
                # A manual startup can acquire service.lock while this bridge is starting.
                if not (directory/"service.lock").exists():
                    break
            time.sleep(.08)
    raise StartupError("The selected local service did not pass its health check. Run Start-Windows.cmd or start.sh with the original data directory; check the configured port and database.")
