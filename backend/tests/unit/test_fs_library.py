"""Unit tests for FsLibraryWriter — real file copy in temp directories.

Tests verify:
  - Original files are never modified (mtime, content).
  - Copies are renamed sequentially: ``<library>/<date>/A-roll/A-0001.<ext>`` etc.
  - Numbering increments per date/type folder and never overwrites.
  - mtime/atime are preserved after copy (shutil.copy2).
  - File size is verified after copy; mismatch raises ``OSError``.

Run with:
    .venv/bin/python -m pytest tests/unit/test_fs_library.py -v
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cutfinder.adapters.fs_library import FsLibraryWriter
from cutfinder.config import AppConfig, EnvSettings, Prefs

# Import fake directly (avoid triggering fakes/__init__.py which has
# relative imports that fail when imported from a test module).
import importlib as _importlib
import sys as _sys
from pathlib import Path as _Path

_fake_lib = str(_Path(__file__).parent.parent / "fakes" / "fake_library.py")
_spec = _importlib.util.spec_from_file_location("fake_lib", _fake_lib)  # noqa: F821
_fake_mod = _importlib.util.module_from_spec(_spec)  # noqa: F821
_sys.modules["fake_lib"] = _fake_mod
_spec.loader.exec_module(_fake_mod)  # type: ignore[union-attr]
FakeLibraryWriter = _fake_mod.FakeLibraryWriter  # type: ignore[union-attr, name-defined]


def _make_config(tmp_path: Path) -> AppConfig:
    """Create an AppConfig pointing at *tmp_path* as the library root."""
    return AppConfig(
        env=EnvSettings(OMLX_BASE_URL="http://localhost:1235/v1", OMLX_API_KEY="test-key"),
        prefs=Prefs(library_path=str(tmp_path)),
    )


def _make_src_file(
    tmp_path: Path, name: str = "test.mp4", content: bytes | None = None
) -> Path:
    """Create a small source file in *tmp_path* and return its path."""
    src = tmp_path / name
    data = content if content is not None else b"0123456789ABCDEF"
    src.write_bytes(data)
    # Set a known mtime (Jan 15, 2024, 10:30 UTC)
    known_ts = 1705312200.0
    os.utime(src, (known_ts, known_ts))
    return src


# ─── Basic copy tests ──────────────────────────────────────────────

class TestCopyInto:
    """Verify basic copy behavior."""

    def test_copy_to_new_path(self, tmp_path):
        """A new A-roll file is renamed to A-0001 in the date/type directory."""
        src = _make_src_file(tmp_path, "clip.mp4")
        writer = FsLibraryWriter(_make_config(tmp_path))

        dest_str = writer.copy_into(src, "2024-01-15", "a")
        dest = Path(dest_str)

        assert dest == tmp_path / "2024-01-15" / "A-roll" / "A-0001.mp4"
        assert dest.exists()

    def test_copy_b_roll(self, tmp_path):
        """B-roll is renamed to B-0001 in the B-roll subdirectory."""
        src = _make_src_file(tmp_path, "broll.mov")
        writer = FsLibraryWriter(_make_config(tmp_path))

        dest_str = writer.copy_into(src, "2024-03-20", "b")
        dest = Path(dest_str)

        assert dest == tmp_path / "2024-03-20" / "B-roll" / "B-0001.mov"
        assert dest.exists()

    def test_directories_created_auto(self, tmp_path):
        """Target directories are auto-created even if they don't exist yet."""
        src = _make_src_file(tmp_path, "deep.mp4")
        writer = FsLibraryWriter(_make_config(tmp_path))

        # Date that doesn't exist yet
        dest_str = writer.copy_into(src, "2099-12-31", "a")
        assert Path(dest_str).exists()

    def test_original_file_unchanged_content(self, tmp_path):
        """Original file content is never modified after copy."""
        original_data = b"original-content-12345"
        src = _make_src_file(tmp_path, "unchanged.mp4", content=original_data)
        writer = FsLibraryWriter(_make_config(tmp_path))

        _ = writer.copy_into(src, "2024-06-01", "a")

        assert src.read_bytes() == original_data

    def test_original_file_unchanged_mtime(self, tmp_path):
        """Original file mtime is preserved (not touched by copy)."""
        known_ts = 1705312200.0
        src = _make_src_file(tmp_path, "mtime.mp4")

        # Verify known_ts was set
        assert os.path.getmtime(src) == known_ts

        writer = FsLibraryWriter(_make_config(tmp_path))
        _ = writer.copy_into(src, "2024-01-15", "a")

        # mtime should remain the same
        assert os.path.getmtime(src) == known_ts

    def test_copy_preserves_mtime(self, tmp_path):
        """shutil.copy2 preserves mtime on the destination file."""
        known_ts = 1705312200.0
        src = _make_src_file(tmp_path, "preserved.mp4")

        writer = FsLibraryWriter(_make_config(tmp_path))
        dest_str = writer.copy_into(src, "2024-01-15", "a")
        dest = Path(dest_str)

        assert os.path.getmtime(dest) == known_ts

    @pytest.mark.skipif(
        sys.platform != "darwin", reason="birth time is only settable on macOS",
    )
    def test_copy_preserves_creation_time(self, tmp_path):
        """The copy's creation (birth) time matches the source on macOS."""
        from cutfinder.adapters.fs_library import _set_birthtime

        src = _make_src_file(tmp_path, "birth.mp4")
        # Backdate the source's creation time to 90 days ago so it differs
        # from "now" (the copy moment) — otherwise the test can't distinguish.
        old_birth = 1705312200.0  # Jan 15, 2024
        _set_birthtime(src, old_birth)
        assert abs(src.stat().st_birthtime - old_birth) < 1

        writer = FsLibraryWriter(_make_config(tmp_path))
        dest = Path(writer.copy_into(src, "2024-01-15", "a"))

        assert abs(dest.stat().st_birthtime - old_birth) < 1


