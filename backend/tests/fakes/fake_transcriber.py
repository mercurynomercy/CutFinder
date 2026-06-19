"""FakeTranscriber — return a preset Transcript for unit testing.

Useful in tests that exercise the pipeline without invoking mlx-whisper
(no real audio processing).

Examples
--------
>>> transcriber = FakeTranscriber()
>>> transcript = transcriber.transcribe(Path("/fake/video.mp4"))  # noqa: D100
>>> assert transcript.full_text == "default Chinese text"

Tracker for call assertions in tests:

    calls :: list[tuple[Path]]
        List of ``(path,)`` tuples recorded on each :meth:`transcribe` call.

    languages :: list[str | None]
        The ``language`` hint passed on each :meth:`transcribe` call.
"""

from __future__ import annotations

from pathlib import Path

from cutfinder.domain.models import Segment, Transcript
from cutfinder.ports.speech import Transcriber


class FakeTranscriber(Transcriber):
    """A transcriber that returns a predetermined Transcript.

    Parameters
    ----------
    full_text:
        The ``full_text`` to return from :meth:`transcribe`. Defaults
        to ``"这是一段中文测试文本。"``, a short Chinese sentence.
    segments:
        List of :class:`Segment` objects to include. Defaults to a single
        segment covering the whole duration.
    should_fail:
        When ``True``, :meth:`transcribe` raises ``RuntimeError`` instead.

    Examples
    --------
    >>> transcriber = FakeTranscriber()
    >>> transcript = transcriber.transcribe(Path("/fake/video.mp4"))  # noqa: D100
    >>> assert transcript.full_text == "这是一段中文测试文本。"

    """

    def __init__(
        self,
        full_text: str = "这是一段中文测试文本。",
        segments: list[Segment] | None = None,
        should_fail: bool = False,
    ) -> None:
        self._full_text = full_text
        self._segments = segments or [Segment(start_s=0.0, end_s=5.0, text=full_text)]
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[tuple[Path]] = []
        self.languages: list[str | None] = []

    def transcribe(self, path: Path, *, language: str | None = None) -> Transcript:
        """Return the pre-set transcript (or fail if configured to)."""
        self.calls.append((path,))
        self.languages.append(language)

        if self._should_fail:
            raise RuntimeError("FakeTranscriber: simulated failure")

        return Transcript(full_text=self._full_text, segments=list(self._segments))


def make_sample_transcript() -> Transcript:
    """Return a sample :class:`Transcript` for tests."""
    return FakeTranscriber().transcribe(Path("/fake/sample.mp4"))
