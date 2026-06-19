"""SubtitleExporter — re-transcribe a finished video and write subtitle files.

This is a standalone tool, decoupled from the catalog: it does *not* reuse any
stored transcript. The chosen video is re-transcribed with mlx-whisper aligned
to its own timeline, then exported as iTT (Final Cut Pro native) and/or SRT.

The source video is read-only; only new subtitle files are created. No
translation happens anywhere — *language* is purely the Whisper language hint
and the subtitle filename suffix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..ports.probe import MetadataProbe
from ..ports.speech import Transcriber
from ..subtitle.format import to_itt, to_srt

# Subtitle file extension per format key.
_EXTENSIONS = {"itt": "itt", "srt": "srt"}


class SubtitleExporter:
    """Re-transcribe a video and render subtitle files into an output folder.

    Parameters
    ----------
    probe:
        Metadata probe (for the frame rate used by the iTT header).
    transcriber:
        Transcriber used to re-transcribe the video on its own timeline.
    """

    def __init__(self, probe: MetadataProbe, transcriber: Transcriber) -> None:
        self._probe = probe
        self._transcriber = transcriber

    def export(
        self,
        video_path: Path,
        out_dir: Path,
        formats: list[str],
        language: str,
        *,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[Path]:
        """Export subtitle files for *video_path* into *out_dir*.

        Returns the written paths in *formats* order. Unknown formats are
        skipped. Files are never overwritten — a numeric suffix is appended
        before the extension when a name already exists.

        *on_progress* is forwarded to the transcriber as a 0..1 progress
        callback (covering separation + transcription).
        """
        meta = self._probe.probe(video_path)
        fps = meta.fps or 25.0

        transcript = self._transcriber.transcribe(
            video_path, language=language, progress=on_progress,
        )
        segments = transcript.segments

        written: list[Path] = []
        for fmt in formats:
            if fmt not in _EXTENSIONS:
                continue
            if fmt == "itt":
                content = to_itt(segments, language=language, fps=fps)
            else:
                content = to_srt(segments)

            target = _non_overwriting_path(
                out_dir, video_path.stem, language, _EXTENSIONS[fmt]
            )
            target.write_text(content, encoding="utf-8")
            written.append(target)

        return written


def _non_overwriting_path(out_dir: Path, stem: str, language: str, ext: str) -> Path:
    """Return ``<stem>.<language>.<ext>`` in *out_dir*, avoiding collisions.

    When the base name exists, append ``" (1)"``, ``" (2)"``, ... before the
    extension until a free name is found.
    """
    base = out_dir / f"{stem}.{language}.{ext}"
    if not base.exists():
        return base
    n = 1
    while True:
        candidate = out_dir / f"{stem}.{language} ({n}).{ext}"
        if not candidate.exists():
            return candidate
        n += 1
