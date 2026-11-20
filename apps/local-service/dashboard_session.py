"""A dashboard credential requires both its HttpOnly cookie and its origin-bound header.

Loopback cookies are shared across ports. A cookie alone must never authenticate a
request, including one from another service listening on the same loopback host.
"""
import re

from access import AccessError

COOKIE_AGE = 400 * 86400
PREFIX = "sls_owner_"


def cookie_name(port):
    return f"sls_dashboard_{port}"


def cookie_header(port, part, max_age=COOKIE_AGE):
    return (f"{cookie_name(port)}={part}; Path=/api/; Max-Age={max_age}; "
            "HttpOnly; Secure; SameSite=Strict")


def browser_reply(handler, token):
    secret = token.removeprefix(PREFIX)
    # Each independent share retains at least 126 bits of fresh randomness.
    split = len(secret) // 2
    handler.reply(200, {"binding": secret[:split], "role": "owner"},
                  headers={"Set-Cookie": cookie_header(handler.server.server_port, secret[split:])})


def browser_token(handler, origin):
    if origin != handler.server.base_url:
        raise AccessError(403, "DASHBOARD_REQUIRED", "请从本机仪表盘连接。")
    if handler.command == "POST" and handler.header("Origin") != origin:
        raise AccessError(403, "DASHBOARD_ORIGIN_REQUIRED", "仪表盘请求来源无效。")
    binding = handler.header("X-SLS-Dashboard")
    name = cookie_name(handler.server.server_port) + "="
    pieces = [v.strip()[len(name):] for v in handler.header("Cookie").split(";") if v.strip().startswith(name)]
    if len(pieces) != 1 or not re.fullmatch(r"[\w-]{21}", binding, re.ASCII) or not re.fullmatch(r"[\w-]{22}", pieces[0], re.ASCII):
        raise AccessError(401, "OWNER_REQUIRED", "此浏览器需要重新连接本机仪表盘。")
    return PREFIX + binding + pieces[0]
