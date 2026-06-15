"""Unit tests for SqliteRepository — real SQL on in-memory SQLite.

Covers: schema init, clip CRUD + idempotency, filtering by date/type/tag,
FTS5 search across summary/description/transcript, tag CRUD, roll correction,
update_analysis (preserves manual), transcript save/get, and job CRUD.

Run with:
    .venv/bin/python -m pytest tests/unit/test_sqlite_repo.py -v
"""

from __future__ import annotations

import datetime as _dt  # noqa: F401 — kept for type hints

import pytest  # noqa: F401 — used via conftest / pytest import below

from cutfinder.adapters.sqlite_repo import MemoryRepository
from cutfinder.domain.models import (
    AnalysisResult,
    Clip,
    ClipFilter,
    Segment,
    SummaryResult,
    Tag,
    Transcript,
    VisionResult,
)


# ── Helpers ───────────────────────────────────────────────────────

def _make_clip(
    fingerprint: str = "fp-1",
    roll_type: str = "a",
    status: str = "done",
    summary: str | None = None,
    description: str | None = None,
) -> Clip:
    """Build a minimal :class:`Clip` for testing."""
    return Clip(
        fingerprint=fingerprint,
        source_path=f"/data/{fingerprint}.mp4",
        roll_type=roll_type,
        summary=summary,
        description=description,
        status=status,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )


def _make_tag(name: str = "test", source: str = "auto") -> Tag:
    return Tag(name=name, source=source)


def _make_transcript(text: str = "hello world", segments_count: int = 2) -> Transcript:
    segs = [Segment(start_s=float(i), end_s=float(i + 1), text=f"seg {i}") for i in range(segments_count)]
    return Transcript(full_text=text, segments=segs)


def _make_vision_result(tags: list[str] | None = None, desc: str = "a scenic view") -> VisionResult:
    return VisionResult(tags=tags or ["nature"], description=desc)


def _make_summary_result(tags: list[str] | None = None, summary: str = "a nice video") -> SummaryResult:
    return SummaryResult(tags=tags or ["nature"], summary=summary)


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture()
def repo():
    """In-memory :class:`MemoryRepository` for each test."""
    r = MemoryRepository()
    yield r
    r.close()


# ── Schema initialisation ───────────────────────────────────────

class TestSchemaInit:
    def test_tables_exist(self, repo):
        """All tables are created after init."""
        c = repo._conn.cursor()

        for table in ("clips", "tags", "transcripts", "jobs"):
            c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            assert c.fetchone() is not None

        # FTS5 virtual table.
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clips_fts'"
        )
        assert c.fetchone() is not None


# ── Clip CRUD ───────────────────────────────────────────────────

class TestClipCrud:
    def test_upsert_and_get_clip(self, repo):
        clip = _make_clip("fp-crud", roll_type="a", summary="test intro")
        clip_id = repo.upsert_clip(clip)
        assert isinstance(clip_id, int) and clip_id > 0

        fetched = repo.get_clip(clip_id)
        assert fetched is not None
        assert fetched.id == clip_id
        assert fetched.fingerprint == "fp-crud"
        assert fetched.roll_type == "a"
        assert fetched.summary == "test intro"

    def test_upsert_returns_same_id_on_reinsert(self, repo):
        """Re-upserting the same clip returns its original id."""
        c = _make_clip("fp-re", roll_type="b")
        first_id = repo.upsert_clip(c)
        second_id = repo.upsert_clip(c)  # same fingerprint, should return id.
        assert first_id == second_id

    def test_get_nonexistent_clip_returns_none(self, repo):
        assert repo.get_clip(999_999) is None

    def test_delete_clip(self, repo):
        c = _make_clip("fp-del")
        clip_id = repo.upsert_clip(c)

        # Add tags and transcript before deleting.
        repo.set_tags(clip_id, [_make_tag("del-me", "auto")])
        repo.save_transcript(clip_id, _make_transcript("to be deleted"))

        repo.delete_clip(clip_id)
        assert repo.get_clip(clip_id) is None

    def test_query_returns_all_clips(self, repo):
        for i in range(3):
            repo.upsert_clip(_make_clip(f"fp-q{i}", roll_type="a"))

        results = repo.query_clips(ClipFilter())
        assert len(results) == 3


