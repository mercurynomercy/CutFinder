"""Pre-download the Demucs htdemucs model so separation runs offline.

Fetches the htdemucs weights into ``<repo>/models/demucs/`` (one-time, ~80 MB).
After this, vocal separation works fully offline.
"""

from __future__ import annotations

MODEL = "htdemucs"


def main() -> None:
    import torch
    from demucs.pretrained import get_model

    from cutfinder.config import DEMUCS_MODELS_DIR

    DEMUCS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.hub.set_dir(str(DEMUCS_MODELS_DIR))

    get_model(MODEL)
    print(f"Demucs model cached at: {DEMUCS_MODELS_DIR} ({MODEL})")


if __name__ == "__main__":
    main()
