-- Teleblock SQLite Schema
-- Run: sqlite3 $DB_PATH < db/schema.sql

CREATE TABLE IF NOT EXISTS calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          DATETIME NOT NULL DEFAULT (datetime('now')),
    cid         TEXT NOT NULL,          -- full caller ID number
    result      TEXT NOT NULL           -- PASS | FAIL | TIMEOUT | BLOCKED
                CHECK(result IN ('PASS', 'FAIL', 'TIMEOUT', 'BLOCKED')),
    dtmf_count  INTEGER NOT NULL DEFAULT 0,
    duration_s  INTEGER,               -- call duration in seconds (NULL if blocked before connect)
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS idx_calls_cid ON calls(cid);

-- Trusted callers: numbers that have already passed the challenge at least once.
-- These callers skip the challenge prompt on future calls.
CREATE TABLE IF NOT EXISTS trusted_callers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cid             TEXT NOT NULL UNIQUE,   -- full caller ID number
    first_passed_at DATETIME NOT NULL DEFAULT (datetime('now')),
    call_count      INTEGER NOT NULL DEFAULT 1,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_trusted_cid ON trusted_callers(cid);

-- Auto-purge view (reference only; use scripts/migrate.py to enforce retention)
-- DELETE FROM calls WHERE ts < datetime('now', '-90 days');
