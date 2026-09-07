from fastapi import APIRouter, HTTPException, Query

from app.services.content_loader import get_home_content
from app.services.request_guards import public_error_message

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("/home")
def home_content(lang: str = Query(default="en", max_length=8)):
    """Locale-aware home content (home.<lang>.json 深合并英文基准，缺译回退英文)。"""
    try:
        return get_home_content(lang)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Home content not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_message(e)) from e
