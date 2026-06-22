"""Tests for the rough-cut (cutplan) job in :mod:`cutfinder.pipeline.worker`."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cutfinder.pipeline.worker import WorkerQueue
from tests.fakes import FakeCatalogRepository


class _FakeCutService:
    """Records handle() calls; optionally raises to test failure isolation."""

    def __init__(self, should_fail: bool = False, has_plan: bool = True) -> None:
        self._should_fail = should_fail
        self._has_plan = has_plan
        self.calls: list[tuple[int, str, Any]] = []

    def handle(self, session_id: int, user_text: str, request: Any = None) -> Any:
        self.calls.append((session_id, user_text, request))
        if self._should_fail:
            raise RuntimeError("director boom")
        plan = object() if self._has_plan else None
        return type("R", (), {"assistant_text": "ok", "plan": plan})()


async def _drain(repo: FakeCatalogRepository, job_id: int) -> None:
    while True:
        job = repo.get_job(job_id)
        if job and job.status in ("done", "failed"):
            return
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_cutplan_job_runs_and_completes() -> None:
    repo = FakeCatalogRepository()
    svc = _FakeCutService()
    queue = WorkerQueue(repository=repo, cutplan_service=svc)
    await queue.start()

    job_id = await queue.enqueue_cutplan(3, "剪一条", None)
    await _drain(repo, job_id)
    await queue.stop()

    job = repo.get_job(job_id)
    assert job is not None and job.status == "done"
    assert job.kind == "cutplan"
    assert svc.calls == [(3, "剪一条", None)]


@pytest.mark.asyncio
async def test_cutplan_job_emits_events() -> None:
    repo = FakeCatalogRepository()
    events: list[dict[str, Any]] = []
    queue = WorkerQueue(
        repository=repo, cutplan_service=_FakeCutService(),
        progress_callback=lambda e: events.append(e),
    )
    await queue.start()
    job_id = await queue.enqueue_cutplan(1, "go")
    await _drain(repo, job_id)
    await queue.stop()

    assert any(e["type"] == "cutplan_started" for e in events)
    done = [e for e in events if e["type"] == "cutplan_done"]
    assert done and done[0]["has_plan"] is True


@pytest.mark.asyncio
async def test_cutplan_job_failure_marks_failed_without_crashing() -> None:
    repo = FakeCatalogRepository()
    queue = WorkerQueue(repository=repo, cutplan_service=_FakeCutService(should_fail=True))
    await queue.start()
    job_id = await queue.enqueue_cutplan(1, "go")
    await _drain(repo, job_id)
    await queue.stop()

    job = repo.get_job(job_id)
    assert job is not None and job.status == "failed"
    # No retryable failed item recorded for cutplan jobs.
    assert repo.get_failed_items(job_id) == []
