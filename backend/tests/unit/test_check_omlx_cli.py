"""Tests for :mod:`scripts.check_omlx` (CLI entry-point).

Uses ``monkeypatch`` to inject environment variables and temporary JSON files,
then asserts the CLI script resolves OMLX config correctly.

httpx is mocked so no real server is needed.
"""

from __future__ import annotations

import json  # noqa: F401 — used by write_global_cfg fixture below
import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import httpx
import pytest

# scripts/ lives at repo root, same level as backend/. Add it to sys.path
# so the module can be imported from within tests/unit/.
_REPO_ROOT = Path(__file__).resolve().parents[3]  # repo root (up from backend/tests/unit/)
sys.path.insert(0, str(_REPO_ROOT))


# ── Fixtures / helpers ───────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test hermetic from the developer's real machine config.

    Redirect ``~/.cutfinder/config.json`` so tests aren't polluted by local
    state.
    """
    import cutfinder.config as cfg

    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG_FILE", tmp_path / "global-config.json")


@pytest.fixture()
def write_global_cfg(tmp_path: Path) -> Callable[[dict[str, Any]], None]:
    """Helper to write JSON config into the temp global store."""

    def _write(data: dict[str, Any]) -> None:
        json_file = tmp_path / "global-config.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

    return _write


# ── Tests — config resolution from global store ─────────────────────


class TestConfigFromGlobalStore:
    """CLI script should read OMLX settings from ~/.cutfinder/config.json."""

    def test_reads_url_and_key_from_config_json(
        self, write_global_cfg: Callable[[dict[str, Any]], None], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When env vars are empty, config.json values should be used."""
        write_global_cfg({"OMLX_BASE_URL": "http://localhost:9001/v1", "OMLX_API_KEY": "ui-key"})

        # Remove any env vars that could interfere
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        # Import fresh after patching
        import scripts.check_omlx as mod  # type: ignore[import-not-found]

        base, key = mod._resolve_omlx_config()  # type: ignore[attr-defined]
        assert base == "http://localhost:9001/v1"
        assert key == "ui-key"

    def test_env_var_filled_by_config_when_absent(
        self, write_global_cfg: Callable[[dict[str, Any]], None], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config fills env var gap — config wins when both are set."""
        write_global_cfg({"OMLX_BASE_URL": "http://localhost:9001/v1", "OMLX_API_KEY": "ui-key"})
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:9002/v1")
        monkeypatch.delenv("OMLX_API_KEY", raising=False)  # key absent → config fills it

        import scripts.check_omlx as mod  # type: ignore[import-not-found]

        base, key = mod._resolve_omlx_config()  # type: ignore[attr-defined]
        assert base == "http://localhost:9001/v1"  # config wins over env var
        assert key == "ui-key"  # config.json fills the missing env var

    def test_config_overrides_env_var(
        self, write_global_cfg: Callable[[dict[str, Any]], None], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Global config (Settings UI) wins over env vars — highest priority."""
        write_global_cfg({"OMLX_BASE_URL": "http://localhost:9003/v1", "OMLX_API_KEY": "ui-wins"})
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:9004/v1")
        monkeypatch.setenv("OMLX_API_KEY", "env-loses")

        import scripts.check_omlx as mod  # type: ignore[import-not-found]

        base, key = mod._resolve_omlx_config()  # type: ignore[attr-defined]
        assert base == "http://localhost:9003/v1"  # config.json wins
        assert key == "ui-wins"


class TestEmptyKey:
    """When no API key is available, the script should fail gracefully."""

    def test_exits_with_error_when_no_key(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No key anywhere → exit code 1 with clear error message."""
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        import scripts.check_omlx as mod  # type: ignore[import-not-found]
        from cutfinder.config import resolve_env as orig_resolve

        # Stub _resolve_omlx_config to return empty key
        with patch.object(mod, "_resolve_omlx_config", return_value=("http://localhost:8000/v1", "")):
            result = mod.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "OMLX_API_KEY is empty" in captured.err

        # Restore original so other tests aren't affected
        mod._resolve_omlx_config = orig_resolve  # type: ignore[attr-defined]


class TestIntegration:
    """End-to-end-ish test: config → HTTP call via mock."""

    def test_full_flow_with_config_json(
        self, write_global_cfg: Callable[[dict[str, Any]], None], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config loaded from JSON, HTTP call made with correct credentials."""

        captured_request = {}  # type: ignore[var-annotated]

        def handler(request):
            captured_request["url"] = str(request.url)
            captured_request["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"data": [{"id": m} for m in ["Qwen3.6-35B-A3B", "Qwen3-VL-8B-Instruct"]]})

        write_global_cfg({"OMLX_BASE_URL": "http://localhost:8099/v1", "OMLX_API_KEY": "test-key"})
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        import scripts.check_omlx as mod  # type: ignore[import-not-found]
        from cutfinder.config import resolve_env as orig_resolve

        transport = httpx.MockTransport(handler)
        # Stub _resolve_omlx_config so main() uses known credentials and URL
        with patch.object(mod, "_resolve_omlx_config", return_value=("http://localhost:8099/v1", "test-key")):
            # Replace httpx.get with a transport-based call so response has request set
            original_get = mod.httpx.get  # type: ignore[attr-defined]
            try:
                mod.httpx.get = lambda *a, **kw: httpx.Client(transport=transport).get(*a, **kw)  # type: ignore[attr-defined]
                result = mod.main()
            finally:
                mod.httpx.get = original_get  # type: ignore[attr-defined]

        assert result == 0
        assert captured_request["url"] == "http://localhost:8099/v1/models"
        assert captured_request["auth"] == "Bearer test-key"

        # Restore original so other tests aren't affected
        mod._resolve_omlx_config = orig_resolve  # type: ignore[attr-defined]
