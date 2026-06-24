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
import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

from ..domain.models import (
    ChatMessage,
    ClipDetail,
    CutPlan,
    RoughCutRequest,
    Shot,
)
from ..ports.cutplan import BrollInspector, FootageRetriever, LLMAgentClient

logger = logging.getLogger(__name__)

# Built-in default director prompt for the staged generator. Editable in the UI
# (persisted to ~/.cutfinder/config.json); the "重置" button restores this text.
# Placeholders {aspect}/{target}/{style} are substituted per request — keep them
# if you want the画面比例/目标时长/风格 to appear in the prompt.
DEFAULT_CUT_DIRECTOR_PROMPT = (
    "你是专业的视频初剪导演。基于下面给出的已编目素材，生成一份精确到片段内 in/out 的"
    "分镜表，供用户照搬到剪辑软件。\n"
    "按【拍摄日期】分章：每个拍摄日期作为一个章节，chapter 字段直接填该日期（ISO 格式，"
    "如 2026-04-25）；把同一天的素材组织成一段叙事，章节按日期先后排列。\n"
    "在每一天内：严格按每条素材给出的【拍摄时间】时间戳先后顺序组织，还原当天真实的行程"
    "时间线——先发生的先出现（例如先到关帝庙、再去 Market City、最后吃饭，就按这个顺序排）。"
    "素材清单已按拍摄时间排好，请保持这个顺序，不要打乱。\n"
    "以 A-roll（有解说）的句子作为叙事主线，A-roll 选段以 transcript（台词内容）为主要依据，"
    "in/out 落在给出的 segment 时间边界上，不要依赖任何已有的关键帧切点；每段 A-roll 后紧跟"
    "与之同一场景/时间的 B-roll 空镜。\n"
    "B-roll 在其时长内取一个合适窗口。\n"
    "只能使用素材清单里出现的 clip_id，不要编造。让总时长尽量贴近目标。\n"
    "你**不必用上所有素材**：按叙事主线和目标时长**主动取舍**，剔除重复、冗余、空泛或废镜；"
    "同一场景的相似 B-roll、连拍/雷同照片**只选最好的 1–2 个**。宁缺毋滥，列出的每个镜头都要有存在理由。\n"
    "画面比例 {aspect}。{target}风格/节奏：{style}"
)

# Critic (task 28 Part B): a single review pass over the already-assembled plan.
# It judges only *subjective* quality (rhythm, narrative flow, A/B-roll balance);
# the duration check stays deterministic in Python. It names shooting dates to
# redo, which the director re-runs through the same per-day merge mechanism.
CRITIC_SYSTEM_PROMPT = (
    "你是资深视频剪辑指导，负责审片。只评判主观质量：节奏松紧、叙事是否连贯、"
    "A-roll 解说主线与 B-roll 空镜的配比、空镜衔接是否缺位。"
    "点名需要调整的【拍摄日期】并给出可执行建议；不要改时长（系统会另行校验）。"
    "只指出最关键的几处。"
)

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

