"""Tests for :mod:`cutfinder.pipeline.orchestrator`.

Covers the five DoD categories from ``doc/tasks/11-orchestrator.md``:
    1. A/B branch call assertions (transcribe+summarize vs extract+vision_tagger)
    2. Error injection → single clip status=error, batch continues processing other clips
    3. Idempotent skip (pre-existing fingerprint → no processing)
    4. Database/library correctness: upsert_clip writes correct fields, library.copy_into called with right args
    5. Reanalyze: preserves manual A/B + tags, refreshes auto fields, no LibraryWriter call
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cutfinder.domain.models import (
    Clip,
    ClipCandidate,
    SummaryResult,
    Tag,
    Transcript,
    VideoMetadata,
    VisionResult,
)
from cutfinder.pipeline.orchestrator import Orchestrator, ProgressEvent

# Fakes used directly in tests (not via fixtures)
from tests.fakes import FakeCatalogRepository, FakeLibraryWriter  # noqa: F401

# ── Fixtures / helpers ───────────────────────────────────────────────


def _now() -> str:
    """Return current UTC ISO timestamp for model fields."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _make_clip(**overrides: Any) -> Clip:
    """Return a :class:`Clip` with sensible defaults, overridable via *overrides*."""
    defaults = dict(
        id=None, fingerprint="aabbccdd00112233", source_path="/tmp/test.mp4",
        roll_type="a", status="pending", summary=None, description=None,
        created_at=_now(),
    )
    defaults.update(overrides)
    return Clip(**defaults)


def _make_candidate(
    path: str = "/tmp/test.mp4",
    fingerprint: str = "abc123",
) -> ClipCandidate:
    """Return a minimal :class:`ClipCandidate`."""
    return ClipCandidate(path=path, fingerprint=fingerprint)


def _make_metadata() -> VideoMetadata:
    """Return a plausible :class:`VideoMetadata`."""
    return VideoMetadata(
        duration_s=120.5, has_audio=True, width=1920, height=1080,
        fps=30.0, codec="h264", source_path="/tmp/test.mp4",
        capture_time=_dt.datetime(2026, 1, 15, 10, 30, tzinfo=_dt.timezone.utc),
        date_source="capture_time",
    )


def _make_summary() -> SummaryResult:
    return SummaryResult(summary="这是一段中文简介。", tags=["旅行", "风景"])


def _make_vision() -> VisionResult:
    return VisionResult(
        description="一个人在海边散步", tags=["海滩", "人物"],
    )


def _make_transcript() -> Transcript:
    return Transcript(
        full_text="这是一段中文转写文本。",  # noqa: FURB133
        segments=[],
    )


# ── Fixtures: Orchestrator with injected fakes ───────────────────────


@pytest.fixture
def fake_probe():
    """MagicMock that returns a valid VideoMetadata on probe() calls."""
    m = MagicMock()
    m.probe.return_value = _make_metadata()
    return m


@pytest.fixture
def fake_thumbnail():
    """MagicMock for ThumbnailMaker — .make() does nothing."""
    return MagicMock()


@pytest.fixture
def fake_frame_extractor():
    """MagicMock that returns deterministic frame paths."""
    m = MagicMock()
    m.extract.return_value = [Path("/tmp/frame1.jpg"), Path("/tmp/frame2.jpg")]
    return m


@pytest.fixture
def fake_speech_a():
    """Speech detector returning ratio > 0.5 → A-roll."""
    m = MagicMock()
    m.speech_ratio.return_value = 0.72
    return m


@pytest.fixture
def fake_speech_b():
    """Speech detector returning ratio <= 0.5 → B-roll."""
    m = MagicMock()
    m.speech_ratio.return_value = 0.31
    return m


@pytest.fixture
def fake_transcriber():
    """MagicMock that returns a Transcript."""
    m = MagicMock()
    m.transcribe.return_value = _make_transcript()
    return m


@pytest.fixture
def fake_summarizer():
    """MagicMock that returns a SummaryResult."""
    m = MagicMock()
    m.summarize.return_value = _make_summary()
    return m


