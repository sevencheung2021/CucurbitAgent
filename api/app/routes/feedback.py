import hashlib
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.feedback_store import save_feedback
from app.services.rate_limit import client_ip, enforce_feedback_rate_limit
from app.services.request_guards import public_error_message

router = APIRouter(prefix="/api", tags=["feedback"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_DESC = 1000


class FeedbackRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    description: str = Field(..., min_length=1, max_length=_MAX_DESC)


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, request: Request):
    enforce_feedback_rate_limit(request)

    email = (body.email or "").strip()
    description = (body.description or "").strip()

    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if not description:
        raise HTTPException(status_code=400, detail="Description is required.")
    if len(description) > _MAX_DESC:
        raise HTTPException(status_code=400, detail=f"Description must be ≤ {_MAX_DESC} characters.")

    ip = client_ip(request)
    ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]
    ua = (request.headers.get("User-Agent") or "")[:300]

    try:
        row_id = save_feedback(
            email=email,
            description=description,
            user_agent=ua,
            ip_hash=ip_hash,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_message(e)) from e

    return {"ok": True, "id": row_id, "message": "Thank you — your feedback has been received."}
