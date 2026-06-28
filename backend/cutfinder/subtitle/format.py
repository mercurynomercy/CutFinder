"""Pure subtitle renderers — no I/O.

Two formats are produced from a list of :class:`~cutfinder.domain.models.Segment`:

* :func:`to_srt` — standard SubRip (``HH:MM:SS,mmm`` timecodes, comma).
* :func:`to_itt` — TTML for Final Cut Pro (``HH:MM:SS.mmm`` timecodes, dot).

Both handle sub-second and multi-hour timestamps and an empty segment list.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from ..domain.models import Segment


def _clamp(seconds: float) -> float:
    """Clamp a timestamp to be non-negative."""
    return seconds if seconds > 0 else 0.0


def _hms_ms(seconds: float) -> tuple[int, int, int, int]:
    """Split *seconds* into (hours, minutes, seconds, milliseconds)."""
    total_ms = int(round(_clamp(seconds) * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return h, m, s, ms


def _srt_timecode(seconds: float) -> str:
    """Render *seconds* as ``HH:MM:SS,mmm`` (comma before milliseconds)."""
    h, m, s, ms = _hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _itt_timecode(seconds: float) -> str:
    """Render *seconds* as ``HH:MM:SS.mmm`` (dot before milliseconds)."""
    h, m, s, ms = _hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def enforce_min_duration(segments: list[Segment], min_s: float) -> list[Segment]:
    """Hold each cue on screen for at least *min_s* seconds.

    A cue's end is pushed out to ``start + min_s`` so short cues (e.g. a 2-3
    character utterance) stay readable, but never past the next cue's start, so
    no overlap is introduced — a cue with little trailing silence extends only
    into the gap available. A cue already long enough is left unchanged, and
    *min_s* <= 0 returns the segments unchanged.
    """
    if min_s <= 0 or not segments:
        return list(segments)
    out: list[Segment] = []
    n = len(segments)
    for i, seg in enumerate(segments):
        new_end = seg.start_s + min_s
        if i + 1 < n:
            new_end = min(new_end, segments[i + 1].start_s)
        new_end = max(new_end, seg.end_s)  # never shorten an existing cue
        out.append(Segment(start_s=seg.start_s, end_s=new_end, text=seg.text))
    return out


def to_srt(segments: list[Segment]) -> str:
    """Render *segments* as a standard SRT document.

    Entries are 1-based; each text is trimmed of surrounding whitespace and
    a blank line separates entries. An empty list yields an empty string.
    """
    blocks: list[str] = []
    for index, seg in enumerate(segments, start=1):
        start = _srt_timecode(seg.start_s)
        end = _srt_timecode(seg.end_s)
        text = seg.text.strip()
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def to_itt(segments: list[Segment], *, language: str, fps: float) -> str:
    """Render *segments* as a TTML (iTT) document for Final Cut Pro.

    The header carries ``ttp:frameRate`` (rounded *fps*) and ``xml:lang``;
    each segment becomes one ``<p>`` with dotted timecodes. Text is
    XML-escaped. An empty list still yields a valid document with an empty
    ``<div>``.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<tt xmlns="http://www.w3.org/ns/ttml" '
            'xmlns:ttp="http://www.w3.org/ns/ttml#parameter" '
            'ttp:timeBase="media" '
            f'ttp:frameRate="{round(fps)}" '
            f'xml:lang="{language}">'
        ),
        "<body>",
        "<div>",
    ]
    for seg in segments:
        begin = _itt_timecode(seg.start_s)
        end = _itt_timecode(seg.end_s)
        text = escape(seg.text.strip())
        lines.append(f'<p begin="{begin}" end="{end}">{text}</p>')
    lines.extend(["</div>", "</body>", "</tt>"])
    return "\n".join(lines)
