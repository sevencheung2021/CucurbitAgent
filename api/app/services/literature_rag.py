"""
Unified hybrid literature retrieval (FTS5 + ChromaDB) with RRF fusion.

Week 1: unified API, cached Chroma, parallel FTS/vector, chunk_text, RRF.
Week 2: FTS AND + species filter, bge-reranker, query rewrite before search.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from app.config import settings
from app.services.literature_query import (
    ParsedLiteratureQuery,
    extract_locus_ids_linked_to_names,
    parse_literature_query,
    rewrite_for_retrieval,
)

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None
    embedding_functions = None

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Force CPU inference. The local box has an RTX 5090 D (Blackwell, sm_120) but
# PyTorch 2.4.1 only ships kernels up to sm_90, so any CUDA op fails with
# "no kernel image is available" and falls back to CPU anyway — just noisily.
# The Aliyun production deployment is CPU-only too, so forcing CPU here makes
# dev and prod behave identically AND silences the CUDA error spam that was
# burying real errors in the logs. Set CUAGENT_DEVICE=cuda to re-enable GPU.
INFERENCE_DEVICE = os.getenv("CUAGENT_DEVICE", "cpu").lower()
if INFERENCE_DEVICE == "cpu":
    # Hide CUDA from PyTorch entirely so it never tries to init it.
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

LITERATURE_DB_PATH = str(settings.literature_db_path)
CHROMA_DB_PATH = str(settings.chroma_db_path)
EMBED_MODEL_NAME = settings.embed_model_local or settings.embed_model_name
CHROMA_COLLECTION_NAME = "cucurbit_papers"
RERANKER_MODEL = os.getenv("CUAGENT_RERANKER_MODEL", "BAAI/bge-reranker-base")
RERANKER_ENABLED = os.getenv("CUAGENT_RERANKER_ENABLED", "true").lower() in ("1", "true", "yes")
QUERY_REWRITE_LLM = os.getenv("CUAGENT_LITERATURE_QUERY_LLM", "true").lower() in ("1", "true", "yes")

RRF_K = 60
DEFAULT_TOP_K = 10
FTS_RECALL = 40
VECTOR_RECALL = 40
RERANK_POOL = 30
VECTOR_MAX_DISTANCE = 0.85
CHUNK_TEXT_AGENT_LIMIT = 1200
CHUNK_TEXT_UI_SNIPPET = 400

_init_lock = threading.Lock()
_chroma_client: Any = None
_chroma_collection: Any = None
_chroma_query_collection: Any = None
_vector_search_available = False
_chroma_ready = False
_chroma_error: Optional[str] = None
_reranker: Any = None
_reranker_failed = False

_search_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="lit-rag")


def initialize() -> dict[str, Any]:
    global _chroma_ready, _chroma_error
    with _init_lock:
        if _chroma_ready:
            return status()

        if chromadb is None:
            _chroma_error = "chromadb not installed"
            return status()

        if not _load_chroma_collections():
            return status()

        _chroma_ready = True
        if _chroma_query_collection is not None:
            try:
                _warm_chroma_into_memory()
                print(f"✅ Literature RAG warmed: Chroma={CHROMA_DB_PATH}, embed={EMBED_MODEL_NAME}")
            except Exception as exc:
                print(f"⚠️ Vector channel unavailable at warm-up (FTS still works): {exc}")
                _chroma_error = f"vector_query: {exc}"
        else:
            print("ℹ️ Literature RAG: FTS keyword mode (vector embedder not on disk)")

        if RERANKER_ENABLED:
            _get_reranker()

        return status()


def status() -> dict[str, Any]:
    count = None
    if _chroma_collection is not None:
        try:
            count = _chroma_collection.count()
        except Exception:
            count = None
    return {
        "sqlite_path": LITERATURE_DB_PATH,
        "sqlite_exists": _sqlite_exists(),
        "chroma_path": CHROMA_DB_PATH,
        "chroma_exists": _chroma_path_exists(),
        "chroma_ready": _chroma_ready,
        "chroma_count": count,
        "chroma_error": _chroma_error,
        "embed_model": EMBED_MODEL_NAME,
        "reranker_enabled": RERANKER_ENABLED,
        "reranker_model": RERANKER_MODEL,
        "reranker_loaded": _reranker is not None and not _reranker_failed,
        "query_rewrite_llm": QUERY_REWRITE_LLM,
        "vector_search_available": _vector_search_available,
    }


def _sqlite_exists() -> bool:
    return os.path.exists(LITERATURE_DB_PATH)


def _ensure_hub_hidden_table(conn: sqlite3.Connection) -> None:
    """Hub-only denylist. Does not affect Chroma / FTS / agent RAG."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hub_hidden (
            paper_key TEXT PRIMARY KEY,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _hub_hidden_keys(conn: sqlite3.Connection, paper_keys: list[str]) -> set[str]:
    """Return the subset of paper_keys that are Hub-hidden."""
    keys = [k for k in dict.fromkeys(paper_keys) if k]
    if not keys:
        return set()
    _ensure_hub_hidden_table(conn)
    hidden: set[str] = set()
    chunk = 500
    for i in range(0, len(keys), chunk):
        batch = keys[i : i + chunk]
        placeholders = ",".join("?" * len(batch))
        rows = conn.execute(
            f"SELECT paper_key FROM hub_hidden WHERE paper_key IN ({placeholders})",
            batch,
        ).fetchall()
        hidden.update(str(r[0]) for r in rows)
    return hidden


