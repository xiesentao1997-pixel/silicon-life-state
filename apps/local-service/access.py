"""Browser pairing and owner permissions; independent of the event database."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone

PAIR_TTL = 600
SESSION_TTL = 30 * 24 * 3600


class AccessError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


def timing(expires, now):
    return {"expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
            "server_time": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "expires_in": max(0, expires - now)}


def prune_codes(db, now):
    # Retain only hashes briefly after expiry to explain slow first installations.
    db.execute("DELETE FROM codes WHERE expires < ?", (now - 86400,))
    db.execute("DELETE FROM finished_codes WHERE expires < ?", (now - 86400,))


def code_record(db, code_hash):
    return db.execute("""SELECT target,expires,'active' FROM codes WHERE hash=?
                         UNION ALL SELECT target,expires,state FROM finished_codes WHERE hash=? LIMIT 1""",
                      (code_hash, code_hash)).fetchone()


def finish_code(db, code_hash, target, state):
    # Keep used codes out of the v1.0 live table. This also preserves one-time
    # use if the owner later starts the original 1.0.0 application.
    db.execute("""INSERT OR REPLACE INTO finished_codes(hash,target,expires,state)
                  SELECT hash,target,expires,? FROM codes WHERE hash=? AND target=?""",
               (state,code_hash,target))
    db.execute("DELETE FROM codes WHERE hash=? AND target=?", (code_hash,target))


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
                CREATE TABLE IF NOT EXISTS finished_codes (
                    hash TEXT PRIMARY KEY, target TEXT NOT NULL, expires INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('used','replaced')));
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
                prune_codes(db, now)
                db.execute("DELETE FROM clients WHERE expires <= ?", (now,))
                db.execute("DELETE FROM operations WHERE client NOT IN (SELECT hash FROM clients)")
                db.execute("INSERT INTO codes(hash,target,expires) VALUES (?,?,?)", (digest(code), target, now + PAIR_TTL))
        return {"code": code, "target": target, **timing(now + PAIR_TTL, now)}

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

    def paired_code(self, token, key, target, replaces=None):
        if target not in ("dashboard", "extension"):
            raise AccessError(400, "INVALID_PAIR_TARGET", "选择 dashboard 或 extension。")
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                if replaces is not None and (not isinstance(replaces, str) or not 1 <= len(replaces) <= 128):
                    raise AccessError(400, "INVALID_CODE", "待替换配对码无效。")
                previous_hash = digest(replaces) if replaces else None
                intent = target if previous_hash is None else target + ":" + previous_hash
                first = self.record_intent(db, token, key, "pair", intent)
                # Deterministic solely for this authenticated issuer and operation.
                # Only the hash reaches disk. Replays cannot reactivate a consumed code.
                code = hmac.new(token.encode(), ("pair:" + target + ":" + key).encode(), hashlib.sha256).hexdigest()
                code_hash = digest(code)
                now = int(time.time())
                if first:
                    prune_codes(db, now)
                    if previous_hash:
                        finish_code(db, previous_hash, target, "replaced")
                    db.execute("INSERT INTO codes(hash,target,expires) VALUES (?,?,?)", (code_hash, target, now + PAIR_TTL))
                row = db.execute("SELECT expires FROM codes WHERE hash=? AND expires>?", (code_hash, now)).fetchone()
                if not row:
                    raise AccessError(409, "PAIR_COMPLETE_OR_EXPIRED", "该次配对码已使用或过期。")
        return {"code": code, "target": target, **timing(row[0], now)}

    def code_status(self, code):
        if not isinstance(code, str) or not 1 <= len(code) <= 128:
            raise AccessError(400, "INVALID_CODE", "请输入完整配对码。")
        now = int(time.time())
        with self.connect() as db:
            row = code_record(db, digest(code))
        if not row:
            return {"state": "unavailable", "expires_in": 0}
        state = "expired" if row[2] == "active" and row[1] <= now else row[2]
        return {"state": state, "target": row[0], **timing(row[1], now)}

    def exchange(self, code, origin):
        if not isinstance(code, str) or len(code) > 128:
            raise AccessError(400, "INVALID_CODE", "请输入有效配对码。")
        target = "extension" if origin.startswith("chrome-extension://") else "dashboard"
        token = "sls_owner_" + secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                code_hash = digest(code)
                row = code_record(db, code_hash)
                if not row:
                    raise AccessError(403, "INVALID_PAIR_CODE", "配对码无效。请核对完整内容，或重新生成配对码。")
                desired = "插件" if target == "extension" else "仪表盘"
                if row[0] != target:
                    raise AccessError(403, "PAIR_WRONG_TARGET", "配对入口不匹配。请使用" + desired + "专用配对码。")
                if row[2] == "used":
                    raise AccessError(409, "PAIR_USED", "配对码已使用。请重新生成配对码。")
                if row[2] == "replaced":
                    raise AccessError(409, "PAIR_REPLACED", "此配对码已替换，请使用最近生成的配对码。")
                if row[1] <= now:
                    raise AccessError(410, "PAIR_EXPIRED", "配对码已过期。请在已连接的仪表盘重新生成配对码，或使用正式重新连接启动器。")
                finish_code(db, code_hash, target, "used")
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
                db.execute("DELETE FROM finished_codes")
                clients = db.execute("DELETE FROM clients").rowcount
        return {"revoked_clients": clients, "cancelled_codes": codes}

    def reset(self, current_token):
        """Clear preference and other pairings on explicit data erasure."""
        with self.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM codes")
                db.execute("DELETE FROM finished_codes")
                db.execute("DELETE FROM clients WHERE hash<>?", (digest(current_token),))
                db.execute("DELETE FROM settings")
                db.execute("DELETE FROM operations")
