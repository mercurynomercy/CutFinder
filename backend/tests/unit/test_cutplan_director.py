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


# ── per-day mini-agent (mode="agent", task 26) ──────────────────

class FakeAgentLLM:
    """run() pops scripted AgentSteps; complete() returns canned JSON (fallback)."""

    def __init__(self, steps: list[AgentStep], raw: str = "{}") -> None:
        self._steps = steps
        self.raw = raw
        self.run_calls = 0
        self.complete_calls = 0

    def run(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentStep:
        self.run_calls += 1
        self.tools_seen = tools
        return self._steps.pop(0) if self._steps else AgentStep(content="done")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        self.complete_calls += 1
        return self.raw


def test_generate_agent_mode_converges_via_tool_loop() -> None:
    # Day worker deep-dives one A-roll (get_clip_detail) then emit_plan.
    llm = FakeAgentLLM([
        AgentStep(tool_calls=[_tc("get_clip_detail", {"clip_id": 1})]),
        AgentStep(content="搞定", tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12, "content": "开场白"},
        ]})]),
    ])
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()))  # default mode="agent"
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")

    assert result.plan is not None
    assert result.plan.total_s == 12.0
    assert result.plan.chapters == ["2026-04-25"]
    assert llm.complete_calls == 0  # converged via tools, no staged fall back
    # Worker is not given search_footage (only detail / inspect / emit).
    assert {t["function"]["name"] for t in llm.tools_seen} == {
        "get_clip_detail", "inspect_broll", "emit_plan",
    }


def test_generate_agent_falls_back_to_staged_on_nonconvergence() -> None:
    # run() never emits a plan (keeps inspecting) → round cap → staged complete().
    looping = [AgentStep(tool_calls=[_tc("get_clip_detail", {"clip_id": 1})]) for _ in range(50)]
    raw = '{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}'
    llm = FakeAgentLLM(looping, raw=raw)
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()), max_tool_rounds=3)
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")

    assert llm.run_calls == 3          # hit the per-day round cap
    assert llm.complete_calls == 1     # then fell back to staged JSON for the day
    assert result.plan is not None
    assert result.plan.total_s == 12.0


def test_run_day_dedups_repeated_tool_calls() -> None:
    # Model inspects the same B-roll twice (hallucinated repeat) → the second is
    # short-circuited by the dedup guard, not re-executed (inspector hit once).
    inspector = FakeInspector()
    llm = FakeAgentLLM([
        AgentStep(tool_calls=[_tc("inspect_broll", {"clip_id": 2})]),
        AgentStep(tool_calls=[_tc("inspect_broll", {"clip_id": 2})]),  # identical → deduped
        AgentStep(content="ok", tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 2, "roll": "b", "in_s": 0, "out_s": 6},
        ]})]),
    ])
    briefs = [ClipBrief(clip_id=2, roll="b", capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()), inspector, vision_budget=5)
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")

    assert result.plan is not None
    assert inspector.count == 1  # second identical inspect_broll deduped, not re-run
    assert llm.complete_calls == 0


def test_generate_staged_mode_skips_tool_loop() -> None:
    raw = '{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}'
    llm = FakeAgentLLM([], raw=raw)
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()), mode="staged")
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")

    assert llm.run_calls == 0          # staged mode never enters the tool loop
    assert llm.complete_calls == 1
    assert result.plan is not None


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


# ── prose recovery + lean agent context (busy-day fix) ──────────

def test_run_day_nudges_once_on_prose_then_emits() -> None:
    # First reply is prose (no tool call) → nudged, NOT bailed; second emits.
    llm = FakeAgentLLM([
        AgentStep(content="我先看看这天的素材"),  # no tool_calls
        AgentStep(tool_calls=[_tc("emit_plan", {"shots": [
            {"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12},
        ]})]),
    ])
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()))
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert result.plan is not None
    assert result.plan.total_s == 12.0
    assert llm.run_calls == 2          # one prose + one retry after the nudge
    assert llm.complete_calls == 0     # converged via tools, no staged fall back


def test_run_day_salvages_prose_embedded_plan() -> None:
    # Model "answers directly" with plan JSON in prose (no emit_plan call) → taken.
    llm = FakeAgentLLM([
        AgentStep(content='{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}'),
    ])
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()))
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert result.plan is not None
    assert result.plan.total_s == 12.0
    assert llm.run_calls == 1          # accepted the very first prose reply
    assert llm.complete_calls == 0     # no fall back


def test_run_day_falls_back_after_repeated_prose() -> None:
    # Prose, nudge, prose again → give up the agent loop and use staged JSON.
    raw = '{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}'
    llm = FakeAgentLLM([AgentStep(content="嗯"), AgentStep(content="还在想")], raw=raw)
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(llm, FakeRetriever(briefs, _details()))
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert llm.run_calls == 2          # prose + one nudge-retry, then bail
    assert llm.complete_calls == 1     # fell back to staged
    assert result.plan is not None


def test_agent_context_is_lean_staged_is_full() -> None:
    # Agent context omits inlined transcripts (fetched via get_clip_detail) but
    # marks A-roll with [有台词]; the staged context inlines the segment text.
    cache: dict[int, ClipDetail] = {}
    clips = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    director = CutDirector(FakeAgentLLM([]), FakeRetriever(clips, _details()))
    lean = director._build_context(clips, cache, include_transcripts=False)
    full = director._build_context(clips, cache, include_transcripts=True)
    assert "[有台词]" in lean
    assert "开场白" not in lean   # transcript text not dumped into the agent prompt
    assert "开场白" in full       # inlined for the toolless staged path


