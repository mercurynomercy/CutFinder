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

    def __init__(self, paths: list[str] | None = None, should_fail: bool = False) -> None:
        self._paths = paths or ["/out/v.zh.itt", "/out/v.zh.srt"]
        self._should_fail = should_fail
        self.calls: list[tuple[Path, Path, list[str], str]] = []

    def export(
        self, video_path: Path, out_dir: Path, formats: list[str], language: str,
    ) -> list[Path]:
        self.calls.append((video_path, out_dir, formats, language))
        if self._should_fail:
            raise RuntimeError("export boom")
        return [Path(p) for p in self._paths]


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
