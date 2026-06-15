"""Domain enums — scalar values used across the application."""

from enum import Enum


class RollType(str, Enum):
    """A-roll or B-roll classification."""

    A = "a"
    B = "b"


class Source(str, Enum):
    """Whether data came from automatic analysis or manual user input."""

    AUTO = "auto"
    MANUAL = "manual"


class JobStatus(str, Enum):
    """Queue job lifecycle state."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DateSource(str, Enum):
    """Where the capture date was derived from."""

    EMBEDDED = "embedded"  # QuickTime / EXIF tag
    FILE = "file"          # Filesystem creation time (fallback, less reliable)


class ClipStatus(str, Enum):
    """Processing status of a single clip."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
