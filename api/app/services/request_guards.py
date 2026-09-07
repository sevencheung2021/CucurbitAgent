"""Shared request guards: chat size caps + safe public error messages."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from fastapi import HTTPException

from app.config import settings

# Shown to browsers / SSE clients — never include exception text or paths.
PUBLIC_ERROR_MESSAGE = "Something went wrong. Please try again later."


def public_error_message(_exc=None) -> str:
    return PUBLIC_ERROR_MESSAGE


def _clip(text: str, limit: int) -> str:
    s = (text or "").strip()
    if limit > 0 and len(s) > limit:
        return s[:limit]
    return s


def enforce_chat_size(
    message: str,
    history: Optional[Sequence[Mapping[str, Any]]] = None,
):
    """Validate/truncate chat payload. Raises HTTP 400 if message empty after trim."""
    max_msg = max(1, int(settings.llm_max_message_chars or 4000))
    max_turns = max(0, int(settings.llm_max_history_turns or 12))
    max_hchars = max(1, int(settings.llm_max_history_chars or 2000))

    msg = _clip(message, max_msg)
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    cleaned = []
    for item in history or []:
        role = str(item.get("role") or "").strip()[:32]
        content = _clip(str(item.get("content") or ""), max_hchars)
        if role not in ("user", "assistant", "system"):
            continue
        if not content:
            continue
        cleaned.append({"role": role, "content": content})
    if max_turns and len(cleaned) > max_turns:
        cleaned = cleaned[-max_turns:]
    return msg, cleaned


def enforce_short_text(label: str, value: str, max_chars: int = 2000) -> str:
    """For gene_id / follow-up question style fields."""
    s = _clip(value, max_chars)
    if label == "gene_id" and not s:
        raise HTTPException(status_code=400, detail="gene_id is required")
    return s
