"""Rate limiting + trusted client IP helpers.

LLM chat endpoints enforce:
  * a short sliding-window cap (burst), and
  * a persistent per-IP daily quota (default 20 questions/day).

Client IP resolution only trusts ``X-Forwarded-For`` / ``X-Real-IP`` when the
TCP peer is a loopback proxy (nginx on the same host) or an address listed in
``CUAGENT_TRUSTED_PROXIES``. Direct internet clients cannot spoof XFF to bypass
quotas or admin checks.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request

from app.config import settings


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Consume a slot; False when the window is full."""
        if self.max_requests <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True

    def would_allow(self, key: str) -> bool:
        """Non-consuming check (for pre-validation before burning a slot)."""
        if self.max_requests <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return True
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if not q:
                del self._hits[key]
                return True
            return len(q) < self.max_requests


_llm_minute_limiter = SlidingWindowRateLimiter(
    max_requests=settings.llm_rate_limit_per_minute,
    window_seconds=60.0,
)
_feedback_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=3600.0)
_visit_record_limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=3600.0)
_download_limiter = SlidingWindowRateLimiter(
    max_requests=settings.download_rate_limit_per_hour,
    window_seconds=3600.0,
)
_db_lock = threading.Lock()


def _peer_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    return h in ("127.0.0.1", "::1", "localhost") or h.startswith("127.")


def _trusted_proxy_peers() -> set[str]:
    """Explicit-only trust (CUAGENT_TRUSTED_PROXIES env).

    Loopback is NOT auto-trusted anymore: today's chain is
    client → Next(:3000) → uvicorn, and Next forwards client-supplied
    X-Forwarded-For / X-Real-Ip UNCHANGED (verified: spoofed XFF 1.2.3.4
    recorded as "Australia"), so any auto-trust equals trusting the client.
    Set CUAGENT_TRUSTED_PROXIES=127.0.0.1 ONLY when nginx fronts the stack
    and overwrites X-Real-Ip from $remote_addr.
    """
    raw = (settings.trusted_proxies or "").strip()
    return {p.strip() for p in raw.split(",") if p.strip()}


def client_ip(request: Request) -> str:
    """Best-effort real client IP for rate limits / analytics.

    Forwarded headers are honored ONLY when the TCP peer is a trusted proxy.
    Priority: X-Real-Ip (nginx sets it from $remote_addr, REPLACING any
    client-supplied value — unspoofable), then the RIGHT-MOST X-Forwarded-For
    entry (the one appended by the nearest trusted proxy in append-style
    chains). The left-most entry is client-controlled and was trivially
    spoofed (verified 2026-08-27: XFF 1.2.3.4 via the Next proxy recorded
    "Australia"), so it must never be trusted.
    """
    peer = _peer_ip(request)
    # Explicit env-configured proxies ONLY — no loopback backdoor (the Next
    # proxy runs on loopback and forwards client headers unchanged).
    if peer in _trusted_proxy_peers():
        xri = (request.headers.get("X-Real-Ip") or "").strip()
        if xri:
            return xri
        xff = (request.headers.get("X-Forwarded-For") or "").strip()
        if xff:
            return xff.split(",")[-1].strip() or peer
    return peer


def _ip_hash(ip: str) -> str:
    salt = (settings.ip_hash_salt or "cuagent").encode("utf-8")
    return hashlib.sha256(salt + ip.encode("utf-8")).hexdigest()


