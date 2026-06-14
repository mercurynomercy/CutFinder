"""Settings route handlers for the CutFinder API.

GET /settings — read current configuration (env vars + prefs)
PUT  /settings   — partial update of user preferences

Delegates to :func:`cutfinder.config.load_config` and
:func:`cutfinder.config.save_prefs`.

Note: thumbnail serving was removed from this module because it had
broken ``repository`` references.  It is not part of the v1 scope anyway.

"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import Field as PydanticField

logger = logging.getLogger(__name__)


def _build_router(
    load_config_fn: Any,  # config.load_config(library_path) -> AppConfig | None
    save_prefs_fn: Any,   # config.save_prefs(prefs, library_path) -> None
    get_library_fn: Any,  # callable that returns current library path or None
) -> APIRouter:
    """Construct and return the settings ``APIRouter``."""

    router = APIRouter(prefix="/api", tags=["Settings"])

    @router.get("/settings", summary="Read current application settings")
    async def get_settings() -> dict[str, Any]:  # type: ignore[misc]
        """Return current configuration (env vars + user prefs)."""
        library_path = get_library_fn()  # type: ignore[union-attr]
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

        try:
            config = load_config_fn(library_path)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 — return best-effort if config unreadable
            raise HTTPException(status_code=503, detail=f"Config error: {exc}")

        # Build env vars dict (mask sensitive values)
        import os  # noqa: E402

        env = {k: ("***MASKED**" if "KEY" in k else v)
               for k, v in os.environ.items() if not k.startswith("_")}

        # Build prefs dict
        prefs = {}
        if config is not None:
            prefs = {
                "source_folders": getattr(config, 'prefs', {}).get('source_folders', []),
                "library_path": config.library_path if hasattr(config, 'library_path') else None,
                "text_model": getattr(getattr(config, 'prefs', {}), 'text_model',
                                      PydanticField().default or "Qwen3-VL-8B-Instruct"),
                "vision_model": getattr(getattr(config, 'prefs', {}), 'vision_model',
                                        PydanticField().default or "Qwen3-VL-8B-Instruct"),
                "whisper_model": getattr(getattr(config, 'prefs', {}), 'whisper_model',
                                         PydanticField().default or "large-v3"),
                "extensions": getattr(getattr(config, 'prefs', {}), 'extensions', ['.mp4']),
                "broll_frame_count": getattr(getattr(config, 'prefs', {}), 'broll_frame_count', 5),
                "vad_threshold": getattr(getattr(config, 'prefs', {}), 'vad_threshold', 0.4),
            }

        # Try to read the actual prefs object from config
        if hasattr(config, 'prefs'):
            p = config.prefs  # type: Prefs from cutfinder.config
            prefs["source_folders"] = getattr(p, 'source_folders', [])
            prefs["library_path"] = config.library_path if hasattr(config, 'library_path') else None
            prefs["text_model"] = getattr(p, 'text_model', "Qwen3-VL-8B-Instruct")
            prefs["vision_model"] = getattr(p, 'vision_model', "Qwen3-VL-8B-Instruct")
            prefs["whisper_model"] = getattr(p, 'whisper_model', "large-v3")
            prefs["extensions"] = getattr(p, 'extensions', [".mp4"])
            prefs["broll_frame_count"] = getattr(p, 'broll_frame_count', 5)
            prefs["vad_threshold"] = getattr(p, 'vad_threshold', 0.4)

        return {"env": env, "prefs": prefs}

    @router.put("/settings", summary="Update user preferences")
    async def update_settings(  # type: ignore[misc]
        body: dict[str, Any],
    ) -> dict[str, str]:  # type: ignore[misc]
        """Apply partial prefs update.

        Only fields present in the request body are updated; others
        retain their current values.  The update is persisted to disk
        via :func:`cutfinder.config.save_prefs`.
        """
        library_path = get_library_fn()  # type: ignore[union-attr]
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

        # Load current prefs first
        try:
            config = load_config_fn(library_path)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Config error: {exc}")

        # Build updated prefs dict
        from copy import deepcopy  # noqa: E402

        current_prefs = {}
        if config is not None and hasattr(config, 'prefs'):
            p = config.prefs  # type: Prefs from cutfinder.config
            current_prefs.update({
                "source_folders": getattr(p, 'source_folders', []),
                "library_path": config.library_path if hasattr(config, 'library_path') else None,
                "text_model": getattr(p, 'text_model', "Qwen3-VL-8B-Instruct"),
                "vision_model": getattr(p, 'vision_model', "Qwen3-VL-8B-Instruct"),
                "whisper_model": getattr(p, 'whisper_model', "large-v3"),
                "extensions": getattr(p, 'extensions', [".mp4"]),
                "broll_frame_count": getattr(p, 'broll_frame_count', 5),
                "vad_threshold": getattr(p, 'vad_threshold', 0.4),
            })

        # Apply updates from request body (partial update)
        for key, value in body.items():
            if key == "library_path":
                # library_path is set on config, not prefs — skip here; handled separately below
                continue
            if key in current_prefs:
                # Validate types
                expected_type = type(current_prefs[key])  # e.g. int, float, str, list
                if expected_type is bool:
                    value = bool(value)  # type: ignore[assignment]
                elif expected_type is int:
                    value = int(value)  # type: ignore[assignment]
                elif expected_type is float or expected_type is int and key == 'vad_threshold':
                    value = float(value)  # type: ignore[assignment]
                elif expected_type is list and not isinstance(value, (list, tuple)):
                    value = [value]  # type: ignore[assignment]

                current_prefs[key] = value
            elif key == "library_path":
                pass  # handle below

        # Update library path if provided (special handling)
        lib_path = body.get("library_path") or current_prefs.get("library_path")

        # Save via config module
        try:
            save_prefs_fn(current_prefs, lib_path)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Save error: {exc}")

        return {"status": "ok", "message": "Settings updated"}

    return router


# ── Public exports ────────────────────────────────────────────────

__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
