"""The single definition of a clip's *shooting day*.

``capture_time`` is stored as a UTC instant, but every place a user sees a date
— the gallery's day headings, the detail panel, the ``YYYY-MM-DD`` library
folder — shows the **local** calendar date of that instant. Anything that
filters, groups or labels by day must agree, or clips shot near local midnight
land under the neighbouring date (the frontend counterpart is
``localDateKey`` in ``frontend/src/lib/date.ts``).

Naive values carry no offset to convert, so they are used as-is.
"""

from __future__ import annotations

import datetime as _dt

__all__ = ["local_day", "local_stamp"]


def _to_local(value: _dt.datetime | str | None) -> _dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value.astimezone() if value.tzinfo is not None else value


def local_day(value: _dt.datetime | str | None) -> str | None:
    """Local ``YYYY-MM-DD`` shooting day for *value*, or None if unusable."""
    local = _to_local(value)
    return local.strftime("%Y-%m-%d") if local is not None else None


def local_stamp(value: _dt.datetime | str | None) -> str | None:
    """Local ``YYYY-MM-DD HH:MM:SS`` for *value*, or None if unusable."""
    local = _to_local(value)
    return local.strftime("%Y-%m-%d %H:%M:%S") if local is not None else None
