"""Route handlers for the CutFinder API layer.

Each handler is a thin wrapper: validate parameters → call business logic
(orchestrator / repository) → serialize response via Pydantic schemas.

No business logic lives in this module — it delegates to injected adapters.
"""

from __future__ import annotations

import json as _json
import logging as _logging
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import Request  # noqa: E402 — needed for dependency injection in closures

logger = _logging.getLogger(__name__)


def _build_router(ctx: Any) -> Any:
    """Construct and return the main application ``APIRouter``.

    ``ctx`` is a mutable :class:`api.app.LibraryContext`; handlers read
    ``ctx.repository`` / ``ctx.worker_queue`` per request so the library can be
    (re)bound at runtime without re-mounting routes.
    """

    from fastapi import APIRouter, HTTPException, Query  # Request is imported at module level for DI
    from starlette.responses import StreamingResponse

    router = APIRouter(prefix="/api", tags=["CutFinder"])

    # ── Scan (POST /scan) ───────────────────────────────────────
    @router.post("/scan")
    async def post_scan(
        candidates: list[dict[str, str]],
    ) -> dict[str, int]:
        """Accept a list of clip candidates and enqueue them for processing."""
        if ctx.worker_queue is None:
            raise HTTPException(status_code=503, detail="Worker queue not available")

        from pydantic import ValidationError  # noqa: E402
        from cutfinder.domain.models import ClipCandidate  # noqa: E402

        try:
            candidates_obj = [ClipCandidate(**c) for c in candidates]
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        job_id = await ctx.worker_queue.enqueue_scan(candidates_obj)
        return {"job_id": job_id}

    # ── Job status (GET /jobs/{id}) ─────────────────────────────
    @router.get("/jobs/{job_id}")
    async def get_job_status(job_id: int) -> dict[str, Any]:
        """Return the current status of a scan/reanalyze job."""
        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Job tracking not available")

        job = ctx.repository.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "id": job.id,
            "status": job.status,
            "total": getattr(job, 'total', 0),
            "done": getattr(job, 'done', 0),
            "failed": getattr(job, 'failed', 0),
            "started_at": getattr(job, 'started_at', None),
        }

    # ── SSE event stream (GET /jobs/{id}/events) ───────────────
    @router.get("/jobs/{job_id}/events")
    async def get_job_events(
        job_id: int,
    ) -> StreamingResponse:
        """Subscribe to progress events for a specific job via SSE."""
        import asyncio as _asyncio

        async def event_generator() -> AsyncIterator[str]:
            sid, queue = ctx.worker_queue.subscribe()
            try:
                while True:
                    event = await queue.get()

                    # Filter events that belong to this job
                    if "job_id" in event and (event.get("job_id") != job_id):
                        continue

                    data = _json.dumps(event)
                    yield f"data: {data}\n\n"

            except (_asyncio.CancelledError, Exception):
                pass  # client disconnected

            finally:
                ctx.worker_queue.unsubscribe(sid)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Clip list (GET /clips) ─────────────────────────────────
    @router.get("/clips")
    async def list_clips(
        date: Optional[str] = Query(None),
        roll_type: Optional[str] = Query(None),
        tag: Optional[str] = Query(None),
    ) -> list[dict[str, Any]]:
        """Return a list of clips, optionally filtered."""
        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        from cutfinder.domain.models import ClipFilter  # noqa: E402
        filters = ClipFilter(date=date, roll_type=roll_type, tag=tag)
        clips = ctx.repository.query_clips(filters)

        return [
            {
                "id": c.id,
                "source_path": c.source_path,
                "library_path": getattr(c, 'library_path', None),
                "roll_type": c.roll_type,
                "summary": getattr(c, 'summary', None),
                "description": getattr(c, 'description', None),
                "duration_s": c.duration_s,
                "thumbnail_path": getattr(c, 'thumbnail_path', None),
                "status": c.status,
            }
            for c in clips
        ]

    # ── Clip detail (GET /clips/{id}) ─────────────────────────
    @router.get("/clips/{clip_id}")
    async def get_clip_detail(
        clip_id: int,
    ) -> dict[str, Any]:
        """Return detailed information for a single clip."""
        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        tags = ctx.repository.get_tags(clip_id)
        transcript = ctx.repository.get_transcript(clip_id)

        result = {
            "id": clip.id,
            "source_path": clip.source_path,
            "library_path": getattr(clip, 'library_path', None),
            "roll_type": clip.roll_type,
            "roll_source": getattr(clip, 'roll_source', 'auto'),
            "summary": getattr(clip, 'summary', None),
            "description": getattr(clip, 'description', None),
            "duration_s": clip.duration_s,
            "width": getattr(clip, 'width', None),
            "height": getattr(clip, 'height', None),
            "fps": getattr(clip, 'fps', None),
            "codec": getattr(clip, 'codec', None),
            "thumbnail_path": getattr(clip, 'thumbnail_path', None),
            "status": clip.status,
            "error": getattr(clip, 'error', None),
        }

        # capture_time may be datetime; serialize to ISO string if so
        ct = getattr(clip, 'capture_time', None)
        result["capture_time"] = ct.isoformat() if ct is not None and hasattr(ct, 'isoformat') else ct
        result["date_source"] = getattr(clip, 'date_source', 'file')

        # Tags
        result["tags"] = [
            {"name": t.name, "source": getattr(t, 'source', 'auto')} for t in tags
        ]

        # Transcript (A-roll only)
        if transcript is not None:
            result["transcript"] = {
                "full_text": getattr(transcript, 'full_text', ''),
                "segments": [
                    {
                        "start_s": getattr(s, 'start_s', 0),
                        "end_s": getattr(s, 'end_s', 0),
                        "text": getattr(s, 'text', ''),
                    }
                    for s in getattr(transcript, 'segments', [])
                ],
            }

        return result

    # ── Roll correction (PATCH /clips/{id}/roll) ─────────────
    @router.patch("/clips/{clip_id}/roll")
    async def correct_roll(
        clip_id: int,
        roll: str = Query(..., pattern="^[ab]$"),  # injected by FastAPI
    ) -> dict[str, Any]:
        """Override the AI-generated A/B classification for a clip."""

        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        ctx.repository.correct_roll(clip_id, roll)
        return {"status": "ok", "clip_id": clip_id, "roll_type": roll}

    # ── Summary/Description edit (PATCH /clips/{id}) ─────────
    @router.patch("/clips/{clip_id}")
    async def edit_clip(
        clip_id: int,
        request: Request,  # injected by FastAPI (module-level import)
    ) -> dict[str, Any]:
        """Edit the summary (A-roll) or description (B-roll)."""

        try:
            body = _json.loads((await request.body()).decode())
        except _json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Body must be a JSON object")

        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        # Build a minimal analysis result with only provided fields
        from cutfinder.domain.models import (  # noqa: E402
            AnalysisResult, SummaryResult, VisionResult,  # noqa: E402
        )

        # Build a minimal analysis result with only provided fields.
        # roll_type is required by AnalysisResult but never changes via edit — carry it forward.
        fields: dict[str, Any] = {"roll_type": clip.roll_type}
        if "summary" in body and body["summary"] is not None:
            fields["summary_result"] = SummaryResult(
                summary=body["summary"], tags=[],
            )
        if "description" in body and body["description"] is not None:
            fields["vision_result"] = VisionResult(
                description=body["description"], tags=[],
            )

        if fields:  # - always has roll_type
            result_obj = AnalysisResult(**fields)
            ctx.repository.update_analysis(clip_id, result_obj)

        return {"status": "ok", "clip_id": clip_id}

    # ── Tag management (PUT /clips/{id}/tags) ───────────────
    @router.put("/clips/{clip_id}/tags")
    async def set_clip_tags(
        clip_id: int,
        request: Request,  # injected by FastAPI (module-level import)
    ) -> dict[str, Any]:
        """Replace all tags on a clip with the provided list."""

        try:
            body = _json.loads((await request.body()).decode())
        except _json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Body must be a JSON object")

        raw_tags = body.get("tags", [])
        if not isinstance(raw_tags, list):
            raise HTTPException(status_code=422, detail="'tags' must be a list")

        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        from cutfinder.domain.models import Tag  # noqa: E402
        tag_objects = [
            Tag(name=t["name"], source=t.get("source", "manual"))
            for t in raw_tags if "name" in t
        ]

        ctx.repository.set_tags(clip_id, tag_objects)
        return {"status": "ok", "clip_id": clip_id, "tags_count": len(tag_objects)}

    # ── Re-analyze (POST /clips/{id}/reanalyze) ─────────────
    @router.post("/clips/{clip_id}/reanalyze")
    async def reanalyze_clip(
        clip_id: int,
    ) -> dict[str, Any]:
        """Trigger re-analysis of an existing clip."""
        if ctx.worker_queue is None:
            raise HTTPException(status_code=503, detail="Worker queue not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        job_id = await ctx.worker_queue.enqueue_reanalyze(clip_id)
        return {"job_id": job_id}

    # ── Thumbnail (GET /clips/{id}/thumbnail) ───────────────
    @router.get("/clips/{clip_id}/thumbnail")
    async def get_clip_thumbnail(
        clip_id: int,
    ) -> StreamingResponse:
        """Serve the thumbnail image for a clip from the library directory."""

        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clip = ctx.repository.get_clip(clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        thumbnail_path = getattr(clip, "thumbnail_path", None)
        if not thumbnail_path:
            raise HTTPException(status_code=404, detail="No thumbnail available")

        thumb_file = Path(thumbnail_path)
        if not thumb_file.is_file():
            raise HTTPException(status_code=404, detail="Thumbnail file not found")

        # Detect content type from extension
        import mimetypes  # noqa: E402

        mime_type, _ = mimetypes.guess_type(str(thumb_file))
        if mime_type is None:
            mime_type = "application/octet-stream"

        def iter_file() -> Any:  # noqa: E402
            with open(thumb_file, "rb") as f:  # noqa: E402
                while chunk := f.read(65_536):
                    yield chunk

        return StreamingResponse(
            iter_file(),
            media_type=mime_type,
            headers={
                "Cache-Control": "public, max-age=86400",
            },
        )

    # ── Search (GET /search) ───────────────────────────────
    @router.get("/search")
    async def search_clips(
        q: str = Query(..., min_length=1),
    ) -> list[dict[str, Any]]:
        """Search clips by full-text match on summary, description, transcript."""
        if ctx.repository is None:
            raise HTTPException(status_code=503, detail="Catalog not available")

        clips = ctx.repository.search(q)
        return [
            {
                "id": c.id,
                "source_path": c.source_path,
                "library_path": getattr(c, 'library_path', None),
                "roll_type": c.roll_type,
                "summary": getattr(c, 'summary', None),
                "description": getattr(c, 'description', None),
            }
            for c in clips
        ]

    return router


# ── Public exports ────────────────────────────────────────────────

__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
