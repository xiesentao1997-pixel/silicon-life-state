CREATE TABLE installations (
    installation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects ON DELETE CASCADE,
    host TEXT NOT NULL,
    created_at TEXT NOT NULL,
    generation TEXT NOT NULL,
    digest TEXT UNIQUE,
    seed_instance_id TEXT UNIQUE REFERENCES instances ON DELETE SET NULL,
    managed INTEGER NOT NULL DEFAULT 0 CHECK(managed IN (0,1))
);
CREATE TABLE conversation_bindings (
    installation_id TEXT NOT NULL REFERENCES installations ON DELETE CASCADE,
    conversation_hash TEXT NOT NULL,
    instance_id TEXT NOT NULL UNIQUE REFERENCES instances ON DELETE CASCADE,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    PRIMARY KEY (installation_id, conversation_hash)
);
PRAGMA user_version=2;
