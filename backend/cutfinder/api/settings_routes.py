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

from cutfinder.config import Prefs

logger = logging.getLogger(__name__)


def _build_router(
    load_config_fn: Any,  # config.load_config(library_path) -> AppConfig | None
    save_prefs_fn: Any,   # config.save_prefs(prefs, library_path) -> None
    get_library_fn: Any,  # callable that returns current library path or None
) -> APIRouter:
    """Construct and return the settings ``APIRouter``."""

    router = APIRouter(prefix="/api", tags=["Settings"])

    @router.get("/settings", summary="Read current application settings")
    async def get_settings() -> dict[str, Any]:
        """Return current configuration (env vars + user prefs)."""
        library_path = get_library_fn()
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

        try:
            config = load_config_fn(library_path)
        except Exception as exc:  # noqa: BLE001 — return best-effort if config unreadable
            raise HTTPException(status_code=503, detail=f"Config error: {exc}") from exc

        # Expose the OMLX endpoint but mask the secret key.
        env = {
            "OMLX_BASE_URL": config.env.OMLX_BASE_URL,
            "OMLX_API_KEY": "***MASKED***" if config.env.OMLX_API_KEY else "",
        }

        return {"env": env, "prefs": config.prefs.model_dump()}

    @router.put("/settings", summary="Update user preferences")
    async def update_settings(
        body: dict[str, Any],
    ) -> dict[str, str]:
        """Apply partial prefs update.

        Only fields present in the request body are updated; others
        retain their current values.  The update is persisted to disk
        via :func:`cutfinder.config.save_prefs`.
        """
        library_path = get_library_fn()
        if not library_path:
            raise HTTPException(status_code=404, detail="No library configured")

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

        return {"status": "ok", "message": "Settings updated"}

    return router


# ── Public exports ────────────────────────────────────────────────

__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
