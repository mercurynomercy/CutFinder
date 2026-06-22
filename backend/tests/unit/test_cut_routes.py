"""Tests for the rough-cut director routes (api/cut_routes.py)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cutfinder.adapters.sqlite_cutplan import MemoryCutSessionStore
from cutfinder.domain.models import ChatMessage, CutPlan, Shot


class _FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def enqueue_cutplan(
        self, session_id: int, text: str, request: Any = None, job_id: int | None = None,
    ) -> int:
        self.calls.append((session_id, text, request))
        return 42


def _client(store: Any, queue: Any = None) -> TestClient:
    from cutfinder.api.cut_routes import _build_router

    ctx = SimpleNamespace(cut_store=store, worker_queue=queue or _FakeQueue())
    app = FastAPI()
    app.include_router(_build_router(ctx))
    return TestClient(app, raise_server_exceptions=False)


def test_create_and_list_sessions() -> None:
    store = MemoryCutSessionStore()
    client = _client(store)

    resp = client.post("/api/cut/sessions", json={"title": "周末"})
    assert resp.status_code == 200
    sid = resp.json()["id"]

    listed = client.get("/api/cut/sessions").json()["sessions"]
    assert [s["id"] for s in listed] == [sid]
    assert listed[0]["title"] == "周末"


def test_get_session_returns_messages_and_plan() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    store.append_message(s.id, ChatMessage(role="user", content="剪一条"))
    store.append_message(s.id, ChatMessage(role="assistant", content="好"))
    store.save_plan(s.id, CutPlan(
        shots=[Shot(clip_id=1, roll="a", in_s=0, out_s=12, chapter="开场", clip_label="A-0001.mov")],
        chapters=["开场"], total_s=12.0,
    ))
    client = _client(store)

    body = client.get(f"/api/cut/sessions/{s.id}").json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["plan"]["total_s"] == 12.0
    assert "## 开场" in body["plan"]["markdown"]


def test_get_session_404() -> None:
    client = _client(MemoryCutSessionStore())
    assert client.get("/api/cut/sessions/999").status_code == 404


def test_prompt_get_put_reset(
    tmp_path: Any, monkeypatch: Any,
) -> None:
    import cutfinder.config as cfg
    from cutfinder.cutplan.director import DEFAULT_CUT_DIRECTOR_PROMPT

    # Isolate the machine-global config file so the real one isn't touched.
    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG_FILE", tmp_path / ".cutfinder" / "config.json")
    client = _client(MemoryCutSessionStore())

    # Unset → default.
    got = client.get("/api/cut/prompt").json()
    assert got["is_default"] is True
    assert got["prompt"] == DEFAULT_CUT_DIRECTOR_PROMPT

    # Save a custom prompt.
    put = client.put("/api/cut/prompt", json={"prompt": "我的导演提示词 {aspect}"}).json()
    assert put["is_default"] is False
    assert put["prompt"] == "我的导演提示词 {aspect}"
    assert client.get("/api/cut/prompt").json()["prompt"] == "我的导演提示词 {aspect}"

    # Reset → default again.
    reset = client.delete("/api/cut/prompt").json()
    assert reset["is_default"] is True
    assert reset["prompt"] == DEFAULT_CUT_DIRECTOR_PROMPT


def test_send_message_enqueues_with_request() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    queue = _FakeQueue()
    client = _client(store, queue)

    resp = client.post(
        f"/api/cut/sessions/{s.id}/messages",
        json={
            "text": "剪 15-20 分钟",
            "request": {"date_from": "2026-04-25", "date_to": "2026-05-11",
                        "target_min_s": 900, "target_max_s": 1200, "style_notes": "轻快"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 42
    sid, text, req = queue.calls[0]
    assert sid == s.id and text == "剪 15-20 分钟"
    assert req.date_from == "2026-04-25" and req.target_max_s == 1200

    # The user message + running status are persisted synchronously, so a
    # reopen/restart before the worker finishes still shows the message.
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["user"]
    assert msgs[0].content == "剪 15-20 分钟"
    assert store.get_session(s.id).status == "running"


def test_send_message_404_unknown_session() -> None:
    client = _client(MemoryCutSessionStore())
    resp = client.post("/api/cut/sessions/999/messages", json={"text": "hi"})
    assert resp.status_code == 404


def test_send_message_422_empty_text() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    resp = _client(store).post(f"/api/cut/sessions/{s.id}/messages", json={"text": ""})
    assert resp.status_code == 422


def test_delete_session() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    store.append_message(s.id, ChatMessage(role="user", content="x"))
    client = _client(store)

    resp = client.delete(f"/api/cut/sessions/{s.id}")
    assert resp.status_code == 200
    assert store.get_session(s.id) is None
    # Deleting again → 404.
    assert client.delete(f"/api/cut/sessions/{s.id}").status_code == 404


def test_get_plan_endpoint() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    client = _client(store)
    # No plan yet.
    assert client.get(f"/api/cut/sessions/{s.id}/plan").json()["plan"] is None
    store.save_plan(s.id, CutPlan(total_s=5.0))
    assert client.get(f"/api/cut/sessions/{s.id}/plan").json()["plan"]["total_s"] == 5.0


def test_503_when_store_unavailable() -> None:
    client = _client(store=None)
    assert client.get("/api/cut/sessions").status_code == 503
