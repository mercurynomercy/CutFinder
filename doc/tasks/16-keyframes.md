# 16 · 关键帧推荐（剪辑切点 + 精选帧）

> 需求 8。为每段素材推荐 **最多 N 个**（默认 3，可配置）排序的**剪辑切点 + 代表帧**。
> **依赖**：05（transcript）、06（文本模型）、07（视觉模型）、03（ffmpeg 抽帧）、09（仓储）、11（编排）、12（队列）、13（API）、14（前端）。
> **位置**：后端 `domain/`、`ports/`、`adapters/`、`pipeline/`、`api/`；前端 `features/detail`、`features/settings`。

---

## 设计概要

每段素材产出**最多 N 条**排序建议（rank 1 最佳）。一条建议 =

```
CutSuggestion(rank:int, start_s:float, end_s:float, reason:str,
              frame_path:str|None, source:str)   # source ∈ {"text","vision"}
```

- `start_s/end_s`：建议保留的 in/out 时间窗（秒）。
- `reason`：一句话理由（按 AI 输出语言 zh/en）。
- `frame_path`：代表帧 JPEG，存于 `<库>/.cutfinder/keyframes/<clip_id>/k{rank}.jpg`（相对路径入库）。
- `source`：`"text"`（A-roll，基于 transcript）或 `"vision"`（B-roll，基于 VL 模型）。

### 生成方式（按 A/B 分流）

- **A-roll —— 文本模型（复用 Qwen3.6 / OmlxSummarizer 的 client）**：
  已存的转写是带时间轴的 `Segment(start_s, end_s, text)`。把**编号后的** segment 列表喂给模型，要求它**按 segment 序号**选出最佳 N 段（不让模型自由生成时间码，避免幻觉），再由序号映射回 `start_s/end_s`。代表帧 = ffmpeg 在该窗口**中点**抓一帧。
  - 无 transcript（如 A-roll 但转写为空/失败）时：跳过并标记，不强行走视觉。
- **B-roll —— 视觉模型（复用 Qwen3-VL / OmlxVisionTagger 的 client）**：
  在片段上**均匀采样约 12 帧**（内部默认，每帧标注时间戳），交给 Qwen3-VL，要求按画面质量返回 top N（含理由）。每个 pick 的帧即代表帧；in/out 窗口取该帧附近一个小跨度（按采样间隔，端点 clamp 到 [0, duration]）。
  - 备注（已知局限）：B-roll 切点粒度受采样密度限制，偏粗。

### 运行时机（混合）

- 新增队列 job kind **`keyframes`**（与 `scan` / `reanalyze` 并列）。
- **扫描后自动**（默认开，设置可关）：scan job 完成后，对**本次新入库**的片段入队一个 `keyframes` job。
- **按需**：详情面板「推荐关键帧」按钮对单片段入队（同 reanalyze 模式）。重跑**覆盖**旧建议。

---

## 子任务

### 后端
- [ ] `domain/models.py`：新增 `CutSuggestion`（frozen）。
- [ ] `config.py` / prefs：新增 `keyframe_count:int=3`、`keyframe_auto:bool=True`。（B-roll 采样密度先用内部默认 ~12，暂不暴露为设置。）
- [ ] `ports/media.py`：`FrameExtractor` 增加 `grab_at(path, seconds, out_path) -> Path`（ffmpeg seek 抓单帧）。
- [ ] `ports/ai.py`：新增关键帧推荐能力——
  - 文本：`recommend_cuts_from_segments(segments, n) -> list[CutSuggestion]`（仅 start/end/reason/rank，frame 后填）。
  - 视觉：`recommend_keyframes(frames_with_ts, n) -> list[CutSuggestion]`。
- [ ] `adapters/`：在 `omlx_text.py` / `omlx_vision.py` 实现上述方法（复用现有 OMLX client、宽松 JSON 解析）；`ffmpeg_media.py` 实现 `grab_at`。
- [ ] `pipeline/orchestrator.py`：`recommend_keyframes(clip_id) -> bool`——按 A/B 分流→生成建议→抓帧→持久化；逐步错误隔离（失败不抛、记 status）。
- [ ] `adapters/sqlite_repo.py` + `ports/repository.py`：`keyframes` 表 + `save_keyframes / get_keyframes / clear_keyframes`；随 clip 级联删除；删除 clip 时一并清理帧文件目录。
- [ ] `pipeline/worker.py`：新增 `enqueue_keyframes(clip_ids, job_id?)` 与 `_process_keyframes`；job kind `keyframes`。scan job 终态完成后，若 `keyframe_auto` 则对新片段入队 keyframes job。
- [ ] `api/routes.py`：
  - `POST /api/clips/{id}/keyframes` → 入队单片段 keyframes job（返回 `{job_id}`）。
  - `GET /api/clips/{id}` 详情响应增加 `keyframes: [...]`。
  - `GET /api/clips/{id}/keyframes/{rank}/image` → 返回帧 JPEG，`Cache-Control: no-store`。
- [ ] `api/schemas.py`：`CutSuggestionOut`；并入 `ClipDetailResponse`。

### 前端
- [ ] `api/client.ts`：类型 `CutSuggestion`；`suggestKeyframes(id)`；详情含 `keyframes`。
- [ ] `features/detail`：新增「Suggested cuts / 剪辑建议」区——每条 = 帧缩略图 + `mm:ss–mm:ss` + 理由；点击帧用默认播放器打开视频。新增「推荐关键帧」按钮 + loading 态；重跑后刷新。
- [ ] `features/settings`：关键帧数量（可配置上限）+「扫描后自动推荐」开关。
- [ ] `i18n`：EN/ZH 文案。
- [ ] （v1 暂不做）画廊卡片「已有建议」标记。

---

## 完成标准（DoD）

- **后端单测（注入 fakes）**：
  - A-roll：给定带 segments 的 transcript，编排调用文本推荐 → 持久化 N 条建议、source=`text`、start/end 落在 segment 边界内、为每条抓了代表帧。
  - B-roll：给定采样帧 → 调用视觉推荐 → 持久化 N 条、source=`vision`。
  - `keyframe_count` 改变上限生效；无 transcript 的 A-roll 优雅跳过（不抛）。
  - 仓储：save/get/clear 往返；clip 删除级联删 keyframes 与帧目录。
  - worker：`keyframes` job 计数/终态正确；scan 完成后 `keyframe_auto=True` 自动入队、`False` 不入队。
  - API：`POST …/keyframes` 入队；详情含 keyframes；图片端点 `no-store`。
- **前端**：详情面板渲染建议列表（缩略图+时码+理由）、`vitest` 通过、`tsc` 干净。
- `ruff` / `mypy`（strict 现状）不新增告警。

---

## 备注 / 风险

- 文本模型按 **segment 序号**选段（而非自由时间码）是关键设计——把输出约束到已知区间，杜绝幻觉时间。
- B-roll 切点粒度受采样密度限制；如需更精细可后续提高采样或加场景检测（`ffmpeg select='gt(scene,…)'`）。
- 关键帧 job 是最贵的一步（A-roll 多一次文本调用、B-roll 视觉判多帧）——故默认放到扫描之后单独排队，不拖慢扫描。
- 帧文件随 clip 删除清理；重跑覆盖（先 clear 再 save）。
- 可与「FCPXML / 字幕导出」TODO 协同：切点时码后续可导出为 FCP 标记/区间。
