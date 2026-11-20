"""Select an instance for each tool call made through an authorized host configuration."""
import json
import os
import re
import secrets
from pathlib import Path

from account_profile import account_binding
from local_client import connection, send
from mcp_wire import VERSION, PREFIX, content, error, success

HANDLE = {
    "type": "string", "pattern": "^slschat_[A-Za-z0-9_-]{43}$",
    "description": "This conversation's private handle from open_conversation; omit when the host supplies a stable thread ID."
}
OPEN = {
    "name": "open_conversation",
    "description": ("When your host has no stable thread ID, call once in a new conversation. "
                    "Keep the returned private handle in this conversation and pass it on each tool call, including after reopening."),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "outputSchema": {"type": "object", "properties": {"conversation_handle": HANDLE}, "required": ["conversation_handle"]},
    "annotations": {"readOnlyHint": True, "openWorldHint": False, "destructiveHint": False},
}


class BindingError(ValueError):
    pass


_PROFILE = os.environ.get("SILICON_CODEX_PROFILE")
_PROCESS_ACCOUNT = account_binding(_PROFILE) if _PROFILE else None


def installation_token():
    filename = os.environ.get("SILICON_INSTALLATION_FILE")
    profile_only=os.environ.get("SILICON_DEDICATED_PROFILE")
    if profile_only and account_binding(profile_only):
        raise BindingError("Codex now has an identifiable login. Enroll this account in the dashboard before using its conversations.")
    if _PROFILE:
        current = account_binding(_PROFILE)
        if not current or current != _PROCESS_ACCOUNT:
            raise BindingError("Codex account changed or signed out. Reload the host and authorize the current account.")
        filename = Path(os.environ['SILICON_ACCOUNT_GRANTS']) / (current + '.token')
    if filename:
        try:
            value = Path(filename).read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as exc:
            raise BindingError("Installation authorization is missing. Reauthorize this host in the local dashboard.") from exc
        if not re.fullmatch(r"slsi_[A-Za-z0-9_.~-]{8,245}", value):
            raise BindingError("Invalid installation authorization file. Reconnect this host from the dashboard.")
        return value
    return os.environ.get("SILICON_INSTALLATION_TOKEN")


def bind(url, token, conversation):
    conn = connection(url)
    try:
        conn.request("POST", "/api/installations/bind", json.dumps({"conversation_id": conversation}),
                     {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        response = conn.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            detail = result.get("error", {})
            raise BindingError(detail.get("message", "Installation is unavailable. Check its authorization."))
        return result["token"]
    finally:
        conn.close()


def dispatch(msg, url):
    token = installation_token()
    if token is None:
        return send(msg, url=url)  # existing single-instance configurations
    method, rid, params = msg["method"], msg["id"], msg.get("params", {})
    if method == "tools/list":
        reply = send(msg, token, url=url)
        if "result" in reply:
            for tool in reply["result"]["tools"]:
                tool["inputSchema"]["properties"]["conversation_handle"] = HANDLE
            reply["result"]["tools"].append(dict(OPEN))
        return reply
    if method != "tools/call" or params.get("_meta", {}).get(PREFIX+"protocolVersion") != VERSION:
        return send(msg, token, url=url)
    args = params.get("arguments", {})
    if not isinstance(args, dict) or not isinstance(params.get("name"), str):
        return error(rid, -32602, "Expected tool name and named arguments")
    if params["name"] == OPEN["name"]:
        if args:
            return error(rid, -32602, "open_conversation takes no arguments")
        # Validate the grant even for this ephemeral operation. A lost response makes no database change.
        ping = send({**msg, "method": "server/discover", "params": {"_meta": params.get("_meta", {})}}, token, url=url)
        if "error" in ping:
            return ping
        return success(rid, content({"conversation_handle": "slschat_"+secrets.token_urlsafe(32)}))

    args = dict(args)
    handle = args.pop("conversation_handle", None)
    metadata = params.get("_meta", {})
    # Only the authorized host supplies metadata. Never derive an identity from the API key,
    # process, display name, tools/call arguments or latest conversation.
    thread = metadata.get("dev.silicon-life-state/conversationId")
    if thread is None and os.environ.get("SILICON_HOST") == "codex":
        thread = metadata.get("threadId")
    if thread is None:
        thread = os.environ.get("SILICON_CONVERSATION_ID")  # a wrapper launching one process per conversation
    if thread is not None:
        if not isinstance(thread, str) or not thread.strip() or len(thread) > 240:
            return error(rid, -32602, "Invalid host conversation ID")
        conversation = "host:"+thread
    elif isinstance(handle, str) and re.fullmatch(HANDLE["pattern"], handle):
        conversation = "fallback:"+handle
    else:
        return success(rid, content({"code": "CONVERSATION_HANDLE_REQUIRED",
                                    "message": "Use the private conversation_handle already in this conversation. In a new conversation, call open_conversation once."}, True))
    instance_token = bind(url, token, conversation)
    return send({**msg, "params": {**params, "arguments": args}}, instance_token, url=url)
