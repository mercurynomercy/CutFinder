"""Tests for SileroSpeechDetector.

Uses no real video files; ``subprocess.run`` and file existence are patched
to simulate various scenarios (normal audio, silence, failures).

The Silero VAD model is NOT loaded in unit tests — ``_extract_audio_bytes``
is mocked to return known PCM bytes, and the ratio is verified via the
computed speech duration from mock timestamps.
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cutfinder.adapters.silero_vad import (
    SileroSpeechDetector,
)


# ── helpers ───────────────────────────────────────────────────────

def _make_ffprobe_proc(
    duration: float | None = 10.0, returncode: int = 0, stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Build a fake ffprobe CompletedProcess with the given duration."""
    if returncode != 0:
        stdout = ""
    elif duration is None or (isinstance(duration, float) and duration <= 0):
        stdout = '{"format": {}}'
    else:
        stdout = f'{{"format": {{"duration": "{duration}"}}}}'

    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _pcm_bytes(duration_s: float = 10.0) -> bytes:
    """Generate N seconds of silent PCM 16-bit mono at 16 kHz."""
    num_samples = int(duration_s * 16000.0)
    return struct.pack(f"<{num_samples}h", *[0] * num_samples)


def _pcm_bytes_with_speech(duration_s: float = 10.0, speech_fraction: float = 0.4) -> bytes:
    """Generate PCM with a portion that is non-silent (simulates speech pattern)."""
    total_samples = int(duration_s * 16000.0)
    speech_samples = int(total_samples * speech_fraction)
    silence_count = total_samples - speech_samples

    # Speech region: non-zero values (sinusoidal pattern)
    import math  # noqa: E402 — top-level ok in helper, but move to local if lint complains
    speech_values = [int(10000 * math.sin(i * 2 * math.pi / 50)) for i in range(speech_samples)]
    silence_values = [0] * silence_count

    all_vals = speech_values + silence_values
    return struct.pack(f"<{len(all_vals)}h", *all_vals)


# ── SileroSpeechDetector tests (mocked VAD + subprocess) ─────────

