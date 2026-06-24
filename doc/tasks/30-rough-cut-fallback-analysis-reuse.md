# 30 · 初剪 fallback 复用 agent 已勘察分析

> **状态：已实现 + 自动测试通过（后端 538 全绿、ruff/mypy 干净；前端 206 全绿、tsc 干净）。真机 eval 待手动。** 单天 mini-agent 收不了口回落到快速模式（`_staged_day`）时，把 agent 已经**花视觉预算**勘察到的 B-roll 画面描述带进快速模式的 prompt，不再白费。外加回落进度文本 + 超/欠时长的一句说明文案。
>
> **依赖**：26（按天 mini-agent）、28（refine 合并 / `_gen_one_day`）、本分支「busy days use tools」修复（lean/full 上下文）。
> **位置**：后端 `cutplan/director.py` 为主；前端 `features/cutplan/index.tsx` + `i18n` 一句文案。
> **设计稿**：`docs/superpowers/specs/2026-06-24-rough-cut-fallback-analysis-reuse-design.md`。

---

## 背景：回落丢弃 agent 已勘察的分析

agent 模式单天先跑 scoped tool 循环（`_run_day`）：模型可 `get_clip_detail` 读 A-roll 完整台词、`inspect_broll`（受 `cut_vision_budget` 约束）让 Qwen3-VL **现场看 B-roll 画面**拿描述，最后 `emit_plan` 收口。收不了口（纯文字且无法 salvage、或超轮数）→ 回落 `_staged_day`（一次结构化 JSON、无工具）。

**问题**：`_run_day` 的工具结果只在它内部那段 `messages` 里。一回落，整段 `messages` 丢弃，`_staged_day` 从头重建、只看每条片段的**存量元数据**（catalog 阶段的 summary/tags）。其中 `inspect_broll` 结果尤其可惜——它**花了视觉预算**，`_do_inspect` 只把文本塞进 messages、**不缓存不落库**，回落后这份新鲜画面分析白做。实测忙日（单天 28 片段）正是高频回落场景。

> 注：读过的台词已在 `cache` 里、快速模式本就**全量内联**台词，无增量价值——所以复用重点是 `inspect_broll` 的视觉描述，不是台词。

## 方案（已确认）

### A — 回落时带入 inspect_broll 勘察结果

数据流：
```
_run_day ── inspect_broll 成功 ──> findings: dict[int,str]  (clip_id → 画面描述)
   │ 返回 (shots, note, vision_used, findings)
   ▼
_gen_one_day ── day_shots is None ──> _staged_day(..., findings=findings)
                                          └─ findings 非空 → prompt 追加「导演已现场勘察…」段
```

**改动（`director.py`）**
1. **`_run_day` 累积 + 返回 findings**：函数内 `findings: dict[int,str] = {}`；`inspect_broll` 分支用 `new_used > vision_used` 作**成功信号**（非"预算耗尽/不可用"错误串）记 `findings[cid]=text`。4 个返回点统一返回四元组 `(shots, note, vision_used, findings)`。
2. **`_gen_one_day` 透传**：解四元组；回落分支 `on_fallback(len(findings))` + `_staged_day(..., findings=findings)`。
3. **`_staged_day` 注入**：新增可选参 `findings: dict[int,str] | None = None`；`_day_messages(..., agent=False)` 建好后，若非空 append 一条 system 消息「导演已现场勘察过以下 B-roll 画面，请优先据此判断（而非仅凭标签）：`[cid] 描述…`」。

### 进度文本

`generate()` 的 `on_fallback` 闭包加计数参 `def on_fallback(n=0, ...)`；`n>0` 显示「第 i/N 天（day）· 改用快速生成（带入 {n} 条已勘察画面）…」，否则维持原文案。

### B — 超/欠时长只列 flag（最小，多为既有）

时长**不裁、不重剪**（用户：时长无硬性要求，超/欠多半是素材问题）。前端已有 `within_target` 的 ⚠️ + 红字（`cutplan/index.tsx:732`），仅在 ⚠️ 后补一句说明：中 `（该范围内素材有限，已尽量贴近）` / 英 `(limited footage in range — fitted as close as possible)`，i18n 加 key。

## 明确不做（YAGNI）

- 不裁镜头、不加 protected/rationale schema、不加重剪轮。
- 不复用台词作额外注入（已全量内联）。
- 不落库勘察结果（保持 surgical，仅本次生成内有效）。
- 不带"半成品分镜"：回落恰在「未成功 emit_plan」时，没有部分 shots 可带。

## 边界

- inspect 返回错误串（inspector 不可用 / 预算耗尽 / 找不到 clip）→ `vision_used` 不增 → **不记 findings**，staged 不被噪音污染。
- findings 为空 → `_staged_day` 行为与现状**逐字节一致**（不追加消息），纯增量无回归。
- findings 段无需额外预算上限：受 `cut_vision_budget`（默认 6）天然约束，至多 6 条。

## 测试

- `_run_day`：scripted agent 调一次 inspect_broll（假 inspector 回固定描述）→ 两轮 prose（无法 salvage）→ 回落；断言 findings 含该描述、`vision_used==1`。
- staged 注入：FakeLLM `complete` 捕获 messages，断言含「导演已现场勘察」段 + 那条描述；findings 为空时断言**不含**。
- 进度：断言回落时 `progress` 收到「带入 1 条已勘察画面」。
- 既有 `test_generate_agent_falls_back_to_staged_on_nonconvergence` 等：确认四元组返回不破坏断言。
- 全套 `uv run pytest` / `ruff` / `mypy` 绿；前端 `tsc` + cutplan 测试绿。

## 验收标准

1. agent 看过 B-roll 后回落，staged prompt 含那些画面描述；视觉预算不再白费。
2. 回落进度行显示带入条数。
3. 超/欠时长时 UI 有 ⚠️ + 一句素材说明；不发生裁剪。
4. findings 为空时行为与改动前一致（纯增量、无回归）。
