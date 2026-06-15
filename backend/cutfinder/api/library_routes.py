"""Library binding routes — always mounted, even with no library bound.

GET  /api/library  → current active library path (or null)
POST /api/library  → bind a library path at runtime (hot reload, persisted)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)


def _build_router(ctx: Any, rebind_fn: Any) -> APIRouter:
    """Construct the library router.

    Parameters
    ----------
    ctx:
        The mutable :class:`api.app.LibraryContext`.
    rebind_fn:
        ``async (ctx, path) -> None`` that rebinds the active library.
    """
    router = APIRouter(prefix="/api", tags=["Library"])

    @router.get("/library", summary="Current active library")
    async def get_library() -> dict[str, Any]:
        """Return the active library path (``null`` when none is bound)."""
        return {"library_path": ctx.library_path}

    @router.post("/library", summary="Bind a library path at runtime")
    async def set_library(body: dict[str, Any]) -> dict[str, Any]:
        """Bind *body['path']* as the active library (hot reload + persisted)."""
        path = body.get("path")
        if not isinstance(path, str) or not path.strip():
            raise HTTPException(status_code=422, detail="'path' is required")

        try:
            await rebind_fn(ctx, path.strip())
        except ValueError as exc:
            # e.g. missing OMLX env vars surfaced by config loading.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=400, detail=f"Cannot use that path: {exc}"
            ) from exc

        return {"status": "ok", "library_path": ctx.library_path}

    return router


__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
