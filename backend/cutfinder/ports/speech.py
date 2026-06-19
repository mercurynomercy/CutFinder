"""SpeechDetector and Transcriber — speech detection & transcription adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from ..domain.models import Transcript


class SpeechDetector(Protocol):
    """Detect whether a video clip contains human speech (for A/B classification)."""

    def speech_ratio(self, path: Path) -> float:
        """Return a value in [0.0, 1.0] representing the fraction of speech."""


class VocalSeparator(Protocol):
    """Separate vocals from accompaniment (strip BGM before transcription)."""

    def isolate(
        self, path: Path, *, progress: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        """Return whisper-ready 16 kHz mono float32 vocals (accompaniment removed).

        *progress* is an optional callback receiving separation progress as a
        0..1 fraction; when ``None`` no progress is reported (default behaviour).
        """


class Transcriber(Protocol):
    """Transcribe spoken audio in a video file to text (A-roll only)."""

    def transcribe(
        self,
        path: Path,
        *,
        language: str | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """Transcribe the audio track of *path* into text + segments.

        *language* is an optional language hint (e.g. ``"zh"`` / ``"en"``);
        when ``None`` the implementation falls back to its configured default.
        *progress* is an optional callback receiving overall progress as a
        0..1 fraction; when ``None`` no progress is reported.
        """
