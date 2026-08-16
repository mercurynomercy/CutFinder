"""Unit tests for CutPlanService — persistence + director orchestration."""

from __future__ import annotations

from typing import Any

import pytest

from cutfinder.adapters.sqlite_cutplan import MemoryCutSessionStore
from cutfinder.cutplan.director import CutDirectorResult
from cutfinder.domain.models import (
    ChatMessage,
    ClipBrief,
    CutPlan,
    PendingClarification,
    RoughCutRequest,
    Shot,
)
from cutfinder.pipeline.cutplan_service import CutPlanService


def test_store_pending_round_trips() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    pending = PendingClarification(
        kind="preflight_date", question="请指定日期范围", options=["2026-04-25", "2026-04-26"],
    )

    store.set_session_pending(s.id, pending)
    store.set_session_status(s.id, "waiting_for_input")

    got = store.get_session(s.id)
    assert got.status == "waiting_for_input"
    assert got.pending == pending

    store.clear_session_pending(s.id)
    assert store.get_session(s.id).pending is None


def test_store_tracks_already_asked_fields() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()

    assert store.get_asked(s.id) == set()
    store.mark_asked(s.id, "date")
    assert store.get_asked(s.id) == {"date"}
    store.mark_asked(s.id, "duration")
    assert store.get_asked(s.id) == {"date", "duration"}


def test_reset_interrupted_sessions_skips_waiting_for_input() -> None:
    store = MemoryCutSessionStore()
    s1 = store.create_session()
    s2 = store.create_session()
    store.set_session_status(s1.id, "running")
    store.set_session_status(s2.id, "waiting_for_input")

    n = store.reset_interrupted_sessions()

    assert n == 1
    assert store.get_session(s1.id).status == "idle"
    assert store.get_session(s2.id).status == "waiting_for_input"


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
        day_steps: list[tuple[int, int]] | None = None,
        resume_result: CutDirectorResult | None = None,
    ) -> None:
        self.result = result
        self.calls: list[tuple[RoughCutRequest, list[Any], str]] = []
        self.prior_plans: list[CutPlan | None] = []
        self._progress_steps = progress_steps or []
        self._partial_plans = partial_plans or []
        self._day_steps = day_steps or []
        self._resume_result = resume_result
        self.resume_calls: list[tuple[RoughCutRequest, dict[str, Any], str, CutPlan | None]] = []

    def generate(
        self,
        request: RoughCutRequest,
        history: list[Any],
        user_text: str,
        *,
        prior_plan: CutPlan | None = None,
        on_progress: Any = None,
        on_partial: Any = None,
        on_day: Any = None,
    ) -> CutDirectorResult:
        self.calls.append((request, list(history), user_text))
        self.prior_plans.append(prior_plan)
        for s in self._progress_steps:
            if on_progress:
                on_progress(s)
        for p in self._partial_plans:
            if on_partial:
                on_partial(p)
        for idx, n in self._day_steps:
            if on_day:
                on_day(idx, n)
        return self.result

    def resume_day(
        self,
        request: RoughCutRequest,
        resume_state: dict[str, Any],
        answer_text: str,
        *,
        prior_plan: CutPlan | None = None,
        on_progress: Any = None,
        on_partial: Any = None,
        on_day: Any = None,
    ) -> CutDirectorResult:
        self.resume_calls.append((request, resume_state, answer_text, prior_plan))
        assert self._resume_result is not None
        return self._resume_result


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


def test_handle_forwards_day_progress_to_store() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("ok", _plan()), day_steps=[(1, 3), (2, 3)])
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    calls: list[tuple[int, int]] = []
    orig = store.set_session_day_progress

    def spy(session_id: int, day_index: int, day_total: int) -> None:
        calls.append((day_index, day_total))
        orig(session_id, day_index, day_total)

    store.set_session_day_progress = spy  # type: ignore[method-assign]

    svc.handle(s.id, "剪一条", RoughCutRequest())

    assert calls == [(1, 3), (2, 3)]
    # Progress is cleared once the turn finishes (same lifecycle as `progress`).
    session = store.get_session(s.id)
    assert session.day_index is None
    assert session.day_total is None


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


