"""Long-retention search / LLM query analytics for product analysis."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings

MAX_QUERY_LEN = 2000
_lock = threading.Lock()
_initialized = False


def _db_path() -> Path:
    p = settings.analytics_db_path
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _hash(value: str) -> str:
    salt = (settings.ip_hash_salt or "cuagent").encode("utf-8")
    return hashlib.sha256(salt + (value or "").encode("utf-8")).hexdigest()[:32]


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_analytics_db() -> None:
    global _initialized
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    user_id INTEGER,
                    email_hash TEXT,
                    role TEXT,
                    module TEXT NOT NULL,
                    action TEXT NOT NULL,
                    query_text TEXT,
                    ip_hash TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_se_ts ON search_events(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_se_module ON search_events(module, ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_se_user ON search_events(user_id, ts)")
            conn.commit()
            _purge_old(conn)
            _initialized = True
        finally:
            conn.close()


def _purge_old(conn: sqlite3.Connection) -> None:
    days = int(settings.analytics_retention_days or 90)
    if days <= 0:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM search_events WHERE ts < ?", (cutoff,))
    conn.commit()


def log_search_event(
    *,
    module: str,
    action: str,
    query_text: str = "",
    user: Optional[dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> None:
    if not _initialized:
        try:
            init_analytics_db()
        except Exception:
            return
    q = (query_text or "").strip()[:MAX_QUERY_LEN]
    uid = None
    email_h = None
    role = None
    if user and user.get("id"):
        uid = int(user["id"])
        email_h = _hash(str(user.get("email") or ""))
        role = (user.get("role") or "")[:64]
    ip_h = _hash(ip or "") if ip else None
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with _lock:
            conn = _conn()
            try:
                conn.execute(
                    """
                    INSERT INTO search_events
                    (ts, user_id, email_hash, role, module, action, query_text, ip_hash)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (ts, uid, email_h, role, module, action, q, ip_h),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass
