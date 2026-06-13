"""FfmpegProbe — probe video file metadata via the ffprobe CLI.

Implements ``MetadataProbe`` by running ``ffprobe -v quiet``,
parsing the JSON output, and returning a frozen ``VideoMetadata`` model.

Edge cases handled:
  * No embedded creation_time → fall back to file birth time (os.stat).
  * FPS stored as a fraction string ("30000/1001") → parsed to float.
  * Multiple streams → first video stream for width/height/fps; any audio
    stream sets has_audio=True.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import Any

from ..domain.models import VideoMetadata


def _parse_fraction(frac: str) -> float | None:
    """Convert a fraction string like ``"30000/1001"`` to float.

    Returns None when the input is empty or unparseable.
    """
    if not frac:
        return None
    try:
        num, _, den = frac.partition("/")
        if not den or den == "0":
            return None  # avoid division by zero / nonsense
        return float(num) / float(den)
    except ValueError:
        return None


def _parse_creation_time(s: str | None) -> datetime.datetime | None:
    """Parse an ISO 8601 creation-time string into a UTC-aware datetime.

    Returns None when *s* is empty, missing, or unparseable.
    """
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s)
        # Ensure the result is UTC-aware; if naive, assume UTC.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        # Convert to UTC if it has a different tz.
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, OverflowError):
        return None


class FfmpegProbe:
    """Run ffprobe on a video file and return structured metadata.

    Parameters
    ----------
    executable:
        Path to the ``ffprobe`` binary.  Defaults to "ffprobe" which is
        looked up via PATH (the default for a Homebrew install on macOS).
    """

    def __init__(self, executable: str = "ffprobe") -> None:
        self._executable = executable

    def probe(self, path: Path) -> VideoMetadata:
        """Probe a single video file and return its metadata.

        Raises ``FileNotFoundError`` if the path doesn't exist,
        or ``RuntimeError`` on CLI / parse failure.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Not a file: {path}")

        try:
            result = self._run_probe(path)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"ffprobe executable not found at PATH: {self._executable}"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe exited with code {result.returncode}: "
                f"{result.stderr.strip()}"
            )

        data: dict[str, Any] = json.loads(result.stdout)

        fmt = data.get("format", {})
        tags: dict[str, str] = fmt.get("tags", {})

        # ── capture_time & date_source ───────────────────────────────
        creation_str = tags.get("creation_time") or ""
        capture_time: datetime.datetime | None = _parse_creation_time(
            creation_str if creation_str else None
        )
        date_source: str = "embedded" if capture_time else "file"

        # Fallback: no embedded creation_time → file birth time
        if capture_time is None:
            try:
                bt = path.stat().st_birthtime  # macOS / BSD only
                capture_time = datetime.datetime.fromtimestamp(
                    bt, tz=datetime.timezone.utc
                )
            except OSError:
                pass  # leave capture_time None; date_source stays "file"

        # ── stream-level fields (width, height, fps, codec) ─────────
        streams: list[dict[str, Any]] = data.get("streams", [])

        width: int | None = None
        height: int | None = None
        fps: float | None = None
        codec: str | None = None
        has_audio: bool = False

        for stream in streams:
            codec_type = stream.get("codec_type")  # "video" | "audio"

            if codec_type == "video":
                # Only take the first video stream for dimensions/fps
                if width is None:
                    width = stream.get("width")
                    height = stream.get("height")
                    # Prefer r_frame_rate; fall back to avg_frame_rate
                    fps_raw = stream.get("r_frame_rate", "") or stream.get(
                        "avg_frame_rate", ""
                    )
                    fps = (
                        _parse_fraction(fps_raw) if isinstance(fps_raw, str) else None
                    )
                    codec = stream.get("codec_name")  # e.g. "h264"
            elif codec_type == "audio":
                has_audio = True  # any audio stream → flag is set

        return VideoMetadata(
            capture_time=capture_time,
            date_source=date_source,
            duration_s=float(fmt.get("duration", 0)),
            width=width,
            height=height,
            fps=fps,
            codec=codec,
            has_audio=has_audio,
        )

    # ── internal helpers (overridable for testing) ───────────────────

    def _run_probe(self, path: Path) -> subprocess.CompletedProcess[str]:
        """Run ffprobe and return the completed process.

        Raises ``RuntimeError`` when ffprobe exits with a non-zero code.
        """
        cmd = [
            self._executable,
            "-v", "quiet",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(path),
        ]
        proc = subprocess.run(  # noqa: S603 — ffprobe is a trusted local tool
            cmd, capture_output=True, text=True, check=False
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"ffprobe exited with code {proc.returncode}: "
                f"{proc.stderr.strip()}"
            )

        return proc
