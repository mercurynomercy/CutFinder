"""Tests for the standalone subtitle-export job in :mod:`cutfinder.pipeline.worker`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from cutfinder.domain.models import SubtitleRequest
from cutfinder.pipeline.worker import WorkerQueue
from tests.fakes import FakeCatalogRepository


class _FakeExporter:
    """Records export calls and returns preset paths (or raises)."""

    def __init__(
        self,
        paths: list[str] | None = None,
        should_fail: bool = False,
        progress_values: list[float] | None = None,
    ) -> None:
        self._paths = paths or ["/out/v.zh.itt", "/out/v.zh.srt"]
        self._should_fail = should_fail
        self._progress_values = progress_values or []
        self.calls: list[tuple[Path, Path, list[str], str]] = []

    def export(
        self,
        video_path: Path,
        out_dir: Path,
        formats: list[str],
        language: str,
        *,
        on_progress: Any = None,
    ) -> list[Path]:
        self.calls.append((video_path, out_dir, formats, language))
        if on_progress is not None:
            for f in self._progress_values:
                on_progress(f)
        if self._should_fail:
            raise RuntimeError("export boom")
        return [Path(p) for p in self._paths]


def test_subtitle_model_ready_delegates_to_exporter() -> None:
    exporter = _FakeExporter()
    exporter.model_ready = lambda: False  # type: ignore[attr-defined]
    queue = WorkerQueue(subtitle_exporter=exporter)
    assert queue.subtitle_model_ready() is False


def test_subtitle_model_ready_true_without_exporter() -> None:
    queue = WorkerQueue(subtitle_exporter=None)
    assert queue.subtitle_model_ready() is True


def _req() -> SubtitleRequest:
    return SubtitleRequest(
        video_path="/tmp/v.mp4", out_dir="/out", formats=["itt", "srt"], language="zh",
    )


@pytest.mark.asyncio
async def test_subtitle_job_runs_and_stores_result() -> None:
    repo = FakeCatalogRepository()
    exporter = _FakeExporter()
    queue = WorkerQueue(repository=repo, subtitle_exporter=exporter)
    await queue.start()

    job_id = await queue.enqueue_subtitle(_req())
    while True:
        job = repo.get_job(job_id)
        if job and job.status in ("done", "failed"):
            break
        await asyncio.sleep(0.02)

    await queue.stop()

    job = repo.get_job(job_id)
    assert job is not None and job.status == "done"
    assert queue.get_subtitle_result(job_id) == ["/out/v.zh.itt", "/out/v.zh.srt"]
    assert exporter.calls and exporter.calls[0][3] == "zh"


@pytest.mark.asyncio
async def test_subtitle_job_emits_events() -> None:
    repo = FakeCatalogRepository()
    events: list[dict[str, Any]] = []
    queue = WorkerQueue(
        repository=repo, subtitle_exporter=_FakeExporter(),
        progress_callback=lambda e: events.append(e),
    )
    await queue.start()

    job_id = await queue.enqueue_subtitle(_req())
    while True:
        job = repo.get_job(job_id)
        if job and job.status in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    await queue.stop()

    assert any(e["type"] == "subtitle_started" for e in events)
    done = [e for e in events if e["type"] == "subtitle_done"]
    assert done and done[0]["files"] == ["/out/v.zh.itt", "/out/v.zh.srt"]


@pytest.mark.asyncio
async def test_subtitle_job_created_with_total_100() -> None:
    repo = FakeCatalogRepository()
    queue = WorkerQueue(repository=repo, subtitle_exporter=_FakeExporter())

    job_id = await queue.enqueue_subtitle(_req())

    job = repo.get_job(job_id)
    assert job is not None and job.total == 100


@pytest.mark.asyncio
async def test_subtitle_progress_throttled_and_emitted() -> None:
    repo = FakeCatalogRepository()
    events: list[dict[str, Any]] = []
    # 0.005 (pct 0) collapses into the prior pct-0 emit → throttled out.
    exporter = _FakeExporter(progress_values=[0.0, 0.005, 0.01, 0.5, 1.0])
    queue = WorkerQueue(
        repository=repo, subtitle_exporter=exporter,
        progress_callback=lambda e: events.append(e),
    )
    await queue.start()

    job_id = await queue.enqueue_subtitle(_req())
    while True:
        job = repo.get_job(job_id)
        if job and job.status in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    await queue.stop()

    dones = [e["done"] for e in events if e["type"] == "job_progress"]
    # Rapid duplicate-percent calls collapse; distinct percents pass through.
    assert dones == [0, 1, 50, 100]
    assert all(e["total"] == 100 for e in events if e["type"] == "job_progress")
    # Final completion lands done at total.
    job = repo.get_job(job_id)
    assert job is not None and job.status == "done" and job.done == 100


@pytest.mark.asyncio
async def test_subtitle_job_failure_marks_failed_without_crashing() -> None:
    repo = FakeCatalogRepository()
    queue = WorkerQueue(
        repository=repo, subtitle_exporter=_FakeExporter(should_fail=True),
    )
    await queue.start()

    job_id = await queue.enqueue_subtitle(_req())
    while True:
        job = repo.get_job(job_id)
        if job and job.status in ("done", "failed"):
            break
        await asyncio.sleep(0.02)

    await queue.stop()

    job = repo.get_job(job_id)
    assert job is not None and job.status == "failed"
    # Subtitle failures record no retryable item (payload is not a ClipCandidate).
    assert repo.get_failed_items(job_id) == []
    assert queue.get_subtitle_result(job_id) is None
