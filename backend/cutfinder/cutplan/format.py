"""Pure shot-list rendering — CutPlan → human-readable Markdown.

No I/O: deterministic and easy to golden-test. Groups shots by chapter,
renders one table per chapter, and appends a duration roll-up that flags
when the total misses the requested target window.
"""

from __future__ import annotations

from ..domain.models import CutPlan, Shot

# Output language is Chinese by default (matches the project), but the static
# labels are kept terse so the table stays readable in any editor.
_HEADER = "| # | 日期 | 入–出 | 时长 | 类型 | 文件 | 缩略图 | 内容/台词 | 用途·理由 |"
_DIVIDER = "|---|---|---|---|---|---|---|---|---|"

_ROLL_LABEL = {"a": "A-roll", "b": "B-roll"}


def format_timecode(seconds: float) -> str:
    """Format *seconds* as ``HH:MM:SS.mmm`` (clamped at 0)."""
    s = max(0.0, float(seconds))
    millis = int(round(s * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_duration(seconds: float) -> str:
    """Format a duration as ``M:SS`` (or ``H:MM:SS`` past an hour)."""
    s = int(round(max(0.0, float(seconds))))
    hours, s = divmod(s, 3600)
    minutes, secs = divmod(s, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _escape(text: str) -> str:
    """Escape pipes/newlines so a cell can't break the Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _shot_row(index: int, shot: Shot) -> str:
    span = max(0.0, shot.out_s - shot.in_s)
    tc = f"{format_timecode(shot.in_s)} – {format_timecode(shot.out_s)}"
    roll = _ROLL_LABEL.get(shot.roll, shot.roll or "")
    thumb = f"![]({shot.thumb_ref})" if shot.thumb_ref else ""
    return (
        f"| {index} | {_escape(shot.clip_date)} | {tc} | {format_duration(span)} | {roll} "
        f"| {_escape(shot.clip_label)} | {thumb} "
        f"| {_escape(shot.content)} | {_escape(shot.rationale)} |"
    )


def _ordered_chapters(plan: CutPlan) -> list[str]:
    """Chapters in plan order, falling back to first-seen order in shots."""
    if plan.chapters:
        return list(plan.chapters)
    seen: list[str] = []
    for shot in plan.shots:
        ch = shot.chapter or ""
        if ch not in seen:
            seen.append(ch)
    return seen or [""]


def to_shotlist_markdown(plan: CutPlan) -> str:
    """Render *plan* as a chapter-grouped Markdown shot list with a footer."""
    lines: list[str] = []

    index = 1
    for chapter in _ordered_chapters(plan):
        shots = [s for s in plan.shots if (s.chapter or "") == (chapter or "")]
        if not shots:
            continue
        lines.append(f"## {chapter}" if chapter else "## 未分章")
        lines.append("")
        lines.append(_HEADER)
        lines.append(_DIVIDER)
        for shot in shots:
            lines.append(_shot_row(index, shot))
            index += 1
        lines.append("")

    # Duration roll-up footer.
    total = format_duration(plan.total_s)
    if plan.target_min_s is not None and plan.target_max_s is not None:
        target = f"{format_duration(plan.target_min_s)}–{format_duration(plan.target_max_s)}"
        if plan.within_target:
            lines.append(f"**总时长：{total}**（目标 {target} ✓）")
        else:
            lines.append(f"**总时长：{total}**（目标 {target} ⚠️ 未命中目标时长）")
    else:
        lines.append(f"**总时长：{total}**")

    if plan.note:
        lines.append("")
        lines.append(plan.note)

    return "\n".join(lines).rstrip() + "\n"
