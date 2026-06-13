"""Fake adapters for unit testing — no real external dependencies.

Exports:
    - FakeProbe (metadata probe)
    - FakeThumbnailMaker, FakeFrameExtractor (media adapters)
"""

from .fake_media import (
    FakeFrameExtractor,
    FakeThumbnailMaker,
    make_sample_frame_paths,
    make_sample_thumbnail_path,
)
from .fake_probe import FakeProbe, make_sample

__all__ = [
    "FakeFrameExtractor",
    "FakeProbe",
    "FakeThumbnailMaker",
    "make_sample",
    "make_sample_frame_paths",
    "make_sample_thumbnail_path",
]
