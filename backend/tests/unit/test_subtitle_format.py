"""Tests for :mod:`cutfinder.subtitle.format` — pure SRT / iTT renderers."""

from __future__ import annotations

from cutfinder.domain.models import Segment
from cutfinder.subtitle.format import enforce_min_duration, to_itt, to_srt


# ── enforce_min_duration ─────────────────────────────────────────────


def test_min_duration_extends_isolated_short_cue() -> None:
    segs = [Segment(start_s=1.0, end_s=1.3, text="好")]
    out = enforce_min_duration(segs, 3.0)
    assert (out[0].start_s, out[0].end_s) == (1.0, 4.0)


def test_min_duration_caps_at_next_cue_start() -> None:
    segs = [
        Segment(start_s=1.0, end_s=1.3, text="好"),
        Segment(start_s=2.0, end_s=2.4, text="嗯"),
    ]
    out = enforce_min_duration(segs, 3.0)
    # First extends only to the next cue's start (no overlap); second extends fully.
    assert out[0].end_s == 2.0
    assert out[1].end_s == 5.0


def test_min_duration_leaves_long_cue_unchanged() -> None:
    segs = [Segment(start_s=0.0, end_s=4.0, text="长句")]
    out = enforce_min_duration(segs, 3.0)
    assert out[0].end_s == 4.0


def test_min_duration_zero_or_empty_is_noop() -> None:
    segs = [Segment(start_s=1.0, end_s=1.3, text="好")]
    assert enforce_min_duration(segs, 0.0) == segs
    assert enforce_min_duration([], 3.0) == []


# ── to_srt ───────────────────────────────────────────────────────────


def test_srt_basic_single_segment() -> None:
    """One segment → index 1, comma timecode, trailing blank-line block."""
    segs = [Segment(start_s=0.0, end_s=1.2, text="你好")]
    assert to_srt(segs) == "1\n00:00:00,000 --> 00:00:01,200\n你好\n"


def test_srt_subsecond_uses_comma() -> None:
    """1.2s renders as ``00:00:01,200`` (comma before milliseconds)."""
    segs = [Segment(start_s=1.2, end_s=2.0, text="x")]
    assert "00:00:01,200 --> 00:00:02,000" in to_srt(segs)


def test_srt_cross_hour_timecode() -> None:
    """3661.5s → 01:01:01,500."""
    segs = [Segment(start_s=3661.5, end_s=3661.9, text="hi")]
    assert "01:01:01,500 --> 01:01:01,900" in to_srt(segs)


def test_srt_multiple_entries_blank_line_between() -> None:
    segs = [
        Segment(start_s=0.0, end_s=1.0, text="a"),
        Segment(start_s=1.0, end_s=2.0, text="b"),
    ]
    expected = (
        "1\n00:00:00,000 --> 00:00:01,000\na\n"
        "\n"
        "2\n00:00:01,000 --> 00:00:02,000\nb\n"
    )
    assert to_srt(segs) == expected


def test_srt_trims_text_whitespace() -> None:
    segs = [Segment(start_s=0.0, end_s=1.0, text="  hi  ")]
    assert to_srt(segs) == "1\n00:00:00,000 --> 00:00:01,000\nhi\n"


def test_srt_empty_segments_is_empty_string() -> None:
    assert to_srt([]) == ""


# ── to_itt ───────────────────────────────────────────────────────────


def test_itt_header_and_dot_timecode() -> None:
    """iTT uses a DOT before milliseconds and rounds fps into the header."""
    segs = [Segment(start_s=1.2, end_s=2.0, text="你好")]
    out = to_itt(segs, language="zh", fps=29.97)
    assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    assert 'ttp:frameRate="30"' in out
    assert 'xml:lang="zh"' in out
    assert '<p begin="00:00:01.200" end="00:00:02.000">你好</p>' in out


def test_itt_cross_hour_timecode() -> None:
    segs = [Segment(start_s=3661.5, end_s=3661.9, text="hi")]
    out = to_itt(segs, language="en", fps=25.0)
    assert '<p begin="01:01:01.500" end="01:01:01.900">hi</p>' in out


def test_itt_xml_escapes_special_chars() -> None:
    """``& < >`` must be XML-escaped in the <p> body."""
    segs = [Segment(start_s=0.0, end_s=1.0, text="a & b < c > d")]
    out = to_itt(segs, language="zh", fps=24.0)
    assert "a &amp; b &lt; c &gt; d" in out
    assert "a & b < c > d" not in out


def test_itt_empty_segments_still_valid() -> None:
    """No segments → still a valid document with an empty <div>."""
    out = to_itt([], language="zh", fps=30.0)
    assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<body>\n<div>\n</div>\n</body>\n</tt>" in out
    assert "<p " not in out


def test_comma_vs_dot_difference() -> None:
    """SRT uses comma, iTT uses dot, for the same timestamp."""
    segs = [Segment(start_s=1.2, end_s=2.0, text="x")]
    assert "00:00:01,200" in to_srt(segs)
    assert "00:00:01.200" in to_itt(segs, language="zh", fps=25.0)
