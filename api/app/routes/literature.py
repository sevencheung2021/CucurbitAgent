import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services import literature_rag
from app.services.chat_intent import capability_reply_for, is_chitchat_or_meta
from app.services.legacy_core import FAST_PATH_MODEL
from app.services.rate_limit import enforce_llm_rate_limit, require_admin
from app.services.auth import require_llm_user, get_optional_user
from app.services.request_guards import enforce_chat_size, public_error_message
from app.services.rate_limit import client_ip
from app.services.user_analytics import log_search_event

router = APIRouter(prefix="/api/literature", tags=["literature"])

PAGE_SIZE = 10


class PaperChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


@router.get("/search")
def search_literature(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    request: Request = None,
):
    """Unified hybrid retrieval (FTS5 + ChromaDB + RRF). Used by Agent and UI."""
    rag_status = literature_rag.status()
    if not rag_status["sqlite_exists"] and not rag_status["chroma_exists"]:
        raise HTTPException(status_code=503, detail="Literature database not found")
    if request is not None:
        log_search_event(
            module="literature",
            action="search",
            query_text=q,
            user=get_optional_user(request),
            ip=client_ip(request),
        )
    return literature_rag.hybrid_search(q, top_k=top_k)


@router.get("/status")
def literature_status():
    """RAG subsystem health (SQLite, Chroma, embedder warm-up).

    Public response omits filesystem paths (ops can use reload / local logs).
    """
    st = literature_rag.status()
    return {
        k: v
        for k, v in st.items()
        if k not in ("sqlite_path", "chroma_path")
    }


@router.post("/reload")
def literature_reload(request: Request):
    """热重载 ChromaDB collection (新增量论文立即可检索)。

    给 scripts/fetch_yesterday.sh 抓完数据后调用,避免重启 API。
    Requires ``X-Admin-Token`` when ``CUAGENT_ADMIN_TOKEN`` is set; otherwise
    loopback clients only.
    """
    require_admin(request)
    return literature_rag.reload()


@router.get("/papers")
def list_papers(q: str = Query(""), page: int = Query(1, ge=1), subject: str = Query(""),
                request: Request = None):
    if not literature_rag.status()["sqlite_exists"]:
        raise HTTPException(status_code=503, detail="Literature database not found")
    if q.strip() and request is not None:
        log_search_event(
            module="literature",
            action="browse",
            query_text=q,
            user=get_optional_user(request),
            ip=client_ip(request),
        )
    return literature_rag.search_papers_page(q, page=page, page_size=PAGE_SIZE, subject=subject)


@router.post("/paper-chat")
def paper_chat(body: PaperChatRequest, request: Request):
    """
    Literature-grounded chat: 用本地知识库 (21k 论文 + ChromaDB + reranker) 检索
    top 相关论文,然后把摘要 + 关键 chunk 喂给 LLM 生成带引用编号的答案。

    SSE 事件流:
      - status:  检索进度提示 (前端可显示 "Searching..." / "Found N papers")
      - papers:  检索到的引用论文列表 (JSON),前端渲染成可点击卡片
      - token:   LLM 流式输出的答案 token
      - done:    完成
      - error:   异常
    """
    user = require_llm_user(request)
    q, _ = enforce_chat_size(body.message, [])
    ok, reason = settings.validate_ai_config()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)
    enforce_llm_rate_limit(request, user=user)
    log_search_event(
        module="literature",
        action="paper_chat",
        query_text=q,
        user=user,
        ip=client_ip(request),
    )

    def event_stream():
        try:
            # Greetings / meta questions: do not search the literature corpus.
            if is_chitchat_or_meta(q):
                yield f"event: token\ndata: {json.dumps({'text': capability_reply_for(q)}, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
                return

            # 1. 检索本地知识库 (hybrid: FTS5 + 向量 + RRF + reranker)
            yield f"event: status\ndata: {json.dumps({'message': 'Searching 21,133 local papers...'}, ensure_ascii=False)}\n\n"

            result = literature_rag.hybrid_search(q, top_k=8, rewrite=True)

            if result["status"] != "success" or not result.get("papers"):
                nohit_msg = (
                    "No relevant papers found in the local database. "
                    "Try rephrasing your question or use more specific gene/species terms."
                )
                yield f"event: token\ndata: {json.dumps({'text': nohit_msg}, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
                return

            papers = result["papers"][:8]
            chunks = result.get("chunks", [])[:8]

            # 2. 推送引用论文列表给前端 (渲染成卡片)
            yield f"event: papers\ndata: {json.dumps({'papers': papers}, ensure_ascii=False)}\n\n"

            found_msg = f"Found {len(papers)} relevant papers · generating answer..."
            yield f"event: status\ndata: {json.dumps({'message': found_msg}, ensure_ascii=False)}\n\n"

            # 3. 构造 LLM 上下文: 每篇论文一个编号块 [n] Title (Year, Journal)
            #    + abstract + 最相关的 chunk 摘录
            ctx_parts = []
            for i, paper in enumerate(papers, start=1):
                title = paper.get("title", "")
                year = paper.get("year", "")
                journal = paper.get("journal", "")
                abstract = paper.get("abstract", "") or ""
                snippet = paper.get("match_snippet", "") or ""
                ctx_parts.append(
                    f"[{i}] {title} ({year}, {journal})\n"
                    f"Abstract: {abstract[:600]}{'...' if len(abstract) > 600 else ''}\n"
                    + (f"Relevant excerpt: {snippet}" if snippet else "")
                )
            context = "\n\n".join(ctx_parts)

            # 4. LLM 生成答案 (强制引用编号,接地到上下文)
            from openai import OpenAI
            from app.services.legacy_core import detect_user_language
            from app.services.llm_text_sanitize import DsmlStreamFilter

            client = OpenAI(api_key=settings.zhipu_api_key, base_url=settings.zhipu_base_url)

            lang = detect_user_language(q)
            if lang == "zh":
                lang_rule = (
                    "CRITICAL LANGUAGE RULE: The user question is in Chinese. "
                    "Answer entirely in Chinese. Do not switch to English except for gene names and citations."
                )
            else:
                # Default English (incl. en and unknown). Zhipu models often drift
                # into Chinese unless this is stated as a hard constraint.
                lang_rule = (
                    "CRITICAL LANGUAGE RULE: The user question is in English. "
                    "Answer entirely in English. Do NOT use Chinese characters at all "
                    "(except unavoidable gene symbols / Latin species names already in the papers)."
                )

            system_prompt = (
                "You are a cucurbit research assistant. Answer the user's question STRICTLY based "
                "on the provided paper context. Cite sources using [n] notation matching the context "
                "numbering (e.g. 'CsAPRR2 regulates flowering time [1][3]'). "
                "If the context doesn't cover the question, say so honestly — do NOT hallucinate. "
                "Write 4-8 concise sentences. "
                + lang_rule
            )
            user_prompt = (
                f"Question: {q}\n\n"
                f"Paper context:\n{context}\n\n"
                f"(Reminder: write the answer in {'Chinese' if lang == 'zh' else 'English'} only.)"
            )

            stream = client.chat.completions.create(
                model=FAST_PATH_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
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
                        yield f"event: token\ndata: {json.dumps({'text': safe}, ensure_ascii=False)}\n\n"
            tail = dsml_filter.flush()
            if tail:
                yield f"event: token\ndata: {json.dumps({'text': tail}, ensure_ascii=False)}\n\n"

            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': public_error_message(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
