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
from ..domain.models import CutSuggestion, Segment, SummaryResult
from ..ports.ai import Summarizer

# ── prompt template ────────────────────────────────────────────────

_SUMMARIZE_PROMPT_ZH = """\
你是一个专业的视频内容整理助手。请根据以下A-roll（有解说）视频的转写文本，完成两件事：

1. **简介**：用中文撰写一段简洁的概述（30-80字），概括视频的核心内容和主题。
2. **标签**：提取5-10个关键词/短语作为标签，涵盖视频的主题、场景、情感等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"summary": "你的简介", "tags": ["标签1", "标签2", ...]}}

转写文本：
{transcript_text}
"""

_SUMMARIZE_PROMPT_EN = """\
You are a professional video content organization assistant. Based on the \
transcript of the following A-roll (narrated) video, do two things:

1. **Summary**: Write a concise overview in English (30-80 words) capturing the \
core content and theme.
2. **Tags**: Extract 5-10 keywords/phrases as tags covering theme, scene, \
emotion, etc.

Reply ONLY in the following JSON format (no extra content):
{{"summary": "your summary", "tags": ["tag1", "tag2", ...]}}

Transcript:
{transcript_text}
"""

_SUMMARIZE_PROMPTS = {"zh": _SUMMARIZE_PROMPT_ZH, "en": _SUMMARIZE_PROMPT_EN}

_CUTS_PROMPT_ZH = """\
你是专业的视频剪辑助手。下面是一段 A-roll（有解说）视频的转写，已按句子编号并标注时间。\
请挑出最值得保留、最精彩或信息量最大的最多 {n} 段，按精彩程度从高到低排序。

要求：
- 每段用**起始句子编号**和**结束句子编号**表示（可只含一句，即 start == end）。
- 只能使用下面列出的句子编号，不要编造时间。
- 每段给一句话理由。

请仅以如下 JSON 回复（不要其他内容）：
{{"cuts": [{{"start": 起始编号, "end": 结束编号, "reason": "理由"}}, ...]}}

句子列表：
{segments}
"""

_CUTS_PROMPT_EN = """\
You are a professional video editing assistant. Below is the transcript of an \
A-roll (narrated) video, numbered by sentence with timestamps. Pick up to {n} \
best stretches to keep — the most compelling or information-rich — ranked best first.

Rules:
- Express each stretch by its **start sentence index** and **end sentence index** \
(a single sentence is fine: start == end).
- Use only the sentence indices listed below; do not invent timecodes.
- Give a one-line reason for each.

Reply ONLY as the following JSON (no extra content):
{{"cuts": [{{"start": start_index, "end": end_index, "reason": "reason"}}, ...]}}

Sentences:
{segments}
"""

_CUTS_PROMPTS = {"zh": _CUTS_PROMPT_ZH, "en": _CUTS_PROMPT_EN}


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

        from openai import OpenAI, APIConnectionError

        from ._jsonparse import parse_json_object

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )

        prompt_template = _SUMMARIZE_PROMPTS.get(
            self._config.prefs.output_language, _SUMMARIZE_PROMPT_ZH
        )
        prompt = prompt_template.format(transcript_text=transcript_text)
        max_retries = 2

        for attempt in range(1 + max_retries):
            try:
                # NOTE: no strict json_schema response_format — grammar-constrained
                # decoding makes the quantized MLX models collapse into a repetition
                # loop. We prompt for JSON and parse it leniently, capping max_tokens.
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.7,
                    # Disable Qwen3 thinking so the token budget goes to the JSON
                    # answer instead of being spent on a <think> block. Passed via
                    # the chat template (same knob OpenWebUI exposes).
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
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

            data = parse_json_object(raw_content)
            if data is None:
                continue  # retry on non-JSON / unparseable output

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

    def recommend_cuts(self, segments: list[Segment], n: int) -> list[CutSuggestion]:
        """Pick up to *n* cut windows from timed transcript *segments* (A-roll).

        The model selects by sentence index ranges, which the adapter maps back to
        ``start_s``/``end_s`` — so the model can't hallucinate timecodes.
        Representative frames are left unset (the orchestrator grabs them).
        """
        if not segments or n <= 0:
            return []

        from openai import OpenAI, APIConnectionError

        from ._jsonparse import parse_json_object

        numbered = "\n".join(
            f"[{i}] ({s.start_s:.1f}-{s.end_s:.1f}s) {s.text}"
            for i, s in enumerate(segments)
        )
        prompt_template = _CUTS_PROMPTS.get(self._config.prefs.output_language, _CUTS_PROMPT_ZH)
        prompt = prompt_template.format(n=n, segments=numbered)

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )
        max_retries = 2
        for attempt in range(1 + max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.4,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            except APIConnectionError as e:
                if attempt == max_retries:
                    raise RuntimeError(f"OMLX connection failed after {1 + max_retries} attempt(s): {e}") from e
                continue
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries:
                    raise RuntimeError(f"OMLX request failed after {1 + max_retries} attempt(s): {e}") from e
                continue

            raw = response.choices[0].message.content
            data = parse_json_object(raw) if raw else None
            if data is None:
                continue
            cuts_raw = data.get("cuts")
            if not isinstance(cuts_raw, list):
                continue

            suggestions = self._build_cuts(cuts_raw, segments, n)
            if suggestions:
                return suggestions
            # Valid JSON but no usable cut → don't loop forever; accept empty.
            return []

        raise RuntimeError("OMLX cut recommender returned no valid result after retries")

    @staticmethod
    def _build_cuts(
        cuts_raw: list[Any], segments: list[Segment], n: int,
    ) -> list[CutSuggestion]:
        """Validate model output and map sentence-index ranges to CutSuggestions."""
        last = len(segments) - 1
        out: list[CutSuggestion] = []
        for item in cuts_raw:
            if not isinstance(item, dict):
                continue
            raw_start = item.get("start")
            if raw_start is None:
                continue
            raw_end = item.get("end")
            try:
                start_i = int(raw_start)
                end_i = int(raw_end) if raw_end is not None else start_i
            except (TypeError, ValueError):
                continue
            start_i = max(0, min(start_i, last))
            end_i = max(start_i, min(end_i, last))
            reason = item.get("reason") or ""
            out.append(CutSuggestion(
                rank=len(out) + 1,
                start_s=segments[start_i].start_s,
                end_s=segments[end_i].end_s,
                reason=reason if isinstance(reason, str) else "",
                frame_path=None,
                source="text",
            ))
            if len(out) >= n:
                break
        return out
