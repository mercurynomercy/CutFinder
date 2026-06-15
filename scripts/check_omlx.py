"""Verify the OMLX server is reachable and required models are loaded.

Reads OMLX_BASE_URL / OMLX_API_KEY from the environment (or .env via the
caller) and checks that both the text and vision models CutFinder needs are
present. Exits non-zero with a clear message on any failure.
"""

from __future__ import annotations

import os
import sys

import httpx

REQUIRED_MODELS = ["qwen3.6-35b-a3b", "qwen3-vl-8b"]


def main() -> int:
    base = os.environ.get("OMLX_BASE_URL", "http://localhost:8000/v1")
    key = os.environ.get("OMLX_API_KEY", "")
    if not key:
        print("OMLX_API_KEY is empty — set it in .env", file=sys.stderr)
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
