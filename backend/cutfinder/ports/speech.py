"""SpeechDetector and Transcriber — speech detection & transcription adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..domain.models import Transcript


class SpeechDetector(Protocol):
    """Detect whether a video clip contains human speech (for A/B classification)."""

    def speech_ratio(self, path: Path) -> float:
        """Return a value in [0.0, 1.0] representing the fraction of speech."""


class Transcriber(Protocol):
    """Transcribe spoken audio in a video file to text (A-roll only)."""

    def transcribe(self, path: Path, *, language: str | None = None) -> Transcript:
        """Transcribe the audio track of *path* into text + segments.

        *language* is an optional language hint (e.g. ``"zh"`` / ``"en"``);
        when ``None`` the implementation falls back to its configured default.
        """
