"""Unit tests for CutDirector — fake LLM (scripted tool calls) + fake tools.

These cover the deterministic scaffold: A-roll spine + B-roll wiring, in/out
clamping, the duration-guardrail re-prompt, the round cap, and the vision
budget. No real models are touched.
"""

from __future__ import annotations

from typing import Any

from cutfinder.cutplan.director import CutDirector
from cutfinder.domain.models import (
    ClipBrief,
    ClipDetail,
    RoughCutRequest,
    Segment,
    VisionResult,
)
from cutfinder.ports.cutplan import AgentStep, ToolCall


# ── fakes ────────────────────────────────────────────────────────

class FakeLLM:
    """Returns a scripted list of AgentSteps; records the messages it saw."""

    def __init__(self, steps: list[AgentStep]) -> None:
        self._steps = steps
        self.calls: list[list[dict[str, Any]]] = []

    def run(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentStep:
        self.calls.append([dict(m) for m in messages])
        if not self._steps:
            return AgentStep(content="done")
        return self._steps.pop(0)


class FakeRetriever:
    def __init__(self, briefs: list[ClipBrief], details: dict[int, ClipDetail]) -> None:
        self._briefs = briefs
        self._details = details
        self.searches: list[dict[str, Any]] = []

    def search_footage(self, **kwargs: Any) -> list[ClipBrief]:
        self.searches.append(kwargs)
        return self._briefs

    def get_clip_detail(self, clip_id: int) -> ClipDetail | None:
        return self._details.get(clip_id)


class FakeInspector:
    def __init__(self) -> None:
        self.count = 0

    def inspect_broll(self, clip_id: int) -> VisionResult | None:
        self.count += 1
        return VisionResult(description=f"clip {clip_id} visuals", tags=["x"])


def _tc(name: str, args: dict[str, Any], cid: str = "c1") -> ToolCall:
    return ToolCall(id=cid, name=name, arguments=args)


def _details() -> dict[int, ClipDetail]:
    return {
        1: ClipDetail(
            clip_id=1, roll="a", duration_s=60.0, library_path="/lib/A-0001.mov",
            segments=[Segment(start_s=0, end_s=12, text="开场白")],
        ),
        2: ClipDetail(clip_id=2, roll="b", duration_s=8.0, library_path="/lib/B-0001.mov"),
    }


# ── tests ────────────────────────────────────────────────────────

def test_aroll_spine_plus_broll_finalizes() -> None:
    llm = FakeLLM([
        AgentStep(tool_calls=[_tc("search_footage", {"roll": "a", "date_from": "2026-04-25"})]),
        AgentStep(tool_calls=[_tc("get_clip_detail", {"clip_id": 1})]),
        AgentStep(content="搞定", tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12, "content": "开场白", "chapter": "开场"},
            {"clip_id": 2, "roll": "b", "in_s": 0, "out_s": 6, "content": "山景", "chapter": "开场"},
        ]})]),
    ])
    retr = FakeRetriever([ClipBrief(clip_id=1, roll="a")], _details())
    director = CutDirector(llm, retr, FakeInspector())

    result = director.run(RoughCutRequest(date_from="2026-04-25"), [], "剪一条开场")

    assert result.plan is not None
    assert result.assistant_text == "搞定"
    assert len(result.plan.shots) == 2
    assert result.plan.total_s == 18.0  # 12 + 6
    assert result.plan.shots[0].clip_label == "A-0001.mov"
    assert result.plan.shots[0].thumb_ref == "/api/clips/1/thumbnail"
    assert retr.searches[0]["roll"] == "a"


def test_in_out_clamped_to_clip_duration() -> None:
    llm = FakeLLM([
        AgentStep(tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 2, "roll": "b", "in_s": 0, "out_s": 999},  # clip is only 8s
        ]})]),
    ])
    director = CutDirector(llm, FakeRetriever([], _details()))
    result = director.run(RoughCutRequest(), [], "go")
    assert result.plan is not None
    assert result.plan.shots[0].out_s == 8.0  # clamped to duration


def test_duration_guardrail_reprompts_once_then_finalizes() -> None:
    # Target 60-120s; first plan is 18s (under) → re-prompt; second plan accepted
    # even though still under (we don't loop forever), flagged within_target=False.
    plan_args = {"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}
    llm = FakeLLM([
        AgentStep(tool_calls=[_tc("emit_plan", plan_args)]),
        AgentStep(content="还是短", tool_calls=[_tc("emit_plan", plan_args)]),
    ])
    director = CutDirector(llm, FakeRetriever([], _details()))
    result = director.run(
        RoughCutRequest(target_min_s=60, target_max_s=120), [], "go",
    )
    assert len(llm.calls) == 2  # re-prompted exactly once
    assert result.plan is not None
    assert result.plan.within_target is False


def test_round_cap_finalizes_without_runaway() -> None:
    # LLM keeps searching forever; director must stop at the cap.
    forever = [
        AgentStep(tool_calls=[_tc("search_footage", {})]) for _ in range(50)
    ]
    llm = FakeLLM(forever)
    director = CutDirector(llm, FakeRetriever([], _details()), max_tool_rounds=5)
    result = director.run(RoughCutRequest(), [], "go")
    assert len(llm.calls) == 5  # capped
    assert result.plan is None
    assert "最大工具轮数" in result.assistant_text


def test_vision_budget_enforced() -> None:
    inspector = FakeInspector()
    llm = FakeLLM([
        AgentStep(tool_calls=[_tc("inspect_broll", {"clip_id": 2})]),
        AgentStep(tool_calls=[_tc("inspect_broll", {"clip_id": 2})]),  # over budget
        AgentStep(content="ok"),
    ])
    director = CutDirector(llm, FakeRetriever([], _details()), inspector, vision_budget=1)
    result = director.run(RoughCutRequest(), [], "go")
    assert inspector.count == 1  # second call refused by budget
    assert result.assistant_text == "ok"


def test_plain_reply_ends_turn_without_plan() -> None:
    llm = FakeLLM([AgentStep(content="请先扫描素材入库。")])
    director = CutDirector(llm, FakeRetriever([], {}))
    result = director.run(RoughCutRequest(), [], "用上周的素材")
    assert result.plan is None
    assert "扫描" in result.assistant_text


def test_history_is_included_in_messages() -> None:
    from cutfinder.domain.models import ChatMessage
    llm = FakeLLM([AgentStep(content="ok")])
    director = CutDirector(llm, FakeRetriever([], {}))
    history = [
        ChatMessage(role="user", content="第一轮需求"),
        ChatMessage(role="assistant", content="第一版分镜"),
    ]
    director.run(RoughCutRequest(), history, "第三段太长")
    sent = llm.calls[0]
    contents = [m["content"] for m in sent]
    assert "第一轮需求" in contents
    assert "第一版分镜" in contents
    assert "第三段太长" in contents
