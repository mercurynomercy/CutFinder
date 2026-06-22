"""CutDirector — constrained tool-calling loop that builds a shot list.

The LLM does the *creative* selection (which A-roll lines form the spine,
which B-roll covers them, how tight the rhythm is). Everything that must be
correct — duration arithmetic, in/out clamping, the vision-call budget, the
round cap — is deterministic Python here, so a flaky local function-caller
can't produce a broken or runaway plan.

Tools the model may call: ``search_footage``, ``get_clip_detail``,
``inspect_broll`` (budgeted), and ``emit_plan`` to finalize. The director
never lets the model do the timeline math: it recomputes ``total_s`` and the
target check itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.models import (
    ChatMessage,
    ClipDetail,
    CutPlan,
    RoughCutRequest,
    Shot,
)
from ..ports.cutplan import BrollInspector, FootageRetriever, LLMAgentClient

# ── Tool schemas (OpenAI function-calling format) ────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_footage",
            "description": "Search the cataloged footage library for candidate clips in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "ISO date YYYY-MM-DD (inclusive)"},
                    "date_to": {"type": "string", "description": "ISO date YYYY-MM-DD (inclusive)"},
                    "roll": {"type": "string", "enum": ["a", "b"], "description": "a = narrated A-roll, b = B-roll"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string", "description": "Full-text query over summary/description/transcript"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clip_detail",
            "description": "Get transcript segments (A-roll), existing keyframe cut points, and metadata for one clip.",
            "parameters": {
                "type": "object",
                "properties": {"clip_id": {"type": "integer"}},
                "required": ["clip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_broll",
            "description": "Look at a B-roll clip's actual frames (vision model) when text metadata is not enough. Use sparingly.",
            "parameters": {
                "type": "object",
                "properties": {"clip_id": {"type": "integer"}},
                "required": ["clip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_plan",
            "description": "Finalize the rough cut as an ordered shot list. Each shot is a sub-clip in/out window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "clip_id": {"type": "integer"},
                                "roll": {"type": "string", "enum": ["a", "b"]},
                                "in_s": {"type": "number"},
                                "out_s": {"type": "number"},
                                "content": {"type": "string", "description": "台词 or 画面内容"},
                                "rationale": {"type": "string", "description": "用途·理由"},
                                "chapter": {"type": "string", "description": "section / chapter title"},
                            },
                            "required": ["clip_id", "roll", "in_s", "out_s"],
                        },
                    },
                    "note": {"type": "string", "description": "optional closing note to the user"},
                },
                "required": ["shots"],
            },
        },
    },
]

@dataclass
class CutDirectorResult:
    """Outcome of one turn: the assistant's reply plus the (maybe new) plan."""

    assistant_text: str
    plan: CutPlan | None