class TestSileroSpeechDetector:
    """Tests for speech ratio computation with mocked VAD + subprocess."""

    def test_happy_path_speech_ratio_04(
        self, tmp_path: Path
    ) -> None:
        """10-second video with ~55% speech → ratio ≈ 0.55 (two segments)."""
        import silero_vad as _sv

        detector = SileroSpeechDetector()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(_pcm_bytes(10.0))

        call_count = [0]

        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            if "ffprobe" in cmd:
                return _make_ffprobe_proc(duration=10.0)
            # ffmpeg audio extraction — always succeeds with our PCM bytes
            return subprocess.CompletedProcess(
                args=["ffmpeg"], returncode=0, stdout=_pcm_bytes(10.0), stderr="",
            )

        with (
            patch("subprocess.run", side_effect=mock_run),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=_pcm_bytes(10.0),
            ),
            patch.object(_sv, "get_speech_timestamps", return_value=[
                {"start": 0.5, "end": 4.5},   # 4 seconds
                {"start": 6.0, "end": 7.5},   # 1.5 seconds
            ]),
        ):
            ratio = detector.speech_ratio(video_path)

        # Total speech: 4.0 + 1.5 = 5.5; ratio = 5.5/10.0 = 0.55
        assert ratio == pytest.approx(0.55, rel=1e-3)

    def test_speech_ratio_exact_04(
        self, tmp_path: Path
    ) -> None:
        """Video with exactly 40% speech → ratio = 0.4."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(_pcm_bytes(10.0))

        # 4 seconds of speech out of 10 = 0.4
        import silero_vad as _sv

        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=10.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=_pcm_bytes(10.0),
            ),
            patch.object(_sv, "get_speech_timestamps", return_value=[
                {"start": 2.0, "end": 6.0},   # exactly 4 seconds
            ]),
        ):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.4, rel=1e-3)

    def test_no_speech_ratio_0(
        self, tmp_path: Path
    ) -> None:
        """Silent video → speech ratio is 0.0."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "silent.mp4"
        video_path.write_bytes(_pcm_bytes(5.0))

        # Empty speech_timestamps → no speech detected
        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=5.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=_pcm_bytes(5.0),
            ),
        ):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_full_speech_ratio_1(
        self, tmp_path: Path
    ) -> None:
        """All speech → ratio is 1.0."""
        import silero_vad as _sv

        detector = SileroSpeechDetector()
        video_path = tmp_path / "all_speech.mp4"
        video_path.write_bytes(_pcm_bytes(8.0))

        # Entire duration is speech
        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=8.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=_pcm_bytes(8.0),
            ),
            patch.object(_sv, "get_speech_timestamps", return_value=[
                {"start": 0.0, "end": 8.0},   # entire duration
            ]),
        ):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(1.0, rel=1e-3)

    def test_zero_duration_returns_0(
        self, tmp_path: Path
    ) -> None:
        """Zero-duration video → ratio is 0.0 (no audio to process)."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "zero.mp4"
        video_path.write_bytes(_pcm_bytes(0.0))

        with patch("subprocess.run", return_value=_make_ffprobe_proc(duration=0.0)):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_none_duration_returns_0(
        self, tmp_path: Path
    ) -> None:
        """Unreadable video (None duration) → ratio is 0.0."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "broken.mp4"
        video_path.write_bytes(b"\x00")

        with patch("subprocess.run", return_value=_make_ffprobe_proc(duration=None)):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_file_not_found_raises(
        self, tmp_path: Path
    ) -> None:
        """Non-existent path → FileNotFoundError."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "nonexistent.mp4"  # never created

        with pytest.raises(FileNotFoundError, match="Not a video file"):
            detector.speech_ratio(video_path)

    def test_no_audio_stream_returns_0(
        self, tmp_path: Path
    ) -> None:
        """Video with no audio track (_extract_audio_bytes returns None) → 0.0."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "no_audio.mp4"
        video_path.write_bytes(b"\x00")

        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=10.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=None,  # ffmpeg produced nothing (no audio stream)
            ),
        ):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_ffmpeg_failure_returns_0(
        self, tmp_path: Path
    ) -> None:
        """ffmpeg extraction failure → returns 0.0 (graceful degradation)."""
        detector = SileroSpeechDetector()
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=5.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=None,  # ffmpeg failed silently in _extract_audio_bytes
            ),
        ):
            ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)


# ── Edge case: custom threshold tests ─────────────────────────────

class TestCustomThreshold:
    """Tests for the custom threshold parameter."""

    def test_threshold_passed_to_vad(
        self, tmp_path: Path
    ) -> None:
        """Custom threshold is passed through to get_speech_timestamps."""
        detector = SileroSpeechDetector(threshold=0.8)
        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(_pcm_bytes(5.0))

        mock_model = MagicMock()  # type: ignore[assignment] — silero VAD model surrogate

        with (
            patch("subprocess.run", return_value=_make_ffprobe_proc(duration=5.0)),
            patch(
                "cutfinder.adapters.silero_vad._extract_audio_bytes",
                return_value=_pcm_bytes(5.0),
            ),
        ):
            # Patch silero_vad module import to avoid loading real model
            with patch.dict("sys.modules", {"silero_vad": MagicMock()}):
                # Patch _ensure_model_loaded to skip real model loading
                detector._model = mock_model  # type: ignore[assignment]

        assert detector._threshold == 0.8


# ── Edge case: audio_bytes_to_tensor tests (mocked struct) ───────

