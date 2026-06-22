# 25 · 初剪导演 Agent（对话生成分镜表）

> 在**已编目素材库**之上，通过**多轮对话**，依据用户给的日期范围 / 目标时长 / 风格 / 节奏 / 画面比例，产出一份
> **精确到片段内 in/out 的文字分镜表（A-roll 叙事主线 + B-roll 插空）**，供用户照搬到剪辑软件。
> **全本地离线**：Agent 推理走 OMLX 的 Qwen3.6 文本模型，必要时调 Qwen3-VL 现场看 B-roll 画面。
> **不渲染、不导出剪辑工程**（FCPXML 留作后续）。
>
> **依赖**：05（transcript segments）、06（Qwen3.6 文本模型 client）、07（Qwen3-VL 视觉 client）、03（ffmpeg 抽帧）、09（仓储）、12（队列+SSE）、13（API）、14（前端）、16（关键帧切点，按需复用）。
> **位置**：后端 `domain/`、`ports/`、`adapters/`、`cutplan/`（新领域）、`api/`；前端 `features/cutplan`。
> **设计**：`detailed-design.md` §3.15。

---

## 已确认的决策（来自用户）

| 维度 | 决策 |
|---|---|
| 产出形态 | **纯文字时间线 + 分镜表**，照搬到剪辑软件手动拼（不做 FCPXML/EDL 导出器） |
| 颗粒度 | **精确到片段内 in/out 时间码**（复用 transcript 分段 + 已有关键帧切点） |
| 素材来源 | **已编目素材库**（查 SQLite，按日期范围 / 类型 / 标签 / 台词检索；素材须先扫描入库） |
| 交互模型 | **多轮对话 agent**（可反复"第 3 段太长 / 换个 B-roll / 节奏再快点"地调整） |
| 叙事结构 | **A-roll 叙事主线 + B-roll 插空** |
| B-roll 选择依据 | **已存文本元数据为主，必要时现场跑 Qwen3-VL** 确认画面 |
| 风格/节奏/比例 | **自然语言自由解释**（作为系统提示注入，不预设映射表/旋钮） |
| 分镜表 | **含缩略图引用 + 章节分组** |
| 会话 | **持久化进 SQLite，可重开，可删除** |

### 硬约束（继承 proposal）

- **原文件只读**：Agent 全程只读编目与副本，不碰源文件、不渲染、不写视频。
- **全本地离线**：文本 Agent 走 Qwen3.6（OMLX），视觉确认走 Qwen3-VL（OMLX），不联网。
- **素材须先入库**：Agent 只读编目；库里没有该日期范围素材时，明确提示先扫描，不现场扫源文件夹。

---

## 设计要点（方案 C：受约束的工具调用环）

把"会算错、要稳定"的部分（时长是否凑够目标区间、in/out 时间码、表格渲染）交给**确定性代码**；把"需要创意"的部分（挑哪句解说当主线、配哪条 B-roll、节奏松紧）交给 **LLM 工具调用环**。LLM 跑飞时由确定性脚手架 + 护栏兜底。

### 工具集（每个工具一个接口，LLM 只能调这些）

- `search_footage(date_from, date_to, roll?, tags?, query?) -> list[ClipBrief]`
  —— 包在 `CatalogRepository` 上的检索；`ClipBrief` = `clip_id, roll, capture_time, duration_s, summary/description, tags, has_transcript, has_keyframes`。
- `get_clip_detail(clip_id) -> ClipDetail`
  —— 带回 **transcript 分段**（`Segment(start_s,end_s,text)`，A-roll 主线 in/out 的来源）、已有关键帧切点、元数据。
- `inspect_broll(clip_id) -> VisionResult`
  —— **现场**对该 B-roll 均匀抽帧调 Qwen3-VL 确认画面（复用 07 `VisionTagger` + 03 `FrameExtractor`）。仅在文本元数据不足以定夺时调用。

> **收尾不是工具**：LLM 通过**结构化输出**给出最终 `CutPlan{shots}`；**时长累计与目标区间校验由 Director 用确定性代码完成**，不让 LLM 自由生成时间码以外的算术。

### in/out 时间码来源

- **A-roll 主线**：in/out = 所选 transcript **segment 的边界**（让 LLM 按 segment 序号选段，映射回 `start_s/end_s`，杜绝幻觉时码——沿用 16 关键帧的约束手法）。
- **B-roll 插空**：优先用已生成的**关键帧切点**；没有则取一个窗口（按片段时长给默认跨度），必要时 `inspect_broll` 抽帧确认。关键帧默认不自动生成，分镜阶段按需取。

### 护栏（Director 内，确定性）

