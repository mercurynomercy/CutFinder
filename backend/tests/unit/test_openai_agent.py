"""Unit tests for OpenAIAgentClient — the OpenAI SDK client is faked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from cutfinder.adapters.openai_agent import OpenAIAgentClient

# What the SDK hands back when the server answers HTTP 200 with an error body
# (OMLX does this for a long request whose tool call was cut off by max_tokens:
# the keepalive already committed the 200, so the error arrives as JSON).
_ERROR_BODY = SimpleNamespace(
    choices=None,
    error={"message": "Model output contains an unrecoverable tool call.",
           "code": "incomplete_tool_call"},
)


def _client(monkeypatch: pytest.MonkeyPatch, response: Any) -> tuple[OpenAIAgentClient, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return response

    fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("openai.OpenAI", lambda **_kw: fake_sdk)
    config = SimpleNamespace(
        env=SimpleNamespace(OPENAI_BASE_URL="http://x/v1", OPENAI_API_KEY="k", TEXT_MODEL="m"),
    )
    return OpenAIAgentClient(config), calls  # type: ignore[arg-type]


def test_run_raises_server_error_when_response_has_no_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, calls = _client(monkeypatch, _ERROR_BODY)
    with pytest.raises(RuntimeError, match="incomplete_tool_call"):
        client.run([{"role": "user", "content": "hi"}], [])
    assert len(calls) == 1  # a truncated tool call isn't worth re-generating


def test_complete_raises_server_error_when_response_has_no_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _calls = _client(monkeypatch, _ERROR_BODY)
    with pytest.raises(RuntimeError, match="incomplete_tool_call"):
        client.complete([{"role": "user", "content": "hi"}])
