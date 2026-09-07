"""Expression module REST endpoints.

Provides:
  GET  /api/expression/overview          -> 9-species statistics overview
  GET  /api/expression/gene               -> single-gene expression profile (tissues + top samples)
  GET  /api/expression/tissue-matrix      -> gene × tissue mean FPKM row (for bar chart)
  GET  /api/expression/coexpression       -> top-N co-expressed genes (Pearson)
  POST /api/expression/gene-chat          -> SSE fast path for "expression of <gene_id>"
"""
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.routes.agent import ChatMessage, _history_messages
from app.services.action_logger import ActionTimer
from app.services.legacy_core import FAST_PATH_MODEL
from app.services.expression_query import (
    overview as svc_overview,
    query_gene_expression,
    get_tissue_matrix,
)
from app.services.expression_coexp import find_coexpressed_genes
from app.services.rate_limit import client_ip, enforce_llm_rate_limit
from app.services.auth import require_llm_user, get_optional_user
from app.services.request_guards import enforce_short_text, public_error_message
from app.services.user_analytics import log_search_event
from app.services.llm_text_sanitize import DsmlStreamFilter

router = APIRouter(prefix="/api/expression", tags=["expression"])


def _req_meta(request: Request = None) -> dict:
    ip = None
    session_id = None
    if request is not None:
        ip = client_ip(request)
        session_id = request.headers.get("X-Session-Id")
    return {"ip": ip, "session_id": session_id}


@router.get("/overview")
def expression_overview():
    """9-species statistics overview for the landing table."""
    return svc_overview()


