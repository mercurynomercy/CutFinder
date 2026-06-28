"""Tests for the subtitle-export API routes in :mod:`cutfinder.api.routes`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes import FakeCatalogRepository


class _FakeQueue:
    """Minimal worker-queue stand-in for the subtitle routes."""

    def __init__(self, result: list[str] | None = None, model_ready: bool = True) -> None:
        self.enqueued: list[Any] = []
        self._result = result
        self._model_ready = model_ready

    async def enqueue_subtitle(self, req: Any, job_id: int | None = None) -> int:
        self.enqueued.append(req)
        return 7

    def get_subtitle_result(self, job_id: int) -> list[str] | None:
        return self._result

    def subtitle_model_ready(self) -> bool:
        return self._model_ready


def _client(
    repository: Any = None,
    worker_queue: Any = None,
    library_path: str | None = None,
) -> TestClient:
    from cutfinder.api.routes import _build_router as main_router

    ctx = SimpleNamespace(
        repository=repository, orchestrator=None, worker_queue=worker_queue,
        thumbnail_root=None, library_path=library_path,
    )
    app = FastAPI()
    app.include_router(main_router(ctx))
    return TestClient(app, raise_server_exceptions=False)


# ── POST /subtitles/export ───────────────────────────────────────────


def test_export_returns_job_id(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    queue = _FakeQueue()
    client = _client(repository=FakeCatalogRepository(), worker_queue=queue)

    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(video), "out_dir": str(tmp_path), "language": "en"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"job_id": 7}
    assert queue.enqueued and queue.enqueued[0].language == "en"


def test_export_503_without_worker(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    client = _client(worker_queue=None)
    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(video), "out_dir": str(tmp_path)},
    )
    assert resp.status_code == 503


def test_export_422_when_video_not_a_file(tmp_path: Path) -> None:
    client = _client(worker_queue=_FakeQueue())
    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(tmp_path / "missing.mp4"), "out_dir": str(tmp_path)},
    )
    assert resp.status_code == 422
    assert "video_path" in resp.json()["detail"]


def test_export_422_when_out_dir_not_a_directory(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    client = _client(worker_queue=_FakeQueue())
    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(video), "out_dir": str(tmp_path / "nope")},
    )
    assert resp.status_code == 422
    assert "out_dir" in resp.json()["detail"]


def test_export_defaults_language_to_zh(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    queue = _FakeQueue()
    client = _client(worker_queue=queue)
    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(video), "out_dir": str(tmp_path)},
    )
    assert resp.status_code == 200
    assert queue.enqueued[0].language == "zh"


def test_export_filters_unknown_formats(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    queue = _FakeQueue()
    client = _client(worker_queue=queue)
    resp = client.post(
        "/api/subtitles/export",
        json={"video_path": str(video), "out_dir": str(tmp_path), "formats": ["srt", "vtt"]},
    )
    assert resp.status_code == 200
    assert queue.enqueued[0].formats == ["srt"]


# ── GET /subtitles/model-ready ───────────────────────────────────────


def test_model_ready_true() -> None:
    client = _client(worker_queue=_FakeQueue(model_ready=True))
    resp = client.get("/api/subtitles/model-ready")
    assert resp.status_code == 200
    assert resp.json() == {"ready": True}


def test_model_ready_false() -> None:
    client = _client(worker_queue=_FakeQueue(model_ready=False))
    resp = client.get("/api/subtitles/model-ready")
    assert resp.status_code == 200
    assert resp.json() == {"ready": False}


def test_model_ready_true_without_worker() -> None:
    client = _client(worker_queue=None)
    resp = client.get("/api/subtitles/model-ready")
    assert resp.status_code == 200
    assert resp.json() == {"ready": True}


# ── GET /subtitles/{job_id} ──────────────────────────────────────────


def test_get_result_returns_files() -> None:
    repo = FakeCatalogRepository()
    job = repo.create_job(total=1, kind="subtitle")
    repo.update_job(job.id, status="done")
    queue = _FakeQueue(result=["/out/v.zh.itt", "/out/v.zh.srt"])
    client = _client(repository=repo, worker_queue=queue)

    resp = client.get(f"/api/subtitles/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["files"] == ["/out/v.zh.itt", "/out/v.zh.srt"]


def test_get_result_404_unknown_job() -> None:
    client = _client(repository=FakeCatalogRepository(), worker_queue=_FakeQueue())
    resp = client.get("/api/subtitles/999")
    assert resp.status_code == 404


def test_get_result_503_without_repository() -> None:
    client = _client(repository=None, worker_queue=_FakeQueue())
    resp = client.get("/api/subtitles/1")
    assert resp.status_code == 503


# ── POST /subtitles/{job_id}/reveal ──────────────────────────────────


def test_reveal_opens_parent_dir(monkeypatch: Any) -> None:
    calls: list[tuple[Any, ...]] = []

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return (b"", b"")

    async def _fake_exec(*args: Any, **_k: Any) -> Any:
        calls.append(args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    queue = _FakeQueue(result=["/out/v.zh.itt", "/out/v.zh.srt"])
    client = _client(worker_queue=queue)

    resp = client.post("/api/subtitles/5/reveal")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    # Opened the parent directory of the first file.
    assert calls and calls[0] == ("open", "/out")


def test_reveal_404_when_no_result() -> None:
    client = _client(worker_queue=_FakeQueue(result=None))
    resp = client.post("/api/subtitles/5/reveal")
    assert resp.status_code == 404


# ── POST /pick-file ──────────────────────────────────────────────────


def test_pick_file_returns_path(monkeypatch: Any) -> None:
    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return (b"/Users/me/Movies/final.mov\n", b"")

    async def _fake_exec(*_a: Any, **_k: Any) -> Any:
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    resp = _client().post("/api/pick-file")
    assert resp.status_code == 200
    assert resp.json() == {"path": "/Users/me/Movies/final.mov"}


def test_pick_file_cancel_returns_null(monkeypatch: Any) -> None:
    class _FakeProc:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return (b"", b"User canceled.")

    async def _fake_exec(*_a: Any, **_k: Any) -> Any:
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    resp = _client().post("/api/pick-file")
    assert resp.status_code == 200
    assert resp.json() == {"path": None}


def test_pick_file_missing_osascript_501(monkeypatch: Any) -> None:
    async def _fake_exec(*_a: Any, **_k: Any) -> Any:
        raise FileNotFoundError("osascript")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    resp = _client().post("/api/pick-file")
    assert resp.status_code == 501
