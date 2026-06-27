"""QwenTranscriber — Chinese / zh-en subtitle transcription via Qwen3-ASR + ForcedAligner.

A drop-in :class:`~cutfinder.ports.speech.Transcriber` that replaces mlx-whisper
when the speech engine is set to ``"qwen"``. Whisper transcribes Chinese poorly
and (for subtitles) its segment timing drifts; the Qwen pair fixes both:

* **Qwen3-ASR** produces accurate Chinese / code-switching text — but no usable
  timestamps (the whole clip comes back as one span).
* **Qwen3-ForcedAligner** takes that text + the audio and returns real
  per-character / per-word timestamps.

Because the aligner's timestamp range caps at ~400 s, and to scale to arbitrarily
long video, the audio is first split with **Silero VAD** into speech spans which
are merged into ``max_chunk_s`` chunks. Each chunk is transcribed and aligned
independently, then its timestamps are offset back onto the clip timeline and the
aligned tokens are grouped into subtitle cues. No whisper, no character-diff
alignment — so the cues stay accurate to the end of a long clip.

Both models are MLX repos downloaded into ``<repo>/models/qwen/`` on first use and
loaded offline thereafter (mirroring :class:`MlxWhisperTranscriber`). Loaded
models are cached process-globally so the orchestrator and the subtitle exporter
share one copy; :meth:`QwenTranscriber.unload_cache` frees them when idle.
"""

from __future__ import annotations

import logging
import struct
import subprocess
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..config import QWEN_MODELS_DIR
from ..domain.models import Segment, Transcript
from ..ports.speech import Transcriber, VocalSeparator

logger = logging.getLogger(__name__)

_SR = 16000  # Qwen3-ASR / aligner / Silero native sample rate
# Separation occupies [0, W] of overall progress; transcription [W, 1].
_SEPARATION_WEIGHT = 0.4

# Map the app's short language codes to the aligner's language *names*.
_LANG_NAMES = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}

# Cue assembly: sentence-final marks force a cue break; the rest is bounded by
# length / duration / silence gaps so cues stay readable.
_HARD_PUNCT = "。！？!?…"

# Loaded models, keyed by resolved local path (shared across instances).
_MODEL_CACHE: dict[str, Any] = {}


def _lang_name(code: str | None) -> str:
    """Return the aligner language name for a short code (default Chinese)."""
    return _LANG_NAMES.get((code or "zh").lower(), "Chinese")


def _safe(cb: Callable[[float], None] | None, value: float) -> None:
    """Invoke *cb* with *value*, swallowing any error (never break work)."""
    if cb is None:
        return
    try:
        cb(value)
    except Exception:  # noqa: BLE001 — UI callback errors must not stop transcription
        pass


# ── audio extraction ──────────────────────────────────────────────

