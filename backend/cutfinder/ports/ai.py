"""Summarizer and VisionTagger — AI model adapters (OpenAI-compatible server).

Both protocols target the same OpenAI-compatible server but use different
models and message formats (text vs vision / base64 frames).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..domain.models import CutSuggestion, Segment, SummaryResult, VisionResult


class Summarizer(Protocol):
    """Generate a Chinese summary + tags from A-roll transcript text (via an OpenAI-compatible server)."""

    def summarize(self, transcript_text: str) -> SummaryResult:
        """Summarise *transcript_text* and return structured tags."""

    def recommend_cuts(self, segments: list[Segment], n: int) -> list[CutSuggestion]:
        """Pick up to *n* best cut windows from timed transcript segments (A-roll).

        The model chooses by segment index; the adapter maps the chosen indices
        back to ``start_s``/``end_s``.  Returned suggestions have ``frame_path``
        unset (the caller grabs the representative frame).
        """


class VisionTagger(Protocol):
    """Generate a visual description + tags from B-roll frames (via an OpenAI-compatible server)."""

    def describe(self, frame_paths: list[Path]) -> VisionResult:
        """Send *frame_paths* (as base64) to the vision model and return results."""

    def recommend_keyframes(
        self, frames: list[tuple[Path, float]], n: int,
    ) -> list[CutSuggestion]:
        """Pick up to *n* best frames from sampled ``(frame_path, timestamp_s)`` pairs (B-roll).

        Each returned suggestion's ``frame_path`` is the chosen sampled frame;
        the caller sets the cut window around it.
        """