def _filter_hub_visible_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop Hub-hidden papers from a Hub listing/search result list."""
    if not papers or not _sqlite_exists():
        return papers
    try:
        with sqlite3.connect(LITERATURE_DB_PATH) as conn:
            hidden = _hub_hidden_keys(
                conn, [str(p.get("paper_key") or "") for p in papers]
            )
        if not hidden:
            return papers
        return [p for p in papers if (p.get("paper_key") or "") not in hidden]
    except Exception as exc:
        print(f"hub_hidden filter error: {exc}")
        return papers


def _chroma_path_exists() -> bool:
    return os.path.exists(CHROMA_DB_PATH)


def _load_chroma_collections() -> bool:
    global _chroma_client, _chroma_collection, _chroma_query_collection, _chroma_error, _vector_search_available
    if not _chroma_path_exists():
        _chroma_error = f"ChromaDB path not found: {CHROMA_DB_PATH}"
        return False
    try:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        _chroma_collection = _chroma_client.get_collection(name=CHROMA_COLLECTION_NAME)
        print(f"✅ ChromaDB cached: {CHROMA_DB_PATH} (count={_chroma_collection.count()})")
        _chroma_query_collection = None
        _vector_search_available = False
        if embedding_functions is not None:
            try:
                ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=EMBED_MODEL_NAME,
                    device=INFERENCE_DEVICE,
                )
                _chroma_query_collection = _chroma_client.get_collection(
                    name=CHROMA_COLLECTION_NAME,
                    embedding_function=ef,
                )
                _vector_search_available = True
            except Exception as exc:
                print(f"⚠️ Chroma query embedder not loaded (FTS-only mode): {exc}")
        _chroma_error = None
        return True
    except Exception as exc:
        _chroma_error = str(exc)
        _chroma_client = None
        _chroma_collection = None
        _chroma_query_collection = None
        _vector_search_available = False
        print(f"⚠️ ChromaDB load failed: {exc}")
        return False


def get_chroma_collection():
    if _chroma_query_collection is not None:
        return _chroma_query_collection
    with _init_lock:
        if _chroma_collection is None:
            _load_chroma_collections()
        return _chroma_query_collection


def _warm_chroma_into_memory():
    """Trigger Chroma's lazy segment loading so queries don't cold-read disk.

    Chroma uses lazy segment loading: the HNSW vector index and metadata
    segments are only read from disk the first time a collection is queried,
    then cached in Chroma's internal segment manager (NOT in Python object
    space). A single small query is sufficient to force this load — the
    segment then stays in RAM for the life of the client.

    IMPORTANT: do NOT use ``collection.get(limit=None, include=["embeddings"])``
    here. That materialises the ENTIRE embedding matrix as a Python list-of-
    lists and returns it to the caller, which on a ~600k-vector / ~2.5GB
    collection pushes peak RSS past 30GB and gets the process OOM-killed
    (verified the hard way on 2026-07-09). The official warm-up recipe from
    the Chroma Cookbook is ``collection.get(limit=1, include=["embeddings"])``;
    we go one step further and issue a real ``query()`` so both the vector
    AND metadata segments warm along the exact code path real queries use.

    Memory cost: ~the size of the HNSW index + metadata segment in Chroma's
    cache (a few hundred MB), no Python-side duplication.
    """
    if _chroma_query_collection is None:
        return
    count = _chroma_query_collection.count()
    if count <= 0:
        print("ℹ️ ChromaDB warm skipped: empty collection")
        return
    print(f"🔥 Warming ChromaDB ({count} vectors) segment into memory...")
    _chroma_query_collection.query(query_texts=["cucumber genomics"], n_results=1)
    print(f"✅ ChromaDB warm: segment loaded ({count} vectors indexed)")


def reload() -> dict:
    """热重载 ChromaDB collection (新入库的论文立即可检索,无需重启 API)。

    场景: scripts/fetch_yesterday.sh 抓完新论文后调用 /api/literature/reload。
    """
    global _chroma_ready, _chroma_error
    with _init_lock:
        old_count = None
        if _chroma_collection is not None:
            try:
                old_count = _chroma_collection.count()
            except Exception:
                pass
        ok = _load_chroma_collections()
        new_count = None
        if _chroma_collection is not None:
            try:
                new_count = _chroma_collection.count()
            except Exception:
                pass
        _chroma_ready = ok
    return {
        "reloaded": ok,
        "old_count": old_count,
        "new_count": new_count,
        "added": (new_count - old_count) if (old_count is not None and new_count is not None) else None,
        "error": _chroma_error,
    }


def _get_reranker():
    global _reranker, _reranker_failed
    if not RERANKER_ENABLED or _reranker_failed:
        return None
    if _reranker is not None:
        return _reranker
    try:
        from sentence_transformers import CrossEncoder

        # Explicit device avoids PyTorch auto-detecting CUDA and then failing
        # on incompatible GPUs (RTX 5090 sm_120 vs PyTorch 2.4 sm_90 max).
        _reranker = CrossEncoder(RERANKER_MODEL, device=INFERENCE_DEVICE)
        print(f"✅ Reranker loaded: {RERANKER_MODEL} (device={INFERENCE_DEVICE})")
        return _reranker
    except Exception as exc:
        print(f"⚠️ Reranker unavailable: {exc}")
        _reranker_failed = True
        return None


def _chunk_key(paper_key: str, rowid: Any = None, chroma_id: str = "", chunk_id: Any = "") -> str:
    if chunk_id is not None and str(chunk_id) != "":
        return f"{paper_key}:{chunk_id}" if paper_key else str(chunk_id)
    if chroma_id:
        return str(chroma_id)
    if rowid is not None and paper_key:
        return f"{paper_key}:{rowid}"
    return str(paper_key or chroma_id or "unknown")


def _paper_row(title, pub_year, abstract, journal, doi, pmid, authors, quality, paper_key, species="") -> dict[str, Any]:
    year = str(pub_year) if pub_year is not None else ""
    return {
        "paper_key": paper_key or "",
        "title": title or "",
        "year": year,
        "pub_date": year,
        "abstract": abstract or "",
        "journal": journal or "",
        "doi": doi or "",
        "pmid": pmid or "",
        "authors": authors or "",
        "quality": quality,
        "species": species or "",
    }


def _species_filter_sql(parsed: ParsedLiteratureQuery) -> tuple[str, list[Any]]:
    if not parsed.species_terms:
        return "", []
    clauses = ["LOWER(p.species) LIKE ?" for _ in parsed.species_terms]
    params = [f"%{term.lower()}%" for term in parsed.species_terms]
    return f" AND ({' OR '.join(clauses)})", params


def _search_fts5(parsed: ParsedLiteratureQuery, limit: int = FTS_RECALL) -> list[dict[str, Any]]:
    if not _sqlite_exists() or not parsed.fts_match:
        return []

    species_sql, species_params = _species_filter_sql(parsed)
    hits: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(LITERATURE_DB_PATH)
        cur = conn.cursor()
        sql = f"""
            SELECT c.rowid, c.paper_key, c.chunk_id, c.chunk_text,
                   p.title, p.pub_year, p.abstract, p.journal, p.doi, p.pmid,
                   p.authors, p.quality, p.species
            FROM chunks_fts c
            JOIN papers p ON p.paper_key = c.paper_key
            WHERE c.chunk_text MATCH ?
            {species_sql}
            ORDER BY bm25(chunks_fts) ASC, p.quality DESC
            LIMIT ?
        """
        cur.execute(sql, (parsed.fts_match, *species_params, limit))
        for row in cur.fetchall():
            (
                rowid, paper_key, chunk_id, chunk_text, title, pub_year, abstract,
                journal, doi, pmid, authors, quality, species,
            ) = row
            key = _chunk_key(paper_key, rowid=rowid, chunk_id=chunk_id)
            hits.append(
                {
                    "chunk_key": key,
                    "chunk_id": str(chunk_id) if chunk_id is not None else key,
                    "paper_key": paper_key or "",
                    "chunk_text": chunk_text or "",
                    "source": "keyword",
                    "paper": _paper_row(
                        title, pub_year, abstract, journal, doi, pmid, authors, quality, paper_key, species
                    ),
                }
            )
        conn.close()
    except Exception as exc:
        print(f"FTS5 chunk search error: {exc}")
    return hits


def _search_vector(query: str, n_results: int = VECTOR_RECALL) -> list[dict[str, Any]]:
    if not query.strip() or not _vector_search_available:
        return []

    collection = get_chroma_collection()
    if collection is None:
        return []

    hits: list[dict[str, Any]] = []
    try:
        res = collection.query(query_texts=[query], n_results=n_results)
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        for i, doc in enumerate(docs):
            chroma_id = ids[i] if i < len(ids) else ""
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            if dist is not None and float(dist) > VECTOR_MAX_DISTANCE:
                continue

            paper_key = str(meta.get("paper_key", "") or "")
            chunk_id = meta.get("chunk_id", chroma_id)
            title = str(meta.get("title", "") or "Unknown")
            pub_year = meta.get("year", meta.get("pub_year", ""))
            hits.append(
                {
                    "chunk_key": _chunk_key(paper_key, chroma_id=chroma_id, chunk_id=chunk_id),
                    "chunk_id": str(chunk_id),
                    "paper_key": paper_key,
                    "chunk_text": doc or "",
                    "source": "semantic",
                    "similarity": round(1.0 - float(dist), 3) if dist is not None else None,
                    "paper": _paper_row(
                        title,
                        pub_year,
                        "",
                        meta.get("journal", ""),
                        meta.get("doi", ""),
                        meta.get("pmid", ""),
                        meta.get("authors", ""),
                        meta.get("quality"),
                        paper_key,
                        meta.get("species", ""),
                    ),
                }
            )
    except Exception as exc:
        print(f"Vector chunk search error: {exc}")
    return hits


def _rrf_fuse(ranked_lists: list[list[dict[str, Any]]], top_k: int) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    best: dict[str, dict[str, Any]] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            key = item.get("chunk_key") or item.get("chunk_id") or ""
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            if key not in best:
                best[key] = item
            else:
                existing = best[key]
                if not existing.get("chunk_text") and item.get("chunk_text"):
                    existing["chunk_text"] = item["chunk_text"]
                if existing.get("source") != item.get("source"):
                    existing["source"] = "hybrid"

    ordered = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    merged: list[dict[str, Any]] = []
    for key in ordered[:top_k]:
        row = dict(best[key])
        row["rrf_score"] = round(scores[key], 6)
        merged.append(row)
    return merged


def _rerank_chunks(query: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    model = _get_reranker()
    if model is None or len(chunks) <= 1:
        return chunks[:top_k]

    pairs = [(query, item.get("chunk_text") or "") for item in chunks]
    try:
        scores = model.predict(pairs)
        ranked = sorted(
            zip(chunks, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for item, score in ranked[:top_k]:
            row = dict(item)
            row["rerank_score"] = round(float(score), 4)
            out.append(row)
        return out
    except Exception as exc:
        print(f"Reranker error: {exc}")
        return chunks[:top_k]


def _llm_expand_query(raw: str) -> Optional[str]:
    if not QUERY_REWRITE_LLM or not settings.zhipu_api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.zhipu_api_key, base_url=settings.zhipu_base_url)
        resp = client.chat.completions.create(
            # Query rewrite is a tiny classification task — use the fast model.
            # Falls back to the same env override as the chat endpoints.
            model=os.getenv("CUAGENT_FAST_PATH_MODEL", "deepseek-v4-flash"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Expand the user's cucurbit genomics literature search into 3-8 English "
                        "scientific keywords. Include gene names, traits, pathways, and species "
                        "if relevant. Return ONLY space-separated keywords, no sentences."
                    ),
                },
                {"role": "user", "content": raw},
            ],
            # temperature=0: query expansion must be deterministic — the same
            # benchmark question should always hit the same retrieval set
            # (0.1 made paper ranking drift between identical runs).
            temperature=0,
            max_tokens=80,
            extra_body=settings.llm_extra_body,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:
        print(f"Query LLM expand skipped: {exc}")
        return None


def _prepare_query(raw: str) -> ParsedLiteratureQuery:
    llm_extra = _llm_expand_query(raw)
    return rewrite_for_retrieval(raw, llm_expand=llm_extra)


def hybrid_search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    fts_limit: int = FTS_RECALL,
    vector_limit: int = VECTOR_RECALL,
    rewrite: bool = True,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {
            "status": "empty_query",
            "query": q,
            "chunks": [],
            "papers": [],
            "keyword_count": 0,
            "semantic_count": 0,
            "count": 0,
        }

    parsed = _prepare_query(q) if rewrite else parse_literature_query(q)
    vector_query = parsed.rewritten or q

    fts_future = _search_pool.submit(_search_fts5, parsed, fts_limit)
    vec_future = _search_pool.submit(_search_vector, vector_query, vector_limit)
    keyword_hits = fts_future.result()
    semantic_hits = vec_future.result()

    fused = _rrf_fuse([keyword_hits, semantic_hits], top_k=max(top_k, RERANK_POOL))
    chunks = _rerank_chunks(vector_query, fused, top_k=top_k)

    # FTS5 unicode61 treats "MYB60" ≠ "CsMYB60". Paper-chat / agent used to
    # miss every CsMYB60 title that the Literature Hub page still found via
    # LIKE recall. Merge exact-substring papers into hybrid for ALL callers.
    anchors = list(dict.fromkeys(
        list(parsed.gene_ids) + _extract_anchor_tokens(q) + _extract_anchor_tokens(parsed.rewritten or "")
    ))
    exact_papers = _recall_exact_substring_papers(anchors) if anchors else []
    if exact_papers and not chunks:
        chunks = [_synthetic_chunk_from_paper(p) for p in exact_papers[:top_k]]
    elif exact_papers and chunks:
        # Prefer keeping reranked chunks; exact papers still surface in papers[].
        pass

    if not chunks:
        return {
            "status": "no_results",
            "query": q,
            "rewritten_query": parsed.rewritten,
            "fts_match": parsed.fts_match,
            "species_filter": parsed.species_key,
            "message": (
                f"No local literature found for: {q}. "
                "(Both keyword and semantic search returned nothing — internet fallback is appropriate.)"
            ),
            "chunks": [],
            "papers": [],
            "keyword_count": len(keyword_hits),
            "semantic_count": len(semantic_hits),
            "count": 0,
        }

    # Re-hydrate identity fields (especially DOI) from SQLite `papers` so
    # Chroma metadata can never serve a stale/wrong DOI on the citation card
    # or in the LLM context. paper-chat SSE papers event shares this path.
    chunks = _hydrate_chunks_from_sqlite(chunks)
    papers = _hydrate_papers_from_sqlite(_aggregate_papers(chunks))
    if exact_papers:
        seen = {p.get("paper_key") or p.get("title") for p in papers}
        for extra in exact_papers:
            key = extra.get("paper_key") or extra.get("title")
            if key and key not in seen:
                papers.append(extra)
                seen.add(key)
        papers = _rank_with_exact_anchor(papers, anchors)
    return {
        "status": "success",
        "query": q,
        "rewritten_query": parsed.rewritten,
        "fts_match": parsed.fts_match,
        "species_filter": parsed.species_key,
        "count": len(chunks),
        "keyword_count": len(keyword_hits),
        "semantic_count": len(semantic_hits),
        "chunks": [_format_chunk(c) for c in chunks],
        "papers": papers,
    }


def _format_chunk(item: dict[str, Any], text_limit: int = CHUNK_TEXT_AGENT_LIMIT) -> dict[str, Any]:
    paper = item.get("paper") or {}
    text = item.get("chunk_text") or ""
    if len(text) > text_limit:
        text = text[:text_limit] + "..."
    return {
        "chunk_key": item.get("chunk_key"),
        "chunk_id": item.get("chunk_id"),
        "paper_key": item.get("paper_key"),
        "chunk_text": text,
        "source": item.get("source"),
        "rrf_score": item.get("rrf_score"),
        "rerank_score": item.get("rerank_score"),
        "similarity": item.get("similarity"),
        "title": paper.get("title", ""),
        "year": paper.get("year", ""),
        "journal": paper.get("journal", ""),
        "doi": paper.get("doi", ""),
        "pmid": paper.get("pmid", ""),
        "authors": paper.get("authors", ""),
    }


def _aggregate_papers(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_paper: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        paper = dict(chunk.get("paper") or {})
        paper_key = chunk.get("paper_key") or paper.get("paper_key") or paper.get("title") or ""
        if not paper_key:
            continue
        snippet = chunk.get("chunk_text") or ""
        if len(snippet) > CHUNK_TEXT_UI_SNIPPET:
            snippet = snippet[:CHUNK_TEXT_UI_SNIPPET] + "..."
        candidate = {
            **paper,
            "paper_key": paper_key,
            "match_snippet": snippet,
            "match_source": chunk.get("source"),
            "rrf_score": chunk.get("rrf_score"),
            "rerank_score": chunk.get("rerank_score"),
        }
        prev = by_paper.get(paper_key)
        prev_score = (prev or {}).get("rerank_score") or (prev or {}).get("rrf_score") or 0
        cand_score = candidate.get("rerank_score") or candidate.get("rrf_score") or 0
        if prev is None or cand_score > prev_score:
            by_paper[paper_key] = candidate
    return list(by_paper.values())


def _lookup_papers_by_key(paper_keys: list[str]) -> dict[str, dict[str, Any]]:
    """Authoritative metadata from SQLite `papers` table, keyed by paper_key.

    Chroma chunk metadata can be stale or incomplete (especially `doi`). Every
    UI citation card and LLM citation context MUST prefer this table so DOI
    never drifts from the canonical record.
    """
    keys = [k for k in dict.fromkeys(paper_keys) if k]
    if not keys or not os.path.exists(LITERATURE_DB_PATH):
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        placeholders = ",".join("?" * len(keys))
        with sqlite3.connect(LITERATURE_DB_PATH) as conn:
            cur = conn.execute(
                f"""
                SELECT paper_key, doi, pmid, title, authors, journal,
                       pub_year, abstract, species, quality
                FROM papers
                WHERE paper_key IN ({placeholders})
                """,
                keys,
            )
            for pk, doi, pmid, title, authors, journal, year, abstract, species, quality in cur.fetchall():
                out[str(pk)] = {
                    "paper_key": str(pk),
                    "doi": (doi or "").strip(),
                    "pmid": (pmid or "").strip(),
                    "title": title or "",
                    "authors": authors or "",
                    "journal": journal or "",
                    "year": str(year or ""),
                    "abstract": abstract or "",
                    "species": species or "",
                    "quality": quality,
                }
    except Exception as exc:
        print(f"SQLite paper hydrate error: {exc}")
    return out


def _hydrate_papers_from_sqlite(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overwrite citation fields with SQLite-canonical values (DOI included)."""
    lookup = _lookup_papers_by_key([p.get("paper_key", "") for p in papers])
    if not lookup:
        return papers
    hydrated: list[dict[str, Any]] = []
    for p in papers:
        pk = p.get("paper_key") or ""
        canon = lookup.get(pk)
        if not canon:
            hydrated.append(p)
            continue
        merged = dict(p)
        # Always prefer SQLite for identity fields — never trust Chroma meta DOI.
        for field in ("doi", "pmid", "title", "authors", "journal", "year", "abstract", "species"):
            if canon.get(field) not in (None, ""):
                merged[field] = canon[field]
            elif field == "doi":
                # Explicit empty DOI from SQLite beats a stale Chroma DOI.
                merged["doi"] = ""
        hydrated.append(merged)
    return hydrated


