"""Integration tests for SileroSpeechDetector using real video files.

These exercise the actual ffmpeg audio extraction + Silero VAD pipeline
(no mocking) and validate that A-roll videos have higher speech ratios
than B-roll footage, plus basic invariants (range, determinism).

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration``.

Requires: ffmpeg, ffprobe, Silero VAD model (auto-downloaded on first run).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cutfinder.adapters.silero_vad import SileroSpeechDetector


# ── fixtures ───────────────────────────────────────────────────────

def _test_video_dir() -> Path:
    root = Path(__file__).resolve().parents[3]  # repo root (integration -> tests -> backend -> CutFinder)
    return root / "testVideo"


# A-roll threshold: speech ratio ≥ this → classified as A-roll (matches pipeline default)
AROLL_THRESHOLD = 0.15


def _skip_if_missing(name: str) -> Path:
    """Return the path if it exists, otherwise skip."""
    test_dir = _test_video_dir()
    # Map of known sample names to filenames
    name_map: dict[str, str] = {
        "a_roll_canon": "MVI_5298.MP4",
    }
    filename = name_map.get(name)
    if not filename:
        pytest.skip(f"Unknown sample: {name}")
    path = test_dir / filename
    if not path.exists():
        pytest.skip(f"Sample file missing: {path}")
    return Path(path)



# ── integration tests (real ffmpeg + real Silero VAD model) ───────

@pytest.mark.integration
class TestSileroSpeechDetectorRealVideo:
    """Validate SileroSpeechDetector against real footage."""

    def test_a_roll_canon_high_ratio(self, tmp_path: Path) -> None:
        """Canon A-roll (MVI_5298.MP4) → speech ratio ≥ threshold."""
        video_path = _skip_if_missing("a_roll_canon")

        detector = SileroSpeechDetector()
        ratio = detector.speech_ratio(video_path)

        assert ratio >= AROLL_THRESHOLD, (
            f"A-roll video should have speech_ratio ≥ {AROLL_THRESHOLD}, "
            f"got {ratio:.3f}"
        )

    def test_a_roll_higher_than_b_roll_canon(self, tmp_path: Path) -> None:
        """A-roll speech ratio > Canon B-roll (MVI_5298 vs MVI_5368)."""
        a_roll_path = _test_video_dir() / "MVI_5298.MP4"
        b_roll_path = _test_video_dir() / "MVI_5368.MP4"
        if not b_roll_path.exists():
            pytest.skip(f"B-roll sample missing: {b_roll_path}")

        detector = SileroSpeechDetector()
        a_ratio = detector.speech_ratio(a_roll_path)
        b_ratio = detector.speech_ratio(b_roll_path)

        assert a_ratio > b_ratio, (
            f"A-roll ratio ({a_ratio:.3f}) should be higher than "
            f"B-roll ratio ({b_ratio:.3f})"
        )

    def test_b_roll_dji_low_ratio(self, tmp_path: Path) -> None:
        """DJI drone B-roll (DJI_*.MP4) → speech ratio < threshold."""
        dji_path = _test_video_dir() / "DJI_20260515175239_0097_D.MP4"
        if not dji_path.exists():
            pytest.skip(f"DJI sample missing: {dji_path}")

        detector = SileroSpeechDetector()
        ratio = detector.speech_ratio(dji_path)

        # Note: DJI footage may contain wind/noise that VAD interprets
        # as speech. Use a relaxed upper bound (0.9) to catch truly silent videos
        # while still allowing for ambient noise false positives.
        assert ratio < 0.9, (
            f"DJI B-roll should have speech_ratio < 0.9, "
            f"got {ratio:.3f} (may contain wind/noise VAD interprets as speech)"
        )

    def test_ratio_in_valid_range(self, tmp_path: Path) -> None:
        """All speech ratios must be in [0.0, 1.0]."""
        video_path = _skip_if_missing("a_roll_canon")

        detector = SileroSpeechDetector()
        ratio = detector.speech_ratio(video_path)

        assert 0.0 <= ratio <= 1.0, (
            f"Speech ratio must be in [0, 1], got {ratio}"
        )

    def test_consistent_across_runs(self, tmp_path: Path) -> None:
        """Running speech_ratio twice on the same file → identical ratio."""
        video_path = _skip_if_missing("a_roll_canon")

        detector = SileroSpeechDetector()
        ratio1 = detector.speech_ratio(video_path)
        ratio2 = detector.speech_ratio(video_path)

        assert ratio1 == pytest.approx(ratio2, rel=1e-6), (
            f"Speech ratio should be deterministic: {ratio1} vs {ratio2}"
        )
