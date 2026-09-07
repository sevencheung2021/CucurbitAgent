"""SQLite persistence for email OTP auth (users, codes, sessions)."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings

_lock = threading.Lock()

VALID_ROLES = (
    "Researcher / Professor",
    "Associate Researcher / Associate Professor",
    "Assistant Researcher / Assistant Professor",
    "Postdoctoral researcher",
    "Student",
    "Research technician",
    "Other",
)

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
SESSION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _hash(value: str) -> str:
    salt = (settings.ip_hash_salt or "cuagent").encode("utf-8")
    return hashlib.sha256(salt + value.encode("utf-8")).hexdigest()


def email_hash(email: str) -> str:
    return _hash((email or "").strip().lower())[:32]


def ip_hash(ip: str) -> str:
    """Salted SHA-256 of a client IP, for consent evidence. Empty-safe."""
    return _hash(ip or "")[:32]


def _conn() -> sqlite3.Connection:
    path = settings.auth_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_auth_db() -> None:
    with _lock:
        conn = _conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    privacy_consented_at TEXT,
                    privacy_version TEXT,
                    privacy_consented_ip TEXT
                );
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_codes(email, purpose);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                """
            )
            # --- Lightweight migration for pre-existing databases ---
            # SQLite's ADD COLUMN cannot be "IF NOT EXISTS", so probe the
            # existing columns and only add the ones missing. Safe to run on
            # every boot; old user rows simply get NULL for the new columns,
            # which the consent gate treats as "not yet consented".
            existing = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            for col, decl in (
                ("privacy_consented_at", "TEXT"),
                ("privacy_version", "TEXT"),
                ("privacy_consented_ip", "TEXT"),
            ):
                if col not in existing:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
            conn.commit()
        finally:
            conn.close()


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    email_n = (email or "").strip().lower()
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email_n,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(
    email: str,
    role: str,
    privacy_version: str = "",
    privacy_consented_ip: str = "",
) -> dict[str, Any]:
    email_n = (email or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("Invalid role")
    now = _iso(_now())
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO users
                    (email, role, created_at, last_login_at,
                     privacy_consented_at, privacy_version, privacy_consented_ip)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    email_n,
                    role,
                    now,
                    now,
                    # Only stamp consent if a policy version was provided
                    # (it always is from the register path, but keep defensive).
                    now if privacy_version else None,
                    privacy_version or None,
                    privacy_consented_ip or None,
                ),
            )
            conn.commit()
            uid = cur.lastrowid
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return dict(row)
        finally:
            conn.close()


def touch_login(user_id: int) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE users SET last_login_at=? WHERE id=?",
                (_iso(_now()), user_id),
            )
            conn.commit()
        finally:
            conn.close()


def store_otp(email: str, code: str, purpose: str) -> None:
    email_n = (email or "").strip().lower()
    expires = _iso(_now() + timedelta(minutes=OTP_TTL_MINUTES))
    created = _iso(_now())
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "DELETE FROM otp_codes WHERE email=? AND purpose=?",
                (email_n, purpose),
            )
            conn.execute(
                """
                INSERT INTO otp_codes (email, code_hash, purpose, expires_at, attempts, created_at)
                VALUES (?,?,?,?,0,?)
                """,
                (email_n, _hash(code), purpose, expires, created),
            )
            conn.commit()
        finally:
            conn.close()


def verify_otp(email: str, code: str, purpose: str) -> bool:
    email_n = (email or "").strip().lower()
    code = (code or "").strip()
    with _lock:
        conn = _conn()
        try:
            row = conn.execute(
                """
                SELECT id, code_hash, expires_at, attempts FROM otp_codes
                WHERE email=? AND purpose=?
                ORDER BY id DESC LIMIT 1
                """,
                (email_n, purpose),
            ).fetchone()
            if not row:
                return False
            if int(row["attempts"]) >= OTP_MAX_ATTEMPTS:
                return False
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if _now() > expires:
                return False
            ok = secrets.compare_digest(row["code_hash"], _hash(code))
            if not ok:
                conn.execute(
                    "UPDATE otp_codes SET attempts=attempts+1 WHERE id=?",
                    (row["id"],),
                )
                conn.commit()
                return False
            conn.execute("DELETE FROM otp_codes WHERE email=? AND purpose=?", (email_n, purpose))
            conn.commit()
            return True
        finally:
            conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = _iso(_now() + timedelta(days=SESSION_DAYS))
    created = _iso(_now())
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)",
                (_hash(token), user_id, expires, created),
            )
            conn.commit()
        finally:
            conn.close()
    return token


def get_session_user(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    with _lock:
        conn = _conn()
        try:
            row = conn.execute(
                """
                SELECT u.*, s.expires_at AS session_expires
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash=?
                """,
                (_hash(token),),
            ).fetchone()
            if not row:
                return None
            expires = datetime.fromisoformat(row["session_expires"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if _now() > expires:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
                conn.commit()
                return None
            return {
                "id": row["id"],
                "email": row["email"],
                "role": row["role"],
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
                "privacy_consented_at": row["privacy_consented_at"],
                "privacy_version": row["privacy_version"],
            }
        finally:
            conn.close()


def record_consent(
    user_id: int, privacy_version: str, privacy_consented_ip: str = ""
) -> bool:
    """Stamp (or re-stamp) privacy consent for an existing user.

    Called on first registration and whenever a user accepts an updated
    policy via POST /api/auth/consent. Returns True on success.
    """
    if not privacy_version:
        return False
    now = _iso(_now())
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE users
                   SET privacy_consented_at = ?,
                       privacy_version = ?,
                       privacy_consented_ip = ?
                 WHERE id = ?
                """,
                (now, privacy_version, privacy_consented_ip or None, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def revoke_session(token: str) -> None:
    if not token:
        return
    with _lock:
        conn = _conn()
        try:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
            conn.commit()
        finally:
            conn.close()
