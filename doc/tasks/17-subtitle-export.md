# 17 字幕导出（独立成片 → Final Cut Pro 字幕：iTT + SRT）

> 依据：[`proposal.md`](../proposal.md) §7 待办、[`detailed-design.md`](../detailed-design.md) §3.13 / §6 / §7、[`progress.md`](./progress.md) 的 FCP 字幕 TODO。
> 与「关键帧」「分类流水线」不同，本功能是一个**独立小工具**，**不入库、不分类、不复制源视频**，只把一段**已剪辑完成的成片**转写成字幕文件供 FCP 导入。

## 目标

用户**单独选一个已剪辑完成的视频**（不一定在素材库里）→ 用 `mlx-whisper` **重新转写**（对齐成片自己的时间轴，**不复用任何已入库 transcript**）→ 导出 **iTT（FCP 原生）+ SRT** 两个字幕文件，**保存到用户用原生对话框选定的文件夹**。字幕语言**跟随 App 的 AI 输出语言设置**（`output_language`），它表示**成片本身的口语语言**：`zh` → Whisper `transcribe`（language=zh）；`en` → Whisper `transcribe`（language=en）。**全程只转写、不翻译**（视频本来就是目标语言）。

### 已确认的决策（来自用户）

| 维度 | 决策 |
|---|---|
| 输入 | 独立成片，**每次重新转写**（忽略库内 transcript） |
| 格式 | **iTT + SRT** |
| 输出位置 | **用户用原生对话框选定的文件夹**（复用/扩展 `pick-folder`） |
| 语言 | **跟随 `output_language`**，即成片口语语言；Whisper `transcribe`（language=zh/en）。**不翻译** |

### 硬约束（继承 proposal）

- **源视频只读**：只读取转写，**绝不修改/重命名源成片**；只在用户选定的输出文件夹里**新建** `.itt` / `.srt`。
- **全本地离线**：转写走本地 `mlx-whisper`，不联网。

---

## 设计要点

- **复用**：`MetadataProbe`（取 `fps`/`duration`）、`Transcriber`（`Transcript{full_text, segments:[Segment(start_s,end_s,text)]}`）、Worker 队列 + SSE、`/api/open`（在 Finder 显示结果）、`output_language` 配置、`pick-folder`。
- **新增**（最小面）：
  - 扩展 `Transcriber`：`transcribe(path, *, language: str | None = None)` —— 把成片口语语言（`output_language`）作为 `mlx_whisper` 的 `language` 提示传入。**只转写、不翻译**，无新增翻译接口。
  - 纯逻辑格式化模块 `subtitle/format.py`：`to_srt(segments)` / `to_itt(segments, *, language, fps)` —— **本任务测试金矿**（确定性、易断言）。
  - 服务 `pipeline/subtitle_exporter.py`：`export(video_path, out_dir, formats, language) -> list[Path]`（注入 probe/transcriber；`language` 同时作为 Whisper 提示与字幕 `xml:lang`）。
  - Worker job kind `subtitle`；payload 为 `SubtitleRequest{video_path, out_dir, formats, language}`。
  - API：`POST /api/subtitles/export`（→ `job_id`，复用 `GET /api/jobs/{id}` + SSE）、`POST /api/pick-file`（原生选文件）、`GET /api/subtitles/{job_id}`（取产出路径，供刷新后恢复）。
  - 前端 `features/subtitles`：选视频 / 选输出文件夹 / 勾选格式 / 显示语言来源 / 进度条 / 完成后列出产出文件 + 「在 Finder 中显示」。
- **iTT 决策**：TTML，`ttp:timeBase="media"`，时间用 `HH:MM:SS.mmm` 时钟码，`xml:lang` 取目标语言。`fps` 读取备用（如需切 smpte 帧码）。**验收必须真机导入 FCP 验证**。
- **语言**：`output_language` 即成片口语语言，作为 Whisper 的 `language` 提示直接转写；**本期不做任何翻译**（若将来要把中文成片导出英文字幕，再引入 Whisper translate 或文本模型翻译）。
- **产出命名**：`<视频名>.<lang>.itt` / `<视频名>.<lang>.srt`（如 `MyEdit.zh.srt`），同名不覆盖（追加序号）。

---

## 任务清单

### 后端

