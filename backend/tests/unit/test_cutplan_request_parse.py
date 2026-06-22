"""Unit tests for deterministic rough-cut request parsing."""

from __future__ import annotations

import datetime as _dt

from cutfinder.cutplan.request_parse import parse_request_fields


def test_full_dates_with_year() -> None:
    out = parse_request_fields(
        "我想要生成一个初剪，用2026/4/25 到 2026/5/11的素材剪成一条 vlog"
    )
    assert out["date_from"] == "2026-04-25"
    assert out["date_to"] == "2026-05-11"


def test_month_day_borrows_current_year() -> None:
    out = parse_request_fields("用 4/25-5/11 的素材剪一条 vlog")
    year = _dt.date.today().year
    assert out["date_from"] == f"{year:04d}-04-25"
    assert out["date_to"] == f"{year:04d}-05-11"


def test_duration_range_minutes() -> None:
    out = parse_request_fields("剪成一条【15~20分钟】的 vlog")
    assert out["target_min_s"] == 15 * 60
    assert out["target_max_s"] == 20 * 60


def test_duration_single_minutes() -> None:
    out = parse_request_fields("大概 10 分钟就好")
    assert out["target_min_s"] == 600
    assert out["target_max_s"] == 600


def test_aspect_ratio() -> None:
    out = parse_request_fields("视屏比例默认【16:9】")
    assert out["aspect_ratio"] == "16:9"


def test_full_message_all_fields() -> None:
    out = parse_request_fields(
        "我想要生成一个初剪，用2026/4/25 到 2026/5/11的素材剪成一条【15～20分钟】的 "
        "vlog，视屏比例默认【16:9】，整体希望风格是【叙述/轻快/有节奏】"
    )
    assert out == {
        "date_from": "2026-04-25",
        "date_to": "2026-05-11",
        "target_min_s": 900.0,
        "target_max_s": 1200.0,
        "aspect_ratio": "16:9",
    }


def test_duration_range_does_not_match_as_date() -> None:
    # "15-20分钟" must not be misread as a month/day pair (month 15 is invalid).
    out = parse_request_fields("剪一条 15-20分钟 的片子")
    assert "date_from" not in out


def test_empty_text() -> None:
    assert parse_request_fields("") == {}
    assert parse_request_fields("随便剪一下") == {}
