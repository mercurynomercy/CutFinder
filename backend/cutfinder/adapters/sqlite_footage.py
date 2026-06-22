"""CatalogFootageRetriever — read-only footage search over the catalog.

Wraps :class:`CatalogRepository` to give the rough-cut director date-range /
type / tag / full-text search plus per-clip detail (transcript segments +
keyframe cut points). Read-only: it never writes to the catalog.
"""

from __future__ import annotations

from ..domain.models import ClipBrief, ClipDetail, ClipFilter, ClipSummary
from ..ports.repository import CatalogRepository


class CatalogFootageRetriever:
    """:class:`FootageRetriever` backed by the SQLite catalog."""

    def __init__(self, repository: CatalogRepository) -> None:
        self._repo = repository

    def search_footage(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        roll: str | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
    ) -> list[ClipBrief]:
        # Pick a base result set: full-text search if a query is given,
        # otherwise a filtered list (roll + first tag handled in SQL).
        if query:
            rows = self._repo.search(query)
        else:
            first_tag = tags[0] if tags else None
            rows = self._repo.query_clips(ClipFilter(roll_type=roll, tag=first_tag))

        out: list[ClipBrief] = []
        for r in rows:
            if roll and r.roll_type != roll:
                continue
            if not _in_date_range(r, date_from, date_to):
                continue
            clip_tags = [t.name for t in self._repo.get_tags(r.id)]
            if tags and not all(t in clip_tags for t in tags):
                continue
            out.append(self._to_brief(r, clip_tags))
        return out

    def get_clip_detail(self, clip_id: int) -> ClipDetail | None:
        clip = self._repo.get_clip(clip_id)
        if clip is None:
            return None
        transcript = self._repo.get_transcript(clip_id)
        return ClipDetail(
            clip_id=clip_id,
            roll=clip.roll_type,
            duration_s=clip.duration_s,
            source_path=clip.source_path,
            library_path=clip.library_path,
            summary=clip.summary,
            description=clip.description,
            tags=[t.name for t in self._repo.get_tags(clip_id)],
            segments=list(transcript.segments) if transcript else [],
            keyframes=self._repo.get_keyframes(clip_id),
        )

    def _to_brief(self, r: ClipSummary, clip_tags: list[str]) -> ClipBrief:
        ct = r.capture_time.isoformat() if r.capture_time is not None else None
        return ClipBrief(
            clip_id=r.id,
            roll=r.roll_type,
            capture_time=ct,
            duration_s=r.duration_s,
            summary=r.summary,
            description=r.description,
            tags=clip_tags,
            has_transcript=self._repo.get_transcript(r.id) is not None,
            has_keyframes=bool(getattr(r, "has_keyframes", False)),
        )


def _in_date_range(r: ClipSummary, date_from: str | None, date_to: str | None) -> bool:
    """True if the clip's capture date falls within [date_from, date_to]."""
    if not date_from and not date_to:
        return True
    ct = r.capture_time
    if ct is None or not hasattr(ct, "isoformat"):
        return False
    day = ct.date().isoformat()
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True
