"""CatalogBrollInspector — live visual check of a B-roll clip.

Samples frames from the clip's video and sends them to the vision model
(Qwen3-VL) so the director can confirm what's actually on screen when stored
text metadata isn't enough. Read-only; any failure returns ``None`` so the
loop falls back to text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..domain.models import VisionResult
from ..ports.ai import VisionTagger
from ..ports.media import FrameExtractor
from ..ports.repository import CatalogRepository

logger = logging.getLogger(__name__)


class CatalogBrollInspector:
    """:class:`BrollInspector` using ffmpeg frame extraction + the vision model."""

    def __init__(
        self,
        repository: CatalogRepository,
        frame_extractor: FrameExtractor,
        vision_tagger: VisionTagger,
        num_frames: int = 5,
    ) -> None:
        self._repo = repository
        self._frames = frame_extractor
        self._vision = vision_tagger
        self._num_frames = max(1, num_frames)

    def inspect_broll(self, clip_id: int) -> VisionResult | None:
        clip = self._repo.get_clip(clip_id)
        if clip is None:
            return None
        # Prefer the organised copy; fall back to the read-only original.
        path = clip.library_path or clip.source_path
        if not path or not Path(path).is_file():
            return None
        try:
            frames = self._frames.extract(Path(path), self._num_frames)
            if not frames:
                return None
            return self._vision.describe(frames)
        except Exception as exc:  # noqa: BLE001 — inspection is best-effort
            logger.warning("inspect_broll failed for clip %s: %s", clip_id, exc)
            return None
