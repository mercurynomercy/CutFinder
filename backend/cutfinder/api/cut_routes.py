"""Routes for the rough-cut director agent (§3.15).

Thin layer: validate → call the session store / worker → serialize. The
heavy lifting (tool loop, plan building, persistence) lives in the cutplan
service + director, reached via the worker queue.
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import Request  # module-level: FastAPI resolves annotations via globalns


def _build_router(ctx: Any) -> Any:
    """Construct the rough-cut ``APIRouter`` reading adapters from *ctx*."""
    from fastapi import APIRouter, HTTPException

    from cutfinder.cutplan.format import to_shotlist_markdown
    from cutfinder.domain.models import ChatMessage, CutPlan, RoughCutRequest

    router = APIRouter(prefix="/api/cut", tags=["RoughCut"])

    def _store() -> Any:
        if getattr(ctx, "cut_store", None) is None:
            raise HTTPException(status_code=503, detail="Rough-cut sessions not available")
        return ctx.cut_store

    def _session_dict(s: Any) -> dict[str, Any]:
        return {
            "id": s.id, "title": s.title, "status": s.status,
            "created_at": s.created_at, "updated_at": s.updated_at,
        }

    def _plan_dict(plan: CutPlan) -> dict[str, Any]:
        data = plan.model_dump()
        data["markdown"] = to_shotlist_markdown(plan)
        return data

    # ── sessions CRUD ────────────────────────────────────────────

    @router.post("/sessions")
    async def create_session(request: Request) -> dict[str, Any]:
        title = ""
        raw = await request.body()
        if raw and raw.strip():
            try:
                body = _json.loads(raw)
                if isinstance(body, dict):
                    title = str(body.get("title") or "")
            except _json.JSONDecodeError:
                pass
        return _session_dict(_store().create_session(title))

    @router.get("/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": [_session_dict(s) for s in _store().list_sessions()]}

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: int) -> dict[str, Any]:
        store = _store()
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in store.get_messages(session_id)
            if m.role in ("user", "assistant")
        ]
        plan = store.get_latest_plan(session_id)
        return {
            "session": _session_dict(session),
            "messages": messages,
            "plan": _plan_dict(plan) if plan is not None else None,
        }

    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: int) -> dict[str, Any]:
        store = _store()
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        store.delete_session(session_id)
        return {"status": "ok", "session_id": session_id}

    # ── messages (enqueue a director turn) ───────────────────────

    @router.post("/sessions/{session_id}/messages")
    async def send_message(session_id: int, request: Request) -> dict[str, Any]:
        from pydantic import ValidationError

        from cutfinder.api.schemas import SendCutMessageRequest

        store = _store()
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if ctx.worker_queue is None:
            raise HTTPException(status_code=503, detail="Worker queue not available")

        try:
            raw = _json.loads(await request.body() or b"{}")
            body = SendCutMessageRequest(**raw)
        except (_json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        req_obj: RoughCutRequest | None = None
        if body.request is not None:
            fields = {k: v for k, v in body.request.model_dump().items() if v is not None}
            req_obj = RoughCutRequest(**fields)

        # Persist the user message + mark the session running *now*, before the
        # job is enqueued — so it survives even if the worker is slow, queued, or
        # the process restarts before the turn finishes. The service's append is
        # idempotent, so it won't be duplicated.
        store.append_message(session_id, ChatMessage(role="user", content=body.text))
        if req_obj is not None:
            import json as _j

            store.set_session_request(session_id, _j.dumps(req_obj.model_dump(), ensure_ascii=False))
        store.set_session_status(session_id, "running")

        job_id = await ctx.worker_queue.enqueue_cutplan(session_id, body.text, req_obj)
        return {"job_id": job_id, "session_id": session_id}

    # ── latest plan ──────────────────────────────────────────────

    @router.get("/sessions/{session_id}/plan")
    async def get_plan(session_id: int) -> dict[str, Any]:
        store = _store()
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")
        plan = store.get_latest_plan(session_id)
        return {"plan": _plan_dict(plan) if plan is not None else None}

    return router


__all__: list[str] = []
