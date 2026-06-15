"""Download the mlx-whisper model, optionally into a custom directory.

If ``WHISPER_MODEL_PATH`` is set, the model is downloaded there so CutFinder
loads it offline from that path (instead of the HuggingFace cache). Otherwise
it is fetched into the default HF cache.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = "mlx-community/whisper-large-v3-mlx"


def main() -> None:
    dest = os.environ.get("WHISPER_MODEL_PATH", "").strip()
    if dest:
        from huggingface_hub import snapshot_download

        Path(dest).mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=REPO, local_dir=dest)
        print(f"Whisper model downloaded to: {dest}")
    else:
        from mlx_whisper.load_models import load_model

        load_model(REPO)
        print(f"Whisper model cached in HF cache: {REPO}")


if __name__ == "__main__":
    main()
