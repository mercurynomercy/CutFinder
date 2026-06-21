"""OmlxAsrTranscriber + alignment — hybrid subtitle text via OMLX ASR.

OMLX-served ASR models (e.g. ``Qwen3-ASR``) transcribe Chinese/code-switching
audio more accurately than whisper, but they return **no timestamps** — the
whole clip comes back as a single span. For subtitles we therefore keep
mlx-whisper's per-segment *timing* and replace each segment's *text* with the
OMLX ASR transcript, distributed across the segments by character-level
alignment (:func:`align_text_to_segments`).

This is used only by the standalone subtitle export, not the catalog pipeline.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import tempfile
from pathlib import Path

from ..config import AppConfig
from ..domain.models import Segment

# Punctuation/space chars that should hug the end of the previous cue rather than
# start the next one (mix of CJK and ASCII marks).
_PUNCT = "，。！？；：、,.!?;: "


def _extract_wav(path: Path) -> Path:
    """Extract the first audio stream to a temp 16 kHz mono WAV.

    Returns the temp file path; the caller is responsible for deleting it.
    Raises ``RuntimeError`` if ffmpeg fails (e.g. no audio stream).
    """
    fd, name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    out = Path(name)
    result = subprocess.run(  # noqa: S603 — ffmpeg is a trusted local tool
        [
            "ffmpeg", "-y", "-i", str(path),
            "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "wav", str(out),
        ],
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        out.unlink(missing_ok=True)
        detail = result.stderr.decode("utf-8", "replace")[-300:]
        raise RuntimeError(f"ffmpeg audio extraction failed: {detail}")
    return out


class OmlxAsrTranscriber:
    """Transcribe a video's audio to plain text via an OMLX ASR model.

    Parameters
    ----------
    config:
        Application config carrying the OMLX endpoint/key.
    model:
        OMLX ASR model id (e.g. ``"Qwen3-ASR-1.7B"``).
    """

    def __init__(self, config: AppConfig, model: str) -> None:
        self._config = config
        self._model = model

    def transcribe_text(self, path: Path, *, language: str | None = None) -> str:
        """Return the full transcript text (no timestamps) for *path*.

        Extracts audio to a temp WAV and POSTs it to OMLX
        ``/audio/transcriptions``. Returns an empty string if the model yields
        nothing. Raises ``RuntimeError`` on extraction/connection failure.
        """
        from openai import OpenAI

        wav = _extract_wav(path)
        try:
            client = OpenAI(
                base_url=self._config.env.OMLX_BASE_URL,
                api_key=self._config.env.OMLX_API_KEY,
            )
            kwargs: dict[str, object] = {
                "model": self._model,
                "response_format": "json",
            }
            if language:
                kwargs["language"] = language
            with open(wav, "rb") as f:
                resp = client.audio.transcriptions.create(file=f, **kwargs)  # type: ignore[arg-type]
            return (getattr(resp, "text", "") or "").strip()
        except Exception as e:  # noqa: BLE001 — surface a clear error to the caller
            raise RuntimeError(f"OMLX ASR transcription failed: {e}") from e
        finally:
            wav.unlink(missing_ok=True)


def align_text_to_segments(segments: list[Segment], full_text: str) -> list[str]:
    """Distribute *full_text* across *segments*, returning one text per segment.

    Uses :class:`difflib.SequenceMatcher` between the concatenated whisper text
    and the accurate OMLX text: matched/replaced chars go to the whisper segment
    they align to; OMLX-only (inserted) chars trail the current segment;
    whisper-only (deleted) chars are dropped. Leading punctuation is snapped back
    to the previous cue. The result always has ``len(segments)`` entries.
    """
    w_texts = [s.text.strip() for s in segments]
    if not full_text.strip():
        return w_texts
    w_full = "".join(w_texts)
    if not w_full:
        # Nothing to align against — put all text in the first cue.
        out = [""] * len(segments)
        if out:
            out[0] = full_text.strip()
        return out

    # Map each char position in w_full back to its segment index.
    seg_of_wchar: list[int] = []
    for i, t in enumerate(w_texts):
        seg_of_wchar += [i] * len(t)

    out = [""] * len(segments)
    last_seg = 0
    matcher = difflib.SequenceMatcher(a=w_full, b=full_text, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "replace"):
            wlen = i2 - i1
            qlen = j2 - j1
            for k, ch in enumerate(full_text[j1:j2]):
                wpos = i1 + (k * wlen // max(qlen, 1))
                seg = seg_of_wchar[min(wpos, len(seg_of_wchar) - 1)]
                out[seg] += ch
                last_seg = seg
        elif tag == "insert":
            out[last_seg] += full_text[j1:j2]
        # tag == "delete": whisper-only chars, skip

    out = _snap_leading_punctuation(out)
    return [t.strip() for t in out]


def _snap_leading_punctuation(texts: list[str]) -> list[str]:
    """Move punctuation that opens a cue to the end of the previous cue."""
    for i in range(1, len(texts)):
        t = texts[i].lstrip()
        while t and t[0] in _PUNCT:
            texts[i - 1] = texts[i - 1] + t[0]
            t = t[1:]
        texts[i] = t
    return texts
