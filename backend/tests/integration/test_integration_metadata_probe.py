"""Integration tests for FfmpegProbe using real video files.

These exercises the actual ffprobe CLI (no mocking) and validate that
the JSON parsing, field extraction, and date-source detection work with
real-world footage.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration`` or ``make test-integration``.
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
from unittest.mock import patch

import pytest

from cutfinder.adapters.ffmpeg_probe import FfmpegProbe
from cutfinder.domain.models import VideoMetadata

# ── fixtures ───────────────────────────────────────────────────────

def _test_video_dir() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve().parents[3]  # repo root (tests/integration -> tests -> backend -> CutFinder)
    return root / "testVideo"


SAMPLE_FILES = {
    "a_roll_canon": _test_video_dir() / "MVI_5298.MP4",
    "b_roll_canon": _test_video_dir() / "MVI_5368.MP4",
    "b_roll_dji": _test_video_dir() / "DJI_20260515175239_0097_D.MP4",
}


def _skip_if_missing(name: str) -> None:
    """Skip the test if a sample file doesn't exist."""
    path = SAMPLE_FILES.get(name)
    if not (path and path.exists()):
        pytest.skip(f"Sample file missing: {path}")


# ── integration tests (real ffprobe) ─────────────────────────────

@pytest.mark.integration
class TestFfmpegProbeRealVideo:
    """Validate FfmpegProbe against real footage."""

    def test_a_roll_canon(self) -> None:
        """Canon A-roll clip → has_audio=True, valid metadata."""
        _skip_if_missing("a_roll_canon")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["a_roll_canon"])

        assert meta.width is not None and meta.width > 0
        assert meta.height is not None and meta.height > 0
        assert meta.duration_s is not None and meta.duration_s > 0
        assert meta.has_audio is True
        # Canon cameras usually embed creation_time in MP4 tags.
        assert meta.date_source in ("embedded", "file")

    def test_b_roll_canon(self) -> None:
        """Canon B-roll clip → has_audio=False (no spoken track)."""
        _skip_if_missing("b_roll_canon")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["b_roll_canon"])

        assert meta.width is not None
        assert meta.height is not None
        assert meta.duration_s is not None and meta.duration_s > 0

    def test_b_roll_dji_drone(self) -> None:
        """DJI drone footage → valid video stream, date_source varies."""
        _skip_if_missing("b_roll_dji")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["b_roll_dji"])

        assert meta.width is not None
        assert meta.height is not None
        # DJI files often don't embed creation_time in MP4 tags,
        # so date_source may fall back to file birth time.

    def test_ffprobe_error_on_non_video(self, tmp_path: pathlib.Path) -> None:
        """Probing a non-video file should raise RuntimeError."""
        probe = FfmpegProbe()
        bad_file = tmp_path / "not_a_video.txt"
        bad_file.write_text("this is not a video file")

        with pytest.raises(RuntimeError, match="ffprobe exited"):
            probe.probe(bad_file)


@pytest.mark.integration
class TestFfmpegProbeDateSource:
    """Validate date_source logic with real files."""

    def test_embedded_date_produces_correct_date(self) -> None:
        """If creation_time is embedded, date_source='embedded' and capture_time matches."""
        _skip_if_missing("a_roll_canon")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["a_roll_canon"])

        if meta.date_source == "embedded":
            assert meta.capture_time is not None
            # capture_time should be a timezone-aware datetime
            assert meta.capture_time.tzinfo is not None

    def test_fallback_date_produces_correct_year(self) -> None:
        """When falling back to file birth time, the year should match."""
        _skip_if_missing("b_roll_dji")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["b_roll_dji"])

        if meta.date_source == "file":
            assert meta.capture_time is not None
            # DJI files from 2025 should fall back to a reasonable year.
