"""Structured user-action logging for the CucurbitAgent platform.

Records every meaningful user interaction (gene/protein/expression/agent
queries, tool traces, errors, latency) into the same SQLite database used
by ``visit_analytics``. Rows older than ``RETENTION_DAYS`` are purged on
startup and once per day by a background thread started from ``main.py``.

Design notes
------------
* Writes use a fresh short-lived connection per call. With WAL mode enabled
  this does not block readers and is plenty fast for the platform's traffic.
* ``query_text`` is stored verbatim (operator decision, 2026-07-08); truncate
  defensively at ``MAX_QUERY_LEN`` to keep rows bounded.
* ``tool_trace`` is a JSON array of ``{tool, args_summary, status, ms}``
  dicts, only populated for the full agent loop. Fast-path routes leave it
  as ``"[]"``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings

RETENTION_DAYS = 7
MAX_QUERY_LEN = 2000
PURGE_INTERVAL_SECONDS = 24 * 3600

_init_lock = threading.Lock()
_initialized = False


def _db_path() -> Path:
    p = settings.visit_db_path
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            gene_id TEXT,
            species TEXT,
            query_text TEXT,
            status TEXT,
            latency_ms INTEGER,
            tool_trace TEXT,
            ip_hash TEXT,
            session_id TEXT,
            error_msg TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_ts ON user_actions(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_module_ts ON user_actions(module, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_status_ts ON user_actions(status, ts)")
    conn.commit()


def _maybe_init() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        conn = sqlite3.connect(_db_path(), timeout=5)
        try:
            _ensure_schema(conn)
        finally:
            conn.close()
        _initialized = True


def purge_old_actions(days: int = RETENTION_DAYS) -> int:
    """Delete rows older than ``days`` days. Returns number of rows deleted."""
    _maybe_init()
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    # SQLite doesn't compute the cutoff timestamp directly; use strftime math.
    conn = sqlite3.connect(_db_path(), timeout=10)
    try:
        cur = conn.execute(
            "DELETE FROM user_actions "
            "WHERE ts < strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def log_action(
    *,
    module: str,
    action: str,
    gene_id: Optional[str] = None,
    species: Optional[str] = None,
    query_text: Optional[str] = None,
    status: str = "success",
    latency_ms: Optional[int] = None,
    tool_trace: Optional[list[dict[str, Any]]] = None,
    ip: Optional[str] = None,
    session_id: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> None:
    """Insert one user-action row.

    Failure to log must NEVER break the user request, so all exceptions are
    swallowed and only printed to stderr. The request handler is the source
    of truth for the response, not the logger.
    """
    try:
        _maybe_init()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        q = query_text[:MAX_QUERY_LEN] if query_text else None
        trace = json.dumps(tool_trace, ensure_ascii=False) if tool_trace else "[]"
        ip_hash = (
            hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else None
        )
        conn = sqlite3.connect(_db_path(), timeout=5)
        try:
            conn.execute(
                """
                INSERT INTO user_actions (
                    ts, module, action, gene_id, species, query_text,
                    status, latency_ms, tool_trace, ip_hash, session_id, error_msg
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (ts, module, action, gene_id, species, q, status, latency_ms,
                 trace, ip_hash, session_id, error_msg),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 - logger must never raise
        import sys
        print(f"[action_logger] failed to log: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Background purge thread
# ---------------------------------------------------------------------------

_purge_stop = threading.Event()
_purge_thread: Optional[threading.Thread] = None


def start_purge_worker() -> None:
    """Start (idempotent) a background thread that purges old rows daily."""
    global _purge_thread
    if _purge_thread and _purge_thread.is_alive():
        return

    def _loop():
        # Run one purge immediately on startup so restarts keep the table tight.
        try:
            purged = purge_old_actions()
            if purged:
                print(f"[action_logger] startup purge: removed {purged} old rows")
        except Exception as e:  # noqa: BLE001
            print(f"[action_logger] startup purge failed: {e}", file=sys.stderr)

        while not _purge_stop.wait(PURGE_INTERVAL_SECONDS):
            try:
                purged = purge_old_actions()
                if purged:
                    print(f"[action_logger] daily purge: removed {purged} old rows")
            except Exception as e:  # noqa: BLE001
                print(f"[action_logger] daily purge failed: {e}", file=sys.stderr)

    _purge_thread = threading.Thread(
        target=_loop, name="action-logger-purge", daemon=True
    )
    _purge_thread.start()


def stop_purge_worker() -> None:
    _purge_stop.set()


# ---------------------------------------------------------------------------
# Convenience context manager: timed action with auto latency/status
# ---------------------------------------------------------------------------

class ActionTimer:
    """Context manager that records latency and auto-flips status on exception.

    Usage::

        with ActionTimer(module="gene", action="chat",
                         gene_id=gid, query_text=q, ip=ip) as at:
            ... do work ...
            at.tool_trace = [...]   # optional, for agent loop

    On normal exit status defaults to "success"; on exception it becomes
    "error" with error_msg populated, and the exception re-raises.
    """

    def __init__(
        self,
        *,
        module: str,
        action: str,
        gene_id: Optional[str] = None,
        species: Optional[str] = None,
        query_text: Optional[str] = None,
        ip: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = "success",
    ):
        self._kwargs = dict(
            module=module, action=action, gene_id=gene_id, species=species,
            query_text=query_text, ip=ip, session_id=session_id, status=status,
        )
        self.tool_trace: Optional[list[dict[str, Any]]] = None
        self.status: str = status
        self._t0: float = 0.0

    def __enter__(self) -> "ActionTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        if exc is not None:
            self.status = "error"
            self._kwargs["error_msg"] = f"{type(exc).__name__}: {exc}"
        # Callers may set ``timer.status = "not_found"`` etc. before exit;
        # always sync the public attribute into the log kwargs.
        self._kwargs["status"] = self.status
        log_action(
            latency_ms=latency_ms,
            tool_trace=self.tool_trace,
            **self._kwargs,
        )
        # Do not suppress the exception.
        return False
