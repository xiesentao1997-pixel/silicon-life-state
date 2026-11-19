"""Browser pairing and owner permissions; independent of the event database."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PAIR_TTL = 600
SESSION_TTL = 30 * 24 * 3600


class AccessError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Access:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "browser-access.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS codes (
                    hash TEXT PRIMARY KEY, target TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS clients (
                    hash TEXT PRIMARY KEY, origin TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    client TEXT NOT NULL, key_hash TEXT NOT NULL, operation TEXT NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY(client, key_hash));
                CREATE TABLE IF NOT EXISTS settings (
                    name TEXT PRIMARY KEY, value INTEGER NOT NULL);
            """)
        if os.name != "nt":
            self.path.chmod(0o600)

    def connect(self):
        return closing(sqlite3.connect(self.path, timeout=15, isolation_level=None))

    def issue_code(self, target):
        if target not in ("dashboard", "extension"):
            raise AccessError(400, "INVALID_PAIR_TARGET", "选择 dashboard 或 extension。")
        code = secrets.token_urlsafe(24)
        now = int(time.time())
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM codes WHERE expires <= ?", (now,))
                db.execute("DELETE FROM clients WHERE expires <= ?", (now,))
                db.execute("DELETE FROM operations WHERE client NOT IN (SELECT hash FROM clients)")
                db.execute("INSERT INTO codes VALUES (?,?,?)", (digest(code), target, now + PAIR_TTL))
        return {"code": code, "target": target, "expires_in": PAIR_TTL}

    @staticmethod
    def record_intent(db, token, key, operation, value):
        if not isinstance(key, str) or not 8 <= len(key.strip()) <= 128:
            raise AccessError(400, "INVALID_KEY", "idempotency_key 必须为 8 至 128 个字符。")
        actor = digest(token)
        if not db.execute("SELECT 1 FROM clients WHERE hash=? AND expires>?", (actor, int(time.time()))).fetchone():
            raise AccessError(401, "OWNER_REQUIRED", "需要有效的所有者配对。")
        intent = (actor, digest(key))
        earlier = db.execute("SELECT operation,value FROM operations WHERE client=? AND key_hash=?", intent).fetchone()
        if earlier:
            if earlier != (operation, value):
                raise AccessError(409, "IDEMPOTENCY_CONFLICT", "此幂等键已用于其他操作。")
            return False
        db.execute("INSERT INTO operations VALUES (?,?,?,?)", (*intent, operation, value))
        return True

    def paired_code(self, token, key, target):
        if target not in ("dashboard", "extension"):
            raise AccessError(400, "INVALID_PAIR_TARGET", "选择 dashboard 或 extension。")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                first = self.record_intent(db, token, key, "pair", target)
                # Deterministic solely for this authenticated issuer and operation.
                # Only the hash reaches disk. Replays cannot reactivate a consumed code.
                code = hmac.new(token.encode(), ("pair:" + target + ":" + key).encode(), hashlib.sha256).hexdigest()
                code_hash = digest(code)
                now = int(time.time())
                if first:
                    db.execute("DELETE FROM codes WHERE expires<=?", (now,))
                    db.execute("INSERT INTO codes VALUES (?,?,?)", (code_hash, target, now + PAIR_TTL))
                row = db.execute("SELECT expires FROM codes WHERE hash=? AND expires>?", (code_hash, now)).fetchone()
                if not row:
                    raise AccessError(409, "PAIR_COMPLETE_OR_EXPIRED", "该次配对码已使用或过期。")
        return {"code": code, "target": target, "expires_in": row[0] - now}

    def exchange(self, code, origin):
        if not isinstance(code, str) or len(code) > 128:
            raise AccessError(400, "INVALID_CODE", "请输入有效配对码。")
        target = "extension" if origin.startswith("chrome-extension://") else "dashboard"
        token = "sls_owner_" + secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                match = db.execute("DELETE FROM codes WHERE hash=? AND target=? AND expires>?",
                                   (digest(code), target, now)).rowcount
                if not match:
                    raise AccessError(403, "INVALID_PAIR_CODE", "配对码已失效或配对入口不匹配。")
                db.execute("INSERT INTO clients VALUES (?,?,?)", (digest(token), origin, now + SESSION_TTL))
        return {"token": token, "expires_in": SESSION_TTL, "role": "owner"}

    def check(self, token, origin):
        with self.connect() as db:
            row = db.execute("SELECT origin FROM clients WHERE hash=? AND expires>?",
                             (digest(token), int(time.time()))).fetchone()
        if not row:
            raise AccessError(401, "OWNER_REQUIRED", "需要本机所有者配对。")
        if row[0] != origin:
            raise AccessError(403, "ORIGIN_MISMATCH", "该凭据属于其他配对来源。")

    def revoke(self, token):
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM operations WHERE client=?", (digest(token),))
                db.execute("DELETE FROM clients WHERE hash=?", (digest(token),))
        return {"revoked": True}

    def settings(self, enabled=None, *, token=None, key=None):
        with self.connect() as db:
            if enabled is not None:
                if type(enabled) is not bool:
                    raise AccessError(400, "INVALID_SETTING", "observation_enabled 必须为布尔值。")
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    if token is None or self.record_intent(db, token, key, "settings", str(int(enabled))):
                        db.execute("INSERT OR REPLACE INTO settings VALUES ('observation_enabled',?)", (int(enabled),))
            row = db.execute("SELECT value FROM settings WHERE name='observation_enabled'").fetchone()
        return {"observation_enabled": bool(row[0]) if row else True}

    def unpair_all(self):
        """Caller proves possession of the private installation directory via CLI."""
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM operations")
                codes = db.execute("DELETE FROM codes").rowcount
                clients = db.execute("DELETE FROM clients").rowcount
        return {"revoked_clients": clients, "cancelled_codes": codes}

    def reset(self, current_token):
        """Clear preference and other pairings on explicit data erasure."""
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM codes")
                db.execute("DELETE FROM clients WHERE hash<>?", (digest(current_token),))
                db.execute("DELETE FROM settings")
                db.execute("DELETE FROM operations")
