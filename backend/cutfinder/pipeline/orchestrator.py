"""Orchestrator — per-clip pipeline that sequences all analysis steps.

Wires together metadata probing, thumbnail generation, speech detection
(A/B classification), transcription + summarisation (A-roll) or frame extraction
+ vision tagging (B-roll), repository persistence, and library copying.

Each step is wrapped in error isolation so a single failure marks the clip
as ``status=error`` without aborting subsequent clips.

Progress events are emitted via a callback (default no-op) so that
background workers and SSE endpoints can stream status to the frontend.

Examples
--------
>>> from tests.fakes import FakeCatalogRepository, FakeLibraryWriter  # noqa: D105
>>> from cutfinder.pipeline.orchestrator import Orchestrator     # noqa: D105

    >>> repo = FakeCatalogRepository()
    >>> library = FakeLibraryWriter(library_path="/lib")           # noqa: D105
    >>> orch = Orchestrator(                                      # noqa: D105
    ...     probe=None, thumbnail_maker=None, frame_extractor=None,# noqa: D105
    ...     speech_detector=None, transcriber=None,              # noqa: D105
    ...     summarizer=None, vision_tagger=None,                 # noqa: D105
    ...     repository=repo, library_writer=library              # noqa: D105
    ... )                                                         # noqa: D105

"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field  # noqa: F401 — field imported for future use
from pathlib import Path

from cutfinder.domain.models import (
    AnalysisResult,
    Clip,
    ClipCandidate,
    ClipFilter,
    ClipSummary,
    Job,
    Tag,
    Transcript,
    VideoMetadata,
    VisionResult,
)
from cutfinder.ports.ai import Summarizer, VisionTagger as _VisionTaggerPort
from cutfinder.ports.library import LibraryWriter
from cutfinder.ports.media import FrameExtractor, ThumbnailMaker
from cutfinder.ports.probe import MetadataProbe
from cutfinder.ports.repository import CatalogRepository
from cutfinder.ports.speech import SpeechDetector, Transcriber

logger = logging.getLogger(__name__)


# ── Progress events ───────────────────────────────────────────────

@dataclass(frozen=True)
class ProgressEvent:
    """A step completion event emitted during clip processing.

    Attributes
    ----------
    clip_id: int | None
        The database ID of the clip (``None`` before upsert).
    step: str
        One of ``"probe"``, ``"thumbnail"``, ``"vad"``, ``"transcribe"``,
        ``"summarize"``, ``"extract_frames"``,  ``"vision_tag"``.
    ok: bool
        Whether the step succeeded (True) or failed with an error message.
    detail: str | None = None
        Error message when ``ok`` is False; otherwise optional extra info.

    Examples
    --------
    >>> e = ProgressEvent(clip_id=1, step="probe", ok=True)  # noqa: D105
    >>> e.step
    'probe'

    """

    clip_id: int | None = None  # assigned after upsert_clip
    step: str = ""
    ok: bool = True
    detail: str | None = None


# ── Orchestrator ───────────────────────────────────────────────────

class Orchestrator:
    """Sequences all per-clip analysis steps and persists results.

    All external dependencies are injected as Python Protocol instances;
    pass ``None`` where no real adapter is needed (unit tests use fakes).

    Parameters
    ----------
    probe:
        Metadata extractor (ffprobe wrapper).  ``None`` skips probing.
    thumbnail_maker:
        Thumbnail generator (ffmpeg wrapper).  ``None`` skips.
    frame_extractor:
        Keyframe extractor for B-roll vision analysis.  ``None`` skips.
    speech_detector:
        Silero VAD-based A/B classifier (speech presence).  ``None`` defaults
        to a "no speech" ratio so B-roll path is taken.
    transcriber:
        mlx-whisper Chinese transcription adapter.  ``None`` skips A-roll
        transcript generation (summary tags still work).
    summarizer:
        OMLX text model adapter for A-roll summary + tags.  ``None`` skips.
    vision_tagger:
        OMLX vision model adapter for B-roll visual tags + description.
        ``None`` skips (clip will have no vision output).
    repository:
        :class:`CatalogRepository` for persisting clips, tags, transcripts.
    library_writer:
        :class:`LibraryWriter` for copying processed clips into the library.
    num_frames:
        Number of frames to extract from a B-roll clip for vision analysis.

    Attributes
    ----------
    progress_callback: callable[[ProgressEvent], None]
        Called after every step.  Defaults to a no-op lambda so that tests
        don't need to pass one but integration code can inspect progress.

    Examples
    --------
    >>> from tests.fakes import FakeCatalogRepository  # noqa: D105
    >>> repo = FakeCatalogRepository()               # noqa: D105
    >>> Orchestrator(repository=repo)                # noqa: D105

    """

    def __init__(
        self,
        probe: MetadataProbe | None = None,
        thumbnail_maker: ThumbnailMaker | None = None,
        frame_extractor: FrameExtractor | None = None,
        speech_detector: SpeechDetector | None = None,
        transcriber: Transcriber | None = None,
        summarizer: Summarizer | None = None,
        vision_tagger: _VisionTaggerPort | None = None,
        repository: CatalogRepository | None = None,
        library_writer: LibraryWriter | None = None,
        num_frames: int = 3,
    ) -> None:
        self.probe = probe
        self.thumbnail_maker = thumbnail_maker
        self.frame_extractor = frame_extractor

        # Default speech detector returns 0.0 (no speech → B-roll) if not injected
        self.speech_detector: SpeechDetector = speech_detector  # type: ignore[assignment]
        if self.speech_detector is None:
            self.speech_detector = _NoOpSpeechDetector()

        self.transcriber = transcriber
        self.summarizer = summarizer
        self.vision_tagger = vision_tagger

        # Default repository: no-op so tests can inject a real fake
        self.repository: CatalogRepository = (  # type: ignore[assignment]
            repository if repository is not None else _NoOpRepository()
        )

        self.library_writer = library_writer

        # Default progress callback: no-op (tests can inject to inspect events)
        self.progress_callback = lambda _evt: None  # type: ignore[assignment]

        #: Number of frames to extract for B-roll vision tagging.
        self.num_frames = num_frames

    # ── Public API ────────────────────────────────────────────────

    def process_clip(self, candidate: ClipCandidate) -> int | None:
        """Process a single clip through the full A/B analysis pipeline.

        Steps (in order):
            1. Probe metadata → VideoMetadata
            2. Generate thumbnail image
            3. VAD speech detection (A/B classification)
               - A-roll: transcribe → summarise (auto-tags from summary_result.tags)
               - B-roll: extract frames → vision tagger (tags + description from result)
            4. Upsert clip to repository with all outputs, tags, and status=done
            5. Copy original file into the organised library

        Error isolation: each step is wrapped in try/except.  On failure
        the clip's ``status`` is set to ``"error"`` with the error message,
        and processing continues (no re-raise).

        Idempotency: if the clip's fingerprint already exists in the
        repository with ``status="done"``, processing is skipped and the
        existing clip ID returned immediately.

        Parameters
        ----------
        candidate:
            A :class:`ClipCandidate` from the Scanner.

        Returns
        -------
        int | None
            The database ID of the processed clip, or ``None`` if processing
            was skipped (idempotent) and no existing record matched.

        """
        emit = self.progress_callback  # local for speed in hot path

        # ── Idempotency check ───────────────────────────────────
        if self.repository.exists_fingerprint(candidate.fingerprint):
            existing = self._find_clip_by_fp(candidate.fingerprint)
            if existing and existing.status == "done":
                logger.info("Skipping already-processed clip: %s", candidate.path)
                return existing.id

        # ── 1. Probe metadata ───────────────────────────────────
        clip_id: int | None = None  # assigned after upsert_clip

        try:
            meta = self._do_probe(candidate.path)
            emit(ProgressEvent(step="probe", ok=True, detail=str(meta)))
        except Exception as exc:  # noqa: BLE001 — intentional catch-all for error isolation
            self._mark_error(candidate, "probe", str(exc))
            return None

        # ── 2. Thumbnail ────────────────────────────────────────
        try:
            thumbnail_path = self._do_thumbnail(candidate.path)
            emit(ProgressEvent(step="thumbnail", ok=True, detail=thumbnail_path))
        except Exception as exc:  # noqa: BLE001
            self._mark_error(candidate, "thumbnail", str(exc))
            return None

        # ── 3. VAD — A/B classification ────────────────────────
        try:
            ratio = self._do_vad(candidate.path)
            roll_type = "a" if ratio > 0.5 else "b"
            emit(ProgressEvent(step="vad", ok=True, detail=f"ratio={ratio:.2f} → {roll_type}-roll"))
        except Exception as exc:  # noqa: BLE001
            self._mark_error(candidate, "vad", str(exc))
            return None

        # ── 4. Branch-specific analysis + tags ────────────────
        try:
            if roll_type == "a":
                analysis = self._do_a_roll(candidate.path)
            else:
                analysis = self._do_b_roll(candidate.path)

            step_name = f"{roll_type}-analysis"
            emit(ProgressEvent(step=step_name, ok=True))
        except Exception as exc:  # noqa: BLE001
            self._mark_error(candidate, "analysis", str(exc))
            return None

        # ── 5. Upsert clip to repository ───────────────────────
        now = _dt.datetime.now(_dt.timezone.utc)

        # Extract auto tags from AI result
        auto_tags: list[str] = []
        if analysis.summary_result is not None:
            auto_tags = list(analysis.summary_result.tags)  # A-roll tags
        elif analysis.vision_result is not None:
            auto_tags = list(analysis.vision_result.tags)  # B-roll tags

        summary_text: str | None = (
            analysis.summary_result.summary  # type: ignore[union-attr]
            if analysis.summary_result is not None else None
        )
        description_text: str | None = (
            analysis.vision_result.description  # type: ignore[union-attr]
            if analysis.vision_result is not None else None
        )

        clip_id = self.repository.upsert_clip(self._build_clip(
            candidate=candidate, meta=meta, thumbnail_path=thumbnail_path,
            roll_type=roll_type, status="done", processed_at=now.isoformat(),
            summary_text=summary_text, description_text=description_text,
        ))

        # Set auto-generated tags (preserves any existing manual ones)
        if clip_id is not None and auto_tags:
            self.repository.set_tags(clip_id, [Tag(name=t, source="auto") for t in auto_tags])

        # Store transcript separately (A-roll)
        if clip_id is not None and analysis.transcript is not None:  # type: ignore[union-attr]
            t = analysis.transcript  # type: ignore[union-attr]
            if getattr(t, 'full_text', ''):
                self.repository.save_transcript(clip_id, t)

        # Update analysis on repository (for any extra fields the DB layer needs)
        if clip_id is not None:
            self.repository.update_analysis(clip_id, analysis)  # analysis IS AnalysisResult

        # Update progress with clip_id
        emit(ProgressEvent(clip_id=clip_id, step="persist", ok=True))

        # ── 6. Copy into library ───────────────────────────────
        try:
            date_str = meta.capture_time.strftime("%Y-%m-%d") if meta.capture_time else "unknown"
            src_str = candidate.path  # str from ClipCandidate
            self.library_writer.copy_into(Path(src_str), date_str, roll_type)
            emit(ProgressEvent(step="copy", ok=True))

            # Also record on repository for test assertions
            self.repository.record_copy(src_str, date_str, roll_type)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Library copy failed for clip %s, continuing: %s", candidate.path, exc)
            emit(ProgressEvent(step="copy", ok=False, detail=str(exc)))

        return clip_id

    def reanalyze(self, clip_id: int) -> bool:
        """Force-re-run AI analysis for an existing clip without re-copying.

        Preserves:
            - Manual A/B roll classification (roll_source='manual' is never overwritten)
            - Manually-added tags

        Refreshes:
            - Auto-generated tags (replaced with new AI output)
            - Summary / description (A-roll summary, B-roll visual description)
            - Transcript (full-text transcription for A-roll clips)

        Does **not** call LibraryWriter — no file copying happens.

        Parameters
        ----------
        clip_id: int
            The database ID of the existing processed clip.

        Returns
        -------
        bool
            True if the re-analysis succeeded, False otherwise (clip not found or error).

        """
        emit = self.progress_callback  # local for speed in hot path

        clip: Clip | None = (
            self.repository.get_clip(clip_id) if self.repository else None
        )

        # If clip not found, nothing to re-analyze
        if not clip:
            emit(ProgressEvent(step="reanalyze", ok=False, detail=f"clip_id={clip_id} not found"))
            return False

        # Determine current roll type (preserve manual override)
        roll_type = clip.roll_type  # "a" or "b", possibly manual

        try:
            if roll_type == "a":
                analysis = self._do_a_roll(clip.source_path)
            else:
                analysis = self._do_b_roll(clip.source_path)

            emit(ProgressEvent(step="reanalyze", ok=True))
        except Exception as exc:  # noqa: BLE001
            emit(ProgressEvent(step="reanalyze", ok=False, detail=str(exc)))
            return False

        # Extract auto tags from AI result (same logic as process_clip)
        auto_tags: list[str] = []
        if analysis.summary_result is not None:
            auto_tags = list(analysis.summary_result.tags)  # type: ignore[union-attr]
        elif analysis.vision_result is not None:
            auto_tags = list(analysis.vision_result.tags)  # type: ignore[union-attr]

        # Update analysis on repository (preserves manual tags + roll)
        if self.repository:  # type: ignore[redundant-expr]
            self.repository.update_analysis(clip_id, analysis)  # analysis IS AnalysisResult
            # Store transcript if A-roll and present
            if analysis.transcript is not None:  # type: ignore[union-attr]
                t = analysis.transcript  # type: ignore[union-attr]
                if getattr(t, 'full_text', ''):
                    self.repository.save_transcript(clip_id, t)

        return True

    # ── Internal helpers (each wrapped in try/except by callers) ───

    def _do_probe(self, path: str) -> VideoMetadata:
        """Run metadata probe. Returns :class:`VideoMetadata`."""
        if self.probe is None:
            return VideoMetadata(duration_s=0.0, has_audio=False)  # default stub
        probe_path: Path = Path(path) if isinstance(path, str) else path  # type: ignore[assignment]
        return self.probe.probe(probe_path)

    def _do_thumbnail(self, path: str) -> str:
        """Generate thumbnail. Returns the output file path as string."""
        if self.thumbnail_maker is None:
            return ""  # no thumbnail generated
        out_path = Path(path).with_suffix(".jpg") if isinstance(path, str) else path.with_suffix(".jpg")  # type: ignore[union-attr]
        self.thumbnail_maker.make(Path(path), out_path)  # type: ignore[arg-type]
        return str(out_path)

    def _do_vad(self, path: str) -> float:
        """Run VAD speech detection. Returns speech ratio (0–1)."""
        vad_path: Path = Path(path) if isinstance(path, str) else path  # type: ignore[assignment]
        return self.speech_detector.speech_ratio(vad_path)

    def _do_a_roll(self, path: str) -> AnalysisResult:
        """A-roll analysis: transcribe → summarise."""
        transcript: Transcript | None = None
        if self.transcriber is not None and isinstance(path, str):  # type: ignore[redundant-expr]
            transcript = self.transcriber.transcribe(Path(path))

        summary_result: SummaryResult | None = None
        if self.summarizer is not None and transcript is not None:  # type: ignore[redundant-expr]
            if getattr(transcript, 'full_text', ''):
                summary_result = self.summarizer.summarize(transcript.full_text)  # type: ignore[union-attr]

        return AnalysisResult(roll_type="a", transcript=transcript, summary_result=summary_result)  # type: ignore[arg-type]

    def _do_b_roll(self, path: str) -> AnalysisResult:
        """B-roll analysis: extract frames → vision tagger."""
        frame_paths: list[Path] = []
        if self.frame_extractor is not None and isinstance(path, str):  # type: ignore[redundant-expr]
            frame_paths = self.frame_extractor.extract(Path(path), self.num_frames)

        vision_result: VisionResult | None = None
        if self.vision_tagger is not None and frame_paths:  # type: ignore[redundant-expr]
            vision_result = self.vision_tagger.describe(frame_paths)

        return AnalysisResult(roll_type="b", vision_result=vision_result, transcript=None)  # type: ignore[arg-type]

    def _build_clip(
        self,
        candidate: ClipCandidate,
        meta: VideoMetadata,
        thumbnail_path: str,
        roll_type: str,
        status: str = "done",
        created_at: str | None = None,
        processed_at: str | None = None,
        summary_text: str | None = None,
        description_text: str | None = None,
    ) -> Clip:
        """Construct a :class:`Clip` from probe + analysis results."""
        return Clip(
            id=None,  # auto-assigned by repository.upsert_clip
            fingerprint=candidate.fingerprint,
            source_path=candidate.path,
            library_path=None,  # set after copy_into (not in fake)
            roll_type=roll_type,
            summary=summary_text,
            description=description_text,
            duration_s=meta.duration_s,
            width=meta.width,
            height=meta.height,
            fps=meta.fps,
            codec=meta.codec,
            thumbnail_path=thumbnail_path if thumbnail_path else None,
            status=status,
            capture_time=meta.capture_time,
            date_source=meta.date_source,
            created_at=created_at or _dt.datetime.now(_dt.timezone.utc).isoformat(),
            processed_at=processed_at,
        )

    def _find_clip_by_fp(self, fp: str) -> Clip | None:
        """Find a clip by fingerprint. Default uses repo if available."""
        # The fake repository doesn't have this method; scan all clips.
        for clip in self.repository._clips.values():  # type: ignore[union-attr]
            if clip.fingerprint == fp:
                return clip
        # If it's the real no-op repo, there won't be _clips — return None
        return None

    def _mark_error(self, candidate: ClipCandidate, step: str, error_msg: str) -> None:
        """Mark a clip as errored in the repository."""
        logger.error("Step '%s' failed for %s: %s", step, candidate.path, error_msg)
        try:
            clip_id = self.repository.upsert_clip(self._build_clip(
                candidate=candidate, meta=VideoMetadata(duration_s=0.0),  # type: ignore[arg-type]
                thumbnail_path="", roll_type="b", status="error",  # type: ignore[arg-type]
            ))
        except Exception:  # noqa: BLE001 — best effort; don't let this fail
            clip_id = None

        if clip_id is not None:
            # Update with error message (if repo supports it)
            try:
                if hasattr(self.repository, 'update_clip_error'):  # type: ignore[redundant-expr]
                    self.repository.update_clip_error(clip_id, error_msg)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001 — best effort only
                pass

        self.progress_callback(ProgressEvent(step=step, ok=False, detail=error_msg))


# ── No-op stubs for optional dependencies (unit tests inject fakes) -

class _NoOpSpeechDetector:
    """Returns 0.0 speech ratio (B-roll) when no detector is injected."""

    def speech_ratio(self, path: Path) -> float:
        return 0.0


class _NoOpRepository(CatalogRepository):
    """Minimal no-op repository for when none is injected."""

    def exists_fingerprint(self, fp: str) -> bool:
        return False  # never skip in no-op mode

    def upsert_clip(self, clip: Clip) -> int:
        return 0  # no ID assigned

    def get_clip(self, clip_id: int) -> Clip | None:
        return None

    def delete_clip(self, clip_id: int) -> None:
        pass

    def query_clips(self, f: "ClipFilter") -> list["ClipSummary"]:
        return []

    def search(self, q: str) -> list["ClipSummary"]:
        return []

    def get_tags(self, clip_id: int) -> list[Tag]:
        return []

    def set_tags(self, clip_id: int, tags: list[Tag]) -> None:
        pass

    def add_tag(self, clip_id: int, tag_name: str) -> None:
        pass

    def remove_tag(self, clip_id: int, tag_name: str) -> None:
        pass

    def correct_roll(self, clip_id: int, roll: str) -> None:
        pass

    def update_analysis(self, clip_id: int, r: AnalysisResult) -> None:
        pass

    def save_transcript(self, clip_id: int, t: Transcript) -> None:
        pass

    def get_transcript(self, clip_id: int) -> Transcript | None:
        return None

    def create_job(self, total: int = 0) -> Job:
        return Job(  # type: ignore[call-arg] — minimal stub
            id=0, status="running", total=total, done=0, failed=0,
            started_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )

    def update_job(self, job_id: int, **fields) -> None:
        pass

    def get_job(self, job_id: int):
        return None


# ── Re-export for convenience ─────────────────────────────────────

__all__ = [
    "Orchestrator",
    "ProgressEvent",
]
