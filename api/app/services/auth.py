"""Auth helpers: OTP request/verify, session extraction, require_user."""

from __future__ import annotations

import re
import secrets
from typing import Any, Optional

from fastapi import HTTPException, Request

from app.config import settings
from app.services import auth_store
from app.services.mailer import send_otp_email
from app.services.rate_limit import client_ip

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def extract_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    # Also accept X-Auth-Token for convenience
    tok = (request.headers.get("X-Auth-Token") or "").strip()
    return tok or None


def get_optional_user(request: Request) -> Optional[dict[str, Any]]:
    token = extract_bearer_token(request)
    if not token:
        return None
    return auth_store.get_session_user(token)


def require_user(request: Request) -> dict[str, Any]:
    user = get_optional_user(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Sign in required. Please verify your email to use AI features.",
        )
    return user


def require_llm_user(request: Request) -> dict[str, Any]:
    """Require login for LLM when CUAGENT_REQUIRE_AUTH_FOR_LLM is enabled."""
    raw = (settings.require_auth_for_llm or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        user = get_optional_user(request)
        return user or {"id": 0, "email": "", "role": ""}
    return require_user(request)


def request_otp(email: str, purpose: str) -> dict[str, Any]:
    email_n = _normalize_email(email)
    if not _EMAIL_RE.match(email_n):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if purpose not in ("register", "login"):
        raise HTTPException(status_code=400, detail="Invalid purpose.")

    existing = auth_store.get_user_by_email(email_n)
    if purpose == "register" and existing:
        raise HTTPException(
            status_code=400,
            detail="This email is already registered. Please sign in instead.",
        )
    if purpose == "login" and not existing:
        raise HTTPException(
            status_code=400,
            detail="No account found for this email. Please register first.",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    auth_store.store_otp(email_n, code, purpose)
    send_otp_email(email_n, code, purpose)
    return {
        "ok": True,
        "message": "Verification code sent. Check your email (or server logs if SMTP is not configured).",
        "expires_in_seconds": auth_store.OTP_TTL_MINUTES * 60,
    }


def verify_otp_and_login(
    email: str,
    code: str,
    purpose: str,
    role: Optional[str] = None,
    agreed: bool = False,
    request: Optional[Request] = None,
) -> dict[str, Any]:
    email_n = _normalize_email(email)
    if not _EMAIL_RE.match(email_n):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if purpose not in ("register", "login"):
        raise HTTPException(status_code=400, detail="Invalid purpose.")

    # Validate register role BEFORE consuming OTP (otherwise a rejected role burns the code).
    role_s = (role or "").strip()
    if purpose == "register":
        if role_s not in auth_store.VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail="Please select a valid role when registering.",
            )
        if auth_store.get_user_by_email(email_n):
            raise HTTPException(status_code=400, detail="This email is already registered.")
        # --- Privacy consent gate (registration only) ---
        # Required by PIPL/CSL: collecting personal data (email, role, IP, AI
        # query logs) demands affirmative, recorded consent at sign-up.
        if not agreed:
            raise HTTPException(
                status_code=400,
                detail="Please agree to the Privacy Policy and Terms of Use to register.",
            )

    if not auth_store.verify_otp(email_n, code, purpose):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    user = auth_store.get_user_by_email(email_n)
    if purpose == "register":
        consent_ip = auth_store.ip_hash(client_ip(request)) if request else ""
        user = auth_store.create_user(
            email_n,
            role_s,
            privacy_version=settings.privacy_version,
            privacy_consented_ip=consent_ip,
        )
    else:
        if not user:
            raise HTTPException(status_code=400, detail="No account found for this email.")
        auth_store.touch_login(user["id"])

    token = auth_store.create_session(user["id"])
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "privacy_consented_at": user.get("privacy_consented_at"),
            "privacy_version": user.get("privacy_version"),
        },
        "expires_in_days": auth_store.SESSION_DAYS,
    }
