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
from .prompts import (
    CRITIC_SYSTEM_PROMPT_EN,
    CRITIC_SYSTEM_PROMPT_ZH,
    DAY_TOOLS,
    DEFAULT_CUT_DIRECTOR_PROMPT_EN,
    DEFAULT_CUT_DIRECTOR_PROMPT_ZH,
    TOOLS,
    message,
)

logger = logging.getLogger(__name__)

# Chars-per-token used only when the server can't count tokens (e.g. offline):
# a conservative estimate for this mixed Chinese-prose + ASCII-metadata catalog,
# so the token budget still maps to a sane character cap as a fallback.
_FALLBACK_CHARS_PER_TOKEN = 1.8


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
        lean_token_budget: int = 50000,
        staged_token_budget: int = 40000,
        ui_language: str = "zh",
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._inspector = inspector
        self._mode = mode
        self._max_tool_rounds = max(1, max_tool_rounds)
        self._vision_budget = max(0, vision_budget)
        self._critic_enabled = critic_enabled
        self._lean_token_budget = lean_token_budget
        self._staged_token_budget = staged_token_budget
        self._ui_language = ui_language

    def _t(self, key: str, **kw: Any) -> str:
        """Look up a bilingual message for the current UI language."""
        return message(key, self._ui_language, **kw)

    def _default_prompt(self) -> str:
        """Return the default director prompt matching *ui_language*."""
        return (DEFAULT_CUT_DIRECTOR_PROMPT_EN if self._ui_language == "en"
                else DEFAULT_CUT_DIRECTOR_PROMPT_ZH)

    def _critic_system_prompt(self) -> str:
        """Return the critic system prompt matching *ui_language*."""
        return (CRITIC_SYSTEM_PROMPT_EN if self._ui_language == "en"
                else CRITIC_SYSTEM_PROMPT_ZH)

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
        lang = self._ui_language

        progress(self._t("searching_footage"))
        clips = self._retriever.search_footage(
            date_from=request.date_from, date_to=request.date_to,
        )
        if not clips:
            return CutDirectorResult(self._t("no_footage_in_range"), None)

        groups: dict[str, list[Any]] = defaultdict(list)
        no_date = self._t("no_date")
        for b in clips:
            day = (getattr(b, "capture_time", None) or "")[:10] or no_date
            groups[day].append(b)
        # Sort each day's clips by capture time so the context — and therefore the
        # shot order the model produces — follows the real shooting timeline.
        for day_clips in groups.values():
            day_clips.sort(key=lambda b: (getattr(b, "capture_time", None) or ""))
        dates = sorted(groups)
        progress(self._t("found_clips_days", n=len(clips), days=len(dates)))

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
                key = shot.chapter or shot.clip_date or no_date
                merged.setdefault(key, []).append(self._shot_to_dict(shot))

        notes: list[str] = []
        failed: list[str] = []
        n_days = len(dates)
        for idx, day in enumerate(dates, 1):
            progress(self._t("generating_day", idx=idx, n=n_days, day=day, clips=len(groups[day])))

            def day_step(detail: str, _i: int = idx, _d: str = day) -> None:
                progress(self._t("day_step", idx=_i, n=n_days, day=_d, detail=detail))

            def on_fallback(n: int = 0, _i: int = idx, _d: str = day) -> None:
                extra = self._t("inspected_carry", n=n) if n else ""
                progress(self._t("day_fallback", idx=_i, n=n_days, day=_d, extra=extra))

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
            progress(self._t("day_done", idx=idx, n=n_days, day=day, shots=total_shots))
            partial(self._build_plan(
                {"shots": self._flatten(merged), "note": " ".join(notes)}, request, cache,
            ))

        if not self._flatten(merged):
            return CutDirectorResult(self._t("generation_failed"), None)

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
            return CutDirectorResult(self._t("no_clips_selected"), None)
        text = self._t("shotlist_generated")
        if failed:
            sep = "、" if lang == "zh" else ", "
            text += self._t("dates_skipped", dates=sep.join(failed))
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
                clips, cache, self._lean_token_budget, include_transcripts=False,
            )
            day_shots, day_note, vision_used, findings = self._run_day(
                request, history, user_text, day, lean, per_day, cache, vision_used,
                on_step=on_step,
            )
        if day_shots is None:
            if self._mode == "agent" and on_fallback is not None:
                on_fallback(len(findings))
            full = self._build_context(
                clips, cache, self._staged_token_budget, include_transcripts=True,
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
        progress(self._t("reviewing_cut"))
        for rev in self._critique(merged):
            day = str(rev.get("date") or "")
            # Only act on dates we still have footage (and a chapter) for.
            if day not in merged or day not in groups:
                continue
            progress(self._t("redoing_per_critic", day=day))
            issue = str(rev.get("issue") or "")
            action = str(rev.get("action") or "")
            crit_text = self._t(
                "critic_feedback", user_text=user_text, day=day, issue=issue, action=action,
            )
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
            {"role": "system", "content": self._critic_system_prompt()},
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

    def _plan_digest(self, merged: dict[str, list[dict[str, Any]]]) -> str:
        """Compact per-date shot summary the critic reviews (no timecodes math)."""
        lines = [self._t("digest_header")]
        for day in sorted(merged):
            lines.append(self._t("digest_day", day=day))
            for i, s in enumerate(merged[day], 1):
                dur = _as_float(s.get("out_s"), 0.0) - _as_float(s.get("in_s"), 0.0)
                roll = str(s.get("roll") or "")
                content = str(s.get("content") or "").replace("\n", " ")[:40]
                lines.append(f"  {i}. {roll}-roll {dur:.0f}s {content}")
        lines.append(self._t("digest_footer"))
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
                "content": self._t("inspected_findings_header") + block,
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
                    step_cb(self._t("accepted_text_shotlist"))
                    return salvaged, "", vision_used, findings
                # Surface the prose so these no-tool rounds aren't invisible —
                # otherwise it looks like the agent bailed right after the first
                # clip, when really it replied in text (here's what it said).
                reply = (step.content or "").strip().replace("\n", " ") or "（空回复）"
                step_cb(self._t("director_replied_text", reply=reply[:60]))
                if prose_nudged:
                    return None, "", vision_used, findings
                prose_nudged = True
                messages.append({"role": "assistant", "content": step.content})
                messages.append({
                    "role": "system",
                    "content": self._t("nudge_use_tools_prose"),
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
                step_cb(self._t("director_thinking", reasoning=reasoning[:50]))

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
                    self._append_tool_result(messages, tc.id, self._t("tool_already_called"))
                    continue
                seen.add(key)
                if tc.name == "get_clip_detail":
                    _cid = _as_int(tc.arguments.get("clip_id"))
                    _d = self._fetch_detail(_cid, cache) if _cid is not None else None
                    # get_clip_detail returns transcripts for A-roll but stored visual description/cut points
                    # for B-roll (which has no transcript) — label by roll, not always "transcript".
                    _what = self._t(
                        "detail_label_transcript" if (_d is not None and _d.roll == "a")
                        else "detail_label_visual"
                    )
                    step_cb(self._t("checking_clip", label=self._label(_cid, cache), what=_what))
                    self._append_tool_result(
                        messages, tc.id, self._do_detail(tc.arguments, cache),
                    )
                elif tc.name == "inspect_broll":
                    step_cb(self._t(
                        "inspecting_clip", label=self._label(_as_int(tc.arguments.get("clip_id")), cache),
                    ))
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
                    "content": self._t("nudge_emit_now_day"),
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

    def _day_user_prompt(
        self, user_text: str, day: str, context: str, per_day: tuple[float, float] | None,
        *, agent: bool = False,
    ) -> str:
        if per_day is not None:
            budget = self._t("day_budget", lo=per_day[0] / 60, hi=per_day[1] / 60)
        else:
            budget = ""
        head = self._t("day_prompt_head", user_text=user_text, day=day, budget=budget, context=context)
        if agent:
            return head + self._t("day_prompt_agent_tail")
        return head + self._t("day_prompt_json_tail")

    def _build_context(
        self, clips: list[Any], cache: dict[int, ClipDetail], token_budget: int = 8000,
        *, include_transcripts: bool = True,
    ) -> str:
        """Compact text catalog of candidate clips, capped by real token count.


        *include_transcripts* — when True (staged mode) each A-roll clip's timed
        transcript segments are inlined, since the staged path has no tools to
        fetch them. In **agent** mode it's False: the catalog stays lean (one
        line per clip, plus an `[has transcript]` marker) so all clips fit even on a busy
        day, and the agent reads transcripts on demand via ``get_clip_detail`` — a huge

        truncated prompt was the reason it bailed to prose on big days.

        The catalog is built in full, then bounded by *token_budget*: we ask the
        server (``count_tokens``) for the catalog's exact token count — the same
        tokenizer the model serves with — and only trim when it actually exceeds
        the budget, cutting by the measured chars/token ratio. If counting is

        unavailable, fall back to a character estimate (``_FALLBACK_CHARS_PER_TOKEN``).
        """
        lines: list[str] = []
        for b in clips:
            dur = f"{b.duration_s:.0f}s" if b.duration_s else "?"
            desc = (b.summary or b.description or "").strip().replace("\n", " ")[:120]
            tags = ",".join(b.tags[:6]) if b.tags else ""
            # Full timestamp (date + time of day) so the model can order shots by
            # the real shooting timeline within a day.
            when = (b.capture_time or "").replace("T", " ")[:19] or self._t("no_capture_time")
            mark = self._t("has_transcript_mark") if (b.roll == "a" and b.has_transcript) else ""
            head = f"[{b.clip_id}] {when} {b.roll}-roll dur={dur}{mark} {desc} tags={tags}"
            lines.append(head)
            if include_transcripts and b.roll == "a" and b.has_transcript:
                detail = self._fetch_detail(b.clip_id, cache)
                if detail is not None:
                    for s in detail.segments[:60]:
                        lines.append(f"   ({s.start_s:.1f}-{s.end_s:.1f}) {s.text}")
        catalog = "\n".join(lines)

        counter = getattr(self._llm, "count_tokens", None)
        n_tok = counter(catalog) if counter is not None else None
        if n_tok is not None and n_tok <= token_budget:
            return catalog
        # Over budget (or counting unavailable) → trim by a chars/token ratio:
        # the real measured one when we have a count, else a conservative default.
        ratio = (len(catalog) / n_tok) if n_tok else _FALLBACK_CHARS_PER_TOKEN
        char_cap = int(token_budget * ratio)
        if len(catalog) <= char_cap:
            return catalog
        kept: list[str] = []
        used = 0
        for line in lines:
            if used > char_cap:
                kept.append("   …(更多素材已省略)")
                break
            kept.append(line)
            used += len(line)
        return "\n".join(kept)

    def _staged_system_prompt(self, request: RoughCutRequest) -> str:
        from ..config import load_cut_director_prompt

        template = load_cut_director_prompt() or self._default_prompt()
        if request.target_min_s is not None and request.target_max_s is not None:
            target = self._t("target_duration", lo=request.target_min_s / 60, hi=request.target_max_s / 60)
        else:
            target = ""
        style_fallback = self._t("style_fallback")
        # Plain replace (not str.format) so stray braces in a custom prompt can't
        # raise; unknown placeholders are simply left as-is.
        return (
            template
            .replace("{aspect}", request.aspect_ratio)
            .replace("{target}", target)
            .replace("{style}", request.style_notes or style_fallback)
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

        clips_seen = 0          # max clips any single search returned
        nudged = False          # whether we force-pushed an emit_plan reminder

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
                text = step.content or self._t("shotlist_generated")
                return CutDirectorResult(text, last_plan)

            # Convergence push: once we're past the halfway point without a plan,
            # force the model to commit to emit_plan (flaky local tool-callers
            # otherwise keep exploring until the round cap).
            if not nudged and round_i + 1 >= self._max_tool_rounds // 2:
                nudged = True
                messages.append({
                    "role": "system",
                    "content": self._t("nudge_emit_now_run" if clips_seen > 0 else "nudge_no_footage_run"),
                })

        # Round cap hit — finalize with the best plan we have + a diagnostic note.
        if last_plan is not None:
            note = self._t("returned_draft")
        elif searches > 0 and clips_seen == 0:
            note = self._t("no_footage_round_cap")
        else:
            note = self._t("generation_failed_round_cap")
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
                "  // No results: do not repeat the same filters; broaden date/type, or"
                " if there truly is no footage, tell the user to scan and add clips first."
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


    def _system_prompt(self, request: RoughCutRequest) -> str:
        target = ""
        if request.target_min_s is not None and request.target_max_s is not None:
            target = self._t("target_duration", lo=request.target_min_s / 60, hi=request.target_max_s / 60)
        date_range = ""
        if request.date_from or request.date_to:
            unlimited = "不限" if self._ui_language == "zh" else "unlimited"
            date_range = self._t(
                "run_sys_daterange",
                df=request.date_from or unlimited,
                dt=request.date_to or unlimited,
            )
        return self._t(
            "run_system_prompt",
            aspect=request.aspect_ratio,
            target=target,
            date_range=date_range,
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
