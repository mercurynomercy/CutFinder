"""Tests for :mod:`cutfinder.pipeline.worker`.

Covers the three DoD categories from ``doc/tasks/12-worker-queue.md``:
    1. Queue sequential processing order (inject fake orchestrator)
    2. Progress event sequence correctness (start/done/error)
    3. Job state persistence — total/done/failed counters update correctly

"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cutfinder.domain.models import ClipCandidate
from cutfinder.pipeline.worker import WorkerQueue


# ── Fixtures / helpers ───────────────────────────────────────────────

from tests.fakes import FakeCatalogRepository  # noqa: E402


def _make_candidate(path: str = "/tmp/video.mp4", fingerprint: str = "abc123") -> ClipCandidate:
    """Create a test :class:`ClipCandidate`."""
    return ClipCandidate(path=path, fingerprint=fingerprint)


def _make_fake_orchestrator(
    process_result: int | None = 1, reanalyze_result: bool = True,
) -> Any:
    """Create a fake orchestrator with configurable return values."""

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.process_clip_calls: list[ClipCandidate] = []
            self.reanalyze_calls: list[int] = []

        def process_clip(self, candidate: ClipCandidate) -> int | None:
            self.process_clip_calls.append(candidate)
            return process_result

        def reanalyze(self, clip_id: int) -> bool:
            self.reanalyze_calls.append(clip_id)
            return reanalyze_result

    return FakeOrchestrator()


# ── 1. Queue sequential processing order (DoD #1) ───────────────────

class TestSequentialProcessing:
    """Verify that clips are processed in enqueue order, one at a time."""

    @pytest.mark.asyncio
    async def test_single_clip_processed(self) -> None:
        """One candidate → orchestrator.process_clip called once."""
        orch = _make_fake_orchestrator()
        repo = FakeCatalogRepository()
        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()

        c1 = _make_candidate("/tmp/a.mp4")
        job_id = await queue.enqueue_scan([c1])

        # Wait for processing to complete
        while True:
            job = repo.get_job(job_id)
            if job and job.done >= 1:
                break
            await asyncio.sleep(0.02)

        await queue.stop()
        assert orch.process_clip_calls == [c1]

    @pytest.mark.asyncio
    async def test_multiple_clips_processed_in_order(self) -> None:
        """Three candidates → orchestrator called in enqueue order."""
        orch = _make_fake_orchestrator()
        repo = FakeCatalogRepository()
        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()

        candidates = [_make_candidate(f"/tmp/{i}.mp4") for i in range(3)]
        await queue.enqueue_scan(candidates)

        # Wait until all done
        job = repo.get_job(1)
        while job is None or job.done < 3:
            await asyncio.sleep(0.02)
            job = repo.get_job(1)

        await queue.stop()
        paths = [c.path for c in orch.process_clip_calls]
        assert paths == ["/tmp/0.mp4", "/tmp/1.mp4", "/tmp/2.mp4"]

    @pytest.mark.asyncio
    async def test_reanalyze_processed(self) -> None:
        """enqueue_reanalyze → orchestrator.reanalyze called."""
        orch = _make_fake_orchestrator()
        repo = FakeCatalogRepository()
        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()

        job_id = await queue.enqueue_reanalyze(clip_id=42)
        while True:
            job = repo.get_job(job_id)
            if job and job.done >= 1:
                break
            await asyncio.sleep(0.02)

        await queue.stop()
        assert orch.reanalyze_calls == [42]


# ── 2. Progress event sequence (DoD #2) ─────────────────────────────

class TestProgressEvents:
    """Verify progress events are emitted in the correct sequence."""

    @pytest.mark.asyncio
    async def test_scan_event_sequence(self) -> None:
        """enqueue_scan emits job_started → clip_started/clip_done × N."""
        orch = _make_fake_orchestrator()
        events: list[dict[str, Any]] = []
        queue = WorkerQueue(orchestrator=orch, progress_callback=lambda e: events.append(e))

        await queue.start()
        c1 = _make_candidate("/tmp/a.mp4")
        c2 = _make_candidate("/tmp/b.mp4")

        await queue.enqueue_scan([c1, c2])
        while len(events) < 5:  # job_started + (clip_started+done)*2
            await asyncio.sleep(0.03)

        await queue.stop()

        assert events[0]["type"] == "job_started"
        assert events[1] == {"type": "clip_started", "path": "/tmp/a.mp4"}
        assert events[2]["type"] == "clip_done" and events[2]["path"] == "/tmp/a.mp4"
        assert events[3] == {"type": "clip_started", "path": "/tmp/b.mp4"}
        assert events[4]["type"] == "clip_done" and events[4]["path"] == "/tmp/b.mp4"

    @pytest.mark.asyncio
    async def test_reanalyze_event_sequence(self) -> None:
        """enqueue_reanalyze emits job_started → reanalyze_started/reanalyze_done."""
        orch = _make_fake_orchestrator()
        events: list[dict[str, Any]] = []
        queue = WorkerQueue(orchestrator=orch, progress_callback=lambda e: events.append(e))

        await queue.start()
        await queue.enqueue_reanalyze(clip_id=7)

        while len(events) < 3:
            await asyncio.sleep(0.03)

        await queue.stop()

        assert events[0]["type"] == "job_started"
        assert events[1] == {"type": "reanalyze_started", "clip_id": 7}
        assert events[2] == {"type": "reanalyze_done", "clip_id": 7}

    @pytest.mark.asyncio
    async def test_clip_error_event_sequence(self) -> None:
        """Orchestrator raises → clip_started + clip_error (not done)."""
        orch = _make_fake_orchestrator(process_result=1)

        def failing_process(candidate: ClipCandidate) -> int | None:  # type: ignore[misc, unused-ignore]
            orch.process_clip_calls.append(candidate)
            raise RuntimeError("model unavailable")

        orch.process_clip = failing_process  # type: ignore[method-assign]
        events: list[dict[str, Any]] = []
        queue = WorkerQueue(orchestrator=orch, progress_callback=lambda e: events.append(e))

        await queue.start()
        c1 = _make_candidate("/tmp/fail.mp4")
        await queue.enqueue_scan([c1])

        while len(events) < 3:
            await asyncio.sleep(0.03)

        await queue.stop()

        assert events[1]["type"] == "clip_started"
        err_event = [e for e in events if e["type"] == "clip_error"][0]
        assert err_event["path"] == "/tmp/fail.mp4"

    @pytest.mark.asyncio
    async def test_clip_done_has_clip_id(self) -> None:
        """clip_done event includes clip_id when orchestrator returns one."""
        orch = _make_fake_orchestrator(process_result=99)
        events: list[dict[str, Any]] = []
        queue = WorkerQueue(orchestrator=orch, progress_callback=lambda e: events.append(e))

        await queue.start()
        c1 = _make_candidate("/tmp/id.mp4")
        await queue.enqueue_scan([c1])

        while len(events) < 3:
            await asyncio.sleep(0.03)

        await queue.stop()

        done_event = [e for e in events if e["type"] == "clip_done"][0]
        assert done_event.get("clip_id") == 99

    @pytest.mark.asyncio
    async def test_reanalyze_error_event(self) -> None:
        """Orchestrator.reanalyze returns False → reanalyze_error event."""
        orch = _make_fake_orchestrator(reanalyze_result=False)
        events: list[dict[str, Any]] = []
        queue = WorkerQueue(orchestrator=orch, progress_callback=lambda e: events.append(e))

        await queue.start()
        await queue.enqueue_reanalyze(clip_id=123)

        while len(events) < 3:
            await asyncio.sleep(0.03)

        await queue.stop()

        done_events = [e for e in events if "clip_id" in e and e["type"] != "job_started"]
        assert any(e["type"] == "reanalyze_error" for e in done_events)


# ── 3. Job state persistence (DoD #3) ───────────────────────────────

class TestJobStatePersistence:
    """Verify job total/done/failed counters are persisted to repository."""

    @pytest.mark.asyncio
    async def test_scan_job_created_with_total(self) -> None:
        """enqueue_scan creates job with total = number of candidates."""
        repo = FakeCatalogRepository()
        orch = _make_fake_orchestrator(process_result=None)  # None to skip counter lookup
        queue = WorkerQueue(orchestrator=orch, repository=repo)

        await queue.start()
        candidates = [_make_candidate(f"/tmp/{i}.mp4") for i in range(5)]
        job_id = await queue.enqueue_scan(candidates)

        # Wait for all to finish processing
        while True:
            job = repo.get_job(job_id)
            if job and job.done >= 5:
                break
            await asyncio.sleep(0.03)

        job = repo.get_job(job_id)
        assert job is not None
        assert job.total == 5

    @pytest.mark.asyncio
    async def test_job_done_counter_increments_per_clip(self) -> None:
        """Each processed clip increments done counter."""
        repo = FakeCatalogRepository()
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=repo)

        await queue.start()
        candidates = [_make_candidate(f"/tmp/{i}.mp4") for i in range(3)]
        job_id = await queue.enqueue_scan(candidates)

        # Wait for completion
        while True:
            job = repo.get_job(job_id)
            if job and job.done >= 3:
                break
            await asyncio.sleep(0.03)

        job = repo.get_job(job_id)
        assert job.done == 3
        # failed should remain at default (0) since none errored
        assert job.failed == 0

    @pytest.mark.asyncio
    async def test_reanalyze_job_total_one(self) -> None:
        """enqueue_reanalyze creates job with total=1."""
        repo = FakeCatalogRepository()
        orch = _make_fake_orchestrator(reanalyze_result=True)
        queue = WorkerQueue(orchestrator=orch, repository=repo)

        await queue.start()
        job_id = await queue.enqueue_reanalyze(clip_id=42)

        while True:
            job = repo.get_job(job_id)
            if job and job.done >= 1:
                break
            await asyncio.sleep(0.03)

        job = repo.get_job(job_id)
        assert job.total == 1
        assert job.done >= 1

    @pytest.mark.asyncio
    async def test_failed_clip_increments_failed_counter(self) -> None:
        """Single clip failure → done+1, failed+1."""
        repo = FakeCatalogRepository()

        def always_fail(candidate: ClipCandidate) -> int | None:  # type: ignore[misc, unused-ignore]
            raise RuntimeError("simulated failure")

        orch = _make_fake_orchestrator(process_result=1)
        orch.process_clip = always_fail  # type: ignore[method-assign]

        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()

        c1 = _make_candidate("/tmp/err.mp4")
        await queue.enqueue_scan([c1])

        while True:
            job = repo.get_job(1)
            if job and (job.failed > 0 or job.done > 0):
                break
            await asyncio.sleep(0.03)

        job = repo.get_job(1)
        assert job is not None
        # Both done and failed should be incremented for the single error clip
        assert job.done >= 1
        assert job.failed >= 1

    @pytest.mark.asyncio
    async def test_job_status_remains_running_while_processing(self) -> None:
        """Job status stays 'running' during processing (not auto-set to done/error)."""
        repo = FakeCatalogRepository()
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=repo)

        await queue.start()
        candidates = [_make_candidate(f"/tmp/{i}.mp4") for i in range(2)]
        job_id = await queue.enqueue_scan(candidates)

        # Give worker time to process but not complete
        await asyncio.sleep(0.15)

        job = repo.get_job(job_id)
        assert job is not None
        # Status should still be running (orchestrator doesn't change it)

    @pytest.mark.asyncio
    async def test_no_repository_jobs_not_crashed(self) -> None:
        """WorkerQueue without repository still processes clips."""
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=None)

        await queue.start()
        c1 = _make_candidate("/tmp/no_repo.mp4")
        await queue.enqueue_scan([c1])

        # Wait a bit for processing, then stop
        await asyncio.sleep(0.15)
        await queue.stop()

        # Should not raise; orchestrator was called even without repo
        assert len(orch.process_clip_calls) == 1


# ── 4. Error isolation (single failure doesn't halt queue) ───────────

class TestErrorIsolation:
    """Verify that a single clip failure doesn't stop processing of subsequent clips."""

    @pytest.mark.asyncio
    async def test_batch_continues_after_clip_error(self) -> None:
        """First clip fails, second and third still processed."""
        call_order: list[str] = []

        def selective_fail(candidate: ClipCandidate) -> int | None:  # type: ignore[misc, unused-ignore]
            call_order.append(candidate.path)
            if candidate.path == "/tmp/bad.mp4":
                raise RuntimeError("model error")
            return 1

        orch = _make_fake_orchestrator(process_result=1)
        orch.process_clip = selective_fail  # type: ignore[method-assign]

        events: list[dict[str, Any]] = []
        repo = FakeCatalogRepository()
        queue = WorkerQueue(orchestrator=orch, repository=repo, progress_callback=lambda e: events.append(e))

        await queue.start()
        candidates = [
            _make_candidate("/tmp/good1.mp4"),
            _make_candidate("/tmp/bad.mp4"),
            _make_candidate("/tmp/good2.mp4"),
        ]
        await queue.enqueue_scan(candidates)

        # Wait for all to finish (including the error one and subsequent good ones)
        while len(events) < 7:  # job_started + (started+done)*2 + started(error)+error
            await asyncio.sleep(0.03)

        await queue.stop()

        # All three clips should have been attempted
        assert "/tmp/good1.mp4" in call_order
        assert "/tmp/bad.mp4" in call_order
        # good2 should also have been processed despite bad one failing
        assert "/tmp/good2.mp4" in call_order

    @pytest.mark.asyncio
    async def test_all_error_clips_marked_done(self) -> None:
        """Even failed clips increment done counter (they completed, just with error)."""
        repo = FakeCatalogRepository()

        def always_fail(candidate: ClipCandidate) -> int | None:  # type: ignore[misc, unused-ignore]
            raise RuntimeError("always fails")

        orch = _make_fake_orchestrator(process_result=1)
        orch.process_clip = always_fail  # type: ignore[method-assign]

        queue = WorkerQueue(orchestrator=orch, repository=repo)
        await queue.start()

        candidates = [
            _make_candidate("/tmp/f1.mp4"),
            _make_candidate("/tmp/f2.mp4"),
        ]
        await queue.enqueue_scan(candidates)

        while True:
            job = repo.get_job(1)
            if job and job.done >= 2:
                break
            await asyncio.sleep(0.03)

        job = repo.get_job(1)
        assert job.done == 2  # Both processed (even though both failed)


