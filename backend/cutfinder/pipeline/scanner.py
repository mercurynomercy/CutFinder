"""Scanner — scan source folders, deduplicate by fingerprint, produce clip candidates.

This module is a **pure-logic** component: it never touches external services
(ffmpeg, OMLX, etc.).  The only I/O dependency is the file system (for walking
directories and reading small chunks for fingerprinting) plus a injected
:class:`~cutfinder.ports.repository.CatalogRepository` to check whether clips have
already been processed.

Fingerprint algorithm (from detailed-design §3.10)::

    sha256( struct.pack('>Q', file_size)  +  first_4_mib_of_content )

Only the size prefix and up to 4 MiB of content are hashed — large video files
are never read in full, yet the fingerprint is stable enough for deduplication.

Examples
--------
>>> from pathlib import Path
>>> repo = FakeCatalogRepository()  # see tests/fakes/ or conftest
>>> scanner = Scanner(repo)
>>> candidates = scanner.scan([Path("/tmp/footage")], {".mp4", ".mov"})
>>> for c in candidates:
...     print(c.path, c.fingerprint)  # noqa: T201 — example only
"""

from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
from typing import Protocol, Set

# ── internal constants ────────────────────────────────────────────────

_FOUR_MIB = 4 * 1024 * 1024  # 4 MiB, max bytes read for fingerprinting


# ── public API ────────────────────────────────────────────────────────

def _compute_fingerprint(path: Path) -> str:
    """Return the sha256 hex digest for *path* using size + first 4 MiB.

    Parameters
    ----------
    path:
        Absolute or relative filesystem path to a regular file.

    Returns
    -------
    str:
        64-character hex digest string (lowercase).

    Raises
    ------
    OSError:
        If the file cannot be opened or read.

    Examples
    --------
    >>> import tempfile, os  # doctest: +SKIP
    >>> with tempfile.NamedTemporaryFile(delete=False) as f:  # doctest: +SKIP
    ...     f.write(b"hello")                                 # doctest: +SKIP
    >>> fp = _compute_fingerprint(Path(f.name))              # doctest: +SKIP
    >>> len(fp) == 64                                        # doctest: +SKIP
    True                                                   # doctest: +SKIP
    >>> os.unlink(f.name)                                    # doctest: +SKIP
    """

    with open(path, "rb") as fh:  # noqa: PTH123 — intentional file read
        size = os.fstat(fh.fileno()).st_size  # noqa: PTH117
        size_bytes = struct.pack(">Q", size)  # big-endian unsigned 64-bit
        to_hash = bytearray(size_bytes)
        remaining = min(_FOUR_MIB, size)
        while remaining > 0:
            chunk = fh.read(remaining)
            if not chunk:
                break
            to_hash.extend(chunk)
            remaining -= len(chunk)
        return hashlib.sha256(bytes(to_hash)).hexdigest()


def _is_hidden(path: Path) -> bool:
    """Return ``True`` if *path* or any of its immediate parents is hidden.

    A path component starting with ``"."`` (Unix convention) is treated as
    hidden and skipped during scanning.

    Examples
    --------
    >>> _is_hidden(Path("."))
    True
    >>> _is_hidden(Path("foo"))
    False
    """

    return any(part.startswith(".") for part in path.parts)


class CatalogRepository(Protocol):
    """Minimal repository protocol — only the method Scanner needs.

    This decouples Scanner from the real SQLite implementation so that
    unit tests can inject a fake or in-memory variant.

    Examples
    --------
    >>> class InMem:  # doctest: +SKIP
    ...     def exists_fingerprint(self, fp: str) -> bool:  # doctest: +SKIP
    ...         return False                                # doctest: +SKIP
    >>> scanner = Scanner(InMem())  # works fine                       # doctest: +SKIP
    """

    def exists_fingerprint(self, fp: str) -> bool: ...


class Scanner:
    """Walk source folders and produce a deduplicated list of new clips.

    Parameters
    ----------
    repository:
        The :class:`CatalogRepository` used to check whether a fingerprint has
        already been processed.

    Examples
    --------
    >>> from cutfinder.fakes import FakeCatalogRepository  # doctest: +SKIP
    >>> scanner = Scanner(FakeCatalogRepository())        # doctest: +SKIP
    """

    def __init__(self, repository: CatalogRepository) -> None:  # type: ignore[misc]
        self._repository = repository

    def scan(
        self,
        source_folders: list[Path],
        extensions: set[str] | None = None,
    ) -> list["ClipCandidate"]:  # type: ignore[name-defined] — forward ref resolved below
        """Walk *source_folders*, filter by extension, fingerprint and deduplicate.

        Parameters
        ----------
        source_folders:
            Directories to walk recursively for video files.  Non-existent
            directories are silently skipped (no error raised).

        extensions:
            Case-insensitive set of file extensions to include, e.g.
            ``{".mp4", ".mov"}``.  When omitted the default is
            ``{" .mov", ".mp4", ".m4v"}``.

        Returns
        -------
        list[ClipCandidate]:
            Files that passed the extension filter, have a unique fingerprint
            not yet seen in the repository.

        Examples
        --------
        >>> from pathlib import Path  # doctest: +SKIP
        >>> scanner = Scanner(FakeCatalogRepository())         # doctest: +SKIP
        >>> candidates = scanner.scan([Path("/tmp")], {".mp4"}) # doctest: +SKIP
        >>> assert all(isinstance(c, ClipCandidate) for c in candidates)  # doctest: +SKIP
        """

        if extensions is None:
            extensions = {".mov", ".mp4", ".m4v"}

        # Normalise to lowercase for case-insensitive comparison.
        ext_lower = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

        seen_fingerprints: Set[str] = set()
        candidates: list["ClipCandidate"] = []

        for folder in source_folders:
            if not folder.is_dir():
                continue  # silently skip non-existent or non-directory paths

            for dirpath, dirnames, filenames in os.walk(folder):
                # Prune hidden directories in-place so os.walk skips them.
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]

                for filename in filenames:
                    # Skip hidden files.
                    if filename.startswith("."):
                        continue

                    file_path = Path(dirpath) / filename

                    # Skip hidden paths (any component starting with ".").
                    if _is_hidden(file_path.relative_to(folder)):
                        continue

                    # Extension whitelist (case-insensitive).
                    file_ext = file_path.suffix.lower() if file_path.suffix else ""
                    if file_ext not in ext_lower:
                        continue

                    # Compute fingerprint.
                    try:
                        fp = _compute_fingerprint(file_path)
                    except (OSError, ValueError):
                        continue  # skip unreadable files

                    # Deduplicate within this scan pass.
                    if fp in seen_fingerprints:
                        continue

                    # Deduplicate against already-processed clips.
                    if self._repository.exists_fingerprint(fp):
                        continue

                    seen_fingerprints.add(fp)
                    # Import here to avoid circular imports at module level.
                    from ..domain.models import ClipCandidate  # noqa: PLC0415

                    candidates.append(ClipCandidate(path=str(file_path), fingerprint=fp))

        return candidates


# ── re-export for convenience ───────────────────────────────────────

from ..domain.models import ClipCandidate  # noqa: E402, PLC0415 — after forward ref above
