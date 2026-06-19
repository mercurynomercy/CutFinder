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

import logging
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..domain.models import Segment, Transcript
from ..ports.speech import Transcriber, VocalSeparator
from ._progress import patch_tqdm

logger = logging.getLogger(__name__)

# Separation occupies [0, W] of overall progress; transcription [W, 1].
_SEPARATION_WEIGHT = 0.4


def _safe(cb: Callable[[float], None] | None, value: float) -> None:
    """Invoke *cb* with *value*, swallowing any error (never break transcription)."""
    if cb is None:
        return
    try:
        cb(value)
    except Exception:  # noqa: BLE001 — UI callback errors must not stop work
        pass


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
        Path to the Whisper MLX model or HuggingFace repo ID. Must be an
        MLX-format repo. Defaults to ``"mlx-community/whisper-large-v3-mlx"``.
    language:
        Language code for transcription. Defaults to ``"zh"`` (Chinese).

    Examples
    --------
    >>> transcriber = MlxWhisperTranscriber()  # default: large-v3, zh
    >>> transcript = transcriber.transcribe(Path("/path/to/video.mp4"))  # noqa: D100
    """

    def __init__(
        self,
        model: str = "mlx-community/whisper-large-v3-mlx",
        language: str = "zh",
        separator: VocalSeparator | None = None,
    ) -> None:
        self._model = model
        self._language = language
        self._separator = separator

    def transcribe(
        self,
        path: Path,
        *,
        language: str | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """Transcribe the audio track of *path* into text + segments.

        *language* overrides the configured default language for this call
        (used by the standalone subtitle export, which aligns to the chosen
        subtitle language). When ``None`` the constructor default is used.

        *progress* receives overall progress as a single 0..1 fraction. When a
        separator is configured, separation occupies ``[0, W]`` and
        transcription ``[W, 1]`` (``W = _SEPARATION_WEIGHT``); without one,
        transcription spans the whole ``[0, 1]``.

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

        w = _SEPARATION_WEIGHT

        # Optionally isolate vocals (strip BGM) before transcription.
        # On any failure, log and fall back to the raw audio extraction path.
        audio_array: np.ndarray | None = None
        if self._separator is not None:
            try:
                audio_array = self._separator.isolate(
                    path,
                    progress=(lambda f: _safe(progress, f * w)) if progress else None,
                )
            except Exception as exc:  # noqa: BLE001 — degrade gracefully to raw audio
                logger.warning(
                    "Vocal separation failed for %s, falling back to raw audio: %s", path, exc
                )
                audio_array = None

        if audio_array is None:
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

        lang = language or self._language

        def _run() -> Any:
            return mlx_whisper.transcribe(
                audio_array,
                path_or_hf_repo=self._model,
                language=lang,
                verbose=False,
                condition_on_previous_text=False,  # break repetition/hallucination chains
            )

        if progress is not None:
            # `mlx_whisper.transcribe` resolves to the FUNCTION (re-exported in
            # __init__), so reach the actual submodule that holds the tqdm
            # attribute via sys.modules and intercept it. Transcription maps to
            # the [W, 1] tail of overall progress.
            tmod = sys.modules["mlx_whisper.transcribe"]
            with patch_tqdm(tmod, lambda f: _safe(progress, w + f * (1 - w))):
                result = _run()
        else:
            result = _run()

        # Map result dict → Transcript domain model
        full_text = result.get("text", "") or ""

        segments_data: list[dict[str, object]] = result.get("segments", [])
        segments = [
            Segment(
                start_s=float(seg["start"]),  # type: ignore[arg-type]
                end_s=float(seg["end"]),      # type: ignore[arg-type]
                text=str(seg.get("text", "")),
            )
            for seg in segments_data
        ]

        return Transcript(full_text=full_text, segments=segments)
