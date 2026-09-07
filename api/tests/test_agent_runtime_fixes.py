"""Unit tests for CuAgent runtime fixes (history, timer, genomes, rate limit)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routes.genomes import _safe_under_root
from app.services.action_logger import ActionTimer
from app.services.rate_limit import SlidingWindowRateLimiter, is_loopback, require_admin


# ---------------------------------------------------------------------------
# History prior-turn handling (logic mirrored from run_agent_loop)
# ---------------------------------------------------------------------------

def _normalize_prior_history(history, user_message: str):
    """Same defensive drop used in legacy_core.run_agent_loop."""
    prior_history = list(history or [])
    if (
        prior_history
        and prior_history[-1].get("role") == "user"
        and (prior_history[-1].get("content") or "").strip() == (user_message or "").strip()
    ):
        prior_history = prior_history[:-1]
    return prior_history


def test_history_keeps_last_assistant_when_frontend_sends_prior_only():
    history = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1 about CsaV3"},
    ]
    prior = _normalize_prior_history(history, "Q2 follow-up")
    assert prior == history
    roles = [m["role"] for m in prior]
    assert "assistant" in roles


def test_history_drops_duplicate_current_user_from_legacy_caller():
    history = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]
    prior = _normalize_prior_history(history, "Q2")
    assert prior == history[:-1]
    assert prior[-1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# ActionTimer status sync
# ---------------------------------------------------------------------------

def test_action_timer_logs_caller_status(monkeypatch):
    logged = {}

    def fake_log_action(**kwargs):
        logged.update(kwargs)

    monkeypatch.setattr("app.services.action_logger.log_action", fake_log_action)

    with ActionTimer(module="gene", action="chat", gene_id="x") as timer:
        timer.status = "not_found"

    assert logged["status"] == "not_found"


def test_action_timer_error_overrides_status(monkeypatch):
    logged = {}

    def fake_log_action(**kwargs):
        logged.update(kwargs)

    monkeypatch.setattr("app.services.action_logger.log_action", fake_log_action)

    with pytest.raises(RuntimeError):
        with ActionTimer(module="gene", action="chat") as timer:
            timer.status = "not_found"
            raise RuntimeError("boom")

    assert logged["status"] == "error"
    assert "RuntimeError" in logged["error_msg"]


# ---------------------------------------------------------------------------
# Genome path sandbox
# ---------------------------------------------------------------------------

def test_safe_under_root_allows_nested(tmp_path: Path):
    root = tmp_path / "genomes"
    nested = root / "Cucumber" / "v3"
    nested.mkdir(parents=True)
    (nested / "file.fa").write_text("x")
    resolved = _safe_under_root(root, "Cucumber", "v3", "file.fa")
    assert resolved == (nested / "file.fa").resolve()


def test_safe_under_root_rejects_traversal(tmp_path: Path):
    root = tmp_path / "genomes"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    with pytest.raises(HTTPException) as ei:
        _safe_under_root(root, "..", "secret.txt")
    assert ei.value.status_code == 400


# ---------------------------------------------------------------------------
# Rate limiter + admin gate
# ---------------------------------------------------------------------------

def test_sliding_window_rate_limiter():
    lim = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    assert lim.allow("ip1") is True
    assert lim.allow("ip1") is True
    assert lim.allow("ip1") is False
    assert lim.allow("ip2") is True


def test_is_loopback():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    assert not is_loopback("8.8.8.8")


def test_require_admin_with_token(monkeypatch):
    monkeypatch.setattr("app.services.rate_limit.settings.admin_api_token", "secret")
    req = MagicMock()
    req.headers.get = lambda k, default=None: (
        "secret" if k == "X-Admin-Token" else None
    )
    req.client = MagicMock(host="8.8.8.8")
    require_admin(req)  # should not raise


def test_require_admin_rejects_bad_token(monkeypatch):
    monkeypatch.setattr("app.services.rate_limit.settings.admin_api_token", "secret")
    req = MagicMock()
    req.headers.get = lambda k, default=None: "wrong" if k == "X-Admin-Token" else None
    req.client = MagicMock(host="127.0.0.1")
    with pytest.raises(HTTPException) as ei:
        require_admin(req)
    assert ei.value.status_code == 401


def test_require_admin_loopback_when_no_token(monkeypatch):
    monkeypatch.setattr("app.services.rate_limit.settings.admin_api_token", "")
    req = MagicMock()
    req.headers.get = lambda k, default=None: None
    req.client = MagicMock(host="127.0.0.1")
    # client_ip reads X-Forwarded-For first; ensure none
    require_admin(req)


def test_require_admin_blocks_remote_when_no_token(monkeypatch):
    monkeypatch.setattr("app.services.rate_limit.settings.admin_api_token", "")
    req = MagicMock()
    req.headers.get = lambda k, default=None: "203.0.113.1" if k == "X-Forwarded-For" else None
    req.client = MagicMock(host="203.0.113.1")
    with pytest.raises(HTTPException) as ei:
        require_admin(req)
    assert ei.value.status_code == 403


def test_require_admin_ignores_spoofed_xff_loopback(monkeypatch):
    """Remote peer cannot become admin by forging X-Forwarded-For: 127.0.0.1."""
    monkeypatch.setattr("app.services.rate_limit.settings.admin_api_token", "")
    req = MagicMock()
    req.headers.get = lambda k, default=None: "127.0.0.1" if k == "X-Forwarded-For" else None
    req.client = MagicMock(host="203.0.113.9")
    with pytest.raises(HTTPException) as ei:
        require_admin(req)
    assert ei.value.status_code == 403


def test_client_ip_trusts_xff_from_loopback_peer():
    from app.services.rate_limit import client_ip

    req = MagicMock()
    req.headers.get = lambda k, default=None: (
        "203.0.113.50" if k == "X-Forwarded-For" else None
    )
    req.client = MagicMock(host="127.0.0.1")
    assert client_ip(req) == "203.0.113.50"


def test_client_ip_ignores_xff_from_untrusted_peer():
    from app.services.rate_limit import client_ip

    req = MagicMock()
    req.headers.get = lambda k, default=None: (
        "127.0.0.1" if k == "X-Forwarded-For" else None
    )
    req.client = MagicMock(host="203.0.113.9")
    assert client_ip(req) == "203.0.113.9"


def test_llm_daily_quota(tmp_path, monkeypatch):
    from app.services import rate_limit as rl

    monkeypatch.setattr(rl.settings, "visit_db_path", tmp_path / "quota.db")
    monkeypatch.setattr(rl.settings, "llm_rate_limit_per_day", 3)
    monkeypatch.setattr(rl.settings, "ip_hash_salt", "test-salt")

    assert rl.check_and_increment_llm_daily("1.2.3.4") == (True, 1, 3)
    assert rl.check_and_increment_llm_daily("1.2.3.4") == (True, 2, 3)
    assert rl.check_and_increment_llm_daily("1.2.3.4") == (True, 3, 3)
    assert rl.check_and_increment_llm_daily("1.2.3.4") == (False, 3, 3)
    # Different IP has its own bucket
    assert rl.check_and_increment_llm_daily("9.9.9.9") == (True, 1, 3)


# ---------------------------------------------------------------------------
# Tool-budget mid-batch (pure logic)
# ---------------------------------------------------------------------------

def test_tool_budget_mid_batch_cap():
    max_tool_calls = 2
    tool_calls_made = 0
    executed = []
    refused = []
    batch = ["a", "b", "c"]
    for name in batch:
        if tool_calls_made >= max_tool_calls:
            refused.append(name)
            continue
        executed.append(name)
        tool_calls_made += 1
    assert executed == ["a", "b"]
    assert refused == ["c"]
