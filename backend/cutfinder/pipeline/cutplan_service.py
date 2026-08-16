"""CutPlanService — one conversation turn: persist, run director, persist.

Sits between the worker and the :class:`CutDirector`: loads a session's
history + stored request params, runs the director, and writes the user +
assistant messages and the generated plan back to the store. Pure
orchestration over injected interfaces, so it unit-tests with fakes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..cutplan.director import CutDirector, CutDirectorResult
from ..cutplan.preflight import check_preflight
from ..cutplan.request_parse import parse_request_fields
from ..domain.models import ChatMessage, CutSession, PendingClarification, RoughCutRequest
from ..ports.cutplan import CutSessionStore

logger = logging.getLogger(__name__)


class CutPlanService:
    """Handle a single user message in a rough-cut conversation."""

    def __init__(
        self,
        store: CutSessionStore,
        director: CutDirector,
        *,
        retriever: Any | None = None,
        ui_language: str = "zh",
    ) -> None:
        self._store = store
        self._director = director
        self._retriever = retriever
        self._ui_language = ui_language

    def handle(
        self,
        session_id: int,
        user_text: str,
        request: RoughCutRequest | None = None,
    ) -> CutDirectorResult:
        """Run one turn for *session_id*; persist messages + plan; return result."""
        session = self._store.get_session(session_id)
        if session is None:
            raise ValueError(f"cut session {session_id} not found")

        if session.status == "waiting_for_input" and session.pending is not None:
            return self._resume(session, user_text)

        # Persist the user's message before running so a crash still records it.
        existing = self._store.get_messages(session_id)
        if not (existing and existing[-1].role == "user" and existing[-1].content == user_text):
            self._store.append_message(session_id, ChatMessage(role="user", content=user_text))
        self._store.set_session_status(session_id, "running")

        if not (session.title or "").strip():
            self._store.set_session_title(session_id, _derive_title(user_text, lang=self._ui_language))

        if request is not None:
            req = request
        else:
            stored = self._load_request(session_id) or RoughCutRequest()
            parsed = parse_request_fields(user_text)
            req = stored.model_copy(update=parsed) if parsed else stored
            if not (parsed.keys() & {"date_from", "date_to"}) and (
                self._store.get_latest_plan(session_id) is None
            ):
                req = req.model_copy(update={"date_from": None, "date_to": None})
        self._store.set_session_request(
            session_id, json.dumps(req.model_dump(), ensure_ascii=False),
        )

        if self._retriever is not None:
            pending = check_preflight(
                req, self._retriever, self._store.get_asked(session_id), lang=self._ui_language,
            )
            if pending is not None:
                self._store.mark_asked(session_id, pending.kind.removeprefix("preflight_"))
                return self._pause(session_id, pending)

        history = self._store.get_messages(session_id)[:-1]
        prior_plan = self._store.get_latest_plan(session_id)

        try:
            result = self._director.generate(
                req, history, user_text,
                prior_plan=prior_plan,
                on_progress=lambda text: self._store.set_session_progress(session_id, text),
                on_partial=lambda plan: self._store.save_plan(session_id, plan),
                on_day=lambda idx, n: self._store.set_session_day_progress(session_id, idx, n),
            )
        except Exception:
            self._store.set_session_status(session_id, "error")
            self._store.clear_session_progress(session_id)
            raise
        return self._finish(session_id, result)

    def _pause(self, session_id: int, pending: PendingClarification) -> CutDirectorResult:
        """Persist a paused turn: the question becomes a normal assistant message."""
        self._store.append_message(session_id, ChatMessage(role="assistant", content=pending.question))
        self._store.set_session_pending(session_id, pending)
        self._store.set_session_status(session_id, "waiting_for_input")
        self._store.clear_session_progress(session_id)
        return CutDirectorResult(pending.question, None, pending=pending)

    def _finish(self, session_id: int, result: CutDirectorResult) -> CutDirectorResult:
        """Persist a director result: either another pause, or a completed turn."""
        if result.pending is not None:
            return self._pause(session_id, result.pending)
        self._store.append_message(
            session_id, ChatMessage(role="assistant", content=result.assistant_text),
        )
        if result.plan is not None:
            self._store.save_plan(session_id, result.plan)
        self._store.set_session_status(session_id, "idle")
        self._store.clear_session_progress(session_id)
        return result

    def _resume(self, session: CutSession, user_text: str) -> CutDirectorResult:
        """Continue a paused turn: pre-flight re-enters ``handle`` fresh; a
        paused day resumes its exact tool-loop conversation (Task 12)."""
        session_id = session.id
        assert session_id is not None
        pending = session.pending
        assert pending is not None
        self._store.clear_session_pending(session_id)

        if pending.kind in ("preflight_date", "preflight_duration"):
            self._store.set_session_status(session_id, "idle")
            return self.handle(session_id, user_text)

        raise NotImplementedError("day_ask_user resume is implemented in Task 12/13")

    def _load_request(self, session_id: int) -> RoughCutRequest | None:
        raw = self._store.get_session_request(session_id)
        if not raw:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            return RoughCutRequest(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None


def _derive_title(user_text: str, max_len: int = 24, lang: str = "zh") -> str:
    """A short sidebar title from the first user message (first line, clipped)."""
    line = (user_text or "").strip().splitlines()[0].strip() if user_text.strip() else ""
    return line[:max_len] or ("Untitled" if lang == "en" else "未命名")
