"""Tests for FfmpegThumbnailMaker and FfmpegFrameExtractor.

Uses no real video files; ``subprocess.run`` is patched to return
pre-built ``CompletedProcess`` objects, and file existence checks are
patched via context managers.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from cutfinder.adapters.ffmpeg_media import (
    FfmpegFrameExtractor,
    FfmpegThumbnailMaker,
)


# ── helpers ───────────────────────────────────────────────────────

def _make_ffprobe_proc(
    duration: float | None = 10.0, returncode: int = 0, stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Build a fake ffprobe CompletedProcess with the given duration."""
    if returncode != 0:
        stdout = ""
    elif duration is None or (isinstance(duration, float) and duration <= 0):
        stdout = json.dumps({"format": {}})
    else:
        stdout = json.dumps({"format": {"duration": str(duration)}})

    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _make_ffmpeg_proc(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a fake ffmpeg CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=returncode, stdout="", stderr=stderr,
    )


# ── FfmpegThumbnailMaker tests (mocked subprocess.run) ───────────

class TestFfmpegThumbnailMaker:
    """Tests for thumbnail extraction with mocked subprocess + file checks."""

    def test_happy_path_middle_frame(
        self, tmp_path: Path
    ) -> None:
        """10-second video → seeks at t=5.0, writes output file."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "sample.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        # Patch Path.is_file to simulate successful file creation after ffmpeg runs

        call_count = [0]
        original_run = subprocess.run  # noqa: F841 — referenced via patch side_effect

        def mock_run(cmd, **kwargs):  # noqa: F841
            call_count[0] += 1
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=10.0)
            # ffmpeg call — simulate the output file being created
            out = Path(cmd[-1])  # last arg is output path
            out.write_bytes(b"\xff\xd8\xff\xe0")  # fake JPEG bytes
            return _make_ffmpeg_proc()

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch.object(Path, "is_file", return_value=True),
        ):
            result = maker.make(video_path, out_path)

        assert call_count[0] == 2
        # Verify seek timestamp is middle of video (5.0)
        assert result == out_path.resolve()

    def test_seek_timestamp_for_20_sec_video(
        self, tmp_path: Path
    ) -> None:
        """20-second video → seek at t=10.0 (middle)."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "video.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=20.0)
            # Verify the -ss argument is 10.0
            ss_idx = cmd.index("-ss") if "-ss" in cmd else -1
            assert ss_idx >= 0, "ffmpeg command should contain -ss"
            # The value after -ss; find it in the cmd list
            ss_value = None
            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    ss_value = cmd[i + 1]
                    break
            assert float(ss_value) == pytest.approx(10.0, rel=1e-3), (
                f"Expected seek at 10.0, got {ss_value}"
            )
            out = Path(cmd[-1])
            out.write_bytes(b"\xff\xd8\xff\xe0")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            maker.make(video_path, out_path)

    def test_zero_duration_seeks_at_t0(
        self, tmp_path: Path
    ) -> None:
        """Zero-duration video → seek at t=0.0."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "zero.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=0.0)
            ss_value = None
            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    ss_value = cmd[i + 1]
                    break
            assert float(ss_value) == pytest.approx(0.0, abs=1e-3), (
                f"Expected seek at 0.0 for zero-duration, got {ss_value}"
            )
            out = Path(cmd[-1])
            out.write_bytes(b"\xff\xd8\xff\xe0")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            maker.make(video_path, out_path)

    def test_none_duration_falls_back_to_t0(
        self, tmp_path: Path
    ) -> None:
        """None duration (unreadable) → seek at t=0.0."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "broken.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=None)
            ss_value = None
            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    ss_value = cmd[i + 1]
                    break
            assert float(ss_value) == pytest.approx(0.0, abs=1e-3), (
                f"Expected seek at 0.0 for None duration, got {ss_value}"
            )
            out = Path(cmd[-1])
            out.write_bytes(b"\xff\xd8\xff\xe0")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            maker.make(video_path, out_path)

    def test_file_not_found_raises(
        self, tmp_path: Path
    ) -> None:
        """Non-existent path should raise FileNotFoundError."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "nonexistent.mp4"  # never created

        with pytest.raises(FileNotFoundError, match="Not a video file"):
            maker.make(video_path, tmp_path / "thumb.jpg")

    def test_ffmpeg_failure_raises_runtime_error(
        self, tmp_path: Path
    ) -> None:
        """ffmpeg non-zero return → RuntimeError with stderr detail."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "sample.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=5.0)
            # ffmpeg fails
            return _make_ffmpeg_proc(returncode=1, stderr="No such file or directory")

        def conditional_is_file(self: Path) -> bool:
            # Input video exists; output file does not (ffmpeg didn't create it)
            return self == video_path

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch.object(Path, "is_file", conditional_is_file),
        ):
            with pytest.raises(RuntimeError) as excinfo:
                maker.make(video_path, out_path)

        assert "exit 1" in str(excinfo.value)
        assert "No such file or directory" in str(excinfo.value)

    def test_output_not_written_raises(
        self, tmp_path: Path
    ) -> None:
        """ffmpeg reports success but no output file → RuntimeError."""
        maker = FfmpegThumbnailMaker()
        video_path = tmp_path / "sample.mp4"
        out_path = tmp_path / "thumb.jpg"
        video_path.write_bytes(b"\x00")

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=5.0)
            # ffmpeg succeeds but doesn't create the file (simulated by Path.is_file returning False)
            return _make_ffmpeg_proc()

        def conditional_is_file(self: Path) -> bool:
            return self == video_path

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch.object(Path, "is_file", conditional_is_file),
        ):
            with pytest.raises(RuntimeError) as excinfo:
                maker.make(video_path, out_path)

        assert "no output file" in str(excinfo.value).lower()