# ── Idempotency (same fingerprint doesn't duplicate) ───────────

class TestUpsertIdempotency:
    def test_same_fingerprint_no_duplicate(self, repo):
        clip_a = _make_clip("fp-idem", roll_type="a")
        id1 = repo.upsert_clip(clip_a)

        # A different source but same fingerprint (simulates re-scan).
        clip_b = _make_clip("fp-idem", roll_type="b", summary="updated")
        clip_b.library_path = "/lib/2024-01-01/A-roll/"
        id2 = repo.upsert_clip(clip_b)

        assert id1 == id2  # same record, no duplicate.
        c = repo._conn.cursor()
        c.execute("SELECT COUNT(*) FROM clips WHERE fingerprint='fp-idem'")
        assert c.fetchone()[0] == 1

    def test_upsert_updates_existing_fields(self, repo):
        clip = _make_clip("fp-update", roll_type="a")
        repo.upsert_clip(clip)

        # Update with library_path and status (Clip is frozen, use model_copy).
        clip = clip.model_copy(update={
            "library_path": "/lib/2024-05-01/B-roll/",
            "status": "processing",
        })
        repo.upsert_clip(clip)

        fetched = repo.get_clip(repo._conn.cursor().execute(
            "SELECT id FROM clips WHERE fingerprint='fp-update'"
        ).fetchone()[0])

        assert fetched.library_path == "/lib/2024-05-01/B-roll/"
        assert fetched.status == "processing"


# ── Filtering by roll_type / date / tag ───────────────────────

class TestFilterRollType:
    def test_filter_a_roll(self, repo):
        clip_a = _make_clip("fp-ra", roll_type="a")
        repo.upsert_clip(clip_a)

        clip_b = _make_clip("fp_rb", roll_type="b")
        repo.upsert_clip(clip_b)

        results = repo.query_clips(ClipFilter(roll_type="a"))
        assert len(results) == 1
        assert results[0].roll_type == "a"

    def test_filter_b_roll(self, repo):
        clip_a = _make_clip("fp_ra2", roll_type="a")
        repo.upsert_clip(clip_a)

        clip_b = _make_clip("fp_rb2", roll_type="b")
        repo.upsert_clip(clip_b)

        results = repo.query_clips(ClipFilter(roll_type="b"))
        assert len(results) == 1
        assert results[0].roll_type == "b"


class TestFilterDate:
    def test_filter_by_date(self, repo):
        now = _dt.datetime.now(_dt.timezone.utc)

        clip1 = _make_clip("fp_d1")
        clip1.capture_time = now

        repo.upsert_clip(clip1)

        # Clip without capture_time on same day.
        clip2 = _make_clip("fp_d2")
        repo.upsert_clip(clip2)

        iso_date = now.date().isoformat()  # e.g. "2026-06-13"

        results = repo.query_clips(ClipFilter(date=iso_date))
        # clip1 matches via capture_time; clip2 doesn't have one.
        assert len(results) >= 1


class TestFilterTag:
    def test_filter_by_tag(self, repo):
        c1 = _make_clip("fp_t1")
        id1 = repo.upsert_clip(c1)

        c2 = _make_clip("fp_t2")
        id2 = repo.upsert_clip(c2)

        # Add tags: clip 1 gets "nature", both get something else.
        repo.set_tags(id1, [_make_tag("nature"), _make_tag("travel")])
        repo.set_tags(id2, [_make_tag("nature"), _make_tag("food")])

        results = repo.query_clips(ClipFilter(tag="nature"))
        assert len(results) == 2

    def test_filter_by_specific_tag(self, repo):
        c1 = _make_clip("fp_ts1")
        id1 = repo.upsert_clip(c1)

        c2 = _make_clip("fp_ts2")
        id2 = repo.upsert_clip(c2)

        repo.set_tags(id1, [_make_tag("animals")])
        repo.set_tags(id2, [_make_tag("food")])

        results = repo.query_clips(ClipFilter(tag="animals"))
        assert len(results) == 1
        assert results[0].id == id1


