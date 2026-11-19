"""Authenticated stdio bridge. Launch from any working directory with Python 3.10+."""
import http.client
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from pathlib import Path

# Windows embeddable Python isolates sys.path via its ._pth file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_client import meta, send
from mcp_wire import CAPABILITIES, INFO, INSTRUCTIONS, LEGACY, PREFIX, VERSION, error

MAX_LINE = 128 * 1024

def main():
    if not os.environ.get("SILICON_AGENT_TOKEN"):
        print("Set SILICON_AGENT_TOKEN in the MCP host environment.",file=sys.stderr)
        return 2
    lock = Lock()
    active = {}
    slots = BoundedSemaphore(32)
    legacy_ready = False

    def emit(obj):
        data = json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
        sys.stdout.buffer.write(data+b"\n")
        sys.stdout.buffer.flush()

    def run_request(msg, old, marker):
        rid = msg["id"]
        with lock:
            if active.get(rid) is not marker:
                # A queued write was cancelled before dispatch to the service.
                slots.release()
                return
        try:
            if old:
                params = dict(msg.get("params",{}))
                params["_meta"] = {**params.get("_meta",{}),**meta("silicon-life-state-stdio-legacy")}
                msg = {**msg,"params":params}
            reply = send(msg)
            if old and "result" in reply:
                reply["result"].pop("resultType",None)
                reply["result"].pop("_meta",None)
            elif not old and msg["method"] == "server/discover" and "result" in reply:
                reply["result"]["supportedVersions"] = [VERSION,LEGACY]
        except (ValueError,OSError,TypeError,RecursionError,http.client.HTTPException):
            reply = error(rid,-32603,"Cannot reach or parse the authorized loopback MCP service")
        finally:
            slots.release()
        with lock:
            if active.get(rid) is marker:
                del active[rid]
                emit(reply)

    with ThreadPoolExecutor(max_workers=4,thread_name_prefix="sls-stdio") as pool:
        while True:
            line = sys.stdin.buffer.readline(MAX_LINE+1)
            if not line:
                break
            if len(line)>MAX_LINE:
                while line and not line.endswith(b"\n"):
                    line = sys.stdin.buffer.readline(MAX_LINE+1)
                with lock:
                    emit(error(None,-32600,"Message exceeds size limit"))
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (ValueError,UnicodeError,RecursionError):
                with lock:
                    emit(error(None,-32700,"Invalid JSON"))
                continue
            with lock:
                if not isinstance(msg,dict) or msg.get("jsonrpc")!="2.0" or not isinstance(msg.get("method"),str):
                    emit(error(None,-32600,"Invalid request"))
                    continue
                params = msg.get("params",{})
                rid = msg.get("id")
                method = msg["method"]
                if not isinstance(params,dict) or not isinstance(params.get("_meta",{}),dict):
                    if "id" in msg:
                        emit(error(rid,-32602,"Expected named parameters"))
                    continue
                if "id" not in msg:
                    if method=="notifications/cancelled" and type(params.get("requestId")) in (int,str):
                        active.pop(params["requestId"],None)
                    continue
                if type(rid) not in (int,str) or rid in active:
                    emit(error(None,-32600,"Invalid or duplicate request ID"))
                    continue
                modern = PREFIX+"protocolVersion" in params.get("_meta",{})
                if method=="initialize" and not modern:
                    if not isinstance(params.get("protocolVersion"),str) or not isinstance(params.get("clientInfo"),dict) or not isinstance(params.get("capabilities"),dict):
                        emit(error(rid,-32602,"Invalid initialization parameters"))
                        continue
                    legacy_ready = True
                    emit({"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":LEGACY,"capabilities":CAPABILITIES,"serverInfo":INFO,"instructions":INSTRUCTIONS}})
                    continue
                if not modern and not legacy_ready:
                    emit(error(rid,-32602,"Supply modern request _meta or initialize legacy MCP"))
                    continue
                if not modern and method=="ping":
                    emit({"jsonrpc":"2.0","id":rid,"result":{}})
                    continue
                if not slots.acquire(blocking=False):
                    emit(error(rid,-32603,"Too many in-flight requests"))
                    continue
                marker = object()
                active[rid] = marker
                pool.submit(run_request,msg,not modern,marker)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
