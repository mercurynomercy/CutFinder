"""Verify the OMLX server is reachable and required models are loaded.

Reads OMLX_BASE_URL / OMLX_API_KEY via CutFinder's config layer
(`~/.cutfinder/config.json` > OS env var) and checks that
both the text and vision models CutFinder needs are present.
Exits non-zero with a clear message on any failure.

Usage from CLI::

    python scripts/check_omlx.py
"""

from __future__ import annotations

import sys
from typing import Tuple  # noqa: E402

# Import early so cutfinder is on the path; scripts/ lives at repo root,
# same level as backend/, so this works when run from the repo root.
import cutfinder.config  # noqa: E401

from cutfinder.config import resolve_env  # noqa: E402
import httpx  # noqa: E402

REQUIRED_MODELS = ["qwen3.6-35b-a3b", "qwen3-vl-8b"]


def _resolve_omlx_config() -> Tuple[str, str]:
    """Return ``(base_url, api_key)`` using the same precedence as the app.

    Priority: ``~/.cutfinder/config.json`` > OS env var.
    Falls back to the default OMLX URL if no base_url is set anywhere.

    Extracted as a separate function for testability — tests can patch
    ``cutfinder.config.resolve_env`` without needing a real OMLX server.
    """

    env = resolve_env()
    base_url = env.OMLX_BASE_URL or "http://localhost:8000/v1"
    api_key = env.OMLX_API_KEY

    return base_url, api_key


def main() -> int:
    base, key = _resolve_omlx_config()

    if not key:
        print("OMLX_API_KEY is empty — set it in the Settings UI or as an env var", file=sys.stderr)
        return 1

    try:
        resp = httpx.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"OMLX unreachable at {base}: {exc}", file=sys.stderr)
        return 1

    models = [m["id"] for m in resp.json().get("data", [])]
    print("OMLX OK — models:", models)

    missing = [
        m for m in REQUIRED_MODELS
        if not any(m.lower() in mid.lower() for mid in models)
    ]
    if missing:
        print("Missing required OMLX models: " + ", ".join(missing), file=sys.stderr)
        return 1

    print("All required text/vision models are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
