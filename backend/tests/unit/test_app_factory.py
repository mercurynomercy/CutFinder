"""Tests for :func:`cutfinder.api.app.create_app` — the real DI assembly.

These guard the wiring layer that ``test_api`` does *not* cover (it tests
``_build_router`` with fakes).  Because ``create_app`` imports and constructs
the real adapters directly (no broad ``try/except``), a wrong import path or
constructor signature makes ``create_app`` raise immediately — so simply
building the app with a library is a strong regression check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cutfinder.api.app import create_app


@pytest.fixture
def omlx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the OMLX env vars EnvSettings requires (no network used)."""
    monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("OMLX_API_KEY", "test-key")


def test_create_app_no_library_returns_503_for_catalog() -> None:
    """With no library, catalog routes are mounted but report 503."""
    client = TestClient(create_app(None))
    assert client.get("/api/clips").status_code == 503


def test_create_app_with_library_wires_repository(
    tmp_path: Path, omlx_env: None
) -> None:
    """A real library path wires the SQLite repository (clips → 200)."""
    client = TestClient(create_app(tmp_path))

    assert client.get("/api/clips").status_code == 200

    # Repository + config bootstrapped on disk.
    assert (tmp_path / ".cutfinder" / "catalog.sqlite").is_file()
    assert (tmp_path / ".cutfinder" / "config.json").is_file()


def test_create_app_with_library_serves_settings(
    tmp_path: Path, omlx_env: None
) -> None:
    """Settings GET returns the full prefs contract; PUT validates + persists."""
    client = TestClient(create_app(tmp_path))

    resp = client.get("/api/settings")
    assert resp.status_code == 200
    prefs = resp.json()["prefs"]
    assert set(prefs) == {
        "source_folders",
        "library_path",
        "text_model",
        "vision_model",
        "whisper_model",
        "extensions",
        "broll_frame_count",
        "vad_threshold",
        "output_language",
    }
    # The OMLX secret is masked, never returned in the clear.
    assert resp.json()["env"]["OMLX_API_KEY"] == "***MASKED***"

    # Valid update persists; invalid value is rejected with 422.
    assert client.put("/api/settings", json={"broll_frame_count": 4}).status_code == 200
    assert client.get("/api/settings").json()["prefs"]["broll_frame_count"] == 4
    assert client.put("/api/settings", json={"vad_threshold": 9}).status_code == 422


def test_create_app_with_library_starts_worker(tmp_path: Path, omlx_env: None) -> None:
    """The full app (with library) starts/stops its worker queue cleanly.

    Using TestClient as a context manager fires startup/shutdown events; this
    exercises that the orchestrator + worker were assembled without error.
    """
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/clips").status_code == 200
