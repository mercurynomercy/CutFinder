"""Deterministic extraction of rough-cut parameters from a Chinese message.

The chat UI only sends free text (e.g. "用 2026/4/25 到 2026/5/11 的素材剪一条
15~20 分钟、16:9 的 vlog"). The director needs structured scoping — without a
date range it searches the *entire* library, overflowing the local model's
context so it returns truncated/invalid JSON. This parser pulls the fields out
in plain Python (date math must be correct), returning only the keys it found
so callers can merge it over remembered params on refine turns.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

# Full date with a year: 2026/4/25, 2026-04-25, 2026年4月25日.
_FULL_DATE = re.compile(r"(\d{4})\s*[./年-]\s*(\d{1,2})\s*[./月-]\s*(\d{1,2})\s*日?")
# Month/day without a year: 4/25, 5-11, 4月25日. Year borrowed from context.
_MD_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-月]\s*(\d{1,2})\s*日?(?!\d)")
# Duration range / single value, in 分钟 (minutes).
_DUR_RANGE = re.compile(r"(\d+)\s*[~～〜\-－—到至]\s*(\d+)\s*分钟?")
_DUR_SINGLE = re.compile(r"(\d+)\s*分钟")
# Aspect ratio: 16:9, 9:16, 2.35:1 (full-width colon tolerated).
_ASPECT = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*[:：]\s*(\d{1,2})(?!\d)")


def parse_request_fields(text: str) -> dict[str, Any]:
    """Return rough-cut params found in *text* (only the keys present)."""
    if not text:
        return {}
    out: dict[str, Any] = {}

    date_from, date_to = _parse_dates(text)
    if date_from is not None:
        out["date_from"] = date_from
    if date_to is not None:
        out["date_to"] = date_to

    lo, hi = _parse_duration(text)
    if lo is not None:
        out["target_min_s"] = lo
    if hi is not None:
        out["target_max_s"] = hi

    aspect = _parse_aspect(text)
    if aspect is not None:
        out["aspect_ratio"] = aspect

    return out


def _parse_dates(text: str) -> tuple[str | None, str | None]:
    """Extract a [from, to] day range, normalised to ISO ``YYYY-MM-DD``."""
    days: list[_dt.date] = []
    years_seen: list[int] = []

    remainder = text
    for m in _FULL_DATE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        day = _safe_date(y, mo, d)
        if day is not None:
            days.append(day)
            years_seen.append(y)
    # Remove matched full dates so their month/day aren't re-parsed below.
    remainder = _FULL_DATE.sub(" ", text)

    fallback_year = years_seen[0] if years_seen else _dt.date.today().year
    for m in _MD_DATE.finditer(remainder):
        mo, d = int(m.group(1)), int(m.group(2))
        day = _safe_date(fallback_year, mo, d)
        if day is not None:
            days.append(day)

    if not days:
        return None, None
    days.sort()
    return days[0].isoformat(), days[-1].isoformat()


def _parse_duration(text: str) -> tuple[float | None, float | None]:
    """Extract a target duration in seconds (min, max)."""
    m = _DUR_RANGE.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = sorted((a, b))
        return lo * 60.0, hi * 60.0
    m = _DUR_SINGLE.search(text)
    if m:
        v = int(m.group(1)) * 60.0
        return v, v
    return None, None


def _parse_aspect(text: str) -> str | None:
    m = _ASPECT.search(text)
    if not m:
        return None
    w, h = m.group(1), m.group(2)
    # Drop a trailing ".0" so "16.0" → "16".
    if w.endswith(".0"):
        w = w[:-2]
    return f"{w}:{h}"


def _safe_date(year: int, month: int, day: int) -> _dt.date | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return _dt.date(year, month, day)
    except ValueError:
        return None
