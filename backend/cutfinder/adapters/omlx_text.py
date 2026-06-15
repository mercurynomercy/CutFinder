"""OmlxSummarizer — A-roll text summary + tags via OMLX (OpenAI-compatible).

Calls the local OMLX server's ``/chat/completions`` endpoint with
structured JSON output to produce a Chinese summary and tag list from
transcript text.

Edge cases handled:
  * Missing ``full_text`` or empty string → returns empty SummaryResult.
  * OMLX unavailable (connection error) → raises ``RuntimeError`` with detail.
  * Malformed LLM response (missing keys) → falls back to empty strings/lists.

Examples
--------
>>> config = AppConfig(env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="key"), prefs=Prefs())
>>> summarizer = OmlxSummarizer(config)  # doctest: +SKIP
>>> result = summarizer.summarize("这是一段关于旅行的视频...")  # doctest: +SKIP
>>> print(result.summary)
"""

from __future__ import annotations

from typing import Any

from ..config import AppConfig
from ..domain.models import SummaryResult
from ..ports.ai import Summarizer

# ── prompt template ────────────────────────────────────────────────

_SUMMARIZE_PROMPT = """\
你是一个专业的视频内容整理助手。请根据以下A-roll（有解说）视频的转写文本，完成两件事：

1. **简介**：用中文撰写一段简洁的概述（30-80字），概括视频的核心内容和主题。
2. **标签**：提取5-10个关键词/短语作为标签，涵盖视频的主题、场景、情感等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"summary": "你的简介", "tags": ["标签1", "标签2", ...]}}

转写文本：
{transcript_text}
"""


# ── OmlxSummarizer ───────────────────────────────────────────────

class OmlxSummarizer(Summarizer):
    """Call a local OpenAI-compatible model server (OMLX) to summarize transcript text.

    Parameters
    ----------
    config:
        Application-wide configuration containing OMLX endpoint and model settings.
    model:
        Override the text model name from config defaults (``Qwen3.6-35B-A3B``).
        Useful when testing with a smaller model like ``"Qwen2.5-7B-Instruct"``.

    Examples
    --------
    >>> config = AppConfig(  # doctest: +SKIP
    ...     env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="test-key"),
    ...     prefs=Prefs(text_model="Qwen3.6-35B-A3B"),
    ... )
    >>> summarizer = OmlxSummarizer(config)  # doctest: +SKIP
    """

    def __init__(self, config: AppConfig, model: str | None = None) -> None:
        self._config = config
        self._model = model or config.prefs.text_model

    def summarize(self, transcript_text: str) -> SummaryResult:
        """Summarize A-roll transcript text via OMLX structured output.

        1. Builds a Chinese prompt with the transcript inserted.
        2. Sends to OMLX /chat/completions using OpenAI Python client with
           ``response_format={"type": "json_schema", ...}`` for structured output.
        3. Parses the JSON response into a :class:`SummaryResult`.

        Parameters
        ----------
        transcript_text:
            The full transcription text from mlx-whisper (typically Chinese).

        Returns
        -------
        SummaryResult
            With ``summary`` (Chinese intro) and ``tags`` (list of strings).

        Raises
        ------
        RuntimeError
            If the OMLX call fails (connection error, bad response, etc.).
        """
        if not transcript_text or not transcript_text.strip():
            return SummaryResult(summary="", tags=[])

        import json as _json  # lazy to avoid top-level cold start

        from openai import OpenAI, APIConnectionError

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )

        json_schema = {
            "name": "summary_result",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["summary", "tags"],
            },
        }

        prompt = _SUMMARIZE_PROMPT.format(transcript_text=transcript_text)
        max_retries = 2

        for attempt in range(1 + max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_schema", "json_schema": json_schema},
                )
            except APIConnectionError as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX connection failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue  # retry on connection error

            except Exception as e:  # noqa: BLE001 — catch-all for unexpected LLM errors
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX request failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue  # retry on other errors

            # Parse structured output
            choice = response.choices[0]
            if choice.message.refusal:  # - model refusal -> retry
                continue  # retry on refusal (model may succeed next attempt)

            raw_content = choice.message.content
            if not raw_content:
                continue  # retry on empty

            try:
                data = _json.loads(raw_content)
            except (ValueError, TypeError):
                continue  # retry on non-JSON

            summary = data.get("summary", "") or ""
            tags_raw: Any = data.get("tags")

            # Validate returned structure before accepting
            if not summary:
                continue  # retry: nothing useful returned

            if not isinstance(tags_raw, list) or any(
                not isinstance(t, str) for t in tags_raw
            ):
                continue  # retry: malformed tags

            return SummaryResult(summary=summary, tags=list(tags_raw))

        raise RuntimeError(
            "OMLX summarizer returned no valid result after retries"
        )
