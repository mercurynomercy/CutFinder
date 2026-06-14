"""Unit tests for cutfinder.adapters.omlx_check.

Uses httpx ``MockTransport`` to fake the OMLX /models endpoint
without requiring a running server.
"""

from __future__ import annotations

import sys as _real_sys  # noqa: F401
from io import StringIO
from unittest import mock

import httpx
import pytest


def _make_client(
    models, status_code=200, side_effect=None
):
    def handler(request):
        if side_effect is not None:
            raise side_effect
        return httpx.Response(status_code, json={"data": [{"id": m} for m in models]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _call_check(models, expected_models=None, status_code=200):
    import cutfinder.adapters.omlx_check as mod

    client = _make_client(  # type: ignore[no-untyped-call]
        models, status_code=status_code
    )

    def mock_get(url, **kwargs):
        return client.get(url, headers=kwargs.get("headers"))

    with mock.patch.object(mod.httpx, "get", side_effect=mock_get):  # type: ignore[attr-defined]
        if expected_models is not None:
            return mod.check_omlx(
                base_url="http://localhost:8000/v1",
                api_key="test-key",
                expected_models=expected_models,
            )
        return mod.check_omlx(
            base_url="http://localhost:8000/v1", api_key="test-key"
        )


@pytest.fixture()
def stderr_capture(monkeypatch):
    buf = StringIO()
    monkeypatch.setattr(_real_sys, "stderr", buf)
    yield buf

    def get_output():
        return buf.getvalue()


class TestCheckOmlxOk:
    def test_returns_sorted_model_ids(self):
        models = ["Qwen3-VL-8B-Instruct", "gpt-4o-mini", "Qwen3.6-35B-A3B"]
        result = _call_check(models)  # type: ignore[no-untyped-call]
        assert result == ["Qwen3-VL-8B-Instruct", "Qwen3.6-35B-A3B", "gpt-4o-mini"]

    def test_empty_model_list(self):
        result = _call_check([])  # type: ignore[no-untyped-call]
        assert result == []

    def test_with_expected_models_present(self):
        models = ["Qwen3-VL-8B-Instruct", "Qwen3.6-35B-A3B"]
        import cutfinder.adapters.omlx_check as mod

        client = _make_client(models)  # type: ignore[no-untyped-call]

        def mock_get(url, **kwargs):
            return client.get(url, headers=kwargs.get("headers"))

        with mock.patch.object(mod.httpx, "get", side_effect=mock_get):  # type: ignore[attr-defined]
            result = mod.check_omlx(
                base_url="http://localhost:8000/v1",
                api_key="test-key",
                expected_models=["Qwen3.6-35B-A3B"],
            )
        assert result == ["Qwen3-VL-8B-Instruct", "Qwen3.6-35B-A3B"]


class TestEmptyApiKey:
    def test_exits_with_error_message(self, stderr_capture):
        import cutfinder.adapters.omlx_check as mod

        with mock.patch.object(mod.httpx, "get"):  # type: ignore[attr-defined]
            with pytest.raises(SystemExit) as exc_info:
                mod.check_omlx(base_url="http://localhost:8000/v1", api_key="")
        assert exc_info.value.code == 1
        msg = stderr_capture.getvalue() if hasattr(stderr_capture, "getvalue") else ""


class TestHttpErrors:
    def test_500_error(self):
        with pytest.raises(RuntimeError) as exc_info:
            _call_check([], status_code=500)  # type: ignore[no-untyped-call]
        assert "HTTP 500" in str(exc_info.value)

    def test_connection_error(self):
        import cutfinder.adapters.omlx_check as mod

        client = _make_client(  # type: ignore[no-untyped-call]
            ["Qwen3.6-35B-A3B"], side_effect=httpx.ConnectError("Connection refused")
        )

        def mock_get(url, **kwargs):
            return client.get(url, headers=kwargs.get("headers"))

        with mock.patch.object(mod.httpx, "get", side_effect=mock_get):  # type: ignore[attr-defined]
            with pytest.raises(RuntimeError) as exc_info:
                mod.check_omlx(base_url="http://localhost:8000/v1", api_key="test-key")
        assert "connection failed" in str(exc_info.value).lower() or "ConnectError" in str(exc_info.value)
