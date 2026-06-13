"""Integration tests for OmlxSummarizer using real OMLX server.

Exercises the actual OpenAI client call to a local OMLX instance
(no mocking) and validates that Chinese transcript text produces
non-empty summary + tags.

Marked ``@pytest.mark.integration`` so they are skipped by default;
run with ``-m integration``.

Requires: local OMLX server running at the URL from .env.
"""

from __future__ import annotations

import pytest


# Skip entire module if openai is not installed
openai = pytest.importorskip("openai")


def _load_config() -> __import__("cutfinder.config", fromlist=["AppConfig"]).AppConfig:
    """Load config from .env file for real OMLX calls."""
    import os  # noqa: I001 — top-level for side effect on pydantic-settings
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]  # repo root
    env_path = root / ".env"

    if not env_path.exists():
        pytest.skip(".env file missing; cannot load OMLX config")

    # pydantic-settings reads .env via EnvSettings
    from cutfinder.config import EnvSettings, Prefs

    try:
        env = EnvSettings()
    except ValueError as e:
        pytest.skip(f"Cannot load OMLX config: {e}")

    return __import__("cutfinder.config", fromlist=["AppConfig"]).AppConfig(
        env=env, prefs=Prefs()
    )


@pytest.mark.integration
class TestOmlxSummarizerRealOMLX:
    """Validate OmlxSummarizer against a real OMLX server."""

    def test_a_roll_chinese_transcript_produces_summary(self):
        """Chinese A-roll transcript → non-empty summary + tags."""
        config = _load_config()

        from cutfinder.adapters.omlx_text import OmlxSummarizer
        summarizer = OmlxSummarizer(config)

        result = summarizer.summarize(
            "这是一段关于旅行的视频，我们去了云南大理和丽江。"
            "洱海的风景非常美，玉龙雪山也很壮观。"
        )

        assert len(result.summary.strip()) > 0, (
            f"A-roll transcript should produce non-empty summary, "
            f"got: {result.summary!r}"
        )

    def test_summary_contains_chinese_characters(self):
        """Summary text should contain Chinese characters."""
        config = _load_config()

        import re  # noqa: I001 — top-level for side effect
        from cutfinder.adapters.omlx_text import OmlxSummarizer

        summarizer = OmlxSummarizer(config)
        result = summarizer.summarize(
            "今天我们来介绍一下这款新产品，它有很多创新的功能。"
        )

        assert re.search(r"[一-鿿]", result.summary), (
            f"Summary should contain Chinese characters, "
            f"got: {result.summary!r}"
        )

    def test_tags_are_non_empty_list_of_strings(self):
        """Tags should be a non-empty list of strings."""
        config = _load_config()

        from cutfinder.adapters.omlx_text import OmlxSummarizer
        summarizer = OmlxSummarizer(config)

        result = summarizer.summarize(
            "这是一段介绍科技产品的视频，讨论了人工智能的发展。"
        )

        assert isinstance(result.tags, list), f"Tags should be a list, got {type(result.tags)}"
        assert len(result.tags) > 0, f"Tags should be non-empty, got {result.tags}"
        assert all(isinstance(t, str) for t in result.tags), (
            f"All tags should be strings: {result.tags}"
        )

    def test_empty_input_returns_empty_result(self):
        """Empty string input → empty summary and tags (no network call)."""
        config = _load_config()

        from cutfinder.adapters.omlx_text import OmlxSummarizer
        summarizer = OmlxSummarizer(config)

        result = summarizer.summarize("")
        assert result.summary == ""
        assert result.tags == []
