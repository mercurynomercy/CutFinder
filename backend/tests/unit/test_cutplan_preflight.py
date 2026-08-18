"""Unit tests for the deterministic pre-flight clarification check (§3.15 B1)."""

from __future__ import annotations

from typing import Any

from cutfinder.cutplan.preflight import check_preflight
from cutfinder.domain.models import ClipBrief, RoughCutRequest


class FakeRetriever:
    def __init__(self, briefs: list[ClipBrief]) -> None:
        self._briefs = briefs

    def search_footage(self, **kwargs: Any) -> list[ClipBrief]:
        return self._briefs

    def get_clip_detail(self, clip_id: int) -> Any:  # unused by preflight
        return None


def test_asks_date_when_missing_and_library_spans_multiple_days() -> None:
    retr = FakeRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    pending = check_preflight(RoughCutRequest(), retr, set())
    assert pending is not None
    assert pending.kind == "preflight_date"
    assert pending.options == ["2026-04-25", "2026-04-26"]


def test_skips_date_question_when_library_has_one_day() -> None:
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00")])
    pending = check_preflight(RoughCutRequest(), retr, set())
    # Date isn't ambiguous with one day, so duration (also missing) is asked instead.
    assert pending is not None
    assert pending.kind == "preflight_duration"


def test_skips_date_question_when_date_already_provided() -> None:
    retr = FakeRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    pending = check_preflight(RoughCutRequest(date_from="2026-04-25"), retr, set())
    assert pending is not None
    assert pending.kind == "preflight_duration"


def test_asks_duration_when_missing() -> None:
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00")])
    pending = check_preflight(RoughCutRequest(date_from="2026-04-25"), retr, set())
    assert pending is not None
    assert pending.kind == "preflight_duration"
    assert pending.options == ["5 分钟以内", "10 分钟", "15-20 分钟", "不限长度"]


def test_returns_none_when_nothing_missing() -> None:
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00")])
    req = RoughCutRequest(date_from="2026-04-25", target_min_s=300, target_max_s=600)
    assert check_preflight(req, retr, set()) is None


def test_does_not_reask_a_field_already_asked() -> None:
    retr = FakeRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    # Date is missing but already asked this session, and duration is also
    # missing but already asked → nothing left to ask.
    pending = check_preflight(RoughCutRequest(), retr, {"date", "duration"})
    assert pending is None


def test_english_lang_uses_english_strings() -> None:
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00")])
    pending = check_preflight(RoughCutRequest(date_from="2026-04-25"), retr, set(), lang="en")
    assert pending is not None
    assert pending.options == ["Under 5 minutes", "10 minutes", "15-20 minutes", "Unlimited"]
