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
from ..cutplan.request_parse import parse_request_fields
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
        # The API route already persists it synchronously (so it survives a slow
        # worker / restart); only append here if it isn't already the last
        # message, to stay correct when the service is used directly (tests).
        existing = self._store.get_messages(session_id)
        if not (existing and existing[-1].role == "user" and existing[-1].content == user_text):
            self._store.append_message(session_id, ChatMessage(role="user", content=user_text))
        self._store.set_session_status(session_id, "running")

        # Auto-title an untitled conversation from its first user message, so the
        # sidebar shows something other than "未命名" after the opening turn.
        if not (session.title or "").strip():
            self._store.set_session_title(session_id, _derive_title(user_text))

        # Resolve the request. Precedence: an explicit request object (from a
        # future structured UI) wins; otherwise parse scoping (date range /
        # duration / aspect) out of the message itself and merge it over the
        # session's remembered params, so refine turns keep the original scope.
        if request is not None:
            req = request
        else:
            stored = self._load_request(session_id) or RoughCutRequest()
            parsed = parse_request_fields(user_text)
            req = stored.model_copy(update=parsed) if parsed else stored
        self._store.set_session_request(
            session_id, json.dumps(req.model_dump(), ensure_ascii=False),
        )

        # History excludes the just-appended user message (passed separately).
        history = self._store.get_messages(session_id)[:-1]

        try:
            # Deterministic per-date generation: the director either runs a
            # scoped tool loop per shooting date (agent mode) or one structured
            # JSON call per date (staged mode), with a per-day fall back. Small
            # per-day context keeps it reliable on local models (task 26).
            # The callbacks surface live progress + completed dates to the polling
            # UI: progress text into the (ephemeral) session field, and the
            # cumulative plan saved after each day so finished shots show early.
            result = self._director.generate(
                req, history, user_text,
                on_progress=lambda text: self._store.set_session_progress(session_id, text),
                on_partial=lambda plan: self._store.save_plan(session_id, plan),
            )
        except Exception:
            self._store.set_session_status(session_id, "error")
            self._store.clear_session_progress(session_id)
            raise

        self._store.append_message(
            session_id, ChatMessage(role="assistant", content=result.assistant_text),
        )
        if result.plan is not None:
            self._store.save_plan(session_id, result.plan)
        self._store.set_session_status(session_id, "idle")
        self._store.clear_session_progress(session_id)
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


def _derive_title(user_text: str, max_len: int = 24) -> str:
    """A short sidebar title from the first user message (first line, clipped)."""
    line = (user_text or "").strip().splitlines()[0].strip() if user_text.strip() else ""
    return line[:max_len] or "未命名"
