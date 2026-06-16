"""ThumbnailMaker and FrameExtractor — video media adapters via ffmpeg.

Implements ``ThumbnailMaker`` (single representative-frame thumbnail)
and ``FrameExtractor`` (evenly-sampled frames for B-roll analysis).

Both adapters:
  * Probe the video first via ``ffprobe`` to obtain duration.
  * Use ffmpeg CLI for frame extraction (no Python video libraries).
  * Create parent directories on the output path automatically.

Edge cases handled:
  * Zero-duration video → thumbnail at t=0; extraction returns empty list.
  * Output directory does not exist → created via ``Path.mkdir``.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..ports.media import FrameExtractor, ThumbnailMaker

#: Prefix for the per-clip temp dirs that hold extracted B-roll frames.
_FRAME_DIR_PREFIX = "cutfinder_frames_"


def purge_stale_frame_dirs() -> int:
    """Remove leftover B-roll frame temp dirs from previous/crashed runs.

    Frame dirs are normally deleted right after vision analysis, but a crash or
    hard kill can leave them behind. Safe to call at startup (no analysis is in
    flight yet). Returns the number of directories removed.
    """
    removed = 0
    tmp_root = Path(tempfile.gettempdir())
    for d in tmp_root.glob(f"{_FRAME_DIR_PREFIX}*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def _probe_duration(path: Path) -> float | None:
    """Return video duration in seconds, or ``None`` on failure.

    Uses ffprobe (quiet JSON) — lightweight and fast compared to full decode.
    """
    try:
        result = subprocess.run(  # noqa: S603 — ffprobe is a trusted local tool
            [
                "ffprobe",
                "-v", "quiet",
                "-show_format",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    try:
        import json as _json
        data = _json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0)) or None
    except (ValueError, TypeError):
        return None


def _ensure_parent(out: Path) -> None:
    """Create parent directories for *out* if they don't exist."""
    out.parent.mkdir(parents=True, exist_ok=True)


class FfmpegThumbnailMaker(ThumbnailMaker):
    """Extract a single representative frame (middle of video) as JPEG.

    Parameters
    ----------
    executable:
        Path to the ``ffmpeg`` binary.  Defaults to "ffmpeg" (looked up via PATH).
    """

    def __init__(self, executable: str = "ffmpeg") -> None:
        self._executable = executable

    def make(self, path: Path, out_path: Path) -> Path:
        """Render one frame from the middle of *path*, writing it to *out_path*.

        Returns the absolute path of the written JPEG file.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        duration = _probe_duration(path)
        if duration is None or duration <= 0:
            # Zero-duration / unreadable → grab frame at t=0 (first keyframe)
            seek = 0.0
        else:
            # Middle frame is a good representative shot
            seek = duration / 2.0

        _ensure_parent(out_path)

        cmd = [
            self._executable,
            "-y",                     # overwrite output without asking
            "-ss", str(seek),        # seek to timestamp (before -i = fast)
            "-i", str(path),         # input file
            "-vframes", "1",        # write exactly one frame
            "-q:v", "2",             # high-quality JPEG (1=best, 31=worst)
            str(out_path),           # output path (will get .jpg appended by convention, but caller decides)
        ]

        result = subprocess.run(  # noqa: S603 — ffmpeg is a trusted local tool
            cmd, capture_output=True, text=True, check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg thumbnail extraction failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        if not out_path.is_file():
            raise RuntimeError(
                f"ffmpeg reported success but no output file was written: {out_path}"
            )

        return out_path.resolve()


class FfmpegFrameExtractor(FrameExtractor):
    """Extract multiple evenly-sampled frames from a video (PNG).

    Parameters
    ----------
    executable:
        Path to the ``ffmpeg`` binary.  Defaults to "ffmpeg" (looked up via PATH).
    default_count:
        Number of frames to extract when ``count`` is not specified.  Default ``3``.
    """

    def __init__(self, executable: str = "ffmpeg", default_count: int = 3) -> None:
        self._executable = executable
        self.default_count = default_count

    def extract(self, path: Path, count: int | None = None) -> list[Path]:
        """Extract *count* frames evenly spaced across the video duration.

        Frames are sampled at timestamps: ``duration * i / count``
        for ``i in range(count)`` — this gives uniform coverage without
        the edge-frame bias of ``(count - 1)`` denominators.

        Returns a list of absolute paths to the written PNG frame images.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a video file: {path}")

        n = count if count is not None else self.default_count
        if n <= 0:
            return []

        duration = _probe_duration(path)
        if duration is None or duration <= 0:
            # Zero-duration / unreadable → try extracting one frame at t=0, return empty if it fails
            timestamps = [0.0] * n

        else:
            # Evenly spaced, including the start frame (i=0) but not forcing end at exact boundary
            timestamps = [duration * i / n for i in range(n)]

        # Write frames into a dedicated temp dir — NEVER the source folder
        # (originals are read-only). The caller cleans up this dir after use.
        tmp_dir = Path(tempfile.mkdtemp(prefix=_FRAME_DIR_PREFIX))

        output_paths: list[Path] = []
        for i, ts in enumerate(timestamps):
            out_path = tmp_dir / f"frame_{i:04d}.jpg"

            cmd = [
                self._executable,
                "-y",
                "-ss", str(ts),
                "-i", str(path),
                "-vframes", "1",
                # Downscale to fit within 1280x720 (preserve aspect) — vision
                # models don't need 4K, and full-res frames balloon the request.
                "-vf", "scale=w=1280:h=720:force_original_aspect_ratio=decrease",
                "-q:v", "3",           # high-quality JPEG (mjpeg scale 2-31)
                str(out_path),
            ]

            result = subprocess.run(  # noqa: S603 — ffmpeg is a trusted local tool
                cmd, capture_output=True, text=True, check=False,
            )

            if result.returncode != 0:
                # Log but continue — one bad frame shouldn't abort the whole batch
                pass  # silently skip; caller gets whatever succeeded

            if out_path.is_file():
                output_paths.append(out_path.resolve())

        # No frames produced (zero-duration or every extraction failed) — remove
        # the now-empty temp dir here, since the orchestrator's cleanup only runs
        # when at least one frame path is returned.
        if not output_paths:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return output_paths
