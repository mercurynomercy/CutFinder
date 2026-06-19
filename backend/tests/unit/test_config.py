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


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test hermetic from the developer's real machine config.

    ``resolve_env`` now reads ``~/.cutfinder/config.json`` and the repo-root
    ``.env``; redirect both so tests aren't polluted by local state.
    """
    import cutfinder.config as cfg

    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG_FILE", tmp_path / "global-config.json")
    monkeypatch.setattr(cfg, "_read_dotenv", dict)


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

    def test_missing_vars_default_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing OMLX vars no longer raise — they default to empty strings.

        Creds are now optional at load time and filled via the UI / global
        store; adapters surface a clear error only if used while unset.
        """
        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)

        # _env_file=None isolates the unit test from the repo-root .env, which
        # EnvSettings otherwise always loads (see config._ROOT_ENV_FILE).
        env = EnvSettings(_env_file=None)
        assert env.OMLX_BASE_URL == ""
        assert env.OMLX_API_KEY == ""


# ── Global settings store (~/.cutfinder/config.json) ─────────────────


class TestGlobalSettings:
    """Machine-global store + env→global layering via resolve_env."""

    @pytest.fixture()
    def global_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        """Redirect the global config file into a temp dir."""
        import cutfinder.config as cfg

        target = tmp_path / ".cutfinder" / "config.json"
        monkeypatch.setattr(cfg, "_GLOBAL_CONFIG_FILE", target)
        # Isolate from the real repo-root .env so env-vs-global precedence is
        # driven only by what each test sets.
        monkeypatch.setattr(cfg, "_read_dotenv", dict)
        return target

    def test_save_then_load_round_trip(self, global_file: Path) -> None:
        """save_global_settings persists only recognised keys; load reads them."""
        from cutfinder.config import load_global_settings, save_global_settings

        save_global_settings(
            {"OMLX_BASE_URL": "http://x/v1", "OMLX_API_KEY": "k", "bogus": "no"}
        )

        loaded = load_global_settings()
        assert loaded == {"OMLX_BASE_URL": "http://x/v1", "OMLX_API_KEY": "k"}

    def test_save_merges_without_clobbering(self, global_file: Path) -> None:
        """A second partial save preserves previously stored keys."""
        from cutfinder.config import load_global_settings, save_global_settings

        save_global_settings({"OMLX_BASE_URL": "http://x/v1", "OMLX_API_KEY": "k"})
        save_global_settings({"OMLX_BASE_URL": "http://y/v1"})

        loaded = load_global_settings()
        assert loaded["OMLX_BASE_URL"] == "http://y/v1"
        assert loaded["OMLX_API_KEY"] == "k"

    def test_load_missing_file_returns_empty(self, global_file: Path) -> None:
        """No file yet → empty dict, not an error."""
        from cutfinder.config import load_global_settings

        assert load_global_settings() == {}

    def test_resolve_env_falls_back_to_global(
        self, global_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty env values are filled from the global store."""
        from cutfinder.config import resolve_env, save_global_settings

        monkeypatch.delenv("OMLX_BASE_URL", raising=False)
        monkeypatch.delenv("OMLX_API_KEY", raising=False)
        save_global_settings(
            {"OMLX_BASE_URL": "http://global/v1", "OMLX_API_KEY": "global-key"}
        )

        env = resolve_env()
        assert env.OMLX_BASE_URL == "http://global/v1"
        assert env.OMLX_API_KEY == "global-key"

    def test_resolve_env_prefers_global_over_env(
        self, global_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Settings UI (global store) is authoritative over env vars.

        ``make dev`` exports ``.env`` into the environment, so a stale env var
        must not shadow what the user saved in the UI.
        """
        from cutfinder.config import resolve_env, save_global_settings

        monkeypatch.setenv("OMLX_BASE_URL", "http://env/v1")
        monkeypatch.setenv("OMLX_API_KEY", "env-key")
        save_global_settings(
            {"OMLX_BASE_URL": "http://global/v1", "OMLX_API_KEY": "global-key"}
        )

        env = resolve_env()
        assert env.OMLX_BASE_URL == "http://global/v1"
        assert env.OMLX_API_KEY == "global-key"


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
        assert prefs.broll_frame_count == 5
        assert prefs.vad_threshold == 0.35
        assert prefs.vocal_separation is False

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

    def test_blank_model_falls_back_to_default(self) -> None:
        """Empty/whitespace model names fall back to their defaults."""
        prefs = Prefs(
            library_path="/tmp/lib",
            text_model="",
            vision_model="   ",
            whisper_model="custom-whisper",
        )

        assert prefs.text_model == "Qwen3.6-35B-A3B"
        assert prefs.vision_model == "Qwen3-VL-8B"
        assert prefs.whisper_model == "custom-whisper"

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
        assert config.prefs.broll_frame_count == 5


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
            vocal_separation=True,
        )

        save_prefs(prefs, tmp_library.parent)

        # Read back via load_config
        config = load_config(tmp_library.parent)

        assert config.prefs.library_path == prefs.library_path
        assert config.prefs.source_folders == prefs.source_folders
        assert config.prefs.broll_frame_count == 4
        assert config.prefs.vad_threshold == 0.25
        assert config.prefs.vocal_separation is True

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
