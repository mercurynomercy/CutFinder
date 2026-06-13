"""FakeLibraryWriter — track calls without doing real file I/O.

Returns a deterministic destination path pattern so tests can assert
on the expected library layout without touching the filesystem.

Examples
--------
>>> writer = FakeLibraryWriter()
>>> path = writer.copy_into("/tmp/video.mp4", "2026-01-01", "a")  # noqa: D100
>>> assert path == "/library/2026-01-01/A-roll/video.mp4"

Tracker for call assertions in tests:

    calls :: list[tuple[str, str, str]]
        List of (src, date, roll_type) tuples recorded on each copy_into call.
"""

from __future__ import annotations


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

    def copy_into(self, src: str | None, date: str, roll_type: str) -> str:
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
        self.calls.append((src, date, roll_type))

        roll_dir = "A-roll" if roll_type == "a" else "B-roll"
        return f"{self._library_path}/{date}/{roll_dir}/"
