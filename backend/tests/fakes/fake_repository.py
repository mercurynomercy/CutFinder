"""FakeCatalogRepository — in-memory dedup tracker for unit testing Scanner.

This fake does **not** implement the full :class:`~cutfinder.ports.repository.CatalogRepository`
protocol (only ``exists_fingerprint`` is needed by Scanner).  It keeps a set of
known fingerprints so tests can verify deduplication logic without touching SQLite.

Examples
--------
>>> from cutfinder.fakes.fake_repository import FakeCatalogRepository
>>> repo = FakeCatalogRepository()
>>> repo.add_fingerprint("abc123")
>>> repo.exists_fingerprint("abc123")
True

Tracker for call assertions in tests:

    fingerprints :: set[str]
        The set of known fingerprint strings.
"""

from __future__ import annotations


class FakeCatalogRepository:
    """A minimal fake that tracks fingerprints for Scanner tests.

    Examples
    --------
    >>> repo = FakeCatalogRepository()  # noqa: D106
    """

    def __init__(self) -> None:
        self.fingerprints: set[str] = set()

    def add_fingerprint(self, fp: str) -> None:
        """Register a fingerprint as already processed."""
        self.fingerprints.add(fp)

    def exists_fingerprint(self, fp: str) -> bool:
        """Return True if *fp* has been registered."""
        return fp in self.fingerprints