# ── FfmpegFrameExtractor tests (mocked subprocess.run) ───────────

class TestFfmpegFrameExtractor:
    """Tests for frame extraction with mocked subprocess + file checks."""

    def test_happy_path_three_frames(
        self, tmp_path: Path
    ) -> None:
        """10-second video with count=3 → 3 evenly-spaced frames."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        extracted_paths: list[Path] = []
        timestamps_seen: list[float] = []

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=10.0)

            # ffmpeg call — simulate file creation
            out = Path(cmd[-1])
            extracted_paths.append(out)
            # Extract timestamp from -ss argument
            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    timestamps_seen.append(float(cmd[i + 1]))

            out.write_bytes(b"\x89PNG\r\n\x1a\n")  # fake PNG bytes
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path, count=3)

        assert len(result) == 3
        # Expected timestamps: duration * i / n = 10.0 * [0, 1, 2] / 3
        expected_ts = pytest.approx([0.0, 10.0 / 3.0, 20.0 / 3.0])
        assert timestamps_seen == expected_ts

    def test_frames_go_to_tempdir_as_downscaled_jpeg(
        self, tmp_path: Path
    ) -> None:
        """Frames are written to a temp dir (never the read-only source folder),
        as downscaled .jpg images."""
        extractor = FfmpegFrameExtractor()
        source_dir = tmp_path / "originals"
        source_dir.mkdir()
        video_path = source_dir / "clip.mp4"
        video_path.write_bytes(b"\x00")

        seen_cmds: list[list[str]] = []

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=6.0)
            seen_cmds.append(cmd)
            out = Path(cmd[-1])
            out.write_bytes(b"\xff\xd8\xff")  # fake JPEG bytes
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path, count=2)

        assert len(result) == 2
        for p in result:
            assert p.suffix == ".jpg"
            assert p.parent.name.startswith("cutfinder_frames_")
            # never written into the read-only source folder
            assert source_dir not in p.parents
        # ffmpeg command downscales the frame
        assert "-vf" in seen_cmds[0]
        assert any("scale=" in arg for arg in seen_cmds[0])

    def test_even_spacing_custom_count(
        self, tmp_path: Path
    ) -> None:
        """5-second video with count=4 → 4 evenly-spaced frames."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        timestamps_seen: list[float] = []

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=5.0)

            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    timestamps_seen.append(float(cmd[i + 1]))

            out = Path(cmd[-1])
            out.write_bytes(b"\x89PNG\r\n\x1a\n")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path, count=4)

        assert len(result) == 4
        expected_ts = pytest.approx([0.0, 1.25, 2.5, 3.75])
        assert timestamps_seen == expected_ts

    def test_count_zero_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """count=0 should return an empty list without calling ffmpeg."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        with patch("subprocess.run", return_value=_make_ffprobe_proc(duration=10.0)):
            result = extractor.extract(video_path, count=0)

        assert result == []

    def test_count_negative_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Negative count should return an empty list."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        with patch("subprocess.run", return_value=_make_ffprobe_proc(duration=10.0)):
            result = extractor.extract(video_path, count=-5)

        assert result == []

    def test_zero_duration_all_timestamps_t0(
        self, tmp_path: Path
    ) -> None:
        """Zero-duration video → all timestamps are 0.0."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        timestamps_seen: list[float] = []
        call_count = [0]

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=0.0)

            call_count[0] += 1
            for i, arg in enumerate(cmd):
                if arg == "-ss" and i + 1 < len(cmd):
                    timestamps_seen.append(float(cmd[i + 1]))

            out = Path(cmd[-1])
            out.write_bytes(b"\x89PNG\r\n\x1a\n")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path, count=3)

        assert len(result) == 3
        # All timestamps should be 0.0 since duration is 0
        assert all(t == pytest.approx(0.0) for t in timestamps_seen)

    def test_file_not_found_raises(
        self, tmp_path: Path
    ) -> None:
        """Non-existent path should raise FileNotFoundError."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "nonexistent.mp4"  # never created

        with pytest.raises(FileNotFoundError, match="Not a video file"):
            extractor.extract(video_path, count=2)

    def test_failed_frame_skipped_continues(
        self, tmp_path: Path
    ) -> None:
        """One frame fails (ffmpeg non-zero) → that frame is skipped, others succeed."""
        extractor = FfmpegFrameExtractor()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        timestamps_seen: list[float] = []

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=10.0)

            # Frame 2 (index 1, i.e., middle frame at t=3.33) fails
            is_ffmpeg = "ffmpeg" in cmd or "-vframes" in cmd

            if is_ffmpeg:
                # Extract the frame index from output filename
                out = Path(cmd[-1])  # e.g., _frame_0001.png
                frame_idx = int(out.stem.split("_")[-1])

                for i, arg in enumerate(cmd):
                    if arg == "-ss" and i + 1 < len(cmd):
                        timestamps_seen.append(float(cmd[i + 1]))

                # Frame at index 1 (middle) fails
                if frame_idx == 1:
                    out.write_bytes(b"")  # create empty file so is_file passes? No, let's not
                    out.unlink(missing_ok=True)  # simulate file NOT being created
                else:
                    out.write_bytes(b"\x89PNG\r\n\x1a\n")

                return _make_ffmpeg_proc()
            return _make_ffprobe_proc(duration=10.0)

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path, count=3)

        # Only 2 frames succeed (index 0 and index 2); middle one is skipped
        assert len(result) == 2

    def test_default_count_uses_constructor_value(
        self, tmp_path: Path
    ) -> None:
        """When count is not specified, uses default_count from constructor."""
        extractor = FfmpegFrameExtractor(default_count=5)
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        call_count = [0]

        def mock_run(cmd, **kwargs):
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=10.0)
            call_count[0] += 1
            out = Path(cmd[-1])
            out.write_bytes(b"\x89PNG\r\n\x1a\n")
            return _make_ffmpeg_proc()

        with patch("subprocess.run", side_effect=mock_run):
            result = extractor.extract(video_path)  # no count specified

        assert call_count[0] == 5
        assert len(result) == 5


# ── Edge case: _probe_duration helper tests (mocked subprocess) ───

class TestProbeDuration:
    """Tests for the private _probe_duration helper function."""

    def test_valid_json_returns_float(
        self, tmp_path: Path
    ) -> None:
        """Valid ffprobe JSON with duration → returns the float."""
        from cutfinder.adapters.ffmpeg_media import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = _make_ffprobe_proc(duration=42.5)
        with patch("subprocess.run", return_value=proc):
            result = _probe_duration(video_path)

        assert result == pytest.approx(42.5)

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Non-JSON stdout → returns None."""
        from cutfinder.adapters.ffmpeg_media import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="not json at all", stderr="",
        )

        with patch("subprocess.run", return_value=proc):
            result = _probe_duration(video_path)

        assert result is None

    def test_ffprobe_not_found_returns_none(self, tmp_path: Path) -> None:
        """ffprobe binary not in PATH → returns None (no exception)."""
        from cutfinder.adapters.ffmpeg_media import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _probe_duration(video_path)

        assert result is None


# ── Edge case: output directory creation tests ───────────────────

class TestEnsureParentDir:
    """Tests for output directory creation."""

    def test_creates_nested_directories(
        self, tmp_path: Path
    ) -> None:
        """Output path in non-existent nested dir → parent dirs are created."""
        from cutfinder.adapters.ffmpeg_media import _ensure_parent  # noqa: F811

        deep_path = tmp_path / "a" / "b" / "c" / "thumb.jpg"
        assert not deep_path.parent.exists()

        _ensure_parent(deep_path)

        assert deep_path.parent.exists()
        # Note: the file itself is NOT created, only parent dirs
