#!/usr/bin/env python3
"""Start the offline, owner-controlled Silicon Life State desktop service."""
import argparse
import json
import math
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import time
from collections import deque
import uuid
import webbrowser
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))  # Also works with the isolated Windows embeddable runtime.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "mcp-server"))
from model_chat import Chat
from access import Access, AccessError
from dashboard_session import browser_reply, browser_token, cookie_header
from host_wizard import HostWizard
from schemas import document
from reconnect import bundle, endpoint_proof, existing_endpoint, publish_endpoint
from packages.core.store import DomainError, Store
from mcp_wire import error as rpc_error, handle_http

VERSION = "1.0.2"
DEFAULT_PORT = 47831
ASSETS = ROOT / "apps" / "dashboard"
MAX_BYTES = 1024 * 1024
EXT_ID = re.compile(r"[a-p]{32}\Z")
BASE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


def data_home():
    if os.environ.get("SILICON_DATA_DIR"):
        return Path(os.environ["SILICON_DATA_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "SiliconLifeState"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/SiliconLifeState"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "silicon-life-state"


def object_fields(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate key")
        obj[key] = value
    return obj


def reject_constant(_):
    raise ValueError("non-finite number")


def number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def require_keys(obj, allowed):
    if set(obj) - set(allowed):
        raise AccessError(400, "UNKNOWN_FIELD", "请求中含有不支持的字段。")


def fresh_key():
    return str(uuid.uuid4())


@contextmanager
def exclusive_service(data_dir):
    """Exclude a second serving process or simultaneous offline restore."""
    path = Path(data_dir) / "service.lock"
    with path.open("a+b") as stream:
        if sys.platform == "win32":
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise AccessError(409, "SERVICE_ACTIVE", "该目录已有运行中的服务。") from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise AccessError(409, "SERVICE_ACTIVE", "该目录已有运行中的服务。") from exc
        yield


class InvocationBudget:
    """Per-grant rolling-window quota. No bearer material or input content is retained."""
    def __init__(self, maximum=240, seconds=60):
        self.maximum = maximum
        self.seconds = seconds
        self.history = {}
        self.sweep_at = 0
        self.lock = threading.Lock()

    def admit(self, grant_id):
        with self.lock:
            now = time.monotonic()
            cutoff = now - self.seconds
            if self.sweep_at <= now:
                self.history = {grant: times for grant, times in self.history.items() if times[-1] > cutoff}
                self.sweep_at = now + self.seconds
            times = self.history.setdefault(grant_id, deque())
            while times and times[0] <= cutoff:
                times.popleft()
            if len(times) >= self.maximum:
                return max(1, math.ceil(times[0] - cutoff))
            times.append(now)
            return 0


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def __init__(self, port, store, access):
        self.store = store
        store.reconcile_host_files()
        self.launch_key = os.urandom(32)
        self.invocations = InvocationBudget()
        self.chats = Chat(self)
        self.access = access
        self.mutations = threading.RLock()
        self.connections = threading.BoundedSemaphore(64)
        super().__init__(("127.0.0.1", port), Handler)
        self.base_url = f"http://127.0.0.1:{self.server_port}"
        self.host_wizard = HostWizard(store, self.base_url)

    def service_actions(self):
        self.chats.expire()
        super().service_actions()

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 close semantics prevent reuse of a rejected request body.
    server_version = "SiliconLifeState"
    sys_version = ""
    timeout = 10

    def log_message(self, fmt, *args):
        # Never persist browser paths, MCP inputs, pairing codes or authorization headers.
        pass

    def header(self, name):
        vals = self.headers.get_all(name) or []
        if len(vals) > 1:
            raise AccessError(400, "DUPLICATE_HEADER", "请求头重复。")
        return vals[0] if vals else ""

    def origins(self):
        if self.header("Host") != self.server.base_url.removeprefix("http://"):
            raise AccessError(403, "INVALID_HOST", "仅允许本机服务地址。")
        origin = self.header("Origin")
        hint = self.header("X-SLS-Extension")
        if hint and not EXT_ID.fullmatch(hint):
            raise AccessError(403, "INVALID_EXTENSION", "扩展来源无效。")
        base = self.server.base_url
        if origin.startswith("chrome-extension://") and EXT_ID.fullmatch(origin[19:]):
            if hint and hint != origin[19:]:
                raise AccessError(403, "ORIGIN_MISMATCH", "扩展来源不匹配。")
            self.cors_origin = origin
            return origin
        if origin and origin != base:
            raise AccessError(403, "INVALID_ORIGIN", "此网页来源未获授权。")
        if hint and origin:
            raise AccessError(403, "ORIGIN_MISMATCH", "请求来源不匹配。")
        if self.header("Sec-Fetch-Site") == "cross-site" and not hint and not origin:
            raise AccessError(403, "INVALID_ORIGIN", "跨站请求被拒绝。")
        return "chrome-extension://" + hint if hint else base

    def bearer(self):
        auth = self.header("Authorization")
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_.~-]{8,256})", auth, re.I)
        if not match:
            raise AccessError(401, "AUTH_REQUIRED", "需要有效的本机访问凭据。")
        return match.group(1)

    def payload(self):
        if self.header("Transfer-Encoding"):
            raise AccessError(400, "UNSUPPORTED_ENCODING", "此服务接收带长度的 JSON 请求。")
        content_type = self.header("Content-Type").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise AccessError(415, "JSON_REQUIRED", "仅接收 application/json。")
        length = self.header("Content-Length")
        if not re.fullmatch(r"\d{1,8}", length):
            raise AccessError(411, "LENGTH_REQUIRED", "请声明请求长度。")
        if int(length) > MAX_BYTES:
            raise AccessError(413, "BODY_TOO_LARGE", "请求超过 1 MiB。")
        try:
            raw = self.rfile.read(int(length))
            if len(raw) != int(length):
                raise ValueError("truncated")
            obj = json.loads(raw.decode("utf-8"), object_pairs_hook=object_fields,
                             parse_constant=reject_constant, parse_float=number)
            # Reject isolated surrogate escapes and excessively deep containers.
            json.dumps(obj, ensure_ascii=False).encode("utf-8")
            return obj
        except (ValueError, RecursionError, OverflowError):
            raise AccessError(400, "INVALID_JSON", "无效的 UTF-8 JSON。") from None

    def reply(self, status, result=None, *, headers=None, content_type="application/json; charset=utf-8"):
        if isinstance(result, bytes):
            body = result
        elif result is None:
            body = b""
        else:
            body = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", BASE_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if getattr(self, "cors_origin", None):
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
            self.send_header("Vary", "Origin")
        for key, value in (headers or {}).items():
            if key.lower() not in {"cache-control", "content-length", "content-type"}:
                self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def serve_file(self, path):
        name = unquote(path).lstrip("/") or "index.html"
        if "\\" in name or "\x00" in name or any(s in (".", "..", "") for s in name.split("/")):
            raise AccessError(404, "NOT_FOUND", "未找到页面。")
        file = (ASSETS / name).resolve()
        if not file.is_relative_to(ASSETS) or file.suffix.lower() not in {
            ".html", ".css", ".js", ".mjs", ".svg", ".png", ".webp", ".ico", ".woff2", ".woff"
        } or not file.is_file():
            raise AccessError(404, "NOT_FOUND", "未找到页面。")
        types = {".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript",
                 ".svg": "image/svg+xml", ".html": "text/html; charset=utf-8"}
        self.reply(200, file.read_bytes(), content_type=types.get(file.suffix, mimetypes.guess_type(file)[0] or "application/octet-stream"))

    def dispatch(self):
        self.cors_origin = None
        origin = self.origins()
        url = urlsplit(self.path)
        if url.scheme or url.netloc or not self.path.startswith("/") or self.path.startswith("//"):
            raise AccessError(400, "INVALID_PATH", "请求路径无效。")
        path = url.path
        store, access = self.server.store, self.server.access
        if self.command == "OPTIONS":
            if origin.startswith("chrome-extension://") and path.startswith("/api/"):
                self.reply(204, headers={"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                                         "Access-Control-Allow-Headers": "Authorization, Content-Type, X-SLS-Extension"})
            else:
                self.reply(405, headers={"Allow": "POST" if path == "/mcp" else "GET, POST"})
            return
        if path == "/mcp":
            if origin != self.server.base_url:
                raise AccessError(403, "MCP_ORIGIN_DENIED", "此入口仅接受本机 Agent。")
            token = self.bearer()
            installation = token.startswith("slsi_")
            principal = store.inspect_installation(token) if installation else store.authenticate_agent(token)
            if self.command != "POST":
                self.reply(405, headers={"Allow": "POST"})
                return
            try:
                obj = self.payload()
            except AccessError as exc:
                if exc.code != "INVALID_JSON":
                    raise
                self.reply(400, rpc_error(None, -32700, "Parse error"))
                return
            if installation and isinstance(obj,dict) and obj.get("method") not in {"tools/list","server/discover","initialize","ping","notifications/initialized"}:
                raise AccessError(403,"INSTANCE_GRANT_REQUIRED","请通过宿主绑定对话后使用分身凭据调用工具。")
            if isinstance(obj, dict) and obj.get("method") == "tools/call":
                retry = self.server.invocations.admit(principal["grant_id"])
                if retry:
                    rid = obj.get("id") if type(obj.get("id")) in (int, str) else None
                    self.reply(429, rpc_error(rid, -32000, "Per-grant invocation limit reached"),
                               headers={"Retry-After": str(retry)})
                    return
            expected_session = self.header("SLS-Expected-Session") or None
            status, headers, answer = handle_http(obj, self.headers, lambda name, args: store.tool(
                token, name, args, expected_session=expected_session))
            if status == 200 and isinstance(obj, dict) and obj.get("method") == "tools/list":
                self.server.host_wizard.discovery(principal.get("installation_id") or principal["grant_id"], obj)
            self.reply(status, answer, headers=headers)
            return
        if not path.startswith("/api/"):
            if self.command in {"GET", "HEAD"}:
                self.serve_file(path)
            else:
                self.reply(405, headers={"Allow": "GET, HEAD"})
            return
        if path in {"/api/installations/bind","/api/installations/inspect"} and self.command == "POST":
            if origin != self.server.base_url or self.header("Origin"):
                raise AccessError(403,"HOST_REQUIRED","请使用本机受信任的宿主适配器。")
            token, body = self.bearer(), self.payload()
            if not isinstance(body,dict):
                raise AccessError(400,"INVALID_INPUT","请求应为 JSON 对象。")
            if path.endswith("/inspect"):
                require_keys(body,set())
                result = store.inspect_installation(token)
            else:
                result = store.bind_installation(token,body)
            self.reply(200,result)
            return
        if path == "/api/health" and self.command == "GET":
            health = {"ok": True, "version": VERSION, "local_only": True}
            challenge = self.header("X-SLS-Reconnect-Challenge")
            if challenge:
                if self.header("Origin") or not re.fullmatch(r"[0-9a-f]{64}", challenge):
                    raise AccessError(400, "INVALID_CHALLENGE", "本机服务核验请求无效。")
                health["reconnect_proof"] = endpoint_proof(self.server.launch_key, self.server.server_port, challenge)
            self.reply(200, health)
            return
        if path == "/api/extension/uninstalled" and self.command == "POST":
            if self.header("Origin") != self.server.base_url:
                raise AccessError(403, "DASHBOARD_REQUIRED", "请打开本机扩展注销页面。")
            body = self.payload()
            if not isinstance(body, dict) or set(body) != {"ticket"}:
                raise AccessError(400, "INVALID_TICKET", "扩展注销需要有效标识。")
            with self.server.mutations:
                result = access.uninstall_extension(body["ticket"])
            self.reply(200, result)
            return
        if path in {"/api/browser/pair", "/api/browser/upgrade"} and self.command == "POST":
            if self.header("Origin") != self.server.base_url or origin != self.server.base_url:
                raise AccessError(403, "DASHBOARD_REQUIRED", "请从本机仪表盘配对。")
            body = self.payload()
            if not isinstance(body, dict):
                raise AccessError(400, "INVALID_INPUT", "配对需要 JSON 对象。")
            with self.server.mutations:
                if path.endswith("/upgrade"):
                    require_keys(body, set())
                    old = self.bearer()
                    token = access.rotate(old, origin)
                    self.server.chats.invalidate(owner=old)
                else:
                    require_keys(body, {"code"})
                    token = access.exchange(body.get("code"), origin)["token"]
            browser_reply(self, token)
            return
        if path == "/api/pair" and self.command == "POST":
            body = self.payload()
            if not isinstance(body, dict):
                raise AccessError(400, "INVALID_INPUT", "配对需要 JSON 对象。")
            require_keys(body, {"code"})
            self.reply(200, access.exchange(body.get("code"), origin))
            return

        dashboard = bool(self.header("X-SLS-Dashboard"))
        token = browser_token(self, origin) if dashboard else self.bearer()
        access.check(token, origin)
        if dashboard and path == "/api/browser/session" and self.command == "GET":
            browser_reply(self, token)
            return
        if path == "/api/pair/rotate" and self.command == "POST":
            if self.payload() != {}:
                raise AccessError(400, "INVALID_INPUT", "轮换无需参数。")
            with self.server.mutations:
                replacement = access.rotate(token, origin)
                self.server.chats.invalidate(owner=token)
            if dashboard:
                browser_reply(self, replacement)
            else:
                self.reply(200, {"token": replacement})
            return
        if self.command == "GET":
            query = parse_qs(url.query, max_num_fields=8)
            paths = {"/api/snapshot": "snapshot", "/api/export": "export",
                     "/api/backups": "list_backups", "/api/integrity": "verify",
                     "/api/installations": "list_installations", "/api/credentials": "list_agents", "/api/subjects": "list_subjects"}
            if path == "/api/schema":
                self.reply(200, document())
                return
            if path == "/api/settings":
                self.reply(200, access.settings())
                return
            if path not in paths:
                raise AccessError(404, "NOT_FOUND", "接口不存在。")
            args = {}
            if path == "/api/snapshot" and "subject_id" in query:
                args["subject_id"] = query["subject_id"][0]
            result = store.admin(paths[path], args)
            self.reply(200, result)
            return
        if self.command != "POST":
            self.reply(405, headers={"Allow": "GET, POST"})
            return
        body = self.payload()
        if not isinstance(body, dict):
            raise AccessError(400, "INVALID_INPUT", "请求应为 JSON 对象。")
        if path.startswith("/api/chat/"):
            self.reply(200, self.server.chats.dispatch(path.removeprefix("/api/chat/"), body, token, origin))
            return
        with self.server.mutations:
            # A pairing may have been revoked between the initial check and taking the lock.
            access.check(token, origin)
            result = self.mutate(path, body, token, origin)
        headers = {"Set-Cookie": cookie_header(self.server.server_port, "", 0)} if dashboard and path == "/api/logout" else None
        self.reply(200, result, headers=headers)

    def mutate(self, path, body, token, origin):
        store, access = self.server.store, self.server.access
        if path == "/api/pair/status":
            require_keys(body, {"code"})
            return access.code_status(body.get("code"))
        if path.startswith("/api/hosts/"):
            if origin != self.server.base_url:
                raise AccessError(403, "DASHBOARD_REQUIRED", "请从已配对的本机仪表盘配置 Agent 宿主。")
            return self.server.host_wizard.dispatch(token, path.removeprefix("/api/hosts/"), body)
        if path == "/api/pair/code":
            require_keys(body, {"target", "idempotency_key", "replaces"})
            return access.paired_code(token, body.get("idempotency_key"), body.get("target", "extension"), body.get("replaces"))
        if path == "/api/logout":
            require_keys(body, {"idempotency_key"})
            result = access.revoke(token)
            self.server.chats.invalidate(owner=token)
            return result
        if path == "/api/settings":
            require_keys(body, {"observation_enabled", "idempotency_key"})
            if type(body.get("observation_enabled")) is not bool:
                raise AccessError(400, "INVALID_SETTING", "observation_enabled 必须为布尔值。")
            return access.settings(body["observation_enabled"], token=token, key=body.get("idempotency_key"))
        if path == "/api/observations":
            source = body.pop("source", None)
            body.pop("subject_id", None)  # The authorized instance owns its subject association.
            actions = {"agent_visible_text": "observe", "user_annotation": "annotate", "model_estimated": "estimate"}
            if not isinstance(source, str) or source not in actions:
                raise AccessError(400, "INVALID_SOURCE", "仅接收网页可见陈述、用户注释或从记录推算的模型值。")
            if source == "agent_visible_text" and not origin.startswith("chrome-extension://"):
                raise AccessError(403, "WEB_ADAPTER_REQUIRED", "请从已配对的网页观察扩展保存可见陈述。")
            if source == "agent_visible_text" and not access.settings()["observation_enabled"]:
                raise AccessError(403, "OBSERVATION_PAUSED", "所有者已暂停网页观察。")
            return store.admin(actions[source], body)
        match = re.fullmatch(r"/api/requests/([A-Za-z0-9_-]{1,128})/respond", path)
        if match:
            require_keys(body, {"status", "stage", "note", "text", "idempotency_key"})
            args = {"request_id": match.group(1), "stage": body.get("stage", body.get("status")),
                    "idempotency_key": body.get("idempotency_key")}
            if "text" in body or "note" in body:
                args["text"] = body.get("text", body.get("note"))
            return store.admin("respond", args)
        if path == "/api/runtime/sample":
            require_keys(body, {"instance_id", "request_id", "idempotency_key"})
            return store.admin("sample_runtime", body)
        if path == "/api/delete":
            require_keys(body, {"scope", "id", "confirm", "idempotency_key"})
            if body.get("confirm") is not True:
                raise AccessError(400, "CONFIRM_REQUIRED", "删除需要明确确认。")
            scope = body.get("scope")
            if scope not in ("session", "subject", "all"):
                raise AccessError(400, "INVALID_SCOPE", "删除范围无效。")
            args = {"idempotency_key": body.get("idempotency_key")}
            if scope != "all":
                args[scope + "_id"] = body.get("id")
            result = store.admin("delete_" + scope, args)
            self.server.chats.invalidate(scope=scope, target=body.get("id"))
            if scope == "all":
                access.reset(token)
            return result
        if path.startswith("/api/installations") and origin != self.server.base_url:
            raise AccessError(403,"DASHBOARD_REQUIRED","请从已配对的本机仪表盘管理安装授权。")
        actions = {"/api/installations": "issue_installation",
                   "/api/installations/revoke": "revoke_installation", "/api/installations/rotate": "rotate_installation",
                   "/api/installations/restore": "restore_installation", "/api/subjects/rename": "rename_subject",
                   "/api/instances/rename": "rename_instance", "/api/subjects": "create_subject", "/api/instances": "create_instance",
                   "/api/credentials": "issue_agent", "/api/credentials/revoke": "revoke_agent",
                   "/api/level": "set_level", "/api/backup": "backup", "/api/restore": "restore"}
        if path not in actions:
            raise AccessError(404, "NOT_FOUND", "接口不存在。")
        result = store.admin(actions[path], body)
        if path == "/api/restore":
            self.server.chats.invalidate()
        if path == "/api/credentials/revoke":
            self.server.chats.invalidate(grant_id=result["grant_id"])
        if path == "/api/credentials":
            result = {**result, "stdio": {
                "command": sys.executable,
                "args": [str(ROOT / "packages" / "mcp-server" / "stdio.py")]
            }}
        return result

    def handle_method(self):
        try:
            self.dispatch()
        except (AccessError, DomainError) as exc:
            challenge = {"WWW-Authenticate": 'Bearer realm="SiliconLifeState"'} if exc.status == 401 else None
            self.reply(exc.status, {"error": {"code": exc.code, "message": str(exc)}}, headers=challenge)
        except (ConnectionError, TimeoutError):
            self.close_connection = True
        except (sqlite3.DatabaseError, OSError):
            self.reply(503, {"error": {"code": "STORAGE_UNAVAILABLE", "message": "本地存储不可用。可关闭服务后使用 --recover 恢复备份。"}})
        except (ValueError, RecursionError):
            self.reply(400, {"error": {"code": "INVALID_INPUT", "message": "请求格式无效。"}})
        except Exception as exc:
            # Type only: raw messages may include private event content.
            print(f"Service error: {type(exc).__name__}", file=sys.stderr)
            self.reply(500, {"error": {"code": "INTERNAL_ERROR", "message": "本地处理失败。"}})

    do_GET = do_HEAD = do_POST = do_DELETE = do_PUT = do_OPTIONS = handle_method


def parser():
    p = argparse.ArgumentParser(description="Silicon Life State · local status service")
    p.add_argument("--data-dir", type=Path, default=data_home(), help="private SQLite and managed backups directory")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="loopback TCP port (0: choose a free port)")
    p.add_argument("--no-browser", action="store_true", help="do not open the dashboard automatically")
    p.add_argument("--json-ready", action="store_true", help="print machine-readable startup/pairing information")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--resume-service", action="store_true", help="serve the existing ledger without opening windows or issuing pairing codes")
    group.add_argument("--reconnect", action="store_true", help="open a fresh authenticated pairing dashboard on this installation")
    group.add_argument("--unpair-all", action="store_true", help="invalidate all owner dashboard/extension sessions and unused pairing codes")
    group.add_argument("--pair", action="store_true", help="issue a new 10-minute pairing code for a running service")
    group.add_argument("--list-backups", action="store_true", help="list managed backups")
    group.add_argument("--recover", metavar="BACKUP_ID", help="recover offline from a managed backup, including after DB corruption")
    p.add_argument("--target", choices=["dashboard", "extension"], default="dashboard", help="client for --pair")
    return p


def show_connection(args, info, data_dir, already_running):
    if args.json_ready:
        print(json.dumps({**info, "version": VERSION, "existing_service": already_running}), flush=True)
    else:
        status = "已连接运行中的本地服务。" if already_running else "请保留此窗口。按 Ctrl+C 退出服务。"
        print(f"\n硅基生命状态  {VERSION}\n作者：匹夫 · 岑衡川 · 沈回音\n\n本机仪表盘\n{info['dashboard_url']}"
              f"\n\n浏览器扩展配对码（10 分钟内有效，仅使用一次）\n{info['extension_code']}"
              f"\n到期时间（UTC）  {info['extension_expires_at']}"
              f"\n\n数据目录  {data_dir}\nMCP 地址  {info['base_url']}/mcp\n{status}\n", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(info["dashboard_url"])
        except webbrowser.Error:
            pass


def main():
    args = parser().parse_args()
    if not 0 <= args.port <= 65535:
        parser().error("--port must be 0..65535")
    if os.name != "nt":
        os.umask(0o077)
    data_dir = args.data_dir.expanduser().resolve()
    if args.resume_service:
        if not data_dir.is_dir():
            raise ValueError("Existing data directory is unavailable.")
    else:
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    maintenance = args.unpair_all or args.pair or args.list_backups or args.recover
    if not (maintenance or args.resume_service):
        base = existing_endpoint(data_dir)
        if base:
            show_connection(args, bundle(Access(data_dir), base, reconnect=args.reconnect), data_dir, True)
            return 0
    if args.unpair_all:
        print(json.dumps(Access(data_dir).unpair_all()))
        return 0
    if args.pair:
        result = Access(data_dir).issue_code(args.target)
        print(json.dumps(result) if args.json_ready else
              f"{args.target} 配对码（10 分钟有效）\n{result['code']}", flush=True)
        return 0
    if args.list_backups:
        print(json.dumps(Store(data_dir).admin("list_backups", {}), ensure_ascii=False, indent=2))
        return 0
    with exclusive_service(data_dir):
        if args.resume_service:
            # Validate the existing ledger under the service lifetime lock. A missing,
            # empty or unrelated SQLite file must never be initialized by a host launch.
            if not (data_dir/"issuance.key").is_file():
                raise ValueError("Existing installation key is unavailable.")
            ledger = (data_dir/"state.sqlite3").as_uri() + "?mode=rw"
            with closing(sqlite3.connect(ledger,uri=True)) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
                    raise ValueError("Existing ledger is missing its events table.")
        store = Store(data_dir)
        if args.recover:
            result = store.admin("restore", {"backup_id": args.recover, "idempotency_key": fresh_key()})
            print(json.dumps(result, ensure_ascii=False))
            return 0
        access = Access(data_dir)
        with LocalServer(args.port, store, access) as server, publish_endpoint(data_dir, server):
            if not args.resume_service:
                info = bundle(access, server.base_url, reconnect=args.reconnect)
                show_connection(args, info, data_dir, False)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        sys.exit(main())
    except (AccessError, DomainError, sqlite3.DatabaseError, OSError, ValueError) as problem:
        print(str(problem), file=sys.stderr)
        sys.exit(1)