# ── refine merge by date (task 28 Part A) ───────────────────────

def _prior_plan() -> Any:
    from cutfinder.domain.models import CutPlan, Shot
    return CutPlan(shots=[
        Shot(clip_id=1, roll="a", in_s=0, out_s=12, content="第一天", chapter="2026-04-25"),
        Shot(clip_id=2, roll="a", in_s=0, out_s=8, content="第二天", chapter="2026-04-26"),
    ])


def test_refine_merges_new_date_keeping_prior_dates() -> None:
    # Prior plan has 4/25 + 4/26; this turn only regenerates 5/11 → all three
    # dates survive, ordered by date, and the prior 4/25 shots are kept verbatim.
    llm = ScriptedCompleteLLM(['{"shots": [{"clip_id": 3, "roll": "a", "in_s": 0, "out_s": 10}]}'])
    briefs = [ClipBrief(clip_id=3, roll="a", has_transcript=True, capture_time="2026-05-11T09:00:00")]
    details = {
        1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00"),
        2: ClipDetail(clip_id=2, roll="a", duration_s=60.0, capture_time="2026-04-26T09:00:00"),
        3: ClipDetail(clip_id=3, roll="a", duration_s=60.0, capture_time="2026-05-11T09:00:00"),
    }
    director = CutDirector(llm, FakeRetriever(briefs, details), mode="staged")
    result = director.generate(
        RoughCutRequest(date_from="2026-05-11", date_to="2026-05-11"), [], "增加一份 5/11",
        prior_plan=_prior_plan(),
    )
    assert result.plan is not None
    assert result.plan.chapters == ["2026-04-25", "2026-04-26", "2026-05-11"]
    assert [s.clip_id for s in result.plan.shots] == [1, 2, 3]
    assert result.plan.total_s == 30.0  # 12 + 8 + 10


def test_refine_keeps_prior_day_when_regeneration_fails() -> None:
    # This turn re-does 4/25 but the model returns garbage → the prior 4/25 day
    # is kept (not dropped, not reported as skipped).
    llm = ScriptedCompleteLLM(["not json"])
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    details = {1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00")}
    director = CutDirector(llm, FakeRetriever(briefs, details), mode="staged")
    result = director.generate(
        RoughCutRequest(date_from="2026-04-25", date_to="2026-04-25"), [], "重做 4/25",
        prior_plan=_prior_plan(),
    )
    assert result.plan is not None
    # Both prior dates remain; nothing reported as skipped.
    assert result.plan.chapters == ["2026-04-25", "2026-04-26"]
    assert "已跳过" not in result.assistant_text


# ── critic agent (task 28 Part B) ───────────────────────────────

class CriticLLM:
    """Staged completions: first the per-day shots, then the critic verdict."""

    def __init__(self, day_raws: list[str], critic_raw: str, redo_raw: str) -> None:
        self._day_raws = list(day_raws)
        self._critic_raw = critic_raw
        self._redo_raw = redo_raw
        self.critic_seen = False

    def run(self, messages: Any, tools: Any) -> AgentStep:
        return AgentStep(content="")

    def complete(self, messages: list[dict[str, Any]]) -> str:
        # The critic call is the one whose system prompt is the critic prompt.
        if messages and "审片" in str(messages[0].get("content", "")):
            self.critic_seen = True
            return self._critic_raw
        if self.critic_seen:
            return self._redo_raw  # post-critic per-day redo
        return self._day_raws.pop(0) if self._day_raws else "{}"


def test_critic_redoes_flagged_date_and_merges() -> None:
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    details = {1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00")}
    llm = CriticLLM(
        day_raws=['{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 30}]}'],
        critic_raw='{"revisions": [{"date": "2026-04-25", "issue": "节奏拖沓", "action": "剪短"}]}',
        redo_raw='{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}',
    )
    director = CutDirector(llm, FakeRetriever(briefs, details), mode="staged", critic_enabled=True)
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert llm.critic_seen is True
    assert result.plan is not None
    assert result.plan.total_s == 12.0  # critic redo (12) replaced the first cut (30)


def test_critic_disabled_skips_review() -> None:
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    details = {1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00")}
    llm = CriticLLM(
        day_raws=['{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 30}]}'],
        critic_raw='{"revisions": [{"date": "2026-04-25", "action": "剪短"}]}',
        redo_raw='{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}',
    )
    director = CutDirector(llm, FakeRetriever(briefs, details), mode="staged")  # critic off
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert llm.critic_seen is False
    assert result.plan is not None
    assert result.plan.total_s == 30.0  # unchanged, no critic pass


def test_critic_bad_json_leaves_plan_unchanged() -> None:
    briefs = [ClipBrief(clip_id=1, roll="a", has_transcript=True, capture_time="2026-04-25T09:00:00")]
    details = {1: ClipDetail(clip_id=1, roll="a", duration_s=60.0, capture_time="2026-04-25T09:00:00")}
    llm = CriticLLM(
        day_raws=['{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 30}]}'],
        critic_raw="garbage, no json",
        redo_raw='{"shots": [{"clip_id": 1, "roll": "a", "in_s": 0, "out_s": 12}]}',
    )
    director = CutDirector(llm, FakeRetriever(briefs, details), mode="staged", critic_enabled=True)
    result = director.generate(RoughCutRequest(date_from="2026-04-25"), [], "剪一条")
    assert llm.critic_seen is True
    assert result.plan is not None
    assert result.plan.total_s == 30.0  # critic returned nothing actionable → unchanged


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
