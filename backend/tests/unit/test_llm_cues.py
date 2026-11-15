"""Unit tests for the pure window / break-mapping helpers of LLM subtitle segmentation."""

from __future__ import annotations

from cutfinder.adapters.llm_cues import (
    breaks_from_reply,
    make_windows,
    marked_text,
    split_at_breaks,
)


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
