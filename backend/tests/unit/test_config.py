"""Tests for :mod:`cutfinder.config`.

Uses ``monkeypatch`` to inject environment variables and temporary JSON files,
then asserts the merged result matches expected defaults.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from cutfinder.config import (
    AppConfig,
    EnvSettings,
    Prefs,
    load_config,
    save_prefs,
)


# ── Fixtures / helpers ───────────────────────────────────────────────


@pytest.fixture()
def tmp_library(tmp_path: Path) -> Path:
    """Return ``<tmp>/.cutfinder`` so the config directory already exists."""
    return tmp_path / ".cutfinder"


@pytest.fixture()
def write_config_json(tmp_library: Path) -> Callable[[dict[str, Any]], None]:
    """Helper to write JSON config into the temp library."""

    def _write(data: dict[str, Any]) -> Path:
        json_file = tmp_library / "config.json"
        json_file.parent.mkdir(parents=True, exist_ok=True)
        json_file.write_text(json.dumps(data), encoding="utf-8")
        return json_file

    return _write


# ── EnvSettings tests ────────────────────────────────────────────────


class TestEnvSettings:
    """Environment variable loading and validation."""

    def test_load_with_all_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All required env vars present → EnvSettings loads successfully."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMLX_API_KEY", "test-key-123")

        env = EnvSettings()
        assert env.OMLX_BASE_URL == "http://localhost:8000/v1"
        assert env.OMLX_API_KEY == "test-key-123"

    def test_missing_base_url_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OMLX_BASE_URL absent → ValueError with clear message."""
        monkeypatch.setenv("OMLX_API_KEY", "test-key-123")
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: OMLX_BASE_URL"):
            EnvSettings()

    def test_missing_api_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OMLX_API_KEY absent → ValueError with clear message."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: OMLX_API_KEY"):
            EnvSettings()

    def test_missing_both_keys_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both missing → ValueError lists both names."""
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: OMLX_BASE_URL, OMLX_API_KEY"):
            EnvSettings()

    def test_empty_string_treated_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string value is treated as missing by pydantic-settings."""
        monkeypatch.setenv("OMLX_BASE_URL", "")
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        with pytest.raises(ValueError):
            EnvSettings()


# ── Prefs tests ──────────────────────────────────────────────────────


class TestPrefs:
    """Default values and serialisation of Prefs."""

    def test_defaults(self) -> None:
        """Prefs without input uses all default values."""
        prefs = Prefs(library_path="/Users/john/Library/CutFinder")

        assert prefs.source_folders == []
        assert prefs.text_model == "Qwen3.6-35B-A3B"
        assert prefs.vision_model == "Qwen3-VL-8B"
        assert prefs.whisper_model == "mlx-community/whisper-large-v3-mlx"
        assert prefs.extensions == [".mov", ".mp4", ".m4v"]
        assert prefs.broll_frame_count == 3
        assert prefs.vad_threshold == 0.15

    def test_custom_values(self) -> None:
        """Prefs accepts custom values and overrides defaults."""
        prefs = Prefs(
            library_path="/tmp/lib",
            source_folders=["/Volumes/DSC01"],
            text_model="custom-model",
            broll_frame_count=5,
            vad_threshold=0.2,
        )

        assert prefs.source_folders == ["/Volumes/DSC01"]
        assert prefs.text_model == "custom-model"
        assert prefs.broll_frame_count == 5
        assert prefs.vad_threshold == 0.2

    def test_serialisation_round_trip(self) -> None:
        """Prefs serialises to dict and back without loss."""
        prefs = Prefs(
            library_path="/tmp/lib",
            source_folders=["/data"],
            broll_frame_count=7,
        )

        dumped = prefs.model_dump()
        restored = Prefs(**dumped)

        assert restored == prefs


# ── load_config tests ────────────────────────────────────────────────


