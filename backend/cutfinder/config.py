"""Configuration loading: .env (OMLX) + JSON (user prefs), merged into AppConfig.

All classes are frozen Pydantic ``BaseModel`` instances so they are
immutable, hashable (where useful), and serialisable to JSON.

Required fields that are missing from both env vars and the JSON file
raise a clear ``ValueError`` at load time.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# EnvSettings — secrets and endpoints from .env / environment variables
# ---------------------------------------------------------------------------

# Keys that live in the machine-global store / environment (not per-library).
_GLOBAL_KEYS = ("OMLX_BASE_URL", "OMLX_API_KEY", "WHISPER_MODEL_PATH")

# Repo root, anchored to this file (backend/cutfinder/config.py -> repo root).
# Used so the root ``.env`` is found even when the process runs from backend/.
_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Machine-global settings written by the UI. These are shared across all
# libraries (OMLX endpoint/key, whisper model path are machine-wide, not
# per-library) and let the app run with no ``.env`` at all.
_GLOBAL_CONFIG_FILE = Path.home() / ".cutfinder" / "config.json"


class EnvSettings(BaseSettings):
    """OMLX endpoint/key + whisper model path.

    Resolved by :func:`resolve_env` with precedence ``OS env / .env`` >
    ``~/.cutfinder/config.json`` (written by the UI) > empty. Missing values
    are allowed: the app starts unconfigured and the user fills them in via
    the Settings UI; adapters surface a clear connection error if used while
    still empty.
    """

    model_config = SettingsConfigDict(
        # Both the repo-root .env (the documented location) and a CWD-local
        # .env are honoured; the latter wins for overlapping keys.
        env_file=(_ROOT_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
    )

    OMLX_BASE_URL: str = Field(
        default="",
        description="Base URL for the local OMLX server.",
    )
    OMLX_API_KEY: str = Field(
        default="",
        description="API key for authenticating with the OMLX server.",
    )
    WHISPER_MODEL_PATH: str = Field(
        default="",
        description=(
            "Optional local directory holding the mlx-whisper model. When set "
            "(and present on disk), it is loaded from here instead of being "
            "downloaded into the HuggingFace cache. Overrides the whisper_model "
            "preference."
        ),
    )


# ── Machine-global settings (UI-editable, no .env required) ──────────


def load_global_settings() -> dict[str, str]:
    """Read the machine-global settings from ``~/.cutfinder/config.json``.

    Returns only the recognised :data:`_GLOBAL_KEYS` with truthy values; a
    missing or unreadable file yields an empty dict.
    """
    if not _GLOBAL_CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(_GLOBAL_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: str(data[k]) for k in _GLOBAL_KEYS if data.get(k)}


def save_global_settings(updates: dict[str, str]) -> None:
    """Merge *updates* into ``~/.cutfinder/config.json`` (creating it if needed).

    Only recognised :data:`_GLOBAL_KEYS` are persisted; other keys are ignored.
    """
    current = load_global_settings()
    current.update({k: v for k, v in updates.items() if k in _GLOBAL_KEYS})
    _GLOBAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GLOBAL_CONFIG_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_dotenv() -> dict[str, str]:
    """Return recognised keys from the ``.env`` file(s) — bootstrap defaults.

    These are the *lowest* priority layer: values saved through the Settings
    UI (the global store) override them so UI edits actually take effect.
    """
    values: dict[str, str | None] = {}
    for env_file in (_ROOT_ENV_FILE, Path(".env")):
        try:
            if env_file.is_file():
                values.update(dotenv_values(env_file))
        except OSError:
            continue
    return {k: v for k, v in values.items() if k in _GLOBAL_KEYS and v}


def resolve_env() -> EnvSettings:
    """Resolve OMLX/whisper config, layering all sources.

    Precedence (highest wins): ``~/.cutfinder/config.json`` (Settings UI) >
    OS environment variable > ``.env`` file > empty.

    The Settings UI is authoritative — values saved there always take effect,
    even when a stale ``.env`` sets the same key (note ``make dev`` exports
    ``.env`` into the environment, so env vars and ``.env`` are effectively the
    same fallback layer). Env / ``.env`` only fill keys the UI hasn't set.
    """
    layered: dict[str, str] = {}
    layered.update(_read_dotenv())
    layered.update({k: os.environ[k] for k in _GLOBAL_KEYS if os.environ.get(k)})
    layered.update(load_global_settings())
    # _env_file=None: the .env is layered above by hand, not by pydantic's own
    # reader (which would otherwise outrank the global store).
    return EnvSettings(_env_file=None, **layered)


# ---------------------------------------------------------------------------
# Prefs — user preferences stored in <library>/.cutfinder/config.json
# ---------------------------------------------------------------------------

_DEFAULT_EXTENSIONS: list[str] = [".mov", ".mp4", ".m4v"]
_DEFAULT_TEXT_MODEL: str = "Qwen3.6-35B-A3B"
_DEFAULT_VISION_MODEL: str = "Qwen3-VL-8B"
_DEFAULT_WHISPER_MODEL: str = "mlx-community/whisper-large-v3-mlx"


class Prefs(BaseModel, frozen=True):
    """User preferences for the library.

    Written to and read from ``<library>/.cutfinder/config.json`` by
    :func:`save_prefs` and :func:`load_config`.
    """

    source_folders: list[str] = []
    library_path: str = ""
    text_model: str = _DEFAULT_TEXT_MODEL
    vision_model: str = _DEFAULT_VISION_MODEL
    whisper_model: str = _DEFAULT_WHISPER_MODEL
    extensions: list[str] = _DEFAULT_EXTENSIONS[:]
    broll_frame_count: int = Field(default=5, ge=1)
    vad_threshold: float = Field(default=0.35, gt=0, le=1)
    # Language for AI-generated summaries / visual descriptions ("zh" or "en").
    output_language: Literal["zh", "en"] = "zh"

    @field_validator("text_model", "vision_model", "whisper_model", mode="before")
    @classmethod
    def _blank_falls_back_to_default(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """Treat an empty/whitespace model name as "use the default".

        The Settings UI lets the user clear these fields; rather than persist an
        empty string (which would break inference), fall back to the field's
        default so behaviour matches "leave blank for the default".
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return cls.model_fields[info.field_name].default
        return value


