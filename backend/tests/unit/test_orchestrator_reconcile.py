"""Tests for Orchestrator library reconciliation (sync-delete).

Covers ``find_orphaned_clips`` (catalog rows whose library copy vanished) and
``delete_clips`` (remove rows + on-disk thumbnail/keyframe files, never source).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from cutfinder.domain.models import Clip
from cutfinder.pipeline.orchestrator import Orchestrator
from tests.fakes import FakeCatalogRepository


def _now() -> _dt.datetime:
    return _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)


def _clip(**over: Any) -> Clip:
    defaults: dict[str, Any] = dict(
        id=None, fingerprint="fp", source_path="/src/a.mp4", roll_type="a",
        status="done", created_at=_now(),
    )
    defaults.update(over)
    return Clip(**defaults)


def test_find_orphaned_clips_flags_only_missing_copies(tmp_path: Path) -> None:
    repo = FakeCatalogRepository()
    present = tmp_path / "present.mp4"
    present.write_bytes(b"x")

    kept = repo.upsert_clip(_clip(fingerprint="keep", source_path="/src/keep.mp4",
                                  library_path=str(present)))
    gone = repo.upsert_clip(_clip(fingerprint="gone", source_path="/src/gone.mp4",
                                  library_path=str(tmp_path / "deleted.mp4")))

    orch = Orchestrator(repository=repo)
    orphans = orch.find_orphaned_clips()

    ids = {s.id for s in orphans}
    assert ids == {gone}
    assert kept not in ids


def test_delete_clips_removes_row_and_derived_files(tmp_path: Path) -> None:
    repo = FakeCatalogRepository()
    thumb = tmp_path / "thumbs" / "fp.jpg"
    thumb.parent.mkdir(parents=True)
    thumb.write_bytes(b"thumb")
    keyframe_dir = tmp_path / "keyframes"
    cid = repo.upsert_clip(_clip(library_path=str(tmp_path / "x.mp4"),
                                 thumbnail_path=str(thumb)))
    (keyframe_dir / str(cid)).mkdir(parents=True)
    (keyframe_dir / str(cid) / "k1.jpg").write_bytes(b"frame")

    orch = Orchestrator(repository=repo, keyframe_dir=keyframe_dir)
    deleted = orch.delete_clips([cid])

    assert deleted == 1
    assert repo.get_clip(cid) is None
    assert not thumb.exists()
    assert not (keyframe_dir / str(cid)).exists()


def test_delete_clips_skips_unknown_ids(tmp_path: Path) -> None:
    repo = FakeCatalogRepository()
    orch = Orchestrator(repository=repo, keyframe_dir=tmp_path)
    assert orch.delete_clips([999]) == 0
