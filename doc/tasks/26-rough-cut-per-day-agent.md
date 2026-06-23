# 26 · 初剪导演升级：按天 mini-agent（确定性编排 + 每日工具循环）

> **状态：代码实现完成 + 自动测试通过（524 全绿），真机 eval 待手动。** 在 25 的基础上，把"每天一次纯 JSON 补全"
> 升级为"每天一个 scoped 工具循环"，让模型当天能**多轮探索素材**（深挖 transcript、按需看 B-roll 画面、迭代调整），
> 换取更智能的分镜，同时保留 25 的确定性骨架与本地可靠性。**v1 不上 critic 审片 agent**（留作 v2）。
>
> **已落地**：`config.Prefs.cut_director_mode`（`"agent"`|`"staged"`，默认 `agent`）+ `PrefsOut`/`SettingsUpdate` 同步；
> `director.DAY_TOOLS`（worker 只暴露 get_clip_detail/inspect_broll/emit_plan，不含 search）+ `CutDirector(mode=...)`；
> `generate()` 每天先跑 `_run_day()`（scoped 工具循环，`tool_choice="auto"` 自然收口 + 过半 nudge），不收口则回落 `_staged_day()`（纯 JSON）；
> inspect_broll 预算跨天共享。`app.py` 接 `mode=prefs.cut_director_mode`。后端 +4 单测（agent 收口 / 回落 / staged 跳过 / 去重），ruff 干净。
>
> **防幻觉/防死循环**：①死循环由 `for round_i in range(max_tool_rounds)` 硬上限 + 过半 nudge + round-cap 回落兜底严格 bound；
> ②`_run_day` 加**每日去重护栏**——同一 `(工具名, 参数)` 第二次出现直接短路返回"结果同上，请用已有信息或 emit_plan"，
> 不重复打 DB / 不重复烧 vision 预算、并推动收口。
>
> **依赖**：25（现有 `CutDirector`、工具集、`cutplan_service`、`omlx_agent`）。
> **位置**：后端 `cutplan/director.py`（主改）、`pipeline/cutplan_service.py`、`adapters/omlx_agent.py`、`config.py`。
> **设计**：`detailed-design.md` §3.15（在现有小节追加"按天 mini-agent"）。

---

## 背景：为什么要改

25 上线后实际走的是 `CutDirector.generate()` 的**纯 JSON staged 路径**（`cutplan_service.py:75`）：
确定性检索 → 按拍摄日期分组排序 → 每天调一次 `complete()`（无工具）吐 JSON → 宽松解析 → 确定性建计划/校验。

这条路**可靠但不够智能**：模型只能照着预先喂进 prompt 的当天素材清单一次性出片，**不能**按需深挖某条 transcript、
**不能**现场看 B-roll 画面定夺、**不能**迭代调整。自主工具循环 `run()` 写好了但实际未被调用。

## 实测依据（OMLX 本地 tool-calling 现状）

对 director 真实的 `TOOLS` schema 跑了对照实验（OMLX `http://localhost:1235/v1`），结论修正了"本地不能 tool calling"的旧判断：

| 测试（×5 取方差） | Gemma4-26b | Qwen3.6-35B-A3B |
|---|---|---|
| **A. 自主 loop（`tool_choice="auto"`，无强制）** | emit ×4 / no-emit ×1 → **4/5 收口** | **emit@round1 ×5 → 5/5 收口** |
| **B. named `tool_choice` 强制 emit_plan** | ❌ 直接吐文字、零 tool call | ✅ honor |
| **C. 只暴露 emit_plan + `tool_choice="required"`** | ❌ 返回列表外的 `search_footage` ×5 | ❌ 同上 ×4 + 空 emit ×1 |

**关键结论：**
1. **emit_plan 能用，而且在"单日小上下文"下可靠**（Qwen 5/5、Gemma 4/5 自然收口）。当初"Qwen 不收口"的根因是**一次性跨多天大上下文**（token 跑飞），不是 tool-calling 缺陷——25 的按天拆分已经解决了这一点。
2. **不要用 named `tool_choice` 强制**（Gemma 无视、退化成文字）。
3. **不要中途裁剪 tools 列表 + `required`**（历史里有 tool_call 时 OMLX 工具约束会"漏"，两个模型 9/10 返回列表外的函数）。
4. → **正确做法：`tool_choice="auto"` + 自然收口 + round-cap 兜底**。不靠任何强制收口。
5. **默认模型：Qwen3.6-35B-A3B**（本测试里 tool 收口更稳，5/5）；Gemma4-26b 可用但略逊（4/5）。

