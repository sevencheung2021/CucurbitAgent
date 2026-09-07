from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.rate_limit import allow_visit_record, client_ip
from app.services.visit_analytics import get_visit_stats, record_visit, build_footer_map_html

router = APIRouter(prefix="/api/visits", tags=["visits"])


@router.get("/stats")
def visit_stats(request: Request, record: bool = True):
    if record and allow_visit_record(request):
        record_visit(client_ip(request), request.headers.get("X-Session-Id"))
    stats = get_visit_stats()
    return stats


@router.get("/map", response_class=HTMLResponse)
def visit_map(request: Request):
    if allow_visit_record(request):
        record_visit(client_ip(request))
    stats = get_visit_stats()
    return build_footer_map_html(stats)
