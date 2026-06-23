"""Unit tests for CutPlanService — persistence + director orchestration."""

from __future__ import annotations

from typing import Any

import pytest

from cutfinder.adapters.sqlite_cutplan import MemoryCutSessionStore
from cutfinder.cutplan.director import CutDirectorResult
from cutfinder.domain.models import CutPlan, RoughCutRequest, Shot
from cutfinder.pipeline.cutplan_service import CutPlanService


class FakeDirector:
    """Records (request, history, user_text) and returns a canned result.

    Optionally emits scripted progress strings / partial plans through the
    callbacks the service passes, to exercise the live-progress wiring.
    """

    def __init__(
        self,
        result: CutDirectorResult,
        progress_steps: list[str] | None = None,
        partial_plans: list[CutPlan] | None = None,
    ) -> None:
        self.result = result
        self.calls: list[tuple[RoughCutRequest, list[Any], str]] = []
        self._progress_steps = progress_steps or []
        self._partial_plans = partial_plans or []

    def generate(
        self,
        request: RoughCutRequest,
        history: list[Any],
        user_text: str,
        *,
        on_progress: Any = None,
        on_partial: Any = None,
    ) -> CutDirectorResult:
        self.calls.append((request, list(history), user_text))
        for s in self._progress_steps:
            if on_progress:
                on_progress(s)
        for p in self._partial_plans:
            if on_partial:
                on_partial(p)
        return self.result


def _plan() -> CutPlan:
    return CutPlan(shots=[Shot(clip_id=1, roll="a", in_s=0, out_s=10)], total_s=10.0)


def test_handle_persists_messages_and_plan() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("这是分镜", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    result = svc.handle(s.id, "剪一条", RoughCutRequest(date_from="2026-04-25"))

    assert result.plan is not None
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "剪一条"
    assert msgs[1].content == "这是分镜"
    assert store.get_latest_plan(s.id).total_s == 10.0
    assert store.get_session(s.id).status == "idle"
    # The explicit request was passed through and remembered.
    assert director.calls[0][0].date_from == "2026-04-25"


def test_handle_saves_partial_plan_and_clears_progress() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    partial = CutPlan(shots=[Shot(clip_id=9, roll="b", in_s=0, out_s=5)], total_s=5.0)
    # Final result carries no plan → the last saved plan is the partial one,
    # proving on_partial reached the store mid-run.
    director = FakeDirector(
        CutDirectorResult("生成中", None),
        progress_steps=["正在生成第 1/2 天（2026-04-25）…"],
        partial_plans=[partial],
    )
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    svc.handle(s.id, "剪一条", RoughCutRequest())

    assert store.get_latest_plan(s.id).total_s == 5.0   # partial plan persisted
    assert store.get_session(s.id).progress == ""        # progress cleared at end


def test_refine_reuses_stored_request() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("v1", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    svc.handle(s.id, "第一轮", RoughCutRequest(target_min_s=60, target_max_s=120))
    # Second turn with no request → should reuse the stored params.
    svc.handle(s.id, "第三段太长")

    assert director.calls[1][0].target_min_s == 60
    # History on the refine turn includes the prior exchange.
    history_roles = [m.role for m in director.calls[1][1]]
    assert history_roles == ["user", "assistant"]


def test_handle_auto_titles_from_first_message() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()  # created untitled (via "新建对话")
    director = FakeDirector(CutDirectorResult("ok", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    svc.handle(s.id, "我想要生成一个初剪，用2026/4/25 到 2026/5/11的素材")

    title = store.get_session(s.id).title
    assert title and title != "未命名"
    assert title.startswith("我想要生成一个初剪")
    # A second turn must not overwrite the established title.
    svc.handle(s.id, "再短一点")
    assert store.get_session(s.id).title == title


def test_handle_parses_request_from_message_text() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("ok", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    # No explicit request object — scoping comes from the message itself.
    svc.handle(s.id, "用2026/4/25 到 2026/5/11的素材剪成一条 15~20 分钟、16:9 的 vlog")

    req = director.calls[0][0]
    assert req.date_from == "2026-04-25"
    assert req.date_to == "2026-05-11"
    assert req.target_min_s == 900.0
    assert req.target_max_s == 1200.0
    assert req.aspect_ratio == "16:9"
    # A refine turn with no new dates keeps the original scope.
    svc.handle(s.id, "第三段太长，整体再紧凑一点")
    assert director.calls[1][0].date_from == "2026-04-25"


def test_handle_marks_error_on_director_failure() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()

    class Boom:
        def generate(self, *_a: Any, **_k: Any) -> CutDirectorResult:
            raise RuntimeError("model down")

    svc = CutPlanService(store, Boom())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        svc.handle(s.id, "go")
    assert store.get_session(s.id).status == "error"
    # The user message is still recorded even though the turn failed.
    assert [m.role for m in store.get_messages(s.id)] == ["user"]


def test_handle_unknown_session_raises() -> None:
    store = MemoryCutSessionStore()
    svc = CutPlanService(store, FakeDirector(CutDirectorResult("x", None)))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.handle(999, "go")