# ---------------------------------------------------------------------------
# AppConfig — merged, application-wide view of env + prefs
# ---------------------------------------------------------------------------

class AppConfig(BaseModel, frozen=True):
    """Merged configuration combining environment and user preferences.

    Created by :func:`load_config`.
    """

    env: EnvSettings
    prefs: Prefs


# ---------------------------------------------------------------------------
# File helpers — load_config() / save_prefs()
# ---------------------------------------------------------------------------

def _config_path(library_dir: Path) -> Path:
    """Return the path to ``<library>/.cutfinder/config.json``."""
    return library_dir / ".cutfinder" / "config.json"


def load_config(library_path: str | Path) -> AppConfig:
    """Load and merge environment variables + JSON prefs, applying defaults.

    Parameters
    ----------
    library_path:
        Absolute path to the root of the CutFinder library.  The JSON config
        lives at ``<library_path>/.cutfinder/config.json``; the directory is
        created if it does not exist yet (so ``save_prefs`` works immediately).

    Returns
    -------
    AppConfig
        Merged configuration object.

    Raises
    ------
    ValueError
        If required environment variables are missing (see :class:`EnvSettings`).
    """
    library_dir = Path(library_path).resolve()

    # Load EnvSettings from environment / .env, falling back to the global store.
    env = resolve_env()

    # Load Prefs — merge JSON file on top of defaults
    json_file = _config_path(library_dir)
    prefs_dict: dict[str, Any] = {}

    if json_file.is_file():
        with open(json_file, "r", encoding="utf-8") as f:
            prefs_dict = json.load(f)

    # Validate required fields in Prefs — library_path is mandatory
    if not prefs_dict.get("library_path"):
        raise ValueError(
            "Missing required preference: 'library_path'. "
            "Please set it in your config or via the UI."
        )

    prefs = Prefs(**prefs_dict)

    # Ensure .cutfinder directory exists (so save_prefs won't fail later)
    cutfinder_dir = library_dir / ".cutfinder"
    cutfinder_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(env=env, prefs=prefs)


def save_prefs(prefs: Prefs, library_path: str | Path) -> None:
    """Write *prefs* to ``<library>/.cutfinder/config.json``.

    Parameters
    ----------
    prefs:
        The Prefs instance to serialise and write.
    library_path:
        Absolute path to the root of the CutFinder library.

    Raises
    ------
    ValueError
        If ``prefs.library_path`` is empty (cannot determine target directory).
    """
    if not prefs.library_path:
        raise ValueError(
            "Cannot save_prefs: 'library_path' is empty. "
            "Set it before saving configuration."
        )

    library_dir = Path(library_path).resolve()
    json_file = _config_path(library_dir)

    # Ensure the directory exists before writing.
    json_file.parent.mkdir(parents=True, exist_ok=True)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(prefs.model_dump(), f, indent=2, ensure_ascii=False)
