"""OpenAIVisionTagger — B-roll visual tagging via a local OpenAI-compatible server (vision model).

Reads frame image paths, encodes as base64 data URIs, sends to the
configured server's ``/chat/completions`` endpoint with multi-frame visual messages,
and parses structured JSON output into a :class:`VisionResult`.

Edge cases handled:
  * Empty ``frame_paths`` → returns empty VisionResult (no network call).
  * Server unavailable (connection error) → raises ``RuntimeError`` with detail.
  * Malformed LLM response (missing keys) → falls back to empty strings/lists; retries.

Examples
--------
>>> config = AppConfig(env=EnvSettings(OPENAI_BASE_URL="http://localhost:8000/v1", OPENAI_API_KEY="key"), prefs=Prefs())
>>> tagger = OpenAIVisionTagger(config)  # doctest: +SKIP
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
from .vision_prompts import (
    KEYFRAMES_PROMPT_ZH,
    KEYFRAMES_PROMPTS,
    VISION_PROMPT_ZH,
    VISION_PROMPTS,
)

# Bound HTTP calls to the OpenAI-compatible server so a hung model server can't block the worker forever.
# Generous read window — local MLX generation of the capped token budgets here
# takes seconds, not minutes; a truly stuck request times out, is retried, then
# surfaces as a task error rather than an indefinite hang.
_REQUEST_TIMEOUT_S = 120.0

# ── OpenAIVisionTagger ─────────────────────────────────────────────

class OpenAIVisionTagger(VisionTagger):
    """Call a local OpenAI-compatible vision model server to tag B-roll frames.

    Parameters
    ----------
    config:
        Application-wide configuration containing the OpenAI-compatible endpoint and model settings.
    model:
        Override the vision model name from config defaults (``Qwen3-VL-8B``).
        Useful when testing with a smaller model.

    Examples
    --------
    >>> config = AppConfig(  # doctest: +SKIP
    ...     env=EnvSettings(OPENAI_BASE_URL="http://localhost:8000/v1", OPENAI_API_KEY="test-key"),
    ...     prefs=Prefs(vision_model="Qwen3-VL-8B"),
    ... )
    >>> tagger = OpenAIVisionTagger(config)  # doctest: +SKIP
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
        """Tag B-roll frames via structured output from the configured vision server.

        1. Reads each frame image and encodes as base64 data URI
           (``data:image/png;base64,<base64>``).
        2. Sends all frames in a single multi-frame visual message to the
           OpenAI-compatible server with the Chinese prompt appended as text.
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
            If the request to the OpenAI-compatible server fails (connection error, bad response, etc.).
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
        prompt = VISION_PROMPTS.get(self._config.prefs.output_language, VISION_PROMPT_ZH)
        image_parts = [_encode_frame(p) for p in frame_paths]
        text_part: dict[str, str] = {"type": "text", "text": prompt}
        content: list[dict[str, Any]] = [text_part] + image_parts

        max_retries = 2

        for attempt in range(1 + max_retries):
            try:
                client = OpenAI(
                    base_url=self._config.env.OPENAI_BASE_URL,
                    api_key=self._config.env.OPENAI_API_KEY,
                    timeout=_REQUEST_TIMEOUT_S,
                )

                # NOTE: no strict json_schema response_format — grammar-constrained
                # decoding makes the quantized MLX vision model collapse into a
                # repetition loop. We prompt for JSON and parse it leniently
                # instead, and cap max_tokens so a misbehaving model can't hang.
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],  # type: ignore[list-item,misc]  # the server accepts plain dict messages
                    max_tokens=512,
                    temperature=0.7,
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
            "vision tagger returned no valid result after retries"
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
        prompt = KEYFRAMES_PROMPTS.get(
            self._config.prefs.output_language, KEYFRAMES_PROMPT_ZH,
        ).format(n=n, frames=listing)
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content += [_encode(p) for p, _ in ordered]

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
                    messages=[{"role": "user", "content": content}],  # type: ignore[list-item,misc]
                    max_tokens=512,
                    temperature=0.4,
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
            picks = data.get("keyframes")
            if not isinstance(picks, list):
                continue
            suggestions = self._build_keyframes(picks, ordered, timestamps, half, n)
            return suggestions  # valid JSON → accept (even if empty)

        raise RuntimeError("keyframe recommender returned no valid result after retries")

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
