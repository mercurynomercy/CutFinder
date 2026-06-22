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
    # Searches all came back empty → diagnostic points at missing footage.
    assert "素材" in result.assistant_text


def test_round_cap_with_footage_but_no_plan_suggests_retry() -> None:
    # Searches find footage but the model never emits a plan → retry guidance.
    forever = [
        AgentStep(tool_calls=[_tc("search_footage", {})]) for _ in range(50)
    ]
    director = CutDirector(
        FakeLLM(forever), FakeRetriever([ClipBrief(clip_id=1, roll="a")], _details()),
        max_tool_rounds=4,
    )
    result = director.run(RoughCutRequest(), [], "go")
    assert result.plan is None
    assert "重试" in result.assistant_text


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


# ── staged generation (the primary path) ───────────────────────

class FakeCompleteLLM:
    """Returns a canned completion string; records messages seen."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls: list[list[dict[str, Any]]] = []

    def run(self, messages: Any, tools: Any) -> AgentStep:  # unused in staged path
        return AgentStep(content="")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        self.calls.append([dict(m) for m in messages])
        return self.raw


class ScriptedCompleteLLM:
    """Pops one canned completion per call (for per-date generation tests)."""

    def __init__(self, raws: list[str]) -> None:
        self._raws = list(raws)
        self.calls: list[list[dict[str, Any]]] = []

    def run(self, messages: Any, tools: Any) -> AgentStep:
        return AgentStep(content="")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        self.calls.append([dict(m) for m in messages])
        return self._raws.pop(0) if self._raws else "{}"


def test_generate_builds_plan_from_structured_json() -> None:
    raw = (
        '{"note": "ok", "shots": ['
        '{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12, "content": "开场白"},'
        '{"clip_id": 2, "roll": "b", "in_s": 0, "out_s": 6, "content": "山景"}]}'
    )
    director = CutDirector(
        FakeCompleteLLM(raw),
        FakeRetriever(
            [
                ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00"),
                ClipBrief(clip_id=2, roll="b", capture_time="2026-04-25T09:01:00"),
            ],
            _details(),
        ),
    )
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert result.plan is not None
    assert result.plan.total_s == 18.0
    assert result.plan.shots[1].out_s == 6.0  # clip 2 clamped within 8s
    # Chapter is forced to the shooting date (date-categorized output).
    assert result.plan.chapters == ["2026-04-25"]
    assert all(s.chapter == "2026-04-25" for s in result.plan.shots)


def test_generate_one_call_per_date_with_date_chapters() -> None:
    # Two shooting dates → two completions, concatenated into date chapters.
    llm = ScriptedCompleteLLM([
        '{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}',
        '{"shots": [{"clip_id": 3, "roll": "a", "in_s": 0, "out_s": 10}]}',
    ])
    briefs = [
        ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=3, roll="a", has_transcript=True, capture_time="2026-05-09T09:00:00"),
    ]
    details = {
        1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00",
                      segments=[Segment(start_s=0, end_s=12, text="第一天")]),
        3: ClipDetail(clip_id=3, roll="a", duration_s=60.0, capture_time="2026-05-09T09:00:00",
                      segments=[Segment(start_s=0, end_s=10, text="第二天")]),
    }
    director = CutDirector(llm, FakeRetriever(briefs, details))
    result = director.generate(
        RoughCutRequest(date_from="2026-04-25", date_to="2026-05-11"), [], "按日期剪",
    )
    assert len(llm.calls) == 2                          # one LLM call per date
    assert result.plan is not None
    assert result.plan.chapters == ["2026-04-25", "2026-05-09"]
    assert [s.chapter for s in result.plan.shots] == ["2026-04-25", "2026-05-09"]
    assert result.plan.total_s == 22.0                 # 12 + 10


def test_generate_orders_day_context_by_capture_time() -> None:
    # Briefs supplied out of order; context must list them by shooting time.
    llm = ScriptedCompleteLLM(['{"shots": []}'])
    briefs = [
        ClipBrief(clip_id=2, roll="a", capture_time="2026-04-25T12:00:00"),
        ClipBrief(clip_id=1, roll="a", capture_time="2026-04-25T09:00:00"),
    ]
    details = {
        1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00"),
        2: ClipDetail(clip_id=2, roll="a", duration_s=60.0, capture_time="2026-04-25T12:00:00"),
    }
    director = CutDirector(llm, FakeRetriever(briefs, details))
    director.generate(RoughCutRequest(date_from="2026-04-25"), [], "按时间剪")
    context = llm.calls[0][-1]["content"]
    assert context.index("[1]") < context.index("[2]")  # 09:00 before 12:00


def test_generate_skips_failed_dates_but_keeps_good_ones() -> None:
    # First date returns garbage, second returns a valid shot → plan from day 2.
    llm = ScriptedCompleteLLM([
        "not json",
        '{"shots": [{"clip_id": 3, "roll": "a", "in_s": 0, "out_s": 10}]}',
    ])
    briefs = [
        ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00"),
        ClipBrief(clip_id=3, roll="a", has_transcript=True, capture_time="2026-05-09T09:00:00"),
    ]
    details = {
        1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00"),
        3: ClipDetail(clip_id=3, roll="a", duration_s=60.0, capture_time="2026-05-09T09:00:00"),
    }
    director = CutDirector(llm, FakeRetriever(briefs, details))
    result = director.generate(
        RoughCutRequest(date_from="2026-04-25", date_to="2026-05-11"), [], "按日期剪",
    )
    assert result.plan is not None
    assert result.plan.chapters == ["2026-05-09"]
    assert "2026-04-25" in result.assistant_text  # the skipped date is reported


def test_generate_fills_clip_date_and_uses_custom_prompt(
    tmp_path: Any, monkeypatch: Any,
) -> None:
    import cutfinder.config as cfg

    monkeypatch.setattr(cfg, "_GLOBAL_CONFIG_FILE", tmp_path / ".cutfinder" / "config.json")
    from cutfinder.config import save_cut_director_prompt

    save_cut_director_prompt("自定义 比例={aspect} 时长={target}风格={style}")

    raw = '{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}'
    llm = FakeCompleteLLM(raw)
    details = {
        1: ClipDetail(
            clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T10:00:00",
            library_path="/lib/A-0001.mov", segments=[Segment(start_s=0, end_s=12, text="开场白")],
        ),
    }
    director = CutDirector(
        llm,
        FakeRetriever(
            [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T10:00:00")],
            details,
        ),
    )
    result = director.generate(
        RoughCutRequest(aspect_ratio="16:9", target_min_s=900, target_max_s=1200, style_notes="轻快"),
        [], "剪一条",
    )
    assert result.plan is not None
    assert result.plan.shots[0].clip_date == "2026-04-25"  # from capture_time
    system = llm.calls[0][0]["content"]
    assert "自定义 比例=16:9" in system               # {aspect} substituted
    assert "时长=目标时长 15–20 分钟。" in system       # {target} substituted
    assert "风格=轻快" in system                        # {style} substituted


def test_generate_no_footage_returns_scan_hint() -> None:
    director = CutDirector(FakeCompleteLLM("{}"), FakeRetriever([], {}))
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "go")
    assert result.plan is None
    assert "素材" in result.assistant_text


def test_generate_bad_json_returns_retry_message() -> None:
    director = CutDirector(
        FakeCompleteLLM("not json at all"),
        FakeRetriever([ClipBrief(clip_id=1, roll="a")], _details()),
    )
    result = director.generate(RoughCutRequest(), [], "go")
    assert result.plan is None
    assert "重试" in result.assistant_text or "失败" in result.assistant_text


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
