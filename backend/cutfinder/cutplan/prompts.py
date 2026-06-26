"""Static prompts, tool schemas, and the bilingual message catalog for the
CutDirector.

Kept out of ``director.py`` so that module stays control-flow only: the long
prompt文案 and the EN/ZH progress / agent strings live here, and the director
reaches them through :func:`message` (``self._t`` at the call site).
"""

from __future__ import annotations

from typing import Any

# Built-in default director prompt for the staged generator. Editable in the UI
# (persisted to ~/.cutfinder/config.json); the "reset" button restores this text.
# Placeholders {aspect}/{target}/{style} are substituted per request — keep them
# if you want the aspect ratio / target duration / style to appear in the prompt.

DEFAULT_CUT_DIRECTOR_PROMPT_ZH = (
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

DEFAULT_CUT_DIRECTOR_PROMPT_EN = (
    "You are a professional rough-cut editor. From the cataloged footage below, produce a shot list\n"
    "with precise in/out points within each clip so the user can load it into their editing software.\n"
    "Organize by shooting date: each date is a chapter (ISO format, e.g. 2026-04-25).\n"
    "Order chapters chronologically; within each day, keep clips in shooting-time order — what happened first\n"
    "comes first. The clip list is already sorted by capture time; preserve that order.\n"
    "Use A-roll (with narration) as the narrative spine. Base A-roll cuts on transcript content;\n"
    "set in/out at segment boundaries, not existing keyframes. Follow each A-roll with B-roll from the same scene/time.\n"
    "For B-roll, pick a suitable window within its duration.\n"
    "Use only clip_ids from the catalog — do not invent. Keep total duration close to target.\n"
    "You **do not need every clip**: curate actively. Drop duplicates, filler, or weak shots;\n"
    "for similar B-roll / burst photos from the same scene, pick only 1–2. Quality over quantity.\n"
    "Aspect ratio: {aspect}. {target} Style/rhythm: {style}"
)

# Critic (task 28 Part B): a single review pass over the already-assembled plan.
# It judges only *subjective* quality (rhythm, narrative flow, A/B-roll balance);
# the duration check stays deterministic in Python. It names shooting dates to
# redo, which the director re-runs through the same per-day merge mechanism.

CRITIC_SYSTEM_PROMPT_ZH = (
    "你是资深视频剪辑指导，负责审片。只评判主观质量：节奏松紧、叙事是否连贯、"
    "A-roll 解说主线与 B-roll 空镜的配比、空镜衔接是否缺位。"
    "点名需要调整的【拍摄日期】并给出可执行建议；不要改时长（系统会另行校验）。"
    "只指出最关键的几处。"
)

CRITIC_SYSTEM_PROMPT_EN = (
    "You are a senior video editor reviewing an assembled rough cut. Judge only subjective quality:\n"
    "rhythm and pacing, narrative flow, A-roll / B-roll balance, whether coverage is missing.\n"
    "Name shooting dates that need adjustment and give actionable suggestions. Do not change durations.\n"
    "Flag only the most critical issues."
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


# ── bilingual message catalog ────────────────────────────────────
#
# key → (zh, en) template pair. Call :func:`message` (or ``self._t`` in the
# director). Entries that take format params interpolate via ``str.format``;
# entries whose text contains literal ``{ }`` braces (JSON examples) carry **no**
# params so ``.format`` is never run on them — keep that invariant when editing.

_MESSAGES: dict[str, tuple[str, str]] = {
    # progress — staged generate()
    "no_date": ("无日期", "No date"),
    "searching_footage": ("正在检索素材…", "Searching footage…"),
    "no_footage_in_range": (
        "没有在该日期范围找到已编目的素材。请确认素材已扫描入库，或调整日期范围。",
        "No cataloged footage in that date range. Check your scan or adjust the range.",
    ),
    "found_clips_days": (
        "找到 {n} 个片段、共 {days} 天，开始生成…",
        "Found {n} clips across {days} days, generating…",
    ),
    "generating_day": (
        "正在生成第 {idx}/{n} 天（{day}）· 本天 {clips} 个片段",
        "Generating day {idx}/{n} ({day}) · {clips} clips",
    ),
    "day_step": ("第 {idx}/{n} 天（{day}）· {detail}", "Day {idx}/{n} ({day}) · {detail}"),
    "inspected_carry": ("（带入 {n} 条已勘察画面）", "(with {n} inspected frames)"),
    "day_fallback": (
        "第 {idx}/{n} 天（{day}）· 改用快速生成{extra}…",
        "Day {idx}/{n} ({day}) · Falling back to fast generation{extra}…",
    ),
    "day_done": (
        "第 {idx}/{n} 天（{day}）完成 · 已选 {shots} 个镜头",
        "Day {idx}/{n} ({day}) done · {shots} shots selected",
    ),
    "generation_failed": (
        "生成分镜表失败（模型未返回有效结果），请重试或把需求说得更具体。",
        "Shot list generation failed (no valid output). Retry or refine your request.",
    ),
    "no_clips_selected": (
        "模型没有选出可用片段，请重试或调整需求。",
        "No clips selected. Retry or adjust your request.",
    ),
    "shotlist_generated": ("已生成初剪分镜表。", "Rough-cut shot list generated."),
    "dates_skipped": (
        "（{dates} 这些日期未能生成，已跳过。)",
        " (dates {dates} failed and were skipped).",
    ),
    # critic pass
    "reviewing_cut": ("正在审片…", "Reviewing cut…"),
    "redoing_per_critic": ("按审片意见重做 {day}…", "Redoing {day} per critic feedback…"),
    "critic_feedback": (
        "{user_text}\n\n[审片意见] {day}：{issue} → {action}",
        "{user_text}\n\n[Critic feedback] {day}: {issue} → {action}",
    ),
    # plan digest (critic review)
    "digest_header": (
        "以下是已拼好的初剪分镜表（按拍摄日期分章）：",
        "Here is the assembled rough-cut shot list (organized by shooting date):",
    ),
    "digest_footer": (
        "\n请审阅主观质量（节奏松紧、叙事是否连贯、A-roll 主线与 B-roll 空镜配比、"
        "空镜是否缺位），只输出 JSON："
        '{"revisions": [{"date": "YYYY-MM-DD", "issue": "问题", "action": "可执行的修改建议"}]}。'
        "整体良好则 revisions 用空数组。",
        "\nReview subjective quality (rhythm, narrative flow, A-roll / B-roll balance, missing coverage).\n"
        "Output only JSON: "
        '{"revisions": [{"date": "YYYY-MM-DD", "issue": "issue", "action": "suggestion"}]}.'
        "Use an empty array if overall fine.",
    ),
    "digest_day": ("【{day}】", "[{day}]"),
    # per-day prompt building
    "day_budget": (
        "\n这一天的目标时长约 {lo:.1f}–{hi:.1f} 分钟。",
        "\nTarget duration for this day: ~{lo:.1f}–{hi:.1f} min.",
    ),
    "day_prompt_head": (
        "{user_text}\n\n本次只为【{day}】这一天生成分镜，chapter 一律填 \"{day}\"。{budget}\n\n"
        "该日期可用素材（只能用下列 clip_id）：\n{context}\n\n",
        "{user_text}\n\nGenerate shots only for {day}, chapter = \"{day}\".{budget}\n\n"
        "Available clips for this date (use only these clip_ids):\n{context}\n\n",
    ),
    "day_prompt_agent_tail": (
        "上面清单里 A-roll 只给了摘要，标 [有台词] 的片段**完整台词分段要用 "
        "get_clip_detail(clip_id) 获取**，再据此把 in/out 落在 segment 边界上。"
        "请**只通过工具推进**：用 get_clip_detail 读取你想用的 A-roll 台词、"
        "必要时用 inspect_broll 现场看 B-roll 画面（尽量少用），"
        "**最后必须调用 emit_plan 工具**给出这一天的最终分镜表，不要用纯文字回答。",
        "The list above gives only summaries for A-roll. For clips marked [has transcript],\n"
        "**use get_clip_detail(clip_id) to fetch full transcripts**, then set in/out at segment boundaries.\n"
        "**Use tools only**: get_clip_detail for A-roll transcripts, inspect_broll to check B-roll frames (sparingly),\n"
        "and **finally call emit_plan** to submit today's shot list. Do not reply in plain text.",
    ),
    "day_prompt_json_tail": (
        "请只输出 JSON，格式：\n"
        '{"note": "可选备注", "shots": [{"clip_id": 整数, "roll": "a"或"b", '
        '"in_s": 数字, "out_s": 数字, "content": "台词或画面", "rationale": "用途理由"}]}',
        'Output only JSON, format:\n'
        '{"note": "optional note", "shots": [{"clip_id": int, "roll": "a" or "b",'
        '"in_s": number, "out_s": number, "content": "text or visual", "rationale": "reason"}]}',
    ),
    # context catalog
    "no_capture_time": ("无拍摄时间", "no capture time"),
    "has_transcript_mark": (" [有台词]", " [has transcript]"),
    # system / staged prompt fragments
    "target_duration": ("目标时长 {lo:.0f}–{hi:.0f} 分钟。", "Target duration: {lo:.0f}–{hi:.0f} min."),
    "style_fallback": ("（自行把握）", "(at your discretion)"),
    # agent loop (per-day)
    "accepted_text_shotlist": (
        "导演直接给出文字分镜，已采纳",
        "Director gave a text shot list directly — accepted",
    ),
    "director_replied_text": (
        "导演未用工具、直接回了文字：{reply}",
        "Director replied in text without tools: {reply}",
    ),
    "nudge_use_tools_prose": (
        "不要用纯文字回复。请**用工具**推进：用 get_clip_detail(clip_id) "
        "查看标了 [有台词] 的 A-roll 片段台词，或直接调用 emit_plan 工具"
        "提交这一天的分镜表（shots 放在工具参数里）。",
        "Do not reply in plain text. **Use tools**: call get_clip_detail(clip_id) "
        "to read transcripts for A-roll clips marked [has transcript], or call emit_plan directly"
        "to submit today's shot list (shots in tool arguments).",
    ),
    "director_thinking": ("导演思路：{reasoning}", "Director thinking: {reasoning}"),
    "tool_already_called": (
        "（你已用相同参数调用过该工具，结果同上；请改用已有信息，或直接调用 emit_plan。）",
        "You already called this tool with the same arguments — use what you have, "
        "or call emit_plan directly.",
    ),
    "detail_label_transcript": ("台词", "transcript"),
    "detail_label_visual": ("画面信息", "visual info"),
    "checking_clip": ("查看片段 {label} 的{what}", "Checking {label} {what}"),
    "inspecting_clip": ("查看片段 {label} 的画面", "Inspecting frames for {label}"),
    "nudge_emit_now_day": (
        "你已了解足够。现在**必须**调用 emit_plan 给出这一天的最终分镜表，不要再查看素材。",
        "You have enough context. **Call emit_plan now** to finalize today's shot list."
        " Do not inspect more clips.",
    ),
    "inspected_findings_header": (
        "导演已现场勘察过以下 B-roll 画面，请优先据此判断其用途（而非仅凭标签）：\n",
        "Director has already inspected the following B-roll frames — use these descriptions first instead of relying only on tags:\n",
    ),
    # autonomous run() loop
    "nudge_emit_now_run": (
        "你已检索足够。现在**必须**调用 emit_plan 给出最终分镜表，"
        "用目前掌握的素材尽力而为，不要再检索。",
        "You have searched enough. **Call emit_plan now** to finalize the shot list, "
        "doing your best with what you have. Do not search further.",
    ),
    "nudge_no_footage_run": (
        "多次检索未找到素材。请直接用文字回复用户：该日期范围内没有"
        "已编目的素材，提示其确认素材已扫描入库或调整日期范围。",
        "No results from multiple searches. Reply directly to the user: no cataloged footage "
        "in this date range; suggest they scan and add clips or adjust the range.",
    ),
    "returned_draft": ("（已返回当前分镜草稿。）", "(Returned current shot list draft.)"),
    "no_footage_round_cap": (
        "没有在该日期范围找到已编目的素材。请确认素材已扫描入库，"
        "或调整日期范围后重试。",
        "No cataloged footage found in this date range. Confirm clips are scanned and added, or adjust the range.",
    ),
    "generation_failed_round_cap": (
        "尝试多次仍未能生成分镜表（本地模型的工具调用可能不稳定）。"
        "请重试，或把需求说得更具体一些。",
        "Multiple attempts still failed to produce a shot list — local model tool calls may be unstable. "
        "Retry or provide more specific requirements.",
    ),
    "run_sys_daterange": (
        "素材日期范围 {df} 到 {dt}。",
        "Footage range: {df} to {dt}. ",
    ),
    "run_system_prompt": (
        "你是专业的视频初剪导演。基于已编目的素材库，为用户生成一份精确到片段内 in/out 的"
        "文字分镜表，供其照搬到剪辑软件。\n"
        "结构：以 A-roll（有解说）的句子作为叙事主线，再为每段配合适的 B-roll 空镜插空。\n"
        "A-roll 选段以 transcript（台词内容）为主要依据，in/out 落在 segment 边界上，不要依赖已有关键帧切点。\n"
        "工具：search_footage 检索素材，get_clip_detail 取 transcript 分段（A-roll 的"
        " in/out 应落在 segment 边界上），inspect_broll 仅在文本元数据不足时现场看 B-roll 画面（尽量少用、"
        "可批量），最后用 emit_plan 给出最终分镜表。\n"
        "不要自己计算总时长，系统会校验。只使用素材库里真实存在的 clip。\n"
        "画面比例 {aspect}。{target}{date_range}\n",
        "You are a professional rough-cut editor. From the cataloged footage, produce an ordered\n"
        "shot list with precise in/out points for the user to load into their editing software.\n"
        "Structure: A-roll (with narration) forms the narrative spine, with B-roll coverage inserted.\n"
        "Base A-roll cuts on transcript content; set in/out at segment boundaries, not existing keyframes.\n"
        "Tools: search_footage to find clips, get_clip_detail for transcript segments,\n"
        "inspect_broll only when text metadata is insufficient (sparingly, batchable),\n"
        "finally emit_plan to submit the shot list.\n"
        "Do not compute total duration yourself — the system checks it. Use only real clips from the catalog.\n"
        "Aspect ratio: {aspect}. {target}{date_range}",
    ),
}


def message(key: str, lang: str, /, **kw: Any) -> str:
    """Return the *lang* ("zh"/"en") message for *key*, formatted with *kw*.

    Non-"en" languages get the Chinese text (the director's default). Entries
    with literal ``{ }`` braces must be called without kwargs so ``.format`` is
    skipped and the braces survive verbatim.
    """
    zh, en = _MESSAGES[key]
    template = en if lang == "en" else zh
    return template.format(**kw) if kw else template
