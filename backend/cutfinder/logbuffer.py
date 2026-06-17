"""In-memory ring buffer of recent log records, surfaced to the UI.

A :class:`RingBufferHandler` is attached to the root logger at app startup so
recent backend log lines can be read via ``GET /api/logs`` and shown in a modal
— no need to watch the terminal.  The buffer is bounded (oldest lines drop) and
each record carries a monotonically increasing ``seq`` so the frontend can poll
for only what's new.
"""

from __future__ import annotations

import logging
from collections import deque
from threading import Lock
from typing import Any


class RingBufferHandler(logging.Handler):
    """A logging handler that keeps the most recent records in memory."""

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self._buf: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 — never let logging crash the app
            message = record.getMessage()
        with self._lock:
            self._seq += 1
            self._buf.append({
                "seq": self._seq,
                "time": record.created,        # epoch seconds (float)
                "level": record.levelname,     # "INFO" / "WARNING" / ...
                "name": record.name,           # logger name
                "message": message,
            })

    def records(self, after: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        """Return buffered records with ``seq > after`` (newest *limit* of them)."""
        with self._lock:
            items = [r for r in self._buf if r["seq"] > after]
        if limit is not None and len(items) > limit:
            items = items[-limit:]
        return items


# ── Singleton wiring ──────────────────────────────────────────────

_handler: RingBufferHandler | None = None


def get_log_buffer() -> RingBufferHandler:
    """Return the process-wide ring-buffer handler (created on first use)."""
    global _handler
    if _handler is None:
        _handler = RingBufferHandler()
        _handler.setFormatter(logging.Formatter("%(message)s"))
    return _handler


def install_log_buffer(level: int = logging.INFO) -> RingBufferHandler:
    """Attach the ring-buffer handler to the root logger (idempotent)."""
    handler = get_log_buffer()
    root = logging.getLogger()
    if handler not in root.handlers:
        root.addHandler(handler)
    # Ensure INFO records actually reach handlers (default root level is WARNING).
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    return handler
