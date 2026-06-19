"""FakeVocalSeparator — return a preset vocals array for unit testing.

Useful in tests that exercise the transcriber's separation path without
invoking Demucs (no real audio processing).

Tracker for call assertions in tests:

    calls :: list[tuple[Path]]
        List of ``(path,)`` tuples recorded on each :meth:`isolate` call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from cutfinder.ports.speech import VocalSeparator


class FakeVocalSeparator(VocalSeparator):
    """A separator that returns a predetermined vocals array.

    Parameters
    ----------
    audio:
        The float32 array to return from :meth:`isolate`. Defaults to a
        short ramp of 16 samples.
    should_fail:
        When ``True``, :meth:`isolate` raises ``RuntimeError`` instead.
    """

    def __init__(
        self,
        audio: np.ndarray | None = None,
        should_fail: bool = False,
    ) -> None:
        if audio is None:
            audio = np.linspace(-0.5, 0.5, 16, dtype=np.float32)
        self._audio = audio
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[tuple[Path]] = []
        self.progress_callbacks: list[Callable[[float], None] | None] = []

    def isolate(
        self, path: Path, *, progress: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        """Return the pre-set vocals array (or fail if configured to).

        When a *progress* callback is given, reports completion (``1.0``) so
        tests can verify the separation phase weighting.
        """
        self.calls.append((path,))
        self.progress_callbacks.append(progress)

        if self._should_fail:
            raise RuntimeError("FakeVocalSeparator: simulated failure")

        if progress is not None:
            progress(1.0)

        return self._audio