## 已确认的方案

**确定性 Python 编排 + 按天 mini-agent**：
- **主编排 = 确定性 Python（不是 LLM）**：复用 `generate()` 的骨架——按拍摄日期分组、组内按 `capture_time` 排序、
  目标时长按天均分、收集每天结果、`_build_plan` 的 in/out 钳位 + 总时长 + 章节 + 校验、失败天兜底跳过。**这部分原封不动。**
- **每天 = 一个 scoped LLM 工具循环**（取代当天那次 `complete()`）：只喂当天素材，模型可多轮
  `get_clip_detail`（深挖 transcript 分段）/ `inspect_broll`（按需 Qwen3-VL 看画面），最后自然 `emit_plan` 出当天分镜。
  - 当天 history 独立、`tool_choice="auto"`、保留 vision 预算（25 已有 `vision_budget`）。
  - **不在 worker 里放 `search_footage`**：当天素材已由主编排确定性检索好并喂入；worker 的增值是"深挖 + 看画面 + 迭代"，不是再检索。
- **每天 round-cap 兜底**：当天循环在 round 上限内没收口 → **回落到该天的纯 JSON `complete()`**（25 现有逻辑），保证那天仍出片。
- **全局开关**：保留 25 的纯 JSON staged 路径作为可选 fallback（`config` 里加 `cut_director_mode: "agent" | "staged"`，默认 `agent`）。

**v1 明确不做：** critic 审片 agent（拼好全片后检查节奏/叙事/A-B 配比再让对应天修一轮）——留作 **v2**，时长校验已是确定性，critic 只管主观质量。

## 工作分解

1. **`director.py`：每天 worker 改为工具循环** → verify：单测覆盖"一天内 search→detail→emit 收口"路径（用 fake `LLMAgentClient`）。
   - 抽出 `_run_day(day, clips, ...) -> day_shots`：scoped messages + `self._llm.run(messages, DAY_TOOLS)` 多轮，
     工具只含 `get_clip_detail` / `inspect_broll` / `emit_plan`；沿用现有 round-cap、vision 预算、`_append_tool_result`。
   - `generate()` 主循环把"调 `complete()` + 解析"换成"调 `_run_day`"。
2. **每天兜底回落** → verify：单测模拟 worker 在 round-cap 内不收口 → 自动走该天 `complete()` 纯 JSON，仍产出 shots。
3. **`config.py`：`cut_director_mode` 开关 + 默认 `agent`** → verify：`test_config` 增项；`cutplan_service` 按 mode 选路径。
4. **`omlx_agent.py`：确认 `run()` 在真机可用** → verify：保留现有 `run()`；`tool_choice="auto"`，不引入 named/required 强制。
5. **（可选）自检脚本** `scripts/check_omlx_toolcalling.py`：对配置的 `TEXT_MODEL` 跑"A 自主 loop 收口率"探测，给出 X/5。
   → verify：能对真实 OMLX 打印每个模型的收口率，便于换模型时复测。
6. **文档**：`detailed-design.md` §3.15 追加"按天 mini-agent"小节 + 本实测表；`25-rough-cut-agent.md` 顶部状态注记指向 26。

## 验收

- [ ] 单测：worker 工具循环收口、worker 不收口→纯 JSON 兜底、mode 开关选路 全绿（`make test`）。
- [ ] 真机 eval：对真实 OMLX（Qwen3.6）跑一段多日素材，确认每天能触发 `get_clip_detail`/按需 `inspect_broll`，
      产出的分镜比纯 staged 更贴合（主观对比），且无某天因不收口而整体失败。
- [ ] mypy / ruff 干净。

## 风险与备注

- **无真并行**：OMLX 单服务、同类调用串行，多 worker 是"更智能/更可靠"，不是"更快"；按天串行执行即可。
- **worker 偶发不收口**：靠 per-day round-cap + 纯 JSON 兜底吸收（Gemma 的 1/5 情形）。
- **不引入多 agent 框架、不让 LLM 自己 spawn sub-agent**：编排必须是确定性 Python（继承 25/proposal 的"算术与收口归代码"哲学）。
