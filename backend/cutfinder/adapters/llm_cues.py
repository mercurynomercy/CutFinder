"""Pure helpers for LLM-chosen subtitle line breaks (no network, no LLM).

Aligned tokens are ``(text, start_s, end_s)`` triples. These helpers split a
token stream into LLM-sized windows, render a window as marked text, and map
the LLM's ``|`` break marks back onto token boundaries.
"""

from __future__ import annotations

import logging
import re

from ..domain.models import Segment
from ..ports.speech import CueSegmenter, SegmenterUnavailable

logger = logging.getLogger(__name__)

Token = tuple[str, float, float]

_SOFT_END = "，、；,;"

# An LLM line wider / longer than this gets one LLM retry, else rule grouping.
_LINE_MAX_WIDTH = 24
_LINE_MAX_DUR = 8.0
# LLM-origin runs only fold true fragments: the LLM's breaks are deliberate.
_LLM_SHORT_MAX_CHARS = 2
_LLM_SHORT_MAX_DUR = 0.7
_LLM_MERGE_MAX_CHARS = 12  # x _MERGE_OVERFLOW (1.5) = 18 visible chars


def _nchars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def make_windows(tokens: list[Token], target: int = 400, cap: int = 600) -> list[list[Token]]:
    """Split *tokens* into windows of ~*target* chars, cut after hard punctuation.

    A window exceeding *cap* is cut after the token followed by the largest
    pause (ties prefer a token ending in a soft comma). A tiny tail window
    merges into the previous one.
    """
    # Lazy: qwen_transcriber imports this module, so a top-level import would be circular.
    from cutfinder.adapters.qwen_transcriber import _HARD_PUNCT

    windows: list[list[Token]] = []
    cur: list[Token] = []
    count = 0
    for tok in tokens:
        cur.append(tok)
        count += _nchars(tok[0])
        if count > cap and len(cur) > 1:
            i = max(
                range(len(cur) - 1),
                key=lambda k: (cur[k + 1][1] - cur[k][2], cur[k][0].rstrip()[-1:] in _SOFT_END),
            )
            windows.append(cur[: i + 1])
            cur = cur[i + 1 :]
            count = sum(_nchars(t[0]) for t in cur)
        if count >= target and any(c in _HARD_PUNCT for c in tok[0]):
            windows.append(cur)
            cur, count = [], 0
    if cur:
        if windows and count < target // 3:
            windows[-1].extend(cur)
        else:
            windows.append(cur)
    return windows


def marked_text(window: list[Token], gap_s: float) -> str:
    """Joined token text with ``/`` before any token that follows a pause > *gap_s*."""
    parts: list[str] = []
    for i, (text, start, _end) in enumerate(window):
        if i and start - window[i - 1][2] > gap_s:
            parts.append("/")
        parts.append(text)
    return "".join(parts).strip()


def breaks_from_reply(original: str, reply: str) -> list[int] | None:
    """Non-whitespace char offsets of each break in *reply*, or None if the text differs.

    *reply* is walked against *original* (whitespace ignored): a char equal to
    the next original char is text (so a literal ``/`` or ``|`` in the transcript
    matches itself); otherwise ``|``/``｜`` is a break, ``/`` a pause marker, and
    anything else a mismatch.
    """
    chars = re.sub(r"\s", "", original)
    offsets: list[int] = []
    pos = 0
    for ch in reply:
        if ch.isspace():
            continue
        if pos < len(chars) and ch == chars[pos]:
            pos += 1
        elif ch in "|｜":
            if 0 < pos < len(chars) and (not offsets or offsets[-1] != pos):
                offsets.append(pos)
        elif ch != "/":
            return None
    return offsets if pos == len(chars) else None


def split_at_breaks(window: list[Token], breaks: list[int]) -> list[list[Token]]:
    """Split *window*; a break at offset k closes the line after the token containing char k."""
    brk = set(breaks)
    lines: list[list[Token]] = []
    cur: list[Token] = []
    prev = 0
    for tok in window:
        pos = prev + _nchars(tok[0])
        cur.append(tok)
        if any(prev < k <= pos for k in brk):
            lines.append(cur)
            cur = []
        prev = pos
    if cur:
        lines.append(cur)
    return lines


def _gap_split(line: list[Token], gap_s: float) -> list[list[Token]]:
    """Split *line* wherever the pause between two tokens exceeds *gap_s*."""
    pieces = [[line[0]]]
    for prev, tok in zip(line, line[1:]):
        if tok[1] - prev[2] > gap_s:
            pieces.append([])
        pieces[-1].append(tok)
    return pieces


def _cue(piece: list[Token]) -> Segment:
    return Segment(
        start_s=piece[0][1], end_s=piece[-1][2], text="".join(t[0] for t in piece).strip(),
    )


class _Breaker:
    """Stops LLM calls for the rest of one transcription once the server is gone."""

    def __init__(self, segmenter: CueSegmenter) -> None:
        self._segmenter = segmenter
        self.tripped = False

    def ask(self, text: str) -> str | None:
        if self.tripped:
            return None
        try:
            return self._segmenter.split(text)
        except SegmenterUnavailable as exc:
            self.tripped = True
            logger.warning("LLM subtitle segmenter unavailable, using rule cues: %s", exc)
            return None


