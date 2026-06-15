"""Lenient JSON-object extraction from chatty / fenced LLM output.

The OMLX adapters no longer use strict ``response_format`` json_schema
(it makes the quantized MLX models collapse into repetition loops), so the
model returns the JSON as free text — possibly wrapped in ```json fences or
with a little surrounding prose. This recovers the first JSON object.
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str | None) -> dict[str, Any] | None:
    """Return the first JSON *object* found in *text*, or ``None``.

    Handles plain JSON, ```json fenced blocks, and JSON embedded in prose.
    """
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped[:4].lower() == "json":
            stripped = stripped[4:]
        stripped = stripped.strip()

    for candidate in (stripped, _first_brace_block(text)):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj

    return None


def _first_brace_block(text: str) -> str | None:
    """Return the substring from the first ``{`` to the last ``}`` (greedy)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None
