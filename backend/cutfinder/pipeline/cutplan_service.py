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
from ..domain.models import ChatMessage, RoughCutRequest
from ..ports.cutplan import CutSessionStore

logger = logging.getLogger(__name__)


class CutPlanService:
    """Handle a single user message in a rough-cut conversation."""

    def __init__(self, store: CutSessionStore, director: CutDirector) -> None:
        self._store = store
        self._director = director

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

        # Persist the user's message before running so a crash still records it.
        self._store.append_message(session_id, ChatMessage(role="user", content=user_text))
        self._store.set_session_status(session_id, "running")

        # Resolve the request: an explicit one overrides + is remembered;
        # otherwise reuse the session's stored params (refine turns).
        if request is not None:
            self._store.set_session_request(
                session_id, json.dumps(request.model_dump(), ensure_ascii=False),
            )
            req = request
        else:
            req = self._load_request(session_id) or RoughCutRequest()

        # History excludes the just-appended user message (passed separately).
        history = self._store.get_messages(session_id)[:-1]

        try:
            result = self._director.run(req, history, user_text)
        except Exception:
            self._store.set_session_status(session_id, "error")
            raise

        self._store.append_message(
            session_id, ChatMessage(role="assistant", content=result.assistant_text),
        )
        if result.plan is not None:
            self._store.save_plan(session_id, result.plan)
        self._store.set_session_status(session_id, "idle")
        return result

    def _load_request(self, session_id: int) -> RoughCutRequest | None:
        raw = self._store.get_session_request(session_id)
        if not raw:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            return RoughCutRequest(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
