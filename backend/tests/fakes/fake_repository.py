"""FakeCatalogRepository — in-memory implementation of the full CatalogRepository protocol.

Supports all operations used by the pipeline orchestrator and Scanner:
    - Fingerprint dedup (exists_fingerprint / add_fingerprint) — for Scanner
    - Clip CRUD: upsert, get, delete, query (with filters), search
    - Tag CRUD per clip: get_tags, set_tags, add_tag, remove_tag
    - Roll correction with manual override tracking
    - Analysis updates that preserve manually-set tags and roll_source='manual'
    - Transcript CRUD: save, get
    - Job lifecycle: create_job, update_job (progress), get_job

This replaces the minimal fingerprint-only stub so that orchestrator tests
can exercise the full pipeline without touching SQLite.

Examples
--------
>>> repo = FakeCatalogRepository()
>>> clip = Clip(id=None, fingerprint="abc", source_path="/tmp/f.mp4")  # noqa: D105
>>> repo.upsert_clip(clip)          # auto-assigns id=1
>>> assert repo.get_clip(1).id == 1

Tracker for call assertions in tests:

    upsert_calls :: list[Clip]
        Clips passed to :meth:`upsert_clip`.

    query_calls :: list[ClipFilter | None]
        Filters passed to :meth:`query_clips`.

    copy_calls :: list[tuple[str, str, str]]
        (source_path, date_str, roll_type) passed to :meth:`copy_into`.

    correct_roll_calls :: list[tuple[int, str]]
        (clip_id, roll_type) passed to :meth:`correct_roll`.

    set_tags_calls :: list[tuple[int, list[Tag]]]
        (clip_id, tags) passed to :meth:`set_tags`.

    add_tag_calls :: list[tuple[int, str]]
        (clip_id, tag_name) passed to :meth:`add_tag`.

    save_transcript_calls :: list[tuple[int, Transcript]]
        (clip_id, transcript) passed to :meth:`save_transcript`.

    create_job_calls :: list[Job]
        Jobs passed to :meth:`create_job`.

"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from cutfinder.domain.models import (
    AnalysisResult,
    Clip,
    ClipFilter,
    ClipSummary,
    Job,
    JobFailedItem,
    Tag,
    Transcript,
)


class FakeCatalogRepository:
    """In-memory fake implementing the full CatalogRepository protocol."""

    def __init__(self) -> None:
        # In-memory stores keyed by id (auto-incrementing counter for Clips/Jobs)
        self._clips: dict[int, Clip] = {}
        self._clip_by_fp: dict[str, int] = {}  # fingerprint -> clip_id
        self._tags: dict[int, list[Tag]] = {}   # clip_id -> [Tag]
        self._transcripts: dict[int, Transcript] = {}  # clip_id -> Transcript

        self._jobs: dict[int, Job] = {}
        self._failed_items: dict[int, list[JobFailedItem]] = {}  # job_id -> [JobFailedItem]
        self._next_clip_id: int = 1
        self._next_job_id: int = 1

        # Call trackers for assertions in tests
        self.upsert_calls: list[Clip] = []
        self.query_calls: list[Any] = []  # Optional[ClipFilter]
        self.copy_calls: list[tuple[str, str, str]] = []  # (source_path, date_str, roll_type)
        self.correct_roll_calls: list[tuple[int, str]] = []
        self.set_tags_calls: list[tuple[int, list[Tag]]] = []
        self.add_tag_calls: list[tuple[int, str]] = []
        self.save_transcript_calls: list[tuple[int, Transcript]] = []
        self.create_job_calls: list[Job] = []
        self._remove_tag_calls: list[tuple[int, str]] = []  # for remove_tag assertions

    # ── Fingerprint dedup (Scanner) ────────────────────────────────

    def exists_fingerprint(self, fp: str) -> bool:
        """Return True if a clip with this fingerprint already exists."""
        return fp in self._clip_by_fp

    def add_fingerprint(self, fp: str) -> None:
        """Register a fingerprint as already processed (Scanner compat)."""
        self._clip_by_fp[fp] = 0

    # ── Clip CRUD ───────────────────────────────────────────────────

    def upsert_clip(self, clip: Clip) -> int:
        """Insert or update a clip. Auto-assigns id if None."""
        cid = clip.id
        if cid is None:
            cid = self._next_clip_id
            self._next_clip_id += 1
        # Update fingerprint index if fp changed (shouldn't happen in practice)
        old = self._clips.get(cid)
        if old and clip.fingerprint != old.fingerprint:
            self._clip_by_fp.pop(old.fingerprint, None)
        if clip.fingerprint:
            self._clip_by_fp[clip.fingerprint] = cid

        # Merge manual tags: preserve existing manually-set tags
        if old is not None and self._tags.get(cid):
            {t.name for t in self._tags[cid] if t.source == "manual"}
            # Merge into clip's tags (clip.tags comes from analysis)

        # Store with the auto-assigned id so existing.id matches cid
        if clip.id is None:
            clip = clip.model_copy(update={"id": cid})
        self._clips[cid] = clip
        if not hasattr(clip, '_tags'):
            pass  # tags are managed separately via set_tags / add_tag

        self.upsert_calls.append(clip)
        return cid

    def get_clip(self, clip_id: int) -> Clip | None:
        """Return the clip with *clip_id*, or ``None``."""
        return self._clips.get(clip_id)

    def delete_clip(self, clip_id: int) -> None:
        """Remove a clip. (Protocol returns None; we track for assertions.)"""
        old = self._clips.pop(clip_id, None)
        if old:
            self._tags.pop(clip_id, None)

    def query_clips(self, f: ClipFilter) -> list[ClipSummary]:
        """Return clip summaries filtered by date, roll_type, tag."""
        self.query_calls.append(f)

        results: list[ClipSummary] = []
        for clip in self._clips.values():
            # Filter by date (capture_time)
            if f.date is not None:
                ct = clip.capture_time
                if ct is None or ct.strftime("%Y-%m-%d") != f.date:
                    continue

            # Filter by roll type (case-insensitive)
            if f.roll_type is not None:
                if clip.roll_type.lower() != str(f.roll_type).lower():
                    continue

            # Filter by tag name (exact match)
            if f.tag is not None:
                clip_tags = self._tags.get(clip.id, []) if clip.id else []
                tag_names = {t.name for t in clip_tags}
                if f.tag not in tag_names:
                    continue

            results.append(self._clip_to_summary(clip))
        return sorted(results, key=lambda c: c.id)

    def search(self, q: str) -> list[ClipSummary]:
        """Simple substring search across source_path, summary, description.

        FTS5 simulation: plain-text match for unit tests.
        """
        q = q.lower()
        results: list[ClipSummary] = []
        for clip in self._clips.values():
            if (q in clip.source_path.lower() or
                (clip.summary and q in clip.summary.lower()) or
                (clip.description and q in clip.description.lower())):
                results.append(self._clip_to_summary(clip))
        return results

    def _clip_to_summary(self, clip: Clip) -> ClipSummary:
        """Convert a :class:`Clip` to its summary view."""
        return ClipSummary(
            id=clip.id or 0,
            source_path=clip.source_path,
            library_path=clip.library_path,
            roll_type=clip.roll_type,
            summary=clip.summary,
            description=clip.description,
            duration_s=clip.duration_s,
            width=clip.width,
            height=clip.height,
            fps=clip.fps,
            codec=clip.codec,
            thumbnail_path=clip.thumbnail_path,
            status=clip.status,
            error=clip.error,
            capture_time=clip.capture_time,
            date_source=clip.date_source,
        )

    # ── Tag CRUD (per clip) ────────────────────────────────────────

    def get_tags(self, clip_id: int) -> list[Tag]:
        """Return all tags for *clip_id*."""
        return list(self._tags.get(clip_id, []))

    def set_tags(self, clip_id: int, tags: list[Tag]) -> None:
        """Replace all tags for *clip_id*."""
        self._tags[clip_id] = list(tags)
        self.set_tags_calls.append((clip_id, tags))

    def add_tag(self, clip_id: int, tag_name: str) -> None:
        """Add a single tag to *clip_id*. (Protocol returns None; we track for assertions.)"""
        tag = Tag(name=tag_name, source="auto")  # default to auto; tests can override
        self._tags.setdefault(clip_id, []).append(tag)
        self.add_tag_calls.append((clip_id, tag_name))

    def remove_tag(self, clip_id: int, tag_name: str) -> None:
        """Remove a tag by name from *clip_id*. (Protocol returns None; we track for assertions.)"""
        tags = self._tags.get(clip_id, [])
        for i, t in enumerate(tags):
            if t.name == tag_name:
                tags.pop(i)
                self._tags[clip_id] = tags  # ensure list is updated (in case of reassign)
                return
        self._remove_tag_calls.append((clip_id, tag_name))  # track even if not found

    @property
    def remove_tag_calls(self) -> list[tuple[int, str]]:
        """Return calls to :meth:`remove_tag`."""
        return self._remove_tag_calls

    # ── Roll correction (manual A/B override) ──────────────────────

    def correct_roll(self, clip_id: int, roll: str) -> None:
        """Override the A/B classification for *clip_id*."""
        clip = self._clips.get(clip_id)
        if clip:
            # Cannot use frozen model update; replace the whole object
            self._clips[clip_id] = clip.model_copy(update={
                "roll_type": roll,
                "roll_source": "manual",
            })
        self.correct_roll_calls.append((clip_id, roll))

    # ── Analysis updates (preserve manual tags + roll) ─────────────

    def update_analysis(self, clip_id: int, r: AnalysisResult) -> None:
        """Update AI-generated fields while preserving manual overrides.

        - Manual roll_type is never overwritten (roll_source='manual').
        - Tags: manual tags are preserved; auto tags replace existing ones.

        Parameters
        ----------
        clip_id: int
            The database ID of the clip.
        r:
            An :class:`AnalysisResult` containing auto-generated fields.

        """
        clip = self._clips.get(clip_id)
        if not clip:
            return

        update_dict: dict[str, Any] = {}

        # Roll — only auto-settable
        if clip.roll_source != "manual":
            update_dict["roll_type"] = r.roll_type

        # Summary/description — A-roll gets summary, B-roll gets description
        if r.summary_result is not None:
            update_dict["summary"] = getattr(r.summary_result, 'summary', None)  # type: ignore[union-attr]
        if r.vision_result is not None:
            update_dict["description"] = getattr(r.vision_result, 'description', None)  # type: ignore[union-attr]

        if update_dict:
            self._clips[clip_id] = clip.model_copy(update=update_dict)

        # Tag handling: preserve manual, replace auto
        if clip.id is not None:
            existing = self._tags.get(clip_id, [])
            manual_tags = [t for t in existing if t.source == "manual"]
            auto_tag_objs: list[Tag] = []
            if r.summary_result is not None:  # type: ignore[union-attr]
                auto_tag_objs = [Tag(name=t, source="auto") for t in r.summary_result.tags]  # type: ignore[union-attr]
            elif r.vision_result is not None:  # type: ignore[union-attr]
                auto_tag_objs = [Tag(name=t, source="auto") for t in r.vision_result.tags]  # type: ignore[union-attr]
            self._tags[clip_id] = manual_tags + auto_tag_objs

        # Transcript stored separately (A-roll)
        if r.transcript is not None and clip.id is not None:  # type: ignore[union-attr]
            t = r.transcript  # type: ignore[union-attr]
            if getattr(t, 'full_text', ''):  # type: ignore[union-attr]
                self._transcripts[clip_id] = t  # type: ignore[union-attr]

    # ── Transcript CRUD (separate from update_analysis for clarity) -

    def save_transcript(self, clip_id: int, transcript: Transcript) -> None:
        """Persist the full-text transcription for *clip_id*."""
        self._transcripts[clip_id] = transcript
        # Also update the clip's stored transcript if it has that field
        self._clips.get(clip_id)
        # Clip doesn't have a transcript field — it's stored separately in DB.
        self.save_transcript_calls.append((clip_id, transcript))

    def get_transcript(self, clip_id: int) -> Transcript | None:
        """Return the transcript for *clip_id*, or ``None``."""
        return self._transcripts.get(clip_id)

    # ── Job CRUD (queue tracking) ───────────────────────────────────

    def create_job(self, total: int = 0, kind: str = "scan") -> Job:
        """Create a new job with status='queued' and return it."""
        jid = self._next_job_id
        self._next_job_id += 1
        job = Job(
            id=jid,
            status="queued",
            kind=kind,
            total=total,
            done=0,
            failed=0,
            started_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        self._jobs[jid] = job
        self.create_job_calls.append(job)
        return job

    def update_job(self, job_id: int, **fields: Any) -> None:
        """Update arbitrary job fields (status/done/failed/...)."""
        job = self._jobs.get(job_id)
        if not job:
            return
        # Auto-set finished_at when moving to a terminal status.
        if fields.get("status") in ("done", "failed", "cancelled") and "finished_at" not in fields:
            fields["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self._jobs[job_id] = job.model_copy(update=fields)

    def get_job(self, job_id: int) -> Job | None:
        """Return the job with *job_id*, or ``None``."""
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int | None = None) -> list[Job]:
        """Return jobs newest-first (by id desc), optionally limited."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.id or 0, reverse=True)
        if limit is not None:
            jobs = jobs[:limit]
        return jobs

    def delete_job(self, job_id: int) -> None:
        """Delete a job and its recorded failed items."""
        self._jobs.pop(job_id, None)
        self._failed_items.pop(job_id, None)

    def record_failed_item(self, item: JobFailedItem) -> None:
        """Record one failed queue item for later retry."""
        self._failed_items.setdefault(item.job_id, []).append(item)

    def get_failed_items(self, job_id: int) -> list[JobFailedItem]:
        """Return all recorded failed items for a job."""
        return list(self._failed_items.get(job_id, []))

    def clear_failed_items(self, job_id: int) -> None:
        """Remove all recorded failed items for a job."""
        self._failed_items.pop(job_id, None)

    # ── LibraryWriter adapter (for copy_into tracking) ───────────────

    def record_copy(self, source_path: str, date_str: str, roll_type: str) -> None:
        """Record a copy operation (mirrors LibraryWriter.copy_into)."""
        self.copy_calls.append((source_path, date_str, roll_type))
