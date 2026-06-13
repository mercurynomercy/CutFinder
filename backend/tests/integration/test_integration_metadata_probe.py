"""Integration tests for FfmpegProbe using real video files.

These exercise the actual ffprobe CLI (no mocking) and validate that
the JSON parsing, field extraction, and date-source detection work with
real-world footage.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration`` or ``make test-integration``.
"""

from __future__ import annotations

import pathlib

import pytest

from cutfinder.adapters.ffmpeg_probe import FfmpegProbe
from cutfinder.domain.models import VideoMetadata


# ── fixtures ───────────────────────────────────────────────────────

def _test_video_dir() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve().parents[3]  # repo root (tests/integration -> tests -> backend -> CutFinder)
    return root / "testVideo"


SAMPLE_FILES = {
    "a_roll_canon": _test_video_dir() / "MVI_5298.MP4",
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

    def test_a_roll_canon_metadata(self) -> None:
        """Canon A-roll clip → duration > 0, width=3840, height=2160, has_audio=True."""
        _skip_if_missing("a_roll_canon")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["a_roll_canon"])

        assert meta.duration_s is not None and meta.duration_s > 0
        assert meta.width == 3840, f"Expected width=3840, got {meta.width}"
        assert meta.height == 2160, f"Expected height=2160, got {meta.height}"
        assert meta.has_audio is True

    def test_b_roll_dji_metadata(self) -> None:
        """DJI drone footage → duration > 0, capture_time not None."""
        _skip_if_missing("b_roll_dji")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["b_roll_dji"])

        assert meta.duration_s is not None and meta.duration_s > 0
        assert meta.capture_time is not None


@pytest.mark.integration
class TestFfmpegProbeDateSource:
    """Validate date_source='embedded' for files with embedded creation_time."""

    def test_canon_embedded_date(self) -> None:
        """Canon A-roll → date_source='embedded'."""
        _skip_if_missing("a_roll_canon")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["a_roll_canon"])

        assert meta.date_source == "embedded"
        assert meta.capture_time is not None

    def test_dji_embedded_date(self) -> None:
        """DJI drone footage → date_source='embedded'."""
        _skip_if_missing("b_roll_dji")

        probe = FfmpegProbe()
        meta: VideoMetadata = probe.probe(SAMPLE_FILES["b_roll_dji"])

        assert meta.date_source == "embedded"
        assert meta.capture_time is not None
