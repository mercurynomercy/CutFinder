"""Integration tests for DemucsSeparator using real video files.

Exercises the actual ffmpeg extraction + Demucs separation pipeline
(no mocking) and validates that vocals are isolated into a 16 kHz mono
float32 array of reasonable length.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration``.

Requires: ffmpeg, demucs (auto-downloads the htdemucs model on first run).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# ── fixtures ───────────────────────────────────────────────────────
def _test_video_dir() -> Path:
    root = Path(__file__).resolve().parents[3]  # repo root (integration → tests → backend → CutFinder)
    return root / "testVideo"


# Skip entire module if demucs is not installed
pytest.importorskip("demucs")


def _skip_if_missing(name: str) -> Path:
    """Return the path if it exists, otherwise skip."""
    name_map: dict[str, str] = {
        "a_roll_canon": "MVI_5298.MP4",
    }
    filename = name_map.get(name)
    if not filename:
        pytest.skip(f"Unknown sample: {name}")
    path = _test_video_dir() / filename
    if not path.exists():
        pytest.skip(f"Sample file missing: {path}")
    return path


# ── integration tests (real ffmpeg + real Demucs model) ────────────

@pytest.mark.integration
class TestDemucsSeparatorRealVideo:
    """Validate DemucsSeparator against real footage."""

    def test_isolate_returns_16k_mono_float32(self) -> None:
        """A-roll (MVI_5298.MP4) → 1-D float32 vocals at ~16k samples/sec."""
        video_path = _skip_if_missing("a_roll_canon")

        from cutfinder.adapters.demucs_separator import DemucsSeparator
        separator = DemucsSeparator()
        vocals = separator.isolate(video_path)

        assert isinstance(vocals, np.ndarray)
        assert vocals.ndim == 1
        assert vocals.dtype == np.float32
        # At least a couple of seconds of audio at 16 kHz.
        assert len(vocals) > 16000
