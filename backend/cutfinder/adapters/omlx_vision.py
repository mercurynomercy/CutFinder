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

from ..config import AppConfig
from ..domain.models import CutSuggestion, VisionResult
from ..ports.ai import VisionTagger

# ── prompt template ────────────────────────────────────────────────

_VISION_PROMPT_ZH = """\
你是一个专业的视频画面分析助手。请仔细观察以下多张从视频中提取的画面帧，完成两件事：

1. **画面描述**：用中文撰写一段简洁的描述（30-80字），概括这些帧中看到的视觉内容、场景、人物动作等。
2. **标签**：提取5-10个关键词/短语作为视觉标签，涵盖场景、物体、色彩、氛围等维度。

请以如下JSON格式回复（不要添加任何其他内容）：
{{"description": "你的画面描述", "tags": ["标签1", "标签2", ...]}}

以下是多帧画面（按时间顺序排列）：
"""

_VISION_PROMPT_EN = """\
You are a professional video frame analysis assistant. Carefully examine the \
following frames extracted from a video and do two things:

1. **Description**: Write a concise description in English (30-80 words) \
summarizing the visual content, scenes, and actions seen in these frames.
2. **Tags**: Extract 5-10 keywords/phrases as visual tags covering scene, \
objects, color, mood, etc.

Reply ONLY in the following JSON format (no extra content):
{{"description": "your description", "tags": ["tag1", "tag2", ...]}}

The frames below are in chronological order:
"""

_VISION_PROMPTS = {"zh": _VISION_PROMPT_ZH, "en": _VISION_PROMPT_EN}

_KEYFRAMES_PROMPT_ZH = """\
你是专业的视频剪辑助手。下面按时间顺序给出从一段 B-roll（无解说）视频采样的若干帧，\
每帧标注了编号和时间戳。请挑出画面最好、最适合做封面或剪辑代表的最多 {n} 帧，按好坏排序。

只能使用下面列出的帧编号。请仅以如下 JSON 回复（不要其他内容）：
{{"keyframes": [{{"index": 帧编号, "reason": "一句话理由"}}, ...]}}

帧清单（编号 / 时间）：
{frames}
"""

_KEYFRAMES_PROMPT_EN = """\
You are a professional video editing assistant. Below are frames sampled in \
chronological order from a B-roll (no narration) video, each labeled with an \
index and timestamp. Pick up to {n} best frames — most striking / best as a \
cover or edit representative — ranked best first.

Use only the frame indices listed below. Reply ONLY as the following JSON \
(no extra content):
{{"keyframes": [{{"index": frame_index, "reason": "one-line reason"}}, ...]}}

Frames (index / time):
{frames}
"""

