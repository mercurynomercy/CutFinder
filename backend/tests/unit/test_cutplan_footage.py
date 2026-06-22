"""Unit tests for CatalogFootageRetriever over an in-memory catalog."""

from __future__ import annotations

import datetime as _dt

from cutfinder.adapters.sqlite_footage import CatalogFootageRetriever
from cutfinder.adapters.sqlite_repo import MemoryRepository
from cutfinder.domain.models import Clip, CutSuggestion, Segment, Tag, Transcript


def _make_clip(repo: MemoryRepository, fp: str, roll: str, day: str) -> int:
    clip = Clip(
        fingerprint=fp,
        source_path=f"/src/{fp}.mov",
        library_path=f"/lib/{day}/{fp}.mov",
        roll_type=roll,
        capture_time=_dt.datetime.fromisoformat(f"{day}T10:00:00+00:00"),
        date_source="embedded",
        duration_s=30.0,
        status="done",
        created_at="",
    )
    return repo.upsert_clip(clip)


def test_date_range_and_roll_filter() -> None:
    repo = MemoryRepository()
    a1 = _make_clip(repo, "a1", "a", "2026-04-26")
    _make_clip(repo, "a2", "a", "2026-05-20")  # outside range
    b1 = _make_clip(repo, "b1", "b", "2026-05-01")

    retr = CatalogFootageRetriever(repo)
    a_results = retr.search_footage(date_from="2026-04-25", date_to="2026-05-11", roll="a")
    assert [r.clip_id for r in a_results] == [a1]

    all_in_range = retr.search_footage(date_from="2026-04-25", date_to="2026-05-11")
    assert {r.clip_id for r in all_in_range} == {a1, b1}


def test_tag_filter() -> None:
    repo = MemoryRepository()
    c1 = _make_clip(repo, "c1", "b", "2026-05-01")
    c2 = _make_clip(repo, "c2", "b", "2026-05-02")
    repo.set_tags(c1, [Tag(name="海", source="auto")])
    repo.set_tags(c2, [Tag(name="山", source="auto")])

    retr = CatalogFootageRetriever(repo)
    results = retr.search_footage(tags=["海"])
    assert [r.clip_id for r in results] == [c1]
    assert "海" in results[0].tags


def test_get_clip_detail_includes_segments_and_keyframes() -> None:
    repo = MemoryRepository()
    cid = _make_clip(repo, "d1", "a", "2026-05-01")
    repo.save_transcript(cid, Transcript(
        full_text="开场白 中段",
        segments=[Segment(start_s=0, end_s=5, text="开场白"), Segment(start_s=5, end_s=10, text="中段")],
    ))
    repo.save_keyframes(cid, [CutSuggestion(rank=1, start_s=2, end_s=4, reason="好", source="text")])

    retr = CatalogFootageRetriever(repo)
    detail = retr.get_clip_detail(cid)
    assert detail is not None
    assert detail.roll == "a"
    assert detail.library_path == "/lib/2026-05-01/d1.mov"
    assert len(detail.segments) == 2
    assert detail.segments[0].text == "开场白"
    assert len(detail.keyframes) == 1
    assert retr.get_clip_detail(9999) is None


def test_has_transcript_flag_in_brief() -> None:
    repo = MemoryRepository()
    a = _make_clip(repo, "ha", "a", "2026-05-01")
    repo.save_transcript(a, Transcript(full_text="x", segments=[Segment(start_s=0, end_s=1, text="x")]))
    _make_clip(repo, "hb", "b", "2026-05-01")

    retr = CatalogFootageRetriever(repo)
    briefs = {r.clip_id: r for r in retr.search_footage(date_from="2026-05-01", date_to="2026-05-01")}
    assert briefs[a].has_transcript is True