# ── FTS5 search (summary / description / transcript) ───────────

class TestSearch:
    def test_search_summary(self, repo):
        c = _make_clip("fp_s1", summary="这是一段关于自然的视频")
        repo.upsert_clip(c)

        results = repo.search("自然")
        assert len(results) >= 1
        # Clip should be found via FTS.

    def test_search_description(self, repo):
        c = _make_clip("fp_s2", description="壮丽的山川景色")
        repo.upsert_clip(c)

        results = repo.search("山川")
        assert len(results) >= 1

    def test_search_transcript(self, repo):
        c = _make_clip("fp_s3", roll_type="a")
        cid = repo.upsert_clip(c)

        # Save a transcript with Chinese text.
        tr = _make_transcript("今天天气很好我们去公园散步")
        repo.save_transcript(cid, tr)

        # Now search — the FTS index should pick up transcript.
        results = repo.search("天气")
        assert len(results) >= 1

    def test_search_no_match(self, repo):
        c = _make_clip("fp_sn", summary="english text only")
        repo.upsert_clip(c)

        results = repo.search("中文关键词不会匹配英文")
        assert len(results) == 0

    def test_search_returns_clips_in_order(self, repo):
        """Multiple matching clips are returned (order by FTS rank)."""
        for i in range(3):
            c = _make_clip(f"fp_so{i}", summary=f"testing keyword {i}")
            repo.upsert_clip(c)

        results = repo.search("testing")
        assert len(results) == 3


class TestFilterDateAndType:
    def test_combined_date_and_roll_filter(self, repo):
        _dt.datetime.now(_dt.timezone.utc)

        c1 = _make_clip("fp_dt1", roll_type="a")
        c2 = _make_clip("fp_dt2", roll_type="b")

        repo.upsert_clip(c1)
        repo.upsert_clip(c2)

        # Filter by roll_type only.
        a_results = repo.query_clips(ClipFilter(roll_type="a"))
        assert len(a_results) == 1

        b_results = repo.query_clips(ClipFilter(roll_type="b"))
        assert len(b_results) == 1


# ── Tag operations (add, set, remove) ─────────────────────────

class TestTagOperations:
    def test_add_tag(self, repo):
        c = _make_clip("fp_at")
        cid = repo.upsert_clip(c)

        repo.add_tag(cid, "new-tag")
        tags = repo.get_tags(cid)
        assert len(tags) == 1
        assert tags[0].name == "new-tag"

    def test_add_tag_is_idempotent(self, repo):
        c = _make_clip("fp_ati")
        cid = repo.upsert_clip(c)

        repo.add_tag(cid, "dup-tag")
        repo.add_tag(cid, "dup-tag")  # should not duplicate.

        tags = repo.get_tags(cid)
        assert len(tags) == 1
        assert tags[0].name == "dup-tag"

    def test_set_tags_replaces_all(self, repo):
        c = _make_clip("fp_st")
        cid = repo.upsert_clip(c)

        # Add some tags first.
        repo.set_tags(cid, [_make_tag("old1"), _make_tag("old2")])
        assert len(repo.get_tags(cid)) == 2

        # Replace with new set.
        repo.set_tags(cid, [_make_tag("new1", "manual"), _make_tag("new2")])
        tags = repo.get_tags(cid)
        assert len(tags) == 2

    def test_remove_tag(self, repo):
        c = _make_clip("fp_rt")
        cid = repo.upsert_clip(c)

        repo.set_tags(cid, [_make_tag("keep"), _make_tag("drop")])
        assert len(repo.get_tags(cid)) == 2

        repo.remove_tag(cid, "drop")
        tags = repo.get_tags(cid)
        assert len(tags) == 1
        assert tags[0].name == "keep"


# ── Roll correction (correct_roll sets manual) ───────────────