def _quota_db() -> sqlite3.Connection:
    path = settings.visit_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_daily_usage (
            ip_hash TEXT NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ip_hash, day)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_user_daily_usage (
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day)
        )
        """
    )
    conn.commit()
    return conn


def check_and_increment_llm_daily(ip: str, *, limit: Optional[int] = None) -> tuple[bool, int, int]:
    """Return (allowed, used_after, daily_limit) for an IP key.

    When daily_limit <= 0, quota is disabled (always allowed, count not stored).
    """
    lim = int(settings.llm_rate_limit_per_day or 0) if limit is None else int(limit)
    if lim <= 0:
        return True, 0, 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = _ip_hash(ip)
    with _db_lock:
        conn = _quota_db()
        try:
            row = conn.execute(
                "SELECT count FROM llm_daily_usage WHERE ip_hash=? AND day=?",
                (key, day),
            ).fetchone()
            used = int(row[0]) if row else 0
            if used >= lim:
                return False, used, lim
            used += 1
            conn.execute(
                """
                INSERT INTO llm_daily_usage (ip_hash, day, count) VALUES (?, ?, ?)
                ON CONFLICT(ip_hash, day) DO UPDATE SET count=excluded.count
                """,
                (key, day, used),
            )
            conn.commit()
            return True, used, lim
        finally:
            conn.close()


def check_and_increment_user_llm_daily(user_id: int) -> tuple[bool, int, int]:
    """Per-account daily LLM quota."""
    lim = int(settings.llm_rate_limit_per_user_day or 0)
    if lim <= 0 or not user_id:
        return True, 0, 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _db_lock:
        conn = _quota_db()
        try:
            row = conn.execute(
                "SELECT count FROM llm_user_daily_usage WHERE user_id=? AND day=?",
                (user_id, day),
            ).fetchone()
            used = int(row[0]) if row else 0
            if used >= lim:
                return False, used, lim
            used += 1
            conn.execute(
                """
                INSERT INTO llm_user_daily_usage (user_id, day, count) VALUES (?, ?, ?)
                ON CONFLICT(user_id, day) DO UPDATE SET count=excluded.count
                """,
                (user_id, day, used),
            )
            conn.commit()
            return True, used, lim
        finally:
            conn.close()


def enforce_llm_rate_limit(request: Request, user: Optional[dict] = None) -> None:
    """Raise 429 if burst / per-user / per-IP daily LLM budgets are exceeded.

    Call after ``require_llm_user`` so ``user`` is available when auth is on.
    """
    ip = client_ip(request)
    if not _llm_minute_limiter.allow(f"min:{ip}"):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many requests ({settings.llm_rate_limit_per_minute}/minute). "
                "Please wait a moment and try again."
            ),
        )

    if user and user.get("id"):
        ok_u, used_u, lim_u = check_and_increment_user_llm_daily(int(user["id"]))
        if not ok_u:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Daily limit reached ({lim_u} AI questions per account per day). "
                    f"Already used {used_u}. Try again tomorrow (UTC)."
                ),
            )
        ip_lim = int(settings.llm_rate_limit_per_ip_day or 0)
        if ip_lim > 0:
            ok_ip, used_ip, lim_ip = check_and_increment_llm_daily(ip, limit=ip_lim)
            if not ok_ip:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Daily limit reached ({lim_ip} AI questions per IP per day). "
                        f"Already used {used_ip}. Try again tomorrow (UTC)."
                    ),
                )
        return

    # Anonymous path (only when auth-for-LLM is disabled)
    ok, used, limit = check_and_increment_llm_daily(ip)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily limit reached ({limit} AI questions per IP per day). "
                f"Already used {used}. Try again tomorrow (UTC)."
            ),
        )


def enforce_feedback_rate_limit(request: Request) -> None:
    ip = client_ip(request)
    if not _feedback_limiter.allow(f"fb:{ip}"):
        raise HTTPException(
            status_code=429,
            detail="Too many feedback submissions from this IP. Please try later.",
        )


def allow_visit_record(request: Request) -> bool:
    """Return False if this IP already recorded a visit too recently."""
    ip = client_ip(request)
    return _visit_record_limiter.allow(f"visit:{ip}")


def enforce_download_rate_limit(request: Request) -> None:
    """Throttle genome / PDB file downloads per IP."""
    if int(settings.download_rate_limit_per_hour or 0) <= 0:
        return
    ip = client_ip(request)
    if not _download_limiter.allow(f"dl:{ip}"):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many downloads from this IP "
                f"({settings.download_rate_limit_per_hour}/hour). Please try later."
            ),
        )


def require_admin(request: Request) -> None:
    """Protect admin-only endpoints (e.g. literature reload).

    - If ``CUAGENT_ADMIN_TOKEN`` is set: require matching ``X-Admin-Token``
      (or ``Authorization: Bearer <token>``).
    - If unset: only allow loopback **TCP peers** (never trust client XFF).
    """
    token = (settings.admin_api_token or "").strip()
    provided = (request.headers.get("X-Admin-Token") or "").strip()
    if not provided:
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()

    if token:
        if not provided or provided != token:
            raise HTTPException(status_code=401, detail="Invalid or missing admin token")
        return

    # No token configured: restrict to local machine only (connection peer).
    peer = _peer_ip(request)
    if not is_loopback(peer):
        raise HTTPException(
            status_code=403,
            detail="Admin endpoint requires CUAGENT_ADMIN_TOKEN or a loopback client",
        )