- **最大工具轮数** `cut_max_tool_rounds`（默认 24）：超出即用当前草稿收尾，避免不收敛。
- **时长校验**：累计 `sum(out_s-in_s)` 落在 `[target_min_s, target_max_s]`；超/欠区间时把差额回灌让 LLM 增删一轮，仍不达标则**照出**并在分镜表尾**明确标注"未命中目标时长"**。
- **视觉调用预算**：`inspect_broll` 次数 = **Settings 可调用户偏好** `cut_vision_budget`（默认 6；设 `0` = **不限**，由用户按机器性能决定——文本/视觉交替会触发 OMLX 模型换入换出（慢），弱机宜限、强机可放开）；Director 提示 LLM 批量、少调。

### 分镜表格式（纯逻辑 `cutplan/format.py`）

按**章节分组**渲染 markdown：每章一个 `## 章节标题`，下接一张表：

```
# | in–out 时间码 | 时长 | 类型 | 库内文件 | 缩略图 | 内容/台词 | 用途·理由
```

- **缩略图引用**：链接到 clip 缩略图（`/api/clips/{id}/thumbnail`）或所选窗口的关键帧帧图；markdown 图片/相对路径两种形态。
- 表尾给**总时长**与"是否落在目标区间"提示。
- 提供"复制为 Markdown"。这是**本任务测试金矿**（确定性、易断言）。

---

## 数据模型（SQLite 新表）

```sql
CREATE TABLE cut_sessions (
  id           INTEGER PRIMARY KEY,
  title        TEXT,
  request_json TEXT,                 -- 最近一次 RoughCutRequest
  status       TEXT NOT NULL,        -- 'idle'|'running'|'error'
  created_at   TEXT, updated_at TEXT
);

CREATE TABLE cut_messages (
  id         INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
  role       TEXT NOT NULL,          -- 'user'|'assistant'|'tool'
  content    TEXT,
  tool_json  TEXT,                   -- 可选：tool_calls / tool_result 原文
  created_at TEXT
);

CREATE TABLE cut_plans (
  id         INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
  plan_json  TEXT NOT NULL,          -- CutPlan{shots[], total_s, target_*, chapters[]}
  created_at TEXT
);
```

删除会话 → 级联删 messages 与 plans。

---

## 任务清单

### 后端

- [ ] `domain/models.py`：`RoughCutRequest(date_from, date_to, target_min_s, target_max_s, aspect_ratio, style_notes:str)`；`Shot(clip_id, roll, in_s, out_s, content, rationale, chapter, thumb_ref)`；`CutPlan(shots:list[Shot], total_s, target_min_s, target_max_s, chapters:list[str])`；`CutSession`、`ChatMessage`、`ClipBrief`、`ClipDetail`（均 frozen）。
- [ ] `config.py` / prefs：`cut_max_tool_rounds:int=24`、`cut_vision_budget:int=6`（**`0`=不限**，用户偏好，由机器性能决定）、`cut_default_aspect_ratio:str="16:9"`。文本模型复用 `text_model`，视觉复用 `vision_model`。
- [ ] `ports/cutplan.py`：工具接口 `FootageRetriever`（`search_footage`/`get_clip_detail`）、`BrollInspector`（`inspect_broll`）、`LLMAgentClient`（`run_tools(messages, tools) -> AgentStep`，含 tool_calls 或 final content）。
- [ ] `adapters/`：
  - [ ] `sqlite_footage.py`：`FootageRetriever` 包在 `CatalogRepository` 上（日期范围 / 类型 / 标签 / FTS 台词检索 + 带回 segments/keyframes）。
  - [ ] `omlx_agent.py`：`LLMAgentClient` 复用现有 OMLX client（`text_model=Qwen3.6`），用 OpenAI 工具调用协议；宽松解析、容错。
  - [ ] `BrollInspector` 复用 07 `VisionTagger` + 03 `FrameExtractor`（薄封装，无新模型依赖）。
- [ ] `cutplan/format.py`（纯逻辑，无 IO）：`to_shotlist_markdown(plan) -> str`（章节分组 + 上述列 + 缩略图引用 + 时长累计/区间校验尾注）。
- [ ] `cutplan/director.py`（编排，纯逻辑，注入接口）：工具调用环 + 护栏（最大轮数 / 时长校验回灌 / 视觉预算）；`start_session()`、`handle_message(session_id, user_text)`（产 `CutPlan` + 助手回复）；refine 轮把既有 plan + 对话历史作为上下文重跑相关步骤。
- [ ] `adapters/sqlite_repo.py` + `ports/repository.py`：`cut_sessions`/`cut_messages`/`cut_plans` 表 + `create_session / list_sessions / get_session / delete_session（级联）/ append_message / get_messages / save_plan / get_plan`。
- [ ] `pipeline/worker.py`：job kind `cutplan`；`enqueue_cutplan(session_id, user_text) -> job_id` 与 `_process_cutplan`；经 SSE 推**工具活动 + 助手 token + 最终 plan ready** 事件。
- [ ] `api/routes.py`：
  - [ ] `POST /api/cut/sessions` → 新建会话（可选 title）→ session。
  - [ ] `GET /api/cut/sessions` → 列表（id/title/updated_at）。
  - [ ] `GET /api/cut/sessions/{id}` → 消息历史 + 最近 plan。
  - [ ] `DELETE /api/cut/sessions/{id}` → **删除对话**（级联）。
  - [ ] `POST /api/cut/sessions/{id}/messages` → body `{text, request?}` → 入队 `cutplan` job（返回 `{job_id}`，复用 `GET /api/jobs/{id}` + SSE）。
  - [ ] `GET /api/cut/sessions/{id}/plan` → 最近 plan（含 `markdown` 渲染）。
