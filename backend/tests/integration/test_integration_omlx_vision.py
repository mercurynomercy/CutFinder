"""Integration tests for OmlxVisionTagger — real OMLX calls.

These tests require a running OMLX server and use the actual vision model
to produce real visual tags. Skip if OMLX is unavailable or credentials are missing.

Run with:
    pytest tests/integration/test_integration_omlx_vision.py -v --run-integration

Pattern matches test_integration_omlx_summarizer.py.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from cutfinder.adapters.omlx_vision import OmlxVisionTagger
from cutfinder.config import EnvSettings, load_config


def _make_test_frame(tmp_path: Path) -> Path:
    """Create a minimal 1x1 PNG for OMLX to process."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03"
        b"\x01\x01\x00\x18\xdd\xe5\xd7"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "test_frame.png"
    p.write_bytes(png_bytes)
    return p


def _has_omlx_config() -> bool:
    """Check if OMLX credentials are configured in the environment."""
    try:
        settings = EnvSettings()
        return bool(settings.OMLX_BASE_URL and settings.OMLX_API_KEY)
    except Exception:
        return False


@pytest.fixture(scope="module")
def vision_tagger(tmp_path_factory):
    """Create a real OmlxVisionTagger for integration tests."""
    if not _has_omlx_config():
        pytest.skip("OMLX credentials not configured (skip integration test)")

    # Use a temp library dir for config
    lib_dir = tmp_path_factory.mktemp("omlx_vision_test")
    # We'll load config from env vars directly since we don't need a real library

    from cutfinder.config import AppConfig, Prefs
    config = AppConfig(
        env=EnvSettings(),
        prefs=Prefs(vision_model="Qwen3-VL-8B"),
    )

    return OmlxVisionTagger(config)


@pytest.mark.integration
class TestOmlxVisionTaggerIntegration:
    """Real OMLX integration tests — require running inference server."""

    def test_single_frame_tagging(self, vision_tagger, tmp_path):
        """Send one frame to OMLX and verify structured JSON response."""
        frame = _make_test_frame(tmp_path)

        result = vision_tagger.describe([frame])
        assert isinstance(result.description, str)
        assert len(result.description) > 0
        assert isinstance(result.tags, list)
        assert len(result.tags) > 0
        for tag in result.tags:
            assert isinstance(tag, str)

    def test_multi_frame_tagging(self, vision_tagger, tmp_path):
        """Send multiple frames in one request — OMLX should handle multi-frame input."""
        frame1 = _make_test_frame(tmp_path, "frame1.png")
        # Reuse same frame for simplicity — OMLX should still return valid output
        result = vision_tagger.describe([frame1, frame1])
        assert isinstance(result.description, str)
        assert len(result.description) > 0
        assert isinstance(result.tags, list)

    def test_base64_encoding_correct(self):
        """Verify base64 encoding of PNG produces valid data URI format."""
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03"
            b"\x01\x01\x00\x18\xdd\xe5\xd7"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        b64 = base64.b64encode(png_bytes).decode("ascii")
        uri = f"data:image/png;base64,{b64}"

        assert uri.startswith("data:image/png;base64,")
        # Verify round-trip: decode back to original bytes
        assert base64.b64decode(uri.split(",", 1)[1]) == png_bytes