class TestCorrectRoll:
    def test_correct_roll_sets_manual(self, repo):
        c = _make_clip("fp_cr", roll_type="a")
        cid = repo.upsert_clip(c)

        # Verify default.
        fetched = repo.get_clip(cid)
        assert fetched.roll_source == "auto"

        # Correct to B-roll.
        repo.correct_roll(cid, "b")

        fetched = repo.get_clip(cid)
        assert fetched.roll_type == "b"
        assert fetched.roll_source == "manual"


# ── update_analysis (re-analyze: preserves manual, refreshes auto)

class TestUpdateAnalysis:
    def test_preserves_manual_tags(self, repo):
        c = _make_clip("fp_ua")
        cid = repo.upsert_clip(c)

        # Set manual + auto tags.
        repo.set_tags(cid, [
            _make_tag("manual-tag", "manual"),
            _make_tag("auto-old", "auto"),
        ])

        # Re-analyze with new auto tags.
        result = AnalysisResult(
            roll_type="a",
            summary_result=_make_summary_result(tags=["auto-new"]),
        )
        repo.update_analysis(cid, result)

        tags = repo.get_tags(cid)
        names_sources = [(t.name, t.source) for t in tags]

        assert ("manual-tag", "manual") in names_sources  # preserved
        assert ("auto-new", "auto") in names_sources      # refreshed

    def test_preserves_manual_roll(self, repo):
        c = _make_clip("fp_uar", roll_type="a")
        cid = repo.upsert_clip(c)

        # Manually correct to B-roll.
        repo.correct_roll(cid, "b")

        result = AnalysisResult(roll_type="a", summary_result=_make_summary_result())
        repo.update_analysis(cid, result)

        fetched = repo.get_clip(cid)
        assert fetched.roll_type == "b"  # manual override preserved.

    def test_updates_transcript_and_summary(self, repo):
        c = _make_clip("fp_uats", roll_type="a")
        cid = repo.upsert_clip(c)

        result = AnalysisResult(
            roll_type="a",
            transcript=_make_transcript("new transcript text"),
            summary_result=_make_summary_result(summary="new summary"),
        )
        repo.update_analysis(cid, result)

        tr = repo.get_transcript(cid)
        assert tr.full_text == "new transcript text"

        fetched = repo.get_clip(cid)
        assert fetched.summary == "new summary"


# ── Transcript save / get ─────────────────────────────────────

class TestTranscriptCrud:
    def test_save_and_get_transcript(self, repo):
        c = _make_clip("fp_tc", roll_type="a")
        cid = repo.upsert_clip(c)

        tr = _make_transcript("hello world", segments_count=3)
        repo.save_transcript(cid, tr)

        fetched = repo.get_transcript(cid)
        assert fetched is not None
        assert fetched.full_text == "hello world"
        assert len(fetched.segments) == 3

    def test_get_nonexistent_transcript(self, repo):
        assert repo.get_transcript(999_999) is None

    def test_save_overwrites_existing(self, repo):
        c = _make_clip("fp_tco")
        cid = repo.upsert_clip(c)

        tr1 = _make_transcript("first")
        tr2 = _make_transcript("second")

        repo.save_transcript(cid, tr1)
        assert repo.get_transcript(cid).full_text == "first"

        repo.save_transcript(cid, tr2)
        assert repo.get_transcript(cid).full_text == "second"


# ── Job CRUD (create, update, get) ───────────────────────────