- [ ] `api/schemas.py`：`CutSessionOut`、`CutMessageOut`、`CutPlanOut`、`ShotOut`、`SendMessageRequest`。

### 前端

- [ ] `api/client.ts`：会话 CRUD（含 `deleteSession`）、`sendCutMessage`、`getCutPlan`；相关类型 + SSE 订阅。
- [ ] `features/cutplan`：新页 ——
  - 左：会话列表（可删除）+ 对话框（用户发需求 / 助手回复 / 工具活动指示）。
  - 右：**实时分镜表预览**（按章节分组、每行带缩略图、in–out 时码、台词/画面、理由）+ 表尾总时长/区间提示 + **「复制为 Markdown」**。
  - 进度条复用 SSE 基建；刷新后从 `GET /api/cut/sessions/{id}` 恢复。
- [ ] 导航入口：在 Header/导航加入「初剪 / Rough Cut」。
- [ ] `features/settings`：初剪 Agent 视觉预算 `cut_vision_budget`（数字输入，**`0`=不限**，附"取决于机器性能"说明）；可选暴露 `cut_max_tool_rounds`、默认比例。
- [ ] `i18n`：EN/ZH 文案。

### 测试

- [ ] 单测 `cutplan/format.py`：章节分组 / 列渲染 / 缩略图引用 / 时长累计 / 命中与未命中目标区间尾注；黄金串；空 plan、单章、跨小时时码。
- [ ] 单测 `cutplan/director.py`（**主力**）：注入**假 LLMAgentClient（脚本化 tool_calls 序列）+ 假工具**，断言：
  - A-roll 主线选段走 segment 序号、映射回正确 in/out；B-roll 配空镜分支；
  - 时长护栏：欠/超区间触发增删回灌一轮；仍不达标则标注且照出；
  - 最大工具轮数护栏触发收尾、视觉预算上限生效；
  - refine 轮：第二条用户消息基于既有 plan + 历史重跑、产出新 plan。
- [ ] 单测 `FootageRetriever`：内存 SQLite + 预置编目，日期范围 / 类型 / 标签 / FTS 检索正确，带回 segments/keyframes。
- [ ] 单测 SessionStore：内存 SQLite，会话/消息/plan 往返；**删除会话级联删消息与 plan**。
- [ ] 单测 worker `cutplan` job + API 路由（假 Director），含会话 CRUD、删除、SSE 事件序列。
- [ ] 前端组件测试（Vitest + MSW）：发消息 / 流式回复 / 分镜表渲染（章节+缩略图）/ 复制 Markdown / 删除会话。
- [ ] （集成，手动）真 OMLX + 预置编目（`testVideo/` 那几条素材）→ 生成一版分镜表 → **人工评估"剪得合不合理"**（创意输出无法自动断言）。

---

## 完成标准（DoD）

1. 在对话里说「用 4/25–5/11 的素材剪一条 15–20 分钟、叙事/轻快/有节奏的 vlog，16:9」→ 得到一份**按章节分组、含缩略图、精确到 in/out 的分镜表**，A-roll 主线 + B-roll 插空，可一键复制为 Markdown。
2. **多轮可调**：再说「第 3 段太长 / 这里换个 B-roll / 节奏再快点」→ 基于既有分镜表产出修订版。
3. **会话持久化**：刷新/重开后会话与分镜表仍在；**可删除对话**（级联清消息与 plan）。
4. **护栏可见**：总时长落在目标区间；未命中时分镜表尾明确标注。
5. **硬约束**：全程只读编目与副本，不碰源文件、不渲染、不联网；库里无该日期素材时提示先扫描。
6. `mypy` / `ruff` / `tsc` 干净；新增单测全绿。

---

## 备注 / 风险

- **首要风险：Qwen3.6 本地 function-calling 可靠性**。对策 = 方案 C 的确定性脚手架 + 护栏；若实测工具调用太差，退化为**分阶段受限调用**（检索→列大纲→填段→格式化，每阶段一次受限 LLM 调用），对话层在其上重跑相关阶段——接口不变，只换 Director 内部策略。
- **OMLX 模型换入换出成本**：文本/视觉交替慢 → `inspect_broll` 设预算、批量调用、能少则少。
- **分镜"质量"不可自动化验收**：硬测只覆盖确定性部分（时长/时间码/格式/工具调用契约/会话 CRUD），创意质量靠 eval 清单 + 真机抽查。
- **可与后续 FCP 集成协同**：`CutPlan` 的 in/out 时码后续可导出为 FCPXML 序列 / FCP 标记（本期不做）。
