"""FakeSummarizer — return a preset SummaryResult for unit testing.

Useful in tests that exercise the pipeline without calling OMLX
(no real network requests).

Examples
--------
>>> summarizer = FakeSummarizer()
>>> result = summarizer.summarize("some transcript")  # noqa: D100
>>> assert result.summary == "这是一段中文简介。"

Tracker for call assertions in tests:

    calls :: list[str]
        List of transcript texts recorded on each :meth:`summarize` call.
"""

from __future__ import annotations

from ..domain.models import SummaryResult
from ..ports.ai import Summarizer


class FakeSummarizer(Summarizer):
    """A summarizer that returns a predetermined SummaryResult.

    Parameters
    ----------
    summary:
        The ``summary`` string to return. Defaults to a short Chinese sentence.
    tags:
        List of tag strings to include. Defaults to ``["旅行", "风景"]``.
    should_fail:
        When ``True``, :meth:`summarize` raises ``RuntimeError`` instead.

    Examples
    --------
    >>> summarizer = FakeSummarizer()
    >>> result = summarizer.summarize("这是一段测试文本")  # noqa: D100
    >>> assert result.tags == ["旅行", "风景"]

    """

    def __init__(
        self,
        summary: str = "这是一段中文简介。",
        tags: list[str] | None = None,
        should_fail: bool = False,
    ) -> None:
        self._summary = summary
        self._tags = tags if tags is not None else ["旅行", "风景"]
        self._should_fail = should_fail
        # Track calls for assertions in tests
        self.calls: list[str] = []

    def summarize(self, transcript_text: str) -> SummaryResult:
        """Return the pre-set summary result (or fail if configured to)."""
        self.calls.append(transcript_text)

        if self._should_fail:
            raise RuntimeError("FakeSummarizer: simulated failure")

        return SummaryResult(summary=self._summary, tags=list(self._tags))


def make_sample_summary() -> SummaryResult:
    """Return a sample :class:`SummaryResult` for tests."""
    return FakeSummarizer().summarize("这是一段测试用的转写文本。")
