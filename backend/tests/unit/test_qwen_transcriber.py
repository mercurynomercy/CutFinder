"""Unit tests for the pure VAD-chunking + cue-assembly helpers of QwenTranscriber.

These cover the logic that turns Qwen3-ASR text + ForcedAligner timestamps into
subtitle cues, without loading any MLX model.
"""

from __future__ import annotations

from dataclasses import dataclass

from cutfinder.adapters.qwen_transcriber import (
    _lang_name,
    assemble_cues,
    clean_cues,
    group_cues,
    merge_short_cues,
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


# ── cue assembly across chunks ────────────────────────────────────

def test_assemble_merges_sentence_split_across_chunks() -> None:
    # Chunk B starts exactly where A ends (a hard VAD cut, no real silence):
    # the trailing 了 must NOT become its own one-character cue.
    chunk_a = [("躺", 9.0, 9.2), ("平", 9.2, 9.4)]
    chunk_b = [("了", 9.4, 9.6)]
    cues = assemble_cues([chunk_a, chunk_b], max_chars=18, max_dur=6.0, gap_s=0.7)
    assert [c.text for c in cues] == ["躺平了"]


def test_assemble_still_splits_on_real_silence_between_chunks() -> None:
    chunk_a = [("躺", 9.0, 9.2), ("平", 9.2, 9.4)]
    chunk_b = [("了", 11.0, 11.2)]  # 1.6s gap > gap_s — a genuine pause
    cues = assemble_cues([chunk_a, chunk_b], max_chars=18, max_dur=6.0, gap_s=0.7)
    assert [c.text for c in cues] == ["躺平", "了"]


def test_assemble_keeps_fallback_segments_standalone_and_ordered() -> None:
    fallback = Segment(start_s=1.0, end_s=2.0, text="对齐失败的整段")
    cues = assemble_cues(
        [
            [("你", 0.0, 0.2), ("好", 0.2, 0.4)],
            fallback,
            [("再", 3.0, 3.2), ("见", 3.2, 3.4)],
        ],
        max_chars=18, max_dur=6.0, gap_s=0.7,
    )
    assert [c.text for c in cues] == ["你好", "对齐失败的整段", "再见"]


# ── short cue merging ──────────────────────────────────────────────

def _seg(start: float, end: float, text: str) -> Segment:
    return Segment(start_s=start, end_s=end, text=text)


def _merge(cues: list[Segment]) -> list[Segment]:
    return merge_short_cues(
        cues, max_gap_s=1.0, short_max_chars=3, max_chars=18, max_dur=6.0,
    )


def test_short_cue_merges_backward_into_previous() -> None:
    cues = [_seg(0.0, 2.0, "马上我就能躺平"), _seg(2.1, 2.4, "了")]
    out = _merge(cues)
    assert [c.text for c in out] == ["马上我就能躺平了"]
    assert out[0].start_s == 0.0 and out[0].end_s == 2.4


def test_leading_short_cue_merges_forward() -> None:
    cues = [_seg(0.0, 0.3, "了"), _seg(0.4, 2.0, "又是先上菜")]
    out = _merge(cues)
    assert [c.text for c in out] == ["了又是先上菜"]
    assert out[0].start_s == 0.0 and out[0].end_s == 2.0


def test_run_of_short_cues_collapses_into_one() -> None:
    # The 好/嗯/就是/因/对 cluster: 2-3 char cues <1s apart fold into one line.
    cues = [
        _seg(0.0, 0.4, "好。"), _seg(0.7, 1.1, "嗯。"), _seg(1.5, 2.1, "就是。"),
        _seg(2.4, 2.7, "因。"), _seg(3.0, 3.3, "对。"),
    ]
    out = _merge(cues)
    assert [c.text for c in out] == ["好。嗯。就是。因。对。"]


def test_short_cue_kept_when_gap_exceeds_threshold() -> None:
    # A genuine standalone short after a real pause must survive untouched.
    cues = [_seg(0.0, 0.3, "嗯"), _seg(5.0, 5.3, "对")]
    out = _merge(cues)
    assert [c.text for c in out] == ["嗯", "对"]


def test_short_cue_not_merged_when_it_would_exceed_max_dur() -> None:
    cues = [_seg(0.0, 5.8, "一二三四五六"), _seg(5.9, 6.2, "了")]
    out = _merge(cues)
    assert [c.text for c in out] == ["一二三四五六", "了"]


def test_short_cue_not_merged_when_combined_exceeds_max_chars() -> None:
    # 17 + 1 = 18 fits; 18 + 1 = 19 overflows one line, so it stays split.
    out = _merge([_seg(0.0, 2.0, "一二三四五六七八九十一二三四五六七"), _seg(2.1, 2.4, "了")])
    assert [c.text for c in out] == ["一二三四五六七八九十一二三四五六七了"]
    out2 = _merge([_seg(0.0, 2.0, "一二三四五六七八九十一二三四五六七八"), _seg(2.1, 2.4, "了")])
    assert [c.text for c in out2] == ["一二三四五六七八九十一二三四五六七八", "了"]


def test_two_long_cues_not_merged() -> None:
    # Neither side short → left as separate cues even when they abut.
    cues = [_seg(0.0, 2.0, "今天天气真的很好"), _seg(2.1, 4.0, "我们出去走走吧")]
    out = _merge(cues)
    assert [c.text for c in out] == ["今天天气真的很好", "我们出去走走吧"]


def test_short_cue_ignores_trailing_punctuation_in_char_count() -> None:
    cues = [_seg(0.0, 2.0, "躺平"), _seg(2.1, 2.3, "了。")]
    out = _merge(cues)
    assert [c.text for c in out] == ["躺平了。"]


# ── cue cleanup ───────────────────────────────────────────────────

def test_clean_folds_zero_duration_trailing_token_into_prev() -> None:
    # ForcedAligner artifact: the final 了。 gets a zero-width timestamp after a
    # gap, so group_cues orphans it into its own zero-duration cue. Its text must
    # fold onto the previous cue, not vanish (the "躺平了 不见了" regression).
    cues = [
        Segment(start_s=8.42, end_s=11.46, text="说，马上他能腾飞了，马上我就能躺平"),
        Segment(start_s=12.26, end_s=12.26, text="了。"),
        Segment(start_s=12.90, end_s=15.14, text="又是先上菜不上饭是吗？"),
    ]
    out = clean_cues(cues)
    assert [c.text for c in out] == [
        "说，马上他能腾飞了，马上我就能躺平了。",
        "又是先上菜不上饭是吗？",
    ]
    assert out[0].end_s == 11.46  # keep the previous cue's reliable timing


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
