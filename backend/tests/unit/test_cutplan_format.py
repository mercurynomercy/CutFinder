"""Unit tests for the pure shot-list formatter (cutplan/format.py)."""

from __future__ import annotations

from cutfinder.cutplan.format import (
    format_duration,
    format_timecode,
    to_shotlist_markdown,
)
from cutfinder.domain.models import CutPlan, Shot


def test_timecode_boundaries() -> None:
    assert format_timecode(0) == "00:00:00.000"
    assert format_timecode(1.5) == "00:00:01.500"
    assert format_timecode(61.25) == "00:01:01.250"
    assert format_timecode(3661.001) == "01:01:01.001"
    assert format_timecode(-5) == "00:00:00.000"  # clamped


def test_duration_formatting() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(75) == "1:15"
    assert format_duration(3725) == "1:02:05"


def test_empty_plan_renders_total_only() -> None:
    md = to_shotlist_markdown(CutPlan())
    assert "总时长：0:00" in md
    assert md.endswith("\n")


def test_single_chapter_table_and_columns() -> None:
    plan = CutPlan(
        shots=[
            Shot(
                clip_id=1, roll="a", in_s=12.0, out_s=25.0,
                content="今天我们去爬山", rationale="开场叙事",
                chapter="开场", clip_label="A-0001.mov",
                thumb_ref="/api/clips/1/thumbnail",
            ),
        ],
        chapters=["开场"],
        total_s=13.0,
        target_min_s=900.0,
        target_max_s=1200.0,
        within_target=False,
    )
    md = to_shotlist_markdown(plan)
    assert "## 开场" in md
    assert "| # | 入–出 | 时长 | 类型 | 文件 | 缩略图 | 内容/台词 | 用途·理由 |" in md
    assert "00:00:12.000 – 00:00:25.000" in md
    assert "A-roll" in md
    assert "A-0001.mov" in md
    assert "![](/api/clips/1/thumbnail)" in md
    assert "未命中目标时长" in md  # within_target False → warning


def test_within_target_shows_checkmark() -> None:
    plan = CutPlan(
        shots=[Shot(clip_id=1, roll="b", in_s=0, out_s=5, chapter="空镜")],
        total_s=1000.0, target_min_s=900.0, target_max_s=1200.0,
        within_target=True,
    )
    md = to_shotlist_markdown(plan)
    assert "✓" in md
    assert "未命中" not in md


def test_chapters_group_and_number_continuously() -> None:
    plan = CutPlan(
        shots=[
            Shot(clip_id=1, roll="a", in_s=0, out_s=10, chapter="A"),
            Shot(clip_id=2, roll="b", in_s=0, out_s=5, chapter="B"),
            Shot(clip_id=3, roll="a", in_s=0, out_s=8, chapter="A"),
        ],
        chapters=["A", "B"],
        total_s=23.0,
    )
    md = to_shotlist_markdown(plan)
    # Chapter A holds shots 1 and 2 (clip 1, clip 3); chapter B holds shot 3.
    assert md.index("## A") < md.index("## B")
    # Continuous numbering across chapters: 1,2 under A, 3 under B.
    assert "| 1 |" in md and "| 2 |" in md and "| 3 |" in md


def test_pipe_in_content_is_escaped() -> None:
    plan = CutPlan(
        shots=[Shot(clip_id=1, roll="a", in_s=0, out_s=1, content="a|b\nc")],
        total_s=1.0,
    )
    md = to_shotlist_markdown(plan)
    assert "a\\|b c" in md
    # Escaped row still has the right number of structural separators
    # (the escaped \| inside the cell doesn't count as one).
    row = next(line for line in md.splitlines() if line.startswith("| 1 |"))
    assert row.replace("\\|", "").count("|") == 9  # 8 columns → 9 pipes
