"""FakeThumbnailMaker and FakeFrameExtractor — return pre-set image paths.

Useful in unit tests where you want to exercise the pipeline without
invoking ffmpeg or touching real video files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cutfinder.ports.media import FrameExtractor, ThumbnailMaker


class FakeThumbnailMaker(ThumbnailMaker):
    """A thumbnail maker that returns a predetermined path instead of calling ffmpeg.

    Parameters
    ----------
    output_path:
        The ``Path`` to return from :meth:`make`.  Defaults to a temporary-lookalike.
    should_fail:
        When ``True``, :meth:`make` raises ``RuntimeError`` instead of returning.

    Examples
    --------
    >>> maker = FakeThumbnailMaker()
    >>> result = maker.make(Path("/fake/video.mp4"), Path("/out/thumb.jpg"))
    >>> assert result.is_absolute()
    """

    def __init__(
        self,
        output_path: Optional[Path] = None,
        should_fail: bool = False,
    ) -> None:
        self._output_path = output_path or Path("/tmp/fake_thumb.jpg")
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[tuple[Path, Path]] = []

    def make(self, path: Path, out_path: Path) -> Path:
        """Return the pre-set output path (or fail if configured to)."""
        self.calls.append((path, out_path))

        if self._should_fail:
            raise RuntimeError("FakeThumbnailMaker: simulated failure")

        return self._output_path.resolve()


class FakeFrameExtractor(FrameExtractor):
    """A frame extractor that returns a list of predetermined paths.

    Parameters
    ----------
    output_paths:
        List of ``Path`` objects to return from :meth:`extract`.  Defaults
        to three temporary-lookalike paths.
    should_fail:
        When ``True``, :meth:`extract` raises ``RuntimeError`` instead.

    Examples
    --------
    >>> extractor = FakeFrameExtractor()
    >>> frames = extractor.extract(Path("/fake/video.mp4"), 3)
    >>> assert len(frames) == 3
    """

    def __init__(
        self,
        output_paths: Optional[list[Path]] = None,
        should_fail: bool = False,
    ) -> None:
        self._output_paths = output_paths or [
            Path("/tmp/fake_frame_0000.png"),
            Path("/tmp/fake_frame_0001.png"),
            Path("/tmp/fake_frame_0002.png"),
        ]
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[tuple[Path, Optional[int]]] = []
        self.grab_calls: list[tuple[Path, float, Path]] = []

    def extract(self, path: Path, count: int | None = None) -> list[Path]:
        """Return the pre-set output paths (or fail if configured to)."""
        self.calls.append((path, count))

        if self._should_fail:
            raise RuntimeError("FakeFrameExtractor: simulated failure")

        return [p.resolve() for p in self._output_paths]

    def grab_at(self, path: Path, seconds: float, out_path: Path) -> Path:
        """Pretend to grab a frame at *seconds*; return the requested out_path."""
        self.grab_calls.append((path, seconds, out_path))
        if self._should_fail:
            raise RuntimeError("FakeFrameExtractor: simulated grab failure")
        return out_path


def make_sample_thumbnail_path() -> Path:
    """Return a typical sample thumbnail path for tests."""
    return Path("/tmp/thumbnails/sample_thumb.jpg")


def make_sample_frame_paths(count: int = 3) -> list[Path]:
    """Return a typical sample frame paths for B-roll analysis tests."""
    return [Path(f"/tmp/frames/frame_{i:04d}.png") for i in range(count)]
