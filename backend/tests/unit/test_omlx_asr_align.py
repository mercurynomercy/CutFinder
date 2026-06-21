"""Tests for align_text_to_segments — distributing OMLX ASR text onto cues."""

from __future__ import annotations

from cutfinder.adapters.omlx_asr import align_text_to_segments
from cutfinder.domain.models import Segment


def _segs(*texts: str) -> list[Segment]:
    return [Segment(start_s=i, end_s=i + 1, text=t) for i, t in enumerate(texts)]


def test_returns_one_text_per_segment() -> None:
    segs = _segs("现在是在视频呢", "听说是半个小时就到光明岭")
    out = align_text_to_segments(segs, "现在是在视频的，听说是半个小时就到光明顶。")
    assert len(out) == len(segs)


def test_accurate_text_propagates() -> None:
    # whisper heard 光明岭; the OMLX text says 光明顶 — the corrected form wins.
    segs = _segs("现在是在视频呢", "听说是半个小时就到光明岭")
    out = align_text_to_segments(segs, "现在是在视频的，听说是半个小时就到光明顶。")
    assert "光明顶" in "".join(out)
    assert "光明岭" not in "".join(out)


def test_empty_asr_text_keeps_whisper_text() -> None:
    segs = _segs("一段", "两段")
    assert align_text_to_segments(segs, "   ") == ["一段", "两段"]


def test_no_whisper_text_dumps_into_first_cue() -> None:
    segs = _segs("", "")
    out = align_text_to_segments(segs, "全部文本")
    assert out[0] == "全部文本"
    assert out[1] == ""


def test_leading_punctuation_snaps_to_previous_cue() -> None:
    # A cue should not begin with a stray punctuation mark.
    segs = _segs("在那里", "我们")
    out = align_text_to_segments(segs, "在那里。我们")
    assert not out[1].startswith("。")
