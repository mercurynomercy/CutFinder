"""Unit tests for the pure window / break-mapping helpers of LLM subtitle segmentation."""

from __future__ import annotations

from cutfinder.adapters.llm_cues import (
    breaks_from_reply,
    llm_assemble_cues,
    make_windows,
    marked_text,
    split_at_breaks,
)
from cutfinder.adapters.qwen_transcriber import (
    _display_width,
    assemble_cues,
    clean_cues,
    merge_short_cues,
)
from cutfinder.domain.models import Segment
from cutfinder.ports.speech import SegmenterUnavailable


def _tok(text, i):
    return (text, float(i), float(i) + 0.9)


def test_windows_cut_after_hard_punct():
    t0 = _tok("甲" * 199 + "。", 0)
    t1 = _tok("乙" * 199 + "。", 1)
    t2 = _tok("丙" * 200, 2)
    assert make_windows([t0, t1, t2]) == [[t0, t1], [t2]]


def test_tiny_tail_window_merges_into_previous():
    t0 = _tok("甲" * 199 + "。", 0)
    t1 = _tok("乙" * 199 + "。", 1)
    t2 = _tok("丙" * 50, 2)
    assert make_windows([t0, t1, t2]) == [[t0, t1, t2]]


def test_window_hard_cap_cuts_at_largest_gap():
    toks = []
    t = 0.0
    for i in range(70):
        t += 2.0 if i == 40 else 0.1
        toks.append(("字" * 10, t, t + 1.0))
        t += 1.0
    windows = make_windows(toks)
    assert windows[0] == toks[:40]
    assert all(sum(len(x[0]) for x in w) <= 600 for w in windows)
    assert [x for w in windows for x in w] == toks


def test_marked_text_inserts_pause_marker():
    assert marked_text([("我们", 0, 0.5), ("回家", 1.5, 2)], 0.7) == "我们/回家"


def test_breaks_from_reply_ok():
    assert breaks_from_reply("我们准备回家啦，这次", "我们准备回家啦，|这次") == [8]


def test_reply_with_extra_text_is_rejected():
    assert breaks_from_reply("我们准备回家啦，这次", "好的：我们准备回家啦，|这次") is None
    assert breaks_from_reply("我们准备回家啦，这次", "我们准备回家啦，|这词") is None


def test_breaks_ignore_pause_markers_and_spaces():
    assert breaks_from_reply("太 popular 就", "太 popular|/就") == [8]


def test_trailing_break_is_excluded():
    assert breaks_from_reply("我们回家", "我们|回家|") == [2]


def test_breaks_map_with_latin_tokens():
    w = [("要", 0, 1), ("不", 1, 2), ("然", 2, 3), ("太", 3, 4), (" popular", 4, 5), (" 就", 5, 6)]
    lines = split_at_breaks(w, [4 + 7])
    assert lines == [w[:5], w[5:]]


def test_split_at_break_inside_multichar_token_closes_after_token():
    a, b = ("天守阁", 0, 1), ("里面", 1, 2)
    assert split_at_breaks([a, b], [2]) == [[a], [b]]


# ── llm_assemble_cues ─────────────────────────────────────────────

# Transcriber defaults: the rule path must use them verbatim.
_PARAMS = dict(
    max_chars=18, max_dur=6.0, gap_s=0.7,
    merge_gap_s=1.5, merge_short_max=4, merge_short_dur=1.0,
)


class FakeSegmenter:
    def __init__(self, replies):
        self.replies = replies
        self.calls: list[str] = []

    def split(self, text):
        self.calls.append(text)
        reply = self.replies(text)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _chars(text, start=0.0, step=0.2):
    """One token per character, *step* seconds each, no gaps."""
    return [(ch, start + i * step, start + (i + 1) * step) for i, ch in enumerate(text)]


def _rule_path(chunk_results):
    return merge_short_cues(
        clean_cues(assemble_cues(chunk_results, max_chars=18, max_dur=6.0, gap_s=0.7)),
        max_gap_s=1.5, short_max_chars=4, short_max_dur=1.0, max_chars=18, max_dur=6.0,
    )


def test_llm_breaks_used_and_timing_from_tokens():
    toks = _chars("我们准备回家啦，这次去大阪。")
    fake = FakeSegmenter(lambda t: t.replace("，", "，|"))
    cues = llm_assemble_cues([toks], fake, **_PARAMS)
    assert [c.text for c in cues] == ["我们准备回家啦，", "这次去大阪。"]
    assert cues[0].start_s == toks[0][1]
    assert cues[0].end_s == toks[7][2]


def test_mismatch_falls_back_to_rules():
    results = [_chars("我们准备回家啦，这次去大阪。")]
    fake = FakeSegmenter(lambda t: t.replace("大阪", "东京"))
    assert llm_assemble_cues(results, fake, **_PARAMS) == _rule_path(results)


