"""Placeholder test — verifies the test harness works.

Replace this with real unit tests as each module is implemented.
"""

from cutfinder.domain import RollType, ClipStatus


def test_roll_type_enum() -> None:
    """RollType has the expected members."""
    assert RollType.A.value == "a"
    assert RollType.B.value == "b"


def test_clip_status_enum() -> None:
    """ClipStatus has the expected members."""
    assert ClipStatus.PENDING.value == "pending"
    assert ClipStatus.DONE.value == "done"


def test_domain_models_import() -> None:
    """All domain models are importable (smoke test)."""
    from cutfinder.domain.models import (  # noqa: F401
        VideoMetadata,
        Clip,
        Tag,
        Transcript,
    )
