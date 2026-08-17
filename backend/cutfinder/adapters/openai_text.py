"""OpenAITextSummarizer — A-roll text summary + tags via a local OpenAI-compatible server.

Calls the configured server's ``/chat/completions`` endpoint with
structured JSON output to produce a Chinese summary and tag list from
transcript text.

Edge cases handled:
  * Missing ``full_text`` or empty string → returns empty SummaryResult.
  * Server unavailable (connection error) → raises ``RuntimeError`` with detail.
  * Malformed LLM response (missing keys) → falls back to empty strings/lists.

Examples
--------
>>> config = AppConfig(env=EnvSettings(OPENAI_BASE_URL="http://localhost:8000/v1", OPENAI_API_KEY="key"), prefs=Prefs())
>>> summarizer = OpenAITextSummarizer(config)  # doctest: +SKIP
>>> result = summarizer.summarize("这是一段关于旅行的视频...")  # doctest: +SKIP
>>> print(result.summary)
"""

from __future__ import annotations

from typing import Any

from ..config import AppConfig
from ..domain.models import CutSuggestion, Segment, SummaryResult
from ..ports.ai import Summarizer
from .text_prompts import CUTS_PROMPT_ZH, CUTS_PROMPTS, SUMMARIZE_PROMPT_ZH, SUMMARIZE_PROMPTS

# Bound HTTP calls to the OpenAI-compatible server so a hung model server can't block the worker forever.
# Generous read window — local MLX generation of the capped token budgets here
# takes seconds, not minutes; a truly stuck request times out, is retried, then
# surfaces as a task error rather than an indefinite hang.
_REQUEST_TIMEOUT_S = 120.0

# ── OpenAITextSummarizer ───────────────────────────────────────────────

class OpenAITextSummarizer(Summarizer):
    """Call a local OpenAI-compatible model server to summarize transcript text.

    Parameters
    ----------
    config:
        Application-wide configuration containing the OpenAI-compatible endpoint and model settings.
    model:
        Override the text model name from config defaults (``Qwen3.6-35B-A3B``).
        Useful when testing with a smaller model like ``"Qwen2.5-7B-Instruct"``.

    Examples
    --------
    >>> config = AppConfig(  # doctest: +SKIP
    ...     env=EnvSettings(OPENAI_BASE_URL="http://localhost:8000/v1", OPENAI_API_KEY="test-key"),
    ...     prefs=Prefs(text_model="Qwen3.6-35B-A3B"),
    ... )
    >>> summarizer = OpenAITextSummarizer(config)  # doctest: +SKIP
    """

    def __init__(self, config: AppConfig, model: str | None = None) -> None:
        self._config = config
        # Precedence: explicit override > global/env > per-library prefs.
        self._model = (
            model
            or config.env.TEXT_MODEL.strip()
            or config.prefs.text_model
        )

    def summarize(self, transcript_text: str) -> SummaryResult:
        """Summarize A-roll transcript text via structured output from the configured server.

        1. Builds a Chinese prompt with the transcript inserted.
        2. Sends to the OpenAI-compatible server's /chat/completions using the
           OpenAI Python client with ``response_format={"type": "json_schema", ...}``
           for structured output.
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
            If the request to the OpenAI-compatible server fails (connection error, bad response, etc.).
        """
        if not transcript_text or not transcript_text.strip():
            return SummaryResult(summary="", tags=[])

        from openai import OpenAI, APIConnectionError

        from ._jsonparse import parse_json_object

        client = OpenAI(
            base_url=self._config.env.OPENAI_BASE_URL,
            api_key=self._config.env.OPENAI_API_KEY,
            timeout=_REQUEST_TIMEOUT_S,
        )

        prompt_template = SUMMARIZE_PROMPTS.get(
            self._config.prefs.output_language, SUMMARIZE_PROMPT_ZH
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
                        f"connection to the OpenAI-compatible server failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue  # retry on connection error

            except Exception as e:  # noqa: BLE001 — catch-all for unexpected LLM errors
                if attempt == max_retries:
                    raise RuntimeError(
                        f"request to the OpenAI-compatible server failed after {1 + max_retries} attempt(s): {e}"
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
            "text summarizer returned no valid result after retries"
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
        prompt_template = CUTS_PROMPTS.get(self._config.prefs.output_language, CUTS_PROMPT_ZH)
        prompt = prompt_template.format(n=n, segments=numbered)

        client = OpenAI(
            base_url=self._config.env.OPENAI_BASE_URL,
            api_key=self._config.env.OPENAI_API_KEY,
            timeout=_REQUEST_TIMEOUT_S,
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
                    raise RuntimeError(f"connection to the OpenAI-compatible server failed after {1 + max_retries} attempt(s): {e}") from e
                continue
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries:
                    raise RuntimeError(f"request to the OpenAI-compatible server failed after {1 + max_retries} attempt(s): {e}") from e
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

        raise RuntimeError("cut recommender returned no valid result after retries")

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

