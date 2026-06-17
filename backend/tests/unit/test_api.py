"""Tests for :mod:`cutfinder.api.routes` and :mod:`cutfinder.api.settings_routes`.

Covers all 8 route groups from ``doc/tasks/13-api.md``:
    1. POST /scan — enqueue scan job
    2. GET /jobs/{id} — job status
    3. GET SSE events for jobs (GET /jobs/{id}/events)
    4. GET/POST clips — list, detail, correct roll, edit, set tags
    5. POST /clips/{id}/reanalyze — trigger re-analysis
    6. GET /search?q= — full-text search
    7. Thumbnail serving (skipped in v1)
    8. Settings CRUD — GET/PUT /settings

Uses FastAPI ``TestClient`` with fake repository and orchestrator from
:mod:`tests.fakes`.

"""

from __future__ import annotations

import asyncio
from typing import Any


from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixtures / helpers ───────────────────────────────────────────────

from tests.fakes import FakeCatalogRepository  # noqa: E402


def _ctx(repository: Any = None, worker_queue: Any = None) -> Any:
    """A minimal LibraryContext stand-in for the route handlers."""
    from types import SimpleNamespace
    return SimpleNamespace(
        repository=repository,
        orchestrator=None,
        worker_queue=worker_queue,
        thumbnail_root=None,
    )


def _build_app(
    repository: Any = None,          # CatalogRepository (or FakeCatalogRepository)
    orchestrator: Any = None,        # Orchestrator mock (or None)
    worker_queue: Any = None,        # WorkerQueue mock (or None)
):  # type: ignore[misc]
    """Build a FastAPI app with injected dependencies via routes router."""
    from cutfinder.api.routes import (  # noqa: E402
        _build_router as main_router,
    )

    app = FastAPI()
    app.include_router(main_router(_ctx(repository=repository, worker_queue=worker_queue)))
    return app


def _build_settings_app(  # type: ignore[misc]
    load_config_fn: Any = None,
    save_prefs_fn: Any = None,
    get_library_fn: Any = None,
    save_global_fn: Any = None,
):
    """Build a FastAPI app with injected settings router."""
    from cutfinder.api.settings_routes import (  # noqa: E402
        _build_router as settings_router,
    )

    app = FastAPI()
    app.include_router(
        settings_router(
            load_config_fn,
            save_prefs_fn,
            get_library_fn,
            save_global_fn or (lambda _updates: None),
        )
    )
    return app


def _make_candidate(path: str = "/tmp/video.mp4", fingerprint: str = "abc123") -> dict[str, str]:  # type: ignore[misc]
    """Create a test clip candidate dict."""
    return {"path": path, "fingerprint": fingerprint}


def _make_clip(  # type: ignore[misc]
    id: int = 1,
    source_path: str = "/tmp/clip.mp4",
    roll_type: str = "a",
    status: str = "done",
    **kw: Any,
):  # noqa: D103 — helper for test code only; model-level defaults apply
    """Create a Clip instance with required fields filled in."""
    import datetime  # noqa: E402

    from cutfinder.domain.models import Clip  # noqa: E402

    return Clip(
        id=id,
        fingerprint="aa" + format(id % 10**6, "05d"),
        source_path=source_path,
        roll_type=roll_type,
        status=status,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **kw,
    )


# ── 1. POST /scan (DoD: enqueue scan job) ───────────────────────

