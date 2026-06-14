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
from typing import Any, Callable

from cutfinder.domain.models import (
    ClipCandidate,
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

    subscribers: dict[str, asyncio.Queue] = field(default_factory=dict)
    wait_event: asyncio.Event = field(default_factory=asyncio.Event)
    _next_id: int = 0

    def add(self) -> tuple[str, asyncio.Queue]:
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
    ) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._repository = repository
        self._progress_callback = progress_callback

        # SSE event stream (lazy-initialized on first subscribe)
        self._stream: _EventStream | None = None

        # Reference to orchestrator (may be None)
        self._orchestrator = orchestrator

        # Track the current job being processed (for counter updates)
        self._current_job_id: int | None = None

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the background worker task.

        Safe to call multiple times — subsequent calls are no-ops
        if the worker is already running.
        """
        if self._worker_task and not self._worker_task.done():
            # Already running — idempotent no-op.
            return
        if self._worker_task and self._worker_task.done():
            # Re-raise any exception from a finished task.
            self._worker_task.result()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Signal the worker to drain remaining items and exit.

        Awaits the worker task so all enqueued work is completed
        before returning.  Safe to call even if ``start()`` was never
        called or the worker is already stopped.
        """
        self._queue.put_nowait(_STOP_SENTINEL)
        if self._worker_task and not self._worker_task.done():
            await self._worker_task
        self._worker_task = None

    # ── Job submission (public API) ──────────────────────────────

    async def enqueue_scan(
        self,
        candidates: list[ClipCandidate],
        job_id: int | None = None,
    ) -> int:
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
            if job_id is not None and (existing := self._repository.get_job(job_id)):
                pass  # reuse existing job record
            elif job_id is None:
                job = self._repository.create_job(total=len(candidates))  # type: ignore[union-attr]
                job_id = job.id

        self._current_job_id = job_id  # track for counter updates in _process_clip

        # Emit progress events for batch start and per-clip processing
        self._emit({"type": "job_started", "job_id": job_id, "total": len(candidates)})

        for candidate in candidates:
            await self._queue.put(("clip", candidate))  # type: ignore[arg-type]

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
            if job_id is not None and (existing := self._repository.get_job(job_id)):
                pass  # reuse existing job record
            elif job_id is None:
                job = self._repository.create_job(total=1)  # type: ignore[union-attr]
                job_id = job.id

        self._current_job_id = job_id  # track for counter updates in _process_reanalyze
        self._emit({"type": "job_started", "job_id": job_id, "total": 1})
        await self._queue.put(("reanalyze", clip_id))

        return job_id  # pyright: ignore[reportPossiblyUnboundVariable]

    async def enqueue_clip(self, candidate: ClipCandidate) -> None:
        """Enqueue a single clip for processing (no job tracking).

        Parameters
        ----------
        candidate:
            A :class:`ClipCandidate` to process.

        """
        await self._queue.put(("clip", candidate))  # type: ignore[arg-type]

    async def enqueue_reanalyze_task(self, clip_id: int) -> None:
        """Enqueue a single re-analysis task (no job tracking).

        Parameters
        ----------
        clip_id:
            Database ID of the existing processed clip.

        """
        await self._queue.put(("reanalyze", clip_id))  # type: ignore[arg-type]

    # ── SSE subscriber management ────────────────────────────────

    def subscribe(self) -> tuple[str, asyncio.Queue]:
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
        try:
            while True:
                item = await self._queue.get()

                # Stop sentinel — drain remaining then exit
                if isinstance(item, type(_STOP_SENTINEL)):
                    self._queue.task_done()
                    break

                kind, payload = item  # type: ignore[misc]

                try:
                    if kind == "clip":
                        await self._process_clip(payload)  # type: ignore[arg-type]
                    elif kind == "reanalyze":
                        await self._process_reanalyze(payload)  # type: ignore[arg-type]

                except Exception as exc:  # noqa: BLE001 — error isolation per clip
                    logger.error(
                        "Worker processing error (continuing): %s", exc, exc_info=True,
                    )

                self._queue.task_done()

        except asyncio.CancelledError:
            # Normal shutdown — drain remaining items if possible
            pass

    async def _process_clip(self, candidate: ClipCandidate) -> None:
        """Process a single clip through the orchestrator pipeline."""
        self._emit({"type": "clip_started", "path": candidate.path})

        try:
            clip_id = self._orchestrator.process_clip(candidate) if self._orchestrator else None

            # Update job counters (current job only)
            if self._repository and self._current_job_id is not None:
                job = self._repository.get_job(self._current_job_id)  # type: ignore[union-attr]
                if job is not None:
                    self._repository.update_job(self._current_job_id, done=job.done + 1)

            # Emit completion event with clip_id
            self._emit({
                "type": "clip_done",
                "path": candidate.path,
                **({"clip_id": clip_id} if clip_id is not None else {}),
            })

        except Exception as exc:  # noqa: BLE001 — error isolation
            self._emit({
                "type": "clip_error",
                "path": candidate.path,
                "error": str(exc),
            })

            # Update job counters on failure (current job only)
            if self._repository and self._current_job_id is not None:
                job = self._repository.get_job(self._current_job_id)  # type: ignore[union-attr]
                if job is not None:
                    self._repository.update_job(
                        self._current_job_id, done=job.done + 1, failed=job.failed + 1,
                    )

    async def _process_reanalyze(self, clip_id: int) -> None:
        """Re-analyze a single existing clip."""
        self._emit({"type": "reanalyze_started", "clip_id": clip_id})

        try:
            success = (
                self._orchestrator.reanalyze(clip_id) if self._orchestrator else True
            )

            # Update job counters (current job only)
            if self._repository and self._current_job_id is not None:
                job = self._repository.get_job(self._current_job_id)  # type: ignore[union-attr]
                if job is not None:
                    self._repository.update_job(self._current_job_id, done=job.done + 1)

            if success:
                self._emit({"type": "reanalyze_done", "clip_id": clip_id})
            else:
                self._emit({"type": "reanalyze_error", "clip_id": clip_id})

        except Exception as exc:  # noqa: BLE001 — error isolation
            self._emit({
                "type": "reanalyze_error",
                "clip_id": clip_id,
                "error": str(exc),
            })

            if self._repository and self._current_job_id is not None:
                job = self._repository.get_job(self._current_job_id)  # type: ignore[union-attr]
                if job is not None:
                    self._repository.update_job(
                        self._current_job_id, done=job.done + 1, failed=job.failed + 1,
                    )



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
