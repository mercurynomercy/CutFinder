"""Pillow-based adapters for still photos (probe + JPEG preview).

Photos are not video, so ffprobe/ffmpeg are a poor fit (and HEIC needs libheif
anyway). These adapters use Pillow — with ``pillow-heif`` registered for HEIC —
to read image dimensions + EXIF capture time and to render a JPEG preview that
doubles as the thumbnail and the vision-model input.

Pillow is imported lazily inside methods so the rest of the app (and the test
suite, which injects fakes) does not require it to be installed.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any

from ..domain.models import VideoMetadata

logger = logging.getLogger(__name__)

# EXIF tag ids (avoid importing PIL at module load just for these constants).
_EXIF_DATETIME_ORIGINAL = 36867  # DateTimeOriginal
_EXIF_DATETIME = 306             # DateTime (fallback)


def _register_heif() -> None:
    """Register the HEIF/HEIC opener with Pillow if pillow-heif is available."""
    try:
        import pillow_heif  # type: ignore[import-untyped]

        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001 — HEIC just won't be supported without it
        pass


def _parse_exif_datetime(value: str | None) -> _dt.datetime | None:
    """Parse an EXIF datetime string (``"YYYY:MM:DD HH:MM:SS"``) to datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        return _dt.datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


class PillowImageProbe:
    """Read photo dimensions + EXIF capture time into a :class:`VideoMetadata`.

    ``duration_s`` is 0 and ``has_audio`` is False for stills. When EXIF carries
    no capture time, falls back to the file's creation/modification time and sets
    ``date_source="file"`` (surfaced in the UI), mirroring the video probe.
    """

    def probe(self, path: Path) -> VideoMetadata:
        from PIL import Image  # lazy

        _register_heif()
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file does not exist: {path}")

        with Image.open(path) as img:
            width, height = img.size
            fmt = (img.format or path.suffix.lstrip(".")).lower()
            capture_time = self._read_exif_time(img)

        date_source = "embedded" if capture_time is not None else "file"
        if capture_time is None:
            try:
                st = path.stat()
                ts = getattr(st, "st_birthtime", None) or st.st_mtime
                capture_time = _dt.datetime.fromtimestamp(ts)
            except OSError:
                pass

        return VideoMetadata(
            capture_time=capture_time,
            date_source=date_source,
            duration_s=0.0,
            width=width,
            height=height,
            fps=None,
            codec=fmt,
            has_audio=False,
        )

    @staticmethod
    def _read_exif_time(img: Any) -> _dt.datetime | None:
        """Return the EXIF DateTimeOriginal (or DateTime) of an open image."""
        getexif = getattr(img, "getexif", None)
        if not callable(getexif):
            return None
        try:
            exif: Any = getexif()
        except Exception:  # noqa: BLE001 — corrupt EXIF must not break cataloguing
            return None
        if not exif:
            return None
        raw = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        return _parse_exif_datetime(raw if isinstance(raw, str) else None)


class PillowThumbnailMaker:
    """Render a downscaled JPEG preview of a photo (thumbnail + vision input)."""

    def __init__(self, max_px: int = 1024) -> None:
        self._max_px = max_px

    def make(self, path: Path, out_path: Path) -> Path:
        from PIL import Image  # lazy

        _register_heif()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            rgb.thumbnail((self._max_px, self._max_px))
            rgb.save(out_path, format="JPEG", quality=85)
        return out_path


__all__ = ["PillowImageProbe", "PillowThumbnailMaker"]
