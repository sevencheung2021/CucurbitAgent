import json
import time
from typing import Callable, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services.action_logger import ActionTimer, log_action
from app.services.legacy_core import (
    run_agent_loop,
    tool_search_protein_structure,
    tool_search_gene_comprehensive,
    FAST_PATH_MODEL,
)
from app.services.llm_text_sanitize import DsmlStreamFilter
from app.services.rate_limit import client_ip, enforce_llm_rate_limit
from app.services.auth import require_llm_user
from app.services.request_guards import (
    enforce_chat_size,
    enforce_short_text,
    public_error_message,
)
from app.services.user_analytics import log_search_event

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatMessage(BaseModel):
    role: str = Field(..., max_length=32)
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)


class ProteinChatRequest(BaseModel):
    gene_id: str = Field(..., min_length=1, max_length=128)
    species: str = Field(default="Cucumber", max_length=64)
    question: str = Field(default="", max_length=4000)
    # Prior turns (Genes/Proteins page follow-up questions need context).
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)


class GeneChatRequest(BaseModel):
    gene_id: str = Field(..., min_length=1, max_length=128)
    species: str = Field(default="Cucumber", max_length=64)
    # Optional follow-up after the default overview (Genes page AI Summary).
    question: str = Field(default="", max_length=4000)
    # Prior turns, so follow-ups like "what about its orthologs?" resolve.
    history: List[ChatMessage] = Field(default_factory=list, max_length=40)