# ─── Sequential naming tests ───────────────────────────────────────

class TestSequentialNaming:
    """Verify copies are renamed A-0001/B-0001… per date/type folder."""

    def test_second_copy_increments(self, tmp_path):
        """A second A-roll copy in the same folder becomes A-0002."""
        writer = FsLibraryWriter(_make_config(tmp_path))

        src1 = _make_src_file(tmp_path, "first.mp4", content=b"first")
        src2 = _make_src_file(tmp_path, "second.mp4", content=b"second")

        dest1 = Path(writer.copy_into(src1, "2024-01-15", "a"))
        dest2 = Path(writer.copy_into(src2, "2024-01-15", "a"))

        assert dest1.name == "A-0001.mp4"
        assert dest2.name == "A-0002.mp4"
        assert dest1.read_bytes() == b"first"
        assert dest2.read_bytes() == b"second"

    def test_numbering_is_per_date_and_type(self, tmp_path):
        """Each date/type folder gets its own independent A-0001/B-0001 sequence."""
        writer = FsLibraryWriter(_make_config(tmp_path))
        src = _make_src_file(tmp_path, "clip.mp4")

        a_day1 = Path(writer.copy_into(src, "2024-01-15", "a"))
        b_day1 = Path(writer.copy_into(src, "2024-01-15", "b"))
        a_day2 = Path(writer.copy_into(src, "2024-01-16", "a"))

        assert a_day1.name == "A-0001.mp4"
        assert b_day1.name == "B-0001.mp4"   # B-roll counts separately
        assert a_day2.name == "A-0001.mp4"   # new date resets

    def test_resumes_after_existing_files(self, tmp_path):
        """Numbering continues from the highest existing index (re-scan safe)."""
        lib_dir = tmp_path / "2024-01-15" / "A-roll"
        lib_dir.mkdir(parents=True)
        (lib_dir / "A-0001.mp4").write_bytes(b"existing-1")
        (lib_dir / "A-0002.mp4").write_bytes(b"existing-2")

        src = _make_src_file(tmp_path, "new.mp4", content=b"new")
        writer = FsLibraryWriter(_make_config(tmp_path))

        dest = Path(writer.copy_into(src, "2024-01-15", "a"))

        assert dest.name == "A-0003.mp4"
        # Pre-existing files are untouched.
        assert (lib_dir / "A-0001.mp4").read_bytes() == b"existing-1"


# ─── Recategorize (A↔B relocation) tests ───────────────────────────

