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


def test_create_app_no_library_returns_503_for_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no library, catalog routes are mounted but report 503."""
    monkeypatch.delenv("CUTFINDER_LIBRARY", raising=False)
    monkeypatch.setattr("cutfinder.api.app._load_persisted_library", lambda: None)
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
        "keyframe_count",
        "keyframe_auto",
        "vocal_separation",
    }
    # The OMLX secret is masked, never returned in the clear.
    assert resp.json()["env"]["OMLX_API_KEY"] == "***MASKED***"

    # Off by default.
    assert prefs["vocal_separation"] is False

    # Valid update persists; invalid value is rejected with 422.
    assert client.put("/api/settings", json={"broll_frame_count": 4}).status_code == 200
    assert client.get("/api/settings").json()["prefs"]["broll_frame_count"] == 4
    assert client.put("/api/settings", json={"vad_threshold": 9}).status_code == 422

    # The vocal_separation toggle persists through PUT and is read back via GET.
    assert client.put("/api/settings", json={"vocal_separation": True}).status_code == 200
    assert client.get("/api/settings").json()["prefs"]["vocal_separation"] is True


def test_create_app_with_library_starts_worker(tmp_path: Path, omlx_env: None) -> None:
    """The full app (with library) starts/stops its worker queue cleanly.

    Using TestClient as a context manager fires startup/shutdown events; this
    exercises that the orchestrator + worker were assembled without error.
    """
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/clips").status_code == 200


def test_vocal_separator_wiring(tmp_path: Path, omlx_env: None) -> None:
    """Subtitle export always gets a separator; the pipeline only when on.

    Builds the real adapter graph via ``_build_into`` and introspects each
    ``MlxWhisperTranscriber._separator``.
    """
    from cutfinder.api.app import LibraryContext, _build_into
    from cutfinder.config import Prefs, load_config, save_prefs

    # Default (vocal_separation off): pipeline transcriber has no separator,
    # subtitle exporter always does.
    ctx = LibraryContext()
    _build_into(ctx, tmp_path)
    assert ctx.orchestrator.transcriber._separator is None
    assert ctx.worker_queue._subtitle_exporter._transcriber._separator is not None

    # Turn the pref on, rebuild: pipeline transcriber now has a separator too.
    prefs = load_config(tmp_path).prefs
    save_prefs(Prefs(**{**prefs.model_dump(), "vocal_separation": True}), tmp_path)
    ctx2 = LibraryContext()
    _build_into(ctx2, tmp_path)
    assert ctx2.orchestrator.transcriber._separator is not None
    assert ctx2.worker_queue._subtitle_exporter._transcriber._separator is not None


def test_set_library_binds_at_runtime(
    tmp_path: Path, omlx_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/library binds a library at runtime without restart."""
    monkeypatch.delenv("CUTFINDER_LIBRARY", raising=False)
    monkeypatch.setattr("cutfinder.api.app._load_persisted_library", lambda: None)
    # Don't write to ~/.cutfinder during tests.
    monkeypatch.setattr("cutfinder.api.app._persist_library", lambda _p: None)

    with TestClient(create_app(None)) as client:
        assert client.get("/api/clips").status_code == 503
        assert client.get("/api/library").json() == {"library_path": None}

        resp = client.post("/api/library", json={"path": str(tmp_path)})
        assert resp.status_code == 200

        # Now bound — catalog + settings work, and the path is reported back.
        assert client.get("/api/clips").status_code == 200
        assert client.get("/api/settings").status_code == 200
        assert client.get("/api/library").json()["library_path"] == str(tmp_path.resolve())

        # Missing path → 422.
        assert client.post("/api/library", json={}).status_code == 422