def test_handle_drops_remembered_dates_when_prior_turn_made_no_plan() -> None:
    """A date range that produced nothing must not poison every follow-up.

    Turn 1 scoped to a range with no footage → no plan. Turn 2 mentions no date,
    so inheriting turn 1's range would just repeat "no footage in that range";
    clear it instead and let the director search the whole library.
    """
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("没有在该日期范围找到已编目的素材。", None))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    svc.handle(s.id, "用 2026/8/31 的素材剪一个 10 分钟的 vlog")
    assert director.calls[0][0].date_from == "2026-08-31"

    svc.handle(s.id, "帮我剪一个 vlog 10 分钟的")
    assert director.calls[1][0].date_from is None
    assert director.calls[1][0].date_to is None
    # Non-date scoping is still remembered.
    assert director.calls[1][0].target_min_s == 600.0


def test_refine_passes_prior_plan_as_merge_base() -> None:
    # The latest stored plan is handed to the director as prior_plan so a refine
    # turn merges over it instead of replacing the whole timeline (task 28).
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("v1", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    svc.handle(s.id, "第一轮", RoughCutRequest())
    assert director.prior_plans[0] is None          # no plan yet on the first turn
    svc.handle(s.id, "增加一份 2026-05-11")
    assert director.prior_plans[1] is not None        # the v1 plan is the merge base
    assert director.prior_plans[1].total_s == 10.0


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


class FakePreflightRetriever:
    def __init__(self, briefs: list[Any]) -> None:
        self._briefs = briefs

    def search_footage(self, **kwargs: Any) -> list[Any]:
        return self._briefs

    def get_clip_detail(self, clip_id: int) -> Any:
        return None


def test_handle_pauses_for_missing_date_before_calling_director() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("不应该被调用", _plan()))
    retriever = FakePreflightRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    svc = CutPlanService(store, director, retriever=retriever)  # type: ignore[arg-type]

    result = svc.handle(s.id, "帮我剪个 vlog")

    assert director.calls == []  # never reached the (expensive) director
    assert result.pending is not None
    assert result.pending.kind == "preflight_date"
    session = store.get_session(s.id)
    assert session.status == "waiting_for_input"
    assert session.pending is not None
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == result.pending.question


def test_handle_resumes_preflight_pause_as_a_normal_turn() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("生成完成", _plan()))
    retriever = FakePreflightRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    svc = CutPlanService(store, director, retriever=retriever)  # type: ignore[arg-type]

    svc.handle(s.id, "帮我剪个 vlog")  # pauses on date
    assert store.get_session(s.id).status == "waiting_for_input"

    result = svc.handle(s.id, "2026/04/25")  # user answers with a real date

    # Duration is still missing but was never asked this session before the
    # date pause resolved — the resumed turn re-checks and would pause again
    # on duration rather than silently reaching the director. Confirm that:
    assert director.calls == []
    assert result.plan is None
    assert result.pending is not None
    assert result.pending.kind == "preflight_duration"
    assert store.get_session(s.id).status == "waiting_for_input"
    pending2 = store.get_session(s.id).pending
    assert pending2 is not None and pending2.kind == "preflight_duration"


def test_handle_skips_preflight_when_no_retriever_wired() -> None:
    # Backward-compat default: retriever=None means pre-flight is disabled,
    # matching every pre-existing CutPlanService(store, director) call site.
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("ok", _plan()))
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    result = svc.handle(s.id, "帮我剪个 vlog")

    assert result.pending is None
    assert director.calls  # director was actually called


def test_handle_resumes_day_ask_user_via_resume_day() -> None:
    store = MemoryCutSessionStore()
    s = store.create_session()
    pending = PendingClarification(
        kind="day_ask_user", question="选哪条开场？", options=["A-0004", "A-0011"],
        resume_state={"day": "2026-04-25", "messages": [], "round_i": 0, "tool_call_id": "call-1"},
    )
    store.set_session_pending(s.id, pending)
    store.set_session_status(s.id, "waiting_for_input")
    store.append_message(s.id, ChatMessage(role="assistant", content="选哪条开场？"))
    resume_result = CutDirectorResult("好的", _plan())
    director = FakeDirector(CutDirectorResult("不应该被调用", None), resume_result=resume_result)
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    result = svc.handle(s.id, "A-0004")

    assert result is resume_result
    assert director.resume_calls[0][1] == pending.resume_state
    assert director.resume_calls[0][2] == "A-0004"
    session = store.get_session(s.id)
    assert session.status == "idle"
    assert session.pending is None
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["assistant", "user", "assistant"]
    assert msgs[1].content == "A-0004"
    assert msgs[2].content == "好的"


