"""WorkerQueue — background queue + SSE progress broadcasting.

Spawns a single asyncio worker task that processes clips sequentially
from an ``asyncio.Queue``.  This respects model VRAM constraints by never
running more than one analysis at a time (OMLX handles model switching).

Progress events are broadcast to any number of SSE subscribers so the
frontend can render real-time progress bars.

Examples
--------
>>> from tests.fakes import FakeCatalogRepository  # noqa: D105
>>> queue = WorkerQueue(repository=FakeCatalogRepository())  # noqa: D105
>>> await queue.start()          # start background worker           # doctest: +SKIP
>>> job_id = await queue.enqueue_scan([...])  # noqa: D105; E501
>>> await queue.stop()           # graceful shutdown                 # doctest: +SKIP

"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cutfinder.domain.models import (
    ClipCandidate,
    JobFailedItem,
)
from cutfinder.ports.repository import CatalogRepository

logger = logging.getLogger(__name__)


# ── Progress event broadcasting for SSE ───────────────────────────

@dataclass
class _EventStream:
    """Internal SSE subscriber registry and broadcast mechanism.

    Each subscriber gets its own ``asyncio.Queue``; the worker task
    puts events into all queues and sets an :class:`asyncio.Event` to
    wake any coroutines waiting on ``wait_event``.

    Attributes
    ----------
    subscribers : dict[str, asyncio.Queue]
        Active SSE connections keyed by unique ID.

    wait_event : ~asyncio.Event
        Set whenever an event is broadcast; clients await this to know
        when new data has arrived.

    _next_id : int
        Auto-increment counter for subscriber IDs.

    """

    subscribers: dict[str, asyncio.Queue[Any]] = field(default_factory=dict)
    wait_event: asyncio.Event = field(default_factory=asyncio.Event)
    _next_id: int = 0

    def add(self) -> tuple[str, asyncio.Queue[Any]]:
        """Register a new subscriber and return (id, queue)."""
        sid = f"sub_{self._next_id}"
        self._next_id += 1
        q: asyncio.Queue[Any] = asyncio.Queue()
        self.subscribers[sid] = q
        return sid, q

    def remove(self, sid: str) -> None:
        """Unregister a subscriber by ID."""
        self.subscribers.pop(sid, None)

    async def broadcast(self, event: Any) -> None:
        """Push *event* into every subscriber queue and wake waiters."""
        for q in self.subscribers.values():
            await q.put(event)
        self.wait_event.set()


# ── WorkerQueue ───────────────────────────────────────────────────

class WorkerQueue:
    """Single-worker task queue backed by ``asyncio.Queue`` + SSE broadcast.

    Parameters
    ----------
    orchestrator : optional
        An object with ``process_clip(candidate)`` and
        ``reanalyze(clip_id) -> bool`` methods (typically an
        :class:`~cutfinder.pipeline.orchestrator.Orchestrator`).  If
        ``None``, the queue still accepts jobs but analysis steps are
        no-ops that return success without real work.

    repository : ~cutfinder.ports.repository.CatalogRepository | None
        Used to persist job state (total/done/failed).  If ``None``,
        jobs are tracked in-memory only.

    progress_callback : callable[[Any], None] | None
        Optional synchronous callback invoked for every progress event.
        Useful when SSE is not needed — the caller can just inspect events
        directly without subscribing to the stream.

    Examples
    --------
    Basic usage with real orchestrator::

        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()
        job_id = await queue.enqueue_scan(candidates)
        # ... frontend subscribes to SSE events ...
        await queue.stop()

    Usage with callback instead of SSE::

        events: list[Any] = []
        queue = WorkerQueue(progress_callback=lambda e: events.append(e))
        await queue.start()

    """

    def __init__(
        self,
        orchestrator: Any | None = None,
        repository: CatalogRepository | None = None,
        progress_callback: Callable[[Any], None] | None = None,
        keyframe_auto: bool = False,
    ) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._repository = repository
        self._progress_callback = progress_callback
        # When True, a completed scan job auto-enqueues a keyframes job for
        # clips that don't have suggestions yet.
        self._keyframe_auto = keyframe_auto
        self._kf_autoqueued: set[int] = set()  # scan job_ids already followed-up

        # SSE event stream (lazy-initialized on first subscribe)
        self._stream: _EventStream | None = None

        # Reference to orchestrator (may be None)
        self._orchestrator = orchestrator

        # Auto-increment counter for job IDs when no repository is available
        self._next_job_counter: int = 0

        # Global pause gate — set means "running", cleared means "paused".
        self._resume: asyncio.Event = asyncio.Event()
        self._resume.set()

        # Jobs whose remaining queued items should be skipped.
        self._cancelled_jobs: set[int] = set()

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the background worker task.

        Safe to call multiple times — subsequent calls are no-ops
        if the worker is already running.
        """
        logger.info("WorkerQueue.start() called")
        if self._worker_task and not self._worker_task.done():
            # Already running — idempotent no-op.
            logger.info("WorkerQueue: worker task already running")
            return
        if self._worker_task and self._worker_task.done():
            # Re-raise any exception from a finished task.
            logger.warning("WorkerQueue: previous worker task is done, re-raising exception")
            self._worker_task.result()
        logger.info("WorkerQueue: spawning worker task")
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Signal the worker to drain remaining items and exit.

        Awaits the worker task so all enqueued work is completed
        before returning.  Safe to call even if ``start()`` was never
        called or the worker is already stopped.
        """
        # Ensure the worker isn't blocked on a pause gate so it can drain + exit.
        self._resume.set()
        self._queue.put_nowait(_STOP_SENTINEL)
        if self._worker_task and not self._worker_task.done():
            await self._worker_task
        self._worker_task = None

    # ── Pause / resume / cancel (global + per-job control) ───────

    def pause(self) -> None:
        """Pause the worker: the in-flight item finishes, then it blocks."""
        self._resume.clear()

    def resume(self) -> None:
        """Resume a paused worker. Queued items are preserved."""
        self._resume.set()

    @property
    def is_paused(self) -> bool:
        """True if the worker is currently paused."""
        return not self._resume.is_set()

    def cancel_job(self, job_id: int) -> None:
        """Mark a job cancelled; its remaining queued items are skipped."""
        self._cancelled_jobs.add(job_id)

    # ── Job submission (public API) ──────────────────────────────

    async def enqueue_scan(
        self,
        candidates: list[ClipCandidate],
        job_id: int | None = None,
    ) -> int:
        logger.info("enqueue_scan: %d candidates", len(candidates))
        """Enqueue a batch of clips for sequential processing.

        Creates (or reuses) a job record, emits a ``job_started``
        progress event, then enqueues each candidate.

        Parameters
        ----------
        candidates:
            List of :class:`ClipCandidate` objects from the Scanner.
        job_id:
            Optional pre-existing job ID to use instead of creating one.

        Returns
        -------
        int
            The job ID for this scan batch.

        """
        # Create or validate job record
        if self._repository:
            if job_id is not None and (self._repository.get_job(job_id) is not None):
                pass  # reuse existing job record
            elif job_id is None:
                job = self._repository.create_job(total=len(candidates), kind="scan")
                job_id = job.id

        if job_id is None:
            self._next_job_counter += 1
            job_id = self._next_job_counter

        # Emit progress events for batch start and per-clip processing
        self._emit({"type": "job_started", "job_id": job_id, "total": len(candidates)})

        # Handle empty candidate list: no items to enqueue → immediately mark done.
        if not candidates:
            logger.info("enqueue_scan: no candidates, marking job %d as done", job_id)
            if self._repository:
                self._repository.update_job(job_id, status="done", total=0, done=0)
            self._emit({"type": "job_completed", "job_id": job_id})
            return job_id

        for candidate in candidates:
            await self._queue.put(("clip", candidate, job_id))

        return job_id

    async def enqueue_reanalyze(
        self,
        clip_id: int,
        job_id: int | None = None,
    ) -> int:
        """Enqueue a single clip for re-analysis.

        Parameters
        ----------
        clip_id:
            Database ID of the existing processed clip.
        job_id:
            Optional pre-existing job ID to use instead of creating one.

        Returns
       -------
        int
            The job ID for this re-analysis job (always total=1).

        """
        # Create or validate job record
        if self._repository:
            if job_id is not None and (self._repository.get_job(job_id) is not None):
                pass  # reuse existing job record
            elif job_id is None:
                job = self._repository.create_job(total=1, kind="reanalyze")
                job_id = job.id

        if job_id is None:
            self._next_job_counter += 1
            job_id = self._next_job_counter

        self._emit({"type": "job_started", "job_id": job_id, "total": 1})
        await self._queue.put(("reanalyze", clip_id, job_id))

        return job_id  # pyright: ignore[reportPossiblyUnboundVariable]

    async def enqueue_keyframes(
        self,
        clip_ids: list[int],
        job_id: int | None = None,
    ) -> int:
        """Enqueue keyframe-suggestion work for *clip_ids* as one job.

        Returns the job id. An empty list creates a job that completes immediately.
        """
        if self._repository:
            if job_id is not None and (self._repository.get_job(job_id) is not None):
                pass
            elif job_id is None:
                job = self._repository.create_job(total=len(clip_ids), kind="keyframes")
                job_id = job.id

        if job_id is None:
            self._next_job_counter += 1
            job_id = self._next_job_counter

        self._emit({"type": "job_started", "job_id": job_id, "total": len(clip_ids)})

        if not clip_ids:
            if self._repository:
                self._repository.update_job(job_id, status="done", total=0, done=0)
            self._emit({"type": "job_completed", "job_id": job_id})
            return job_id

        for cid in clip_ids:
            await self._queue.put(("keyframes", cid, job_id))
        return job_id

    async def enqueue_clip(self, candidate: ClipCandidate) -> None:
        """Enqueue a single clip for processing (no job tracking).

        Parameters
        ----------
        candidate:
            A :class:`ClipCandidate` to process.

        """
        await self._queue.put(("clip", candidate, None))

    async def enqueue_reanalyze_task(self, clip_id: int) -> None:
        """Enqueue a single re-analysis task (no job tracking).

        Parameters
        ----------
        clip_id:
            Database ID of the existing processed clip.

        """
        await self._queue.put(("reanalyze", clip_id, None))

    async def retry_job(self, job_id: int) -> bool:
        """Re-enqueue a job's failed items under the same job_id.

        Returns ``False`` (no-op) when the job has no recorded failures.
        """
        if self._repository is None:
            return False

        items = self._repository.get_failed_items(job_id)
        if not items:
            return False

        self._repository.clear_failed_items(job_id)

        job = self._repository.get_job(job_id)
        n = len(items)
        if job is not None:
            self._repository.update_job(
                job_id,
                status="queued",
                done=max(job.done - n, 0),
                failed=max(job.failed - n, 0),
            )

        # A retried job is no longer cancelled.
        self._cancelled_jobs.discard(job_id)

        for item in items:
            if item.kind == "reanalyze":
                await self._queue.put(("reanalyze", item.clip_id, job_id))
            elif item.kind == "keyframes":
                await self._queue.put(("keyframes", item.clip_id, job_id))
            elif item.path is not None and item.fingerprint is not None:
                await self._queue.put((
                    "clip",
                    ClipCandidate(path=item.path, fingerprint=item.fingerprint),
                    job_id,
                ))

        return True

    # ── SSE subscriber management ────────────────────────────────

    def subscribe(self) -> tuple[str, asyncio.Queue[Any]]:
        """Register a new SSE subscriber.

        Returns ``(subscriber_id, event_queue)`` — the caller should
        read from *event_queue* in a loop and call :meth:`unsubscribe`
        when done.

        Returns
        -------
        tuple[str, ~asyncio.Queue]

        """
        if self._stream is None:
            self._stream = _EventStream()
        return self._stream.add()

    def unsubscribe(self, sid: str) -> None:
        """Remove an SSE subscriber by ID."""
        if self._stream is not None:
            self._stream.remove(sid)

    # ── Internal helpers ─────────────────────────────────────────

    def _emit(self, event: Any) -> None:
        """Broadcast a progress/event dict to callback + SSE stream."""
        # Callback
        cb = self._progress_callback
        if cb is not None:
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001 — callback errors must not stop processing
                logger.warning("Progress callback error: %s", exc)

        # SSE stream broadcast (async — fire-and-forget in worker context)
        if self._stream is not None:
            try:
                # Run broadcast in a fire-and-forget task since we're already
                # inside the worker coroutine (can't await here)
                asyncio.create_task(self._stream.broadcast(event))  # noqa: RUF006 — intentional fire-and-forget
            except RuntimeError:
                # No running event loop (shouldn't happen in worker context)
                pass

    async def _worker_loop(self) -> None:
        """Main loop: dequeue items and process them sequentially.

        Exits when the stop sentinel is received or the queue is closed.
        """
        logger.info("Worker loop started")
        try:
            while True:
                # Global pause gate — block here so the in-flight item (if any)
                # has already finished. Queued items are preserved meanwhile.
                await self._resume.wait()

                item = await self._queue.get()

                # Stop sentinel — drain remaining then exit
                if isinstance(item, type(_STOP_SENTINEL)):
                    self._queue.task_done()
                    break

                kind, payload, job_id = item

                # Skip items belonging to a cancelled job (no counters, no work).
                if job_id is not None and job_id in self._cancelled_jobs:
                    self._queue.task_done()
                    continue

                # Transition a freshly-started job 'queued' -> 'running' once.
                if job_id is not None and self._repository is not None:
                    job = self._repository.get_job(job_id)
                    if job is not None and job.status == "queued":
                        self._repository.update_job(job_id, status="running")

                try:
                    if kind == "clip":
                        success, error = await self._process_clip(payload)
                    elif kind == "reanalyze":
                        success, error = await self._process_reanalyze(payload)
                    elif kind == "keyframes":
                        success, error = await self._process_keyframes(payload)
                    else:
                        success, error = True, None

                except Exception as exc:  # noqa: BLE001 — error isolation per item
                    logger.error(
                        "Worker processing error (continuing): %s", exc, exc_info=True,
                    )
                    success, error = False, str(exc)

                self._update_job_after_item(job_id, kind, payload, success, error)
                # After a scan finishes, optionally auto-queue keyframe suggestion.
                if kind == "clip" and job_id is not None:
                    await self._maybe_autoqueue_keyframes(job_id)
                self._queue.task_done()

        except asyncio.CancelledError:
            # Normal shutdown — drain remaining items if possible
            pass

    async def _maybe_autoqueue_keyframes(self, scan_job_id: int) -> None:
        """When a scan job has just completed, enqueue keyframes for new clips."""
        if not self._keyframe_auto or self._repository is None:
            return
        if scan_job_id in self._kf_autoqueued:
            return
        job = self._repository.get_job(scan_job_id)
        if job is None or job.kind != "scan" or job.status != "done":
            return
        self._kf_autoqueued.add(scan_job_id)
        clip_ids = self._repository.clip_ids_without_keyframes()
        if clip_ids:
            logger.info("Auto-queueing keyframes for %d clip(s) after scan #%s", len(clip_ids), scan_job_id)
            await self.enqueue_keyframes(clip_ids)

    def _update_job_after_item(
        self,
        job_id: int | None,
        kind: str,
        payload: Any,
        success: bool,
        error: str | None,
    ) -> None:
        """Update per-job counters + terminal status for one processed item."""
        if job_id is None or self._repository is None:
            return

        job = self._repository.get_job(job_id)
        if job is None:
            return

        if success:
            self._repository.update_job(job_id, done=job.done + 1)
        else:
            self._repository.update_job(
                job_id, done=job.done + 1, failed=job.failed + 1,
            )
            if kind in ("reanalyze", "keyframes"):
                # payload is a clip_id (int) for these kinds.
                self._repository.record_failed_item(JobFailedItem(
                    job_id=job_id, kind=kind, clip_id=payload, error=error,
                ))
            else:
                self._repository.record_failed_item(JobFailedItem(
                    job_id=job_id, kind="clip",
                    path=payload.path, fingerprint=payload.fingerprint, error=error,
                ))

        # Terminal transition once all items are accounted for.
        job = self._repository.get_job(job_id)
        if (
            job is not None
            and job.status in ("queued", "running")
            and job.done >= job.total
        ):
            if job.failed > 0:
                self._repository.update_job(job_id, status="failed")
                self._emit({
                    "type": "job_failed", "job_id": job_id,
                    "done": job.done, "total": job.total, "failed": job.failed,
                })
            else:
                self._repository.update_job(job_id, status="done")
                self._emit({
                    "type": "job_completed", "job_id": job_id,
                    "done": job.done, "total": job.total, "failed": job.failed,
                })

    async def _process_clip(self, candidate: ClipCandidate) -> tuple[bool, str | None]:
        """Process a single clip through the orchestrator pipeline.

        Returns ``(success, error)`` — counters are updated by the caller.
        """
        name = Path(candidate.path).name
        logger.info("▶ Processing %s", name)
        self._emit({"type": "clip_started", "path": candidate.path})

        try:
            # process_clip is blocking (ffmpeg/whisper/OMLX); run it off the event
            # loop so the API (SSE, /jobs, /clips) stays responsive during a scan.
            clip_id = (
                await asyncio.to_thread(self._orchestrator.process_clip, candidate)
                if self._orchestrator else None
            )
            logger.info("✓ Finished %s%s", name, f" (clip #{clip_id})" if clip_id is not None else "")
            self._emit({
                "type": "clip_done",
                "path": candidate.path,
                **({"clip_id": clip_id} if clip_id is not None else {}),
            })
            return True, None

        except Exception as exc:  # noqa: BLE001 — error isolation
            logger.error("✗ Failed %s: %s", name, exc)
            self._emit({
                "type": "clip_error",
                "path": candidate.path,
                "error": str(exc),
            })
            return False, str(exc)

    async def _process_reanalyze(self, clip_id: int) -> tuple[bool, str | None]:
        """Re-analyze a single existing clip.

        Returns ``(success, error)`` — counters are updated by the caller.
        """
        logger.info("▶ Re-analyzing clip #%s", clip_id)
        self._emit({"type": "reanalyze_started", "clip_id": clip_id})

        try:
            # reanalyze is blocking (whisper/OMLX); run it off the event loop.
            success = (
                await asyncio.to_thread(self._orchestrator.reanalyze, clip_id)
                if self._orchestrator else True
            )
            if success:
                logger.info("✓ Re-analyzed clip #%s", clip_id)
                self._emit({"type": "reanalyze_done", "clip_id": clip_id})
                return True, None
            logger.warning("✗ Re-analyze returned False for clip #%s", clip_id)
            self._emit({"type": "reanalyze_error", "clip_id": clip_id})
            return False, "reanalyze returned False"

        except Exception as exc:  # noqa: BLE001 — error isolation
            self._emit({
                "type": "reanalyze_error",
                "clip_id": clip_id,
                "error": str(exc),
            })
            return False, str(exc)

    async def _process_keyframes(self, clip_id: int) -> tuple[bool, str | None]:
        """Generate keyframe suggestions for a single clip.

        Returns ``(success, error)`` — counters are updated by the caller.
        """
        logger.info("▶ Suggesting keyframes for clip #%s", clip_id)
        self._emit({"type": "keyframes_started", "clip_id": clip_id})
        try:
            ok = (
                await asyncio.to_thread(self._orchestrator.recommend_keyframes, clip_id)
                if self._orchestrator else True
            )
            if ok:
                logger.info("✓ Keyframes ready for clip #%s", clip_id)
                self._emit({"type": "keyframes_done", "clip_id": clip_id})
                return True, None
            logger.warning("✗ Keyframes returned False for clip #%s", clip_id)
            self._emit({"type": "keyframes_error", "clip_id": clip_id})
            return False, "keyframes returned False"
        except Exception as exc:  # noqa: BLE001 — error isolation
            self._emit({"type": "keyframes_error", "clip_id": clip_id, "error": str(exc)})
            return False, str(exc)



# ── Sentinel value for graceful shutdown ───────────────────────────

class _StopSentinel:
    """Marker object placed in the queue to signal worker shutdown."""

    def __repr__(self) -> str:
        return "<STOP>"


_STOP_SENTINEL = _StopSentinel()

# ── Public exports ────────────────────────────────────────────────


__all__ = [
    "WorkerQueue",
]
