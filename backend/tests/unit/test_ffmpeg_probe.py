"""Tests for FfmpegProbe — validate JSON parsing and edge cases.

Uses no real video files; instead ``subprocess.run`` is patched
to return pre-built ``CompletedProcess`` objects, and ``Path.stat`` is
patched via context manager for the file-birth-time fallback path.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cutfinder.adapters.ffmpeg_probe import (
    FfmpegProbe,
    _parse_creation_time,
    _parse_fraction,
)


# ── helpers ───────────────────────────────────────────────────────

def _sample_json(
    has_creation_time: bool = True,
    has_audio_stream: bool = False,
    extra_streams: list[dict[str, Any]] | None = None,
) -> str:
    """Return a minimal ffprobe JSON payload matching the spec."""

    streams = [
        {
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30000/1001",
            "codec_name": "h264",
        }
    ]

    if has_audio_stream:
        streams.append({"codec_type": "audio", "codec_name": "aac"})

    if extra_streams:
        streams.extend(extra_streams)

    tags: dict[str, str] = {}
    if has_creation_time:
        tags["creation_time"] = "2026-04-25T03:24:44.000000Z"

    payload = {
        "format": {"duration": "19.085733", "tags": tags},
        "streams": streams,
    }

    return json.dumps(payload)


def _make_proc(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ── _parse_fraction tests ────────────────────────────────────────

class TestParseFraction:
    """Tests for the _parse_fraction helper."""

    def test_simple_fraction(self) -> None:
        """'30000/1001' should parse to approximately 29.97 fps (NTSC)."""
        result = _parse_fraction("30000/1001")
        assert result == pytest.approx(29.97, rel=1e-3)

    def test_whole_number(self) -> None:
        """'30/1' should parse to exactly 30.0."""
        assert _parse_fraction("30/1") == pytest.approx(30.0)

    def test_none_input(self) -> None:
        """None input should return None."""
        assert _parse_fraction(None) is None

    def test_empty_string(self) -> None:
        """Empty string input should return None."""
        assert _parse_fraction("") is None

    def test_zero_denominator(self) -> None:
        """Denominator of 0 should return None (avoid division by zero)."""
        assert _parse_fraction("30/0") is None

    def test_unparseable(self) -> None:
        """Non-numeric values should return None."""
        assert _parse_fraction("not_a_number/2") is None


# ── _parse_creation_time tests ───────────────────────────────────

class TestParseCreationTime:
    """Tests for the _parse_creation_time helper."""

    def test_utc_zulu(self) -> None:
        """ISO 8601 with 'Z' suffix should produce a UTC-aware datetime."""
        result = _parse_creation_time("2026-04-25T03:24:44.000000Z")
        expected = _dt.datetime(2026, 4, 25, 3, 24, 44, tzinfo=_dt.timezone.utc)
        assert result == expected

    def test_none_input(self) -> None:
        """None input should return None."""
        assert _parse_creation_time(None) is None

    def test_empty_string(self) -> None:
        """Empty string input should return None."""
        assert _parse_creation_time("") is None

    def test_naive_string_assumes_utc(self) -> None:
        """ISO 8601 without timezone info should default to UTC."""
        result = _parse_creation_time("2026-04-25T03:24:44")
        expected = _dt.datetime(2026, 4, 25, 3, 24, 44, tzinfo=_dt.timezone.utc)
        assert result == expected

    def test_unparseable_string(self) -> None:
        """Invalid date string should return None."""
        assert _parse_creation_time("not-a-date") is None


# ── FfmpegProbe tests (mocked subprocess.run) ───────────────────

class TestFfmpegProbe:
    """Tests for the FfmpegProbe.probe method using mocked subprocess.run."""

    def test_happy_path_all_fields(
        self, tmp_path: Path
    ) -> None:
        """Valid ffprobe JSON returns VideoMetadata with all fields, date_source='embedded'."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        stdout = _sample_json()
        proc = _make_proc(stdout)

        with patch("subprocess.run", return_value=proc):
            meta = probe.probe(path)

        assert meta.date_source == "embedded"
        assert meta.capture_time == _dt.datetime(2026, 4, 25, 3, 24, 44, tzinfo=_dt.timezone.utc)
        assert meta.duration_s == pytest.approx(19.085733)
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.fps == pytest.approx(30000 / 1001, rel=1e-6)
        assert meta.codec == "h264"
        assert meta.has_audio is False

    def test_fallback_to_file_birth_time(
        self, tmp_path: Path
    ) -> None:
        """No creation_time tag → fall back to mocked file birth time, date_source='file'."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        # JSON without creation_time tag, and a mock stat result with birth time
        stdout = _sample_json(has_creation_time=False)
        proc = _make_proc(stdout)

        mock_stat = type("stat_result", (), {
            "st_birthtime": 1_745_532_284.0,
            "st_mode": 33188,
        })()

        with patch("subprocess.run", return_value=proc):
            with patch.object(Path, "stat", return_value=mock_stat):
                meta = probe.probe(path)

        assert meta.date_source == "file"
        # st_birthtime=1_745_532_284.0 → 2025-04-24T22:04:44 UTC
        expected_time = _dt.datetime(2025, 4, 24, 22, 4, 44, tzinfo=_dt.timezone.utc)
        assert meta.capture_time == expected_time

    def test_no_audio_stream(
        self, tmp_path: Path
    ) -> None:
        """No audio stream → has_audio=False, codec from video only."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        # Only a video stream, no audio
        stdout = _sample_json(has_audio_stream=False)
        proc = _make_proc(stdout)

        with patch("subprocess.run", return_value=proc):
            meta = probe.probe(path)

        assert meta.has_audio is False
        assert meta.codec == "h264"  # codec from the video stream

    def test_multiple_streams_picks_first_video(
        self, tmp_path: Path
    ) -> None:
        """Multiple streams → correctly picks first video stream for width/height/fps."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        # First stream is video (1920x1080 @ 30fps), second is audio, third is video (4K)
        # The probe should pick the first video stream.
        extra_stream = {
            "codec_type": "video",
            "width": 3840,
            "height": 2160,
            "r_frame_rate": "60/1",
            "codec_name": "hevc",
        }
        stdout = _sample_json(
            has_audio_stream=True, extra_streams=[extra_stream],
        )
        proc = _make_proc(stdout)

        with patch("subprocess.run", return_value=proc):
            meta = probe.probe(path)

        # Should use the first video stream (1920x1080), not the second
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.fps == pytest.approx(30000 / 1001, rel=1e-6)
        assert meta.codec == "h264"
        # Audio stream is still detected
        assert meta.has_audio is True


# ── FfmpegProbeError tests (mocked subprocess.run) ───────────────

class TestFfmpegProbeError:
    """Tests for error paths in FfmpegProbe."""

    def test_ffprobe_nonzero_returncode(
        self, tmp_path: Path
    ) -> None:
        """ffprobe returns non-zero → RuntimeError with stderr message."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        bad_proc = _make_proc("", returncode=1, stderr="Invalid data found when processing input")

        with patch("subprocess.run", return_value=bad_proc):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                probe.probe(path)

    def test_ffprobe_nonzero_with_stderr_detail(
        self, tmp_path: Path
    ) -> None:
        """ffprobe error message is included in the RuntimeError."""
        probe = FfmpegProbe()
        path = tmp_path / "sample.mp4"
        path.write_bytes(b"\x00")

        bad_proc = _make_proc(
            "", returncode=1, stderr="File '/path/to/bad.mp4' is not a supported format",
        )

        with patch("subprocess.run", return_value=bad_proc):
            with pytest.raises(RuntimeError, match="not a supported format"):
                probe.probe(path)