class CutDirector:
    """Run the bounded tool-calling loop for one conversation turn."""

    def __init__(
        self,
        llm: LLMAgentClient,
        retriever: FootageRetriever,
        inspector: BrollInspector | None = None,
        *,
        max_tool_rounds: int = 24,
        vision_budget: int = 6,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._inspector = inspector
        self._max_tool_rounds = max(1, max_tool_rounds)
        self._vision_budget = max(0, vision_budget)

    # ── public entry ─────────────────────────────────────────────

    def run(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
    ) -> CutDirectorResult:
        """Generate / refine a plan for *user_text* given prior *history*."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt(request)}]
        for m in history:
            if m.role in ("user", "assistant") and m.content:
                messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": user_text})

        clip_cache: dict[int, ClipDetail] = {}
        vision_used = 0
        searches = 0          # how many search_footage calls were made
        clips_seen = 0        # max clips any single search returned
        nudged = False        # whether we force-pushed an emit_plan reminder
        last_plan: CutPlan | None = None
        reprompted = False

        for round_i in range(self._max_tool_rounds):
            step = self._llm.run(messages, TOOLS)

            if not step.tool_calls:
                # Plain assistant reply (no tool use) ends the turn.
                return CutDirectorResult(step.content, last_plan)

            messages.append({
                "role": "assistant",
                "content": step.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in step.tool_calls
                ],
            })

            finalize = False
            for tc in step.tool_calls:
                if tc.name == "emit_plan":
                    plan = self._build_plan(tc.arguments, request, clip_cache)
                    last_plan = plan
                    needs_target = (
                        request.target_min_s is not None
                        and request.target_max_s is not None
                    )
                    if plan.within_target or reprompted or not needs_target:
                        finalize = True
                        result = "Plan accepted."
                    else:
                        # One deterministic re-prompt to nudge the duration in.
                        reprompted = True
                        result = self._duration_feedback(plan)
                    self._append_tool_result(messages, tc.id, result)
                elif tc.name == "search_footage":
                    searches += 1
                    text, count = self._do_search(tc.arguments)
                    clips_seen = max(clips_seen, count)
                    self._append_tool_result(messages, tc.id, text)
                elif tc.name == "get_clip_detail":
                    self._append_tool_result(
                        messages, tc.id, self._do_detail(tc.arguments, clip_cache),
                    )
                elif tc.name == "inspect_broll":
                    text, used = self._do_inspect(tc.arguments, vision_used)
                    vision_used = used
                    self._append_tool_result(messages, tc.id, text)
                else:
                    self._append_tool_result(messages, tc.id, f"Unknown tool: {tc.name}")

            if finalize:
                text = step.content or "已生成初剪分镜表。"
                return CutDirectorResult(text, last_plan)

            # Convergence push: once we're past the halfway point without a plan,
            # force the model to commit to emit_plan (flaky local tool-callers
            # otherwise keep exploring until the round cap).
            if not nudged and round_i + 1 >= self._max_tool_rounds // 2:
                nudged = True
                messages.append({
                    "role": "system",
                    "content": (
                        "你已检索足够。现在**必须**调用 emit_plan 给出最终分镜表，"
                        "用目前掌握的素材尽力而为，不要再检索。"
                        if clips_seen > 0
                        else "多次检索未找到素材。请直接用文字回复用户：该日期范围内没有"
                        "已编目的素材，提示其确认素材已扫描入库或调整日期范围。"
                    ),
                })

        # Round cap hit — finalize with the best plan we have + a diagnostic note.
        if last_plan is not None:
            note = "（已返回当前分镜草稿。）"
        elif searches > 0 and clips_seen == 0:
            note = (
                "没有在该日期范围找到已编目的素材。请确认素材已扫描入库，"
                "或调整日期范围后重试。"
            )
        else:
            note = (
                "尝试多次仍未能生成分镜表（本地模型的工具调用可能不稳定）。"
                "请重试，或把需求说得更具体一些。"
            )
        return CutDirectorResult(note, last_plan)

    # ── tool dispatch ────────────────────────────────────────────

    def _do_search(self, args: dict[str, Any]) -> tuple[str, int]:
        briefs = self._retriever.search_footage(
            date_from=args.get("date_from"),
            date_to=args.get("date_to"),
            roll=args.get("roll"),
            tags=args.get("tags"),
            query=args.get("query"),
        )
        payload = json.dumps([b.model_dump() for b in briefs], ensure_ascii=False)
        if not briefs:
            # Steer the model away from repeating the same empty search.
            payload += (
                "  // 无结果：不要重复相同筛选；放宽日期/类型，"
                "或若确无素材则直接用文字告知用户先扫描入库。"
            )
        return payload, len(briefs)

    def _do_detail(self, args: dict[str, Any], cache: dict[int, ClipDetail]) -> str:
        cid = _as_int(args.get("clip_id"))
        if cid is None:
            return "Error: clip_id is required."
        detail = self._fetch_detail(cid, cache)
        if detail is None:
            return f"Error: clip {cid} not found."
        return json.dumps(detail.model_dump(), ensure_ascii=False)

    def _do_inspect(self, args: dict[str, Any], vision_used: int) -> tuple[str, int]:
        if self._inspector is None:
            return ("inspect_broll is unavailable.", vision_used)
        if self._vision_budget and vision_used >= self._vision_budget:
            return (
                f"Vision budget exhausted ({self._vision_budget}); rely on text metadata.",
                vision_used,
            )
        cid = _as_int(args.get("clip_id"))
        if cid is None:
            return ("Error: clip_id is required.", vision_used)
        result = self._inspector.inspect_broll(cid)
        if result is None:
            return (f"Error: could not inspect clip {cid}.", vision_used)
        return (json.dumps(result.model_dump(), ensure_ascii=False), vision_used + 1)

    def _fetch_detail(self, cid: int, cache: dict[int, ClipDetail]) -> ClipDetail | None:
        if cid not in cache:
            detail = self._retriever.get_clip_detail(cid)
            if detail is None:
                return None
            cache[cid] = detail
        return cache[cid]

    # ── plan building (deterministic) ────────────────────────────

    def _build_plan(
        self,
        args: dict[str, Any],
        request: RoughCutRequest,
        cache: dict[int, ClipDetail],
    ) -> CutPlan:
        raw_shots = args.get("shots")
        shots: list[Shot] = []
        chapters: list[str] = []
        total = 0.0
        for item in raw_shots or []:
            if not isinstance(item, dict):
                continue
            cid = _as_int(item.get("clip_id"))
            if cid is None:
                continue
            in_s = _as_float(item.get("in_s"), 0.0)
            out_s = _as_float(item.get("out_s"), 0.0)
            detail = self._fetch_detail(cid, cache)
            # Clamp in/out to the real clip duration so the model can't invent
            # timecodes past the end of the footage.
            if detail is not None and detail.duration_s:
                in_s = max(0.0, min(in_s, detail.duration_s))
                out_s = max(in_s, min(out_s, detail.duration_s))
            else:
                out_s = max(in_s, out_s)
            chapter = str(item.get("chapter") or "")
            if chapter and chapter not in chapters:
                chapters.append(chapter)
            shots.append(Shot(
                clip_id=cid,
                roll=str(item.get("roll") or (detail.roll if detail else "a")),
                in_s=in_s,
                out_s=out_s,
                content=str(item.get("content") or ""),
                rationale=str(item.get("rationale") or ""),
                chapter=chapter,
                clip_label=_clip_label(detail),
                thumb_ref=f"/api/clips/{cid}/thumbnail",
            ))
            total += max(0.0, out_s - in_s)

        within = True
        note = str(args.get("note") or "")
        if request.target_min_s is not None and request.target_max_s is not None:
            within = request.target_min_s <= total <= request.target_max_s

        return CutPlan(
            shots=shots,
            chapters=chapters,
            total_s=round(total, 3),
            target_min_s=request.target_min_s,
            target_max_s=request.target_max_s,
            within_target=within,
            note=note,
        )

    @staticmethod
    def _duration_feedback(plan: CutPlan) -> str:
        lo = plan.target_min_s or 0
        hi = plan.target_max_s or 0
        verb = "over" if plan.total_s > hi else "under"
        return (
            f"Current total is {plan.total_s:.0f}s, which is {verb} the target "
            f"{lo:.0f}-{hi:.0f}s. Adjust the shot selection (add/trim) and call "
            f"emit_plan again."
        )

    @staticmethod
    def _append_tool_result(messages: list[dict[str, Any]], call_id: str, content: str) -> None:
        messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    @staticmethod
    def _system_prompt(request: RoughCutRequest) -> str:
        target = ""
        if request.target_min_s is not None and request.target_max_s is not None:
            target = f"目标时长 {request.target_min_s/60:.0f}–{request.target_max_s/60:.0f} 分钟。"
        date_range = ""
        if request.date_from or request.date_to:
            date_range = f"素材日期范围 {request.date_from or '不限'} 到 {request.date_to or '不限'}。"
        return (
            "你是专业的视频初剪导演。基于已编目的素材库，为用户生成一份精确到片段内 in/out 的"
            "文字分镜表，供其照搬到剪辑软件。\n"
            "结构：以 A-roll（有解说）的句子作为叙事主线，再为每段配合适的 B-roll 空镜插空。\n"
            "工具：search_footage 检索素材，get_clip_detail 取 transcript 分段与关键帧切点（A-roll 的"
            " in/out 应落在 segment 边界上），inspect_broll 仅在文本元数据不足时现场看 B-roll 画面（尽量少用、"
            "可批量），最后用 emit_plan 给出最终分镜表。\n"
            "不要自己计算总时长，系统会校验。只使用素材库里真实存在的 clip。\n"
            f"画面比例 {request.aspect_ratio}。{target}{date_range}\n"
            f"风格/节奏：{request.style_notes or '（用户未指定，自行把握）'}"
        )


# ── small parse helpers ──────────────────────────────────────────

def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip_label(detail: ClipDetail | None) -> str:
    if detail is None:
        return ""
    path = detail.library_path or detail.source_path
    return Path(path).name if path else ""
