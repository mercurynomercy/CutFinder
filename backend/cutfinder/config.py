"""Configuration loading: .env (OMLX) + JSON (user prefs), merged into AppConfig.

All classes are frozen Pydantic ``BaseModel`` instances so they are
immutable, hashable (where useful), and serialisable to JSON.

Required fields that are missing from both env vars and the JSON file
raise a clear ``ValueError`` at load time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# EnvSettings — secrets and endpoints from .env / environment variables
# ---------------------------------------------------------------------------

_REQUIRED_ENV_VARS = ("OMLX_BASE_URL", "OMLX_API_KEY")

# Repo root, anchored to this file (backend/cutfinder/config.py -> repo root).
# Used so the root ``.env`` is found even when the process runs from backend/.
_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class EnvSettings(BaseSettings):
    """Environment-driven configuration from ``.env`` / OS env vars.

    When any required field is missing a clear :class:`ValueError` is raised
    at load time so the user knows exactly what to fix.
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

    def __init__(self, **data: Any) -> None:  # noqa: ANN401
        super().__init__(**data)
        missing = [v for v in _REQUIRED_ENV_VARS if not getattr(self, v)]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


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
    broll_frame_count: int = Field(default=3, ge=1)
    vad_threshold: float = Field(default=0.15, gt=0, le=1)
    # Language for AI-generated summaries / visual descriptions ("zh" or "en").
    output_language: Literal["zh", "en"] = "zh"


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

    # Load EnvSettings from environment / .env
    env = EnvSettings()

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
