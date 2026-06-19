"""DemucsSeparator — vocal isolation (strip BGM) before transcription.

Extracts audio from a video with ffmpeg (44.1 kHz stereo float32 — Demucs'
native rate; downsampling first would degrade separation quality), runs it
through Demucs (``htdemucs``) to isolate the ``vocals`` stem, then downmixes
to mono and resamples to 16 kHz so the result is a drop-in replacement for
the whisper audio input.

The Demucs model is lazily loaded and cached on the instance; device is
auto-picked (MPS when available, else CPU).  Any failure raises — the
caller (transcriber) catches it and falls back to the original audio.
"""

from __future__ import annotations

import subprocess
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..ports.speech import VocalSeparator
from ._progress import patch_tqdm


def _extract_audio_bytes(path: Path) -> bytes | None:
    """Extract raw audio as PCM 32-bit float stereo at 44.1 kHz (Demucs native).

    Uses ``-map 0:a:0`` to explicitly select the first audio stream,
    avoiding issues with video edit-list errors.

    Returns ``None`` if ffmpeg fails or produces no output (e.g. no audio stream).
    """
    result = subprocess.run(  # noqa: S603 — ffmpeg is trusted local tool
        [
            "ffmpeg", "-y", "-i", str(path),
            "-map", "0:a:0",    # explicitly map first audio stream (avoids video edit-list issues)
            "-acodec", "pcm_f32le",
            "-ar", "44100",     # Demucs native sample rate
            "-ac", "2",         # stereo (Demucs expects 2 channels)
            "-f", "f32le",      # raw float32 output → stdout
            "-",                # write to stdout
        ],
        capture_output=True,
        check=False,
    )

    if result.returncode != 0 or not result.stdout:
        return None

    return result.stdout


class DemucsSeparator(VocalSeparator):
    """Isolate vocals from a video's audio using Demucs.

    Parameters
    ----------
    model:
        Demucs model name. Defaults to ``"htdemucs"`` (~80 MB, balanced).
    device:
        Torch device. When ``None`` it auto-picks ``"mps"`` if available,
        else ``"cpu"``.

    Examples
    --------
    >>> separator = DemucsSeparator()  # lazy-load model on first call
    >>> vocals = separator.isolate(Path("/path/to/video.mp4"))  # noqa: D100
    """

    def __init__(self, model: str = "htdemucs", device: str | None = None) -> None:
        self._model = model
        self._device = device
        # Lazy-loaded demucs model, cached on first isolate() call.
        self._dmodel: Any = None

    def _ensure_model_loaded(self) -> None:
        """Load the Demucs model on first use (cached per instance)."""
        if self._dmodel is not None:
            return

        import torch
        from demucs.pretrained import get_model

        device = self._device
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._device = device

        model = get_model(self._model)
        model.to(device)
        model.eval()
        self._dmodel = model

    def isolate(
        self, path: Path, *, progress: Callable[[float], None] | None = None,
    ) -> np.ndarray:
        """Return whisper-ready 16 kHz mono float32 vocals (BGM removed).

        1. Extracts audio with ffmpeg (44.1 kHz stereo float32).
        2. Runs Demucs to separate stems, taking ``vocals``.
        3. Downmixes to mono and resamples to 16 kHz.

        When *progress* is given, separation progress is forwarded as a 0..1
        fraction (Demucs' internal tqdm is intercepted); ``apply_model`` is run
        with ``progress=True`` so the tqdm bar exists.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist as a file.
        RuntimeError
            If no audio stream is found.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        raw_audio = _extract_audio_bytes(path)
        if raw_audio is None:
            raise RuntimeError(f"No audio stream found in video file: {path}")

        import demucs.apply as _apply
        import torch
        import torchaudio
        from demucs.apply import apply_model

        # Raw f32le stereo bytes → (2, N) channels-first tensor at 44100 Hz.
        samples = np.frombuffer(raw_audio, dtype=np.float32).reshape(-1, 2)
        wav = torch.from_numpy(samples.copy()).t().contiguous()

        self._ensure_model_loaded()
        model = self._dmodel

        # Demucs expects the mix normalized by its own mean/std (see demucs CLI).
        ref = wav.mean(dim=0)
        mean = ref.mean()
        std = ref.std() + 1e-8
        wav_norm = (wav - mean) / std

        # demucs only creates its tqdm bar when progress=True (and requires the
        # default split=True). Intercept that tqdm to forward 0..1 progress.
        ctx = patch_tqdm(_apply, progress) if progress is not None else nullcontext()
        with torch.no_grad(), ctx:
            sources = apply_model(
                model, wav_norm[None], device=self._device,
                progress=progress is not None,
            )[0]
        sources = sources * std + mean  # (stems, 2, M) at model.samplerate

        vocals = sources[model.sources.index("vocals")]  # (2, M)

        # Downmix to mono, then resample to 16 kHz for whisper.
        mono = vocals.mean(dim=0)
        resampled = torchaudio.functional.resample(
            mono, orig_freq=model.samplerate, new_freq=16000,
        )

        return np.asarray(resampled.cpu().numpy(), dtype=np.float32)
