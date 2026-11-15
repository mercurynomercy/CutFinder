"""OpenAICueSegmenter — subtitle line-break selection via a local OpenAI-compatible server."""

from __future__ import annotations

import logging
import re

from ..config import AppConfig
from ..ports.speech import SegmenterUnavailable
from .text_prompts import SEGMENT_PROMPT_ZH

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 120.0


class OpenAICueSegmenter:
    """Ask the text model to insert ``|`` line breaks into a transcript window."""

    def __init__(self, config: AppConfig, model: str | None = None) -> None:
        self._config = config
        self._model = model or config.env.TEXT_MODEL.strip() or config.prefs.text_model

    def split(self, text: str) -> str | None:
        """Return *text* with ``|`` breaks, None on soft failure.

        Raises SegmenterUnavailable on connection error / timeout.
        """
        from openai import APIConnectionError, OpenAI

        client = OpenAI(
            base_url=self._config.env.OPENAI_BASE_URL,
            api_key=self._config.env.OPENAI_API_KEY,
            timeout=_REQUEST_TIMEOUT_S,
            max_retries=0,
        )
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": SEGMENT_PROMPT_ZH.format(text=text)}],
                temperature=0,
                max_tokens=max(512, 3 * len(text)),
                # Reasoning models return no content unless thinking is disabled.
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except APIConnectionError as exc:  # also covers APITimeoutError
            raise SegmenterUnavailable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - soft failure, caller falls back to rules
            logger.warning("cue segmenter request failed: %s", exc)
            return None

        content = response.choices[0].message.content or ""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        content = re.sub(r"^.*?</think>", "", content, flags=re.DOTALL).strip()
        return content or None
