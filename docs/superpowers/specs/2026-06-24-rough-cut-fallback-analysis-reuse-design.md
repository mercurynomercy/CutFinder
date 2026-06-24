# 初剪 fallback 复用 agent 分析 — 设计文档

- **日期**：2026-06-24
- **范围**：`backend/cutfinder/cutplan/director.py` 为主，外加前端时长 flag 的一句文案
- **状态**：设计已与用户确认（A 通过；B 缩为既有 flag + 一句说明）

## 背景与动机

初剪导演按拍摄日期逐天生成（`CutDirector.generate` → `_gen_one_day`）。agent 模式下，单天先跑 scoped tool 循环（`_run_day`）：模型可用 `get_clip_detail` 读 A-roll 完整台词、用 `inspect_broll`（受 `cut_vision_budget` 约束）让 Qwen3-VL **现场看 B-roll 画面**拿到描述，最后 `emit_plan` 收口。收不了口（纯文字回复且无法 salvage、或超轮数）时回落到 `_staged_day`（一次结构化 JSON 补全，无工具）。

**问题**：`_run_day` 的工具结果只存在它内部那段 `messages` 里。一旦回落，这段 `messages` 被整段丢弃，`_staged_day` 从头重建对话、只看每条片段的**存量元数据**（catalog 阶段存的 summary/tags）。其中 `inspect_broll` 的结果尤其可惜——它**花了视觉预算**、`_do_inspect` 只把文本塞进 messages、**不缓存也不落库**，回落后这份新鲜的画面分析白做。

实测忙日（如单天 28 片段）正是高频回落场景，浪费最明显。

## 范围

- **A（主要）**：回落到快速模式时，把 agent 已勘察的 `inspect_broll` 画面描述带进 `_staged_day` 的 prompt。
- **进度文本**：回落进度行在有勘察结果时显示带入条数，UI 可见分析被复用。
- **B（最小）**：超/欠目标时长**不裁、不重剪**，沿用既有 `within_target` flag；前端在 ⚠️ 时补一句"可能素材有限"的说明文案。

### 明确不做（YAGNI）

- 不裁剪镜头、不做 protected/rationale schema、不加重剪轮（用户明确：时长无硬性要求，超了多半是素材问题）。
- 不复用读过的台词作为**额外**注入——台词已在 `cache`，快速模式本就全量内联，无增量价值。
- 不持久化勘察结果到 catalog（保持 surgical，仅本次生成内有效）。
- 不带"半成品分镜"：回落恰好发生在「没成功 emit_plan」时，没有部分 shots 可带。

## 设计

### 数据流

```
_run_day  ── 执行 inspect_broll 成功时 ──> findings: dict[int, str]  (clip_id → 画面描述)
   │ 返回 (shots, note, vision_used, findings)
   ▼
_gen_one_day ── day_shots is None（回落）──> _staged_day(..., findings=findings)
                                                  │ findings 非空时，prompt 追加
                                                  ▼
                                       「导演已现场勘察过这些 B-roll 画面…」段
```

### 组件改动（`director.py`）

1. **`_run_day` 累积 findings**
   - 新建局部 `findings: dict[int, str] = {}`。
   - `inspect_broll` 分支：`text, new_used = self._do_inspect(...)`；当 `new_used > vision_used`（即真的看了，非"预算耗尽/不可用"错误串）时 `findings[clip_id] = text`；再 `vision_used = new_used`。用 vision_used 自增作为**成功信号**，避免把错误串喂给 staged。
   - 所有返回点（salvage / 已 emit / 回落 None / 轮数用尽）统一返回四元组，新增末位 `findings`。

2. **`_gen_one_day` 透传**
   - `day_shots, day_note, vision_used, findings = self._run_day(...)`。
   - 回落分支：`self._staged_day(request, history, user_text, day, full, per_day, findings=findings)`。
   - 调 `on_fallback(len(findings))`（见进度文本）。

3. **`_staged_day` 注入**
   - 新增可选参数 `findings: dict[int, str] | None = None`。
   - 用 `_day_messages(..., agent=False)` 建 messages 后，若 `findings`，追加一条 system 消息：
     ```
     导演已现场勘察过以下 B-roll 画面，请优先据此判断（而非仅凭标签）：
     [clip_id] 描述…
     ```
   - 其余逻辑不变。

### 进度文本

- `generate()` 里的 `on_fallback` 闭包签名加一个计数参数：`def on_fallback(n=0, _i=idx, _d=day)`。
- 文案：`n > 0` 时 `第 i/N 天（day）· 改用快速生成（带入 {n} 条已勘察画面）…`；否则维持原「· 改用快速生成…」。

### B：前端时长说明（最小）

- `frontend/src/features/cutplan/index.tsx` 时长行（~732）：`!within_target` 时在 `⚠️` 后补一句 `t('roughcut.durationFootageHint')`。
- i18n 加 key（中/英）：中 `（该范围内素材有限，已尽量贴近）` / 英 `(limited footage in range — fitted as close as possible)`。

## 错误处理与边界

- `inspect_broll` 返回错误串（inspector 不可用 / 预算耗尽 / clip 找不到）时 `vision_used` 不增，**不记入 findings**——staged 不会被错误噪音污染。
- `findings` 为空（agent 没看过任何 B-roll 就回落）时，`_staged_day` 行为与现状完全一致（不追加消息）。
- findings 段长度不设额外预算上限：受 `cut_vision_budget`（默认 6）天然约束，最多 6 条描述，不会撑爆 staged prompt。

## 测试

- **`_run_day` 累积 + 回落带出**：脚本化 FakeAgentLLM —— 第 1 轮调 `inspect_broll`（假 inspector 回固定描述），第 2、3 轮纯文字（无法 salvage）→ 触发回落。断言 `_run_day` 返回的 findings 含该 clip 描述、`vision_used == 1`。
- **staged 注入**：FakeLLM 的 `complete` 捕获 messages，断言含「导演已现场勘察」段且包含那条描述；findings 为空时断言**不含**该段。
- **进度文本**：断言回落时 `progress` 收到「带入 1 条已勘察画面」。
- **既有用例**：`test_generate_agent_falls_back_to_staged_on_nonconvergence` 等需确认四元组返回不破坏现有断言。
- 全套 `uv run pytest`、`ruff`、`mypy` 维持绿；前端 `tsc` + cutplan 测试绿。

## 验收标准

1. agent 看过 B-roll 后回落，staged prompt 含那些画面描述；花掉的视觉预算不再白费。
2. 回落进度行显示带入的勘察条数。
3. 超/欠目标时长时 UI 有 ⚠️ + 一句素材说明；不发生任何裁剪。
4. findings 为空时，行为与改动前逐字节一致（纯增量、无回归）。
