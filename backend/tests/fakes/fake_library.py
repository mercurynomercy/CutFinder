"""FakeLibraryWriter — track calls without doing real file I/O.

Returns a deterministic destination path pattern so tests can assert
on the expected library layout without touching the filesystem.

Examples
--------
>>> writer = FakeLibraryWriter()
>>> from pathlib import Path
>>> path = writer.copy_into(Path("/tmp/video.mp4"), "2026-01-01", "a")  # noqa: D100
>>> assert path == "/library/2026-01-01/A-roll/"

Tracker for call assertions in tests:

    calls :: list[tuple[str, str, str]]
        List of (src_str, date, roll_type) tuples recorded on each copy_into call.
"""

from __future__ import annotations

from pathlib import Path


class FakeLibraryWriter:
    """A library writer that records calls without performing real copies.

    Parameters
    ----------
    library_path:
        The virtual library root to use in destination path construction.

    Examples
    --------
    >>> writer = FakeLibraryWriter()  # noqa: D100
    """

    def __init__(self, library_path: str = "/library") -> None:
        self._library_path = library_path
        # Track calls for assertions in tests
        self.calls: list[tuple[str, str, str]] = []
        self.recategorize_calls: list[tuple[str, str]] = []  # (old_path, new_roll_type)

    def copy_into(self, src: Path | None, date: str, roll_type: str) -> str:
        """Return a deterministic destination path without copying.

        Parameters
        ----------
        src:
            The source file path (recorded for assertions).
        date:
            ISO-formatted date string.
        roll_type:
            ``"a"`` or ``"b"``.

        Returns
        -------
        str
            The expected destination path as a string.
        """
        src_str = str(src) if src is not None else ""
        self.calls.append((src_str, date, roll_type))

        roll_dir = "A-roll" if roll_type == "a" else "B-roll"
        return f"{self._library_path}/{date}/{roll_dir}/"

    def recategorize(self, old_path: Path | str, new_roll_type: str) -> str:
        """Return a deterministic relocated path without moving any file.

        Keeps the date folder from *old_path* and swaps the roll subfolder,
        mirroring :class:`FsLibraryWriter` behaviour for assertions.
        """
        old = Path(str(old_path))
        self.recategorize_calls.append((str(old_path), new_roll_type))

        date_dir = old.parent.parent
        roll_dir = "A-roll" if new_roll_type == "a" else "B-roll"
        prefix = "A" if new_roll_type == "a" else "B"
        return str(date_dir / roll_dir / f"{prefix}-0001{old.suffix}")
