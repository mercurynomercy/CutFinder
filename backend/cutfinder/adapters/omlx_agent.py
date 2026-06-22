"""OmlxAgentClient — one tool-calling turn against the OMLX text model.

Implements :class:`LLMAgentClient` by calling OMLX's OpenAI-compatible
``/chat/completions`` with the director's tool schemas. Reuses the same
endpoint/key/model resolution as :class:`OmlxSummarizer`.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import AppConfig
from ..ports.cutplan import AgentStep, ToolCall


class OmlxAgentClient:
    """Tool-calling client for the rough-cut director (text model)."""

    def __init__(self, config: AppConfig, model: str | None = None) -> None:
        self._config = config
        self._model = model or config.env.TEXT_MODEL.strip() or config.prefs.text_model

    def run(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
    ) -> AgentStep:
        from openai import APIConnectionError, OpenAI

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )

        max_retries = 2
        for attempt in range(1 + max_retries):
            try:
                response = client.chat.completions.create(  # type: ignore[call-overload]
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=2048,
                    temperature=0.7,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            except APIConnectionError as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX connection failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue
            except Exception as e:  # noqa: BLE001 — retry unexpected LLM errors
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX agent request failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue

            msg = response.choices[0].message
            tool_calls: list[ToolCall] = []
            for tc in (msg.tool_calls or []):
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args if isinstance(args, dict) else {},
                ))
            return AgentStep(content=msg.content or "", tool_calls=tool_calls)

        raise RuntimeError("OMLX agent returned no result after retries")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        """Plain chat completion (no tools) → raw assistant text.

        Used by the staged generator, which is far more reliable on local
        models than autonomous multi-round tool calling.
        """
        from openai import APIConnectionError, OpenAI

        client = OpenAI(
            base_url=self._config.env.OMLX_BASE_URL,
            api_key=self._config.env.OMLX_API_KEY,
        )

        max_retries = 2
        for attempt in range(1 + max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    # Staged generation runs one call per shooting date, so one
                    # day's shot list is small; this cap is generous for that yet
                    # stops a runaway model from looping for minutes on one call.
                    max_tokens=8192,
                    # Low temperature → more deterministic, less likely to fall
                    # into a repetition loop while emitting structured JSON.
                    temperature=0.3,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            except APIConnectionError as e:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX connection failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries:
                    raise RuntimeError(
                        f"OMLX request failed after {1 + max_retries} attempt(s): {e}"
                    ) from e
                continue

            return response.choices[0].message.content or ""

        raise RuntimeError("OMLX agent returned no completion after retries")
