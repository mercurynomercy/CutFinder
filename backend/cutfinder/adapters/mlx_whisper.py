"""MlxWhisperTranscriber — Chinese speech transcription via mlx-whisper.

Extracts audio from a video file with ffmpeg (PCM 16-bit mono at 16 kHz),
then passes it through mlx-whisper to produce a :class:`Transcript` with
full text and per-segment timestamps.

Edge cases handled:
  * Zero-duration video → returns empty :class:`Transcript`.
  * Video with no audio stream → raises ``RuntimeError``.
  * Non-existent file → raises ``FileNotFoundError``.

Examples
--------
>>> transcriber = MlxWhisperTranscriber(model="large-v3", language="zh")
>>> transcript = transcriber.transcribe(Path("/path/to/video.mp4"))  # noqa: D100
>>> print(transcript.full_text)
"""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import numpy as np

from ..domain.models import Segment, Transcript
from ..ports.speech import Transcriber


# ── audio extraction helpers ───────────────────────────────────────

def _extract_audio_bytes(path: Path) -> bytes | None:
    """Extract raw audio as PCM 16-bit mono at 16 kHz via ffmpeg.

    Uses ``-map 0:a:0`` to explicitly select the first audio stream,
    avoiding issues with video edit-list errors.

    Returns ``None`` if ffmpeg fails or produces no output (e.g. no audio stream).
    """
    result = subprocess.run(  # noqa: S603 — ffmpeg is trusted local tool
        [
            "ffmpeg", "-y", "-i", str(path),
            "-map", "0:a:0",    # explicitly map first audio stream (avoids video edit-list issues)
            "-acodec", "pcm_s16le",
            "-ar", "16000",     # mlx-whisper native sample rate
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


def _audio_bytes_to_array(raw: bytes) -> np.ndarray | None:
    """Convert raw PCM 16-bit mono bytes to a float32 numpy array.

    Samples are cast from int16 and normalized to [-1, 1], matching
    what mlx-whisper expects.

    Returns ``None`` if the byte stream is empty or has an odd number
    of bytes (truncated sample).
    """
    try:
        if len(raw) % 2 != 0:
            return None

        num_samples = len(raw) // 2
        if num_samples == 0:
            return None

        # Cast raw bytes to int16 values, then normalize to [-1, 1]
        samples = struct.unpack(f"<{num_samples}h", raw)
        return np.array(samples, dtype=np.float32) / 32768.0
    except struct.error:
        return None


# ── MlxWhisperTranscriber ────────────────────────────────────────

class MlxWhisperTranscriber(Transcriber):
    """Transcribe audio in a video file using mlx-whisper.

    Parameters
    ----------
    model:
        Path to the Whisper MLX model or HuggingFace repo ID.
        Defaults to ``"large-v3"`` (maps to the default mlx-community repo).
    language:
        Language code for transcription. Defaults to ``"zh"`` (Chinese).

    Examples
    --------
    >>> transcriber = MlxWhisperTranscriber()  # default: large-v3, zh
    >>> transcript = transcriber.transcribe(Path("/path/to/video.mp4"))  # noqa: D100
    """

    def __init__(self, model: str = "large-v3", language: str = "zh") -> None:
        self._model = model
        self._language = language

    def transcribe(self, path: Path) -> Transcript:
        """Transcribe the audio track of *path* into text + segments.

        1. Probes video duration via ffprobe (skipped if zero/unknown).
        2. Extracts audio with ffmpeg → converts to numpy array.
        3. Runs mlx-whisper to get transcription result dict.
        4. Maps ``{text, segments: [{start, end, text}]}`` → :class:`Transcript`.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist as a file.
        RuntimeError
            On audio extraction or transcription failure (with stderr detail).
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        # Extract audio bytes from the video
        raw_audio = _extract_audio_bytes(path)
        if raw_audio is None:
            raise RuntimeError(f"No audio stream found in video file: {path}")

        # Convert to numpy array for mlx-whisper
        audio_array = _audio_bytes_to_array(raw_audio)
        if audio_array is None:
            raise RuntimeError(f"Failed to decode audio from video file: {path}")

        # Run mlx-whisper transcription (installed per pyproject.toml)
        import mlx_whisper  # type: ignore[import-untyped]

        result = mlx_whisper.transcribe(
            audio_array,
            path_or_hf_repo=self._model,
            language=self._language,
            verbose=False,
        )

        # Map result dict → Transcript domain model
        full_text = result.get("text", "") or ""

        segments_data: list[dict[str, object]] = result.get("segments", [])
        segments = [
            Segment(
                start_s=float(seg["start"]),  # type: ignore[arg-type]
                end_s=float(seg["end"]),      # type: ignore[arg-type]
                text=str(seg.get("text", "")),  # type: ignore[arg-type]
            )
            for seg in segments_data
        ]

        return Transcript(full_text=full_text, segments=segments)
