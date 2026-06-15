"""Integration tests for MlxWhisperTranscriber using real video files.

Exercises the actual ffmpeg audio extraction + mlx-whisper pipeline
(no mocking) and validates that A-roll footage produces non-empty Chinese text.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration``.

Requires: ffmpeg, mlx-whisper (auto-downloads model on first run).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# ── fixtures ───────────────────────────────────────────────────────
def _test_video_dir() -> Path:
    root = Path(__file__).resolve().parents[3]  # repo root (integration → tests → backend)
    return root / "testVideo"


# Skip entire module if mlx-whisper is not installed
mlx_whisper = pytest.importorskip("mlx_whisper")


def _skip_if_missing(name: str) -> Path:
    """Return the path if it exists, otherwise skip."""
    name_map: dict[str, str] = {
        "a_roll_canon": "MVI_5298.MP4",
    }
    filename = name_map.get(name)
    if not filename:
        pytest.skip(f"Unknown sample: {name}")
    path = _test_video_dir() / filename
    if not path.exists():
        pytest.skip(f"Sample file missing: {path}")
    return path


# ── integration tests (real ffmpeg + real mlx-whisper) ────────────

@pytest.mark.integration
class TestMlxWhisterRealVideo:
    """Validate MlxWhisperTranscriber against real footage."""

    def test_a_roll_canon_non_empty_chinese(self, tmp_path: Path) -> None:
        """Canon A-roll (MVI_5298.MP4) → full_text non-empty and contains Chinese."""
        video_path = _skip_if_missing("a_roll_canon")

        from cutfinder.adapters.mlx_whisper import MlxWhisperTranscriber
        transcriber = MlxWhisperTranscriber(model="mlx-community/whisper-large-v3-mlx", language="zh")
        transcript = transcriber.transcribe(video_path)

        assert len(transcript.full_text.strip()) > 0, (
            f"A-roll video should produce non-empty transcription, "
            f"got empty text (segments: {len(transcript.segments)})"
        )

        # Check for at least one CJK character (U+4E00–U+9FFF)
        assert re.search(r"[一-鿿]", transcript.full_text), (
            f"A-roll transcription should contain Chinese characters, "
            f"got: {transcript.full_text!r}"
        )

    def test_segments_have_valid_timestamps(self, tmp_path: Path) -> None:
        """All segment timestamps are non-negative and end ≥ start."""
        video_path = _skip_if_missing("a_roll_canon")

        from cutfinder.adapters.mlx_whisper import MlxWhisperTranscriber
        transcriber = MlxWhisperTranscriber(model="mlx-community/whisper-large-v3-mlx", language="zh")
        transcript = transcriber.transcribe(video_path)

        for seg in transcript.segments:
            assert 0.0 <= seg.start_s, f"Segment start must be ≥ 0: {seg}"
            assert seg.end_s >= seg.start_s, (
                f"Segment end must be ≥ start: {seg}"
            )

    def test_full_text_matches_concatenated_segments(self, tmp_path: Path) -> None:
        """full_text should equal the concatenation of segment texts."""
        video_path = _skip_if_missing("a_roll_canon")

        from cutfinder.adapters.mlx_whisper import MlxWhisperTranscriber
        transcriber = MlxWhisperTranscriber(model="mlx-community/whisper-large-v3-mlx", language="zh")
        transcript = transcriber.transcribe(video_path)

        concatenated = "".join(seg.text for seg in transcript.segments).strip()
        assert transcript.full_text.strip() == concatenated, (
            f"full_text mismatch with segment concatenation:\n  full: {transcript.full_text!r}\n"
            f" concat: {concatenated!r}"
        )
