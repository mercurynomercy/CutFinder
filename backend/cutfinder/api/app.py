"""FastAPI application factory and dependency-injection assembly.

This module wires together the real adapters (repository, orchestrator,
worker queue) and assembles them into ``APIRouter`` instances that are
mounted on the top-level :class:`fastapi.FastAPI` application.

When ``library_path`` is ``None``, the catalog routes are still mounted
but return 503 — useful for smoke tests and health checks.

A module-level ``app`` is exported for ``uvicorn cutfinder.api.app:app``.
It reads the optional ``CUTFINDER_LIBRARY`` environment variable; when unset
the app starts in "no library" mode (catalog routes return 503 until a
library is configured).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from fastapi import FastAPI

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
    from fastapi import FastAPI

    app = FastAPI(title="CutFinder", version="0.1.0")

    repository = None
    orchestrator = None
    load_config_fn = None
    save_prefs_fn = None

    has_library = library_path is not None and str(library_path).strip()

    if has_library:
        lib_dir = Path(str(library_path)).resolve()
        cutfinder_dir = lib_dir / ".cutfinder"
        cutfinder_dir.mkdir(parents=True, exist_ok=True)

        from cutfinder.config import (
            AppConfig,
            EnvSettings,
            Prefs,
            load_config,
            save_prefs,
        )

        # ── 1. Config — bootstrap default prefs on first run ─────────
        # load_config() requires a persisted ``library_path`` pref; on a
        # fresh library none exists yet, so default it to this directory.
        try:
            config = load_config(lib_dir)
        except ValueError as exc:
            if "library_path" in str(exc):
                config = AppConfig(
                    env=EnvSettings(),
                    prefs=Prefs(library_path=str(lib_dir)),
                )
                # Persist the bootstrapped prefs so load_config() (used by the
                # settings route) succeeds on subsequent calls.
                save_prefs(config.prefs, lib_dir)
            else:
                raise  # missing OMLX env vars — surface the real error

        prefs = config.prefs

        # ── 2. Repository (SQLite-backed) ────────────────────────────
        from cutfinder.adapters.sqlite_repo import SqliteRepository

        db_path = cutfinder_dir / "catalog.sqlite"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        repository = SqliteRepository(conn)

        # ── 3. Orchestrator (full per-clip pipeline) ─────────────────
        from cutfinder.adapters.ffmpeg_media import (
            FfmpegFrameExtractor,
            FfmpegThumbnailMaker,
        )
        from cutfinder.adapters.ffmpeg_probe import FfmpegProbe
        from cutfinder.adapters.fs_library import FsLibraryWriter
        from cutfinder.adapters.mlx_whisper import MlxWhisperTranscriber
        from cutfinder.adapters.omlx_text import OmlxSummarizer
        from cutfinder.adapters.omlx_vision import OmlxVisionTagger
        from cutfinder.adapters.silero_vad import SileroSpeechDetector
        from cutfinder.pipeline.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            probe=FfmpegProbe(),
            thumbnail_maker=FfmpegThumbnailMaker(),
            frame_extractor=FfmpegFrameExtractor(default_count=prefs.broll_frame_count),
            speech_detector=SileroSpeechDetector(threshold=prefs.vad_threshold),
            transcriber=MlxWhisperTranscriber(model=prefs.whisper_model),
            summarizer=OmlxSummarizer(config),
            vision_tagger=OmlxVisionTagger(config),
            repository=repository,
            library_writer=FsLibraryWriter(config),
            num_frames=prefs.broll_frame_count,
        )

        load_config_fn = load_config
        save_prefs_fn = save_prefs

    # ── 4. Worker Queue (background processing + SSE broadcast) ──────
    worker_queue = None

    if orchestrator is not None or repository is not None:
        from cutfinder.pipeline.worker import WorkerQueue

        worker_queue = WorkerQueue(
            orchestrator=orchestrator,
            repository=repository,
        )

    def get_library() -> Optional[str]:
        """Return the current library path (or None)."""
        return str(library_path) if has_library else None

    # ── 5. Assemble routers and mount on app ────────────────────────
    from cutfinder.api.routes import _build_router as main_router
    from cutfinder.api.settings_routes import (
        _build_router as settings_router,
    )

    thumbnail_root = str(library_path) if has_library else None

    app.include_router(
        main_router(repository, orchestrator, worker_queue, thumbnail_root),
    )

    if load_config_fn is not None and save_prefs_fn is not None:
        app.include_router(settings_router(load_config_fn, save_prefs_fn, get_library))

    # ── 6. Startup / shutdown — start/stop the worker queue ─────────
    @app.on_event("startup")
    async def _startup() -> None:
        if worker_queue is not None:
            await worker_queue.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if worker_queue is not None:
            await worker_queue.stop()

    return app


# ── Module-level ASGI app for `uvicorn cutfinder.api.app:app` ────────
app = create_app(os.environ.get("CUTFINDER_LIBRARY") or None)


# ── Public exports ──────────────────────────────────────────────────

__all__: list[str] = ["app", "create_app"]