def _hydrate_chunks_from_sqlite(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same SQLite hydrate for chunk.paper (used by LLM citation context)."""
    lookup = _lookup_papers_by_key([c.get("paper_key", "") for c in chunks])
    if not lookup:
        return chunks
    out: list[dict[str, Any]] = []
    for c in chunks:
        pk = c.get("paper_key") or ""
        canon = lookup.get(pk)
        if not canon:
            out.append(c)
            continue
        paper = dict(c.get("paper") or {})
        for field in ("doi", "pmid", "title", "authors", "journal", "year", "abstract", "species"):
            if canon.get(field) not in (None, ""):
                paper[field] = canon[field]
            elif field == "doi":
                paper["doi"] = ""
        paper["paper_key"] = pk
        nc = dict(c)
        nc["paper"] = paper
        out.append(nc)
    return out


def _extract_anchor_tokens(query: str) -> list[str]:
    """Extract precise-match anchor tokens from a UI search query.

    Anchors are entity-like tokens (gene names, protein families, IDs) that a
    user expects to find *literally* in title/abstract. We require letters AND a
    digit so that generic English words ("drought", "resistance") are never
    treated as anchors — those should keep ranking by reranker semantics.

    Examples:
      "MYB60"            -> ["MYB60"]
      "CsMYB60"          -> ["CsMYB60"]
      "CsaV3_5G010920"   -> ["CsaV3_5G010920"]
      "cucumber drought" -> []   (no digit -> semantic ranking unchanged)
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*", query)
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        key = tok.lower()
        if key in seen or len(tok) < 3:
            continue
        seen.add(key)
        out.append(tok)
    return out


def _rank_with_exact_anchor(
    papers: list[dict[str, Any]], anchors: list[str]
) -> list[dict[str, Any]]:
    """Sort aggregated papers so that exact-substring matches of any anchor
    token (in title or abstract) come first; within each group, keep the
    reranker/rrf ordering already on the paper dict.

    This is a defensive reorder: the reranker is a semantic model and can bury
    a paper whose title literally contains "CsMYB60" in favor of a topically
    related but non-matching paper. For UI keyword search, an exact hit on the
    user's entity token is the strongest possible relevance signal and must
    not be pushed below fold.
    """
    if not anchors:
        return papers

    lowered = [a.lower() for a in anchors]

    def score_of(p: dict[str, Any]) -> float:
        return float(p.get("rerank_score") or p.get("rrf_score") or 0.0)

    def has_exact(p: dict[str, Any]) -> int:
        haystack = f"{p.get('title','')}\n{p.get('abstract','')}".lower()
        return 1 if any(a in haystack for a in lowered) else 0

    return sorted(papers, key=lambda p: (has_exact(p), score_of(p)), reverse=True)


def _recall_exact_substring_papers(anchors: list[str], limit: int = 80) -> list[dict[str, Any]]:
    """FTS5 with unicode61 tokenizer treats 'CsMYB60' and 'MYB60' as distinct
    tokens (no substring match), so a query for 'MYB60' silently misses every
    paper whose title/abstract only contains 'CsMYB60'. This fallback does a
    case-insensitive substring (LIKE) recall on papers.title/abstract for each
    anchor token, returning full paper rows that the FTS channel missed.

    These rows are merged into the hybrid result and then surface to the top
    via _rank_with_exact_anchor (they have the anchor literally in title/abs).
    """
    if not anchors or not _sqlite_exists():
        return []
    conn = sqlite3.connect(LITERATURE_DB_PATH)
    cur = conn.cursor()
    where = " OR ".join(["title LIKE ? OR abstract LIKE ?" for _ in anchors])
    params: list[str] = []
    for a in anchors:
        params.extend([f"%{a}%", f"%{a}%"])
    cur.execute(
        f"""
        SELECT paper_key, doi, pmid, title, authors, journal,
               COALESCE(pub_date_display, pub_date) AS pub_date,
               pub_year, abstract, species, quality
        FROM papers
        WHERE {where}
        ORDER BY quality DESC, pub_year DESC
        LIMIT ?
        """,
        params + [limit],
    )
    rows: list[dict[str, Any]] = []
    for pk, doi, pmid, title, authors, journal, pub_date, year, abstract, species, quality in cur.fetchall():
        rows.append(
            {
                "paper_key": pk,
                "doi": doi or "",
                "pmid": pmid or "",
                "title": title or "",
                "authors": authors or "",
                "journal": journal or "",
                "pub_date": pub_date or "",
                "year": str(year or ""),
                "abstract": abstract or "",
                "species": species or "",
                "quality": quality or 0.0,
                "match_snippet": (abstract or "")[:CHUNK_TEXT_UI_SNIPPET],
                "match_source": "exact_substring",
                # No rerank score; anchor-sorting will place these correctly.
                "rerank_score": None,
                "rrf_score": None,
            }
        )
    conn.close()
    return rows


def _synthetic_chunk_from_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Turn an exact-substring paper row into a chunk so hybrid_search can
    still return status=success + LLM context when FTS/vector both miss
    (classic MYB60 vs CsMYB60 case)."""
    pk = paper.get("paper_key") or paper.get("title") or ""
    text = (paper.get("abstract") or paper.get("match_snippet") or paper.get("title") or "").strip()
    return {
        "chunk_key": f"exact:{pk}",
        "chunk_id": f"exact:{pk}",
        "paper_key": pk,
        "chunk_text": text[:CHUNK_TEXT_AGENT_LIMIT],
        "source": "exact_substring",
        "rrf_score": None,
        "rerank_score": None,
        "paper": {
            "paper_key": pk,
            "title": paper.get("title", ""),
            "year": paper.get("year", ""),
            "journal": paper.get("journal", ""),
            "doi": paper.get("doi", ""),
            "pmid": paper.get("pmid", ""),
            "authors": paper.get("authors", ""),
            "abstract": paper.get("abstract", ""),
            "species": paper.get("species", ""),
            "quality": paper.get("quality") or 0.0,
        },
    }

def _generate_cited_answer(
    query: str,
    chunks: list[dict[str, Any]],
    max_chunks: int = 10,
) -> Optional[str]:
    """Generate a complete cited answer from reranked chunks using glm-4.5-air.

    This mirrors the architecture of the Potato Knowledge Hub's
    `search_RAG_db` tool: instead of returning raw chunk JSON for the outer
    agent to synthesize (slow: the agent then spends 25-35s "thinking" over
    the chunks), we generate a fully-formed, citation-tagged answer INSIDE
    the tool. The outer agent then only needs light polishing, cutting its
    decision + synthesis time dramatically.

    Args:
        query: The user's original (English) query.
        chunks: Already reranked chunks (each is a _format_chunk dict with
            title/year/journal/doi/chunk_text fields).
        max_chunks: How many top chunks to feed the LLM (Potato uses 10).

    Returns:
        A markdown string with [N] inline citations and a References list,
        or None on failure (caller falls back to returning raw chunks).
    """
    if not chunks:
        return None
    if not settings.zhipu_api_key:
        return None

    # Build the numbered context block. Each chunk becomes "Source N" with its
    # text + DOI. Truncate each chunk to keep total prompt bounded.
    context_parts: list[str] = []
    used_dois: list[str] = []
    doi_to_num: dict[str, int] = {}
    for i, chunk in enumerate(chunks[:max_chunks]):
        doi = (chunk.get("doi") or "").strip()
        if doi and doi not in doi_to_num:
            doi_to_num[doi] = len(used_dois) + 1
            used_dois.append(doi)
        num = doi_to_num.get(doi, len(context_parts) + 1) if doi else len(context_parts) + 1
        text = (chunk.get("chunk_text") or "").strip()
        if len(text) > 800:
            text = text[:800] + "..."
        context_parts.append(f"Source {num}:\nText: {text}\nDOI: {doi or 'N/A'}")

    if not context_parts:
        return None
    full_context = "\n\n".join(context_parts)

    system_prompt = (
        "You are an expert in molecular biology and plant genomics. Synthesize "
        "findings from the provided literature sources into a clear, scientifically "
        "accurate answer.\n\n"
        "Rules:\n"
        "1. Base your answer ONLY on the provided Context. Do NOT fabricate.\n"
        "2. If the Context is unrelated or insufficient, respond exactly: "
        "`Sorry, no relevant literature found in the local database.`\n"
        "3. Cite each claim with an inline tag [N] where N is the Source number. "
        "If a sentence draws on multiple sources, add multiple tags like [1][3].\n"
        "4. Organize with headings/bullets where helpful.\n"
        "5. Use the same language as the User Question.\n"
        "6. Do NOT mention 'context' or 'provided sources' — integrate citations naturally.\n"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.zhipu_api_key, base_url=settings.zhipu_base_url)
        resp = client.chat.completions.create(
            model=os.getenv("CUAGENT_FAST_PATH_MODEL", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"User Question:\n{query}\n\n"
                        f"Context:\n{full_context}\n\nAnswer:"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1500,
            extra_body=settings.llm_extra_body,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            return None

        # If the model triggered the "no relevant" escape, pass it through.
        if "no relevant literature" in answer.lower():
            return answer

        # Post-process [N] tags → swap "Source N" numbering for DOI-based
        # numbering, then append a References list. glm usually follows the
        # numbering we gave it, but defensively rebuild the references from
        # the used_dois list so the list always matches the inline numbers.
        referenced_nums = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
        if referenced_nums and used_dois:
            refs_lines = []
            for num in referenced_nums:
                if 1 <= num <= len(used_dois):
                    doi = used_dois[num - 1]
                    # Find a chunk carrying this DOI to get its title.
                    title = next(
                        (
                            (c.get("title") or "")
                            for c in chunks[:max_chunks]
                            if (c.get("doi") or "").strip() == doi
                        ),
                        "",
                    )
                    title_part = f"{title} " if title else ""
                    refs_lines.append(f"[{num}] {title_part}DOI: {doi}")
            if refs_lines:
                answer = answer.rstrip() + "\n\n**References:**\n" + "\n".join(refs_lines)
        return answer
    except Exception as exc:
        print(f"generate_cited_answer failed: {exc}")
        return None


def _gene_name_tokens_for_locus_recall(query: str, parsed: Optional[ParsedLiteratureQuery] = None) -> list[str]:
    """Symbols like CsSGR / MYB60 — not locus IDs — used to find ID-bearing chunks."""
    names: list[str] = []
    if parsed:
        names.extend(parsed.gene_ids)
    names.extend(re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", query or ""))
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        if re.search(r"Csa(?:V3_)?\d", n, re.IGNORECASE):
            continue
        if n.lower() in {"the", "and", "gene", "id", "cucumber", "stay", "green"}:
            continue
        key = n.lower()
        if key in seen or len(n) < 3:
            continue
        seen.add(key)
        out.append(n)
    return out[:8]


def fetch_locus_evidence_chunks(
    gene_names: list[str],
    paper_keys: Optional[list[str]] = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Pull PDF chunks where a gene symbol co-occurs with a cucumber locus ID.

    Hybrid rerank often returns abstract/intro snippets (no Csa ID). The ID is
    typically in a later results/figure chunk of the same paper, or in a citing
    paper that writes ``CsSGR (Csa5G156180)``.
    """
    names = [n for n in gene_names if n and len(n) >= 3]
    if not names or not _sqlite_exists():
        return []
    name_clauses = " OR ".join(["c.chunk_text LIKE ?" for _ in names])
    name_params = [f"%{n}%" for n in names]
    keys = [k for k in (paper_keys or []) if k]

    # Two-tier recall: (1) chunks whose TEXT mentions a queried gene name —
    # these carry the symbol↔locus pairing we need; (2) only if tier-1 is
    # short, pad with Csa-ID chunks from the already-retrieved papers.
    # (The old single OR query let unrelated paper chunks fill the LIMIT
    # before the name-matched ones — no ORDER BY, arbitrary row order.)
    base_where = """
            c.chunk_text LIKE '%Csa5G%' OR c.chunk_text LIKE '%Csa5M%'
            OR c.chunk_text LIKE '%CsaV3_%' OR c.chunk_text LIKE '%Csa0%'
    """
    select_cols = """
        SELECT c.rowid, c.paper_key, c.chunk_id, c.chunk_text,
               p.title, p.pub_year, p.abstract, p.journal, p.doi, p.pmid,
               p.authors, p.quality, p.species
        FROM chunks_fts c
        JOIN papers p ON p.paper_key = c.paper_key
    """
    queries = [
        (f"{select_cols} WHERE ({base_where}) AND ({name_clauses}) LIMIT ?",
         list(name_params) + [limit]),
    ]
    if keys:
        queries.append(
            (
                f"{select_cols} WHERE ({base_where}) AND c.paper_key IN ({','.join('?' * len(keys))}) LIMIT ?",
                list(keys) + [max(0, limit)],
            )
        )
    hits: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(LITERATURE_DB_PATH)
        cur = conn.cursor()
        rows = []
        seen_rowids: set = set()
        for sql, params in queries:
            if len(rows) >= limit:
                break
            for row in cur.execute(sql, params).fetchall():
                if row[0] in seen_rowids:
                    continue
                seen_rowids.add(row[0])
                rows.append(row)
                if len(rows) >= limit:
                    break
        for row in rows:
            (
                rowid, paper_key, chunk_id, chunk_text, title, pub_year, abstract,
                journal, doi, pmid, authors, quality, species,
            ) = row
            text = chunk_text or ""
            linked = extract_locus_ids_linked_to_names(text, names)
            if not linked:
                continue
            key = _chunk_key(paper_key, rowid=rowid, chunk_id=chunk_id)
            hits.append(
                {
                    "chunk_key": key,
                    "chunk_id": str(chunk_id) if chunk_id is not None else key,
                    "paper_key": paper_key or "",
                    "chunk_text": text,
                    "source": "locus_evidence",
                    "paper": _paper_row(
                        title, pub_year, abstract, journal, doi, pmid, authors, quality, paper_key, species
                    ),
                }
            )
        conn.close()
    except Exception as exc:
        print(f"locus evidence chunk search error: {exc}")
    return hits


_STRICT_SYMBOL_BLOCKLIST = {
    "RNA", "DNA", "UV", "GO", "SNP", "QTL", "PCR", "ABA", "IAA", "GA", "ET",
    "SA", "JA", "ROS", "DEG", "TF", "KO", "OE", "WT", "BL", "V1", "V2", "V3",
    "CHINESE", "CHINESELONG", "DHL", "T2T", "FPKM", "ESMFOLD", "NCBI", "PMCID",
    "HTTP", "HTTPS", "DOI", "PDF",
}


def _strict_symbol_names(query: str) -> list:
    """Gene-symbol-like tokens + their prefix-stripped cores (CsCHS → CHS).
    ≥2 uppercase letters filters out plain words (chalcone/synthase)."""
    import re as _re

    out = []
    for tok in _re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", query or ""):
        letters = _re.sub(r"[^A-Za-z]", "", tok)
        if len(letters) < 3 or sum(1 for c in letters if c.isupper()) < 2:
            continue
        if tok.upper() in _STRICT_SYMBOL_BLOCKLIST:
            continue
        out.append(tok)
        m = _re.match(r"^(?:[A-Z][a-z])+([A-Z][A-Za-z0-9]{2,})$", tok)
        if m and m.group(1).upper() not in _STRICT_SYMBOL_BLOCKLIST:
            out.append(m.group(1))
    return list(dict.fromkeys(out))


def search_for_agent(query: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    result = hybrid_search(query, top_k=top_k, rewrite=True)
    if result["status"] == "empty_query":
        return {
            "status": "no_results",
            "message": "Empty literature query.",
            "chunks": [],
            "papers": [],
            "count": 0,
        }

    parsed = parse_literature_query(query)
    names = _gene_name_tokens_for_locus_recall(query, parsed)
    # Strict gene symbols (CsCHS → also bare CHS) MUST drive the locus-evidence
    # chunk recall — and when they exist, EXCLUSIVELY: the plain-token list
    # above (chalcone/what/official…) fills the recall LIMIT with loosely
    # matching chunks before the symbol-paired ones (no ORDER BY in SQL).
    strict = _strict_symbol_names(query)
    names = strict if strict else list(names)
    paper_keys = [p.get("paper_key") for p in (result.get("papers") or []) if p.get("paper_key")]
    extra = fetch_locus_evidence_chunks(names, paper_keys=paper_keys, limit=8) if names else []
    if extra:
        chunks = list(result.get("chunks") or [])
        seen = {c.get("chunk_key") or c.get("chunk_id") for c in chunks}
        prepended = []
        for ch in extra:
            ck = ch.get("chunk_key") or ch.get("chunk_id")
            if ck in seen:
                continue
            seen.add(ck)
            prepended.append(_format_chunk(ch))
        if prepended:
            result["chunks"] = prepended + chunks
            result["count"] = len(result["chunks"])
            extra_papers = _aggregate_papers(extra)
            papers = list(result.get("papers") or [])
            seen_pk = {p.get("paper_key") or p.get("title") for p in papers}
            for p in extra_papers:
                key = p.get("paper_key") or p.get("title")
                if key and key not in seen_pk:
                    papers.append(p)
                    seen_pk.add(key)
            result["papers"] = papers
            result["status"] = "success"
    return result


def search_for_agent_with_answer(
    query: str, top_k: int = DEFAULT_TOP_K
) -> dict[str, Any]:
    """Like search_for_agent, but also generates a complete cited answer.

    Architecture change (2026-07-09, learning from Potato Knowledge Hub):
    the outer agent used to receive raw chunks and spend 25-35s synthesizing
    them. Now this tool returns a ready-made `answer` field so the agent only
    does light polishing. The chunks/papers are still returned for the UI's
    evidence panel.

    The `answer` is generated with glm-4.5-air (same model as the agent) so
    there is no extra provider. On generation failure we transparently fall
    back to the raw-chunks shape (no `answer` field), and the agent falls
    back to its original synthesis behavior.
    """
    result = search_for_agent(query, top_k=top_k)
    if result.get("status") != "success":
        return result

    chunks = result.get("chunks") or []
    answer = _generate_cited_answer(query, chunks)
    if answer:
        result["answer"] = answer
    return result


def search_papers_page(query: str, page: int = 1, page_size: int = 10, subject: str = "") -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return _browse_papers(page, page_size, subject=subject)

    recall = max(page_size * page * 3, 60)
    result = hybrid_search(q, top_k=min(recall, 200), rewrite=True)
    if result["status"] != "success":
        return {
            "total": 0,
            "page": 1,
            "pages": 1,
            "papers": [],
            "query": q,
            "mode": "hybrid",
            "rewritten_query": result.get("rewritten_query"),
        }

    papers = result["papers"]
    # Anchor exact-substring recall: FTS5 unicode61 tokenizes 'CsMYB60' and
    # 'MYB60' as distinct tokens, so a search for 'MYB60' silently misses all
    # CsMYB60 papers. Pull any papers whose title/abstract literally contain
    # an anchor token (gene/ID) and merge them in (dedup by paper_key).
    anchors = _extract_anchor_tokens(q)
    if anchors:
        seen_keys = {p.get("paper_key") or p.get("title") for p in papers}
        for extra in _recall_exact_substring_papers(anchors):
            key = extra.get("paper_key") or extra.get("title")
            if key and key not in seen_keys:
                papers.append(extra)
                seen_keys.add(key)
        # Anchor exact-substring matches at the top so the reranker can't bury
        # a paper whose title literally contains the user's entity token.
        papers = _rank_with_exact_anchor(papers, anchors)

    # Hub-only denylist: hide bad/off-topic rows from Literature Hub search,
    # without touching Chroma / FTS used by agent RAG.
    papers = _filter_hub_visible_papers(papers)

    total = len(papers)
    pages = max(1, (total - 1) // page_size + 1) if total else 1
    page = min(max(page, 1), pages)
    offset = (page - 1) * page_size
    slice_papers = papers[offset : offset + page_size]

    # Batch-fetch subject for the sliced papers. The hybrid recall path (FTS /
    # vector / LIKE) does not propagate papers.subject, so without this the UI
    # would fall back to "Other" for every hybrid result even though the DB
    # stores the correct category (agri/biomed/food/chem).
    subject_map: dict[str, str] = {}
    keys_to_lookup = [p.get("paper_key") for p in slice_papers if p.get("paper_key")]
    if keys_to_lookup and _sqlite_exists():
        try:
            conn = sqlite3.connect(LITERATURE_DB_PATH)
            cur = conn.cursor()
            placeholders = ",".join("?" * len(keys_to_lookup))
            cur.execute(
                f"SELECT paper_key, subject FROM papers WHERE paper_key IN ({placeholders})",
                keys_to_lookup,
            )
            subject_map = {pk: (s or "other") for pk, s in cur.fetchall()}
            conn.close()
        except Exception as exc:
            print(f"subject lookup error: {exc}")

    rows = []
    for p in slice_papers:
        abstract = p.get("abstract") or p.get("match_snippet") or ""
        rows.append(
            {
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "journal": p.get("journal", ""),
                "doi": p.get("doi", ""),
                "pmid": p.get("pmid", ""),
                "pub_date": p.get("pub_date") or p.get("year", ""),
                "abstract": abstract,
                "match_snippet": p.get("match_snippet", ""),
                "match_source": p.get("match_source", ""),
                "subject": subject_map.get(p.get("paper_key", ""), p.get("subject") or "other"),
            }
        )

    return {
        "total": total,
        "page": page,
        "pages": pages,
        "papers": rows,
        "query": q,
        "mode": "hybrid",
        "rewritten_query": result.get("rewritten_query"),
        "species_filter": result.get("species_filter"),
        "keyword_count": result.get("keyword_count", 0),
        "semantic_count": result.get("semantic_count", 0),
    }


def _browse_papers(page: int, page_size: int, subject: str = "") -> dict[str, Any]:
    if not _sqlite_exists():
        return {"total": 0, "page": 1, "pages": 1, "papers": [], "mode": "browse"}

    conn = sqlite3.connect(LITERATURE_DB_PATH)
    cur = conn.cursor()
    _ensure_hub_hidden_table(conn)

    # subject 筛选 (空 / all = 全部; agri/biomed/food/chem/other = 单类)
    # Hub denylist: LEFT JOIN hub_hidden so RAG rows stay in papers/FTS/Chroma.
    clauses = ["h.paper_key IS NULL"]
    params: list = []
    if subject and subject != "all":
        clauses.append("p.subject = ?")
        params.append(subject)
    where_clause = "WHERE " + " AND ".join(clauses)

    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM papers p
        LEFT JOIN hub_hidden h ON h.paper_key = p.paper_key
        {where_clause}
        """,
        params,
    )
    total = cur.fetchone()[0]
    pages = max(1, (total - 1) // page_size + 1) if total else 1
    page = min(max(page, 1), pages)
    offset = (page - 1) * page_size

    # 排序: pub_date_real DESC (PubMed DEP Epub 日,精确到日) > sort_ym DESC > pmid DESC (兜底)
    # 老的 sort_ym 是基于 DP (期刊期号) 解析的, 不准; 新的 pub_date_real 才是真实 Epub 日
    #   e.g. 期刊排到 "2026 Dec" 那期, 但实际 4/28 就 Epub 了, 应该按 4/28 排
    # 显示用 pub_date_display (期刊期号), 排序用 pub_date_real (Epub 日)
    cur.execute(
        f"""
        SELECT p.title, p.authors, p.journal, p.doi, p.pmid,
               COALESCE(p.pub_date_display, p.pub_date) AS pub_date,
               p.abstract, p.subject
        FROM papers p
        LEFT JOIN hub_hidden h ON h.paper_key = p.paper_key
        {where_clause}
        ORDER BY p.pub_date_real DESC, p.sort_ym DESC, p.pub_year DESC, CAST(p.pmid AS INTEGER) DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, offset],
    )
    rows = []
    for title, authors, journal, doi, pmid, pub_date, abstract, subj in cur.fetchall():
        rows.append(
            {
                "title": title,
                "authors": authors,
                "journal": journal,
                "doi": doi,
                "pmid": pmid,
                "pub_date": pub_date,
                "abstract": abstract,
                "subject": subj or "other",
            }
        )
    conn.close()
    return {
        "total": total, "page": page, "pages": pages,
        "papers": rows, "mode": "browse", "subject_filter": subject or "all",
    }
