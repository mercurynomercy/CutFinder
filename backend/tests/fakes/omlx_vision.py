"""Fake VisionTagger for unit testing — no real OMLX calls.

Returns a fixed :class:`VisionResult` so tests can verify
prompt construction, request parameters, and JSON parsing logic without network access.

Examples
--------
>>> from tests.fakes.omlx_vision import FakeVisionTagger, make_sample_result
>>> fake = FakeVisionTagger()
>>> result = fake.describe([Path("frame1.png")])
>>> assert isinstance(result.description, str)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cutfinder.domain.models import VisionResult


def make_sample_result() -> VisionResult:
    """Return a typical sample :class:`VisionResult`."""
    return VisionResult(
        description="画面展示了日落时分的海滩景色，海浪拍打着沙滩，天空呈现橙红色渐变。",
        tags=["日落", "海滩", "海浪", "沙滩", "橙红色天空", "自然风光"],
    )


class FakeVisionTagger:
    """Fake :class:`~cutfinder.ports.ai.VisionTagger` that returns a fixed result."""

    def __init__(self, result: VisionResult | None = None) -> None:
        self._result = result or make_sample_result()
        # Track calls for assertions in tests
        self.last_frame_paths: list[Path] = []

    def describe(self, frame_paths: list[Path]) -> VisionResult:
        self.last_frame_paths = frame_paths
        return self._result
