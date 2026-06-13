"""Fake adapters for unit testing — no real external dependencies.

Exports:
    - FakeProbe (metadata probe)
    - FakeThumbnailMaker, FakeFrameExtractor (media adapters)
    - FakeSpeechDetector (speech detection adapter)
"""

from .fake_media import (
    FakeFrameExtractor,
    FakeThumbnailMaker,
    make_sample_frame_paths,
    make_sample_thumbnail_path,
)
from .fake_probe import FakeProbe, make_sample
from .fake_speech import (
    FakeSpeechDetector,
    make_sample_ratio,
)

__all__ = [
    "FakeFrameExtractor",
    "FakeProbe",
    "FakeSpeechDetector",
    "FakeThumbnailMaker",
    "make_sample",
    "make_sample_frame_paths",
    "make_sample_ratio",
    "make_sample_thumbnail_path",
]
