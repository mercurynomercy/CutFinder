"""Unit tests for SqliteCutSessionStore (in-memory) — sessions/messages/plans."""

from __future__ import annotations

from cutfinder.adapters.sqlite_cutplan import MemoryCutSessionStore
from cutfinder.domain.models import ChatMessage, CutPlan, Shot


def test_create_list_get_session() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session(title="周末 vlog")
    assert s.id is not None
    assert s.status == "idle"

    listed = store.list_sessions()
    assert [x.id for x in listed] == [s.id]
    assert store.get_session(s.id).title == "周末 vlog"
    assert store.get_session(9999) is None


def test_messages_roundtrip_and_order() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    store.append_message(s.id, ChatMessage(role="user", content="剪一条"))
    store.append_message(s.id, ChatMessage(role="assistant", content="好的"))
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "剪一条"


def test_save_and_get_latest_plan() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    p1 = CutPlan(shots=[Shot(clip_id=1, roll="a", in_s=0, out_s=10)], total_s=10.0)
    p2 = CutPlan(shots=[Shot(clip_id=2, roll="b", in_s=0, out_s=5)], total_s=5.0)
    store.save_plan(s.id, p1)
    store.save_plan(s.id, p2)
    latest = store.get_latest_plan(s.id)
    assert latest is not None
    assert latest.total_s == 5.0
    assert latest.shots[0].clip_id == 2


def test_delete_cascades_messages_and_plans() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    store.append_message(s.id, ChatMessage(role="user", content="x"))
    store.save_plan(s.id, CutPlan(total_s=1.0))

    store.delete_session(s.id)

    assert store.get_session(s.id) is None
    assert store.get_messages(s.id) == []
    assert store.get_latest_plan(s.id) is None


def test_status_and_request_updates() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    store.set_session_status(s.id, "running")
    assert store.get_session(s.id).status == "running"
    store.set_session_request(s.id, '{"date_from":"2026-04-25"}')
    # request_json isn't surfaced on CutSession; just assert no error + still gettable.
    assert store.get_session(s.id) is not None