def test_handle_resumes_via_real_production_sequence() -> None:
    """Regression for the final-review Finding 1 (Critical): the resume gate
    must not depend on session.status.

    cut_routes.send_message persists the user message and flips status to
    "running" *synchronously*, before enqueueing the worker job — so by the
    time the worker calls handle(), status is already "running", not
    "waiting_for_input" (every other pause/resume test in this file sets
    status directly to "waiting_for_input" and so never exercises this path).
    Gating _resume on session.pending alone (not status) is what makes this
    work; and since the route already appended the user message, handle()
    must not duplicate it.
    """
    store = MemoryCutSessionStore()
    s = store.create_session()
    pending = PendingClarification(
        kind="day_ask_user", question="选哪条开场？", options=["A-0004", "A-0011"],
        resume_state={"day": "2026-04-25", "messages": [], "round_i": 0, "tool_call_id": "call-1"},
    )
    store.set_session_pending(s.id, pending)
    store.set_session_status(s.id, "waiting_for_input")
    store.append_message(s.id, ChatMessage(role="assistant", content="选哪条开场？"))

    # Mirror cut_routes.send_message exactly: append the user message via the
    # store, then flip status to "running" synchronously — BEFORE handle() runs.
    store.append_message(s.id, ChatMessage(role="user", content="A-0004"))
    store.set_session_status(s.id, "running")

    resume_result = CutDirectorResult("好的", _plan())
    director = FakeDirector(CutDirectorResult("不应该被调用", None), resume_result=resume_result)
    svc = CutPlanService(store, director)  # type: ignore[arg-type]

    result = svc.handle(s.id, "A-0004")

    assert result is resume_result
    assert director.calls == []  # generate() must NOT fire — this is a resume
    assert director.resume_calls  # resume_day fired instead
    assert director.resume_calls[0][1] == pending.resume_state
    assert director.resume_calls[0][2] == "A-0004"
    # The route already appended the user message — handle() must not duplicate it.
    msgs = store.get_messages(s.id)
    assert [m.role for m in msgs] == ["assistant", "user", "assistant"]
    assert msgs[1].content == "A-0004"
    session = store.get_session(s.id)
    assert session.status == "idle"
    assert session.pending is None


def test_handle_full_preflight_chain_preserves_date_through_to_generation() -> None:
    """Regression for the final-review Finding 2 (Critical): a date resolved
    via pre-flight must survive a later pre-flight pause in the same chain.

    Turn 1 (no date) -> pauses asking for a date. Turn 2 (answers date) ->
    date resolved and saved, but duration is still missing -> pauses AGAIN
    asking for duration (no plan generated yet, so the "drop remembered
    dates" heuristic is still armed). Turn 3 (answers duration) -> must
    finally reach the director with turn 2's date intact, not wiped.
    """
    store = MemoryCutSessionStore()
    s = store.create_session()
    director = FakeDirector(CutDirectorResult("生成完成", _plan()))
    retriever = FakePreflightRetriever([
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-26T09:00:00"),
    ])
    svc = CutPlanService(store, director, retriever=retriever)  # type: ignore[arg-type]

    r1 = svc.handle(s.id, "帮我剪个 vlog")
    assert r1.pending is not None and r1.pending.kind == "preflight_date"

    r2 = svc.handle(s.id, "2026-04-25")
    assert r2.pending is not None and r2.pending.kind == "preflight_duration"
    assert director.calls == []  # still hasn't reached the director

    r3 = svc.handle(s.id, "10 分钟")

    assert r3.pending is None
    assert director.calls  # finally reached the director
    assert director.calls[0][0].date_from == "2026-04-25"
