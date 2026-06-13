"""Fake adapters for unit testing — no real external dependencies.

Exports:
    - FakeProbe (metadata probe)
    - FakeThumbnailMaker, FakeFrameExtractor (media adapters)
    - FakeSpeechDetector (speech detection adapter)
    - FakeTranscriber (transcription adapter)
    - FakeSummarizer (text summarization adapter)
    - FakeVisionTagger, make_sample_result (vision tagger for B-roll testing)
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
from .fake_summarizer import (
    FakeSummarizer,
    make_sample_summary,
)
from .fake_transcriber import (
    FakeTranscriber,
    make_sample_transcript,
)
from .fake_library import FakeLibraryWriter
from .omlx_vision import FakeVisionTagger, make_sample_result

__all__ = [
    "FakeFrameExtractor",
    "FakeLibraryWriter",
    "FakeProbe",
    "FakeSpeechDetector",
    "FakeSummarizer",
    "FakeTranscriber",
    "FakeVisionTagger",
    "make_sample",
    "make_sample_frame_paths",
    "make_sample_ratio",
    "make_sample_result",
    "make_sample_summary",
    "make_sample_thumbnail_path",
    "make_sample_transcript",
]
