"""CatalogRepository — SQLite data access for all clip/tag/transcript/job records."""

from __future__ import annotations

from typing import Any, Protocol
import datetime as _dt  # noqa: F401 — kept for type annotations below

from ..domain.models import (
    Clip,
    ClipSummary,
    Tag,
    Transcript,
    AnalysisResult,
    Job,
    JobFailedItem,
    ClipFilter,
)


class CatalogRepository(Protocol):
    """Persist and query the catalog database (SQLite).

    This protocol hides all SQL from business logic.  The real
    implementation lives in ``adapters/sqlite_repo.py`` and uses an
    ``:memory:`` or on-disk SQLite connection.  Tests inject either a
    fake (for unit tests) or an in-memory real impl (fast & no deps).
    """

    # ── Clip CRUD ────────────────────────────────────────────────

    def exists_fingerprint(self, fp: str) -> bool:
        """Return True if a clip with this fingerprint already exists."""

    def upsert_clip(self, clip: Clip) -> int:
        """Insert or update a clip record. Returns the clip id."""

    def get_clip(self, clip_id: int) -> Clip | None:
        """Fetch a single clip by id (with tags + transcript joined)."""

    def delete_clip(self, clip_id: int) -> None:
        """Delete a clip and all related tags/transcripts."""

    # ── Query / Filter / Search (FTS5) ─────────────────────────

    def query_clips(self, f: ClipFilter) -> list[ClipSummary]:
        """List clips matching optional filters (date, roll_type, tag)."""

    def search(self, q: str) -> list[ClipSummary]:
        """Full-text search across summary + description + transcript."""

    # ── Tags (per-clip) ────────────────────────────────────────

    def get_tags(self, clip_id: int) -> list[Tag]:
        """Return all tags for a given clip."""

    def set_tags(self, clip_id: int, tags: list[Tag]) -> None:
        """Replace all tags for a clip (full overwrite)."""

    def add_tag(self, clip_id: int, tag_name: str) -> None:
        """Add a single manual tag (idempotent by clip_id+name)."""

    def remove_tag(self, clip_id: int, tag_name: str) -> None:
        """Remove a specific tag from a clip."""

    # ── Roll correction (remember manual A/B override) ───────────

    def correct_roll(self, clip_id: int, roll: str) -> None:
        """Set ``roll_source='manual'`` and update the roll type.

        This prevents future auto-scans from overwriting the user's
        correction (see proposal §5.1).
        """

    # ── Re-analyze: update only AI-generated fields ───────────────

    def update_analysis(self, clip_id: int, r: AnalysisResult) -> None:
        """Update transcript/summary/vision fields and auto-tags only.

        Manual tags and manual roll corrections are preserved untouched
        (see detailed-design §3.11 re-analyze semantics).
        """

    # ── Transcript (A-roll) ───────────────────────────────────────

    def save_transcript(self, clip_id: int, t: Transcript) -> None:
        """Upsert transcript for a clip (replaces old one)."""

    def get_transcript(self, clip_id: int) -> Transcript | None:
        """Load transcript for a single clip."""

    # ── Job queue tracking ────────────────────────────────────────

    def create_job(self, total: int, kind: str = "scan") -> Job:
        """Create a new queued job record. Returns the ``Job``."""

    def update_job(self, job_id: int, **fields: Any) -> None:
        """Update selected fields of a queued/running/completed job."""

    def get_job(self, job_id: int) -> Job | None:
        """Fetch a single job record."""

    def list_jobs(self, limit: int | None = None) -> list[Job]:
        """List jobs newest-first, optionally limited."""

    def delete_job(self, job_id: int) -> None:
        """Delete a job and its recorded failed items."""

    def record_failed_item(self, item: JobFailedItem) -> None:
        """Record one failed queue item for later retry."""

    def get_failed_items(self, job_id: int) -> list[JobFailedItem]:
        """Return all recorded failed items for a job."""

    def clear_failed_items(self, job_id: int) -> None:
        """Remove all recorded failed items for a job."""
