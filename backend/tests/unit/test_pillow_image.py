"""Tests for the Pillow-based photo adapters (probe + JPEG preview).

Skipped entirely when Pillow is not installed, so the suite stays green in
environments without it; when present, they exercise the real code paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")  # noqa: N816 — skip module if Pillow missing

from cutfinder.adapters.pillow_image import PillowImageProbe, PillowThumbnailMaker  # noqa: E402


def _make_jpeg(path: Path, size: tuple[int, int] = (1600, 1200)) -> None:
    from PIL import Image

    Image.new("RGB", size, (123, 222, 64)).save(path, format="JPEG")


def test_probe_reads_dimensions_and_falls_back_to_file_time(tmp_path: Path) -> None:
    img = tmp_path / "photo.jpg"
    _make_jpeg(img)

    meta = PillowImageProbe().probe(img)

    assert (meta.width, meta.height) == (1600, 1200)
    assert meta.duration_s == 0.0
    assert meta.has_audio is False
    # No EXIF DateTimeOriginal → file-time fallback, flagged for the UI.
    assert meta.date_source == "file"
    assert meta.capture_time is not None


def test_probe_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PillowImageProbe().probe(tmp_path / "nope.jpg")


def test_thumbnail_downscales_to_jpeg(tmp_path: Path) -> None:
    from PIL import Image

    img = tmp_path / "big.jpg"
    _make_jpeg(img, size=(4000, 3000))
    out = tmp_path / "thumbs" / "preview.jpg"

    result = PillowThumbnailMaker(max_px=512).make(img, out)

    assert result == out
    assert out.is_file()
    with Image.open(out) as t:
        assert max(t.size) <= 512
        assert t.format == "JPEG"
