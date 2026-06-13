"""Integration tests for FfmpegThumbnailMaker and FfmpegFrameExtractor using real video files.

These exercise the actual ffmpeg CLI (no mocking) and validate that
thumbnail extraction, frame sampling, output dimensions, and file counts
work with real-world footage.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cutfinder.adapters.ffmpeg_media import (
    FfmpegFrameExtractor,
    FfmpegThumbnailMaker,
)


# ── fixtures ───────────────────────────────────────────────────────

def _test_video_dir() -> Path:
    root = Path(__file__).resolve().parents[3]  # repo root (tests/integration -> tests -> backend -> CutFinder)
    return root / "testVideo"


def _integration_video_dir() -> Path:
    """Return the VlogRaw directory that holds real sample footage."""
    return Path("/Users/jianhengpan/VlogRaw")


SAMPLE_FILES = {
    "a_roll_canon": _test_video_dir() / "MVI_5298.MP4",
    "b_roll_dji": _test_video_dir() / "DJI_20260515175239_0097_D.MP4",
}

INTEGRATION_FILES = {
    "a_roll_canon": _integration_video_dir() / "MVI_5298.MP4",
    "b_roll_canon": _integration_video_dir() / "MVI_5368.MP4",
    "b_roll_dji": _integration_video_dir() / "DJI_20260515175239_0097_D.MP4",
}


def _skip_if_missing(name: str) -> None:
    """Skip the test if a sample file doesn't exist."""
    path = SAMPLE_FILES.get(name) or INTEGRATION_FILES.get(name)
    if not (path and path.exists()):
        pytest.skip(f"Sample file missing: {path}")


def _get_image_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image file using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return (0, 0)
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    return (int(stream.get("width", 0)), int(stream.get("height", 0)))


# ── integration tests: thumbnail maker (real ffmpeg) ─────────────

@pytest.mark.integration
class TestFfmpegThumbnailMakerRealVideo:
    """Validate FfmpegThumbnailMaker against real footage."""

    def test_a_roll_canon_thumbnail(self, tmp_path: Path) -> None:
        """Canon A-roll → thumbnail exists with reasonable dimensions."""
        _skip_if_missing("a_roll_canon")

        maker = FfmpegThumbnailMaker()
        video_path = SAMPLE_FILES["a_roll_canon"]
        out_path = tmp_path / "thumb_a.jpg"

        result = maker.make(video_path, out_path)
        assert result.exists(), "Thumbnail file was not created"

        w, h = _get_image_dimensions(result)
        assert w >= 100 and h >= 100, (
            f"Thumbnail dimensions too small: {w}x{h}"
        )

    def test_b_roll_dji_thumbnail(self, tmp_path: Path) -> None:
        """DJI drone footage → thumbnail exists with reasonable dimensions."""
        _skip_if_missing("b_roll_dji")

        maker = FfmpegThumbnailMaker()
        video_path = SAMPLE_FILES["b_roll_dji"]
        out_path = tmp_path / "thumb_b.jpg"

        result = maker.make(video_path, out_path)
        assert result.exists(), "Thumbnail file was not created"

        w, h = _get_image_dimensions(result)
        assert w >= 100 and h >= 100, (
            f"Thumbnail dimensions too small: {w}x{h}"
        )

    def test_output_in_nested_dir(self, tmp_path: Path) -> None:
        """Output path in non-existent nested directory → parent dirs created, file exists."""
        _skip_if_missing("a_roll_canon")

        maker = FfmpegThumbnailMaker()
        video_path = SAMPLE_FILES["a_roll_canon"]
        out_path = tmp_path / "deep" / "nested" / "dir" / "thumb.jpg"

        result = maker.make(video_path, out_path)
        assert result.exists()


# ── integration tests: frame extractor (real ffmpeg) ─────────────

@pytest.mark.integration
class TestFfmpegFrameExtractorRealVideo:
    """Validate FfmpegFrameExtractor against real footage."""

    def test_a_roll_three_frames(self, tmp_path: Path) -> None:
        """Canon A-roll → 3 evenly-spaced frames, all exist with valid dimensions."""
        _skip_if_missing("a_roll_canon")

        extractor = FfmpegFrameExtractor()
        video_path = SAMPLE_FILES["a_roll_canon"]

        result = extractor.extract(video_path, count=3)
        assert len(result) == 3, f"Expected 3 frames, got {len(result)}"

        for frame_path in result:
            assert frame_path.exists(), f"Frame file missing: {frame_path}"
            w, h = _get_image_dimensions(frame_path)
            assert w >= 100 and h >= 100, (
                f"Frame dimensions too small: {w}x{h}"
            )

    def test_b_roll_custom_count(self, tmp_path: Path) -> None:
        """B-roll with count=5 → 5 frames, all exist."""
        _skip_if_missing("b_roll_canon")

        extractor = FfmpegFrameExtractor()
        video_path = INTEGRATION_FILES["b_roll_canon"]

        result = extractor.extract(video_path, count=5)
        assert len(result) == 5, f"Expected 5 frames, got {len(result)}"

        for frame_path in result:
            assert frame_path.exists(), f"Frame file missing: {frame_path}"

    def test_count_zero_returns_empty(self, tmp_path: Path) -> None:
        """count=0 → empty list (no ffmpeg calls)."""
        _skip_if_missing("a_roll_canon")

        extractor = FfmpegFrameExtractor()
        video_path = SAMPLE_FILES["a_roll_canon"]

        result = extractor.extract(video_path, count=0)
        assert result == []


# ── integration tests: default_count parameter (real ffmpeg) ─────

@pytest.mark.integration
class TestFfmpegFrameExtractorDefaultCount:
    """Validate the default_count constructor parameter."""

    def test_default_count_five(self, tmp_path: Path) -> None:
        """Extractor(default_count=5), no count arg → 5 frames extracted."""
        _skip_if_missing("a_roll_canon")

        extractor = FfmpegFrameExtractor(default_count=5)
        video_path = SAMPLE_FILES["a_roll_canon"]

        result = extractor.extract(video_path)  # no count specified
        assert len(result) == 5, f"Expected 5 frames (default_count), got {len(result)}"
