"""SileroSpeechDetector — speech ratio via Silero VAD.

Uses ffmpeg to extract audio from a video file, then passes it through
Silero VAD (ONNX) to compute the fraction of time that contains speech.

Edge cases handled:
  * Zero-duration video → ratio is ``0.0`` (no speech possible).
  * Video with no audio stream → ratio is ``0.0`` (handled by ffmpeg returning empty).
  * Non-existent file → raises ``FileNotFoundError``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import torch  # type: ignore[import]

from ..ports.speech import SpeechDetector


def _probe_duration(path: Path) -> float | None:
    """Return video duration in seconds, or ``None`` on failure."""
    try:
        result = subprocess.run(  # noqa: S603 — ffprobe is trusted local tool
            [
                "ffprobe",
                "-v", "quiet",
                "-show_format",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    try:
        import json as _json
        data = _json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0)) or None
    except (ValueError, TypeError):
        return None


def _extract_audio_bytes(path: Path) -> bytes | None:
    """Extract raw audio as PCM 16-bit mono at 16 kHz (Silero VAD native).

    Uses ``-map 0:a:0`` to explicitly select the first audio stream,
    avoiding issues with video edit-list errors that can cause ffmpeg
    to bail out before processing any streams.

    Returns ``None`` if ffmpeg fails or produces no output.
    """
    result = subprocess.run(  # noqa: S603 — ffmpeg is trusted local tool
        [
            "ffmpeg",
            "-y",
            "-i", str(path),
            "-map", "0:a:0",    # explicitly map first audio stream (avoids video edit-list issues)
            "-acodec", "pcm_s16le",
            "-ar", "16000",     # Silero VAD native sample rate
            "-ac", "1",         # mono channel
            "-f", "data",       # raw output format → stdout
            "-",                # write to stdout
        ],
        capture_output=True,
        check=False,
    )

    if result.returncode != 0 or not result.stdout:
        return None

    return result.stdout


def _audio_bytes_to_tensor(raw: bytes, duration_s: float) -> torch.Tensor | None:
    """Convert raw PCM 16-bit mono bytes to a float32 torch tensor scaled [-1, 1].

    Silero VAD expects normalized floats.
    """
    try:
        import struct

        # pcm_s16le → 2 bytes per sample, little-endian signed int
        num_samples = len(raw) // 2
        if num_samples == 0:
            return None

        # Cast raw bytes to int16 values, then normalize to [-1, 1]
        samples = struct.unpack(f"<{num_samples}h", raw)
        # Convert tuple → numpy array → torch tensor (torch.from_numpy needs np.ndarray)
        import numpy as _np  # type: ignore[import]

        tensor = torch.from_numpy(_np.array(samples, dtype=_np.int16)).float() / 32768.0

        # Trim to exact duration (ffmpeg may produce extra padding samples)
        expected = int(duration_s * 16000.0)
        if len(tensor) > expected:
            tensor = tensor[:expected]

        return tensor.squeeze(0)  # ensure 1-D
    except (struct.error, ValueError):
        return None


# ── SileroSpeechDetector ─────────────────────────────────────────

class SileroSpeechDetector(SpeechDetector):
    """Detect speech fraction in a video using the Silero VAD model.

    Parameters
    ----------
    threshold:
        Speech probability threshold for classifying a chunk as speech.
        Default ``0.5`` (Silero VAD recommended default).  Only affects the
        internal chunking; the returned ratio is always in [0, 1].
    model:
        A pre-loaded Silero VAD ONNX/JIT model.  When ``None`` the model
        is lazily loaded on first call (cached per instance).

    Examples
    --------
    >>> detector = SileroSpeechDetector()  # lazy-load model on first call
    >>> ratio = detector.speech_ratio(Path("/path/to/video.mp4"))  # noqa: D100
    """

    def __init__(
        self,
        threshold: float = 0.5,
        model: Optional[object] = None,
    ) -> None:
        self._threshold = threshold
        # Lazy-loaded; set after first __init__ call in speech_ratio()
        self._model = model  # type: ignore[assignment]

    def _ensure_model_loaded(self) -> None:
        """Load the Silero VAD ONNX model on first use (cached per instance)."""
        if self._model is not None:
            return

        import silero_vad  # type: ignore[import] — installed per pyproject.toml

        self._model = silero_vad.load_silero_vad(onnx=True, opset_version=16)

    def speech_ratio(self, path: Path) -> float:
        """Return a value in ``[0.0, 1.0]`` representing the fraction of speech.

        * Probes video duration via ffprobe (cached per call).
        * Extracts audio with ffmpeg (PCM 16-bit mono at 16 kHz).
        * Runs Silero VAD to get speech timestamps.
        * Ratio = total_speech_duration / video_total_duration.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist as a file.
        RuntimeError
            On audio extraction or VAD inference failure (with stderr detail).
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        self._ensure_model_loaded()
        duration = _probe_duration(path)

        # Zero / unknown duration → nothing to compute ratio against
        if duration is None or duration <= 0:
            return 0.0

        raw_audio = _extract_audio_bytes(path)
        if raw_audio is None:
            # No audio track or ffmpeg failed → no speech possible
            return 0.0

        tensor = _audio_bytes_to_tensor(raw_audio, duration)
        if tensor is None:
            return 0.0

        # Silero VAD returns list of {"start": ..., "end": ...} dicts
        import silero_vad  # type: ignore[import]

        speech_timestamps = silero_vad.get_speech_timestamps(
            tensor,
            self._model,  # type: ignore[arg-type]
            threshold=self._threshold,
            sampling_rate=16000,
            return_seconds=True,  # timestamps in seconds directly
        )

        total_speech = sum(
            ts["end"] - ts["start"] for ts in speech_timestamps
        )

        # Clamp ratio to [0, 1] (should always be in range but safety first)
        return min(1.0, max(0.0, total_speech / duration))
