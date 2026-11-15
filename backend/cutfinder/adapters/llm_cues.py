"""Pure helpers for LLM-chosen subtitle line breaks (no network, no LLM).

Aligned tokens are ``(text, start_s, end_s)`` triples. These helpers split a
token stream into LLM-sized windows, render a window as marked text, and map
the LLM's ``|`` break marks back onto token boundaries.
"""

from __future__ import annotations

import re

Token = tuple[str, float, float]

_SOFT_END = "，、；,;"


def _nchars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def make_windows(tokens: list[Token], target: int = 400, cap: int = 600) -> list[list[Token]]:
    """Split *tokens* into windows of ~*target* chars, cut after hard punctuation.

    A window exceeding *cap* is cut after the token followed by the largest
    pause (ties prefer a token ending in a soft comma). A tiny tail window
    merges into the previous one.
    """
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
    """Non-whitespace char offsets of each ``|`` in *reply*, or None if the text differs."""
    reply = reply.replace("/", "")
    if re.sub(r"\s", "", reply.replace("|", "")) != re.sub(r"\s", "", original):
        return None
    total = _nchars(original)
    offsets: list[int] = []
    pos = 0
    for ch in reply:
        if ch == "|":
            if 0 < pos < total and (not offsets or offsets[-1] != pos):
                offsets.append(pos)
        elif not ch.isspace():
            pos += 1
    return offsets


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
