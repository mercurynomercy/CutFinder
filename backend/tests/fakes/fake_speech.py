"""FakeSpeechDetector — return a preset speech ratio for unit testing.

Useful in tests that exercise the pipeline without invoking ffmpeg or
Silero VAD (no real audio processing).

Examples
--------
>>> detector = FakeSpeechDetector(ratio=0.7)
>>> ratio = detector.speech_ratio(Path("/fake/video.mp4"))  # noqa: D100
>>> assert ratio == 0.7
"""

from __future__ import annotations

from pathlib import Path

from cutfinder.ports.speech import SpeechDetector


class FakeSpeechDetector(SpeechDetector):
    """A speech detector that returns a predetermined ratio.

    Parameters
    ----------
    ratio:
        The speech fraction to return from :meth:`speech_ratio`.  Defaults
        to ``0.5`` (half the audio is speech).
    should_fail:
        When ``True``, :meth:`speech_ratio` raises ``RuntimeError`` instead.

    Examples
    --------
    >>> detector = FakeSpeechDetector()
    >>> ratio = detector.speech_ratio(Path("/fake/video.mp4"))  # noqa: D100
    >>> assert ratio == 0.5

    Tracker for call assertions in tests:

        calls :: list[tuple[Path]]
            List of ``(path,)`` tuples recorded on each :meth:`speech_ratio` call.
    """

    def __init__(
        self,
        ratio: float = 0.5,
        should_fail: bool = False,
    ) -> None:
        self._ratio = ratio
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[tuple[Path]] = []

    def speech_ratio(self, path: Path) -> float:
        """Return the pre-set ratio (or fail if configured to)."""
        self.calls.append((path,))

        if self._should_fail:
            raise RuntimeError("FakeSpeechDetector: simulated failure")

        return self._ratio


def make_sample_ratio() -> float:
    """Return a typical sample speech ratio for tests."""
    return 0.5
