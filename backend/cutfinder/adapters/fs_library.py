"""FsLibraryWriter — copy original files into the organised library structure.

Copies (via ``shutil.copy2``) an original video file into
``<library>/<date>/A-roll/`` or ``<library>/<date>/B-roll/``,
preserving file timestamps.  The copy is **renamed** to a sequential
``A-0001.<ext>`` / ``B-0001.<ext>`` scheme (per date/type folder) so the
library reads cleanly regardless of the source filenames.  The number is
the next free index in that folder.  After copying, verifies that the
destination size matches the source so silent truncation is caught
immediately.

The original source file is never touched; its path is preserved
separately in the catalog (``Clip.source_path``).

Edge cases handled:
  * Source file does not exist → raises ``FileNotFoundError`` (OSError).
  * Destination size mismatch → raises ``OSError``.

Examples
--------
>>> config = AppConfig(env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="key"), prefs=Prefs(library_path="/tmp/lib"))
>>> writer = FsLibraryWriter(config)  # doctest: +SKIP
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import re
import shutil
import sys
from pathlib import Path

from ..config import AppConfig

logger = logging.getLogger(__name__)


# ── macOS birth-time (creation time) preservation ──────────────────
# ``shutil.copy2`` preserves mtime/atime but NOT the creation (birth) time on
# macOS — the copy gets a fresh "Created = now".  We restore it via the BSD
# ``setattrlist`` syscall so the library copy keeps the original's Created date.

_ATTR_BIT_MAP_COUNT = 5
_ATTR_CMN_CRTIME = 0x00000200


class _attrlist(ctypes.Structure):
    _fields_ = [
        ("bitmapcount", ctypes.c_ushort),
        ("reserved", ctypes.c_uint16),
        ("commonattr", ctypes.c_uint32),
        ("volattr", ctypes.c_uint32),
        ("dirattr", ctypes.c_uint32),
        ("fileattr", ctypes.c_uint32),
        ("forkattr", ctypes.c_uint32),
    ]


class _timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]


def _set_birthtime(path: Path, birthtime: float) -> None:
    """Set *path*'s creation (birth) time on macOS via ``setattrlist``.

    No-op on non-macOS platforms.  Raises ``OSError`` if the syscall fails.
    """
    if sys.platform != "darwin":
        return
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    al = _attrlist()
    al.bitmapcount = _ATTR_BIT_MAP_COUNT
    al.commonattr = _ATTR_CMN_CRTIME
    sec = int(birthtime)
    nsec = int((birthtime - sec) * 1e9)
    ts = _timespec(sec, nsec)
    rc = libc.setattrlist(
        os.fsencode(str(path)), ctypes.byref(al), ctypes.byref(ts), ctypes.sizeof(ts), 0,
    )
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


# ── FsLibraryWriter ────────────────────────────────────────────────

class FsLibraryWriter:
    """Copy an original video file into the library's date/type directory.

    Parameters
    ----------
    config:
        Application-wide configuration containing the library path at
        ``config.prefs.library_path``.

    Examples
    --------
    >>> config = AppConfig(  # doctest: +SKIP
    ...     env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="test-key"),
    ...     prefs=Prefs(library_path="/tmp/test_lib"),
    ... )
    >>> writer = FsLibraryWriter(config)  # doctest: +SKIP
    """

    def __init__(self, config: AppConfig) -> None:
        self._library_dir = Path(config.prefs.library_path).resolve()

    def copy_into(self, src: Path | str, date: str, roll_type: str) -> str:
        """Copy *src* to ``<library>/<date>/roll/`` with a sequential name.

        - Original file is never modified (read-only).
        - The copy is renamed to ``A-0001.<ext>`` / ``B-0001.<ext>``, using the
          next free index within the date/type folder — never overwrites.
        - Returns the destination path (as string).

        Parameters
        ----------
        src:
            Path to the original (read-only) video file.
        date:
            ISO-formatted date string, e.g. ``"2026-06-13"``.
        roll_type:
            Either ``"a"`` or ``"b"`` (RollType).

        Returns
        -------
        str
            The absolute destination path as a string.

        Raises
        ------
        FileNotFoundError:
            If *src* does not exist on disk.
        OSError:
            On copy failure or size mismatch after copying.
        """
        src = Path(src).resolve()

        if not src.is_file():
            raise FileNotFoundError(f"Source file does not exist: {src}")

        # Determine target directory and filename prefix (A-roll → "A").
        is_a_roll = roll_type == RollType.A.value
        roll_dir = "A-roll" if is_a_roll else "B-roll"
        prefix = "A" if is_a_roll else "B"
        target_dir = self._library_dir / date / roll_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Pick the next sequential name, preserving the source extension.
        dest = self._next_dest(target_dir, prefix, src.suffix)

        # Copy with preserved timestamps
        shutil.copy2(src, dest)

        # Verify size integrity after copy
        if src.stat().st_size != dest.stat().st_size:
            raise OSError(
                f"Size mismatch after copy: source={src.stat().st_size}, "
                f"dest={dest.stat().st_size}"
            )

        # copy2 preserves mtime/atime; also restore the original creation time
        # (macOS) so the copy's "Created" matches the source.  Best-effort:
        # a failure here must not fail the copy (mtime is already preserved).
        src_birthtime = getattr(src.stat(), "st_birthtime", None)
        if src_birthtime is not None:
            try:
                _set_birthtime(dest, src_birthtime)
            except OSError as exc:
                logger.warning("Could not preserve creation time for %s: %s", dest, exc)

        return str(dest)

    def recategorize(self, old_path: Path | str, new_roll_type: str) -> str:
        """Move an existing library copy into the other A/B folder, renamed.

        Used when the user corrects a clip's A/B classification.  The copy is
        *moved* (a same-volume rename, so all timestamps are preserved) into the
        sibling ``A-roll``/``B-roll`` folder under the same date, and given the
        next sequential name there.  The source date folder is unchanged.

        Parameters
        ----------
        old_path:
            Current location of the library copy (``Clip.library_path``).
        new_roll_type:
            The corrected roll, ``"a"`` or ``"b"`` (RollType).

        Returns
        -------
        str
            The new absolute destination path as a string.

        Raises
        ------
        FileNotFoundError:
            If *old_path* does not exist on disk.
        """
        old = Path(old_path).resolve()
        if not old.is_file():
            raise FileNotFoundError(f"Library copy does not exist: {old}")

        # old_path is ``<library>/<date>/<roll>/<name>`` — keep the date folder,
        # swap only the roll subfolder.
        date_dir = old.parent.parent
        is_a_roll = new_roll_type == RollType.A.value
        roll_dir = "A-roll" if is_a_roll else "B-roll"
        prefix = "A" if is_a_roll else "B"
        target_dir = date_dir / roll_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        dest = self._next_dest(target_dir, prefix, old.suffix)
        shutil.move(str(old), str(dest))  # rename on same volume → times preserved
        return str(dest)

    def _next_dest(self, target_dir: Path, prefix: str, suffix: str) -> Path:
        """Return ``<target_dir>/<prefix>-NNNN<suffix>`` for the next free index.

        Scans ``target_dir`` for existing ``<prefix>-NNNN`` files and uses the
        highest index + 1, so re-scans keep numbering monotonically.
        """
        index_re = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        max_idx = 0
        for entry in target_dir.iterdir():
            m = index_re.match(entry.stem)
            if m:
                max_idx = max(max_idx, int(m.group(1)))

        idx = max_idx + 1
        while True:
            candidate = target_dir / f"{prefix}-{idx:04d}{suffix}"
            if not candidate.exists():
                return candidate
            idx += 1


# ── import RollType at module level (lazy to avoid circular dep)
from ..domain.enums import RollType  # noqa: E402, isort: skip
