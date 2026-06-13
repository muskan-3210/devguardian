"""Shared SQLite layer for all DevGuardian modules.

Schema covers developers, per-developer metrics, DTS history, pull requests,
reviews, security findings, risk assessments and an audit log. SQLite is used
in WAL mode so the FastAPI webhook handler and background jobs can share it.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS developers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT DEFAULT 'engineer',
    joined_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS developer_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    developer_id INTEGER NOT NULL REFERENCES developers(id),
    bug_rate REAL NOT NULL DEFAULT 0,            -- bugs per 10 merged PRs
    revert_rate REAL NOT NULL DEFAULT 0,         -- 0.0 - 1.0
    coverage_delta REAL NOT NULL DEFAULT 0,      -- avg % coverage change
    security_count INTEGER NOT NULL DEFAULT 0,   -- HIGH/CRITICAL findings, 90d
    accept_rate REAL NOT NULL DEFAULT 0,         -- 0.0 - 1.0 first-pass accepts
    window_start TEXT,
    window_end TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_dev ON developer_metrics(developer_id, created_at);

CREATE TABLE IF NOT EXISTS trust_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    developer_id INTEGER NOT NULL REFERENCES developers(id),
    score INTEGER NOT NULL,
    depth TEXT NOT NULL CHECK (depth IN ('shallow','standard','deep','block')),
    breakdown_json TEXT NOT NULL,                 -- explainable factor contributions
    calculated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trust_dev ON trust_scores(developer_id, calculated_at);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,                             -- GitHub PR number
    repo TEXT,
    title TEXT,
    author_id INTEGER REFERENCES developers(id),
    status TEXT DEFAULT 'open'
        CHECK (status IN ('open','merged','reverted','blocked')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pr_author ON pull_requests(author_id);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER REFERENCES pull_requests(id),
    depth TEXT NOT NULL,
    model TEXT NOT NULL,
    verdict TEXT,                                 -- approve | comment | request_changes | block
    findings_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_pr ON reviews(pr_id);

CREATE TABLE IF NOT EXISTS dna_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    traits_json TEXT NOT NULL DEFAULT '{}',       -- learned conventions summary
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER REFERENCES pull_requests(id),
    developer_id INTEGER REFERENCES developers(id),
    rule_id TEXT,
    severity TEXT,                                -- LOW | MEDIUM | HIGH | CRITICAL
    file TEXT,
    line INTEGER,
    message TEXT,
    explanation TEXT,                             -- plain-English AI explanation + fix
    resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_dev ON security_findings(developer_id, created_at);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER REFERENCES pull_requests(id),
    bug_risk TEXT, security_risk TEXT, maintainability_risk TEXT, deployment_risk TEXT,
    explanation TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


def audit(actor: str, action: str, detail: dict | None = None) -> None:
    with get_db() as db:
        db.execute(
            "INSERT INTO audit_logs (actor, action, detail_json, created_at) VALUES (?,?,?,?)",
            (actor, action, json.dumps(detail or {}), now()),
        )