- [ ] `domain/models.py`：`SubtitleRequest`（frozen：`video_path, out_dir, formats:list[str], language:str`）；可选 `SubtitleResult`（产出路径列表）。
- [ ] `config.py` / prefs：可选 `subtitle_default_formats: list[str] = ["itt","srt"]`（仅作 UI 默认；语言不另存，直接读 `output_language`）。
- [ ] `ports/speech.py` + `adapters/mlx_whisper.py`：`Transcriber.transcribe` 增加 `language: str | None=None`，透传给 `mlx_whisper` 的 `language` 提示（不传则保持现状/自动检测）。
- [ ] `subtitle/format.py`（纯逻辑，无 IO）：`to_srt(segments) -> str`、`to_itt(segments, *, language, fps) -> str`；时码格式化 `HH:MM:SS,mmm`（SRT）/ `HH:MM:SS.mmm`（iTT）；XML 转义。
- [ ] `pipeline/subtitle_exporter.py`：`export(...)` —— probe(fps) → transcribe(language) → 按 `formats` 写文件 → 返回路径；逐步错误隔离（失败记错误、不抛）。
- [ ] `adapters/`（写文件）：在选定 `out_dir` 写入，同名不覆盖；**绝不碰源视频**。
- [ ] `pipeline/worker.py`：job kind `subtitle`；`enqueue_subtitle(req) -> job_id`（`create_job(total=1, kind="subtitle")`）与 `_process_subtitle`；产出路径存入可由 `GET /api/subtitles/{job_id}` 读取的（内存）结果存储，避免改 DB schema。
- [ ] `api/routes.py`：
  - [ ] `POST /api/subtitles/export`：body `{video_path, out_dir, formats?, language?}`（`language` 缺省取 `output_language`）→ `{job_id}`。
  - [ ] `POST /api/pick-file`：原生 `choose file`（视频类型过滤）→ `{path}`；非 macOS 返回 501（对齐 `pick-folder`）。
  - [ ] `GET /api/subtitles/{job_id}`：返回该 job 的产出文件路径（完成后）。
- [ ] `api/schemas.py`：`SubtitleExportRequest` / `SubtitleExportResponse`（job_id）/ `SubtitleResultOut`（paths）。

### 前端

- [ ] `api/client.ts`：`pickFile()`、`exportSubtitles(req)`、`getSubtitleResult(jobId)`；相关类型。
- [ ] `features/subtitles`：新页/弹窗 —— 「选择视频…」(`pick-file`) + 「选择输出文件夹…」(`pick-folder`) + 格式勾选（iTT/SRT，默认两者）+ 语言来源说明（跟随 AI 输出语言）+「导出」按钮 → 订阅 SSE 进度 → 完成后列出产出文件 + 「在 Finder 中显示」(`/api/open`)。
- [ ] 导航入口：在 Header/导航加入「字幕导出」。
- [ ] `i18n`：EN/ZH 文案。

### 测试

- [ ] 单测 `subtitle/format.py`：SRT/iTT 黄金串；时码边界（亚秒、跨小时、0 时长）；XML 转义；空分段。
- [ ] 单测 `subtitle_exporter`：注入假 probe/transcriber —— 断言把 `language`（zh/en）透传给 transcribe、按 formats 产出、命名/不覆盖、`xml:lang` 正确。
- [ ] 单测 worker `subtitle` job + API 路由（假队列/假服务）。
- [ ] 前端组件测试：选文件/选目录/导出/进度/产出列表与 Reveal。
- [ ] （集成，手动）真 `mlx-whisper` 跑一段短成片 → 真 iTT → **导入 Final Cut Pro 验证**（字幕轨正确、时码对齐）。

---

## 完成标准

1. 选一段已剪辑成片 → 选输出文件夹 → 导出，得到 `<名>.<lang>.itt` 与 `<名>.<lang>.srt`，时间轴对齐该成片。
2. 字幕语言跟随 `output_language`：`en` 成片转写为英文、`zh` 为中文；**全程不翻译**，`xml:lang` 标注正确。
3. 源视频始终未被修改/重命名；仅在选定文件夹新建文件，同名不覆盖。
4. iTT **真机导入 Final Cut Pro 成功**，显示为字幕轨。
5. `mypy` / `ruff` / `tsc` 干净；新增单测全绿。
