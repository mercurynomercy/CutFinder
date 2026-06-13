"""MetadataProbe — probe video file metadata via ffprobe."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Protocol

from ..domain.models import VideoMetadata


class MetadataProbe(Protocol):
    """Extract metadata from a video file."""

    def probe(self, path: Path) -> VideoMetadata:
        """Probe a single video file and return its metadata.

        Raises ``FileNotFoundError`` if the path doesn't exist,
        or a descriptive exception on parse failure.
        """