class TestLoadConfig:
    """Merged AppConfig from env vars + JSON prefs."""

    def test_merged_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_library: Path,
        write_config_json: Callable[[dict[str, Any]], None],
    ) -> None:
        """Env vars + JSON are merged into AppConfig with correct values."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8001/v1")
        monkeypatch.setenv("OMLX_API_KEY", "key-from-env")

        write_config_json({
            "library_path": "/tmp/test-lib",
            "source_folders": ["/data/photos"],
            "broll_frame_count": 5,
        })

        config = load_config(tmp_library.parent)

        assert isinstance(config, AppConfig)
        assert config.env.OMLX_BASE_URL == "http://localhost:8001/v1"
        assert config.env.OMLX_API_KEY == "key-from-env"

        # JSON values override defaults
        assert config.prefs.library_path == "/tmp/test-lib"
        assert config.prefs.source_folders == ["/data/photos"]
        assert config.prefs.broll_frame_count == 5

        # Defaults preserved for fields not in JSON
        assert config.prefs.vision_model == "Qwen3-VL-8B"
        assert config.prefs.extensions == [".mov", ".mp4", ".m4v"]

    def test_missing_library_path_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_library: Path,
    ) -> None:
        """JSON without library_path → ValueError."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMLX_API_KEY", "test-key")

        tmp_library.mkdir(parents=True, exist_ok=True)
        json_file = tmp_library / "config.json"
        json_file.write_text(json.dumps({"source_folders": ["/data"]}), encoding="utf-8")

        with pytest.raises(ValueError, match="'library_path'"):
            load_config(tmp_library.parent)

    def test_no_json_file_uses_defaults(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_library: Path,
    ) -> None:
        """No JSON file → Prefs uses defaults (except mandatory library_path)."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMLX_API_KEY", "test-key")

        # Write JSON with only the mandatory field
        tmp_library.mkdir(parents=True, exist_ok=True)
        json_file = tmp_library / "config.json"
        json_file.write_text(
            json.dumps({"library_path": "/tmp/lib"}), encoding="utf-8"
        )

        config = load_config(tmp_library.parent)
        assert config.prefs.source_folders == []
        assert config.prefs.broll_frame_count == 3


# ── save_prefs tests (round-trip) ────────────────────────────────────


class TestSavePrefs:
    """save_prefs writes JSON that load_config can read back identically."""

    def test_round_trip(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_library: Path,
    ) -> None:
        """save_prefs → load_config produces identical Prefs values."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMLX_API_KEY", "round-trip-key")

        prefs = Prefs(
            library_path="/tmp/rt-lib",
            source_folders=["/data/a", "/data/b"],
            broll_frame_count=4,
            vad_threshold=0.25,
        )

        save_prefs(prefs, tmp_library.parent)

        # Read back via load_config
        config = load_config(tmp_library.parent)

        assert config.prefs.library_path == prefs.library_path
        assert config.prefs.source_folders == prefs.source_folders
        assert config.prefs.broll_frame_count == 4
        assert config.prefs.vad_threshold == 0.25

    def test_round_trip_preserves_defaults(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_library: Path,
    ) -> None:
        """Fields not explicitly set are preserved as defaults after round-trip."""
        monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.setenv("OMLX_API_KEY", "preserves-defaults-key")

        prefs = Prefs(library_path="/tmp/pres-lib")
        save_prefs(prefs, tmp_library.parent)

        config = load_config(tmp_library.parent)
        assert config.prefs.extensions == [".mov", ".mp4", ".m4v"]
        assert config.prefs.text_model == "Qwen3.6-35B-A3B"
        assert config.prefs.vision_model == "Qwen3-VL-8B"

    def test_save_prefs_empty_library_path_raises(
        self, monkeypatch: pytest.MonkeyPatch  # noqa: ARG002 — name used by convention
    ) -> None:
        """save_prefs with empty library_path → ValueError."""
        prefs = Prefs(library_path="")

        with pytest.raises(ValueError, match="'library_path' is empty"):
            save_prefs(prefs, "/tmp/lib")
