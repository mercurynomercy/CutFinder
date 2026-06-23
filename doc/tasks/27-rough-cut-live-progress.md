# 27 · 初剪实时进度 + 部分分镜先显示

> **状态：代码实现完成 + 自动测试通过，真机验收待手动。** 在 26 的按天 mini-agent 之上，把"导演正在生成…"
> 升级为**逐天/逐片段的实时状态**，并让**已完成日期的分镜先显示在分镜表**、其余标注"生成中"。
>
> **依赖**：26（按天 mini-agent，进度回调挂在每天/每个工具调用上）。
> **位置**：后端 `cutplan/director.py`、`pipeline/cutplan_service.py`、`adapters/sqlite_cutplan.py`、`domain/models.py`、
> `ports/cutplan.py`、`api/cut_routes.py`、`api/schemas.py`；前端 `features/cutplan/index.tsx`、`api/client.ts`、`i18n`。

---

## 背景

26 之前，`_process_cutplan` 只发 `cutplan_started` / `cutplan_done` 两个事件，中间无进度；`generate()` 跑完所有天
才一次性 `save_plan`。所以 UI 只能显示一个静态的"导演正在生成…"，且全部完成前看不到任何分镜。

## 关键决策

- **粒度：到"查看哪个 clip"级**（用户选定）。事件如 `第 2/6 天（2026-04-25）· 查看片段 #123 台词`。
- **不引入 SSE / 线程桥接。** `cutplan_service.handle` 整个跑在 `asyncio.to_thread` 里，本来就在往 SQLite store 写；
  前端已是**轮询** `getCutSession`。所以让 director 把"进度字符串 + 部分 plan"写进 store，轮询天然增量读到——比 SSE 干净得多。
- **进度字符串是临时态**：存 store 的**内存映射**（不落库、不做 schema 迁移），重启即清（中断的会话本就重置为 idle）。

## 已落地

**后端**
- `CutSession.progress: str`（仅读时从内存映射填充，不持久化）。
- `SqliteCutSessionStore`：内存 `self._progress` + `set_session_progress` / `clear_session_progress`，`get_session` 填充 progress；
  `MemoryCutSessionStore` 继承即得。`CutSessionStore` 协议同步加这两个方法。
- `CutDirector.generate(..., on_progress, on_partial)`：每天开始/完成发进度串；每查看一个 clip 经 `_run_day(on_step=...)` 发
  `查看片段 #N 台词|画面`；**每天结束用累积 shots 建一次部分 plan 经 `on_partial` 发出**。
- `CutPlanService.handle`：`on_progress → store.set_session_progress`、`on_partial → store.save_plan`；turn 结束/出错 `clear_session_progress`。
- `cut_routes._session_dict` 带 `progress`；`PrefsOut`/`SettingsUpdate` 无关。

**前端**（沿用轮询，无 SSE）
- `CutSession.progress?` 类型字段。
- `resumePoll` 改为**先轮询再 sleep**，每个 tick：有 plan 就 `setPlan`（已完成日期先显示）+ `setProgress(session.progress)`（实时状态）；
  非 running 时定稿。`send` 改用 `resumePoll`（路由同步置 running，无竞态），删除旧的 `waitForJob`。
- 聊天气泡显示 `progress || roughcut.thinking`；分镜表上方在 busy 时显示一条"`部分日期已生成，其余仍在继续…`"横幅（`roughcut.partialGenerating`，中英）。

## 测试

- 后端 +1 service 单测（partial plan 落库 + progress 结束清除）；`FakeDirector` 支持脚本化 progress/partial。后端 526 全绿、ruff/mypy 干净。
- 前端：cutplan 6/6 通过（resume mock 调整为前两次轮询仍 running，给 thinking 真实窗口）。
  （settings/gallery 3 个失败为**既有**、与本任务无关。）

## 验收（手动）

- [ ] 真机跑多日初剪：聊天区滚动显示"第 k/N 天 · 查看片段 #X …"；分镜表随每天完成增量出现，顶部横幅提示生成中；全部完成后横幅消失、状态清空。

---

## 后续增强（待做）：更丰富的进度 UI，看清导演"思考到哪一步"

当前只有一行替换式状态（"正在生成第 1/6 天（2026-04-25）…"）。用户希望**信息更多、能看到思考轨迹**。

**后端：发更多、更具体的进度事件**（`director.py` 的 `on_progress` / `_run_day` `on_step`）：
- **检索阶段**：开头补 "正在检索 4/25–5/11 的素材…" → "找到 N 个片段、共 M 天"（现在这步无任何提示）。
- **每天起始**带素材数：" 正在生成第 k/N 天（date）· 本天 X 个片段"。
- **工具调用带 clip 标签/内容**而非仅 `#id`：" 查看片段 A-0002.MP4 的台词" / " 查看 B-0001.MP4 的画面"（需把 clip_label/摘要传进 step 文案）。
- **导演思路**：agent loop 里模型在工具调用之间常输出 reasoning 文本（`step.content`），截断后作为 " 导演思路：…" 透出，让用户看到"在想什么"。
- **收口/回落**：" 正在编排第 k 天的分镜…"、" 第 k 天改用快速生成…"（staged 回落）。
- （配合 28）critic 阶段：" 正在审片…" / " 重做 2026-05-03（节奏拖沓）…"。

**前端：从"单行替换"改成"最近几步的滚动轨迹"**（`features/cutplan/index.tsx`）：
- 保留**最近 ~5 条**进度为一个小列表（最新一条带动画点），让用户看到思考链，而不是只有当前一行；其余历史可折叠。
- 需把 `progress: string` 升级为 `progress: string[]`（或前端累积），后端仍可只发最新串、前端 append 去重；或后端直接发结构化事件（type+text）。
- 仍走轮询：每个 tick 读到的新进度串 push 进列表（去重相邻重复）。

> 注意：进度串是临时态、轮询粒度 ~1.5s，比模型实际步进慢；"滚动轨迹"能弥补轮询漏掉的中间步（每 tick 只取到最新一条，append 即可累积可见历史）。
