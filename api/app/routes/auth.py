"""Auth HTTP routes: request OTP, verify, me, logout, consent."""

import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.services import auth_store
from app.services.auth import (
    extract_bearer_token,
    request_otp,
    require_user,
    verify_otp_and_login,
)
from app.services.rate_limit import SlidingWindowRateLimiter, client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])

# OTP send caps: per email (anti email-bombing / spam to one inbox) and per IP
# (anti mass-registration / spraying many inboxes from one source). Hourly window.
# Env-tunable like every other limit in the codebase (CUAGENT_* env vars).
_OTP_EMAIL_HOURLY_LIMIT = int(os.getenv("CUAGENT_OTP_EMAIL_HOURLY", "30"))
_OTP_IP_HOURLY_LIMIT = int(os.getenv("CUAGENT_OTP_IP_HOURLY", "100"))
_OTP_VERIFY_HOURLY_LIMIT = int(os.getenv("CUAGENT_OTP_VERIFY_HOURLY", "60"))
_otp_send_email_limiter = SlidingWindowRateLimiter(
    max_requests=_OTP_EMAIL_HOURLY_LIMIT, window_seconds=3600.0
)
_otp_send_ip_limiter = SlidingWindowRateLimiter(
    max_requests=_OTP_IP_HOURLY_LIMIT, window_seconds=3600.0
)
# /verify guesses: no cap here would allow 30 codes × 5 attempts = 150
# brute-force guesses/hour against one inbox.
_otp_verify_limiter = SlidingWindowRateLimiter(
    max_requests=_OTP_VERIFY_HOURLY_LIMIT, window_seconds=3600.0
)


def _email_limiter_key(email: str) -> str:
    """Canonical limiter key: lowercase + strip plus-address tags so
    victim+1@… / victim+2@… (same inbox) share ONE bucket."""
    e = (email or "").strip().lower()
    if "@" in e:
        local, _, domain = e.rpartition("@")
        local = local.split("+", 1)[0]
        # Gmail treats dots in the local part as ignorable — fold them too.
        if domain in ("gmail.com", "googlemail.com"):
            local = local.replace(".", "")
        e = f"{local}@{domain}"
    return f"otp:email:{e}"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequestCodeBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    purpose: Literal["register", "login"]


class VerifyBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    code: str = Field(..., min_length=4, max_length=12)
    purpose: Literal["register", "login"]
    role: Optional[str] = Field(default=None, max_length=128)
    # Registration only: must be true to create an account. Ignored for login.
    agreed: bool = False


class ConsentBody(BaseModel):
    # Optional explicit version pin; defaults to the server's current version.
    privacy_version: Optional[str] = Field(default=None, max_length=32)


@router.get("/roles")
def list_roles():
    return {"roles": list(auth_store.VALID_ROLES)}


@router.post("/request-code")
def auth_request_code(body: RequestCodeBody, request: Request):
    # Pre-check WITHOUT consuming: validation failures below (bad purpose,
    # unknown account, already registered) must not burn the caller's budget —
    # otherwise an attacker locks any victim out of OTP for an hour without
    # sending a single email.
    email_key = _email_limiter_key(body.email)
    ip_key = f"otp:ip:{client_ip(request)}"
    if not _otp_send_email_limiter.would_allow(email_key):
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many verification code requests for this email address. "
                "Please try again later."
            ),
        )
    if not _otp_send_ip_limiter.would_allow(ip_key):
        raise HTTPException(
            status_code=429,
            detail="Too many verification code requests from this IP. Please try again later.",
        )
    result = request_otp(body.email, body.purpose)
    # Consume slots only when a code was actually generated & mailed.
    if isinstance(result, dict) and result.get("ok"):
        _otp_send_email_limiter.allow(email_key)
        _otp_send_ip_limiter.allow(ip_key)
    return result


@router.post("/verify")
def auth_verify(body: VerifyBody, request: Request):
    if not _otp_verify_limiter.allow(f"otpv:ip:{client_ip(request)}"):
        raise HTTPException(
            status_code=429,
            detail="Too many verification attempts. Please try again later.",
        )
    return verify_otp_and_login(
        body.email,
        body.code,
        body.purpose,
        body.role,
        agreed=body.agreed,
        request=request,
    )


@router.get("/me")
def auth_me(request: Request):
    user = require_user(request)
    return {
        "user": user,
        # Surface the server's current policy version so the client can detect
        # a stale consent (user.privacy_version != current) and re-prompt.
        "current_privacy_version": settings.privacy_version,
    }


@router.post("/logout")
def auth_logout(request: Request):
    token = extract_bearer_token(request)
    if token:
        auth_store.revoke_session(token)
    return {"ok": True}


@router.post("/consent")
def auth_record_consent(body: ConsentBody, request: Request):
    """Record (or refresh) the signed-in user's privacy-policy consent.

    Called by the frontend re-consent banner when the server-side policy
    version has moved past the version the user last agreed to.
    """
    user = require_user(request)
    version = (body.privacy_version or settings.privacy_version).strip()
    if not version:
        raise HTTPException(status_code=400, detail="Missing privacy version.")
    ok = auth_store.record_consent(
        user["id"],
        privacy_version=version,
        privacy_consented_ip=auth_store.ip_hash(client_ip(request)),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="User not found.")
    return {
        "ok": True,
        "privacy_version": version,
        "privacy_consented_at": _iso_now(),
    }
