"""FastAPI application factory and dependency-injection assembly.

This module wires together the real adapters (repository, orchestrator,
worker queue) and assembles them into ``APIRouter`` instances that are
mounted on the top-level :class:`fastapi.FastAPI` application.

When ``library_path`` is ``None``, the catalog routes are still mounted
but return 503 — useful for smoke tests and health checks.

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from fastapi import FastAPI  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def create_app(  # noqa: C901 — simple linear assembly, not complex
    library_path: Optional[Union[str, Path]] = None,
) -> "FastAPI":
    """Build and return the FastAPI application with all routers mounted.

    Parameters
    ----------
    library_path:
        Absolute path to the CutFinder library.  When ``None``, routes that
        depend on a catalog repository will return HTTP-503.

    Returns
    -------
    fastapi.FastAPI
        Fully wired application ready for ``uvicorn`` or ``TestClient``.

    Notes
    -----
    This is the **only** place where real adapters are instantiated.  All
    other modules receive them as parameters (injection).
    """
    # Lazy imports so this module can be imported without ffmpeg / OMLX etc.
    from fastapi import FastAPI  # noqa: E402

    app = FastAPI(title="CutFinder", version="0.1.0")

    # ── 1. Repository (SQLite-backed) ─────────────────────────────
    repository = None

    if library_path is not None and str(library_path).strip():
        try:
            from cutfinder.infrastructure.sqlite import SQLiteRepository  # noqa: E402

            db_path = Path(library_path) / ".cutfinder" / "catalog.sqlite"
            repository = SQLiteRepository(db_path=str(db_path))

        except Exception as exc:  # noqa: BLE001
            logger.warning("SQLite repository failed to initialise — catalog routes disabled: %s", exc)

    # ── 2. Orchestrator (adapters for summarizer, vision tagger, etc.) ──
    orchestrator = None

    if library_path is not None and str(library_path).strip():
        try:
            from cutfinder.config import load_config  # noqa: E402

            config = load_config(library_path)
            prefs = config.prefs

            from cutfinder.adapters.summarizer import (  # noqa: E402
                OmlxSummarizer,
            )

            summarizer = OmlxSummarizer(
                api_key=config.env.OMLX_API_KEY,
                base_url=config.env.OMLX_BASE_URL,
                model_name=prefs.text_model,
            )

            from cutfinder.adapters.vision_tagger import (  # noqa: E402
                OmlxVisionTagger,
            )

            vision_tagger = OmlxVisionTagger(
                api_key=config.env.OMLX_API_KEY,
                base_url=config.env.OMLX_BASE_URL,
                model_name=prefs.vision_model,
            )

            from cutfinder.pipeline.orchestrator import (  # noqa: E402
                Orchestrator,
            )

            orchestrator = Orchestrator(
                summarizer=summarizer,
                vision_tagger=vision_tagger,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Orchestrator failed to initialise — analysis routes disabled: %s", exc)

    # ── 3. Worker Queue (background processing + SSE broadcast) ──
    worker_queue = None

    if orchestrator is not None or repository is not None:
        from cutfinder.pipeline.worker import WorkerQueue  # noqa: E402

        worker_queue = WorkerQueue(
            orchestrator=orchestrator,
            repository=repository,
        )

    # ── 4. Config helpers (for settings routes) ─────────────────
    load_config_fn = None
    save_prefs_fn = None

    if library_path is not None and str(library_path).strip():
        from cutfinder.config import load_config as _lc  # noqa: E402
        from cutfinder.config import save_prefs as _sp  # noqa: E402

        load_config_fn = _lc
        save_prefs_fn = _sp

    def get_library() -> Optional[str]:
        """Return the current library path (or None)."""
        return str(library_path) if library_path else None

    # ── 5. Assemble routers and mount on app ─────────────────────
    from cutfinder.api.routes import _build_router as main_router  # noqa: E402
    from cutfinder.api.settings_routes import (  # noqa: E402
        _build_router as settings_router,
    )

    thumbnail_root = str(library_path) if library_path else None

    app.include_router(
        main_router(repository, orchestrator, worker_queue, thumbnail_root),
    )

    if load_config_fn is not None and save_prefs_fn is not None:
        app.include_router(settings_router(load_config_fn, save_prefs_fn, get_library))

    # ── 6. Startup / shutdown — start/stop the worker queue ─────
    @app.on_event("startup")
    async def _startup() -> None:  # noqa: E402
        if worker_queue is not None:
            await worker_queue.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # noqa: E402
        if worker_queue is not None:
            await worker_queue.stop()

    return app


# ── Public exports ────────────────────────────────────────────────

__all__: list[str] = ["create_app"]  # noqa: PLE0611
