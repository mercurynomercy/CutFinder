"""LibraryWriter — copy original file into the organised library structure."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class LibraryWriter(Protocol):
    """Copy an original video file into the library's date/type directory."""

    def copy_into(self, src: Path, date: str, roll_type: str) -> str:
        """Copy *src* to ``<library>/<date>/roll_type/`` preserving times.

        - Original file is never modified (read-only).
        - If a同名 exists, append ``(1)``, ``(2)`` etc. — never overwrite.
        - Returns the destination path on success.

        Args:
            src: Path to the original (read-only) video file.
            date: ISO-formatted date string, e.g. ``"2026-06-13"``.
            roll_type: Either ``"a"`` or ``"b"`` (RollType).

        Raises:
            OSError: On copy failure or size mismatch after copying.
        """

    def recategorize(self, old_path: Path | str, new_roll_type: str) -> str:
        """Move an existing library copy into the other A/B folder, renamed.

        Used when the user corrects a clip's A/B classification.  The copy is
        moved (same-volume rename, preserving timestamps) into the sibling
        ``A-roll``/``B-roll`` folder under the same date, with the next
        sequential name.  Returns the new destination path.

        Args:
            old_path: Current location of the library copy.
            new_roll_type: The corrected roll, ``"a"`` or ``"b"``.

        Raises:
            FileNotFoundError: If *old_path* does not exist.
        """
