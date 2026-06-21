"""Unit tests for the pure VAD-chunking + cue-assembly helpers of QwenTranscriber.

These cover the logic that turns Qwen3-ASR text + ForcedAligner timestamps into
subtitle cues, without loading any MLX model.
"""

from __future__ import annotations

from dataclasses import dataclass

from cutfinder.adapters.qwen_transcriber import (
    _lang_name,
    clean_cues,
    group_cues,
    merge_speech_into_chunks,
    reattach_punctuation,
)
from cutfinder.domain.models import Segment


@dataclass
class _Item:
    """Stand-in for an mlx-audio ForcedAlignItem."""

    text: str
    start_time: float
    end_time: float


# ── language mapping ──────────────────────────────────────────────

def test_lang_name_maps_known_codes() -> None:
    assert _lang_name("zh") == "Chinese"
    assert _lang_name("en") == "English"
    assert _lang_name("ZH") == "Chinese"


def test_lang_name_defaults_to_chinese() -> None:
    assert _lang_name(None) == "Chinese"
    assert _lang_name("fr") == "Chinese"


# ── VAD chunk merging ─────────────────────────────────────────────

def test_merge_combines_adjacent_spans_under_limit() -> None:
    spans = [(0.0, 5.0), (6.0, 10.0), (11.0, 14.0)]
    assert merge_speech_into_chunks(spans, max_chunk_s=60.0) == [(0.0, 14.0)]


def test_merge_breaks_when_limit_exceeded() -> None:
    spans = [(0.0, 40.0), (41.0, 70.0)]
    chunks = merge_speech_into_chunks(spans, max_chunk_s=60.0)
    # First span+second would span 0..70 > 60, so the second starts a new chunk.
    assert chunks == [(0.0, 40.0), (41.0, 70.0)]


def test_merge_splits_overlong_single_span() -> None:
    chunks = merge_speech_into_chunks([(0.0, 150.0)], max_chunk_s=60.0)
    assert chunks == [(0.0, 60.0), (60.0, 120.0), (120.0, 150.0)]


def test_merge_empty() -> None:
    assert merge_speech_into_chunks([], max_chunk_s=60.0) == []


# ── punctuation re-attachment ─────────────────────────────────────

def test_reattach_restores_trailing_punctuation() -> None:
    text = "你好，世界。"
    items = [
        _Item("你", 0.0, 0.1), _Item("好", 0.1, 0.2),
        _Item("世", 0.5, 0.6), _Item("界", 0.6, 0.7),
    ]
    timed = reattach_punctuation(text, items)
    # The comma trails 好; the full stop trails 界.
    assert "".join(t for t, _, _ in timed) == "你好，世界。"
    assert timed[1][0] == "好，"
    assert timed[3][0] == "界。"


def test_reattach_preserves_latin_spacing() -> None:
    text = "Easter Holiday"
    items = [_Item("Easter", 0.0, 0.5), _Item("Holiday", 0.6, 1.1)]
    timed = reattach_punctuation(text, items)
    assert "".join(t for t, _, _ in timed) == "Easter Holiday"


# ── cue grouping ──────────────────────────────────────────────────

def test_group_breaks_on_hard_punctuation() -> None:
    timed = [
        ("我", 0.0, 0.2), ("要", 0.2, 0.4), ("吃", 0.4, 0.6),
        ("饭", 0.6, 0.8), ("。", 0.8, 0.8),
        ("好", 1.0, 1.2), ("吧", 1.2, 1.4),
    ]
    cues = group_cues(timed, offset=0.0, max_chars=18, max_dur=6.0, gap_s=0.7)
    assert [c.text for c in cues] == ["我要吃饭。", "好吧"]


def test_group_offset_is_applied() -> None:
    timed = [("好", 0.0, 0.5), ("。", 0.5, 0.5)]
    cues = group_cues(timed, offset=100.0, max_chars=18, max_dur=6.0, gap_s=0.7)
    assert cues[0].start_s == 100.0
    assert cues[0].end_s == 100.5


def test_group_breaks_on_long_gap() -> None:
    timed = [("嗯", 0.0, 0.3), ("对", 5.0, 5.3)]
    cues = group_cues(timed, offset=0.0, max_chars=18, max_dur=6.0, gap_s=0.7)
    assert [c.text for c in cues] == ["嗯", "对"]


def test_group_breaks_on_max_chars() -> None:
    timed = [(c, i * 0.1, i * 0.1 + 0.1) for i, c in enumerate("一二三四")]
    cues = group_cues(timed, offset=0.0, max_chars=2, max_dur=6.0, gap_s=0.7)
    assert [c.text for c in cues] == ["一二", "三四"]


# ── cue cleanup ───────────────────────────────────────────────────

def test_clean_drops_zero_duration_and_dups() -> None:
    cues = [
        Segment(start_s=0.0, end_s=0.0, text="rep"),        # zero-duration
        Segment(start_s=1.0, end_s=2.0, text="hello"),
        Segment(start_s=2.0, end_s=3.0, text="hello"),      # consecutive dup
        Segment(start_s=3.0, end_s=4.0, text="  "),         # blank
        Segment(start_s=4.0, end_s=5.0, text="world"),
    ]
    out = clean_cues(cues)
    assert [c.text for c in out] == ["hello", "world"]