def _llm_window_cues(
    window: list[Token], breaker: _Breaker, *, max_chars: int, max_dur: float, gap_s: float,
) -> list[Segment] | None:
    """Cues for *window* from LLM-chosen breaks plus guards; None = use the rule path."""
    from cutfinder.adapters.qwen_transcriber import _display_width, group_cues  # lazy: circular

    plain = "".join(t[0] for t in window)
    reply = breaker.ask(marked_text(window, gap_s))
    if reply is None:
        return None
    breaks = breaks_from_reply(plain, reply)
    if breaks is None:
        logger.warning("LLM subtitle breaks changed the text; using rule cues for this window")
        return None

    def _fits(cue: Segment) -> bool:
        return (
            _display_width(cue.text) <= _LINE_MAX_WIDTH
            and cue.end_s - cue.start_s <= _LINE_MAX_DUR
        )

    def _keep_or_group(piece: list[Token]) -> list[Segment]:
        cue = _cue(piece)
        if _fits(cue):
            return [cue]
        return group_cues(piece, offset=0.0, max_chars=max_chars, max_dur=max_dur, gap_s=gap_s)

    cues: list[Segment] = []
    for line in split_at_breaks(window, breaks):
        for piece in _gap_split(line, gap_s):
            cue = _cue(piece)
            if _fits(cue):
                cues.append(cue)
                continue
            text = "".join(t[0] for t in piece)
            retry = breaker.ask(text)
            sub_breaks = breaks_from_reply(text, retry) if retry is not None else None
            sub_lines = split_at_breaks(piece, sub_breaks) if sub_breaks else []
            # Retry pieces are guarded again (no further retry); one line = rule grouping.
            pieces = (
                [p for sub in sub_lines for p in _gap_split(sub, gap_s)]
                if len(sub_lines) > 1 else [piece]
            )
            cues.extend(c for p in pieces for c in _keep_or_group(p))
    return cues


def llm_assemble_cues(
    chunk_results: list[list[Token] | Segment],
    segmenter: CueSegmenter,
    *, max_chars: int, max_dur: float, gap_s: float,
    merge_gap_s: float, merge_short_max: int, merge_short_dur: float,
) -> list[Segment]:
    """Like the rule path (assemble → clean → merge), but with LLM-chosen line breaks.

    Token stretches are cut into windows; each window the LLM answers validly
    becomes LLM-origin cues, any other window (and every fallback ``Segment``)
    stays rule-origin. Adjacent rule-origin items are assembled together exactly
    as :func:`assemble_cues` would, so with no usable LLM the output equals
    today's rule path. Cleaning spans all runs; each run is merged with its
    origin's params.
    """
    from cutfinder.adapters.qwen_transcriber import (  # lazy: circular
        assemble_cues, clean_cues, merge_short_cues,
    )

    breaker = _Breaker(segmenter)
    # Ordered runs: ("llm", [Segment, ...]) or ("rule", [token list | Segment, ...]).
    runs: list[tuple[str, list]] = []

    def _add(origin: str, items: list) -> None:
        if runs and runs[-1][0] == origin:
            runs[-1][1].extend(items)
        else:
            runs.append((origin, list(items)))

    def _flush(stretch: list[Token]) -> None:
        for window in make_windows(stretch):
            try:
                cues = _llm_window_cues(
                    window, breaker, max_chars=max_chars, max_dur=max_dur, gap_s=gap_s,
                )
            except Exception:
                logger.warning("LLM subtitle segmenter failed; using rule cues", exc_info=True)
                cues = None
            if cues is None:
                _add("rule", [window])
            else:
                _add("llm", cues)

    stretch: list[Token] = []
    for r in chunk_results:
        if isinstance(r, Segment):
            _flush(stretch)
            stretch = []
            _add("rule", [r])
        else:
            stretch.extend(r)
    _flush(stretch)

    # Clean as one pass over all runs (clean_cues folds a zero-width cue onto its
    # predecessor, which may sit in the previous run), keeping each run's origin.
    cleaned: list[tuple[str, list[Segment]]] = []
    for origin, items in runs:
        raw = items if origin == "llm" else assemble_cues(
            items, max_chars=max_chars, max_dur=max_dur, gap_s=gap_s,
        )
        # The LLM breaks after commas, so a back-to-back repeat is real speech.
        llm = origin == "llm"
        prev = next((c for _, c in reversed(cleaned) if c), None)
        if prev:
            head, *rest = clean_cues([prev[-1], *raw], dedup_overlap_only=llm)
            prev[-1] = head
            cleaned.append((origin, rest))
        else:
            cleaned.append((origin, clean_cues(raw, dedup_overlap_only=llm)))

    out: list[Segment] = []
    for origin, cues in cleaned:
        if origin == "llm":
            out.extend(merge_short_cues(
                cues, max_gap_s=merge_gap_s,
                short_max_chars=_LLM_SHORT_MAX_CHARS, short_max_dur=_LLM_SHORT_MAX_DUR,
                max_chars=_LLM_MERGE_MAX_CHARS, max_dur=max_dur,
            ))
        else:
            out.extend(merge_short_cues(
                cues, max_gap_s=merge_gap_s, short_max_chars=merge_short_max,
                short_max_dur=merge_short_dur, max_chars=max_chars, max_dur=max_dur,
            ))
    return out