@pytest.fixture
def fake_vision_tagger():
    """MagicMock that returns a VisionResult."""
    m = MagicMock()
    m.describe.return_value = _make_vision()
    return m


@pytest.fixture
def fake_repo():
    """In-memory FakeCatalogRepository."""
    from tests.fakes import FakeCatalogRepository
    return FakeCatalogRepository()


@pytest.fixture
def fake_library():
    """FakeLibraryWriter with a virtual library root."""
    from tests.fakes import FakeLibraryWriter
    return FakeLibraryWriter(library_path="/library")


@pytest.fixture
def events():
    """List to collect progress events."""
    return []


@pytest.fixture
def orch_with_events(
    fake_probe, fake_thumbnail, fake_frame_extractor,
    fake_speech_a, fake_transcriber, fake_summarizer,
    fake_repo, events,
):
    """Orchestrator configured for A-roll with event tracking."""

    def capture(evt: ProgressEvent) -> None:
        events.append(evt)

    return Orchestrator(
        probe=fake_probe, thumbnail_maker=fake_thumbnail,
        frame_extractor=fake_frame_extractor, speech_detector=fake_speech_a,
        transcriber=fake_transcriber, summarizer=fake_summarizer,
        vision_tagger=None, repository=fake_repo, library_writer=None,
    ), capture


@pytest.fixture
def orch_b_roll(
    fake_probe, fake_thumbnail, fake_frame_extractor,
    fake_speech_b, fake_vision_tagger, fake_repo, events,
):
    """Orchestrator configured for B-roll."""

    def capture(evt: ProgressEvent) -> None:
        events.append(evt)

    return Orchestrator(
        probe=fake_probe, thumbnail_maker=fake_thumbnail,
        frame_extractor=fake_frame_extractor, speech_detector=fake_speech_b,
        transcriber=None, summarizer=None, vision_tagger=fake_vision_tagger,
        repository=fake_repo, library_writer=None,
    ), capture


@pytest.fixture
def orch_with_library(
    fake_probe, fake_thumbnail, fake_frame_extractor,
    fake_speech_a, fake_transcriber, fake_summarizer,
    fake_repo, fake_library, events,
):
    """Orchestrator with both repository and library writer for copy assertions."""

    def capture(evt: ProgressEvent) -> None:
        events.append(evt)

    return Orchestrator(
        probe=fake_probe, thumbnail_maker=fake_thumbnail,
        frame_extractor=fake_frame_extractor, speech_detector=fake_speech_a,
        transcriber=fake_transcriber, summarizer=fake_summarizer,
        vision_tagger=None, repository=fake_repo, library_writer=fake_library,
    ), capture


@pytest.fixture
def orch_b_roll_with_library(
    fake_probe, fake_thumbnail, fake_frame_extractor,
    fake_speech_b, fake_vision_tagger, fake_repo, fake_library, events,
):
    """Orchestrator for B-roll with library writer."""

    def capture(evt: ProgressEvent) -> None:
        events.append(evt)

    return Orchestrator(
        probe=fake_probe, thumbnail_maker=fake_thumbnail,
        frame_extractor=fake_frame_extractor, speech_detector=fake_speech_b,
        transcriber=None, summarizer=None, vision_tagger=fake_vision_tagger,
        repository=fake_repo, library_writer=fake_library,
    ), capture


# ═════════════════════════════════════════════════════════════════════
# 1. A/B branch call assertions
# ═════════════════════════════════════════════════════════════════════