def test_unavailable_stops_further_calls():
    toks = [("字" * 9 + "。", float(i), i + 0.9) for i in range(80)]
    assert len(make_windows(toks)) == 2
    fake = FakeSegmenter(lambda t: SegmenterUnavailable("down"))
    assert llm_assemble_cues([toks], fake, **_PARAMS) == _rule_path([toks])
    assert len(fake.calls) == 1


def test_silence_guard_splits_llm_line():
    toks = _chars("我们准备回家啦") + _chars("这次去大阪。", start=1.4 + 1.5)
    fake = FakeSegmenter(lambda t: t)
    cues = llm_assemble_cues([toks], fake, **_PARAMS)
    assert [c.text for c in cues] == ["我们准备回家啦", "这次去大阪。"]


def test_overlong_line_retried_then_split():
    text = "甲乙丙丁戊己庚辛壬癸" * 3
    toks = _chars(text)
    replies = iter([text, text[:15] + "|" + text[15:]])
    fake = FakeSegmenter(lambda t: next(replies))
    cues = llm_assemble_cues([toks], fake, **_PARAMS)
    assert "".join(c.text for c in cues) == text
    assert all(_display_width(c.text) <= 24 for c in cues)
    assert len(fake.calls) == 2
    assert fake.calls[1] == text


def test_overlong_line_rule_fallback_when_retry_fails():
    text = "甲乙丙丁戊己庚辛壬癸" * 3
    replies = iter([text, None])
    fake = FakeSegmenter(lambda t: next(replies))
    cues = llm_assemble_cues([_chars(text)], fake, **_PARAMS)
    assert "".join(c.text for c in cues) == text
    assert len(cues) > 1
    assert all(_display_width(c.text) <= 18 for c in cues)


def test_fallback_segments_stay_in_order():
    a = _chars("我们准备回家啦。")
    b = _chars("这次去大阪。", start=20.0)
    fake = FakeSegmenter(lambda t: t)
    cues = llm_assemble_cues([a, Segment(start_s=10, end_s=12, text="x"), b], fake, **_PARAMS)
    assert [c.text for c in cues] == ["我们准备回家啦。", "x", "这次去大阪。"]
    assert [c.start_s for c in cues] == sorted(c.start_s for c in cues)


def test_llm_run_does_not_reglue_separated_lines():
    first = "甲乙丙丁戊己庚辛壬癸甲乙丙丁"
    toks = _chars(first) + _chars("这次去大阪啦", start=14 * 0.2, step=0.8 / 6)
    fake = FakeSegmenter(lambda t: first + "|" + t[len(first):])
    cues = llm_assemble_cues([toks], fake, **_PARAMS)
    assert [c.text for c in cues] == [first, "这次去大阪啦"]


def test_zero_width_token_at_run_start_folds_onto_previous_run():
    a = _chars("我们准备回家啦。")
    b = [("了。", 20.0, 20.0)] + _chars("这次去大阪。", start=21.0)
    fake = FakeSegmenter(lambda t: t)
    cues = llm_assemble_cues([a, Segment(start_s=10, end_s=12, text="x"), b], fake, **_PARAMS)
    assert [c.text for c in cues] == ["我们准备回家啦。", "x了。", "这次去大阪。"]


def test_retry_pieces_are_reguarded():
    text = "甲乙丙丁戊己庚辛壬癸" * 4
    replies = iter([text, text[:2] + "|" + text[2:]])
    fake = FakeSegmenter(lambda t: next(replies))
    cues = llm_assemble_cues([_chars(text)], fake, **_PARAMS)
    assert "".join(c.text for c in cues) == text
    assert len(fake.calls) == 2
    assert all(_display_width(c.text) <= 24 for c in cues)
    assert all(c.end_s - c.start_s <= 8.0 for c in cues)


def test_llm_split_repeated_phrase_is_kept():
    text = "对对对，对对对，我们走吧。"
    fake = FakeSegmenter(lambda t: t.replace("，", "，|"))
    cues = llm_assemble_cues([_chars(text, step=0.25)], fake, **_PARAMS)
    assert "".join(c.text for c in cues) == text


def test_clean_cues_dedup_overlap_only_collapses_only_overlaps():
    a = Segment(start_s=0.0, end_s=1.0, text="对对对，")
    b = Segment(start_s=1.0, end_s=2.0, text="对对对，")
    c = Segment(start_s=1.5, end_s=2.5, text="对对对，")
    assert clean_cues([a, b]) == [a]
    assert clean_cues([a, b], dedup_overlap_only=True) == [a, b]
    assert clean_cues([b, c], dedup_overlap_only=True) == [b]