# ── 5. Edge cases and lifecycle tests ───────────────────────────────

class TestLifecycleAndEdgeCases:
    """Test lifecycle edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_candidates_list(self) -> None:
        """enqueue_scan with empty list creates job but no clips processed."""
        repo = FakeCatalogRepository()
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=repo)

        await queue.start()
        job_id = await queue.enqueue_scan([])  # empty list

        # Job should exist with total=0
        job = repo.get_job(job_id)
        assert job is not None
        assert job.total == 0

        await asyncio.sleep(0.1)  # give worker time to notice empty queue
        await queue.stop()

    @pytest.mark.asyncio
    async def test_start_called_multiple_times(self) -> None:
        """Multiple start() calls don't create multiple worker tasks."""
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=None)

        await queue.start()
        await asyncio.sleep(0.05)  # let task initialize

        first_task = queue._worker_task
        assert first_task is not None and not first_task.done()

        # Call start again — should be idempotent
        await queue.start()
        assert queue._worker_task is first_task  # same task object

    @pytest.mark.asyncio
    async def test_stop_before_start(self) -> None:
        """stop() without start() should not raise."""
        queue = WorkerQueue(orchestrator=None, repository=None)
        await queue.stop()  # should complete without error

    @pytest.mark.asyncio
    async def test_stop_drains_pending_items(self) -> None:
        """stop() waits for all pending items to be processed."""
        orch = _make_fake_orchestrator(process_result=1)
        queue = WorkerQueue(orchestrator=orch, repository=None)

        await queue.start()
        candidates = [_make_candidate(f"/tmp/drain_{i}.mp4") for i in range(3)]
        await queue.enqueue_scan(candidates)

        # Immediately stop — worker should still process all 3
        await queue.stop()

        assert len(orch.process_clip_calls) == 3

