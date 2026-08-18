"""Unit tests for Scanner — scan source folders, filter by extension, fingerprint and deduplicate.

Covers:
    - Extension whitelist filtering (case-insensitive)
    - Fingerprint computation correctness and stability
    - Skipping files whose fingerprint already exists in the repository
    - Same-content deduplication within a single scan pass
    - Hidden files / hidden directories are skipped
    - Non-existent source folders are silently ignored
    - Empty directories produce no candidates
    - Unreadable files are skipped gracefully

Run with:
    .venv/bin/python -m pytest tests/unit/test_scanner.py -v

Tracker: docs/tasks/10-scanner.md — all DoD items covered.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Dict  # noqa: F401 — kept for type hints

import pytest

from cutfinder.domain.models import ClipCandidate, VideoMetadata
from tests.fakes.fake_repository import FakeCatalogRepository
from cutfinder.pipeline.scanner import Scanner, _compute_fingerprint, _is_hidden


# ── Helpers ───────────────────────────────────────────────────────

def _write_file(dirpath: Path, name: str, content: bytes) -> Path:
    """Write *content* to ``dirpath/name`` and return the path."""

    fp = dirpath / name
    fp.write_bytes(content)
    return fp


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture()
def tmp_folder(tmp_path: Path) -> Path:
    """Return a temporary directory (tmp_path from pytest, used as source root)."""

    return tmp_path


@pytest.fixture()
def repo() -> FakeCatalogRepository:
    """Fresh in-memory fake repository for each test."""

    return FakeCatalogRepository()


@pytest.fixture()
def scanner(repo: FakeCatalogRepository) -> Scanner:
    """Scanner wired to the fake repository."""

    return Scanner(repo)


# ── _is_hidden tests ─────────────────────────────────────────────

class TestIsHidden:
    def test_root_is_not_hidden(self):
        assert _is_hidden(Path("/")) is False

    def test_normal_dir_not_hidden(self):
        assert _is_hidden(Path("foo/bar")) is False

    def test_dotfile_is_hidden(self):
        assert _is_hidden(Path(".gitignore")) is True

    def test_nested_dotfile_is_hidden(self):
        assert _is_hidden(Path("foo/.bar/baz")) is True

    def test_dotdir_is_hidden(self):
        assert _is_hidden(Path(".hidden/file.mp4")) is True


# ── _compute_fingerprint tests ───────────────────────────────────

class TestComputeFingerprint:
    def test_returns_64_char_hex(self, tmp_folder: Path):
        _write_file(tmp_folder, "f.bin", b"hello world")
        fp = _compute_fingerprint(tmp_folder / "f.bin")
        assert len(fp) == 64

    def test_deterministic(self, tmp_folder: Path):
        content = b"deterministic test data"
        _write_file(tmp_folder, "a.bin", content)
        fp1 = _compute_fingerprint(tmp_folder / "a.bin")
        fp2 = _compute_fingerprint(tmp_folder / "a.bin")
        assert fp1 == fp2

    def test_different_content_different_fp(self, tmp_folder: Path):
        _write_file(tmp_folder, "x.bin", b"content A")
        _write_file(tmp_folder, "y.bin", b"content B")
        assert _compute_fingerprint(tmp_folder / "x.bin") != \
               _compute_fingerprint(tmp_folder / "y.bin")

    def test_same_content_same_fp_across_files(self, tmp_folder: Path):
        payload = b"identical content for dedup test" * 100
        _write_file(tmp_folder, "a.bin", payload)
        _write_file(tmp_folder, "b.bin", payload)
        assert _compute_fingerprint(tmp_folder / "a.bin") == \
               _compute_fingerprint(tmp_folder / "b.bin")

    def test_includes_file_size(self, tmp_folder: Path):
        """Files of different sizes but same prefix content should differ."""

        _write_file(tmp_folder, "short.bin", b"abc")
        # A longer file starting with the same bytes.
        _write_file(tmp_folder, "long.bin", b"abc" + b"x" * 1000)
        assert _compute_fingerprint(tmp_folder / "short.bin") != \
               _compute_fingerprint(tmp_folder / "long.bin")

    def test_empty_file_has_fp(self, tmp_folder: Path):
        _write_file(tmp_folder, "empty.bin", b"")
        fp = _compute_fingerprint(tmp_folder / "empty.bin")
        assert len(fp) == 64


# ── Scanner.scan — extension whitelist tests ─────────────────────

class TestScanExtensionFilter:
    def test_only_includes_whitelist_extensions(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "a.mp4", b"fake mp4")
        _write_file(tmp_folder, "b.mov", b"fake mov")
        _write_file(tmp_folder, "c.txt", b"text file")  # excluded

        candidates = scanner.scan([tmp_folder], {".mp4", ".mov"})
        paths = [c.path for c in candidates]

        assert any("a.mp4" in p for p in paths)
        assert any("b.mov" in p for p in paths)
        assert not any("c.txt" in p for p in paths)

    def test_case_insensitive_extension(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "upper.MP4", b"data")
        _write_file(tmp_folder, "lower.mp4", b"data2")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 2

    def test_default_extensions_include_m4v(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "a.m4v", b"data")
        candidates = scanner.scan([tmp_folder])  # no extensions arg → default

        assert len(candidates) == 1
        assert "a.m4v" in candidates[0].path

    def test_no_files_match_extensions(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "readme.md", b"hi")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 0


# ── Scanner.scan — fingerprint deduplication against repository ───

class TestScanRepositoryDedup:
    def test_skips_existing_fingerprint(self, tmp_folder: Path, scanner: Scanner, repo: FakeCatalogRepository):
        fp = _compute_fingerprint(_write_file(tmp_folder, "clip.mp4", b"video data"))

        # Register the fingerprint in the repo as already processed.
        repo.add_fingerprint(fp)

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 0

    def test_allows_new_fingerprint(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "new.mp4", b"brand new content xyz")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 1


# ── Scanner.scan — same-content deduplication within a scan pass ─

class TestScanInternalDedup:
    def test_same_content_not_duplicated(self, tmp_folder: Path, scanner: Scanner):
        """Two files with identical content should yield only one candidate."""

        payload = b"identical video data for dedup test"
        _write_file(tmp_folder, "copy1.mp4", payload)
        _write_file(tmp_folder, "copy2.mp4", payload)

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 1

    def test_different_content_both_included(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "a.mp4", b"content A unique")
        _write_file(tmp_folder, "b.mp4", b"content B different")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 2


# ── Scanner.scan — hidden files / directories skipped ────────────

class TestScanHiddenFiles:
    def test_skips_hidden_files(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, ".hidden.mp4", b"data")
        _write_file(tmp_folder, "visible.mp4", b"other data")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 1

    def test_skips_files_inside_hidden_dir(self, tmp_folder: Path, scanner: Scanner):
        dotdir = tmp_folder / ".git"
        dotdir.mkdir()
        _write_file(dotdir, "clip.mp4", b"inside hidden dir")
        _write_file(tmp_folder, "ok.mp4", b"outside")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 1


# ── Scanner.scan — edge cases ───────────────────────────────────

class TestScanEdgeCases:
    def test_non_existent_folder_silently_skipped(self, tmp_folder: Path, scanner: Scanner):
        bogus = tmp_folder / "does_not_exist"

        candidates = scanner.scan([bogus], {".mp4"})
        assert len(candidates) == 0

    def test_empty_folder_produces_no_candidates(self, tmp_folder: Path, scanner: Scanner):
        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 0

    def test_multiple_folders(self, tmp_folder: Path, scanner: Scanner):
        sub1 = tmp_folder / "a"
        sub2 = tmp_folder / "b"
        sub1.mkdir()
        sub2.mkdir()

        _write_file(sub1, "one.mp4", b"data 1")
        _write_file(sub2, "two.mov", b"data 2")

        candidates = scanner.scan([sub1, sub2], {".mp4", ".mov"})
        assert len(candidates) == 2

    def test_unreadable_file_skipped(self, tmp_folder: Path, scanner: Scanner):
        fp = _write_file(tmp_folder, "locked.mp4", b"data")
        os.chmod(fp, 0o000)  # noqa: S103 — test only, will be restored

        try:
            scanner.scan([tmp_folder], {".mp4"})
            # Should not raise; file is simply skipped.
        finally:
            os.chmod(fp, 0o644)

    def test_returns_clip_candidate_instances(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "clip.mp4", b"sample")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        assert len(candidates) == 1
        assert isinstance(candidates[0], ClipCandidate)

    def test_candidate_has_path_and_fingerprint(self, tmp_folder: Path, scanner: Scanner):
        _write_file(tmp_folder, "clip.mp4", b"sample data")

        candidates = scanner.scan([tmp_folder], {".mp4"})
        c = candidates[0]

        assert "clip.mp4" in c.path
        assert len(c.fingerprint) == 64


# ── Scanner.scan — capture-time ordering ─────────────────────────

class _MapProbe:
    """Fake MetadataProbe returning a per-filename capture_time."""

    def __init__(self, times_by_filename: Dict[str, dt.datetime]) -> None:
        self._times = times_by_filename

    def probe(self, path: Path) -> VideoMetadata:
        return VideoMetadata(capture_time=self._times[path.name], date_source="embedded", duration_s=1.0)


class TestScanCaptureTimeOrdering:
    def test_sorts_candidates_by_capture_time_ascending(self, tmp_folder: Path, repo: FakeCatalogRepository):
        # Write the later-captured file first so filesystem/walk order would
        # produce the wrong (unsorted) order if capture-time sorting were absent.
        _write_file(tmp_folder, "A-0001.mp4", b"shot later, written first")
        _write_file(tmp_folder, "A-0002.mp4", b"shot earlier, written second")

        probe = _MapProbe({
            "A-0002.mp4": dt.datetime(2026, 8, 18, 9, 16, tzinfo=dt.timezone.utc),
            "A-0001.mp4": dt.datetime(2026, 8, 18, 9, 20, tzinfo=dt.timezone.utc),
        })
        scanner = Scanner(repo, probe=probe)

        candidates = scanner.scan([tmp_folder], {".mp4"})
        names = [Path(c.path).name for c in candidates]

        assert names == ["A-0002.mp4", "A-0001.mp4"]

    def test_probe_failure_does_not_crash_scan(self, tmp_folder: Path, repo: FakeCatalogRepository):
        """A probe that raises for one file should not abort the whole scan."""

        class _RaisingProbe:
            def probe(self, path: Path) -> VideoMetadata:
                raise RuntimeError("ffprobe exploded")

        _write_file(tmp_folder, "broken.mp4", b"corrupt")
        scanner = Scanner(repo, probe=_RaisingProbe())

        candidates = scanner.scan([tmp_folder], {".mp4"})

        assert len(candidates) == 1

    def test_photo_extensions_use_image_probe_for_ordering(self, tmp_folder: Path, repo: FakeCatalogRepository):
        """Photos are ordered using image_probe, not the video probe."""

        _write_file(tmp_folder, "photo_later.jpg", b"later photo, written first")
        _write_file(tmp_folder, "photo_earlier.jpg", b"earlier photo, written second")

        image_probe = _MapProbe({
            "photo_later.jpg": dt.datetime(2026, 8, 18, 10, 0, tzinfo=dt.timezone.utc),
            "photo_earlier.jpg": dt.datetime(2026, 8, 18, 8, 0, tzinfo=dt.timezone.utc),
        })
        scanner = Scanner(repo, image_probe=image_probe, photo_extensions={".jpg"})

        candidates = scanner.scan([tmp_folder], {".jpg"})
        names = [Path(c.path).name for c in candidates]

        assert names == ["photo_earlier.jpg", "photo_later.jpg"]

    def test_mixed_naive_and_aware_capture_times_do_not_crash(
        self, tmp_folder: Path, repo: FakeCatalogRepository
    ):
        """Video probes return tz-aware capture_time; PillowImageProbe returns
        naive capture_time (both EXIF and its file-time fallback are naive).
        Sorting a folder with both video and photo candidates must not raise
        TypeError from comparing naive vs. aware datetimes.
        """

        class _NaivePhotoProbe:
            def probe(self, path: Path) -> VideoMetadata:
                return VideoMetadata(
                    capture_time=dt.datetime(2026, 8, 18, 9, 0),  # naive, like PillowImageProbe
                    date_source="file",
                    duration_s=0.0,
                )

        _write_file(tmp_folder, "clip.mp4", b"video")
        _write_file(tmp_folder, "photo.jpg", b"photo")

        video_probe = _MapProbe({
            "clip.mp4": dt.datetime(2026, 8, 18, 9, 30, tzinfo=dt.timezone.utc),
        })
        scanner = Scanner(
            repo, probe=video_probe, image_probe=_NaivePhotoProbe(), photo_extensions={".jpg"},
        )

        candidates = scanner.scan([tmp_folder], {".mp4", ".jpg"})

        assert len(candidates) == 2

    def test_no_probe_injected_falls_back_to_birthtime(
        self, tmp_folder: Path, repo: FakeCatalogRepository, monkeypatch: pytest.MonkeyPatch
    ):
        """With no probes injected at all, ordering falls back directly to
        filesystem birth time and stays deterministic (no crash, no None-vs-
        datetime comparison error)."""

        _write_file(tmp_folder, "later.mp4", b"later")
        _write_file(tmp_folder, "earlier.mp4", b"earlier")

        birthtimes = {
            "later.mp4": dt.datetime(2026, 8, 18, 9, 30, tzinfo=dt.timezone.utc).timestamp(),
            "earlier.mp4": dt.datetime(2026, 8, 18, 9, 0, tzinfo=dt.timezone.utc).timestamp(),
        }
        real_stat = Path.stat

        class _FakeStat:
            def __init__(self, real_result: Any, birthtime: float) -> None:
                self._real = real_result
                self.st_birthtime = birthtime

            def __getattr__(self, name: str) -> Any:
                return getattr(self._real, name)

        def fake_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
            result = real_stat(self, *args, **kwargs)
            if self.name not in birthtimes:
                return result
            return _FakeStat(result, birthtimes[self.name])

        monkeypatch.setattr(Path, "stat", fake_stat)

        scanner = Scanner(repo)  # no probe, no image_probe
        candidates = scanner.scan([tmp_folder], {".mp4"})
        names = [Path(c.path).name for c in candidates]

        assert names == ["earlier.mp4", "later.mp4"]
