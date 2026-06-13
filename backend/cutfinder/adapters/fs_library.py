"""FsLibraryWriter — copy original files into the organised library structure.

Copies (via ``shutil.copy2``) an original video file into
``<library>/<date>/A-roll/`` or ``<library>/<date>/B-roll/``,
preserving file timestamps.  If a同名 (same-name) file already exists,
appends ``(1)``, ``(2)``, etc. — never overwrites the existing file.
After copying, verifies that the destination size matches the source
so silent truncation is caught immediately.

Edge cases handled:
  * Source file does not exist → raises ``FileNotFoundError`` (OSError).
  * Destination size mismatch → raises ``OSError``.
  * Same-name file already exists → appends ``(1)``, ``(2)`` …

Examples
--------
>>> config = AppConfig(env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="key"), prefs=Prefs(library_path="/tmp/lib"))
>>> writer = FsLibraryWriter(config)  # doctest: +SKIP
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config import AppConfig


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
        """Copy *src* to ``<library>/<date>/roll/`` preserving times.

        - Original file is never modified (read-only).
        - If a同名 exists, append ``(1)``, ``(2)`` etc. — never overwrite.
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

        # Determine target directory
        roll_dir = "A-roll" if roll_type == RollType.A.value else "B-roll"
        target_dir = self._library_dir / date / roll_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Resolve conflict: append (1), (2), ...
        dest = self._resolve_dest(src.name, target_dir)

        # Copy with preserved timestamps
        shutil.copy2(src, dest)

        # Verify size integrity after copy
        if src.stat().st_size != dest.stat().st_size:  # type: ignore[union-attr]
            raise OSError(
                f"Size mismatch after copy: source={src.stat().st_size}, "
                f"dest={dest.stat().st_size}"  # type: ignore[union-attr]
            )

        return str(dest)

    def _resolve_dest(self, filename: str, target_dir: Path) -> Path:
        """Return a destination path that does not collide with existing files.

        If ``filename`` already exists, appends ``(1)``, ``(2)``, etc.
        """
        candidate = target_dir / filename
        if not candidate.exists():
            return candidate

        stem, suffix = Path(filename).stem, Path(filename).suffix
        counter = 1
        while True:
            candidate = target_dir / f"{stem}({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1


# ── import RollType at module level (lazy to avoid circular dep)
from ..domain.enums import RollType  # noqa: E402, isort: skip
