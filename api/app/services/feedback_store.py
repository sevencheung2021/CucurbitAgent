"""Persist user feedback / issue reports to a local SQLite DB."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.config import settings


def _db_path():
    path = settings.feedback_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            email TEXT NOT NULL,
            description TEXT NOT NULL,
            user_agent TEXT,
            ip_hash TEXT
        )
        """
    )
    conn.commit()


def save_feedback(
    *,
    email: str,
    description: str,
    user_agent: str = "",
    ip_hash: str = "",
) -> int:
    conn = sqlite3.connect(_db_path(), timeout=10)
    try:
        _ensure_schema(conn)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = conn.execute(
            """
            INSERT INTO feedback (created_at, email, description, user_agent, ip_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created, email, description, user_agent or None, ip_hash or None),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()