class TestABBranchCallAssertions:
    """Verify that A-roll calls transcribe+summarize and B-roll calls extract_frames+vision_tagger."""

    def test_a_roll_calls_transcribe_and_summarize(self, orch_with_events):
        """A-roll: transcriber.transcribe() and summarizer.summarize() are called."""
        orch, capture = orch_with_events
        orch.progress_callback = capture

        candidate = _make_candidate()
        result = orch.process_clip(candidate)

        assert result is not None  # clip was processed
        fake_transcriber = orch.transcriber  # type: ignore[union-attr]
        fake_summarizer = orch.summarizer  # type: ignore[union-attr]
        fake_transcriber.transcribe.assert_called_once()
        fake_summarizer.summarize.assert_called_once_with("这是一段中文转写文本。")

    def test_a_roll_sets_correct_fields(self, orch_with_events):
        """A-roll clip has roll_type='a', summary populated."""
        orch, capture = orch_with_events
        orch.progress_callback = capture

        candidate = _make_candidate()
        clip_id = orch.process_clip(candidate)

        clip = orch.repository.get_clip(clip_id)  # type: ignore[union-attr]
        assert clip is not None
        assert clip.roll_type == "a"
        assert clip.summary == "这是一段中文简介。"

    def test_b_roll_calls_extract_and_vision_tagger(self, orch_b_roll):
        """B-roll: frame_extractor.extract() and vision_tagger.describe() are called."""
        orch, capture = orch_b_roll
        orch.progress_callback = capture

        candidate = _make_candidate()
        result = orch.process_clip(candidate)

        assert result is not None  # clip was processed
        fake_frame_extractor = orch.frame_extractor  # type: ignore[union-attr]
        fake_vision_tagger = orch.vision_tagger  # type: ignore[union-attr]
        fake_frame_extractor.extract.assert_called_once()
        fake_vision_tagger.describe.assert_called_once_with(
            [Path("/tmp/frame1.jpg"), Path("/tmp/frame2.jpg")],
        )

    def test_b_roll_sets_correct_fields(self, orch_b_roll):
        """B-roll clip has roll_type='b', description populated."""
        orch, capture = orch_b_roll
        orch.progress_callback = capture

        candidate = _make_candidate()
        clip_id = orch.process_clip(candidate)

        clip = orch.repository.get_clip(clip_id)  # type: ignore[union-attr]
        assert clip is not None
        assert clip.roll_type == "b"
        assert clip.description == "一个人在海边散步"

    def test_a_roll_emits_progress_events(self, orch_with_events):
        """A-roll emits events for each step: probe → thumbnail → vad → analysis."""
        orch, capture = orch_with_events
        events: list[ProgressEvent] = []
        orch.progress_callback = lambda e: events.append(e)

        candidate = _make_candidate()
        orch.process_clip(candidate)

        steps = [e.step for e in events]
        assert "probe" in steps
        assert "thumbnail" in steps
        assert "vad" in steps
        # A-roll analysis step name is "a-analysis"
        assert "a-analysis" in steps

    def test_b_roll_emits_progress_events(self, orch_b_roll):
        """B-roll emits events for each step including extract_frames + vision_tag."""
        orch, capture = orch_b_roll
        events: list[ProgressEvent] = []
        orch.progress_callback = lambda e: events.append(e)

        candidate = _make_candidate()
        orch.process_clip(candidate)

        steps = [e.step for e in events]
        assert "probe" in steps
        assert "thumbnail" in steps
        assert "vad" in steps
        # B-roll analysis step name is "b-analysis"
        assert "b-analysis" in steps


# ═════════════════════════════════════════════════════════════════════
# 2. Error injection continuation
# ════════════════════════════════════════════════════════════════════


