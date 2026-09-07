import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import settings
from app.services.action_logger import ActionTimer
from app.services.genome_catalog import GENOME_DIR_MAP
from app.services.legacy_core import (
    format_variant_display_df,
    fetch_gene_variants,
    summarize_variants,
    tool_search_gene_comprehensive,
)
from app.services.rate_limit import client_ip
from app.services.auth import get_optional_user
from app.services.user_analytics import log_search_event

VARIANT_PAGE_SIZE = 50

router = APIRouter(prefix="/api/genes", tags=["genes"])


@router.get("/species")
def list_species():
    return {"species": list(settings.global_search_config.keys())}


@router.get("/search")
def search_gene(species: str = Query(...), gene_id: str = Query(...), request: Request = None):
    # Empty species is allowed — tool_search_gene_comprehensive will scan all
    # 9 cucurbit databases and auto-detect by gene ID prefix (CsaV3.., MELO3C..,
    # Cla.., Cmo.., etc). This lets the Agent send just a gene ID without
    # knowing the species name. An unknown species name also falls through to
    # the auto-detect branch (not in GLOBAL_SEARCH_CONFIG → search all).
    if species and species not in settings.global_search_config:
        raise HTTPException(status_code=400, detail=f"Invalid species: {species}")
    ip = client_ip(request) if request is not None else None
    session_id = request.headers.get("X-Session-Id") if request is not None else None
    if request is not None:
        log_search_event(
            module="gene",
            action="search",
            query_text=gene_id,
            user=get_optional_user(request),
            ip=ip,
        )
    with ActionTimer(module="gene", action="search", gene_id=gene_id,
                     species=species, query_text=gene_id, ip=ip, session_id=session_id):
        raw = tool_search_gene_comprehensive(gene_id=gene_id, species=species)
        data = json.loads(raw)
        if data.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=data.get("message", "Not found"))
        return data


@router.get("/variants")
def gene_variants(
    species: str = Query(...),
    gene_id: str = Query(...),
    page: int = Query(1, ge=1),
    tab: str = Query("cds", pattern="^(cds|non_cds|all)$"),
    consequence: str = Query("all", pattern="^(all|synonymous|missense|nonsense)$"),
):
    df = fetch_gene_variants(species, gene_id)
    if df is None or df.empty:
        return {
            "summary": {},
            "rows": [],
            "total": 0,
            "page": 1,
            "pages": 0,
            "chart": {"categories": [], "counts": []},
        }

    summary = summarize_variants(df)
    if tab == "cds":
        filtered = df[df["region"] == "CDS"].copy()
    elif tab == "non_cds":
        filtered = df[df["region"] != "CDS"].copy()
    else:
        filtered = df.copy()

    if consequence != "all" and "impact_class" in filtered.columns:
        wanted = {
            "synonymous": "cds_synonymous",
            "missense": "cds_missense",
            "nonsense": "cds_nonsense",
        }[consequence]
        filtered = filtered[filtered["impact_class"] == wanted].copy()

    total = len(filtered)
    pages = max(1, (total - 1) // VARIANT_PAGE_SIZE + 1) if total else 1
    page = min(page, pages)
    start = (page - 1) * VARIANT_PAGE_SIZE
    chunk = filtered.iloc[start:start + VARIANT_PAGE_SIZE]
    display = format_variant_display_df(chunk)
    rows = display.to_dict(orient="records")

    chart = {
        "categories": ["Synonymous", "Missense", "Nonsense", "Intron/UTR", "Other"],
        "counts": [
            summary["synonymous"],
            summary["missense"],
            summary["nonsense"],
            summary["non_cds"],
            summary["total"] - summary["cds_total"] - summary["non_cds"],
        ],
    }
    chart["categories"] = [c for i, c in enumerate(chart["categories"]) if chart["counts"][i] > 0]
    chart["counts"] = [c for c in chart["counts"] if c > 0]

    return {
        "summary": summary,
        "rows": rows,
        "total": total,
        "page": page,
        "pages": pages,
        "chart": chart,
    }
