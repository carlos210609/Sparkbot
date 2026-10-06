from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def db_path() -> Path:
    configured = os.getenv("SPARKBOT_DB_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    return PROJECT_ROOT / "data" / "sparkbot.db"

DB_PATH = db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'ACTIVE',
 kpi TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 goal_id INTEGER,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 priority TEXT NOT NULL DEFAULT 'P2',
 status TEXT NOT NULL DEFAULT 'QUEUED',
 tool TEXT NOT NULL DEFAULT 'internal',
 expected_output TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(goal_id) REFERENCES goals(id)
);
CREATE TABLE IF NOT EXISTS activity_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_type TEXT NOT NULL,
 message TEXT NOT NULL,
 task_id INTEGER,
 metadata TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS browser_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT NOT NULL UNIQUE,
 action TEXT NOT NULL,
 url TEXT NOT NULL DEFAULT '',
 target TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'observed',
 details TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 action TEXT NOT NULL,
 actor TEXT NOT NULL,
 target TEXT NOT NULL DEFAULT '',
 result TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS missions (
 id TEXT PRIMARY KEY,
 request TEXT NOT NULL,
 goal TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'PLANNED',
 confidence REAL NOT NULL DEFAULT 0,
 selected_agents INTEGER NOT NULL DEFAULT 0,
 selected_skills INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mission_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 mission_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 message TEXT NOT NULL,
 metadata TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(mission_id) REFERENCES missions(id)
);
CREATE TABLE IF NOT EXISTS agent_metrics (
 agent_id TEXT PRIMARY KEY,
 runs INTEGER NOT NULL DEFAULT 0,
 successes INTEGER NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0,
 avg_latency_ms REAL NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS memories (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL,
 key TEXT NOT NULL,
 value TEXT NOT NULL,
 importance REAL NOT NULL DEFAULT 0.5,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return int(cur.lastrowid)