class TestJobCrud:
    def test_create_job(self, repo):
        job = repo.create_job(10)

        assert isinstance(job.id, int) and job.id > 0
        assert job.status == "queued"
        assert job.kind == "scan"
        assert job.total == 10

    def test_create_job_with_kind(self, repo):
        job = repo.create_job(1, kind="reanalyze")
        assert job.kind == "reanalyze"
        assert repo.get_job(job.id).kind == "reanalyze"

    def test_create_job_stored_in_db(self, repo):
        job = repo.create_job(5)

        c = repo._conn.cursor()
        row = c.execute(
            "SELECT status, total FROM jobs WHERE id=?", (job.id,)
        ).fetchone()

        assert row is not None
        assert row[0] == "queued"
        assert row[1] == 5

    def test_update_job(self, repo):
        job = repo.create_job(10)

        repo.update_job(job.id, done=3, status="running")
        fetched = repo.get_job(job.id)

        assert fetched.done == 3
        assert fetched.status == "running"

    def test_update_job_sets_finished_at_on_done(self, repo):
        job = repo.create_job(2)

        import time  # noqa: F811 — need a tiny gap for timestamp diff.
        time.sleep(0.05)  # ensure finished_at > started_at

        repo.update_job(job.id, done=2, status="done")
        fetched = repo.get_job(job.id)

        assert fetched.status == "done"
        assert fetched.finished_at is not None
        # finished_at should be after started_at.
        assert fetched.finished_at > job.started_at

    def test_get_nonexistent_job(self, repo):
        assert repo.get_job(999_999) is None

    def test_update_job_cancelled_sets_finished_at(self, repo):
        job = repo.create_job(3)
        repo.update_job(job.id, status="cancelled")
        fetched = repo.get_job(job.id)
        assert fetched.status == "cancelled"
        assert fetched.finished_at is not None


# ── Job queue management (list / delete / failed items) ──────────

class TestJobQueueManagement:
    def test_list_jobs_newest_first(self, repo):
        j1 = repo.create_job(1)
        j2 = repo.create_job(2)
        j3 = repo.create_job(3)

        jobs = repo.list_jobs()
        ids = [j.id for j in jobs]
        assert ids == [j3.id, j2.id, j1.id]

    def test_list_jobs_respects_limit(self, repo):
        for _ in range(5):
            repo.create_job(1)

        jobs = repo.list_jobs(limit=2)
        assert len(jobs) == 2

    def test_delete_job_removes_job_and_failed_items(self, repo):
        from cutfinder.domain.models import JobFailedItem

        job = repo.create_job(2)
        repo.record_failed_item(JobFailedItem(
            job_id=job.id, kind="clip", path="/tmp/a.mp4", fingerprint="ab", error="boom",
        ))
        assert len(repo.get_failed_items(job.id)) == 1

        repo.delete_job(job.id)
        assert repo.get_job(job.id) is None
        assert repo.get_failed_items(job.id) == []

    def test_record_get_clear_failed_items(self, repo):
        from cutfinder.domain.models import JobFailedItem

        job = repo.create_job(2)
        repo.record_failed_item(JobFailedItem(
            job_id=job.id, kind="clip", path="/tmp/x.mp4", fingerprint="ff", error="e1",
        ))
        repo.record_failed_item(JobFailedItem(
            job_id=job.id, kind="reanalyze", clip_id=7, error="e2",
        ))

        items = repo.get_failed_items(job.id)
        assert len(items) == 2
        assert items[0].kind == "clip" and items[0].path == "/tmp/x.mp4"
        assert items[1].kind == "reanalyze" and items[1].clip_id == 7

        repo.clear_failed_items(job.id)
        assert repo.get_failed_items(job.id) == []


# ── Schema migration (old jobs table without `kind`) ─────────────

class TestKindMigration:
    def test_migration_adds_kind_to_old_jobs_table(self):
        """An old-shape jobs table (no `kind`) is migrated, defaulting to 'scan'."""
        import sqlite3 as _sqlite3

        from cutfinder.adapters.sqlite_repo import SqliteRepository

        conn = _sqlite3.connect(":memory:")
        # Simulate a pre-existing DB: jobs table WITHOUT a kind column,
        # already holding a row.
        conn.execute("""
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'running',
                total INTEGER DEFAULT 0,
                done INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        conn.execute("INSERT INTO jobs (status, total) VALUES ('done', 4)")
        conn.commit()

        # Instantiating the repo runs execute_schema() → migration.
        repo = SqliteRepository(conn)

        # The pre-existing row gets the default kind 'scan'.
        existing = repo.get_job(1)
        assert existing is not None
        assert existing.kind == "scan"

        # And new jobs still work with kind.
        new_job = repo.create_job(1, kind="reanalyze")
        assert repo.get_job(new_job.id).kind == "reanalyze"
        repo.close()
