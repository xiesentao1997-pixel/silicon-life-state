ALTER TABLE installations ADD COLUMN account_binding TEXT;
CREATE UNIQUE INDEX installations_bound_account ON installations(account_binding) WHERE account_binding IS NOT NULL;
CREATE TABLE name_history (
    revision INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL REFERENCES subjects ON DELETE CASCADE,
    instance_id TEXT REFERENCES instances ON DELETE CASCADE,
    name TEXT NOT NULL,
    action TEXT NOT NULL,
    source TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX name_history_target ON name_history(subject_id,instance_id,revision);
INSERT INTO name_history(subject_id,name,action,source,actor,created_at)
    SELECT subject_id,name,'create','historical','migration',created_at FROM subjects;
INSERT INTO name_history(subject_id,instance_id,name,action,source,actor,created_at)
    SELECT subject_id,instance_id,name,'create','historical','migration',created_at FROM instances;
PRAGMA user_version=3;