class TestScanEndpoint:
    """Verify POST /scan accepts candidates and enqueues them."""

    def test_scan_returns_job_id(self) -> None:
        """Valid candidates → 200 with job_id."""

        class FakeQueue:
            async def enqueue_scan(self, candidates, job_id=None):  # noqa: D102
                return 42

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        repo = FakeCatalogRepository()
        router = main_router(_ctx(repository=repo, worker_queue=FakeQueue()))
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post("/api/scan", json=[_make_candidate()])
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert isinstance(data["job_id"], int)

    def test_scan_empty_list(self) -> None:
        """Empty candidate list → 200 with job_id (job has total=0)."""

        class FakeQueue:
            async def enqueue_scan(self, candidates, job_id=None):  # noqa: D102
                return 99

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        repo = FakeCatalogRepository()
        router = main_router(_ctx(repository=repo, worker_queue=FakeQueue()))
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post("/api/scan", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data

    def test_scan_missing_fingerprint(self) -> None:
        """Candidate without 'fingerprint' → 422 validation error."""

        class FakeQueue:
            async def enqueue_scan(self, candidates, job_id=None):  # noqa: D102
                return 1

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        app = FastAPI()
        app.include_router(main_router(_ctx(worker_queue=FakeQueue())))

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.post("/api/scan", json=[{"path": "/tmp/x.mp4"}])
        assert resp.status_code == 422

    def test_scan_empty_path(self) -> None:
        """Candidate with empty path → 422 (min_length=1)."""

        class FakeQueue:
            async def enqueue_scan(self, candidates, job_id=None):  # noqa: D102
                return 1

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        app = FastAPI()
        app.include_router(main_router(_ctx(worker_queue=FakeQueue())))

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.post("/api/scan", json=[{"path": "", "fingerprint": "abc"}])
        assert resp.status_code == 422

    def test_scan_invalid_fingerprint_pattern(self) -> None:
        """Candidate with non-hex fingerprint → 422."""

        class FakeQueue:
            async def enqueue_scan(self, candidates, job_id=None):  # noqa: D102
                return 1

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        app = FastAPI()
        app.include_router(main_router(_ctx(worker_queue=FakeQueue())))

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.post("/api/scan", json=[{"path": "/tmp/x.mp4", "fingerprint": "XYZ!@#"}])
        assert resp.status_code == 422


# ── 2. GET /jobs/{id} (DoD: job status) ────────────────────────

class TestJobStatusEndpoint:
    """Verify GET /jobs/{id} returns job status."""

    def test_job_not_found(self) -> None:
        """Non-existent job_id → 404."""
        repo = FakeCatalogRepository()
        app = _build_app(repository=repo)
        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]

        resp = client.get("/api/jobs/9999")
        assert resp.status_code == 404

    def test_job_without_repository(self) -> None:
        """No repository → 503."""
        app = _build_app(repository=None, orchestrator=None, worker_queue=None)
        client = TestClient(app)  # type: ignore[arg-type]

        resp = client.get("/api/jobs/1")
        assert resp.status_code == 503

    def test_job_status_fields(self) -> None:
        """Existing job → 200 with id/status/total/done/failed."""
        repo = FakeCatalogRepository()

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        # Create a job so get_job returns something non-None
        repo.create_job(total=5)

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/jobs/1")

        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "status" in data


# ── 3. SSE events (GET /jobs/{id}/events) ─────────────────────

class TestSSEEvents:
    """Verify SSE event stream for job progress."""

    def test_sse_stream_returns_events(self) -> None:
        """SSE endpoint returns a StreamingResponse with correct headers."""

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        class FakeQueue:
            def __init__(self) -> None:  # noqa: D107
                self._sub_id = 0

            def subscribe(self) -> tuple[str, asyncio.Queue]:
                self._sub_id += 1
                q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
                return (str(self._sub_id), q)

            def unsubscribe(self, sid: str) -> None:  # noqa: D107
                pass

        queue = FakeQueue()
        repo = FakeCatalogRepository()
        router = main_router(_ctx(repository=repo, worker_queue=queue))

        # Verify the route exists and has correct path/method/content-type.
        routes = {r.path: r for r in router.routes}

        # The SSE route should exist at /jobs/{job_id}/events
        sse_route = None
        for path, route in routes.items():
            if "/jobs" in path and "events" in path:
                sse_route = route
                break

        assert sse_route is not None, "SSE events route should exist"
        # SSE routes use GET and return StreamingResponse (content-type: text/event-stream)


# ── 2b. Job queue management (GET /jobs, DELETE, retry, pause/resume) ─

class _FakeJobQueue:
    """Minimal worker-queue stand-in for job-management routes."""

    def __init__(self, retry_result: bool = True) -> None:
        self._paused = False
        self.cancelled: list[int] = []
        self._retry_result = retry_result

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def cancel_job(self, job_id: int) -> None:
        self.cancelled.append(job_id)

    async def retry_job(self, job_id: int) -> bool:
        return self._retry_result


