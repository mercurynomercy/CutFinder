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
from typing import Any

from fastapi import APIRouter, HTTPException

from cutfinder.config import _GLOBAL_KEYS, _GLOBAL_PREF_KEYS, Prefs

logger = logging.getLogger(__name__)

# Sentinel returned by GET for a configured secret; PUT ignores it so the
# real key is never overwritten by the masked value the UI received.
_MASKED = "***MASKED***"


def _build_router(
    load_config_fn: Any,  # config.load_config(library_path) -> AppConfig | None
    save_prefs_fn: Any,   # config.save_prefs(prefs, library_path) -> None
    get_library_fn: Any,  # callable that returns current library path or None
    save_global_fn: Any,  # config.save_global_settings(dict) -> None
    save_global_prefs_fn: Any,  # config.save_global_prefs(dict) -> None
    reload_fn: Any = None,  # async () -> None: rebuild adapters for current lib
) -> APIRouter:
    """Construct and return the settings ``APIRouter``."""

    router = APIRouter(prefix="/api", tags=["Settings"])

    @router.get("/settings", summary="Read current application settings")
    async def get_settings() -> dict[str, Any]:
        """Return current configuration as one unified ``prefs`` view.

        Per-library prefs and the machine-global keys (OMLX endpoint/key, model
        names) are merged into a single object — there is no separate ``env``
        grouping; both are stored in config.json (the env keys machine-globally,
        the prefs per library). The OMLX secret is masked.
        """
        library_path = get_library_fn()
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

        try:
            config = load_config_fn(library_path)
        except Exception as exc:  # noqa: BLE001 — return best-effort if config unreadable
            raise HTTPException(status_code=503, detail=f"Config error: {exc}") from exc

        # Merge machine-global keys into the prefs view; mask the secret key.
        prefs = {
            **config.prefs.model_dump(),
            "OMLX_BASE_URL": config.env.OMLX_BASE_URL,
            "OMLX_API_KEY": _MASKED if config.env.OMLX_API_KEY else "",
            "TEXT_MODEL": config.env.TEXT_MODEL,
            "VISION_MODEL": config.env.VISION_MODEL,
        }

        return {"prefs": prefs}

    @router.put("/settings", summary="Update user preferences")
    async def update_settings(
        body: dict[str, Any],
    ) -> dict[str, str]:
        """Apply a partial settings update.

        Per-library prefs are persisted via :func:`cutfinder.config.save_prefs`;
        machine-global keys (OMLX endpoint/key, model names) are persisted via
        :func:`cutfinder.config.save_global_settings` so they apply across all
        libraries. Only fields present in the request body are touched. A masked
        ``OMLX_API_KEY`` is ignored so the stored secret is never clobbered.
        """
        library_path = get_library_fn()
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

        # Persist machine-global env keys first (independent of prefs).
        global_updates = {
            k: v
            for k, v in body.items()
            if k in _GLOBAL_KEYS and not (k == "OMLX_API_KEY" and v == _MASKED)
        }
        if global_updates:
            try:
                save_global_fn(global_updates)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=503, detail=f"Save error: {exc}") from exc

        # Machine-global typed prefs (whisper model + toggles): one value for all
        # libraries, persisted to the global store. They still flow through the
        # per-library save below (harmless — load_config overlays the global
        # value on top), but the global store is authoritative.
        global_pref_updates = {k: v for k, v in body.items() if k in _GLOBAL_PREF_KEYS}
        if global_pref_updates:
            try:
                save_global_prefs_fn(global_pref_updates)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=503, detail=f"Save error: {exc}") from exc

        # Load current prefs first
        try:
            config = load_config_fn(library_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Config error: {exc}") from exc

        # Apply only known prefs fields from the request body, then re-validate
        # through the Prefs model (enforces ranges, types, etc.).
        allowed = set(Prefs.model_fields)
        updates = {k: v for k, v in body.items() if k in allowed}
        merged = {**config.prefs.model_dump(), **updates}

        try:
            updated = Prefs(**merged)
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError
            raise HTTPException(status_code=422, detail=f"Invalid settings: {exc}") from exc

        # Persist into the active library directory.
        try:
            save_prefs_fn(updated, library_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Save error: {exc}") from exc

        # Rebuild the live pipeline so the new settings (models, language, VAD,
        # OMLX endpoint/key, …) take effect without a restart. The values are
        # snapshotted into the adapters at build time, so a save alone is inert.
        # Best-effort: the settings are already persisted; a failed reload only
        # means a restart is needed for them to apply.
        if reload_fn is not None:
            try:
                await reload_fn()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Settings saved but live reload failed: %s", exc)

        return {"status": "ok", "message": "Settings updated"}

    return router


# ── Public exports ────────────────────────────────────────────────

__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
