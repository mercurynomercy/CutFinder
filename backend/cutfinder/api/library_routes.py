"""Library binding routes — always mounted, even with no library bound.

GET  /api/library  → current active library path (or null)
POST /api/library  → bind a library path at runtime (hot reload, persisted)
"""

from __future__ import annotations

import logging
from pathlib import Path
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

    @router.get("/library/orphans", summary="Clips whose library copy was deleted")
    async def list_orphans() -> dict[str, Any]:
        """List catalog entries whose organised library copy no longer exists.

        Safety: when the library root itself is unreachable (e.g. an external
        drive is unmounted), return ``library_reachable=False`` and an empty
        list — every file would look "missing", and deleting then would wipe the
        catalog. The caller must not offer deletions in that case.
        """
        if ctx.repository is None or ctx.orchestrator is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        if not ctx.library_path or not Path(ctx.library_path).is_dir():
            return {"library_reachable": False, "orphans": []}

        orphans = ctx.orchestrator.find_orphaned_clips()
        return {
            "library_reachable": True,
            "orphans": [
                {
                    "id": s.id,
                    "source_path": s.source_path,
                    "library_path": getattr(s, "library_path", None),
                    "roll_type": s.roll_type,
                }
                for s in orphans
            ],
        }

    @router.post("/library/orphans/delete", summary="Delete catalog entries + derived files")
    async def delete_orphans(body: dict[str, Any]) -> dict[str, Any]:
        """Delete the given clip ids (catalog rows + thumbnails + keyframes).

        Source files are never touched. Only ids the caller passes are removed,
        so the UI is responsible for confirming the preview first.
        """
        if ctx.repository is None or ctx.orchestrator is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        raw = body.get("clip_ids")
        if not isinstance(raw, list) or not all(isinstance(i, int) for i in raw):
            raise HTTPException(status_code=422, detail="'clip_ids' must be a list of integers")

        deleted = ctx.orchestrator.delete_clips(raw)
        return {"deleted": deleted}

    return router


__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
