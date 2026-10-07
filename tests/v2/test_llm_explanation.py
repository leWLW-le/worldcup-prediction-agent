import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from app.explanation.llm import generate_explanation


def test_generation_cached_and_numbers_unchanged(tmp_path, monkeypatch):
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "德国是模型看好的争冠热门，但优势并不意味着必胜。晋级各轮仍有不确定性，其他球队同样拥有夺冠机会。"}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr("app.explanation.llm.httpx.post", post)
    settings = SimpleNamespace(LLM_MODEL="test", LLM_API_KEY="test", LLM_BASE_URL="https://example.com", LLM_MAX_DAILY_CALLS=10)
    store = Mock()
    generated = generate_explanation(result, settings, store)
    assert generated["source"] == "llm"
    assert generated["champion_probability"] == result["champion_probability"]
    assert generate_explanation(result, settings, store) == generated
    assert post.call_count == store.consume_budget.call_count == 1


def test_failed_call_is_explicit_fallback(tmp_path, monkeypatch):
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.explanation.llm.httpx.post", Mock(side_effect=httpx.ConnectError("secret must not leak")))
    settings = SimpleNamespace(LLM_MODEL="test", LLM_API_KEY="test", LLM_BASE_URL="https://example.com", LLM_MAX_DAILY_CALLS=10)
    explanation = generate_explanation(result, settings, Mock())
    assert explanation["source"] == "template"
    assert explanation["fallback_reason"]
    assert "secret" not in str(explanation)
