"""SqliteCutSessionStore — persistence for rough-cut conversations (§3.15).

Kept separate from :class:`SqliteRepository` (clips/tags/jobs) so the agent's
session tables are an independent, independently-testable concern. Shares the
caller's connection; deleting a session cascades its messages and plans.
"""

from __future__ import annotations

import datetime as _dt
import json
from sqlite3 import Connection as _Conn
from typing import Any

from ..domain.models import ChatMessage, CutPlan, CutSession

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS cut_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT,
    request_json TEXT,
    status       TEXT NOT NULL DEFAULT 'idle',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS cut_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT,
    tool_json  TEXT,
    created_at TEXT NOT NULL
)"""

_CREATE_PLANS = """
CREATE TABLE IF NOT EXISTS cut_plans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
    plan_json  TEXT NOT NULL,
    created_at TEXT NOT NULL
)"""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class SqliteCutSessionStore:
    """SQLite-backed :class:`CutSessionStore`."""

    def __init__(self, conn: _Conn) -> None:
        self._conn = conn
        self.execute_schema()

    def execute_schema(self) -> None:
        c = self._conn.cursor()
        c.execute(_CREATE_SESSIONS)
        c.execute(_CREATE_MESSAGES)
        c.execute(_CREATE_PLANS)
        self._conn.commit()

    # ── sessions ─────────────────────────────────────────────────

    def create_session(self, title: str = "") -> CutSession:
        now = _now()
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO cut_sessions (title, request_json, status, created_at, updated_at)"
            " VALUES (?, ?, 'idle', ?, ?)",
            (title, None, now, now),
        )
        self._conn.commit()
        sid = int(c.lastrowid or 0)
        return CutSession(id=sid, title=title, status="idle", created_at=now, updated_at=now)

    def list_sessions(self) -> list[CutSession]:
        c = self._conn.cursor()
        c.execute(
            "SELECT id, title, status, created_at, updated_at"
            " FROM cut_sessions ORDER BY updated_at DESC, id DESC",
        )
        return [
            CutSession(id=r[0], title=r[1] or "", status=r[2], created_at=r[3], updated_at=r[4])
            for r in c.fetchall()
        ]

    def get_session(self, session_id: int) -> CutSession | None:
        c = self._conn.cursor()
        c.execute(
            "SELECT id, title, status, created_at, updated_at FROM cut_sessions WHERE id = ?",
            (session_id,),
        )
        r = c.fetchone()
        if r is None:
            return None
        return CutSession(id=r[0], title=r[1] or "", status=r[2], created_at=r[3], updated_at=r[4])

    def delete_session(self, session_id: int) -> None:
        c = self._conn.cursor()
        # Cascade explicitly (FK enforcement may be off on the connection).
        c.execute("DELETE FROM cut_messages WHERE session_id = ?", (session_id,))
        c.execute("DELETE FROM cut_plans WHERE session_id = ?", (session_id,))
        c.execute("DELETE FROM cut_sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def set_session_status(self, session_id: int, status: str) -> None:
        c = self._conn.cursor()
        c.execute(
            "UPDATE cut_sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )
        self._conn.commit()

    def set_session_request(self, session_id: int, request_json: str) -> None:
        c = self._conn.cursor()
        c.execute(
            "UPDATE cut_sessions SET request_json = ?, updated_at = ? WHERE id = ?",
            (request_json, _now(), session_id),
        )
        self._conn.commit()

    def get_session_request(self, session_id: int) -> str | None:
        c = self._conn.cursor()
        c.execute("SELECT request_json FROM cut_sessions WHERE id = ?", (session_id,))
        r = c.fetchone()
        return r[0] if r and r[0] else None

    # ── messages ─────────────────────────────────────────────────

    def append_message(self, session_id: int, message: ChatMessage) -> None:
        now = message.created_at or _now()
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO cut_messages (session_id, role, content, tool_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, message.role, message.content, message.tool_json, now),
        )
        c.execute("UPDATE cut_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        self._conn.commit()

    def get_messages(self, session_id: int) -> list[ChatMessage]:
        c = self._conn.cursor()
        c.execute(
            "SELECT role, content, tool_json, created_at FROM cut_messages"
            " WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        return [
            ChatMessage(role=r[0], content=r[1] or "", tool_json=r[2], created_at=r[3])
            for r in c.fetchall()
        ]

    # ── plans ────────────────────────────────────────────────────

    def save_plan(self, session_id: int, plan: CutPlan) -> None:
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO cut_plans (session_id, plan_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(plan.model_dump(), ensure_ascii=False), _now()),
        )
        self._conn.commit()

    def get_latest_plan(self, session_id: int) -> CutPlan | None:
        c = self._conn.cursor()
        c.execute(
            "SELECT plan_json FROM cut_plans WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        r = c.fetchone()
        if r is None:
            return None
        data: dict[str, Any] = json.loads(r[0])
        return CutPlan(**data)

    def close(self) -> None:
        self._conn.close()


class MemoryCutSessionStore(SqliteCutSessionStore):
    """In-memory store for fast unit tests."""

    def __init__(self) -> None:
        import sqlite3
        # check_same_thread=False mirrors the app's shared connection so the
        # store works under FastAPI's TestClient threadpool.
        super().__init__(sqlite3.connect(":memory:", check_same_thread=False))