def _extract_audio(path: Path) -> np.ndarray | None:
    """Extract the first audio stream as float32 mono [-1, 1] at 16 kHz.

    Returns ``None`` if ffmpeg fails or the file has no audio stream.
    """
    result = subprocess.run(  # noqa: S603 — ffmpeg is a trusted local tool
        [
            "ffmpeg", "-y", "-i", str(path),
            "-map", "0:a:0", "-acodec", "pcm_s16le",
            "-ar", str(_SR), "-ac", "1", "-f", "data", "-",
        ],
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    raw = result.stdout
    n = len(raw) // 2
    if n == 0:
        return None
    samples = struct.unpack(f"<{n}h", raw[: n * 2])
    return np.array(samples, dtype=np.float32) / 32768.0


# ── VAD chunking ──────────────────────────────────────────────────

def merge_speech_into_chunks(
    spans: list[tuple[float, float]], max_chunk_s: float,
) -> list[tuple[float, float]]:
    """Merge VAD speech *spans* (seconds) into chunks no longer than *max_chunk_s*.

    Adjacent speech spans accumulate into one chunk until adding the next would
    exceed *max_chunk_s* (measured from the chunk start); a single span longer
    than *max_chunk_s* is split into back-to-back pieces. Returns ``(start, end)``
    chunk windows on the original timeline.
    """
    chunks: list[tuple[float, float]] = []
    cs: float | None = None
    ce: float = 0.0
    for a, b in spans:
        if cs is None:
            cs, ce = a, b
        elif b - cs <= max_chunk_s:
            ce = b
        else:
            chunks.append((cs, ce))
            cs, ce = a, b
        while ce - cs > max_chunk_s:
            chunks.append((cs, cs + max_chunk_s))
            cs = cs + max_chunk_s
    if cs is not None:
        chunks.append((cs, ce))
    return chunks


# ── cue assembly ──────────────────────────────────────────────────

def reattach_punctuation(
    text: str, items: list[Any],
) -> list[tuple[str, float, float]]:
    """Re-attach punctuation/spacing from *text* onto the aligned *items*.

    The forced aligner strips punctuation, returning bare tokens with timestamps
    (``item.text`` / ``item.start_time`` / ``item.end_time``). Walking the
    original ASR *text* in parallel restores the marks: characters between two
    tokens trail the earlier token, so cues keep their commas and full stops.
    Returns ``(token_text, start_s, end_s)`` triples in order.
    """
    out: list[list[Any]] = []
    pos = 0
    for it in items:
        tok = it.text
        idx = text.find(tok, pos)
        if idx == -1:
            out.append([tok, it.start_time, it.end_time])
            continue
        lead = text[pos:idx]
        if lead and out:
            out[-1][0] += lead  # trailing punctuation/space hugs previous token
        piece = (lead + tok) if (lead and not out) else tok
        out.append([piece, it.start_time, it.end_time])
        pos = idx + len(tok)
    if pos < len(text) and out:
        out[-1][0] += text[pos:]
    return [(t, s, e) for t, s, e in out]


def group_cues(
    timed: list[tuple[str, float, float]],
    *,
    offset: float,
    max_chars: int,
    max_dur: float,
    gap_s: float,
) -> list[Segment]:
    """Group reconstructed *timed* tokens into subtitle cues (offset to timeline).

    A cue is flushed when it ends on sentence punctuation, reaches *max_chars*,
    spans *max_dur* seconds, or the silence before the next token exceeds
    *gap_s*. Empty / whitespace tokens never start a cue.
    """
    cues: list[Segment] = []
    cur = ""
    cs: float | None = None
    ce = 0.0
    n = len(timed)
    for i, (txt, s, e) in enumerate(timed):
        if cs is None:
            cs = s
        cur += txt
        ce = e
        stripped = cur.strip()
        next_gap = (timed[i + 1][1] - e) if i + 1 < n else 99.0
        hard = any(c in _HARD_PUNCT for c in txt)
        flush = (
            hard
            or len(stripped) >= max_chars
            or next_gap > gap_s
            or (ce - cs) >= max_dur
        )
        if flush and stripped:
            cues.append(Segment(start_s=cs + offset, end_s=ce + offset, text=stripped))
            cur, cs, ce = "", None, 0.0
    if cur.strip() and cs is not None:
        cues.append(Segment(start_s=cs + offset, end_s=ce + offset, text=cur.strip()))
    return cues


def clean_cues(cues: list[Segment]) -> list[Segment]:
    """Drop empty / near-zero-duration cues and collapse consecutive duplicates."""
    out: list[Segment] = []
    for c in cues:
        if not c.text.strip() or c.end_s - c.start_s < 0.08:
            continue
        if out and out[-1].text == c.text:
            continue
        out.append(c)
    return out


# ── QwenTranscriber ───────────────────────────────────────────────

class QwenTranscriber(Transcriber):
    """Transcribe + force-align a video's speech with the local Qwen3 models.

    Parameters
    ----------
    asr_model / aligner_model:
        MLX repo ids (or local dirs) for Qwen3-ASR and Qwen3-ForcedAligner.
    language:
        Default short language code (``"zh"``/``"en"``); overridable per call.
    separator:
        Optional vocal separator (strip BGM before transcription).
    vad_threshold:
        Silero VAD speech probability threshold for chunking.
    max_chunk_s:
        Max seconds of audio per ASR/aligner call (VAD-merged).
    """

    def __init__(
        self,
        asr_model: str,
        aligner_model: str,
        language: str = "zh",
        separator: VocalSeparator | None = None,
        vad_threshold: float = 0.35,
        max_chunk_s: float = 60.0,
        cue_max_chars: int = 18,
        cue_max_dur: float = 6.0,
        cue_gap_s: float = 0.7,
    ) -> None:
        self._asr_model = asr_model
        self._aligner_model = aligner_model
        self._language = language
        self._separator = separator
        self._vad_threshold = vad_threshold
        self._max_chunk_s = max_chunk_s
        self._cue_max_chars = cue_max_chars
        self._cue_max_dur = cue_max_dur
        self._cue_gap_s = cue_gap_s
        self._vad: Any = None  # lazily-loaded Silero VAD model

    # ── model loading / unloading ────────────────────────────────

    @staticmethod
    def _resolve_model_path(repo: str) -> str:
        """Return a local model dir for *repo*, downloading from HF if missing.

        A local directory is used as-is; an HF repo id is materialised under
        ``<repo>/models/qwen/<basename>`` on first use, then loaded offline.
        """
        candidate = Path(repo)
        if candidate.is_dir():
            return str(candidate)
        local = QWEN_MODELS_DIR / repo.split("/")[-1]
        if not local.is_dir():
            from huggingface_hub import snapshot_download

            local.parent.mkdir(parents=True, exist_ok=True)
            snapshot_download(repo, local_dir=str(local))
        return str(local)

    @staticmethod
    def _repo_ready(repo: str) -> bool:
        """Whether *repo* is already on disk (local dir, or materialised)."""
        candidate = Path(repo)
        if candidate.is_dir():
            return True
        return (QWEN_MODELS_DIR / repo.split("/")[-1]).is_dir()

    def is_model_ready(self) -> bool:
        """Whether both Qwen models are on disk (no download needed).

        Cheap directory check so callers can warn before the first
        transcription triggers a multi-GB download of the ASR + aligner repos.
        """
        return self._repo_ready(self._asr_model) and self._repo_ready(self._aligner_model)

    def _load(self, repo: str) -> Any:
        """Load (and process-globally cache) an MLX STT model for *repo*."""
        path = self._resolve_model_path(repo)
        model = _MODEL_CACHE.get(path)
        if model is None:
            from mlx_audio.stt.utils import load_model

            logger.info("Loading Qwen MLX model %s", repo)
            model = load_model(path)
            _MODEL_CACHE[path] = model
        return model

    @staticmethod
    def unload_cache() -> None:
        """Release the process-global Qwen models and MLX buffer cache.

        Safe to call when nothing is loaded (no-op). Mirrors
        :meth:`MlxWhisperTranscriber.unload_cache` so the idle hook can free
        unified memory between jobs.
        """
        if _MODEL_CACHE:
            logger.info("Unloading %d Qwen MLX model(s) from memory", len(_MODEL_CACHE))
        _MODEL_CACHE.clear()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:  # noqa: BLE001 — best-effort cleanup, never raise
            logger.debug("Qwen unload skipped", exc_info=True)

    # ── VAD ──────────────────────────────────────────────────────

    def _speech_spans(self, audio: np.ndarray) -> list[tuple[float, float]]:
        """Return Silero VAD speech spans ``(start_s, end_s)`` for *audio*."""
        import silero_vad  # noqa: E402
        import torch  # noqa: E402

        if self._vad is None:
            self._vad = silero_vad.load_silero_vad(onnx=True, opset_version=16)

        ts = silero_vad.get_speech_timestamps(
            torch.from_numpy(audio),
            self._vad,
            threshold=self._vad_threshold,
            sampling_rate=_SR,
            return_seconds=True,
        )
        return [(float(t["start"]), float(t["end"])) for t in ts]

    # ── main entry point ─────────────────────────────────────────

    def transcribe(
        self,
        path: Path,
        *,
        language: str | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """Transcribe + align *path* into a :class:`Transcript` of cue segments.

        Returns an empty transcript when the clip has no audio or no detected
        speech. Raises ``FileNotFoundError`` if *path* is not a file.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        lang_code = language or self._language
        lang = _lang_name(lang_code)
        w = _SEPARATION_WEIGHT if self._separator is not None else 0.0

        # Audio: optionally isolate vocals, else raw 16 kHz mono.
        audio: np.ndarray | None = None
        if self._separator is not None:
            try:
                audio = self._separator.isolate(
                    path,
                    progress=(lambda f: _safe(progress, f * w)) if progress else None,
                )
            except Exception as exc:  # noqa: BLE001 — degrade to raw audio
                logger.warning("Vocal separation failed for %s, using raw audio: %s", path, exc)
                audio = None
        if audio is None:
            audio = _extract_audio(path)
        if audio is None or audio.size == 0:
            return Transcript(full_text="", segments=[])

        spans = self._speech_spans(audio)
        chunks = merge_speech_into_chunks(spans, self._max_chunk_s)
        if not chunks:
            _safe(progress, 1.0)
            return Transcript(full_text="", segments=[])

        asr = self._load(self._asr_model)
        aligner = self._load(self._aligner_model)

        all_cues: list[Segment] = []
        full_parts: list[str] = []
        total = len(chunks)
        for ci, (a, b) in enumerate(chunks):
            seg = audio[int(a * _SR): int(b * _SR)]
            # Cap output length to the chunk duration so an ASR repetition loop
            # cannot run to max_tokens; the penalty further discourages loops.
            cap = int((b - a) * 12) + 32
            result = asr.generate(
                seg, language=lang, repetition_penalty=1.1, max_tokens=cap,
            )
            text = (getattr(result, "text", "") or "").strip()
            if text:
                full_parts.append(text)
                items = list(aligner.generate(seg, text=text, language=lang))
                if items:
                    timed = reattach_punctuation(text, items)
                    all_cues.extend(group_cues(
                        timed, offset=a,
                        max_chars=self._cue_max_chars,
                        max_dur=self._cue_max_dur,
                        gap_s=self._cue_gap_s,
                    ))
                else:
                    # Alignment yielded nothing — fall back to a single chunk cue.
                    all_cues.append(Segment(start_s=a, end_s=b, text=text))
            _safe(progress, w + (1 - w) * (ci + 1) / total)

        return Transcript(full_text="".join(full_parts), segments=clean_cues(all_cues))
