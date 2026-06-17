"""ThumbnailMaker and FrameExtractor — video media adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ThumbnailMaker(Protocol):
    """Generate a single representative-frame thumbnail from a video."""

    def make(self, path: Path, out_path: Path) -> Path:
        """Render a thumbnail image for *path*, writing it to *out_path*.

        Returns the absolute path of the written file.
        """


class FrameExtractor(Protocol):
    """Extract multiple evenly-sampled frames from a video (for B-roll analysis)."""

    def extract(self, path: Path, count: int) -> list[Path]:
        """Extract *count* frames evenly spaced across the video duration.

        Returns a list of paths to the written frame images (PNG).
        """

    def grab_at(self, path: Path, seconds: float, out_path: Path) -> Path:
        """Grab a single frame at *seconds* into *path*, writing it to *out_path*.

        Used to capture a representative frame for a keyframe suggestion.
        Returns the absolute path of the written image.
        """
