CREATE TABLE subjects (
    subject_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK(level IN (1,2,3))
);
CREATE TABLE instances (
    instance_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL REFERENCES instances ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE INDEX sessions_current ON sessions(instance_id);
CREATE TABLE grants (
    grant_id TEXT PRIMARY KEY,
    digest TEXT UNIQUE NOT NULL,
    subject_id TEXT REFERENCES subjects ON DELETE CASCADE,
    instance_id TEXT REFERENCES instances ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX single_instance_grant ON grants(instance_id) WHERE instance_id IS NOT NULL;
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    subject_id TEXT NOT NULL REFERENCES subjects ON DELETE CASCADE,
    instance_id TEXT NOT NULL REFERENCES instances ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    related TEXT NOT NULL,
    model_version TEXT,
    adapter_version TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    version INTEGER NOT NULL
);
CREATE INDEX events_scope ON events(subject_id,instance_id,seq);
CREATE INDEX events_chain ON events(session_id,seq);
CREATE TABLE receipts (
    actor TEXT NOT NULL,
    key TEXT NOT NULL,
    action TEXT NOT NULL,
    digest TEXT NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY(actor,key)
);
PRAGMA user_version=1;
