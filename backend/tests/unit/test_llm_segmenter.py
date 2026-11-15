"""Unit tests for OpenAICueSegmenter (mocked openai client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import openai
import pytest

from cutfinder.adapters.llm_segmenter import OpenAICueSegmenter
from cutfinder.ports.speech import SegmenterUnavailable


def _config() -> MagicMock:
    config = MagicMock()
    config.env.OPENAI_BASE_URL = "http://localhost:8000/v1"
    config.env.OPENAI_API_KEY = "k"
    config.env.TEXT_MODEL = ""
    config.prefs.text_model = "Qwen-test"
    return config


def _patch_client(monkeypatch, content=None, error=None):
    client = MagicMock()
    if error is not None:
        client.chat.completions.create.side_effect = error
    else:
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = content
        client.chat.completions.create.return_value = resp
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(openai, "OpenAI", factory)
    return factory, client


_REQ = httpx.Request("POST", "http://localhost:8000/v1/chat/completions")


def test_request_shape(monkeypatch):
    factory, client = _patch_client(monkeypatch, "我们|回家")
    out = OpenAICueSegmenter(_config()).split("我们回家")
    assert out == "我们|回家"
    kw = factory.call_args.kwargs
    assert kw["timeout"] == 120.0 and kw["max_retries"] == 0
    ckw = client.chat.completions.create.call_args.kwargs
    assert ckw["model"] == "Qwen-test"
    assert ckw["temperature"] == 0
    assert ckw["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert ckw["max_tokens"] == 512
    assert "我们回家" in ckw["messages"][0]["content"]


def test_strips_think_block(monkeypatch):
    _patch_client(monkeypatch, "<think>x</think>\n我们|回家")
    assert OpenAICueSegmenter(_config()).split("我们回家") == "我们|回家"


def test_connection_error_raises_unavailable(monkeypatch):
    _patch_client(monkeypatch, error=openai.APIConnectionError(request=_REQ))
    with pytest.raises(SegmenterUnavailable):
        OpenAICueSegmenter(_config()).split("abc")


def test_timeout_raises_unavailable(monkeypatch):
    _patch_client(monkeypatch, error=openai.APITimeoutError(request=_REQ))
    with pytest.raises(SegmenterUnavailable):
        OpenAICueSegmenter(_config()).split("abc")


def test_other_error_returns_none(monkeypatch):
    _patch_client(monkeypatch, error=RuntimeError("boom"))
    assert OpenAICueSegmenter(_config()).split("abc") is None


@pytest.mark.parametrize("content", [None, "", "  <think>x</think> \n"])
def test_empty_content_returns_none(monkeypatch, content):
    _patch_client(monkeypatch, content)
    assert OpenAICueSegmenter(_config()).split("abc") is None
