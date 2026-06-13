"""FakeProbe — returns fixed VideoMetadata for testing.

Useful in unit tests where you want to exercise the code path without
invoking ffprobe or touching real video files.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Optional

from cutfinder.domain.models import VideoMetadata
from cutfinder.ports.probe import MetadataProbe


class FakeProbe(MetadataProbe):
    """A probe that always returns the same ``VideoMetadata``.

    Parameters
    ----------
    capture_time:
        ISO 8601 datetime string or ``datetime`` object for the clip's
        capture time.  When omitted (None), date_source is "file".
    duration_s:
        Duration in seconds.  Default ``10.0``.
    width, height:
        Video dimensions in pixels.  Default ``1920`` / ``1080``.
    fps:
        Frames per second as a float.  Default ``29.97``.
    codec:
        Codec name string (e.g. ``"h264"``).  Default ``"h264"``.
    has_audio:
        Whether the clip contains an audio stream.  Default ``True``.

    Examples
    --------
    >>> probe = FakeProbe(capture_time="2026-04-25T03:24:44+00:00")
    >>> meta = probe.probe(Path("/dev/null"))  # path is ignored
    >>> assert meta.has_audio is True
    """

    def __init__(
        self,
        capture_time: Optional[str | _dt.datetime] = None,
        duration_s: float = 10.0,
        width: int = 1920,
        height: int = 1080,
        fps: float = 29.97,
        codec: str = "h264",
        has_audio: bool = True,
    ) -> None:
        # Normalise capture_time to datetime | None
        if isinstance(capture_time, str):
            self._capture_time: Optional[_dt.datetime] = _dt.datetime.fromisoformat(
                capture_time
            )
        elif isinstance(capture_time, _dt.datetime):
            self._capture_time = capture_time
        else:
            self._capture_time = None

        self._duration_s = duration_s
        self._width = width
        self._height = height
        self._fps = fps
        self._codec = codec
        self._has_audio = has_audio

    def probe(self, path: Path) -> VideoMetadata:
        """Return the fixed ``VideoMetadata`` configured at construction time."""
        capture_time = self._capture_time
        date_source: str = "embedded" if capture_time else "file"

        return VideoMetadata(
            capture_time=capture_time,
            date_source=date_source,
            duration_s=self._duration_s,
            width=self._width,
            height=self._height,
            fps=self._fps,
            codec=self._codec,
            has_audio=self._has_audio,
        )


def make_sample() -> VideoMetadata:
    """Return a typical A-roll-ish metadata record for tests."""

    return VideoMetadata(
        capture_time=_dt.datetime(2026, 4, 25, 3, 24, 44, tzinfo=_dt.timezone.utc),
        date_source="embedded",
        duration_s=19.085733,
        width=1920,
        height=1080,
        fps=round(30000 / 1001, 4),
        codec="h264",
        has_audio=True,
    )
