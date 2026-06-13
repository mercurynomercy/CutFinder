"""Summarizer and VisionTagger — AI model adapters (OMLX).

Both protocols target the same OMLX server but use different models
and message formats (text vs vision / base64 frames).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..domain.models import SummaryResult, VisionResult


class Summarizer(Protocol):
    """Generate a Chinese summary + tags from A-roll transcript text (via OMLX)."""

    def summarize(self, transcript_text: str) -> SummaryResult:
        """Summarise *transcript_text* and return structured tags."""


class VisionTagger(Protocol):
    """Generate a visual description + tags from B-roll frames (via OMLX)."""

    def describe(self, frame_paths: list[Path]) -> VisionResult:
        """Send *frame_paths* (as base64) to the vision model and return results."""
