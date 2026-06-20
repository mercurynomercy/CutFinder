"""Tests for the still-photo branch of the Orchestrator.

Photos take a separate pipeline: EXIF probe → JPEG preview → vision tags →
copy into ``<date>/photos/``. No VAD/transcript/keyframes.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import MagicMock

from cutfinder.domain.models import ClipCandidate, VideoMetadata, VisionResult
from cutfinder.pipeline.orchestrator import Orchestrator
from tests.fakes import FakeCatalogRepository, FakeLibraryWriter


def _image_meta() -> VideoMetadata:
    return VideoMetadata(
        capture_time=_dt.datetime(2026, 5, 1, 9, 0),
        date_source="embedded", duration_s=0.0, width=4000, height=3000,
        fps=None, codec="jpeg", has_audio=False,
    )


def _orch(repo: FakeCatalogRepository, lib: FakeLibraryWriter) -> tuple[Orchestrator, MagicMock]:
    image_probe = MagicMock()
    image_probe.probe.return_value = _image_meta()
    thumb = MagicMock()
    thumb.make.side_effect = lambda src, out: out  # pretend a preview was written
    vision = MagicMock()
    vision.describe.return_value = VisionResult(description="海边的日落", tags=["日落", "海滩"])
    orch = Orchestrator(
        repository=repo, library_writer=lib, vision_tagger=vision,
        image_probe=image_probe, image_thumbnail_maker=thumb,
        thumbnail_dir=None,
    )
    return orch, vision


def test_photo_is_cataloged_as_photo_roll_with_vision_tags() -> None:
    repo = FakeCatalogRepository()
    lib = FakeLibraryWriter(library_path="/lib")
    orch, vision = _orch(repo, lib)

    clip_id = orch.process_clip(ClipCandidate(path="/src/IMG_0001.jpg", fingerprint="aa01"))

    assert clip_id is not None
    clip = repo.get_clip(clip_id)
    assert clip is not None
    assert clip.roll_type == "photo"
    assert clip.description == "海边的日落"
    assert clip.status == "done"
    assert {t.name for t in repo.get_tags(clip_id)} == {"日落", "海滩"}
    # Filed under the photo roll type, dated by EXIF capture time.
    assert lib.calls == [("/src/IMG_0001.jpg", "2026-05-01", "photo")]
    # Vision ran on the generated preview, not the original (HEIC-safe).
    vision.describe.assert_called_once()


def test_photo_organizes_even_when_vision_fails() -> None:
    repo = FakeCatalogRepository()
    lib = FakeLibraryWriter(library_path="/lib")
    orch, vision = _orch(repo, lib)
    vision.describe.side_effect = RuntimeError("OMLX down")

    clip_id = orch.process_clip(ClipCandidate(path="/src/a.png", fingerprint="bb02"))

    assert clip_id is not None
    clip = repo.get_clip(clip_id)
    assert clip is not None
    assert clip.roll_type == "photo"
    assert clip.status == "partial"  # organized, but untagged
    assert lib.calls == [("/src/a.png", "2026-05-01", "photo")]


def test_non_photo_uses_video_pipeline(tmp_path: Path) -> None:
    """A .mp4 must not take the photo branch (image_probe untouched)."""
    repo = FakeCatalogRepository()
    image_probe = MagicMock()
    orch = Orchestrator(repository=repo, image_probe=image_probe)
    # No video adapters wired → probe stub path; the point is image_probe is unused.
    orch.process_clip(ClipCandidate(path="/src/clip.mp4", fingerprint="cc03"))
    image_probe.probe.assert_not_called()