class TestRecategorize:
    """Verify a library copy moves to the other A/B folder, renamed."""

    def test_moves_to_other_roll_folder(self, tmp_path):
        """An A-roll copy corrected to B-roll moves into B-roll/B-0001."""
        src = _make_src_file(tmp_path, "clip.mp4")
        writer = FsLibraryWriter(_make_config(tmp_path))

        a_path = Path(writer.copy_into(src, "2024-01-15", "a"))
        assert a_path.name == "A-0001.mp4"

        new_path = Path(writer.recategorize(a_path, "b"))

        assert new_path == tmp_path / "2024-01-15" / "B-roll" / "B-0001.mp4"
        assert new_path.exists()
        assert not a_path.exists()  # the old A-roll copy is gone (moved)

    def test_preserves_times_on_move(self, tmp_path):
        """Relocation is a rename, so mtime is preserved."""
        known_ts = 1705312200.0
        src = _make_src_file(tmp_path, "clip.mp4")
        writer = FsLibraryWriter(_make_config(tmp_path))

        a_path = Path(writer.copy_into(src, "2024-01-15", "a"))
        new_path = Path(writer.recategorize(a_path, "b"))

        assert os.path.getmtime(new_path) == known_ts

    def test_missing_copy_raises(self, tmp_path):
        """Recategorizing a path that no longer exists raises FileNotFoundError."""
        writer = FsLibraryWriter(_make_config(tmp_path))
        with pytest.raises(FileNotFoundError, match="Library copy does not exist"):
            writer.recategorize(tmp_path / "2024-01-15" / "A-roll" / "A-0001.mp4", "b")


# ─── Error handling tests ──────────────────────────────────────────

class TestErrorHandling:
    """Verify error paths raise appropriate exceptions."""

    def test_nonexistent_source_raises_file_not_found(self, tmp_path):
        """Copying a non-existent source raises FileNotFoundError."""
        writer = FsLibraryWriter(_make_config(tmp_path))

        with pytest.raises(FileNotFoundError, match="Source file does not exist"):
            writer.copy_into("/nonexistent/path/video.mp4", "2024-01-15", "a")

    def test_size_mismatch_raises_os_error(self, tmp_path):
        """If destination size differs from source after copy, raises OSError.

        We mock ``shutil.copy2`` to write only a partial file so the
        destination size is smaller than the source — triggering the
        post-copy size check in ``FsLibraryWriter.copy_into``.
        """
        src = _make_src_file(tmp_path, "truncated.mp4")  # 16 bytes
        writer = FsLibraryWriter(_make_config(tmp_path))

        _real_copy2 = shutil.copy2
        partial_written: list[bytes] = []

        def fake_copy2(src_path, dest_path):
            _real_copy2(src_path, dest_path)
            # Truncate destination to 9 bytes (less than source's 16).
            partial_written.append(b"X" * 9)
            with open(dest_path, "wb") as f:
                f.write(partial_written[-1])

        with patch("cutfinder.adapters.fs_library.shutil.copy2", fake_copy2):
            with pytest.raises(OSError, match="Size mismatch"):
                writer.copy_into(src, "2024-01-15", "a")


# ─── Config integration tests ──────────────────────────────────────

class TestConfigIntegration:
    """Verify library_path from AppConfig is used correctly."""

    def test_uses_config_library_path(self, tmp_path):
        """Destination is under the library path configured in AppConfig."""
        custom_lib = tmp_path / "my_custom_library"
        config = _make_config(custom_lib)

        src = _make_src_file(tmp_path, "test.mp4")
        writer = FsLibraryWriter(config)

        dest_str = writer.copy_into(src, "2024-05-10", "b")
        assert dest_str.startswith(str(custom_lib))


# ─── FakeLibraryWriter tests ──────────────────────────────────────

class TestFakeLibraryWriter:
    """Verify FakeLibraryWriter records calls and returns expected paths."""

    def test_records_call(self):
        writer = FakeLibraryWriter()
        _ = writer.copy_into("/tmp/video.mp4", "2026-01-01", "a")
        assert writer.calls == [("/tmp/video.mp4", "2026-01-01", "a")]

    def test_returns_a_roll_path(self):
        writer = FakeLibraryWriter()
        path = writer.copy_into("video.mp4", "2026-01-01", "a")
        assert path == "/library/2026-01-01/A-roll/"

    def test_returns_b_roll_path(self):
        writer = FakeLibraryWriter()
        path = writer.copy_into("video.mp4", "2026-01-01", "b")
        assert path == "/library/2026-01-01/B-roll/"

    def test_custom_library_path(self):
        writer = FakeLibraryWriter(library_path="/custom/lib")
        path = writer.copy_into("video.mp4", "2026-03-15", "a")
        assert path == "/custom/lib/2026-03-15/A-roll/"
