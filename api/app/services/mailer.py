"""OTP email delivery: SMTP when configured, otherwise log the code."""

from __future__ import annotations

import logging
import smtplib
import ssl
import sys
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("cuagent.mailer")


def _log_otp_fallback(to_email: str, purpose: str, code: str, note: str = "") -> None:
    """Write OTP where local ops can see it (api.log via stdout/stderr redirect).

    Uvicorn's default logging often leaves `cuagent.*` loggers without handlers,
    so `log.info` alone may never appear in logs/api.log. Always print as well.
    """
    suffix = f"  [{note}]" if note else ""
    msg = f"OTP for {to_email} ({purpose}): {code}{suffix}"
    log.info(msg)
    print(msg, file=sys.stderr, flush=True)


def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """Send a 6-digit OTP. Falls back to logging when SMTP_HOST is empty."""
    subject = "CucurbitAgent verification code"
    body = (
        f"Your CucurbitAgent verification code is: {code}\n\n"
        f"Purpose: {purpose}\n"
        f"This code expires in 10 minutes.\n"
        f"If you did not request this, you can ignore this email.\n"
    )
    host = (settings.smtp_host or "").strip()
    if not host:
        _log_otp_fallback(
            to_email,
            purpose,
            code,
            "SMTP not configured — code logged for local testing",
        )
        return

    from_addr = (settings.smtp_from or settings.smtp_user or "").strip()
    if not from_addr or not settings.smtp_user:
        log.warning("SMTP_HOST set but SMTP_FROM/SMTP_USER missing; logging OTP instead")
        _log_otp_fallback(to_email, purpose, code)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(body)

    use_ssl = (settings.smtp_use_ssl or "1").strip().lower() in ("1", "true", "yes", "on")
    port = int(settings.smtp_port or (465 if use_ssl else 587))
    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        log.info("OTP email sent to %s (%s)", to_email, purpose)
    except Exception:
        log.exception("Failed to send OTP email to %s; logging code as fallback", to_email)
        _log_otp_fallback(to_email, purpose, code)
