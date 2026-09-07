"""Public legal metadata: current privacy/terms versions and contact.

The policy text itself is rendered statically on the frontend
(/privacy, /terms) so it can be indexed and read without authentication.
This endpoint only exposes the *version* identifiers so clients can detect
when the policy they last agreed to is older than the current one and
prompt the user to re-consent.
"""

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/legal", tags=["legal"])


@router.get("/meta")
def legal_meta():
    return {
        "privacy_version": settings.privacy_version,
        "privacy_policy_updated_at": settings.privacy_policy_updated_at,
        "terms_version": settings.terms_version,
        "contact_email": settings.privacy_contact_email,
        # Operator identity shown in the policy footer.
        "operator": {
            "cn": "Beijing Vegetable Research Center (BVRC)",
            "en": "Beijing Academy of Agriculture and Forestry Sciences (BAAFS)",
        },
        # Retention windows, mirrored from settings so the policy page stays
        # in sync with the actual purge configuration without manual edits.
        "retention": {
            "session_days": 30,
            "analytics_days": settings.analytics_retention_days,
        },
    }
