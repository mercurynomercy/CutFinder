"""Configuration loading: OS env + JSON (machine-global + per-library prefs).

OMLX endpoint/key and model names come from ``~/.cutfinder/config.json``
(written by the Settings UI) or OS environment variables; per-library
preferences live in ``<library>/.cutfinder/config.json``. All classes are
frozen Pydantic ``BaseModel`` instances so they are immutable, hashable
(where useful), and serialisable to JSON.

Required fields that are missing from both env vars and the JSON file
raise a clear ``ValueError`` at load time.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# EnvSettings — OMLX endpoint/key from OS env vars / the machine-global store
# ---------------------------------------------------------------------------

# Keys that live in the machine-global store / environment (not per-library).
_GLOBAL_KEYS = ("OMLX_BASE_URL", "OMLX_API_KEY", "TEXT_MODEL", "VISION_MODEL")

# Typed Prefs fields the UI stores machine-globally (in ~/.cutfinder/config.json)
# instead of per library, so one value applies across every library. Unlike
# _GLOBAL_KEYS (env-style strings) these keep their native JSON types (the
# toggles stay booleans). load_config overlays them on top of the per-library
# prefs; the settings route persists them via save_global_prefs.
_GLOBAL_PREF_KEYS = (
    "whisper_model",
    "vocal_separation",
    "keyframe_auto",
    # Speech engine (whisper vs Qwen3-ASR+aligner) and its Qwen model/chunk
    # settings are machine-global, like whisper_model — one value for all libraries.
    "transcription_engine",
    "qwen_asr_model",
    "qwen_aligner_model",
    "qwen_max_chunk_s",
    # UI language is per-device (not per-library) — one setting for the whole machine.
    "ui_language",
)

# Repo root, anchored to this file (backend/cutfinder/config.py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Local model store: ``<repo>/models/`` (gitignored). Whisper and Demucs models
# are downloaded here on first use and loaded offline thereafter — no manual
# path configuration. See adapters/mlx_whisper.py and adapters/demucs_separator.py.
MODELS_DIR = _REPO_ROOT / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
DEMUCS_MODELS_DIR = MODELS_DIR / "demucs"
# Qwen3-ASR + ForcedAligner MLX models for the "qwen" speech engine, downloaded
# here on first use and loaded offline thereafter (see adapters/qwen_transcriber.py).
QWEN_MODELS_DIR = MODELS_DIR / "qwen"

# Machine-global settings written by the UI. These are shared across all
# libraries (the OMLX endpoint/key are machine-wide, not per-library) so the
# app runs with no environment variables at all.
_GLOBAL_CONFIG_FILE = Path.home() / ".cutfinder" / "config.json"


class EnvSettings(BaseSettings):
    """OMLX endpoint/key.

    Resolved by :func:`resolve_env` with precedence
    ``~/.cutfinder/config.json`` (written by the UI) > OS environment
    variable > empty. Missing values are allowed: the app starts
    unconfigured and the user fills them in via the Settings UI; adapters
    surface a clear connection error if used while still empty.
    """

    OMLX_BASE_URL: str = Field(
        default="",
        description="Base URL for the local OMLX server.",
    )
    OMLX_API_KEY: str = Field(
        default="",
        description="API key for authenticating with the OMLX server.",
    )

    # Default model names — overridable via global config (settings UI) or env.
    TEXT_MODEL: str = Field(
        default="",
        description="Default text model for A-roll summary + tags (e.g. Qwen3.6-35B-A3B).",
    )
    VISION_MODEL: str = Field(
        default="",
        description="Default vision model for B-roll visual tags (e.g. Qwen3-VL-8B).",
    )


# ── Machine-global settings (UI-editable, no .env required) ──────────


def _read_global_file() -> dict[str, Any]:
    """Return the raw machine-global config dict (all keys), or ``{}``.

    A missing or unreadable/non-object file yields an empty dict. Callers
    filter to the key set they own so the env keys and the typed pref keys can
    coexist in the one file without clobbering each other.
    """
    if not _GLOBAL_CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(_GLOBAL_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_global_file(data: dict[str, Any]) -> None:
    """Write *data* to ``~/.cutfinder/config.json`` (creating the dir)."""
    _GLOBAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GLOBAL_CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_global_settings() -> dict[str, str]:
    """Read the machine-global env settings from ``~/.cutfinder/config.json``.

    Returns only the recognised :data:`_GLOBAL_KEYS` with truthy values; a
    missing or unreadable file yields an empty dict.
    """
    data = _read_global_file()
    return {k: str(data[k]) for k in _GLOBAL_KEYS if data.get(k)}


def save_global_settings(updates: dict[str, str]) -> None:
    """Merge *updates* into ``~/.cutfinder/config.json`` (creating it if needed).

    Only recognised :data:`_GLOBAL_KEYS` are persisted; other keys (including the
    typed global pref keys) already in the file are preserved.
    """
    data = _read_global_file()
    data.update({k: v for k, v in updates.items() if k in _GLOBAL_KEYS})
    _write_global_file(data)


def load_global_prefs() -> dict[str, Any]:
    """Read the machine-global typed pref overrides (:data:`_GLOBAL_PREF_KEYS`).

    Membership-based (not truthiness) so a stored ``false`` toggle is honoured;
    a missing key just means "no global override, use the per-library value".
    """
    data = _read_global_file()
    return {k: data[k] for k in _GLOBAL_PREF_KEYS if k in data}


def save_global_prefs(updates: dict[str, Any]) -> None:
    """Merge typed pref *updates* (:data:`_GLOBAL_PREF_KEYS`) into the global file.

    Native JSON types are preserved (booleans stay booleans); other keys
    already in the file (the env keys) are left untouched.
    """
    data = _read_global_file()
    data.update({k: v for k, v in updates.items() if k in _GLOBAL_PREF_KEYS})
    _write_global_file(data)


_CUT_DIRECTOR_PROMPT_KEY = "cut_director_prompt"


def load_cut_director_prompt() -> str | None:
    """Return the user's custom rough-cut director prompt, or ``None``.

    ``None`` means "no override — use the built-in default"; the director falls
    back to :data:`~cutfinder.cutplan.director.DEFAULT_CUT_DIRECTOR_PROMPT`.
    """
    data = _read_global_file()
    value = data.get(_CUT_DIRECTOR_PROMPT_KEY)
    return value if isinstance(value, str) and value.strip() else None


def save_cut_director_prompt(prompt: str | None) -> None:
    """Persist a custom director prompt (``None``/blank resets to the default)."""
    data = _read_global_file()
    if prompt and prompt.strip():
        data[_CUT_DIRECTOR_PROMPT_KEY] = prompt
    else:
        data.pop(_CUT_DIRECTOR_PROMPT_KEY, None)
    _write_global_file(data)


def resolve_env() -> EnvSettings:
    """Resolve OMLX config, layering all sources.

    Precedence (highest wins): ``~/.cutfinder/config.json`` (Settings UI) >
    OS environment variable > empty. The Settings UI is authoritative — values
    saved there always take effect, even when an OS env var sets the same key.
    Env vars only fill keys the UI hasn't set.
    """
    layered: dict[str, str] = {}
    layered.update({k: os.environ[k] for k in _GLOBAL_KEYS if os.environ.get(k)})
    layered.update(load_global_settings())
    # _env_file=None: don't let pydantic's own env-file reader run; sources are
    # layered above by hand so the global store outranks OS env vars.
    return EnvSettings(_env_file=None, **layered)


# ---------------------------------------------------------------------------
# Prefs — user preferences stored in <library>/.cutfinder/config.json
# ---------------------------------------------------------------------------

_DEFAULT_EXTENSIONS: list[str] = [".mov", ".mp4", ".m4v"]
_DEFAULT_PHOTO_EXTENSIONS: list[str] = [".jpg", ".jpeg", ".png", ".heic"]
_DEFAULT_TEXT_MODEL: str = "Qwen3.6-35B-A3B"
_DEFAULT_VISION_MODEL: str = "Qwen3-VL-8B"
_DEFAULT_WHISPER_MODEL: str = "mlx-community/whisper-large-v3-mlx"
_DEFAULT_QWEN_ASR_MODEL: str = "mlx-community/Qwen3-ASR-1.7B-8bit"
_DEFAULT_QWEN_ALIGNER_MODEL: str = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"


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
    # Speech engine for all A-roll work (catalog transcription, keyframes, and
    # subtitle export): "whisper" (mlx-whisper) or "qwen" (local Qwen3-ASR +
    # ForcedAligner, more accurate for Chinese / zh-en mixed audio).
    transcription_engine: Literal["whisper", "qwen"] = "whisper"
    qwen_asr_model: str = _DEFAULT_QWEN_ASR_MODEL
    qwen_aligner_model: str = _DEFAULT_QWEN_ALIGNER_MODEL
    # Max seconds of audio per VAD-merged chunk fed to Qwen3-ASR + aligner.
    # Kept well under the aligner's ~400s timestamp range; larger = fewer cue
    # boundaries and faster, smaller = finer alignment.
    qwen_max_chunk_s: float = Field(default=60.0, gt=0, le=300)
    extensions: list[str] = _DEFAULT_EXTENSIONS[:]
    # Still-image extensions cataloged as photos (separate "photo" roll type).
    photo_extensions: list[str] = _DEFAULT_PHOTO_EXTENSIONS[:]
    broll_frame_count: int = Field(default=5, ge=1)
    vad_threshold: float = Field(default=0.35, gt=0, le=1)
    # Language for AI-generated summaries / visual descriptions ("zh" or "en").
    output_language: Literal["zh", "en"] = "zh"
    # UI interface language — per-device (one value for the whole machine). Drives
    # which default director prompt is shown and used, as well as progress messages.
    ui_language: Literal["en", "zh"] = "en"
    # Keyframe recommendation: max ranked cut/frame suggestions per clip, and
    # whether to auto-queue a keyframes job after each scan completes.
    keyframe_count: int = Field(default=3, ge=1, le=10)
    # Off by default: keyframe recommendation is the most expensive step, so a
    # scan stays fast unless the user opts in (Settings) or runs it per-clip.
    keyframe_auto: bool = False
    # A-roll transcription strips BGM with Demucs before Whisper; off by
    # default. Subtitle export always separates regardless of this flag.
    vocal_separation: bool = False
    # Rough-cut director agent (§3.15) guardrails.
    # Generation mode: "agent" runs a scoped tool loop per shooting date (the
    # model can get_clip_detail / inspect_broll then emit_plan — smarter, with a
    # per-day fall back to staged JSON when it doesn't converge); "staged" is the
    # original one-structured-JSON-call-per-date path. See task 26.
    cut_director_mode: Literal["agent", "staged"] = "agent"
    # Max tool-calling rounds before the loop force-finalizes the current draft.
    cut_max_tool_rounds: int = Field(default=24, ge=1, le=200)
    # Max live inspect_broll (Qwen3-VL) calls per generation; 0 = unlimited.
    # Tunable because text/vision interleaving makes OMLX swap models (slow) —
    # weak machines should cap it, strong machines can open it up.
    cut_vision_budget: int = Field(default=6, ge=0)
    # Default aspect ratio when the user doesn't state one in chat.
    cut_default_aspect_ratio: str = "16:9"
    # Off by default: after assembling the plan, run one extra critic LLM pass
    # that judges subjective quality (rhythm/narrative/A-B balance) and re-does
    # the dates it flags. Costs one more LLM call + the flagged days' redo, so
    # the user opts in. See task 28 Part B.
    cut_critic_enabled: bool = False
    # Per-shooting-date catalog size caps (characters), fed to the day generator.
    # The Qwen3.6 text model takes a 260k-token context, so these are generous on
    # purpose — they exist to bound local OMLX prefill cost/RAM, not to truncate.
    # Counted as real tokens (OMLX /messages/count_tokens), not characters.
    # lean = agent mode (one short line per clip, transcripts fetched on demand);
    # staged = fast mode (台词 inlined since it has no tools, so it fills faster).
    cut_lean_token_budget: int = Field(default=50000, ge=1000, le=200000)
    cut_staged_token_budget: int = Field(default=40000, ge=1000, le=200000)

    @field_validator(
        "text_model", "vision_model", "whisper_model",
        "qwen_asr_model", "qwen_aligner_model", mode="before",
    )
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

    # Load OMLX settings from the global store, falling back to OS env vars.
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

    # Overlay machine-global pref overrides (whisper model + toggles) so one
    # value applies across all libraries; they win over the per-library file.
    prefs_dict.update(load_global_prefs())

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
