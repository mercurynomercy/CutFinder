"""FastAPI application factory and dependency-injection assembly.

The active library can be (re)bound at runtime via ``POST /api/library`` — so
instead of capturing adapters in route closures, all routers read them from a
mutable :class:`LibraryContext`. The chosen library is persisted so it survives
a restart.

When no library is bound, catalog/analysis routes return 503 and the settings
route returns 404; the library-setup route (``/api/library``) is always
available.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Where the chosen library path is persisted (so it survives a restart).
_ACTIVE_LIBRARY_FILE = Path.home() / ".cutfinder" / "active_library"


class LibraryContext:
    """Mutable holder for the adapters bound to the active library.

    Routers read these attributes per request, so rebinding the library at
    runtime takes effect immediately without re-mounting routes.
    """

    def __init__(self) -> None:
        self.library_path: Optional[str] = None
        self.repository: Any = None
        self.orchestrator: Any = None
        self.worker_queue: Any = None

    @property
    def thumbnail_root(self) -> Optional[str]:
        return self.library_path


def _persist_library(library_path: str) -> None:
    """Remember *library_path* as the active library across restarts."""
    try:
        _ACTIVE_LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ACTIVE_LIBRARY_FILE.write_text(library_path, encoding="utf-8")
    except OSError as exc:  # non-fatal — runtime binding still works
        logger.warning("Could not persist active library: %s", exc)


def _load_persisted_library() -> Optional[str]:
    """Return the persisted active library path, if any."""
    try:
        if _ACTIVE_LIBRARY_FILE.is_file():
            text = _ACTIVE_LIBRARY_FILE.read_text(encoding="utf-8").strip()
            return text or None
    except OSError:
        pass
    return None


def _build_into(ctx: LibraryContext, library_path: Union[str, Path]) -> None:
    """Build the repository + orchestrator + worker for *library_path* into ctx.

    Synchronous: the worker queue is created but not started (the caller starts
    it — either the FastAPI startup event or :func:`rebind_library`).
    """
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

    # Config — bootstrap default prefs on first run (load_config requires a
    # persisted library_path pref; default it to this directory).
    try:
        config = load_config(lib_dir)
    except ValueError as exc:
        if "library_path" in str(exc):
            config = AppConfig(env=EnvSettings(), prefs=Prefs(library_path=str(lib_dir)))
            save_prefs(config.prefs, lib_dir)
        else:
            raise  # missing OMLX env vars — surface the real error

    prefs = config.prefs

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
    from cutfinder.adapters.sqlite_repo import SqliteRepository
    from cutfinder.pipeline.orchestrator import Orchestrator
    from cutfinder.pipeline.worker import WorkerQueue

    db_path = cutfinder_dir / "catalog.sqlite"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    repository = SqliteRepository(conn)

    # A custom WHISPER_MODEL_PATH (env) overrides the whisper_model pref so the
    # model loads from a local directory instead of the HF cache.
    whisper_model = config.env.WHISPER_MODEL_PATH or prefs.whisper_model

    orchestrator = Orchestrator(
        probe=FfmpegProbe(),
        thumbnail_maker=FfmpegThumbnailMaker(),
        frame_extractor=FfmpegFrameExtractor(default_count=prefs.broll_frame_count),
        speech_detector=SileroSpeechDetector(threshold=prefs.vad_threshold),
        transcriber=MlxWhisperTranscriber(model=whisper_model),
        summarizer=OmlxSummarizer(config),
        vision_tagger=OmlxVisionTagger(config),
        repository=repository,
        library_writer=FsLibraryWriter(config),
        num_frames=prefs.broll_frame_count,
    )

    worker_queue = WorkerQueue(orchestrator=orchestrator, repository=repository)

    ctx.library_path = str(lib_dir)
    ctx.repository = repository
    ctx.orchestrator = orchestrator
    ctx.worker_queue = worker_queue


async def rebind_library(ctx: LibraryContext, library_path: Union[str, Path]) -> None:
    """Rebind the active library at runtime: stop old worker, build, start new."""
    old_worker = ctx.worker_queue
    if old_worker is not None:
        try:
            await old_worker.stop()
        except Exception as exc:  # noqa: BLE001 — best-effort teardown
            logger.warning("Error stopping previous worker on rebind: %s", exc)

    _build_into(ctx, library_path)
    await ctx.worker_queue.start()
    if ctx.library_path:
        _persist_library(ctx.library_path)


def create_app(
    library_path: Optional[Union[str, Path]] = None,
) -> "FastAPI":
    """Build and return the FastAPI application with all routers mounted.

    The initial library comes from (in order) the ``library_path`` argument, the
    ``CUTFINDER_LIBRARY`` env var, or the persisted active-library file. When
    none is found the app starts with no library bound (set one via the UI →
    ``POST /api/library``).
    """
    from fastapi import FastAPI

    app = FastAPI(title="CutFinder", version="0.1.0")
    ctx = LibraryContext()
    app.state.library_context = ctx

    initial = (
        str(library_path).strip()
        if library_path is not None and str(library_path).strip()
        else (os.environ.get("CUTFINDER_LIBRARY") or _load_persisted_library())
    )
    if initial:
        # Never let a bad/persisted library crash startup — fall back to "no
        # library bound" and let the user re-bind via POST /api/library.
        try:
            _build_into(ctx, initial)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not bind initial library %r: %s", initial, exc)

    # ── Routers ─────────────────────────────────────────────────────
    from cutfinder.api.library_routes import _build_router as library_router
    from cutfinder.api.routes import _build_router as main_router
    from cutfinder.api.settings_routes import _build_router as settings_router
    from cutfinder.config import load_config, save_prefs

    app.include_router(main_router(ctx))
    app.include_router(
        settings_router(load_config, save_prefs, lambda: ctx.library_path)
    )
    app.include_router(library_router(ctx, rebind_library))

    # ── Startup / shutdown — start/stop the worker queue ────────────
    @app.on_event("startup")
    async def _startup() -> None:
        logger.info("_startup event fired, worker_queue=%s", ctx.worker_queue is not None)
        if ctx.worker_queue is not None:
            await ctx.worker_queue.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if ctx.worker_queue is not None:
            await ctx.worker_queue.stop()

    return app


# ── Module-level ASGI app for `uvicorn cutfinder.api.app:app` ────────
app = create_app(os.environ.get("CUTFINDER_LIBRARY") or None)


# ── Public exports ──────────────────────────────────────────────────

__all__: list[str] = ["app", "create_app", "rebind_library", "LibraryContext"]
