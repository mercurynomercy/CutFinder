"""Fake adapters for unit testing — no real external dependencies.

Exports:
    - FakeProbe (metadata probe)
    - FakeThumbnailMaker, FakeFrameExtractor (media adapters)
    - FakeSpeechDetector (speech detection adapter)
    - FakeTranscriber (transcription adapter)
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
from .fake_transcriber import (
    FakeTranscriber,
    make_sample_transcript,
)

__all__ = [
    "FakeFrameExtractor",
    "FakeProbe",
    "FakeSpeechDetector",
    "FakeTranscriber",
    "make_sample",
    "make_sample_frame_paths",
    "make_sample_ratio",
    "make_sample_thumbnail_path",
    "make_sample_transcript",
]
