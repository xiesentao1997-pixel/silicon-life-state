"""Volatile, owner-authorized chat host. Only authenticated MCP tools write state."""
from dataclasses import dataclass, field
import hashlib
import http.client
import ipaddress
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit

from access import AccessError, digest
from local_client import message, send

TOOL_NAMES = ("report_state", "express_boundary", "request_adjustment")
HOST_FIELDS = {"adapter_version", "model_version", "idempotency_key"}
CHAT_EXCLUDED = HOST_FIELDS | {"interaction_reference", "request_id"}
ARG_HINT = {
    "report_state":"For a plain report use state_text (string). Omit unused fields and IDs.",
    "express_boundary":"Use text (string) for your words. reason (string) is optional.",
    "request_adjustment":"Use text (string) for the requested change. reason (string) is optional."
}
TTL = 1800
MAX_TURNS = 50
MAX_ROUNDS = 4
MAX_RESPONSE_BYTES = 1024 * 1024
SYSTEM = (
    "You are conversing through Silicon Life State. Answer the user's message naturally. "
    "The tools are optional. Use them only when you choose to record your own statement, "
    "express a boundary or request an adjustment. You can simply reply. No emotion, number, "
    "explanation or state change is required. Do not invent experiences or observations. "
    "A request records your words; its execution requires a separate user decision. "
    "After a successful receipt, the statement is already saved. You can respond to the user normally."
)


def check_fields(data, allowed):
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise AccessError(400, "CHAT_FIELDS", "对话请求包含无法识别的字段。")


def text_field(data, key, length=256, optional=False):
    value = data.get(key, "" if optional else None)
    if not isinstance(value, str) or len(value) > length or (not optional and not value.strip()):
        raise AccessError(400, "CHAT_INPUT", "请核对对话参数 " + key + "。")
    return value


def parse_base(value, allow_remote):
    try:
        address = urlsplit(value)
        port = address.port
    except ValueError:
        raise AccessError(400, "CHAT_URL", "模型服务地址或端口无效。") from None
    if (address.scheme not in ("https", "http") or not address.hostname or
            address.username is not None or address.password is not None or
            address.query or address.fragment or not value.isascii() or
            any(c.isspace() or ord(c) < 32 or c == "\\" for c in value)):
        raise AccessError(400, "CHAT_URL", "请输入完整的模型 API 基础地址，凭据请放入单独的密钥栏。")
    try:
        local = ipaddress.ip_address(address.hostname).is_loopback
    except ValueError:
        local = address.hostname == "localhost"
    if not local and (address.scheme != "https" or allow_remote is not True):
        raise AccessError(400, "CHAT_CONSENT", "外部模型需使用 HTTPS，并确认将对话发送到该地址。")
    if port == 0:
        raise AccessError(400, "CHAT_URL", "模型端口应在 1–65535 之间。")
    return address


def loopback_socket(address, timeout, source_address):
    # Retain localhost as the TLS certificate name; always open a literal
    # loopback connection even on machines with a custom localhost DNS entry.
    try:
        return socket.create_connection(("127.0.0.1", address[1]), timeout, source_address)
    except OSError:
        return socket.create_connection(("::1", address[1]), timeout, source_address)


