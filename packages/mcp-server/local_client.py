"""A client for the bundled JSON-only loopback MCP endpoint. No proxy or redirects."""
import base64
import http.client
import json
import os
import uuid
from urllib.parse import urlsplit

from mcp_wire import PREFIX, VERSION, error

DEFAULT_URL = "http://127.0.0.1:47831/mcp"

def meta(client="silicon-life-state-client"):
    return {PREFIX+"protocolVersion":VERSION,PREFIX+"clientCapabilities":{},PREFIX+"clientInfo":{"name":client,"version":"1.0.1"}}

def message(method, params=None, client="silicon-life-state-client"):
    return {"jsonrpc":"2.0","id":str(uuid.uuid4()),"method":method,"params":{"_meta":meta(client),**(params or {})}}

def as_header(name):
    if name.isascii() and name.isprintable() and name==name.strip() and not (name.startswith("=?base64?") and name.endswith("?=")):
        return name
    return "=?base64?" + base64.b64encode(name.encode("utf-8")).decode("ascii") + "?="

def connection(url=None):
    u = urlsplit(url if url is not None else os.environ.get("SILICON_MCP_URL", DEFAULT_URL))
    if (u.scheme != "http" or u.hostname != "127.0.0.1" or u.path != "/mcp" or
            u.username is not None or u.password is not None or u.query or u.fragment):
        raise ValueError("SILICON_MCP_URL must be http://127.0.0.1:PORT/mcp")
    return http.client.HTTPConnection("127.0.0.1",u.port or 80,timeout=15)

def send(msg, token=None, *, url=None, expected_session=None):
    token = token or os.environ.get("SILICON_AGENT_TOKEN","")
    if not token:
        raise ValueError("Set SILICON_AGENT_TOKEN to this instance's agent credential")
    params = msg.get("params", {})
    method = msg["method"]
    h = {"Authorization":"Bearer "+token,"Content-Type":"application/json",
         "Accept":"application/json, text/event-stream","Mcp-Method":method,
         "MCP-Protocol-Version":params.get("_meta",{}).get(PREFIX+"protocolVersion",VERSION)}
    if expected_session:
        h["SLS-Expected-Session"] = expected_session
    if method in ("tools/call","resources/read","prompts/get"):
        name = params.get("uri" if method=="resources/read" else "name")
        if isinstance(name,str):
            h["Mcp-Name"] = as_header(name)
    conn = connection(url)
    try:
        conn.request("POST","/mcp",json.dumps(msg,ensure_ascii=True,allow_nan=False).encode("utf-8"),h)
        response = conn.getresponse()
        if response.status in (401,403):
            return error(msg.get("id"),-32603,"Instance authorization failed; check the local agent credential")
        if response.status == 429:
            return error(msg.get("id"),-32603,"Rate limit reached; retry the same operation key later")
        doc = json.loads(response.read())
        if not isinstance(doc,dict) or doc.get("jsonrpc")!="2.0" or doc.get("id") != msg.get("id"):
            raise ValueError("Local service returned a non-MCP reply")
        return doc
    finally:
        conn.close()