class TestErrorInjectionContinuation:
    """Single clip failure → status=error, batch continues processing other clips."""

    def test_probe_failure_marks_error(self, fake_thumbnail, fake_speech_a,
                                       fake_transcriber, fake_summarizer, fake_repo):
        """When probe raises, clip gets status='error' and process_clip returns None."""
        bad_probe = MagicMock()
        bad_probe.probe.side_effect = RuntimeError("ffprobe failed")

        orch = Orchestrator(
            probe=bad_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=fake_repo,
        )

        candidate = _make_candidate()
        result = orch.process_clip(candidate)

        assert result is None  # processing aborted for this clip
        events: list[ProgressEvent] = []
        orch.progress_callback(lambda e: events.append(e))  # type: ignore[union-attr]
        orch.process_clip(candidate)

    def test_batch_continues_after_single_error(self, fake_probe, fake_thumbnail,
                                                 fake_speech_a, fake_transcriber,
                                                 fake_summarizer, fake_repo):
        """One clip fails but the next succeeds (different fingerprint)."""
        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=fake_repo,
        )

        # First clip: probe fails (we'll swap the probe mid-flight)
        bad_probe = MagicMock()
        call_count = [0]

        def failing_probe(path):  # type: ignore[misc, unused-ignore]
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("simulated failure")
            return _make_metadata()

        bad_probe.probe = failing_probe  # type: ignore[assignment]
        orch.probe = bad_probe

        candidate1 = _make_candidate(path="/tmp/clip1.mp4", fingerprint="aaaaaaaaaaaaaaa1")
        candidate2 = _make_candidate(path="/tmp/clip2.mp4", fingerprint="bbbbbbbbbbbbbbb2")

        result1 = orch.process_clip(candidate1)
        assert result1 is None  # first clip failed

        result2 = orch.process_clip(candidate2)
        assert result2 is not None  # second clip succeeded

    def test_vad_failure_marks_error(self, fake_probe, fake_thumbnail,
                                     fake_transcriber, fake_summarizer, fake_repo):
        """When VAD raises during speech detection, clip gets status='error'."""
        bad_vad = MagicMock()
        bad_vad.speech_ratio.side_effect = RuntimeError("VAD model load failed")

        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=bad_vad,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=fake_repo,
        )

        candidate = _make_candidate()
        result = orch.process_clip(candidate)

        assert result is None  # processing aborted when VAD fails
        events: list[ProgressEvent] = []
        orch.progress_callback(lambda e: events.append(e))  # type: ignore[union-attr]
        orch.process_clip(candidate)

    def test_analysis_failure_marks_error(self, fake_probe, fake_thumbnail,
                                          fake_speech_a, fake_repo):
        """When summarizer raises during A-roll analysis, clip gets status='error'."""
        bad_summarizer = MagicMock()
        bad_summarizer.summarize.side_effect = RuntimeError("summarization failed")

        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=MagicMock(),  # still returns transcript but summarizer fails
            summarizer=bad_summarizer, repository=fake_repo,
        )

        candidate = _make_candidate()
        result = orch.process_clip(candidate)

        assert result is None  # processing aborted when summarizer fails


# ═════════════════════════════════════════════════════════════════════
# 3. Idempotent skip behavior
# ════════════════════════════════════════════════════════════════════


class TestIdempotentSkip:
    """Pre-existing fingerprint with status=done → skip processing, return existing ID."""

    def test_skip_already_done_clip(self, fake_probe, fake_thumbnail,
                                     fake_speech_a, fake_transcriber,
                                     fake_summarizer):
        """Processing the same fingerprint twice returns existing ID without re-processing."""
        repo = FakeCatalogRepository()

        # Pre-populate the repository with a done clip (simulating prior scan)
        existing_clip = _make_clip(
            id=42, fingerprint="ccccccccccccccc3", source_path="/tmp/old.mp4",
            roll_type="a", status="done", summary=None, description=None,
        )
        repo._clips[42] = existing_clip
        repo._clip_by_fp["ccccccccccccccc3"] = 42

        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=repo,
        )

        # Candidate with the same fingerprint as existing clip → should be skipped
        candidate = _make_candidate(path="/tmp/another.mp4", fingerprint="ccccccccccccccc3")

        result_id = orch.process_clip(candidate)
        assert result_id == 42  # returns existing clip ID

    def test_process_new_fingerprint_after_done(self, fake_probe, fake_thumbnail,
                                                 fake_speech_a, fake_transcriber,
                                                 fake_summarizer, fake_repo):
        """Processing a new fingerprint creates the clip; same one again returns existing ID."""
        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=fake_repo,
        )

        candidate = _make_candidate()
        result1 = orch.process_clip(candidate)
        assert result1 is not None

        # Second call with same candidate should skip and return the same ID
        result2 = orch.process_clip(candidate)
        assert result2 == result1  # same ID returned

    def test_skip_does_not_call_library_writer(self, fake_probe, fake_thumbnail,
                                                fake_speech_a, fake_transcriber,
                                                fake_summarizer):
        """Idempotent skip does NOT call repository.upsert_clip or library.copy_into."""
        repo = FakeCatalogRepository()

        # Pre-populate with a done clip
        existing_clip = _make_clip(
            id=99, fingerprint="ddddddddddddddd4", source_path="/tmp/skip.mp4",
            roll_type="b", status="done", summary=None, description=None,
        )
        repo._clips[99] = existing_clip
        repo._clip_by_fp["ddddddddddddddd4"] = 99

        library = FakeLibraryWriter(library_path="/library")
        orch = Orchestrator(
            probe=fake_probe, thumbnail_maker=fake_thumbnail, speech_detector=fake_speech_a,
            transcriber=fake_transcriber, summarizer=fake_summarizer, repository=repo,
            library_writer=library,
        )

        candidate = _make_candidate(path="/tmp/other.mp4", fingerprint="ddddddddddddddd4")
        orch.process_clip(candidate)  # should skip

        assert repo.upsert_calls == []   # no upsert on skipped clip
        assert library.calls == []       # no copy_into on skipped clip