def _history_messages(history: Optional[List[ChatMessage]]) -> List[dict]:
    """Chat history → OpenAI messages. Only user/assistant turns are passed
    through; anything else (empty content, odd roles) is dropped so a bad
    client payload can't break the LLM call."""
    if not history:
        return []
    out: List[dict] = []
    for m in history:
        role = m.get("role") if isinstance(m, dict) else m.role
        content = m.get("content") if isinstance(m, dict) else m.content
        if role in ("user", "assistant") and content and content.strip():
            out.append({"role": role, "content": content})
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_ai():
    """Raise 503 if the AI backend is not configured. Routes that stream
    LLM output call this BEFORE constructing the StreamingResponse so the
    error reaches the client as a normal JSON error instead of an SSE
    error event halfway through."""
    ok, reason = settings.validate_ai_config()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_fast_path(
    *,
    module: str,
    gene_id: str,
    species: str,
    request: Request,
    tool_fn: Callable[[str, str], str],
    build_user_prompt: Callable[[dict, str, str], str],
    system_prompt: str,
    status_reading_label: str,
    status_found_template: Callable[[dict], str],
    max_tokens: int = 800,
    history: Optional[List[ChatMessage]] = None,
):
    """Shared SSE flow for the fast-path chat routes (gene/protein/expression).

    All three routes follow the same shape:
      1. status: reading local DB
      2. call one tool
      3. status: found / not_found
      4. stream final answer from glm-4.5-air
      5. done

    Per-route differences are injected via ``tool_fn``, ``build_user_prompt``
    and ``status_found_template``. The whole flow is wrapped in an
    ``ActionTimer`` so we always get a structured log row, including on error.
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.zhipu_api_key, base_url=settings.zhipu_base_url)
    ip = client_ip(request)
    session_id = request.headers.get("X-Session-Id")
    timer = ActionTimer(
        module=module, action="chat",
        gene_id=gene_id, species=species,
        query_text=gene_id, ip=ip, session_id=session_id,
    )

    def event_stream():
        try:
            with timer:
                yield _sse("status", {"message": status_reading_label})

                raw = tool_fn(gene_id, species)
                tool_data = json.loads(raw)

                if tool_data.get("status") != "success":
                    msg = tool_data.get("message", f"{module} not found.")
                    yield _sse("status", {"message": f"⚠️ {msg}"})
                    yield _sse("token", {"text": msg})
                    yield _sse("done", {})
                    timer.status = tool_data.get("status", "not_found")
                    return

                yield _sse("status", {"message": status_found_template(tool_data)})
                yield _sse("status", {"message": "✍️ Generating interpretation..."})

                user_prompt = build_user_prompt(tool_data, gene_id, species)

                stream = client.chat.completions.create(
                    model=FAST_PATH_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *_history_messages(history),
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=max_tokens,
                    stream=True,
                    extra_body=settings.llm_extra_body,
                )
                dsml_filter = DsmlStreamFilter()
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        safe = dsml_filter.feed(chunk.choices[0].delta.content)
                        if safe:
                            yield _sse("token", {"text": safe})
                tail = dsml_filter.flush()
                if tail:
                    yield _sse("token", {"text": tail})

                yield _sse("done", {})
        except Exception as e:
            # ActionTimer will flip status to "error" on exception exit,
            # but exceptions raised inside the generator's `with` block need
            # us to also push an SSE error so the browser shows it.
            yield _sse("error", {"message": public_error_message(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Full Agent loop route
# ---------------------------------------------------------------------------

@router.post("/chat")
def agent_chat(body: ChatRequest, request: Request):
    user = require_llm_user(request)
    message, history = enforce_chat_size(
        body.message,
        [{"role": m.role, "content": m.content} for m in body.history],
    )
    _require_ai()
    enforce_llm_rate_limit(request, user=user)

    ip = client_ip(request)
    session_id = request.headers.get("X-Session-Id")
    log_search_event(module="agent", action="chat", query_text=message, user=user, ip=ip)

    tool_trace: list[dict] = []

    def _sink(entry: dict):
        tool_trace.append(entry)

    timer = ActionTimer(
        module="agent", action="chat",
        query_text=message, ip=ip, session_id=session_id,
    )

    def event_stream():
        try:
            with timer:
                for event in run_agent_loop(message, history, None,
                                            tool_trace_sink=_sink):
                    etype = event.get("type")
                    if etype == "status":
                        yield _sse("status", {"message": event["message"]})
                    elif etype == "token":
                        # Tokens are already fully sanitized in legacy_core
                        # before chunking — do NOT re-sanitize each 48-char
                        # fragment (that can empty mid-sentence pieces).
                        text = event.get("text") or ""
                        if text:
                            yield _sse("token", {"text": text})
                    elif etype == "tool_result":
                        yield _sse("tool_result", {
                            "tool": event.get("tool", ""),
                            "data": event.get("data") or {},
                        })
                timer.tool_trace = tool_trace
                yield _sse("done", {})
        except Exception as e:
            # Force-flush whatever trace we have so far before re-raising.
            timer.tool_trace = tool_trace
            yield _sse("error", {"message": public_error_message(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/simple")
def agent_chat_simple(body: ChatRequest, request: Request):
    """Non-streaming fallback for simple clients."""
    user = require_llm_user(request)
    message, history = enforce_chat_size(
        body.message,
        [{"role": m.role, "content": m.content} for m in body.history],
    )
    ok, reason = settings.validate_ai_config()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)
    enforce_llm_rate_limit(request, user=user)

    ip = client_ip(request)
    session_id = request.headers.get("X-Session-Id")
    log_search_event(module="agent", action="chat_simple", query_text=message, user=user, ip=ip)
    tool_trace: list[dict] = []

    def _sink(entry: dict):
        tool_trace.append(entry)

    parts = []
    try:
        with ActionTimer(module="agent", action="chat_simple",
                         query_text=message, ip=ip, session_id=session_id) as timer:
            for event in run_agent_loop(
                message,
                history,
                None,
                tool_trace_sink=_sink,
            ):
                if event.get("type") == "token":
                    parts.append(event["text"])
            timer.tool_trace = tool_trace
        return {"content": "".join(parts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=public_error_message(e)) from e


# ---------------------------------------------------------------------------
# Fast-path routes (gene / protein)
# ---------------------------------------------------------------------------

_PROTEIN_SYSTEM_PROMPT = (
    "You are a concise protein structure analyst. Given ESMFold prediction data, "
    "write a SHORT (4-8 sentences) plain summary for a researcher. Cover: overall fold "
    "quality based on pLDDT, notable predicted binding sites if any, and one practical "
    "suggestion. No markdown headings, no preamble, no references section. Reply in the "
    "same language the user used (default English for gene IDs).\n"
    "RESIDUE COUNTING RULES (strict): all counts use per-residue confidence > 0.5. "
    "A residue may belong to several binding types — per-type counts overlap. When "
    "reporting a total residue number, use binding_residues_unique_count (deduplicated). "
    "NEVER sum per-type counts as the total; never quote raw JSON entry counts."
)


def _protein_user_prompt(tool_data: dict, gene_id: str, species: str) -> str:
    sites = tool_data.get("binding_sites", [])
    site_summary = ", ".join(f"{s['site']} ({s['confidence']})" for s in sites) if sites else "none predicted"
    sites_block = json.dumps(sites, ensure_ascii=False) if sites else "[]"
    return (
        f"Gene: {tool_data.get('gene_id', gene_id)}  Species: {species}\n"
        f"pLDDT: {tool_data.get('plddt_score', 'N/A')} ({tool_data.get('plddt_label', '')})\n"
        f"Predicted binding sites: {site_summary}\n"
        f"Raw sites JSON: {sites_block}\n"
        f"PDB file available: {tool_data.get('pdb_file', '')}\n"
    )


def _protein_status_found(tool_data: dict) -> str:
    plddt = tool_data.get("plddt_score", "N/A")
    label = tool_data.get("plddt_label", "")
    sites = tool_data.get("binding_sites", [])
    return f"✅ pLDDT={plddt} ({label}), {len(sites)} binding sites"


@router.post("/protein-chat")
def agent_protein_chat(body: ProteinChatRequest, request: Request):
    """Fast path for Proteins-page AI Summary / follow-up on a gene ID."""
    user = require_llm_user(request)
    gene_id = enforce_short_text("gene_id", body.gene_id, 128)
    species = enforce_short_text("species", body.species or "Cucumber", 64) or "Cucumber"
    question = enforce_short_text("question", body.question or "", settings.llm_max_message_chars)
    _require_ai()
    enforce_llm_rate_limit(request, user=user)
    log_search_event(
        module="protein",
        action="chat",
        query_text=question or gene_id,
        user=user,
        ip=client_ip(request),
    )

    def build_user_prompt(tool_data: dict, gid: str, sp: str) -> str:
        base = _protein_user_prompt(tool_data, gid, sp)
        if question:
            return (
                f"{base}\n\n"
                f"Researcher follow-up question:\n{question}\n\n"
                "Answer this question using ONLY the structured data above. "
                "Keep the reply short (3-8 sentences)."
            )
        return f"{base}\n\nWrite a concise overview summary of this protein structure."

    return _stream_fast_path(
        module="protein",
        gene_id=gene_id,
        species=species,
        request=request,
        tool_fn=tool_search_protein_structure,
        build_user_prompt=build_user_prompt,
        system_prompt=_PROTEIN_SYSTEM_PROMPT,
        status_reading_label=f"🔧 Reading {gene_id} protein structure (local DB)...",
        status_found_template=_protein_status_found,
        max_tokens=600,
        history=body.history,
    )


_GENE_SYSTEM_PROMPT = (
    "You are a concise gene function analyst for a cucurbit genomics platform. "
    "Given structured gene data (annotation, GO terms, Pfam domains, orthologs, variants), "
    "write a SHORT (5-10 sentences) plain summary for a researcher. Cover: "
    "(1) what the gene likely does based on annotation/GO/Pfam, "
    "(2) conservation hints from orthologs (which species have homologs, identity range), "
    "(3) notable variants if any (e.g. nonsense/missense count). "
    "No markdown headings, no preamble, no references section, no tool suggestions. "
    "Reply in the same language the user used (default English for gene IDs)."
)


def _gene_user_prompt(tool_data: dict, gene_id: str, species: str) -> str:
    # Strip bulky payload we don't need for the summary: full sequences AND
    # the priority_variants detail list (we keep the summary counts).
    slim = {k: v for k, v in tool_data.items()
            if k not in ("cds_sequence", "protein_sequence")}
    if "cds_sequence" in tool_data:
        slim["cds_sequence"] = {"length_bp": tool_data["cds_sequence"].get("length_bp")}
    if "protein_sequence" in tool_data:
        slim["protein_sequence"] = {"length_aa": tool_data["protein_sequence"].get("length_aa")}
    if "natural_variants" in tool_data and isinstance(tool_data["natural_variants"], dict):
        nv = tool_data["natural_variants"]
        slim["natural_variants"] = {
            "count": nv.get("count", 0),
            "summary": nv.get("summary", {}),
        }

    return (
        f"Gene: {tool_data.get('gene_id', gene_id)}  Species: {tool_data.get('species', species)}\n\n"
        f"Structured data (JSON):\n{json.dumps(slim, ensure_ascii=False)}"
    )


def _gene_status_found(tool_data: dict) -> str:
    parts = []
    if "gene_structure" in tool_data: parts.append("gene structure")
    if "go_terms" in tool_data:
        parts.append(f"GO ({sum(len(v) for v in tool_data['go_terms'].values())})")
    if "pfam_domains" in tool_data: parts.append(f"{len(tool_data['pfam_domains'])} Pfam domains")
    if "plant_orthologs" in tool_data: parts.append(f"{len(tool_data['plant_orthologs'])} orthologs")
    if "natural_variants" in tool_data:
        nv = tool_data["natural_variants"]
        parts.append(f"{nv.get('count', 0) if isinstance(nv, dict) else 0} variants")
    return f"✅ Loaded: {', '.join(parts) if parts else 'basic info'}"


@router.post("/gene-chat")
def agent_gene_chat(body: GeneChatRequest, request: Request):
    """Fast path for Genes-page AI Summary / follow-up on a gene ID."""
    user = require_llm_user(request)
    gene_id = enforce_short_text("gene_id", body.gene_id, 128)
    # Empty species = auto-detect: tool_search_gene_comprehensive will scan all
    # 9 cucurbit databases and set `found_sp`. This lets the frontend send just
    # a gene ID (MELO3C.., Cla.., Cmo..) without knowing the species name.
    species = enforce_short_text("species", body.species or "", 64)
    question = enforce_short_text("question", body.question or "", settings.llm_max_message_chars)
    _require_ai()
    enforce_llm_rate_limit(request, user=user)
    log_search_event(
        module="gene",
        action="chat",
        query_text=question or gene_id,
        user=user,
        ip=client_ip(request),
    )

    def build_user_prompt(tool_data: dict, gid: str, sp: str) -> str:
        base = _gene_user_prompt(tool_data, gid, sp)
        if question:
            return (
                f"{base}\n\n"
                f"Researcher follow-up question:\n{question}\n\n"
                "Answer this question using ONLY the structured data above. "
                "Keep the reply short (3-8 sentences)."
            )
        return (
            f"{base}\n\n"
            "Write a concise overview summary of this gene for a researcher."
        )

    return _stream_fast_path(
        module="gene",
        gene_id=gene_id,
        species=species,
        request=request,
        tool_fn=tool_search_gene_comprehensive,
        build_user_prompt=build_user_prompt,
        system_prompt=_GENE_SYSTEM_PROMPT,
        status_reading_label=f"🔧 Reading {gene_id} gene info (local DB)...",
        status_found_template=_gene_status_found,
        max_tokens=800,
        history=body.history,
    )
