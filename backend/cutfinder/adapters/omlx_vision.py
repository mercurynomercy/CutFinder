"""OmlxVisionTagger — B-roll visual tagging via OMLX (vision model).

Reads frame image paths, encodes as base64 data URIs, sends to the local
OMLX server's ``/chat/completions`` endpoint with multi-frame visual messages,
and parses structured JSON output into a :class:`VisionResult`.

Edge cases handled:
  * Empty ``frame_paths`` → returns empty VisionResult (no network call).
  * OMLX unavailable (connection error) → raises ``RuntimeError`` with detail.
  * Malformed LLM response (missing keys) → falls back to empty strings/lists; retries.

Examples
--------
>>> config = AppConfig(env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="key"), prefs=Prefs())
>>> tagger = OmlxVisionTagger(config)  # doctest: +SKIP
>>> result = tagger.describe([Path("frame1.png"), Path("frame2.png")])  # doctest: +SKIP
>>> print(result.description)
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ..config import AppConfig, _DEFAULT_VISION_MODEL
from ..domain.models import VisionResult
from ..ports.ai import VisionTagger

# ── prompt template ────────────────────────────────────────────────

_VISION_PROMPT = """\
你是一个专业的视频画面分析助手。请仔细观察以下多张从视频中提取的画面帧，完成两件事：

1. **画面描述**：用中文撰写一段简洁的描述（30-80字），概括这些帧中看到的视觉内容、场景、人物动作等。
2. **标签**：提取5-10个关键词/短语作为视觉标签，涵盖场景、物体、色彩、氛围等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"description": "你的画面描述", "tags": ["标签1", "标签2", ...]}}

以下是多帧画面（按时间顺序排列）：
"""


# ── OmlxVisionTagger ─────────────────────────────────────────────

class OmlxVisionTagger(VisionTagger):
    """Call a local OpenAI-compatible vision model server (OMLX) to tag B-roll frames.

    Parameters
    ----------
    config:
        Application-wide configuration containing OMLX endpoint and model settings.
    model:
        Override the vision model name from config defaults (``Qwen3-VL-8B``).
        Useful when testing with a smaller model.

    Examples
    --------
    >>> config = AppConfig(  # doctest: +SKIP
    ...     env=EnvSettings(OMLX_BASE_URL="http://localhost:8000/v1", OMLX_API_KEY="test-key"),
    ...     prefs=Prefs(vision_model="Qwen3-VL-8B"),
    ... )
    >>> tagger = OmlxVisionTagger(config)  # doctest: +SKIP
    """

    def __init__(self, config: AppConfig, model: str | None = None) -> None:
        self._config = config
        self._model = model or config.prefs.vision_model

    def describe(self, frame_paths: list[Path]) -> VisionResult:
        """Tag B-roll frames via OMLX vision model structured output.

        1. Reads each frame image and encodes as base64 data URI
           (``data:image/png;base64,<base64>``).
        2. Sends all frames in a single multi-frame visual message to OMLX
           with the Chinese prompt appended as text.
        3. Parses structured JSON response into :class:`VisionResult`.

        Parameters
        ----------
        frame_paths:
            List of paths to PNG/JPEG frame images extracted by a FrameExtractor.

        Returns
        -------
        VisionResult
            With ``description`` (Chinese visual description) and ``tags`` (list of strings).

        Raises
        ------
        RuntimeError
            If the OMLX call fails (connection error, bad response, etc.).
        """
        if not frame_paths:
            return VisionResult(description="", tags=[])

        import json as _json  # lazy to avoid top-level cold start
        from openai import OpenAI, APIConnectionError  # type: ignore[import]

        def _encode_frame(path: Path) -> dict[str, Any]:
            """Read image file and return base64 data URI dict."""
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }

        # Build multi-frame visual message: one text + N images in single user message
        image_parts = [_encode_frame(p) for p in frame_paths]
        text_part: dict[str, str] = {"type": "text", "text": _VISION_PROMPT}
        content: list[dict[str, Any]] = [text_part] + image_parts

        max_retries = 2
        prompt_text = _VISION_PROMPT

        for attempt in range(1 + max_retries):
            try:
                client = OpenAI(
                    base_url=self._config.env.OMLX_BASE_URL,
                    api_key=self._config.env.OMLX_API_KEY,
                )

                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],
                    response_format={"type": "json_schema", "json_schema": {
                        "name": "vision_result",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["description", "tags"],
                        },
                    }},
                )

            except APIConnectionError as e:  # type: ignore[attr-defined]
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX vision connection failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue  # retry on connection error

            except Exception as e:  # noqa: BLE001 — catch-all for unexpected LLM errors
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX vision request failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue  # retry on other errors

            # Parse structured output
            choice = response.choices[0]
            if choice.message.refusal:  # type: ignore[attr-defined]
                continue  # retry on refusal

            raw_content = choice.message.content
            if not raw_content:
                continue  # retry on empty

            try:
                data = _json.loads(raw_content)
            except (ValueError, TypeError):
                continue  # retry on non-JSON

            description = data.get("description", "") or ""
            tags_raw: Any = data.get("tags")

            # Validate returned structure before accepting
            if not description:
                continue  # retry: nothing useful

            if not isinstance(tags_raw, list) or any(
                not isinstance(t, str) for t in tags_raw  # type: ignore[arg-type]
            ):
                continue  # retry: malformed tags

            return VisionResult(description=description, tags=list(tags_raw))

        raise RuntimeError(
            "OMLX vision tagger returned no valid result after retries"
        )
