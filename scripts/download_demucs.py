"""Pre-download the Demucs htdemucs model so separation runs offline.

Fetches the htdemucs weights into the local torch hub cache (one-time,
~80 MB). After this, vocal separation works fully offline.
"""

from __future__ import annotations

MODEL = "htdemucs"


def main() -> None:
    from demucs.pretrained import get_model

    get_model(MODEL)
    print(f"Demucs model cached: {MODEL}")


if __name__ == "__main__":
    main()