_KEYFRAMES_PROMPTS = {"zh": _KEYFRAMES_PROMPT_ZH, "en": _KEYFRAMES_PROMPT_EN}


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
        # Precedence: explicit override > global/env > per-library prefs.
        self._model = (
            model
            or config.env.VISION_MODEL.strip()
            or config.prefs.vision_model
        )

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

        from openai import OpenAI, APIConnectionError

        from ._jsonparse import parse_json_object

        def _encode_frame(path: Path) -> dict[str, Any]:
            """Read image file and return base64 data URI dict (mime by suffix)."""
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }

        # Build multi-frame visual message: one text + N images in single user message
        prompt = _VISION_PROMPTS.get(self._config.prefs.output_language, _VISION_PROMPT_ZH)
        image_parts = [_encode_frame(p) for p in frame_paths]
        text_part: dict[str, str] = {"type": "text", "text": prompt}
        content: list[dict[str, Any]] = [text_part] + image_parts

        max_retries = 2

        for attempt in range(1 + max_retries):
            try:
                client = OpenAI(
                    base_url=self._config.env.OMLX_BASE_URL,
                    api_key=self._config.env.OMLX_API_KEY,
                )

                # NOTE: no strict json_schema response_format — grammar-constrained
                # decoding makes the quantized MLX vision model collapse into a
                # repetition loop. We prompt for JSON and parse it leniently
                # instead, and cap max_tokens so a misbehaving model can't hang.
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],  # type: ignore[list-item,misc]  # OMLX accepts plain dict messages
                    max_tokens=512,
                    temperature=0.7,
                )

            except APIConnectionError as e:
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
            if choice.message.refusal:
                continue  # retry on refusal

            raw_content = choice.message.content
            if not raw_content:
                continue  # retry on empty

            data = parse_json_object(raw_content)
            if data is None:
                continue  # retry on non-JSON / unparseable output

            description = data.get("description", "") or ""
            tags_raw: Any = data.get("tags")

            # Validate returned structure before accepting
            if not description:
                continue  # retry: nothing useful

            if not isinstance(tags_raw, list) or any(
                not isinstance(t, str) for t in tags_raw
            ):
                continue  # retry: malformed tags

            return VisionResult(description=description, tags=list(tags_raw))

        raise RuntimeError(
            "OMLX vision tagger returned no valid result after retries"
        )

    def recommend_keyframes(
        self, frames: list[tuple[Path, float]], n: int,
    ) -> list[CutSuggestion]:
        """Pick up to *n* best frames from sampled ``(frame, timestamp_s)`` pairs (B-roll).

        Sends all frames (chronological), asks the vision model for the best frame
        indices, and maps each pick to a CutSuggestion whose ``frame_path`` is the
        chosen frame and whose cut window spans roughly one sampling gap around it.
        """
        if not frames or n <= 0:
            return []

        from openai import OpenAI, APIConnectionError

        from ._jsonparse import parse_json_object

        ordered = sorted(frames, key=lambda fp: fp[1])
        timestamps = [ts for _, ts in ordered]
        half = self._window_half(timestamps)

        def _encode(path: Path) -> dict[str, Any]:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}

        listing = "\n".join(f"[{i}] {ts:.1f}s" for i, ts in enumerate(timestamps))
        prompt = _KEYFRAMES_PROMPTS.get(
            self._config.prefs.output_language, _KEYFRAMES_PROMPT_ZH,
        ).format(n=n, frames=listing)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content += [_encode(p) for p, _ in ordered]

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )
        max_retries = 2
        for attempt in range(1 + max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],  # type: ignore[list-item,misc]
                    max_tokens=512,
                    temperature=0.4,
                )
            except APIConnectionError as e:
                if attempt == max_retries:
                    raise RuntimeError(f"OMLX vision connection failed after {1 + max_retries} attempt(s): {e}") from e
                continue
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries:
                    raise RuntimeError(f"OMLX vision request failed after {1 + max_retries} attempt(s): {e}") from e
                continue

            raw = response.choices[0].message.content
            data = parse_json_object(raw) if raw else None
            if data is None:
                continue
            picks = data.get("keyframes")
            if not isinstance(picks, list):
                continue
            suggestions = self._build_keyframes(picks, ordered, timestamps, half, n)
            return suggestions  # valid JSON → accept (even if empty)

        raise RuntimeError("OMLX keyframe recommender returned no valid result after retries")

    @staticmethod
    def _window_half(timestamps: list[float]) -> float:
        """Half-width (seconds) of the cut window around a chosen frame."""
        if len(timestamps) < 2:
            return 1.0
        gaps = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
        avg = sum(gaps) / len(gaps) if gaps else 2.0
        return max(0.5, avg / 2.0)

    @staticmethod
    def _build_keyframes(
        picks: list[Any],
        ordered: list[tuple[Path, float]],
        timestamps: list[float],
        half: float,
        n: int,
    ) -> list[CutSuggestion]:
        last = len(ordered) - 1
        out: list[CutSuggestion] = []
        seen: set[int] = set()
        for item in picks:
            if not isinstance(item, dict):
                continue
            raw_idx = item.get("index")
            if raw_idx is None:
                continue
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            idx = max(0, min(idx, last))
            if idx in seen:
                continue
            seen.add(idx)
            ts = timestamps[idx]
            reason = item.get("reason") or ""
            out.append(CutSuggestion(
                rank=len(out) + 1,
                start_s=max(0.0, ts - half),
                end_s=ts + half,
                reason=reason if isinstance(reason, str) else "",
                frame_path=str(ordered[idx][0]),
                source="vision",
            ))
            if len(out) >= n:
                break
        return out