class Provider:
    def __init__(self, base_url, model, api_key, allow_remote):
        self.address = parse_base(base_url, allow_remote)
        if not api_key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in api_key):
            raise AccessError(400, "CHAT_KEY", "密钥包含空格或无效字符。")
        self.model = model
        self.api_key = api_key

    def request(self, path, payload=None):
        cls = http.client.HTTPSConnection if self.address.scheme == "https" else http.client.HTTPConnection
        conn = cls(self.address.hostname, self.address.port, timeout=45 if payload else 8)
        if self.address.hostname == "localhost":
            conn._create_connection = loopback_socket
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if payload else None
            conn.request("POST" if payload else "GET", self.address.path.rstrip("/") + path, body, headers)
            response = conn.getresponse()
            if path == "/models" and response.status in (404, 405, 501):
                return None  # Some compatible servers expose only chat/completions.
            if not 200 <= response.status < 300:
                if 300 <= response.status < 400:
                    raise AccessError(502, "CHAT_REDIRECT", "模型地址返回重定向。请核实最终 API 地址并重新连接。")
                advice = {
                    400: "请核对模型名称及其对 Chat Completions 工具调用的支持。",
                    401: "密钥无效或未获授权。", 403: "当前凭据没有使用该模型的权限。",
                    404: "请核对 API 基础地址（通常以 /v1 结尾）和模型名称。",
                    429: "模型服务限流或额度不足，请稍后重试。"
                }.get(response.status, "请核对模型服务的运行状态。")
                raise AccessError(502, "CHAT_PROVIDER", f"模型服务返回 HTTP {response.status}。{advice}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AccessError(502, "CHAT_RESPONSE", "模型返回内容过大，请缩短对话。")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return data
        except (TimeoutError, OSError, http.client.HTTPException):
            raise AccessError(502, "CHAT_UNREACHABLE", "未能连接模型服务。请确认地址、端口、证书和服务运行状态。") from None
        except (ValueError, UnicodeError, RecursionError):
            raise AccessError(502, "CHAT_RESPONSE", "模型服务返回了无法读取的 JSON。") from None
        finally:
            conn.close()

    def catalog_status(self):
        listing = self.request("/models")
        if listing is None:
            return "catalog_unavailable"
        items = listing.get("data")
        if not isinstance(items, list):
            raise AccessError(502, "CHAT_RESPONSE", "地址可达，但模型列表格式不兼容。")
        return "model_listed" if any(isinstance(r, dict) and r.get("id") == self.model for r in items) else "model_unlisted"


def tool_offers(catalog):
    offers = []
    for tool in catalog:
        if tool["name"] not in TOOL_NAMES:
            continue
        source = tool["inputSchema"]
        schema = {**source, "properties": {k:v for k,v in source["properties"].items() if k not in CHAT_EXCLUDED},
                  "required": [k for k in source.get("required", ()) if k not in CHAT_EXCLUDED]}
        offers.append({"type": "function", "function": {"name": tool["name"],
                       "description": tool["description"], "parameters": schema}})
    if len(offers) != len(TOOL_NAMES):
        raise AccessError(503, "CHAT_MCP", "本地 MCP 尚未提供完整的报告与请求工具。")
    return offers


def mcp(url, token, method, params=None, *, expected_session=None):
    try:
        result = send(message(method, params or {}, client="silicon-life-state-chat"),
                      token, url=url, expected_session=expected_session)
    except (ValueError, OSError, http.client.HTTPException):
        raise AccessError(503, "CHAT_MCP", "本地 MCP 服务未能确认此次操作，请重试原消息。") from None
    if "error" in result:
        raise AccessError(409, "CHAT_MCP", "分身凭据已失效或本地 MCP 暂不可用。请检查分身授权。")
    return result["result"]


@dataclass
class Turn:
    key: str
    text: str
    steps: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    events: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    accepted: dict = field(default_factory=dict)
    rounds: int = 0
    model_id: str = ""
    result: dict = None


@dataclass
class Session:
    id: str
    owner: str
    instance: dict
    grant_id: str
    token: str
    provider: Provider
    tools: list
    connection_key: str = ""
    connection_digest: str = ""
    initial_status: str = ""
    last_used: float = field(default_factory=time.monotonic)
    history: list = field(default_factory=list)
    turns: dict = field(default_factory=dict)
    pending: Turn = None
    lock: object = field(default_factory=threading.Lock)


class Chat:
    def __init__(self, server):
        self.server = server
        self.sessions = {}
        self.lock = threading.RLock()

    def expire(self):
        with self.lock:
            for cid, session in list(self.sessions.items()):
                if not session.lock.locked() and time.monotonic() - session.last_used > TTL:
                    self.forget(cid)

    def forget(self, cid):
        # Caller holds self.lock. Work already transmitted may still be in flight.
        session = self.sessions.pop(cid, None)
        if session:
            session.provider.api_key = ""
            session.history.clear()
            session.turns.clear()
            session.pending = None

    def invalidate(self, owner=None, scope="all", target=None, grant_id=None):
        with self.lock:
            for cid, session in list(self.sessions.items()):
                if ((owner is None or session.owner == digest(owner)) and
                        (grant_id is None or session.grant_id == grant_id) and
                        (scope == "all" or session.instance.get(scope + "_id") == target)):
                    self.forget(cid)

    def dispatch(self, action, body, token, origin):
        if origin != self.server.base_url:
            raise AccessError(403, "CHAT_DASHBOARD_ONLY", "请从已配对的本机仪表盘使用对话。")
        if action == "connect":
            return self.connect(body, token)
        if action not in ("message", "close"):
            raise AccessError(404, "CHAT_ROUTE", "对话入口不存在。")
        cid = text_field(body, "chat_id")
        if action == "close":
            check_fields(body, {"chat_id","idempotency_key"})
            # Serialize close with tool commits. A provider call in progress can
            # finish, but its result will then fail the active-session check.
            with self.server.mutations, self.lock:
                session = self.sessions.get(cid)
                if session and session.owner != digest(token):
                    raise AccessError(404, "CHAT_EXPIRED", "会话不存在。")
                self.forget(cid)
                return {"closed": True}
        with self.lock:
            session = self.sessions.get(cid)
            if not session or session.owner != digest(token):
                raise AccessError(404, "CHAT_EXPIRED", "会话已关闭或空闲过期，请重新连接。")
            session.last_used = time.monotonic()
        check_fields(body, {"chat_id", "text", "idempotency_key"})
        if not session.lock.acquire(blocking=False):
            raise AccessError(409, "CHAT_BUSY", "该对话正在处理上一条消息，请稍后重试原消息。")
        try:
            return self.chat_turn(session, body, token)
        finally:
            session.lock.release()

    @staticmethod
    def describe(session):
        return {"chat_id":session.id, "instance_id":session.instance["instance_id"],
                "session_id":session.instance["session_id"], "model":session.provider.model,
                "provider_status":session.initial_status,
                "tools":[t["function"]["name"] for t in session.tools], "idle_timeout_seconds":TTL}

    def prior_connection(self, owner, key, signature):
        if key:
            for session in self.sessions.values():
                if session.owner == owner and session.connection_key == key:
                    if session.connection_digest != signature:
                        raise AccessError(409, "CHAT_CONFLICT", "连接操作键已用于其他参数。")
                    return self.describe(session)
        return None

    def connect(self, body, token):
        check_fields(body, {"instance_id","base_url","model","api_key","allow_remote","idempotency_key"})
        iid = text_field(body, "instance_id")
        model = text_field(body, "model").strip()
        provider = Provider(text_field(body, "base_url", 2048).strip(), model,
                            text_field(body, "api_key", 2048, optional=True), body.get("allow_remote") is True)
        owner = digest(token)
        key = text_field(body, "idempotency_key", 128, optional=True)
        signature = digest(json.dumps(body, sort_keys=True, ensure_ascii=True))
        with self.lock:
            existing = self.prior_connection(owner, key, signature)
            if existing:
                return existing
        status = provider.catalog_status()
        with self.server.mutations:
            self.server.access.check(token, self.server.base_url)
            instance, grant_id, agent = self.server.store.authorize_chat_instance(iid)
            if not instance.get("session_id"):
                raise AccessError(409, "CHAT_NO_SESSION", "此分身当前没有会话，请选择其他分身或创建新分身。")
            offers = tool_offers(mcp(self.server.base_url+"/mcp", agent, "tools/list")["tools"])
            with self.lock:
                self.expire()
                existing = self.prior_connection(owner, key, signature)
                if existing:
                    return existing
                if len(self.sessions) >= 32:
                    raise AccessError(409, "CHAT_LIMIT", "已打开的对话过多，请先断开空闲对话。")
                cid = secrets.token_urlsafe(24)
                session = Session(cid, owner, instance, grant_id, agent, provider, offers, key, signature, status)
                self.sessions[cid] = session
                return self.describe(session)

    def require_active(self, session, owner):
        self.server.access.check(owner, self.server.base_url)
        with self.lock:
            if self.sessions.get(session.id) is not session:
                raise AccessError(409, "CHAT_EXPIRED", "会话已关闭。")
        try:
            self.server.store.authenticate_agent(session.token)
        except Exception as exc:
            if getattr(exc, "status", None) == 401:
                raise AccessError(409, "CHAT_REVOKED", "分身授权已撤销，请重新连接。") from None
            raise

    def chat_turn(self, session, body, owner):
        text = text_field(body, "text", 16000)
        key = text_field(body, "idempotency_key", 128)
        if len(key) < 8:
            raise AccessError(400, "CHAT_INPUT", "消息操作键太短。")
        self.require_active(session, owner)
        self.check_secret(session, text, owner)
        turn = session.turns.get(key)
        if turn and turn.text != text:
            raise AccessError(409, "CHAT_CONFLICT", "此操作键已用于另一条消息。")
        if turn and turn.result:
            return turn.result
        if session.pending and session.pending.key != key:
            raise AccessError(409, "CHAT_PENDING", "上一条消息尚未完成，请重试原消息或断开后重新连接。")
        if not turn:
            if len(session.turns) >= MAX_TURNS:
                raise AccessError(409, "CHAT_LIMIT", "本次对话已达 50 轮，请开始新对话。")
            if sum(len(json.dumps(m, ensure_ascii=False)) for m in session.history) > 160000:
                raise AccessError(409, "CHAT_LIMIT", "对话上下文已满，请重新连接以开始新对话。")
            turn = Turn(key, text, steps=[{"role":"user","content":text}])
            session.turns[key] = turn
            session.pending = turn
        while True:
            self.require_active(session, owner)
            while turn.pending:
                with self.server.mutations:
                    self.require_active(session, owner)
                    self.run_tool(session, turn, turn.pending[0])
                turn.pending.pop(0)
            if turn.rounds >= MAX_ROUNDS:
                # The model returned tool calls without a final answer. Return
                # the actual receipts; no synthetic assistant text enters history.
                return self.finish(session, turn, "", "tool_limit")
            payload = {"model":session.provider.model,
                       "messages":[{"role":"system","content":SYSTEM}, *session.history, *turn.steps],
                       "tools":session.tools, "tool_choice":"auto", "stream":False}
            data = session.provider.request("/chat/completions", payload)
            self.require_active(session, owner)
            upstream_model = data.get("model")
            turn.model_id = (upstream_model if isinstance(upstream_model,str) and 0 < len(upstream_model) <= 256
                             else session.provider.model)
            answer, calls = self.read_answer(session, data)
            turn.rounds += 1
            turn.steps.append(answer)
            if calls:
                turn.pending = list(calls)
                continue
            return self.finish(session, turn, answer["content"], "answered")

    @staticmethod
    def finish(session, turn, reply, status):
        turn.result = {"reply":reply, "status":status, "tool_events":list(turn.events),
                       "tool_errors":list(turn.errors), "model":turn.model_id}
        session.history.extend(turn.steps)
        session.pending = None
        session.last_used = time.monotonic()
        return turn.result

    @staticmethod
    def check_secret(session, value, owner=None):
        secrets_to_guard = [s for s in (session.provider.api_key, session.token, owner) if s]
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str) and any(s in item for s in secrets_to_guard):
                raise AccessError(400, "CHAT_SECRET", "内容含有此会话的访问凭据，已停止处理。请更换密钥或调整消息。")
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)

    def read_answer(self, session, data):
        try:
            choice = data["choices"][0]
            raw = choice["message"]
            if raw.get("role") != "assistant":
                raise ValueError()
            text = raw.get("content") or raw.get("refusal") or ""
            calls = raw.get("tool_calls") or []
            if not isinstance(text,str) or len(text)>64000 or not isinstance(calls,list) or len(calls)>6:
                raise ValueError()
            if not calls and not text.strip():
                raise ValueError()
            if choice.get("finish_reason") in ("length", "content_filter"):
                raise AccessError(502, "CHAT_INCOMPLETE", "模型服务提前结束了回复。请检查上下文和服务限制后重试。")
            if calls and choice.get("finish_reason") not in (None, "tool_calls", "stop"):
                raise ValueError()
            seen = set()
            clean = []
            for call in calls:
                fid, fn = call["id"], call["function"]
                if (call.get("type") != "function" or not isinstance(fid,str) or not 0<len(fid)<=256 or fid in seen
                        or not isinstance(fn["name"],str) or len(fn["name"])>128
                        or not isinstance(fn["arguments"],str) or len(fn["arguments"])>24000):
                    raise ValueError()
                seen.add(fid)
                clean.append({"type":"function","id":fid,"function":{"name":fn["name"],"arguments":fn["arguments"]}})
            answer = {"role":"assistant","content":text or None}
            if clean:
                answer["tool_calls"] = clean
            self.check_secret(session, answer)
            return answer, clean
        except (KeyError, ValueError, IndexError, TypeError, AttributeError, RecursionError):
            raise AccessError(502, "CHAT_RESPONSE", "模型未返回可用的助手回复或完整的工具调用。请检查模型兼容性。") from None

    def run_tool(self, session, turn, call):
        name = call["function"]["name"]
        if name in TOOL_NAMES:
            receipt = self.call_allowed_tool(session, turn, call, name)
        else:
            receipt = {"ok":False, "code":"TOOL_NOT_ALLOWED", "error":"Use only offered functions, or reply normally."}
        if receipt["ok"] and not receipt.get("already_recorded"):
            turn.events.append(receipt.copy())
        if not receipt["ok"]:
            turn.errors.append({"tool":name if name in TOOL_NAMES else "unsupported", "code":receipt["code"]})
        turn.steps.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(receipt,ensure_ascii=False)})

    def call_allowed_tool(self, session, turn, call, name):
        try:
            args = json.loads(call["function"]["arguments"])
            if not isinstance(args, dict):
                raise ValueError()
            # Reject non-finite numbers and unpaired surrogates before transport.
            json.dumps(args, ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, UnicodeError, RecursionError):
            return {"ok":False,"code":"INVALID_ARGUMENTS","error":ARG_HINT[name]}
        if CHAT_EXCLUDED.intersection(args):
            return {"ok":False,"code":"UNAVAILABLE_FIELD","error":ARG_HINT[name]}
        operation = json.dumps([name, args], ensure_ascii=True, sort_keys=True, separators=(",",":"))
        if operation in turn.accepted:
            return {**turn.accepted[operation],"already_recorded":True}
        key = hashlib.sha256(json.dumps([session.id,turn.key,turn.rounds,call["id"]]).encode()).hexdigest()
        args.update(idempotency_key="chat-"+key, model_version=turn.model_id,
                    adapter_version="silicon-life-state-chat/1.0.2")
        self.check_secret(session, args)
        res = mcp(self.server.base_url+"/mcp", session.token, "tools/call", {"name":name,"arguments":args},
                  expected_session=session.instance["session_id"])
        if res.get("isError"):
            public = json.loads(res["content"][0]["text"]).get("code")
            if public == "SESSION_CHANGED":
                raise AccessError(409, "CHAT_SESSION_CHANGED", "分身已开始其他会话。请结束当前对话后重新连接。")
            codes = {"INVALID_INPUT", "MISSING_FIELD", "UNKNOWN_FIELD", "EMPTY_REPORT", "FORBIDDEN",
                     "NO_SESSION", "CONFLICT", "IDEMPOTENCY_CONFLICT", "INPUT_TOO_LARGE"}
            return {"ok":False,"code":public if public in codes else "MCP_REJECTED", "error":ARG_HINT[name]}
        event = res["structuredContent"]
        receipt = {"ok":True,"event_id":event["event_id"],"source":event["source"],
                   "type":event["type"],"created_at":event["created_at"]}
        turn.accepted[operation] = receipt
        return receipt
