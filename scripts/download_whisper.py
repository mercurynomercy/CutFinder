"""Pre-download the mlx-whisper model into ``<repo>/models/whisper/``.

CutFinder loads the model offline from there (the same path the transcriber
resolves on first use). One-time, ~3 GB for large-v3.
"""

from __future__ import annotations

REPO = "mlx-community/whisper-large-v3-mlx"


def main() -> None:
    from huggingface_hub import snapshot_download

    from cutfinder.config import WHISPER_MODELS_DIR

    dest = WHISPER_MODELS_DIR / REPO.split("/")[-1]
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=REPO, local_dir=str(dest))
    print(f"Whisper model downloaded to: {dest}")


if __name__ == "__main__":
    main()