# Tools a per-day worker may call (task 26). It does **not** get search_footage:
# the day's clips are already retrieved deterministically and fed in the prompt,
# so the worker's value-add is deep-diving transcript (get_clip_detail), looking
# at B-roll frames (inspect_broll), and finalizing (emit_plan) — not re-searching.
DAY_TOOLS: list[dict[str, Any]] = [
    t for t in TOOLS if t["function"]["name"] in ("get_clip_detail", "inspect_broll", "emit_plan")
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
        mode: str = "agent",
        max_tool_rounds: int = 24,
        vision_budget: int = 6,
        critic_enabled: bool = False,
        lean_char_budget: int = 80000,
        staged_char_budget: int = 60000,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._inspector = inspector
        self._mode = mode
        self._max_tool_rounds = max(1, max_tool_rounds)
        self._vision_budget = max(0, vision_budget)
        self._critic_enabled = critic_enabled
        self._lean_char_budget = lean_char_budget
        self._staged_char_budget = staged_char_budget

    # ── staged generation (primary path; reliable on local models) ──

    def generate(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        *,
        prior_plan: CutPlan | None = None,
        on_progress: Callable[[str], None] | None = None,
        on_partial: Callable[[CutPlan], None] | None = None,
    ) -> CutDirectorResult:
        """Deterministic retrieval + one LLM call **per shooting date** → shot list.

        A single call for a whole multi-day 15–20 min plan overwhelms local
        models (they run away generating tens of thousands of tokens and never
        return parseable JSON). Generating one focused shot list per shooting
        date keeps each completion small and reliable, and is exactly the
        date-chaptered structure the UI wants.

        *on_progress* receives a human-readable status string as each day /
        clip is worked; *on_partial* receives the cumulative plan after each day
        finishes (so the UI can show completed dates while the rest generate).
        """
        from collections import defaultdict

        progress = on_progress or (lambda _s: None)
        partial = on_partial or (lambda _p: None)

        progress("正在检索素材…")
        clips = self._retriever.search_footage(
            date_from=request.date_from, date_to=request.date_to,
        )
        if not clips:
            return CutDirectorResult(
                "没有在该日期范围找到已编目的素材。请确认素材已扫描入库，或调整日期范围。",
                None,
            )

        groups: dict[str, list[Any]] = defaultdict(list)
        for b in clips:
            day = (getattr(b, "capture_time", None) or "")[:10] or "无日期"
            groups[day].append(b)
        # Sort each day's clips by capture time so the context — and therefore the
        # shot order the model produces — follows the real shooting timeline.
        for day_clips in groups.values():
            day_clips.sort(key=lambda b: (getattr(b, "capture_time", None) or ""))
        dates = sorted(groups)
        progress(f"找到 {len(clips)} 个片段、共 {len(dates)} 天，开始生成…")

        cache: dict[int, ClipDetail] = {}
        per_day = self._per_day_target(request, len(dates))
        vision_used = 0  # inspect_broll budget shared across all days this turn

        # A plan is a dict keyed by chapter (= shooting date). Seed it from any
        # prior plan so a refine turn that regenerates only the dates in its
        # (possibly narrowed) range **merges** them over the existing timeline
        # instead of replacing the whole thing (task 28 Part A). flatten() then
        # re-orders by date so the merged plan stays a clean timeline.
        merged: dict[str, list[dict[str, Any]]] = {}
        if prior_plan is not None:
            for shot in prior_plan.shots:
                key = shot.chapter or shot.clip_date or "无日期"
                merged.setdefault(key, []).append(self._shot_to_dict(shot))

        notes: list[str] = []
        failed: list[str] = []
        n_days = len(dates)
        for idx, day in enumerate(dates, 1):
            progress(f"正在生成第 {idx}/{n_days} 天（{day}）· 本天 {len(groups[day])} 个片段")

            def day_step(detail: str, _i: int = idx, _d: str = day) -> None:
                progress(f"第 {_i}/{n_days} 天（{_d}）· {detail}")

            def on_fallback(n: int = 0, _i: int = idx, _d: str = day) -> None:
                extra = f"（带入 {n} 条已勘察画面）" if n else ""
                progress(f"第 {_i}/{n_days} 天（{_d}）· 改用快速生成{extra}…")

            day_shots, day_note, vision_used = self._gen_one_day(
                request, history, user_text, day, groups[day], per_day, cache, vision_used,
                on_step=day_step, on_fallback=on_fallback,
            )
            day_dicts = self._normalize_day(day_shots, day)
            if not day_dicts:
                # No fresh shots this turn. Keep the prior version of the day if we
                # have one — refine must not drop unrelated dates; only report a
                # date as "skipped" when there was nothing to fall back on.
                if day not in merged:
                    logger.warning(
                        "cutplan: date %s produced no valid shots (%d clips)",
                        day, len(groups[day]),
                    )
                    failed.append(day)
                continue
            merged[day] = day_dicts  # success → overwrite just this day
            if day_note:
                notes.append(day_note)
            # Surface completed dates immediately: emit the cumulative plan so the
            # UI can render finished days while the remaining ones generate.
            total_shots = sum(len(v) for v in merged.values())
            progress(f"第 {idx}/{n_days} 天（{day}）完成 · 已选 {total_shots} 个镜头")
            partial(self._build_plan(
                {"shots": self._flatten(merged), "note": " ".join(notes)}, request, cache,
            ))

        if not self._flatten(merged):
            return CutDirectorResult(
                "生成分镜表失败（模型未返回有效结果），请重试或把需求说得更具体。", None,
            )

        # Part B (task 28): an optional one-round critic over the assembled plan,
        # re-doing the dates it flags through the same per-day merge mechanism.
        if self._critic_enabled:
            vision_used = self._apply_critic(
                request, history, user_text, merged, groups, per_day, cache,
                vision_used, notes, progress, partial,
            )

        plan = self._build_plan(
            {"shots": self._flatten(merged), "note": " ".join(notes)}, request, cache,
        )
        if not plan.shots:
            return CutDirectorResult("模型没有选出可用片段，请重试或调整需求。", None)
        text = "已生成初剪分镜表。"
        if failed:
            text += f"（{('、').join(failed)} 这些日期未能生成，已跳过。）"
        return CutDirectorResult(text, plan)

    # ── per-day generation + merge helpers (task 26/28) ──────────────

    def _gen_one_day(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        day: str,
        clips: list[Any],
        per_day: tuple[float, float] | None,
        cache: dict[int, ClipDetail],
        vision_used: int,
        *,
        on_step: Callable[[str], None] | None = None,
        on_fallback: Callable[[int], None] | None = None,
    ) -> tuple[list[dict[str, Any]] | None, str, int]:
        """Generate one day's shots → (shots, note, vision_used).

        In agent mode runs the scoped tool loop (:meth:`_run_day`) over a **lean**
        catalog (no inlined transcripts — the agent fetches台词 via the tool) and
        falls back to one structured-JSON call (:meth:`_staged_day`) over the
        **full** catalog when it doesn't converge; *on_fallback* fires on fall back.
        """
        day_shots: list[dict[str, Any]] | None = None
        day_note = ""
        findings: dict[int, str] = {}  # inspect_broll descriptions gathered by the agent
        if self._mode == "agent":
            lean = self._build_context(
                clips, cache, self._lean_char_budget, include_transcripts=False,
            )
            day_shots, day_note, vision_used, findings = self._run_day(
                request, history, user_text, day, lean, per_day, cache, vision_used,
                on_step=on_step,
            )
        if day_shots is None:
            if self._mode == "agent" and on_fallback is not None:
                on_fallback(len(findings))
            full = self._build_context(
                clips, cache, self._staged_char_budget, include_transcripts=True,
            )
            # Reuse the agent's gathered B-roll vision findings so the spent
            # vision budget isn't wasted when we fall back to staged.
            day_shots, day_note = self._staged_day(
                request, history, user_text, day, full, per_day, findings=findings,
            )
        return day_shots, day_note, vision_used

    @staticmethod
    def _normalize_day(
        day_shots: list[dict[str, Any]] | None, day: str,
    ) -> list[dict[str, Any]]:
        """Keep the dict shots for *day*, forcing chapter to the shooting date."""
        out: list[dict[str, Any]] = []
        for item in day_shots or []:
            if isinstance(item, dict):
                item["chapter"] = day
                out.append(item)
        return out

    @staticmethod
    def _salvage_plan(content: str | None) -> list[dict[str, Any]] | None:
        """Recover a shot list from a prose reply that embeds plan JSON, else None.

        Lets the agent loop accept a day when the model "answered directly" with
        a ``{"shots": [...]}`` body instead of wrapping it in an emit_plan call.
        """
        from ..adapters._jsonparse import parse_json_object

        data = parse_json_object(content) if content else None
        if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
            return None
        shots = [s for s in data["shots"] if isinstance(s, dict)]
        return shots or None

    @staticmethod
    def _flatten(merged: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Concatenate per-date shot dicts in shooting-date order."""
        out: list[dict[str, Any]] = []
        for day in sorted(merged):
            out.extend(merged[day])
        return out

    @staticmethod
    def _shot_to_dict(shot: Shot) -> dict[str, Any]:
        """Turn a stored Shot back into the dict shape :meth:`_build_plan` reads."""
        return {
            "clip_id": shot.clip_id,
            "roll": shot.roll,
            "in_s": shot.in_s,
            "out_s": shot.out_s,
            "content": shot.content,
            "rationale": shot.rationale,
            "chapter": shot.chapter,
        }

    # ── critic pass (task 28 Part B) ─────────────────────────────────

    def _apply_critic(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        merged: dict[str, list[dict[str, Any]]],
        groups: dict[str, list[Any]],
        per_day: tuple[float, float] | None,
        cache: dict[int, ClipDetail],
        vision_used: int,
        notes: list[str],
        progress: Callable[[str], None],
        partial: Callable[[CutPlan], None],
    ) -> int:
        """One critic round: re-do the dates it flags, merged in place.

        Best-effort — a missing / unparseable critic reply, or a date with no
        footage, leaves the plan untouched. Returns the updated vision budget.
        """
        progress("正在审片…")
        for rev in self._critique(merged):
            day = str(rev.get("date") or "")
            # Only act on dates we still have footage (and a chapter) for.
            if day not in merged or day not in groups:
                continue
            progress(f"按审片意见重做 {day}…")
            issue = str(rev.get("issue") or "")
            action = str(rev.get("action") or "")
            crit_text = f"{user_text}\n\n[审片意见] {day}：{issue} → {action}"
            day_shots, day_note, vision_used = self._gen_one_day(
                request, history, crit_text, day, groups[day], per_day, cache, vision_used,
            )
            day_dicts = self._normalize_day(day_shots, day)
            if not day_dicts:
                continue  # redo failed → keep the original day
            merged[day] = day_dicts
            if day_note:
                notes.append(day_note)
            partial(self._build_plan(
                {"shots": self._flatten(merged), "note": " ".join(notes)}, request, cache,
            ))
        return vision_used

    def _critique(
        self, merged: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Ask the text model to flag subjective issues by shooting date."""
        from ..adapters._jsonparse import parse_json_object

        messages = [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": self._plan_digest(merged)},
        ]
        raw = self._llm.complete(messages)
        data = parse_json_object(raw) if raw else None
        if not isinstance(data, dict):
            return []
        revisions = data.get("revisions")
        if not isinstance(revisions, list):
            return []
        return [r for r in revisions if isinstance(r, dict) and r.get("date")]

    @staticmethod
    def _plan_digest(merged: dict[str, list[dict[str, Any]]]) -> str:
        """Compact per-date shot summary the critic reviews (no timecodes math)."""
        lines = ["以下是已拼好的初剪分镜表（按拍摄日期分章）："]
        for day in sorted(merged):
            lines.append(f"【{day}】")
            for i, s in enumerate(merged[day], 1):
                dur = _as_float(s.get("out_s"), 0.0) - _as_float(s.get("in_s"), 0.0)
                roll = str(s.get("roll") or "")
                content = str(s.get("content") or "").replace("\n", " ")[:40]
                lines.append(f"  {i}. {roll}-roll {dur:.0f}s {content}")
        lines.append(
            "\n请审阅主观质量（节奏松紧、叙事是否连贯、A-roll 主线与 B-roll 空镜配比、"
            "空镜是否缺位），只输出 JSON："
            '{"revisions": [{"date": "YYYY-MM-DD", "issue": "问题", "action": "可执行的修改建议"}]}。'
            "整体良好则 revisions 用空数组。"
        )
        return "\n".join(lines)

    def _day_messages(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        day: str,
        context: str,
        per_day: tuple[float, float] | None,
        *,
        agent: bool,
    ) -> list[dict[str, Any]]:
        """Build the message list for one day (system + history + day prompt)."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._staged_system_prompt(request)},
        ]
        for m in history:
            if m.role in ("user", "assistant") and m.content:
                messages.append({"role": m.role, "content": m.content})
        messages.append({
            "role": "user",
            "content": self._day_user_prompt(user_text, day, context, per_day, agent=agent),
        })
        return messages

    def _staged_day(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        day: str,
        context: str,
        per_day: tuple[float, float] | None,
        findings: dict[int, str] | None = None,
    ) -> tuple[list[dict[str, Any]] | None, str]:
        """One structured-JSON completion for a day → (shots, note) or (None, "").

        *findings* (clip_id → B-roll vision description) carries over the agent's
        on-the-spot ``inspect_broll`` look-ups when this runs as a fallback, so
        the staged model judges those B-roll clips from the fresh描述 rather than
        only their stored tags.
        """
        from ..adapters._jsonparse import parse_json_object

        messages = self._day_messages(
            request, history, user_text, day, context, per_day, agent=False,
        )
        if findings:
            block = "\n".join(f"[{cid}] {desc}" for cid, desc in findings.items())
            messages.append({
                "role": "system",
                "content": (
                    "导演已现场勘察过以下 B-roll 画面，请优先据此判断其用途（而非仅凭标签）：\n"
                    + block
                ),
            })
        raw = self._llm.complete(messages)
        data = parse_json_object(raw) if raw else None
        if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
            return None, ""
        shots = [s for s in data["shots"] if isinstance(s, dict)]
        return shots, str(data.get("note") or "")

    def _run_day(
        self,
        request: RoughCutRequest,
        history: list[ChatMessage],
        user_text: str,
        day: str,
        context: str,
        per_day: tuple[float, float] | None,
        cache: dict[int, ClipDetail],
        vision_used: int,
        *,
        on_step: Callable[[str], None] | None = None,
    ) -> tuple[list[dict[str, Any]] | None, str, int, dict[int, str]]:
        """Scoped tool loop for one day → (shots, note, vision_used, findings).

        Returns shots ``None`` when the model doesn't converge to emit_plan
        within the round cap (or replies in prose); the caller then falls back
        to :meth:`_staged_day` for this day. *findings* maps clip_id → the
        ``inspect_broll`` vision description the agent gathered (it cost vision
        budget and isn't persisted), so a fallback can reuse that work instead
        of discarding it.

        *on_step* (if given) receives a short status string each time the worker
        looks at a clip, so the UI can show what it is doing right now.
        """
        step_cb = on_step or (lambda _s: None)
        findings: dict[int, str] = {}  # clip_id → inspect_broll description (for fallback reuse)
        messages = self._day_messages(
            request, history, user_text, day, context, per_day, agent=True,
        )
        nudged = False
        prose_nudged = False  # whether we've already pushed back on a prose reply
        seen: set[tuple[str, str]] = set()  # (tool, args) already executed this day
        for round_i in range(self._max_tool_rounds):
            step = self._llm.run(messages, DAY_TOOLS)
            if not step.tool_calls:
                # Model replied in prose instead of calling a tool. Don't bail on
                # the first one (that's why busy days never used tools): (1) if
                # the prose already carries a usable shot list — the model just
                # "answered directly" — take it; (2) otherwise nudge it once to
                # use the tools and retry; only then fall back to staged.
                salvaged = self._salvage_plan(step.content)
                if salvaged is not None:
                    step_cb("导演直接给出文字分镜，已采纳")
                    return salvaged, "", vision_used, findings
                # Surface the prose so these no-tool rounds aren't invisible —
                # otherwise it looks like the agent bailed right after the first
                # clip, when really it replied in text (here's what it said).
                reply = (step.content or "").strip().replace("\n", " ") or "（空回复）"
                step_cb(f"导演未用工具、直接回了文字：{reply[:60]}")
                if prose_nudged:
                    return None, "", vision_used, findings
                prose_nudged = True
                messages.append({"role": "assistant", "content": step.content})
                messages.append({
                    "role": "system",
                    "content": (
                        "不要用纯文字回复。请**用工具**推进：用 get_clip_detail(clip_id) "
                        "查看标了 [有台词] 的 A-roll 片段台词，或直接调用 emit_plan 工具"
                        "提交这一天的分镜表（shots 放在工具参数里）。"
                    ),
                })
                continue

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

            # Surface the model's own reasoning between tool calls ("what it's
            # thinking"), trimmed — only when it actually wrote something.
            reasoning = (step.content or "").strip().replace("\n", " ")
            if reasoning:
                step_cb(f"导演思路：{reasoning[:50]}")

            emitted: list[dict[str, Any]] | None = None
            note = ""
            for tc in step.tool_calls:
                if tc.name == "emit_plan":
                    raw_shots = tc.arguments.get("shots")
                    emitted = [s for s in raw_shots if isinstance(s, dict)] if isinstance(raw_shots, list) else []
                    note = str(tc.arguments.get("note") or "")
                    self._append_tool_result(messages, tc.id, "Plan accepted.")
                    continue
                # Dedup guard: a hallucinating model can repeat the same call;
                # short-circuit identical (tool, args) so it can't burn the round
                # budget / vision budget re-fetching what it already has.
                key = (tc.name, json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False))
                if key in seen:
                    self._append_tool_result(
                        messages, tc.id,
                        "（你已用相同参数调用过该工具，结果同上；请改用已有信息，或直接调用 emit_plan。）",
                    )
                    continue
                seen.add(key)
                if tc.name == "get_clip_detail":
                    step_cb(f"查看片段 {self._label(_as_int(tc.arguments.get('clip_id')), cache)} 的台词")
                    self._append_tool_result(
                        messages, tc.id, self._do_detail(tc.arguments, cache),
                    )
                elif tc.name == "inspect_broll":
                    step_cb(f"查看片段 {self._label(_as_int(tc.arguments.get('clip_id')), cache)} 的画面")
                    text, used = self._do_inspect(tc.arguments, vision_used)
                    # vision_used only increments on a real look (not an error/
                    # budget-exhausted string) — use that as the success signal to
                    # record the description for a possible staged fallback.
                    cid = _as_int(tc.arguments.get("clip_id"))
                    if used > vision_used and cid is not None:
                        findings[cid] = text
                    vision_used = used
                    self._append_tool_result(messages, tc.id, text)
                else:
                    self._append_tool_result(messages, tc.id, f"Unknown tool: {tc.name}")

            if emitted is not None:
                return emitted, note, vision_used, findings

            # Past the halfway point without a plan → push the model to commit
            # (local tool-callers otherwise keep exploring until the round cap).
            if not nudged and round_i + 1 >= self._max_tool_rounds // 2:
                nudged = True
                messages.append({
                    "role": "system",
                    "content": "你已了解足够。现在**必须**调用 emit_plan 给出这一天的最终分镜表，不要再查看素材。",
                })

        return None, "", vision_used, findings

    @staticmethod
    def _per_day_target(
        request: RoughCutRequest, n_days: int,
    ) -> tuple[float, float] | None:
        """Split the overall target duration evenly across shooting dates."""
        if request.target_min_s is None or request.target_max_s is None or n_days <= 0:
            return None
        return request.target_min_s / n_days, request.target_max_s / n_days

    @staticmethod
    def _day_user_prompt(
        user_text: str, day: str, context: str, per_day: tuple[float, float] | None,
        *, agent: bool = False,
    ) -> str:
        budget = ""
        if per_day is not None:
            budget = f"\n这一天的目标时长约 {per_day[0]/60:.1f}–{per_day[1]/60:.1f} 分钟。"
        head = (
            f"{user_text}\n\n本次只为【{day}】这一天生成分镜，chapter 一律填 \"{day}\"。{budget}\n\n"
            f"该日期可用素材（只能用下列 clip_id）：\n{context}\n\n"
        )
        if agent:
            return head + (
                "上面清单里 A-roll 只给了摘要，标 [有台词] 的片段**完整台词分段要用 "
                "get_clip_detail(clip_id) 获取**，再据此把 in/out 落在 segment 边界上。"
                "请**只通过工具推进**：用 get_clip_detail 读取你想用的 A-roll 台词、"
                "必要时用 inspect_broll 现场看 B-roll 画面（尽量少用），"
                "**最后必须调用 emit_plan 工具**给出这一天的最终分镜表，不要用纯文字回答。"
            )
        return head + (
            "请只输出 JSON，格式：\n"
            '{"note": "可选备注", "shots": [{"clip_id": 整数, "roll": "a"或"b", '
            '"in_s": 数字, "out_s": 数字, "content": "台词或画面", "rationale": "用途理由"}]}'
        )

    def _build_context(
        self, clips: list[Any], cache: dict[int, ClipDetail], char_budget: int = 12000,
        *, include_transcripts: bool = True,
    ) -> str:
        """Compact text catalog of candidate clips.

        *include_transcripts* — when True (staged mode) each A-roll clip's timed
        transcript segments are inlined, since the staged path has no tools to
        fetch them. In **agent** mode it's False: the catalog stays lean (one
        line per clip, plus an `[有台词]` marker) so all clips fit even on a busy
        day, and the agent reads台词 on demand via ``get_clip_detail`` — a huge
        truncated prompt was the reason it bailed to prose on big days.
        """
        lines: list[str] = []
        used = 0
        for b in clips:
            dur = f"{b.duration_s:.0f}s" if b.duration_s else "?"
            desc = (b.summary or b.description or "").strip().replace("\n", " ")[:120]
            tags = ",".join(b.tags[:6]) if b.tags else ""
            # Full timestamp (date + time of day) so the model can order shots by
            # the real shooting timeline within a day.
            when = (b.capture_time or "").replace("T", " ")[:19] or "无拍摄时间"
            mark = " [有台词]" if (b.roll == "a" and b.has_transcript) else ""
            head = f"[{b.clip_id}] {when} {b.roll}-roll dur={dur}{mark} {desc} tags={tags}"
            lines.append(head)
            used += len(head)
            if include_transcripts and b.roll == "a" and b.has_transcript:
                detail = self._fetch_detail(b.clip_id, cache)
                if detail is not None:
                    for s in detail.segments[:60]:
                        seg = f"   ({s.start_s:.1f}-{s.end_s:.1f}) {s.text}"
                        lines.append(seg)
                        used += len(seg)
            if used > char_budget:
                lines.append("   …(更多素材已省略)")
                break
        return "\n".join(lines)

    @staticmethod
    def _staged_system_prompt(request: RoughCutRequest) -> str:
        from ..config import load_cut_director_prompt

        template = load_cut_director_prompt() or DEFAULT_CUT_DIRECTOR_PROMPT
        target = ""
        if request.target_min_s is not None and request.target_max_s is not None:
            target = f"目标时长 {request.target_min_s/60:.0f}–{request.target_max_s/60:.0f} 分钟。"
        # Plain replace (not str.format) so stray braces in a custom prompt can't
        # raise; unknown placeholders are simply left as-is.
        return (
            template
            .replace("{aspect}", request.aspect_ratio)
            .replace("{target}", target)
            .replace("{style}", request.style_notes or "（自行把握）")
        )

    # ── public entry (autonomous tool loop; advanced/experimental) ──

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

    def _label(self, cid: int | None, cache: dict[int, ClipDetail]) -> str:
        """Human-friendly clip label (file name) for progress text; falls back to #id."""
        if cid is None:
            return "#?"
        return _clip_label(self._fetch_detail(cid, cache)) or f"#{cid}"

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
                clip_date=(detail.capture_time or "")[:10] if detail else "",
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
            "A-roll 选段以 transcript（台词内容）为主要依据，in/out 落在 segment 边界上，不要依赖已有关键帧切点。\n"
            "工具：search_footage 检索素材，get_clip_detail 取 transcript 分段（A-roll 的"
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