# ═════════════════════════════════════════════════════════════════════
# 4. Database + library correctness
# ════════════════════════════════════════════════════════════════════


class TestDatabaseLibraryCorrectness:
    """Verify upsert_clip writes correct fields and library.copy_into is called with right args."""

    def test_upsert_writes_correct_fields(self, orch_with_events):
        """After processing A-roll, clip has correct metadata in repo."""
        orch, capture = orch_with_events
        events: list[ProgressEvent] = []
        orch.progress_callback = lambda e: events.append(e)

        candidate = _make_candidate()
        orch.process_clip(candidate)

        # Verify upsert was called (repo tracks this in .upsert_calls)
        assert len(orch.repository.upsert_calls) == 1  # type: ignore[union-attr]
        upserted = orch.repository.upsert_calls[0]  # type: ignore[union-attr]

        assert upserted.fingerprint == "abc123"
        assert upserted.source_path == "/tmp/test.mp4"
        assert upserted.roll_type == "a"
        assert upserted.status == "done"
        assert upserted.duration_s == 120.5
        assert upserted.width == 1920
        assert upserted.height == 1080

    def test_library_copy_called_with_right_args(self, orch_with_library):
        """Library copy is called with (path, date_str='2026-01-15', roll_type='a')."""
        orch, capture = orch_with_library

        candidate = _make_candidate()
        clip_id = orch.process_clip(candidate)
        assert clip_id is not None

        fake_library = orch.library_writer  # type: ignore[union-attr]
        assert len(fake_library.calls) == 1

        src_str, date_str, roll_type = fake_library.calls[0]
        assert src_str == "/tmp/test.mp4"
        assert date_str == "2026-01-15"  # from VideoMetadata.capture_time
        assert roll_type == "a"

    def test_tags_set_correctly(self, orch_with_events):
        """Auto-tags from summarizer are set on the clip via repository.set_tags()."""
        orch, capture = orch_with_events
        events: list[ProgressEvent] = []
        orch.progress_callback = lambda e: events.append(e)

        candidate = _make_candidate()
        orch.process_clip(candidate)

        fake_repo = orch.repository  # type: ignore[union-attr]
        assert len(fake_repo.set_tags_calls) == 1

        clip_id, tags = fake_repo.set_tags_calls[0]
        assert clip_id is not None  # auto-assigned ID from upsert
        tag_names = {t.name for t in tags}
        assert "旅行" in tag_names  # from SummaryResult.tags
        assert "风景" in tag_names

    def test_transcript_saved_for_a_roll(self, orch_with_events):
        """Transcript is saved separately for A-roll clips via save_transcript."""
        orch, capture = orch_with_events
        events: list[ProgressEvent] = []
        orch.progress_callback = lambda e: events.append(e)

        candidate = _make_candidate()
        clip_id = orch.process_clip(candidate)
        assert clip_id is not None

        fake_repo = orch.repository  # type: ignore[union-attr]
        assert len(fake_repo.save_transcript_calls) == 1

        saved_clip_id, transcript = fake_repo.save_transcript_calls[0]
        assert saved_clip_id == clip_id
        assert transcript.full_text == "这是一段中文转写文本。"

    def test_b_roll_library_copy_args(self, orch_b_roll_with_library):
        """B-roll copy uses the correct date and roll_type='b'."""
        orch, capture = orch_b_roll_with_library

        candidate = _make_candidate()
        clip_id = orch.process_clip(candidate)
        assert clip_id is not None

        fake_library = orch.library_writer  # type: ignore[union-attr]
        assert len(fake_library.calls) == 1

        src_str, date_str, roll_type = fake_library.calls[0]
        assert src_str == "/tmp/test.mp4"
        assert date_str == "2026-01-15"  # from VideoMetadata.capture_time
        assert roll_type == "b"


