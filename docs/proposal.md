# CutFinder 需求文档

> 一个本地运行的视频素材（footage）智能分类与检索工具，灵感来自 [Argus](https://github.com/discoposse/argus)。
> 面向个人 Vlog 创作者：自动区分 A-roll / B-roll、为 A-roll 生成中文简介、按日期与类型分类、打标签、生成缩略图，方便日后快速找回素材。

- **版本**：v1（需求文档）
- **日期**：2026-06-27
- **平台**：macOS（Apple Silicon），配合 Final Cut Pro 工作流
- **运行形态**：本地 Web App（浏览器打开 `localhost`），原生 macOS `.app` 外壳；全程离线，AI 全本地
- **详细设计**：模块划分、接口、数据模型、测试与部署见 [`docs/detailed-design.md`](./detailed-design.md)

---

## 1. 背景与目标

我有大量日常 Vlog 素材，分两类：

- **A-roll**：有人出镜/解说的镜头，通常带**中文解说**。
- **B-roll**：纯画面、无解说的空镜。

素材越积越多，靠人工找内容很慢。本工具的目标：**自动分析、分类、打标签、生成缩略图与简介**，让我之后能按日期 / 类型 / 标签 / 台词快速定位到任意一段素材。

### 核心设计原则

1. **原文件只读，绝不破坏**：所有整理动作只发生在「复制出来的新素材库」里。
2. **拍摄时间永不改变**：视频内嵌的 QuickTime / EXIF 拍摄时间全程不被修改，复制时同时保留文件系统的修改时间（`shutil.copy2`）。
3. **全本地、离线**：不上传任何素材到云端，所有 AI 推理在本机完成。
4. **幂等可重跑**：再次扫描只处理新文件，已处理的按文件指纹跳过，不重复复制。

---

## 2. 用户需求清单（对应原始需求 0–8）

| # | 需求 | v1 状态 | 说明 |
|---|------|:--------:|------|
| 0 | 可自定义 footage 文件夹 | ✅ 已实现 | 用户指定「源文件夹」与「目标素材库文件夹」，支持多个源目录 |
| 1 | 拍摄时间不被改变 | ✅ 已实现 | 原文件只读；复制保留内嵌时间与文件时间（`copy2`） |
| 2 | 自动分析 A-roll / B-roll | ✅ 已实现 | Silero VAD 人声检测自动判定，可手动纠正并记住（`roll_source='manual'`） |
| 3 | A-roll 生成内容简介（中文） | ✅ 已实现 | Whisper / Qwen3-ASR 转写 → Qwen3.6 文本模型总结 |
| 4 | 按拍摄日期 + A/B-roll 自动分类到目录 | ✅ 已实现 | 目录结构 `库/日期/A-roll(或 B-roll)/`，重名自动加序号 |
| 5 | 标签标记素材内容 | ✅ 已实现 | AI 自动生成 + 用户手动增删，来源可区分（auto vs manual） |
| 6 | 素材缩略图生成与浏览墙 | ✅ 已实现 | ffmpeg 抽代表帧，存储于 `.cutfinder/thumbnails/`；支持照片（HEIC/JPG/PNG） |
| 7 | 接本地 MLX / OpenAI 兼容接口 Qwen3.6/视觉模型 | ✅ 已实现 | A-roll 文本总结、B-roll 画面识别均走 OMLX（`localhost:8000/v1`） |
| 8 | 关键帧（keyframe）建议 | ✅ 已实现 | 复用 B-roll 视觉模型，为每段素材推荐最佳切点；详情面板 + 画廊角标展示 |

---

## 3. 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 运行形态 | 本地 Web App（浏览器访问 `localhost`）；原生 macOS `.app` 外壳（Swift/AppKit + WKWebView 内嵌前端，已实现） | AI/视频工具链最顺；Dock 生命周期、签名公证完整支持 |
| 模型服务 | [OMLX](https://github.com/jundot/omlx)（本地推理服务器，OpenAI 兼容） | 同一个接口同时托管文本与视觉模型，内置 LRU/pin/TTL 内存管理 |
| 后端 | Python + FastAPI（`backend/cutfinder/`） | 视频与 AI 生态最全，模块通过 `Protocol` 接口隔离可测 |
| 数据库 | SQLite（单文件，存于 `<库>/.cutfinder/catalog.sqlite`），含 FTS5 全文搜索 | 零配置、易备份；FTS5 支持按转写文本 + 画面描述全文检索 |
| 前端 | Vite + React + Tailwind CSS + shadcn/ui（`frontend/`） | 缩略图墙 + 多维筛选 / 搜索；深色 UI，详情面板右抽屉 |
| 进度反馈 | `asyncio.Queue` + Worker 后台队列 + SSE 事件流 | 批量处理时实时推送逐个进度，刷新页可恢复断点（resumePoll） |
| 视频处理 | ffmpeg / ffprobe + Pillow（照片分析） | 抽帧、缩略图、读取元数据；HEIC/JPG/PNG 照片入库 |
| 测试 | pytest + Vitest / RTL + Playwright E2E | 外部依赖接口抽象，单元测试无真实模型可秒级跑完；集成测试打 `@pytest.mark.integration` |
| 环境/部署 | mise + uv + Brewfile + Makefile（Docker 不适用：MLX 需 Metal） | `make setup` 一键安装，换机免折腾；首次启动自动装齐本地依赖 |

### AI 模型（全本地）

| 用途 | 模型 | 运行方式 |
|------|------|---------|
| 人声检测（A/B 判定） | Silero VAD（轻量） | `adapters/silero_vad.py`，本地推理独立进程；阈值默认 0.35（可配置） |
| 人声分离（转写前去 BGM） | **Demucs** `htdemucs`（约 80 MB） | `adapters/demucs_separator.py`，本地 torch/MPS；A-roll 流水线可选开关 `vocal_separation`（默认关），字幕导出强制分离 |
| 中文语音转写（A-roll） | `mlx-whisper` large-v3 / **Qwen3-ASR** + ForcedAligner | 双引擎，`transcription_engine` 偏好切换（默认 `whisper`）；不走 OMLX，独立本地进程 |
| A-roll 简介 + 标签（文本总结） | **Qwen3.6-35B-A3B**（文本 MoE） | OMLX `/chat/completions`，结构化输出 `{summary, tags}` |
| B-roll 画面识别 + 标签 | **Qwen3-VL-8B**（视觉） | OMLX 同一接口换 `model` 名，base64 发帧；结构化输出 `{description, tags}` |

> **模型分工**：`Qwen3.6-35B-A3B` 是文本模型，只看文字；`Qwen3-VL-8B-Instruct` 是视觉模型，专门「看」画面。两者由 OMLX 同时托管，通过同一 OpenAI 兼容接口、用不同 `model` 名调用。OMLX 负责模型的加载/卸载与内存管理（LRU 淘汰、pin、按模型 TTL）。

---

## 4. 处理流水线

```
用户配置：[源文件夹] + [目标素材库文件夹]
        │
        ▼
  扫描视频/照片文件（.mov/.mp4/.m4v/.heic/.jpg 等）
  └─ sha256 文件指纹去重，已处理的跳过
        │
        ▼
  ffprobe/Pillow 读元数据（拍摄日期/时长/分辨率/编码）
  ffmpeg/Pillow 生成缩略图（代表帧偏中部 / JPEG from HEIC）
        │
        ▼
  ┌────── Silero VAD：检测是否有人声解说 ──────┐
  │                                            │
  有人声 (A-roll)                        无人声 (B-roll)
   ▼                                      ▼
(可选 Demucs 去 BGM → )               ffmpeg 均匀抽若干帧（默认5）
mlx-whisper / Qwen3-ASR 转写中文全文          ▼
▼                                   Qwen3-VL 给帧打「标签+描述」(OMLX)
Qwen3.6 生成「简介+标签」(OMLX)           │
  │                                       │
  └───────────────┬───────────────────────┘
                  ▼
   写入 SQLite（元数据/类型/简介/标签/转写全文/缩略图路径）
                   ▼
   复制原文件到：库/YYYY-MM-DD/A-roll(或 B-roll)/原文件名
   （保留内嵌拍摄时间与文件时间，原文件不动）
```

**关键特性：**
- **幂等重入**：开始处理前再次检查指纹，已 `done` 的跳过。
- **错误隔离**：任一步骤失败 → 该片段 `status=error`，整批继续。
- **重新分析**：单段素材可一键 re-analyze（换模型或结果不佳时重跑 AI），保留手动纠正与标签，不重新复制原文件。

---

## 5. 分类、标签与浏览

### 5.1 分类目录结构

```
<素材库>/
├── 2026-06-13/
│   ├── A-roll/
│   │   └── clip_001.mov
│   └── B-roll/
│       └── clip_002.mov
├── 2026-06-14/
│   └── ...
├── .cutfinder/
│   ├── catalog.sqlite        # 数据库（含 FTS5）
│   └── thumbnails/           # 缩略图文件
```

- **日期来源**：取自视频内嵌拍摄时间（QuickTime `creation_time` / EXIF）；无内嵌时间则回退到文件创建时间，UI 标注「日期来源不确定」。
- **同名冲突**：自动追加序号 `(1)`、`(2)`，不覆盖已有文件。
- **照片支持**：HEIC/JPG/PNG 等静态图片作为 `photo` roll 类型入库，缩略图为 JPEG。

### 5.2 标签来源

- **AI 自动生成**：A-roll 来自转写文本总结；B-roll 来自视觉模型画面识别。
- **用户手动增删**：详情面板可编辑标签，`source='manual'` 的在 re-analyze 时保留。
- UI 可区分标签来源（auto vs manual）。

### 5.3 浏览与检索（前端）

- **缩略图墙**：每段素材一张代表帧，分页/虚拟滚动。
- **多维筛选**：按日期 / A-B-roll 类型 / 标签组合过滤。
- **全文搜索**：A-roll 可按转写台词全文搜；B-roll 按画面描述/标签搜（SQLite FTS5）。
- **详情面板**：右抽屉展示简介、可编辑标签（区分来源）、转写全文/画面描述、元数据、库内路径。
- **重新分析**：单段素材一键重跑 AI，保留手动纠正与标签。

---

## 6. 配置项

配置分两类来源：**密钥/端点走全局配置或 OS env**（不进 git），**用户偏好走 JSON**（`<库>/.cutfinder/config.json`）。

### 全局配置 / OS env vars（密钥/端点）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OMLX_BASE_URL` | 空（可设在 `~/.cutfinder/config.json`） | OMLX 接口地址，可在 Settings UI 中设置 |
| `OMLX_API_KEY` | **必填**，无默认值 | OMLX 鉴权密钥；缺失时启动不报错但 AI 分析不可用 |

### JSON 偏好设置（`<库>/.cutfinder/config.json`）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `source_folders` | 空列表 | 源文件夹路径，可多个 |
| `library_path` | 空（必填） | 复制目标素材库根目录；保存时校验非空 |
| `text_model` | `Qwen3.6-35B-A3B` | A-roll 简介/标签用的文本模型名（空则用默认） |
| `vision_model` | `Qwen3-VL-8B`（空则用默认） | B-roll 画面识别用的视觉模型名（量化等级在 OMLX 侧选择） |
| `whisper_model` | `mlx-community/whisper-large-v3-mlx` | mlx-whisper 模型档位（独立于 OMLX） |
| `transcription_engine` | `whisper` | 转写引擎选择：`whisper`（mlx-whisper）或 `qwen`（Qwen3-ASR + ForcedAligner），机器全局 |
| `qwen_asr_model` | `mlx-community/Qwen3-ASR-1.7B-8bit` | Qwen3-ASR 模型名（机器全局） |
| `qwen_aligner_model` | `mlx-community/Qwen3-ForcedAligner-0.6B-8bit` | ForcedAligner 模型名（机器全局） |
| `qwen_max_chunk_s` | `60.0`（上限 300） | Qwen-ASR VAD 分块最大秒数，受对齐器约 400s 时间戳范围限制 |
| `extensions` | `.mov .mp4 .m4v` | 视频扫描白名单扩展名 |
| `photo_extensions` | `.jpg .jpeg .png .heic` | 照片扫描白名单扩展名，作为 `photo` roll 类型入库 |
| `broll_frame_count` | `5` | B-roll 均匀抽帧数量，可配置（默认 5） |
| `vad_threshold` | `0.35`（范围 0–1） | Silero VAD speech_ratio 判定阈值，≥此值判 A-roll |
| `output_language` | `zh` | AI 简介/描述语言（中文），字幕导出也沿用此值 |
| `ui_language` | `en` | 界面语言（EN/ZH），初剪导演默认 Prompt 与进度文案按此切换；机器全局 |
| `keyframe_count` | `3`（上限 10） | 每段素材推荐的关键帧数量 |
| `keyframe_auto` | `false` | 扫描完成后自动请求关键帧分析；默认关（最耗时的步骤） |
| `vocal_separation` | `false` | A-roll 转写前是否用 Demucs 去 BGM；仅影响之后 scan 的新片。字幕导出强制分离 |
| `subtitle_default_formats` | `["itt","srt"]` | 字幕导出 UI 默认格式选项 |
| `cut_director_mode` | `agent` | 初剪 Agent（见 §7）生成模式：`agent`=按天 scoped 工具环 / `staged`=每天一次纯 JSON |
| `cut_max_tool_rounds` | `24`（上限 200） | Agent 模式单天工具调用环最大轮数护栏；初剪页「初剪设置」弹窗可调 |
| `cut_vision_budget` | `6`（0=不限） | Agent 单次生成内视觉确认调用上限；弱机宜限、强机可放开 |
| `cut_critic_enabled` | `false` | 初剪审片复检：拼好后跑一轮 critic LLM 评主观质量并对点名日期重做 |
| `cut_lean_token_budget` | `50000`（范围 1000–200000） | Agent 模式单日素材目录 token 上限（精简版上下文，台词按需取）；按真实 token 计 |
| `cut_staged_token_budget` | `40000`（范围 1000–200000） | Staged 模式单日素材目录 token 上限（内联台词版，填得更快） |
| `cut_default_aspect_ratio` | `16:9` | 初剪 Agent 默认画面比例，用户可在对话中覆盖 |
| `cut_director_prompt` | （自带默认） | 初剪 Agent system prompt；用户可在初剪页编辑，删除即重置回自带默认 |

---

## 7. v1 范围边界

### v1 已实现（需求 0–8）

| # | 功能 | 状态 |
|---|------|------|
| 0 | 可自定义源文件夹与目标素材库 | ✅ 已实现 |
| 1 | 拍摄时间不被改变（原文件只读） | ✅ 已实现 |
| 2 | A-roll / B-roll 自动判定（可手动纠正） | ✅ 已实现 |
| 3 | A-roll 中文简介 + 标签生成 | ✅ 已实现 |
| 4 | 按拍摄日期+类型自动分类到目录 | ✅ 已实现 |
| 5 | AI自动生成 + 用户手动标签，来源可区分 | ✅ 已实现 |
| 6 | ffmpeg/Pillow 缩略图生成与浏览墙（含照片） | ✅ 已实现 |
| 7 | OMLX Qwen3.6 / VL 本地模型集成（文本+视觉） | ✅ 已实现 |
| 8 | 关键帧建议（A-roll/B-roll）+ 详情面板角标 + 自动开关 | ✅ 已实现 |

### v1 之外的独立工具（复用适配器/队列/SSE，不改动 per-clip 流水线）

| 功能 | 状态 | 说明 |
|------|------|------|
| **字幕导出**（成片 → FCP iTT/SRT） | ✅ 已实现 | 强制人声分离，独立 job 类型；纯逻辑格式化器 + Worker 队列 |
| **转写前人声分离**（Demucs） | ✅ 已实现 | A-roll 可选开关，字幕导出强制；模型懒加载缓存到实例 |
| **原生 macOS .app**（Swift/AppKit） | ✅ 已实现 | WKWebView 内嵌前端，首次启动自动安装 uv/ffmpeg/demucs；Dock 生命周期完整 |
| **库文件删除同步清理** | ✅ 已实现 | orphan 检测 + 级联删除缩略图/关键帧（SQLite CASCADE） |
| **照片分析入库**（HEIC/Pillow） | ✅ 已实现 | photo roll 类型支持，JPEG 缩略图生成 |
| **进度条恢复**（resumePoll） | ✅ 已实现 | jobs API + 轮询增量读取，刷新页面后断点续传；进度轨迹完成后折叠 |
| **初剪导演 Agent**（对话生成分镜表） | ✅ beta，持续改进中 | 按天 scoped 工具环 + 回落、实时进度（逐日/片段）、refine 按日期合并、审片 critic agent；多片段日用精简上下文兜底 |
| **设置统一 config.json**（去 env 分组） | ✅ 已实现 | machine-global 键并入统一 `prefs` 视图，仍存 `~/.cutfinder/config.json` |
| **初剪 fallback 复用勘察分析** | ✅ 已实现 | agent inspect_broll 视觉描述带入 staged 回落模式，不浪费视觉预算 |

---

## 8. 关键风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| **复制改动原文件** | 用户素材丢失或损坏 | 原文件全程只读；只对副本操作；复制后校验文件大小一致性（LibraryWriter） |
| **拍摄时间被改** | 分类日期错误，素材顺序混乱 | 不改原文件；副本用 `copy2` 保留 mtime/atime；内嵌元数据天然不变 |
| **占用双倍磁盘空间**（复制模式） | 素材库膨胀，磁盘压力 | 文档明示设计选择；后续可提供「仅索引/移动」模式作为选项（未实现） |
| **AI 判定/简介出错** | A/B 分类不准，摘要不可用 | VAD 阈值可配置（默认 0.35）；A/B 判定可手动纠正并记住（`roll_source='manual'`）；简介与标签均可人工编辑 |
| **文本+视觉两模型同驻内存** | Apple Silicon 显存不足，推理变慢或 OOM | OMLX LRU/pin/TTL 内存管理；视觉默认量化（4/6-bit）；抽帧数量可配置 |
| **中文转写准确率** | A-roll 简介基于错误文本，标签不准 | Whisper large-v3 中文表现好；Qwen3-ASR+ForcedAligner 更准且时间轴不漂移（zh-en mixed audio）；保留全文供人工核对 |
| **LLM function-calling 不稳定**（初剪 Agent） | 多轮工具调用不收敛，分镜表无法生成 | 已退化为「按天 mini-agent」+ 回落 staged 纯 JSON；round cap + emit_plan 催收兜底；多片段日用精简上下文 |
| **OMLX 服务不可达** | A-roll/B-roll AI 分析失败，但基础功能（扫描/VAD/缩略图）仍可用 | 原生 App Shell 启动时探测 OMLX，不可达弹引导页（含下载链接 + 重试）；Web App 启动时明确报错 |

---

*本文档为需求与方案设计稿，配套详细设计见 [`docs/detailed-design.md`](./detailed-design.md)。*
