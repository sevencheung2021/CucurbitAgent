"""Unit tests for literature RAG (Week 1)."""
from app.services.literature_rag import _rrf_fuse


def test_rrf_fuse_prefers_items_in_both_lists():
    fts = [
        {"chunk_key": "a", "chunk_text": "alpha"},
        {"chunk_key": "b", "chunk_text": "beta"},
    ]
    vec = [
        {"chunk_key": "a", "chunk_text": "alpha semantic"},
        {"chunk_key": "c", "chunk_text": "gamma"},
    ]
    merged = _rrf_fuse([fts, vec], top_k=3)
    keys = [m["chunk_key"] for m in merged]
    assert keys[0] == "a"
    assert set(keys) == {"a", "b", "c"}


def test_rrf_fuse_respects_top_k():
    fts = [{"chunk_key": f"k{i}", "chunk_text": str(i)} for i in range(5)]
    merged = _rrf_fuse([fts], top_k=2)
    assert len(merged) == 2