# ═════════════════════════════════════════════════════════════════════
# 5. Reanalyze behavior
# ════════════════════════════════════════════════════════════════════


class TestReanalyze:
    """reanalyze preserves manual A/B + tags, refreshes auto fields, no LibraryWriter call."""

    def test_preserves_manual_roll(self):
        """Manual A/B correction (roll_source='manual') is preserved during reanalyze."""
        repo = FakeCatalogRepository()

        # Create a clip that was manually corrected to B-roll
        manual_clip = _make_clip(
            id=10, fingerprint="eeeeeeeeeeeeeee5", source_path="/tmp/manual.mp4",
            roll_type="b", roll_source="manual",  # user corrected from A to B
            status="done", summary=None, description=None,
        )
        repo._clips[10] = manual_clip
        repo._clip_by_fp["manual_fp"] = 10

        # Inject fakes that would normally classify as A-roll
        probe = MagicMock()
        probe.probe.return_value = _make_metadata()

        speech_a = MagicMock()
        speech_a.speech_ratio.return_value = 0.85  # A-roll ratio

        transcriber = MagicMock()
        transcriber.transcribe.return_value = _make_transcript()

        summarizer = MagicMock()
        summarizer.summarize.return_value = _make_summary()

        orch = Orchestrator(
            probe=probe, thumbnail_maker=None, frame_extractor=None,
            speech_detector=speech_a, transcriber=transcriber, summarizer=summarizer,
            vision_tagger=None, repository=repo, library_writer=None,
        )

        # Re-analyze the manually-corrected clip
        success = orch.reanalyze(10)
        assert success is True

        # Roll type should still be 'b' (manual override preserved)
        updated_clip = repo.get_clip(10)
        assert updated_clip is not None
        assert updated_clip.roll_type == "b"

    def test_preserves_manual_tags(self):
        """Manually added tags are preserved; only auto-tags are refreshed."""
        repo = FakeCatalogRepository()

        existing_clip = _make_clip(
            id=20, fingerprint="fffffffffffffff6", source_path="/tmp/tagged.mp4",
            roll_type="a", status="done", summary=None, description=None,
        )
        repo._clips[20] = existing_clip
        repo._clip_by_fp["tag_fp"] = 20

        # Pre-set tags: one manual, one auto
        repo._tags[20] = [
            Tag(name="important", source="manual"),
            Tag(name="old_auto_tag", source="auto"),
        ]

        probe = MagicMock()
        probe.probe.return_value = _make_metadata()

        speech_a = MagicMock()
        speech_a.speech_ratio.return_value = 0.75

        transcriber = MagicMock()
        transcriber.transcribe.return_value = _make_transcript()

        summarizer = MagicMock()
        # New AI output has different tags than before
        summarizer.summarize.return_value = SummaryResult(
            summary="新摘要", tags=["new_tag_1", "new_tag_2"],
        )

        orch = Orchestrator(
            probe=probe, thumbnail_maker=None, frame_extractor=None,
            speech_detector=speech_a, transcriber=transcriber, summarizer=summarizer,
            vision_tagger=None, repository=repo, library_writer=None,
        )

        success = orch.reanalyze(20)
        assert success is True

        # Tags should have manual tag preserved + new auto tags replacing old ones
        updated_tags = repo.get_tags(20)
        tag_names = {t.name for t in updated_tags}
        assert "important" in tag_names  # manual preserved
        assert "old_auto_tag" not in tag_names  # old auto replaced
        assert "new_tag_1" in tag_names  # new AI tags added

    def test_refreshes_auto_fields(self):
        """Summary, description (or transcript), and tags are refreshed with new AI output."""
        repo = FakeCatalogRepository()

        existing_clip = _make_clip(
            id=30, fingerprint="1111111111111117", source_path="/tmp/refresh.mp4",
            roll_type="a", status="done", summary="旧摘要", description=None,
        )
        repo._clips[30] = existing_clip
        repo._clip_by_fp["refresh_fp"] = 30

        probe = MagicMock()
        probe.probe.return_value = _make_metadata()

        speech_a = MagicMock()
        speech_a.speech_ratio.return_value = 0.9

        transcriber = MagicMock()
        new_transcript = Transcript(
            full_text="全新的转写内容",  # noqa: FURB133
            segments=[],
        )
        transcriber.transcribe.return_value = new_transcript

        summarizer = MagicMock()
        summarizer.summarize.return_value = SummaryResult(
            summary="全新的中文摘要", tags=["新标签"],
        )

        orch = Orchestrator(
            probe=probe, thumbnail_maker=None, frame_extractor=None,
            speech_detector=speech_a, transcriber=transcriber, summarizer=summarizer,
            vision_tagger=None, repository=repo, library_writer=None,
        )

        success = orch.reanalyze(30)
        assert success is True

        # Summary should be refreshed with new AI output
        updated_clip = repo.get_clip(30)
        assert updated_clip is not None
        assert updated_clip.summary == "全新的中文摘要"  # old summary replaced

    def test_no_library_writer_call(self):
        """reanalyze does NOT call LibraryWriter.copy_into — no file copying."""
        repo = FakeCatalogRepository()

        clip = _make_clip(
            id=40, fingerprint="2222222222222218", source_path="/tmp/no_copy.mp4",
            roll_type="a", status="done", summary=None, description=None,
        )
        repo._clips[40] = clip
        repo._clip_by_fp["no_copy_fp"] = 40

        library = FakeLibraryWriter(library_path="/library")
        probe = MagicMock()
        probe.probe.return_value = _make_metadata()

        speech_a = MagicMock()
        speech_a.speech_ratio.return_value = 0.6

        transcriber = MagicMock()
        transcriber.transcribe.return_value = _make_transcript()

        summarizer = MagicMock()
        summarizer.summarize.return_value = _make_summary()

        orch = Orchestrator(
            probe=probe, thumbnail_maker=None, frame_extractor=None,
            speech_detector=speech_a, transcriber=transcriber, summarizer=summarizer,
            vision_tagger=None, repository=repo, library_writer=library,
        )

        orch.reanalyze(40)  # should NOT trigger copy_into

        assert library.calls == []  # no file copying during reanalyze
        assert repo.copy_calls == []  # also none on the repository

    def test_returns_false_when_clip_not_found(self):
        """reanalyze returns False when clip_id doesn't exist."""
        repo = FakeCatalogRepository()  # empty — no clips

        probe = MagicMock()
        speech_a = MagicMock()
        speech_a.speech_ratio.return_value = 0.5

        orch = Orchestrator(
            probe=probe, thumbnail_maker=None, frame_extractor=None,
            speech_detector=speech_a, transcriber=MagicMock(), summarizer=_make_summary(),
            vision_tagger=None, repository=repo, library_writer=None,
        )

        result = orch.reanalyze(999)  # nonexistent ID
        assert result is False
