PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    body_json TEXT NOT NULL,

    status TEXT NOT NULL,

    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,

    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    next_attempt_at REAL,

    worker_id TEXT,
    release_id TEXT,

    accepted_at REAL NOT NULL,
    completed_at REAL,

    last_error TEXT,
    final_reason TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    work_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,

    worker_id TEXT,

    started_at REAL NOT NULL,
    finished_at REAL,

    outcome TEXT,
    error TEXT,

    release_id TEXT,

    FOREIGN KEY (work_id)
        REFERENCES work_items(id)
);

CREATE TABLE IF NOT EXISTS dedupe_records (
    work_id TEXT PRIMARY KEY,

    first_seen_at REAL NOT NULL,
    completed_at REAL,

    result_hash TEXT,

    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_id TEXT UNIQUE NOT NULL,
    occurred_at REAL NOT NULL,

    event_type TEXT NOT NULL,

    subject_type TEXT,
    subject_id TEXT,

    work_id TEXT,
    worker_id TEXT,
    release_id TEXT,
    incident_id TEXT,

    severity TEXT NOT NULL,

    decision TEXT,
    reason TEXT,

    before_json TEXT,
    after_json TEXT,

    message TEXT
);

CREATE TABLE IF NOT EXISTS releases (
    release_id TEXT PRIMARY KEY,

    version TEXT NOT NULL,

    status TEXT NOT NULL,

    previous_release_id TEXT,

    created_at REAL NOT NULL,
    activated_at REAL,
    rolled_back_at REAL,

    rollback_reason TEXT,

    FOREIGN KEY (previous_release_id)
        REFERENCES releases(release_id)
);