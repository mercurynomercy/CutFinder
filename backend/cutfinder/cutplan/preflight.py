"""Deterministic pre-flight clarification check (§3.15, B1).

Runs before the director's per-day generation loop starts. Only two fields
have no safe default — date range (no range means "search the whole
library", which can overflow local-model context on a large library) and
target duration (no target means no duration check at all). Both are checked
against the real catalog, not just the message text, so we only ask when
guessing would actually be ambiguous.
"""

from __future__ import annotations

from ..domain.models import ClipBrief, PendingClarification, RoughCutRequest
from ..localdate import local_day
from .prompts import message


def check_preflight(
    request: RoughCutRequest,
    retriever: object,
    already_asked: set[str],
    lang: str = "zh",
) -> PendingClarification | None:
    """Return a pending question if *request* is missing something worth asking, else None."""
    if request.date_from is None and request.date_to is None and "date" not in already_asked:
        briefs: list[ClipBrief] = retriever.search_footage()  # type: ignore[attr-defined]
        days = sorted({d for d in (local_day(b.capture_time) for b in briefs) if d})
        if len(days) > 1:
            return PendingClarification(
                kind="preflight_date",
                question=message("preflight_date_question", lang),
                options=days[:8],
            )

    if (
        request.target_min_s is None
        and request.target_max_s is None
        and "duration" not in already_asked
    ):
        return PendingClarification(
            kind="preflight_duration",
            question=message("preflight_duration_question", lang),
            options=[
                message("duration_opt_5min", lang),
                message("duration_opt_10min", lang),
                message("duration_opt_15_20min", lang),
                message("duration_opt_unlimited", lang),
            ],
        )

    return None