@router.get("/gene")
def expression_gene(
    request: Request,
    gene_id: str = Query(..., description="Gene ID, e.g. CsaV3_3G027830"),
    species: str = Query("", description="Optional UI species name to override auto-detect"),
    tissue: str = Query("", description="Optional tissue filter for top samples"),
    top: int = Query(15, ge=1, le=100, description="Number of top samples to return"),
):
    """Single-gene expression profile (tissue breakdown + top high-FPKM samples)."""
    meta = _req_meta(request)
    log_search_event(
        module="expression",
        action="gene",
        query_text=gene_id,
        user=get_optional_user(request),
        ip=meta.get("ip"),
    )
    with ActionTimer(module="expression", action="gene", gene_id=gene_id,
                     species=species or None, query_text=gene_id, **meta):
        result = query_gene_expression(gene_id, ui_species=species, tissue_filter=tissue, top_samples=top)
        if result["status"] == "invalid":
            raise HTTPException(status_code=400, detail=result["message"])
        if result["status"] in ("unknown_species", "no_data", "not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result


@router.get("/tissue-matrix")
def expression_tissue_matrix(
    request: Request,
    gene_id: str = Query(...),
    species: str = Query(""),
):
    """Gene × tissue mean FPKM row (sorted desc) for bar chart visualization."""
    meta = _req_meta(request)
    with ActionTimer(module="expression", action="tissue_matrix", gene_id=gene_id,
                     species=species or None, query_text=gene_id, **meta):
        result = get_tissue_matrix(gene_id, ui_species=species)
        if result["status"] == "invalid":
            raise HTTPException(status_code=400, detail=result["message"])
        if result["status"] in ("unknown_species", "no_data", "not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result


@router.get("/coexpression")
def expression_coexpression(
    request: Request,
    gene_id: str = Query(...),
    species: str = Query(""),
    top_k: int = Query(20, ge=1, le=200),
    min_corr: float = Query(0.5, ge=0.0, le=1.0),
):
    """Top-N co-expressed genes. Low-sample species return results WITH a warning."""
    meta = _req_meta(request)
    with ActionTimer(module="expression", action="coexpression", gene_id=gene_id,
                     species=species or None, query_text=gene_id, **meta):
        result = find_coexpressed_genes(gene_id, ui_species=species, top_k=top_k, min_corr=min_corr)
        if result["status"] == "invalid":
            raise HTTPException(status_code=400, detail=result["message"])
        if result["status"] in ("unknown_species", "no_data", "not_found"):
            raise HTTPException(status_code=404, detail=result)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result


class ExpressionChatRequest(BaseModel):
    gene_id: str = Field(..., min_length=1, max_length=128)
    species: str = Field(default="", max_length=64)
    question: str = Field(default="", max_length=4000)
    # Prior turns, so follow-up questions on the Expression page resolve.
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)


@router.post("/gene-chat")
def expression_gene_chat(body: ExpressionChatRequest, request: Request):
    """SSE fast path for "expression profile of <gene_id>" queries.

    Mirrors /api/agent/gene-chat and /api/agent/protein-chat:
      1. call query_gene_expression + find_coexpressed_genes locally (~1s)
      2. stream a short summary via glm-4.5-air

    Expected latency ~5-10s vs full Agent loop ~60s.
    """
    user = require_llm_user(request)
    gene_id = enforce_short_text("gene_id", body.gene_id, 128)
    species = enforce_short_text("species", body.species or "", 64)
    question = enforce_short_text("question", body.question or "", settings.llm_max_message_chars)

    ok, reason = settings.validate_ai_config()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)
    enforce_llm_rate_limit(request, user=user)
    log_search_event(
        module="expression",
        action="chat",
        query_text=question or gene_id,
        user=user,
        ip=client_ip(request),
    )

    from openai import OpenAI

    client = OpenAI(api_key=settings.zhipu_api_key, base_url=settings.zhipu_base_url)
    meta = _req_meta(request)
    timer = ActionTimer(module="expression", action="chat", gene_id=gene_id,
                        species=species or None, query_text=gene_id, **meta)

    def event_stream():
        try:
            with timer:
                yield _status(f"🔧 Reading {gene_id} expression profile (local DB)...")

                expr = query_gene_expression(gene_id, ui_species=species, top_samples=10)
                if expr["status"] != "success":
                    msg = expr.get("message", "Expression data not found.")
                    yield _status(f"⚠️ {msg}")
                    yield _token(msg)
                    yield _done()
                    timer.status = expr.get("status", "not_found")
                    return

                # Best-effort co-expression (warn on low samples, but still include)
                coexp = find_coexpressed_genes(
                    gene_id,
                    ui_species=species,
                    top_k=10,
                    min_corr=0.5,
                )
                coexp_list = coexp.get("coexpressed", []) if coexp.get("status") == "success" else []
                coexp_warning = coexp.get("warning")

                parts = [
                    f"{expr['n_samples']} samples across {expr['n_projects']} projects",
                    f"mean FPKM {expr['mean_fpkm']}, max {expr['max_fpkm']}",
                    f"top tissue: {expr['top_tissue']}",
                    f"reliability {expr['reliability']}",
                ]
                if coexp_warning:
                    parts.append(f"coexpression: {len(coexp_list)} hits (low-sample warning)")
                else:
                    parts.append(f"coexpression: {len(coexp_list)} hits")
                yield _status(f"✅ Loaded: {', '.join(parts)}")
                yield _status("✍️ Generating expression interpretation...")

                # Build slim payload (omit full sample lists to save tokens)
                slim = {
                    "gene_id": expr["gene_id"],
                    "species": expr["species_label"],
                    "n_samples": expr["n_samples"],
                    "n_projects": expr["n_projects"],
                    "mean_fpkm": expr["mean_fpkm"],
                    "max_fpkm": expr["max_fpkm"],
                    "tau_specificity": expr.get("tau_specificity"),
                    "top_tissue": expr.get("top_tissue"),
                    "top_tissue_fpkm": expr.get("top_tissue_fpkm"),
                    "reliability": expr["reliability"],
                    "tissue_profile_top8": expr["tissue_profile"][:8],
                    "condition_distribution_top5": expr.get("condition_distribution", [])[:5],
                    "coexpressed_top5": [
                        {"gene_id": g["gene_id"], "r": g["pearson_r"], "desc": g["description"]}
                        for g in coexp_list[:5]
                    ],
                    "coexpression_warning": coexp_warning,
                }

                system_prompt = (
                    "You are a concise gene expression analyst for a cucurbit genomics platform. "
                    "Given tissue-level FPKM, tau specificity, sample stats, and top co-expressed genes, "
                    "write a SHORT (4-8 sentences) plain summary for a researcher. Cover: "
                    "(1) where the gene is most expressed (top tissues) and how specific it is (tau), "
                    "(2) whether the data is reliable enough for strong conclusions (sample count tier), "
                    "(3) if co-expression hits are available, what functional hints they provide, "
                    "(4) if there's a low-sample warning, say so explicitly. "
                    "No markdown headings, no preamble, no references section. "
                    "Reply in the same language the user used (default English for gene IDs)."
                )
                user_prompt = (
                    f"Gene: {expr['gene_id']}  Species: {expr['species_label']}\n\n"
                    f"Structured data (JSON):\n{json.dumps(slim, ensure_ascii=False)}"
                )
                if question:
                    user_prompt += (
                        f"\n\nResearcher follow-up question:\n{question}\n\n"
                        "Answer this question using ONLY the structured data above. "
                        "Keep the reply short (3-8 sentences)."
                    )
                else:
                    user_prompt += (
                        "\n\nWrite a concise overview summary of this gene's expression profile."
                    )

                stream = client.chat.completions.create(
                    model=FAST_PATH_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *_history_messages(body.history),
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                    stream=True,
                    extra_body=settings.llm_extra_body,
                )
                dsml_filter = DsmlStreamFilter()
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        safe = dsml_filter.feed(chunk.choices[0].delta.content)
                        if safe:
                            yield _token(safe)
                tail = dsml_filter.flush()
                if tail:
                    yield _token(tail)

                yield _done()
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': public_error_message(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---- SSE event helpers ----
def _status(message: str) -> str:
    return f"event: status\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"


def _token(text: str) -> str:
    return f"event: token\ndata: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"


def _done() -> str:
    return "event: done\ndata: {}\n\n"
