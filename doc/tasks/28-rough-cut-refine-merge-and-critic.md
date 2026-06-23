# 28 · 初剪 refine 按日期合并 + 审片 critic agent

> **状态：planned（设计已确认，待执行）。** 两件事共用同一套"重做指定日期 → 并入已有 plan"的机制，合并为一个任务：
> ① **修 refine bug**：多轮对话里"增加/重做某天"应**并入**已有分镜表，而不是整体替换；
> ② **v2 审片 critic agent**：全片拼好后由 critic 检查主观质量（节奏/叙事连贯/A-B 配比），让对应日期的 worker 修一轮。
>
> **依赖**：26（按天 mini-agent）、27（实时进度 + 部分 plan）。
> **位置**：后端 `cutplan/director.py`、`pipeline/cutplan_service.py`（+ critic：可能新增 `cutplan/critic.py`）。
> **为什么合在一起**：两者都是"在已有 plan 上按日期迭代"。critic 的"把 5/3 那天剪紧一点"= 重做 5/3 章节并合并——正是 refine 合并的机制。

---

## 背景：refine 现在是"整体替换"，不是"增量改"

实测 bug（2026-06-23）：
- 第 1 轮"用 4/25–5/11 剪 vlog"→ 生成了除 5/11 外的各天（5/11 当轮失败、被跳过）。
- 第 2 轮"增加一份 2026-05-11 的进去"→ **结果只剩 5/11**，之前各天全没了。

根因链条（与"确定性检索"直接相关）：
1. `generate()` 第一步**确定性检索**按日期范围捞素材（模型不参与）。
2. refine 句子里的"2026-05-11"被 `request_parse._parse_dates` 解析成 `date_from=date_to=5/11`，**覆盖**了记忆里的 4/25–5/11（`cutplan_service.py:62-64`）。
3. → 检索这次只捞到 5/11 → 只重生成 5/11。
4. → 重建的 plan 只有 5/11，`save_plan` **覆盖**旧 plan → 其它日期丢失。（task 27 的逐天部分落库也是覆盖式，refine 中途同样会冲掉旧日期。）

## Part A — refine 按日期合并（已确认方案）

把 plan 当成"按日期分章的字典"，refine 时**以旧 plan 为基底，只覆盖本轮重生成的日期、保留其它日期**。

**改动**
1. `director.generate(..., prior_plan: CutPlan | None = None)`：
   - 用 `merged: dict[日期, list[shot_dict]]`，**先用 `prior_plan` 的 shots 按 chapter(日期) 填充**做基底。
   - 本轮每个日期**成功**生成 → `merged[日期] = 新 shots`（覆盖该天）；**失败** → 保留旧那天（不再丢）。
   - partial（27 的逐天落库）和最终 plan 都用 `flatten(merged)` **按日期排序**后再 `_build_plan` → 时间线不乱、refine 中途不闪掉旧日期。
   - 失败提示只报"既没生成、又无旧版本可留"的日期。
   - 边界：refine 缩到一个**无素材**的日期 → 不清空，保留旧 plan 并提示。
2. `cutplan_service.handle`：调用前 `prior = store.get_latest_plan(session_id)`，传 `prior_plan=prior`。
3. 小工具 `_shot_to_dict(Shot)`：旧 Shot 转回 dict 复用 `_build_plan` 的钳位/总时长/校验。

**三种 refine 都对**：增加一份 5/11 → 并入；5/3 重弄 → 只换 5/3 章节；整体节奏快点（无日期 → 全程范围）→ 全部重做替换。

**不改**：日期解析逻辑（"改窄范围"在合并语义下正是"圈定本次重做哪些天"，是对的）；`_build_plan` 的钳位/总时长。

## Part B — 审片 critic agent（v2）

时长校验已是确定性的，critic 专管**主观质量**：节奏松紧、叙事连贯、A-roll 主线 / B-roll 配比、空镜是否缺位。

**流程**
1. 主编排（确定性 Python）拼好全片后，把"按日期分章的分镜摘要"（每镜 roll/时长/台词或画面/章节）喂给一个 **critic LLM 调用**。
2. critic 输出**结构化修订意见**，按日期定位：如 `{"date": "2026-05-03", "issue": "节奏拖沓", "action": "剪短前两镜"}`、`{"date": "2026-04-25", "issue": "缺空镜衔接", "action": "在第3镜后补一条 B-roll"}`。
3. 主编排对**被点名的日期**调用 Part A 的"重做该日期 → 并入"机制（把 critic 意见作为额外指令拼进那天的 user prompt），修一轮。
4. 收口：最多 1 轮 critic（避免来回拉锯/延迟膨胀）；critic 不动时长校验（仍由确定性代码兜底）。

**开关 & 代价**：默认**关**（`cut_critic_enabled`，或并入 `cut_director_mode` 增加 `"agent+critic"`）；多一轮 LLM + 被点名日期重做，延迟增加。本地模型 critic 的结构化输出同样走宽松 JSON 解析 + 失败则跳过（不阻断出片）。

**复用 Part A**：critic 的"重做 5/3 并入"与 refine 的"重做 5/3 并入"是同一条代码路径——这正是合并做的理由。

## 验收

- [x] 单测（A）：prior 有 4/25、4/26，本轮范围只 5/11 → 结果含三天、按日期排序、4/25 shots 保留；失败的天若有旧版本则保留、不进"已跳过"提示；service 把 `get_latest_plan` 作为 `prior_plan` 传入。
- [x] 单测（B）：fake critic 返回点名某日期 + action → 该日期被重做并合并；critic 返回空/坏 JSON → 跳过、原 plan 不变。
- [ ] 真机：refine"增加一份 X"得到完整表；开启 critic 后某拖沓日期被剪短。（待手动验收）
- [x] mypy / ruff 干净。

## 备注
- 无前端改动（前端轮询读合并后的 plan 即可）；critic 阶段可复用 27 的进度串（"正在审片…/重做 2026-05-03…"）。
- 仍是"确定性 Python 编排 + LLM 只做创意/评审"，不让 LLM 自己 spawn agent（继承 26 哲学）。