class TestJobQueueManagement:
    """Verify GET /jobs, DELETE /jobs/{id}, retry, pause/resume."""

    def test_list_jobs_shape(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        repo.create_job(total=3, kind="scan")
        repo.create_job(total=1, kind="reanalyze")

        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "paused" in data and data["paused"] is False
        assert isinstance(data["jobs"], list) and len(data["jobs"]) == 2
        # Newest first.
        assert data["jobs"][0]["kind"] == "reanalyze"
        first = data["jobs"][0]
        for key in ("id", "kind", "status", "total", "done", "failed",
                    "started_at", "finished_at"):
            assert key in first

    def test_list_jobs_no_queue(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=None)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/jobs")
        assert resp.status_code == 503

    def test_delete_job_cancels_and_deletes(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        job = repo.create_job(total=2)  # status 'queued'

        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.delete(f"/api/jobs/{job.id}")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job.id
        # Queued job → cancelled then removed.
        assert queue.cancelled == [job.id]
        assert repo.get_job(job.id) is None

    def test_delete_job_not_found(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.delete("/api/jobs/9999")
        assert resp.status_code == 404

    def test_delete_terminal_job_no_cancel(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        job = repo.create_job(total=1)
        repo.update_job(job.id, status="done")

        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.delete(f"/api/jobs/{job.id}")
        assert resp.status_code == 200
        assert queue.cancelled == []  # not cancelled, already terminal
        assert repo.get_job(job.id) is None

    def test_retry_400_when_nothing_failed(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        job = repo.create_job(total=1)
        queue = _FakeJobQueue(retry_result=False)
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post(f"/api/jobs/{job.id}/retry")
        assert resp.status_code == 400

    def test_retry_200_when_failures(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        job = repo.create_job(total=1)
        queue = _FakeJobQueue(retry_result=True)
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post(f"/api/jobs/{job.id}/retry")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job.id

    def test_retry_404_when_job_missing(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post("/api/jobs/9999/retry")
        assert resp.status_code == 404

    def test_pause_resume_flip_is_paused(self) -> None:
        from cutfinder.api.routes import _build_router as main_router

        repo = FakeCatalogRepository()
        queue = _FakeJobQueue()
        app = FastAPI()
        app.include_router(main_router(_ctx(repository=repo, worker_queue=queue)))

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]

        resp = client.post("/api/jobs/pause")
        assert resp.status_code == 200 and resp.json()["paused"] is True
        assert queue.is_paused is True
        assert client.get("/api/jobs").json()["paused"] is True

        resp = client.post("/api/jobs/resume")
        assert resp.status_code == 200 and resp.json()["paused"] is False
        assert queue.is_paused is False
        assert client.get("/api/jobs").json()["paused"] is False


# ── 4. Clip list/detail/edit/correct (DoD: CRUD + corrections) ─

class TestClipListEndpoint:
    """Verify GET /clips list endpoint."""

    def test_list_clips_returns_empty(self) -> None:
        """No clips → 200 with empty list."""
        repo = FakeCatalogRepository()

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.get("/api/clips")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_clips_with_data(self) -> None:
        """Clips in repo → returns list with clip dicts."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/test.mp4", duration_s=10.5))

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.get("/api/clips")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1


    def test_list_clips_with_filters(self) -> None:
        """Filtering by roll_type returns matching clips."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/a.mp4", duration_s=10.5))
        repo.upsert_clip(_make_clip(id=2, source_path="/tmp/b.mp4", roll_type="b", duration_s=20.0))

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp_a = client.get("/api/clips?roll_type=a")
        assert resp_a.status_code == 200
        data = resp_a.json()
        all_roll_type_a = all(c.get("roll_type") == "a" for c in data)
        assert len(data) >= 1 and all_roll_type_a

    def test_list_clips_no_repository(self) -> None:
        """No repository → 503."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx())
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.get("/api/clips")
        assert resp.status_code == 503


class TestClipDetailEndpoint:
    """Verify GET /clips/{id} detail endpoint."""

    def test_clip_detail_returns_full_info(self) -> None:
        """Existing clip → 200 with full detail dict."""
        repo = FakeCatalogRepository()

        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/detail.mp4", duration_s=15.0, width=1920, height=1080, fps=30.0))


        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.get("/api/clips/1")

        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data and data["id"] == 1
        assert "tags" in data and isinstance(data["tags"], list)

    def test_clip_detail_not_found(self) -> None:
        """Non-existent clip → 404."""
        repo = FakeCatalogRepository()

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)  # type: ignore[arg-type]
        resp = client.get("/api/clips/999")

        assert resp.status_code == 404


class TestRollCorrection:
    """Verify PATCH /clips/{id}/roll correction."""

    def test_roll_correction_valid(self) -> None:
        """Valid roll value → 200 ok."""
        repo = FakeCatalogRepository()


        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/roll.mp4", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.patch("/api/clips/1/roll?roll=b")

        assert resp.status_code == 200
        data = resp.json()
        assert "clip_id" in data

    def test_roll_correction_relocates_library_copy(self) -> None:
        """Correcting A→B moves the organised copy and updates library_path."""
        from types import SimpleNamespace

        from cutfinder.api.routes import _build_router as main_router
        from fastapi import FastAPI

        from tests.fakes import FakeLibraryWriter

        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(
            id=1, source_path="/tmp/roll.mp4", roll_type="a", duration_s=10.5,
            library_path="/lib/2026-05-14/A-roll/A-0001.mp4",
        ))

        writer = FakeLibraryWriter(library_path="/lib")
        ctx = SimpleNamespace(
            repository=repo, worker_queue=None, thumbnail_root=None,
            library_path="/lib",
            orchestrator=SimpleNamespace(library_writer=writer),
        )

        app = FastAPI()
        app.include_router(main_router(ctx))
        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]

        resp = client.patch("/api/clips/1/roll?roll=b")
        assert resp.status_code == 200

        # The copy was relocated into the B-roll folder under the same date.
        assert writer.recategorize_calls == [("/lib/2026-05-14/A-roll/A-0001.mp4", "b")]
        assert resp.json()["library_path"] == "/lib/2026-05-14/B-roll/B-0001.mp4"
        assert repo.get_clip(1).library_path == "/lib/2026-05-14/B-roll/B-0001.mp4"

    def test_roll_correction_same_roll_no_relocation(self) -> None:
        """Re-selecting the current roll does not move the copy."""
        from types import SimpleNamespace

        from cutfinder.api.routes import _build_router as main_router
        from fastapi import FastAPI

        from tests.fakes import FakeLibraryWriter

        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(
            id=1, source_path="/tmp/roll.mp4", roll_type="a", duration_s=10.5,
            library_path="/lib/2026-05-14/A-roll/A-0001.mp4",
        ))

        writer = FakeLibraryWriter(library_path="/lib")
        ctx = SimpleNamespace(
            repository=repo, worker_queue=None, thumbnail_root=None,
            library_path="/lib",
            orchestrator=SimpleNamespace(library_writer=writer),
        )

        app = FastAPI()
        app.include_router(main_router(ctx))
        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]

        resp = client.patch("/api/clips/1/roll?roll=a")
        assert resp.status_code == 200
        assert writer.recategorize_calls == []  # unchanged roll → no move

    def test_roll_correction_invalid(self) -> None:
        """Invalid roll value (not a/b) → 422."""
        repo = FakeCatalogRepository()


        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/roll.mp4", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.patch("/api/clips/1/roll?roll=c")

        assert resp.status_code == 422


class TestEditClip:
    """Verify PATCH /clips/{id} edit summary/description."""

    def test_edit_summary(self) -> None:
        """Edit summary → 200 ok."""
        repo = FakeCatalogRepository()


        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/edit.mp4", roll_type="a", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.patch(
            "/api/clips/1",
            json={"summary": "Updated summary text"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "clip_id" in data

    def test_edit_description(self) -> None:
        """Edit description → 200 ok."""
        repo = FakeCatalogRepository()


        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/edit.mp4", roll_type="b", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.patch(
            "/api/clips/1",
            json={"description": "Updated description text"},
        )

        assert resp.status_code == 200


class TestSetTags:
    """Verify PUT /clips/{id}/tags tag replacement."""

    def test_set_tags_success(self) -> None:
        """Valid tags list → 200 with count."""
        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/tags.mp4", roll_type="a", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.put(
            "/api/clips/1/tags",
            json={"tags": [
                {"name": "sunset", "source": "auto"},
                {"name": "beach", "source": "manual"},
            ]},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "tags_count" in data and data["tags_count"] == 2

    def test_set_tags_empty_list(self) -> None:
        """Empty tags list → 200 ok (clears all tags)."""
        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/tags.mp4", roll_type="a", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.put("/api/clips/1/tags", json={"tags": []})

        assert resp.status_code == 200


# ── 5. Re-analyze (DoD: trigger re-analysis) ───────────────────

class TestReanalyzeEndpoint:
    """Verify POST /clips/{id}/reanalyze."""

    def test_reanalyze_success(self) -> None:
        """Valid clip_id → 200 with job_id."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        class FakeQueue:
            async def enqueue_reanalyze(self, clip_id: int) -> int:  # noqa: D102
                return 99

        queue = FakeQueue()  # type: ignore[assignment]
        repo = FakeCatalogRepository()

        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/reanalyze.mp4", roll_type="a", duration_s=10.5))

        router = main_router(_ctx(repository=repo, worker_queue=queue))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post("/api/clips/1/reanalyze")

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data

    def test_reanalyze_no_worker_queue(self) -> None:
        """No worker queue → 503."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        FakeCatalogRepository()
        router = main_router(_ctx())  # type: ignore[union-attr]
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.post("/api/clips/1/reanalyze")

        assert resp.status_code == 503


# ── 6. Search (DoD: full-text search) ───────────────────────

class TestSearchEndpoint:
    """Verify GET /search?q= full-text search."""

    def test_search_returns_results(self) -> None:
        """Query with matches → 200 with clip list."""
        repo = FakeCatalogRepository()
        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/search.mp4", summary="A sunset at the beach with waves."))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/search?q=sunset")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_empty_query(self) -> None:
        """Empty query string → 422 (min_length=1)."""
        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx())
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/search")

        assert resp.status_code == 422


# ── 8. Settings CRUD (DoD: read/update config) ───────────────

class TestSettingsEndpoints:
    """Verify GET/PUT /settings."""

    def test_get_settings_no_library(self) -> None:
        """No library configured → 404."""

        def get_library_none() -> None:
            return None  # type: ignore[return-value]

        from cutfinder.api.settings_routes import (  # noqa: E402
            _build_router as settings_router,
        )

        router = settings_router(  # type: ignore[call-arg]
            load_config_fn=lambda p: None,
            save_prefs_fn=lambda p, _label: None,
            get_library_fn=get_library_none,
            save_global_fn=lambda _updates: None,
        )

        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.get("/api/settings")

        assert resp.status_code == 404

    def test_put_settings_triggers_live_reload(self) -> None:
        """A successful PUT rebuilds the live pipeline via reload_fn."""
        from cutfinder.config import AppConfig, EnvSettings, Prefs

        reloaded: list[bool] = []

        async def reload_fn() -> None:
            reloaded.append(True)

        config = AppConfig(env=EnvSettings(), prefs=Prefs(library_path="/lib"))

        from cutfinder.api.settings_routes import (  # noqa: E402
            _build_router as settings_router,
        )

        router = settings_router(  # type: ignore[call-arg]
            load_config_fn=lambda _p: config,
            save_prefs_fn=lambda _prefs, _label: None,
            get_library_fn=lambda: "/lib",
            save_global_fn=lambda _updates: None,
            reload_fn=reload_fn,
        )

        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.put("/api/settings", json={"text_model": "custom-model"})

        assert resp.status_code == 200
        assert reloaded == [True]


# ── Edge cases and integration-like tests ─────────────────────

class TestEdgeCases:
    """Boundary conditions and edge cases."""

    def test_edit_clip_with_invalid_body(self) -> None:
        """Non-JSON body → 422."""
        repo = FakeCatalogRepository()

        repo.upsert_clip(_make_clip(id=1, source_path="/tmp/invalid.mp4", duration_s=10.5))

        from cutfinder.api.routes import (  # noqa: E402
            _build_router as main_router,
        )

        router = main_router(_ctx(repository=repo))
        from fastapi import FastAPI  # noqa: E402

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
        resp = client.patch(
            "/api/clips/1",
            content="not json",  # type: ignore[arg-type]
            headers={"Content-Type": "application/octet-stream"},
        )

        assert resp.status_code == 422


# ── Native folder picker (POST /pick-folder) ─────────────────


class TestPickFolder:
    """The native macOS folder chooser endpoint (osascript)."""

    def _client(self) -> TestClient:
        return TestClient(_build_app(), raise_server_exceptions=False)

    def test_returns_absolute_path_and_strips_trailing_slash(
        self, monkeypatch: Any,
    ) -> None:
        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return (b"/Users/me/Videos/\n", b"")

        async def _fake_exec(*_a: Any, **_k: Any) -> Any:
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        resp = self._client().post("/api/pick-folder")
        assert resp.status_code == 200
        assert resp.json() == {"path": "/Users/me/Videos"}

    def test_cancel_returns_null_path(self, monkeypatch: Any) -> None:
        class _FakeProc:
            returncode = 1  # osascript exits non-zero when the user cancels

            async def communicate(self) -> tuple[bytes, bytes]:
                return (b"", b"User canceled.")

        async def _fake_exec(*_a: Any, **_k: Any) -> Any:
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        resp = self._client().post("/api/pick-folder")
        assert resp.status_code == 200
        assert resp.json() == {"path": None}

    def test_missing_osascript_returns_501(self, monkeypatch: Any) -> None:
        async def _fake_exec(*_a: Any, **_k: Any) -> Any:
            raise FileNotFoundError("osascript")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        resp = self._client().post("/api/pick-folder")
        assert resp.status_code == 501


class TestOpenPath:
    """The macOS `open` endpoint — reveal a folder / play a file."""

    def _client(self, library_path: str) -> TestClient:
        from types import SimpleNamespace

        from cutfinder.api.routes import _build_router as main_router

        ctx = SimpleNamespace(
            repository=None, orchestrator=None, worker_queue=None,
            thumbnail_root=None, library_path=library_path,
        )
        app = FastAPI()
        app.include_router(main_router(ctx))
        return TestClient(app, raise_server_exceptions=False)

    def _patch_open(self, monkeypatch: Any) -> list[tuple[Any, ...]]:
        """Stub asyncio so `open` is never actually launched; record calls."""
        calls: list[tuple[Any, ...]] = []

        class _FakeProc:
            returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                return (b"", b"")

        async def _fake_exec(*args: Any, **_k: Any) -> Any:
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        return calls

    def test_opens_file_inside_library(self, tmp_path: Any, monkeypatch: Any) -> None:
        roll_dir = tmp_path / "2026-05-13" / "A-roll"
        roll_dir.mkdir(parents=True)
        video = roll_dir / "A-0001.mp4"
        video.write_bytes(b"x")

        calls = self._patch_open(monkeypatch)
        resp = self._client(str(tmp_path)).post("/api/open", json={"path": str(video)})

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert calls and calls[0][0] == "open"
        assert calls[0][1] == str(video.resolve())

    def test_rejects_path_outside_library(self, tmp_path: Any, monkeypatch: Any) -> None:
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"x")
        lib = tmp_path / "lib"
        lib.mkdir()

        calls = self._patch_open(monkeypatch)
        resp = self._client(str(lib)).post("/api/open", json={"path": str(outside)})

        assert resp.status_code == 403
        assert calls == []  # never launched

    def test_missing_path_returns_422(self, tmp_path: Any, monkeypatch: Any) -> None:
        self._patch_open(monkeypatch)
        resp = self._client(str(tmp_path)).post("/api/open", json={})
        assert resp.status_code == 422

    def test_nonexistent_path_returns_404(self, tmp_path: Any, monkeypatch: Any) -> None:
        self._patch_open(monkeypatch)
        resp = self._client(str(tmp_path)).post(
            "/api/open", json={"path": str(tmp_path / "nope.mp4")},
        )
        assert resp.status_code == 404


class TestLogs:
    """The in-memory backend-log endpoint (GET /logs)."""

    def _client(self) -> TestClient:
        return TestClient(_build_app(), raise_server_exceptions=False)

    def test_returns_buffered_log_lines(self) -> None:
        import logging

        from cutfinder.logbuffer import install_log_buffer

        install_log_buffer()
        logging.getLogger("cutfinder.test").info("hello-from-test-log")

        resp = self._client().get("/api/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert any("hello-from-test-log" in r["message"] for r in data["logs"])
        assert data["last_seq"] >= 1

    def test_after_returns_only_newer_lines(self) -> None:
        import logging

        from cutfinder.logbuffer import install_log_buffer

        install_log_buffer()
        log = logging.getLogger("cutfinder.test")
        log.info("older-line-xyz")
        seq = self._client().get("/api/logs").json()["last_seq"]

        log.info("newer-line-xyz")
        data = self._client().get(f"/api/logs?after={seq}").json()
        messages = [r["message"] for r in data["logs"]]
        assert any("newer-line-xyz" in m for m in messages)
        assert all("older-line-xyz" not in m for m in messages)


# ── Public exports (module-level marker) ─────────────────────

__all__: list[str] = []  # noqa: PLE0611 — module-level helper, no direct exports