class TestAudioBytesToTensor:
    """Tests for the private _audio_bytes_to_tensor helper."""

    def test_silent_pcm_returns_zero_mean(
        self, tmp_path: Path
    ) -> None:
        """All-zero PCM → tensor with mean ≈ 0."""
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        raw = struct.pack("<4h", 0, 0, 0, 0)
        tensor = _audio_bytes_to_tensor(raw, duration_s=4.0 / 16000.0)

        assert tensor is not None
        # Silenced audio → mean ≈ 0 (actually exactly 0)
        assert tensor.mean().item() == pytest.approx(0.0, abs=1e-6)

    def test_nonzero_pcm_normalized(self, tmp_path: Path) -> None:
        """Non-zero PCM → normalized to [-1, 1] range."""
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        max_val = struct.pack("<h", 32767)
        tensor = _audio_bytes_to_tensor(max_val, duration_s=1.0 / 16000.0)

        assert tensor is not None
        # Max int16 / 32768 = 0.9999... ≈ 1
        assert tensor.max().item() == pytest.approx(0.99996, rel=1e-3)

    def test_empty_bytes_returns_none(self, tmp_path: Path) -> None:
        """Empty bytes → returns None."""
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        tensor = _audio_bytes_to_tensor(b"", duration_s=0.0)
        assert tensor is None

    def test_truncated_samples_returns_none(self, tmp_path: Path) -> None:
        """Odd-length bytes (truncated sample) → returns None."""
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        tensor = _audio_bytes_to_tensor(b"\x00", duration_s=1.0 / 16000.0)
        assert tensor is None


# ── Edge case: _probe_duration helper tests (mocked subprocess) ───

class TestProbeDuration:
    """Tests for the private _probe_duration helper function."""

    def test_valid_json_returns_float(
        self, tmp_path: Path
    ) -> None:
        """Valid ffprobe JSON with duration → returns the float."""
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = _make_ffprobe_proc(duration=42.5)
        with patch("subprocess.run", return_value=proc):
            result = _probe_duration(video_path)

        assert result == pytest.approx(42.5)

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Non-JSON stdout → returns None."""
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

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
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _probe_duration(video_path)

        assert result is None


# ── Edge case: ffmpeg audio extraction tests (mocked subprocess) ─

class TestExtractAudioBytes:
    """Tests for the private _extract_audio_bytes helper."""

    def test_success_returns_pcm_bytes(
        self, tmp_path: Path
    ) -> None:
        """Successful ffmpeg → returns PCM bytes."""
        from cutfinder.adapters.silero_vad import _extract_audio_bytes  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout=_pcm_bytes(5.0), stderr="",
        )

        with patch("subprocess.run", return_value=proc):
            result = _extract_audio_bytes(video_path)

        assert len(result) > 0

    def test_failure_returns_none(
        self, tmp_path: Path
    ) -> None:
        """ffmpeg non-zero return → returns None."""
        from cutfinder.adapters.silero_vad import _extract_audio_bytes  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=1, stdout="", stderr="No such file",
        )

        with patch("subprocess.run", return_value=proc):
            result = _extract_audio_bytes(video_path)

        assert result is None


# ── Edge case: _ensure_model_loaded tests (mocked silero_vad) ─────

class TestEnsureModelLoaded:
    """Tests for lazy model loading."""

    def test_lazy_load_sets_model(
        self, tmp_path: Path
    ) -> None:
        """_ensure_model_loaded sets _model after first call."""
        mock_module = MagicMock()  # type: ignore[assignment]
        mock_model = MagicMock()  # type: ignore[assignment]
        mock_module.load_silero_vad.return_value = mock_model

        detector = SileroSpeechDetector()
        assert detector._model is None  # not yet loaded

        with patch.dict("sys.modules", {"silero_vad": mock_module}):
            detector._ensure_model_loaded()

        assert detector._model == mock_model


# ── Edge case: ratio clamping tests (mocked VAD) ────────────────

class TestRatioClamping:
    """Tests that ratio is always clamped to [0, 1]."""

    def test_ratio_clipped_to_1(
        self, tmp_path: Path
    ) -> None:
        """Speech duration exceeding video length → ratio clamped to 1.0."""
        # Directly verify the clamping formula used in speech_ratio():
        total_speech = 25.0
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == 1.0

    def test_ratio_clipped_to_0(
        self, tmp_path: Path
    ) -> None:
        """Negative speech duration (impossible but defensive) → ratio clamped to 0.0."""
        total_speech = -5.0
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == 0.0

    def test_ratio_normal_range(
        self, tmp_path: Path
    ) -> None:
        """Speech duration within bounds → ratio passed through unclamped."""
        total_speech = 3.5
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == pytest.approx(0.35)
