"""OMLX health-check utility.

Extracted from the Makefile ``check-omlx`` target so it can be unit-tested
with fake HTTP responses.

Usage from CLI::

    python -m cutfinder.adapters.omlx_check
"""

from __future__ import annotations

import httpx  # noqa: E402
import sys as _sys


def check_omlx(
    base_url: str,
    api_key: str,
    expected_models: list[str] | None = None,
) -> list[str]:
    """Probe the OMLX server and return a sorted list of model IDs.

    Parameters
    ----------
    base_url:
        OMLX API base URL, e.g. ``http://localhost:8000/v1``.
    api_key:
        Non-empty API key string for Bearer authentication.
    expected_models:
        Optional list of model IDs that **must** be present for the check to pass.

    Returns
    -------
    list[str]
        Sorted model IDs reported by the ``/models`` endpoint.

    Raises
    ------
    SystemExit
        If *api_key* is empty (meets Makefile behaviour).
    RuntimeError
        If the HTTP request fails or expected models are missing.

    Examples
    --------
    >>> check_omlx("http://localhost:8000/v1", "test-key")  # doctest: +SKIP
    ['model-1', 'Qwen3.6-35B-A3B']
    """

    if not api_key:
        print("OMLX_API_KEY is empty — set it in .env", file=_sys.stderr)
        _sys.exit(1)

    models_url = f"{base_url}/models"
    try:
        resp = httpx.get(
            models_url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except httpx.HTTPError as e:
        raise RuntimeError(f"OMLX connection failed ({e})") from e

    if resp.status_code != 200:
        raise RuntimeError(
            f"OMLX returned HTTP {resp.status_code}: {resp.text}"
        )

    data = resp.json()
    model_ids: list[str] = [m["id"] for m in data.get("data", [])]

    if expected_models:
        present = set(model_ids)
        for needed in expected_models:
            if needed not in present:
                raise RuntimeError(
                    f"Expected model '{needed}' is NOT available. "
                    f"Served models: {model_ids}"
                )

    return sorted(model_ids)
