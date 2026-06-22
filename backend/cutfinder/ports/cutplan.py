"""Ports for the rough-cut director agent (§3.15).

Three interfaces the :class:`~cutfinder.cutplan.director.CutDirector` depends
on — all injectable so the loop runs in unit tests with no real models:

* :class:`FootageRetriever` — read-only catalog search + per-clip detail.
* :class:`BrollInspector` — live Qwen3-VL look at a B-roll clip's frames.
* :class:`LLMAgentClient` — one tool-calling step against the text model.

The small ``ToolCall`` / ``AgentStep`` carriers are plain frozen dataclasses so
fakes can build scripted responses without pydantic ceremony.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..domain.models import (
    ChatMessage,
    ClipBrief,
    ClipDetail,
    CutPlan,
    CutSession,
    VisionResult,
)


# ── tool-calling carriers ────────────────────────────────────────

@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentStep:
    """One step of the agent loop.

    If ``tool_calls`` is non-empty the director executes them and feeds the
    results back; otherwise ``content`` is the model's final assistant reply.
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


# ── ports ────────────────────────────────────────────────────────

class FootageRetriever(Protocol):
    """Read-only catalog access the agent searches over (never writes)."""

    def search_footage(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        roll: str | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
    ) -> list[ClipBrief]:
        """Return catalog clips in the date range matching optional filters."""

    def get_clip_detail(self, clip_id: int) -> ClipDetail | None:
        """Return transcript segments + keyframes + metadata for one clip."""


class BrollInspector(Protocol):
    """Live visual check of a B-roll clip (samples frames → Qwen3-VL)."""

    def inspect_broll(self, clip_id: int) -> VisionResult | None:
        """Describe a B-roll clip's actual frames, or ``None`` if unavailable."""


class LLMAgentClient(Protocol):
    """Text-model access for the director (OMLX Qwen3.6)."""

    def run(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
    ) -> AgentStep:
        """Send *messages* + *tools*; return the model's next step (tool loop)."""

    def complete(self, messages: list[dict[str, Any]]) -> str:
        """Plain (no-tools) chat completion → raw text. Used by staged generation."""


class CutSessionStore(Protocol):
    """Persist rough-cut conversations + their generated plans (SQLite)."""

    def create_session(self, title: str = "") -> CutSession:
        """Create and return a new conversation."""

    def list_sessions(self) -> list[CutSession]:
        """List sessions, newest activity first."""

    def get_session(self, session_id: int) -> CutSession | None:
        """Fetch one session by id."""

    def delete_session(self, session_id: int) -> None:
        """Delete a session and cascade its messages + plans."""

    def set_session_status(self, session_id: int, status: str) -> None:
        """Update a session's status ('idle'|'running'|'error')."""

    def set_session_request(self, session_id: int, request_json: str) -> None:
        """Store the latest structured request params (JSON) for a session."""

    def get_session_request(self, session_id: int) -> str | None:
        """Return the stored request params JSON for a session, if any."""

    def append_message(self, session_id: int, message: ChatMessage) -> None:
        """Append one chat message to a session (bumps updated_at)."""

    def get_messages(self, session_id: int) -> list[ChatMessage]:
        """Return a session's messages in insertion order."""

    def save_plan(self, session_id: int, plan: CutPlan) -> None:
        """Store a generated plan as the session's latest."""

    def get_latest_plan(self, session_id: int) -> CutPlan | None:
        """Return the most recent plan for a session, if any."""
