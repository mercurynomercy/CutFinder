# CutFinder 详细设计文档（Detailed Design）

> 配套需求文档：[`doc/proposal.md`](./proposal.md)。本文件把需求拆成可独立开发、独立测试的模块，给出每个模块的职责、接口、输入输出、依赖与测试方式。
>
> - **日期**：2026-06-13（v1）；2026-06-18 增补 §3.13 字幕导出（独立成片 → FCP iTT/SRT）；2026-06-22 增补 §3.15 初剪导演 Agent（对话生成分镜表，**beta，持续改进中**）：分阶段生成已细化为**按拍摄日期逐日生成**、消息内自然语言参数解析、可编辑导演 Prompt（`~/.cutfinder/config.json`，可重置）、分镜表带拍摄日期列并按当天真实时间线排序。2026-06-24 §3.15 再迭代（`tasks/26–28`）：**按天 mini-agent**（scoped 工具环 + 回落，开关 `cut_director_mode`）、**实时进度 + 部分分镜先显示**、**refine 按日期合并**（修「增加某天却整表替换」bug）、**审片 critic agent**（默认关 `cut_critic_enabled`）；逐次生成参数（审片复检 / 视觉确认次数）移到初剪页「初剪设置」弹窗。`tasks/29`：设置去掉历史 `"env"` 分组，machine-global 键并入统一 `prefs` 视图（仍存 `~/.cutfinder/config.json`）。2026-06-25 §3.15 小修：单日素材目录上限改**按真实 token 计**（OMLX `/v1/messages/count_tokens`，`cut_lean_char_budget`→`cut_lean_token_budget` 等）、修长任务生成完不恢复回复（轮询上限 10→60 分钟 + 超时再同步）、进度轨迹完成后保留且完整可滚动、`get_clip_detail` 进度文案按 roll 区分（A-roll 台词 / B-roll 画面信息）。
> - **范围**：proposal v1（需求 0–7）。需求 8（关键帧建议）已实现（见 `tasks/16-keyframes.md`）。**字幕导出**（§3.13、`tasks/17`）与**初剪导演 Agent**（§3.15、`tasks/25`）均为 v1 之外的独立工具，复用已有适配器/队列/SSE，**不改动 v1 per-clip 流水线接口**。

---

## 1. 设计目标与原则

1. **模块强隔离、可独立测试**：每个模块只做一件事，通过明确接口通信，能脱离其他模块单独测。
2. **外部重依赖全部藏在接口后面**：ffmpeg/ffprobe、Silero VAD、mlx-whisper、OMLX（文本+视觉）都通过 Python `Protocol` 抽象，业务逻辑只依赖接口，测试时注入假实现（fake/mock），不碰真实模型、不跑真实视频。
3. **前后端分离**：后端 FastAPI 提供 REST + SSE，前端 React 只通过 HTTP 通信，两端可各自独立开发与测试。
4. **继承 proposal 的四条硬约束**：原文件只读、拍摄时间永不改、全本地离线、扫描幂等。

---

## 2. 总体架构

分层架构，依赖方向**自上而下、单向**（上层依赖下层接口，下层不知道上层）：

```
┌─────────────────────────────────────────────────────────┐
│  前端 (Vite + React + Tailwind + shadcn/ui)               │
│  缩略图墙 / 筛选 / 搜索 / 详情编辑 / 设置 / 进度条(SSE)    │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP (REST + SSE)
┌───────────────────────────▼─────────────────────────────┐
│  API 层 (FastAPI)  ── 薄，只做路由/校验/序列化            │
└───────────────────────────┬─────────────────────────────┘
                            │ 调用
┌───────────────────────────▼─────────────────────────────┐
│  编排层  Pipeline Orchestrator + Job Queue/Worker         │
│  （把各领域模块串成 per-clip 流水线，发 SSE 进度事件）    │
└───────────────────────────┬─────────────────────────────┘
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
┌───────────────┐ ┌─────────────────┐ ┌────────────────────┐
│ 领域模块       │ │ Catalog 仓储     │ │ 适配器层(外部依赖)  │
│ Scanner       │ │ (SQLite 数据访问)│ │ MetadataProbe      │
│ Classifier    │ └─────────────────┘ │ ThumbnailMaker     │
│ LibraryWriter │                     │ FrameExtractor     │
│ (纯逻辑)      │                     │ SpeechDetector     │
└───────────────┘                     │ Transcriber        │
                                      │ Summarizer (OMLX)  │
                                      │ VisionTagger(OMLX) │
                                      └────────────────────┘
                                            │ 真实实现
                          ffmpeg/ffprobe · Silero · mlx-whisper · OMLX
```

**关键点**：编排层、领域模块、仓储都只依赖「适配器接口」，不依赖具体实现。测试时用假适配器替换，因此整条流水线可在毫秒级、无外部依赖下跑通。

### 建议的代码结构

```
cutfinder/
├── mise.toml                    # 钉死 Python/Node 版本
├── Brewfile                     # 系统依赖(ffmpeg)
├── Makefile                     # setup/dev/models/check-omlx/test...
├── backend/
│   ├── pyproject.toml + uv.lock # uv 管理依赖
│   ├── cutfinder/
│   │   ├── config.py            # 配置模型与读写
│   │   ├── domain/              # 纯领域模型(dataclass/pydantic)，无 IO
│   │   │   ├── models.py        # Clip, VideoMetadata, Transcript, Tag, Job...
│   │   │   └── enums.py         # RollType, Source, JobStatus...
│   │   ├── ports/               # 接口(Protocol)定义 —— 隔离的核心
│   │   │   ├── probe.py         # MetadataProbe
│   │   │   ├── media.py         # ThumbnailMaker, FrameExtractor
│   │   │   ├── speech.py        # SpeechDetector, Transcriber
│   │   │   ├── ai.py            # Summarizer, VisionTagger
│   │   │   ├── library.py       # LibraryWriter
│   │   │   └── repository.py    # CatalogRepository
│   │   ├── adapters/            # 接口的真实实现(碰外部依赖)
│   │   │   ├── ffmpeg_probe.py
│   │   │   ├── ffmpeg_media.py
│   │   │   ├── silero_vad.py
│   │   │   ├── mlx_whisper.py
│   │   │   ├── omlx_text.py     # OpenAI 客户端 → OMLX 文本模型
│   │   │   ├── omlx_vision.py   # OpenAI 客户端 → OMLX 视觉模型
│   │   │   ├── fs_library.py
│   │   │   └── sqlite_repo.py
│   │   ├── pipeline/
│   │   │   ├── orchestrator.py  # per-clip 流水线(纯逻辑，注入接口)
│   │   │   ├── scanner.py       # 扫描+去重(纯逻辑，注入 probe/repo)
│   │   │   └── worker.py        # 后台队列+SSE 事件
│   │   └── api/
│   │       ├── app.py           # FastAPI 应用装配(依赖注入真实适配器)
│   │       ├── routes_*.py
│   │       └── sse.py
│   └── tests/
│       ├── unit/                # 全 mock，无外部依赖
│       ├── integration/         # @pytest.mark.integration，碰真实依赖
│       └── fakes/               # 各 port 的假实现 + 样本素材
└── frontend/
    ├── src/
    │   ├── api/                 # API 客户端(唯一与后端通信处)
    │   ├── features/{gallery,filters,search,detail,settings,jobs}/
    │   └── components/
    └── tests/                   # Vitest + RTL；e2e/ 放 Playwright
```

---

## 3. 后端模块详细设计

每个模块给出：**职责 / 接口 / 输入 → 输出 / 依赖 / 如何独立测**。

### 3.1 Config（配置）
- **职责**：提供类型安全的配置对象；区分**密钥/端点**与**用户偏好**两类来源。
- **两类来源**：
  - **密钥/端点 → 全局配置 / OS env vars**（`pydantic-settings` 读取，不入库不进 git）：`OMLX_BASE_URL`、`OMLX_API_KEY`。
  - **用户偏好 → JSON**（`<库>/.cutfinder/config.json`）：`source_folders`、`library_path`、`text_model`、`vision_model`、`whisper_model`、`extensions`（默认 `.mov .mp4 .m4v`）、`broll_frame_count`（默认 3）、`vad_threshold`（默认 0.15）。
- **接口**：`resolve_env() -> EnvSettings`（全局配置优先，OS env 覆盖）、`load_config() -> AppConfig`、`save_prefs(Prefs)`。`AppConfig` 合并全局配置/OS env 与 JSON 两部分；全部缺失时给出明确报错（OMLX 必填）。
- **独立测**：用 `monkeypatch` OS env + 临时 JSON，断言合并结果、默认值；全局配置缺失时报错。

### 3.2 MetadataProbe（元数据探测，适配器）
- **接口**（`ports/probe.py`）：
  ```python
  class MetadataProbe(Protocol):
      def probe(self, path: Path) -> VideoMetadata: ...
  ```
  `VideoMetadata`：`capture_time: datetime | None`、`date_source: "embedded"|"file"`、`duration_s`、`width`、`height`、`fps`、`codec`、`has_audio: bool`。
- **真实实现**：`ffprobe -show_format -show_streams -print_format json`，读 `format.tags.creation_time`（QuickTime）。无内嵌时间则回退 `st_birthtime`（macOS），`date_source="file"`。
- **独立测**：单元测试用 fake（返回固定 `VideoMetadata`）。适配器本身用 `@pytest.mark.integration` + 样本 `.mov` 验证真实解析。

### 3.3 ThumbnailMaker / FrameExtractor（缩略图 / 抽帧，适配器）
- **接口**（`ports/media.py`）：
  ```python
  class ThumbnailMaker(Protocol):
      def make(self, path: Path, out_path: Path) -> Path: ...   # 代表帧
  class FrameExtractor(Protocol):
      def extract(self, path: Path, count: int) -> list[Path]: ... # 均匀采样
  ```
- **真实实现**：ffmpeg。缩略图取偏中部一帧；抽帧按时长均匀取 `count` 帧（默认 3）。
- **独立测**：fake 返回事先准备的图片路径；适配器集成测试对样本视频验证产出文件存在、尺寸合理。

### 3.4 SpeechDetector（A/B 判定，适配器）
- **接口**（`ports/speech.py`）：
  ```python
  class SpeechDetector(Protocol):
      def speech_ratio(self, path: Path) -> float: ...  # 0..1
  ```
- **真实实现**：Silero VAD。`speech_ratio >= 阈值(默认 0.15)` → 判 A-roll，否则 B-roll。阈值可配置。
- **独立测**：fake 直接返回设定的比例，验证编排层据此分支；适配器集成测试用一段有解说/一段纯空镜样本。

### 3.5 Transcriber（语音转写，适配器）
- **接口**：
  ```python
  class Transcriber(Protocol):
      def transcribe(self, path: Path) -> Transcript: ...
  ```
  `Transcript`：`full_text: str`、`segments: list[Segment(start_s, end_s, text)]`。
- **真实实现（两种引擎，由 `transcription_engine` 偏好选择，均为本地独立进程、不走 OMLX）**：
  - **`mlx-whisper`**（large-v3，中文）—— `adapters/mlx_whisper.py`。
  - **Qwen3-ASR + Qwen3-ForcedAligner**（经 `mlx-audio` 本地运行）—— `adapters/qwen_transcriber.py`：先按 Silero VAD 把音频切成 ≤`qwen_max_chunk_s`（默认 60，上限 300，受对齐器约 400 秒时间戳范围限制）的片段，逐段用 Qwen3-ASR 出准确中文/中英文本、用 ForcedAligner 出逐字时间戳，偏移回整段时间轴后再归并成字幕 cue。中文更准且时间轴不漂移；OMLX 无法经 HTTP 托管对齐器，故必须本地跑，模型下载到 `models/qwen/`。该选择作用于所有 A-roll 语音处理（编目转写、关键帧、字幕导出）。
- **转写前人声分离**（见 §3.14）：构造可注入 `VocalSeparator`；注入时先抽干声去 BGM 再转写，分离失败回落原始音频。whisper 路径补防幻觉 kwargs（如 `condition_on_previous_text=False`），Qwen 路径用 `repetition_penalty` + 按片段时长限制 `max_tokens` 防止 ASR 复读。`transcribe()` 端口签名不变——是否分离由构造时是否注入 separator 决定。
- **独立测**：fake 返回固定文本；适配器集成测试用一段短中文语音样本。

### 3.6 Summarizer（A-roll 文本总结，适配器→OMLX）
- **接口**（`ports/ai.py`）：
  ```python
  class Summarizer(Protocol):
      def summarize(self, transcript_text: str) -> SummaryResult: ...
  ```
  `SummaryResult`：`summary: str`（中文简介）、`tags: list[str]`。
- **真实实现**：OpenAI 客户端指向 OMLX（`base_url=OMLX_BASE_URL`、`api_key=OMLX_API_KEY`，来自全局配置 / OS env；`model=text_model` 默认 `Qwen3.6-35B-A3B`）。用**结构化输出**（JSON）约束返回 `{summary, tags}`。
- **独立测**：fake 返回固定 `SummaryResult`；适配器集成测试需本机 OMLX，打 `integration` 标记。

### 3.7 VisionTagger（B-roll 画面识别，适配器→OMLX）
- **接口**：
  ```python
  class VisionTagger(Protocol):
      def describe(self, frame_paths: list[Path]) -> VisionResult: ...
  ```
  `VisionResult`：`description: str`（中文画面描述）、`tags: list[str]`。
- **真实实现**：把抽帧读成 **base64**，按 OpenAI 视觉消息格式（`image_url` data URI）发给 OMLX（同样用全局配置 / OS env 的 `OMLX_BASE_URL`/`OMLX_API_KEY`，`model=vision_model` 默认 `Qwen3-VL-8B-Instruct`），一次请求带多帧；结构化输出 `{description, tags}`。
- **独立测**：fake 返回固定结果；适配器集成测试需本机 OMLX。

### 3.8 LibraryWriter（库文件组织，适配器）
- **职责**：把原文件**复制**到 `库/YYYY-MM-DD/A-roll|B-roll/`，保留时间，处理重名，校验。**原文件只读。**
- **接口**（`ports/library.py`）：
  ```python
  class LibraryWriter(Protocol):
      def copy_into(self, src: Path, date: date, roll: RollType) -> Path: ...
  ```
- **真实实现**：`shutil.copy2`（保留 mtime/atime；内嵌拍摄时间天然不变）。目标已存在同名则追加 ` (1)` 等序号，不覆盖。复制后校验大小一致。
- **独立测**：在临时目录用真实小文件即可（不算重依赖），断言：原文件未被改动、目标路径符合 `日期/类型`、重名不覆盖、mtime 保留。

### 3.9 CatalogRepository（数据仓储）
- **职责**：所有 SQLite 读写的唯一入口（见 §5 数据模型）。
- **接口**（节选，`ports/repository.py`）：
  ```python
  class CatalogRepository(Protocol):
      def exists_fingerprint(self, fp: str) -> bool: ...
      def upsert_clip(self, clip: Clip) -> int: ...
      def get_clip(self, clip_id: int) -> Clip | None: ...
      def query_clips(self, f: ClipFilter) -> list[ClipSummary]: ...
      def search(self, q: str) -> list[ClipSummary]: ...      # 转写全文/画面描述
      def set_tags(self, clip_id: int, tags: list[Tag]) -> None: ...
      def correct_roll(self, clip_id: int, roll: RollType) -> None: ...
      def update_analysis(self, clip_id: int, r: AnalysisResult) -> None: ...  # re-analyze: 只更 auto 标签/简介/描述/转写
      def create_job(...) / update_job(...) / get_job(...): ...
  ```
- **真实实现**：`sqlite_repo.py`。全文搜索用 SQLite **FTS5** 虚拟表（转写文本 + 画面描述）。
- **独立测**：用 **内存 SQLite**（`:memory:`）跑真实实现的单元测试——快且无外部依赖，验证 CRUD、查询过滤、FTS 搜索、幂等 upsert。

### 3.10 Scanner（扫描去重，纯逻辑）
- **职责**：遍历源文件夹，按扩展名白名单过滤，算**文件指纹**，与仓储比对，产出「待处理新片段」清单。
- **指纹**：`sha256(文件大小字节 + 头部 4MB)`——避免全量读大文件，又能稳定去重。
- **依赖（注入接口）**：文件系统遍历、`CatalogRepository.exists_fingerprint`。
- **独立测**：用临时目录造文件 + 内存仓储，验证：只挑白名单扩展名、跳过已存在指纹、同内容不重复入列。

### 3.11 Pipeline Orchestrator（编排，纯逻辑——隔离的核心）
- **职责**：对单个片段执行流水线，**只依赖接口**，不碰任何真实外部依赖：
  ```
  probe 元数据 → 生成缩略图
    → speech_ratio 判 A/B
       A: transcribe → summarize(OMLX 文本)
       B: extract 抽帧 → describe(OMLX 视觉)
    → repository.upsert_clip(+tags +transcript/description)
    → library.copy_into(复制到日期/类型目录)
    → 发进度事件
  ```
- **错误处理**：任一步失败 → 该片段 `status=error` 记录错误信息，**整批继续**，可重试；不影响其他片段。
- **幂等**：开始前再查指纹；已 `done` 跳过。
- **重新分析单个片段（re-analyze）**：对已入库片段强制重跑 **AI 分析**（VAD→A/B、转写+总结 / 抽帧+视觉），用于换模型或结果不理想时刷新。语义：
  - **不重新复制**原文件（`library_path` 不变），**不改**已有元数据/拍摄时间。
  - **保留手动纠正**：`roll_source='manual'` 的 A/B 判定不被自动结果覆盖；`source='manual'` 的标签保留，只刷新 `source='auto'` 的标签与 `summary`/`description`/转写。
  - 走与批量相同的队列与 SSE 进度（单片段任务）。
- **依赖（全部注入）**：`MetadataProbe, ThumbnailMaker, FrameExtractor, SpeechDetector, Transcriber, Summarizer, VisionTagger, LibraryWriter, CatalogRepository`。
- **独立测**：注入**全部假适配器**，断言：
  - A 分支调用了 transcribe+summarize、未调用 vision；B 分支相反；
  - 错误注入时该片段标 error 且循环继续；
  - 已处理片段被幂等跳过；
  - 落库内容与复制目标正确；
  - re-analyze：刷新了 auto 标签/简介，但保留了 manual 标签与 manual 的 A/B，且未调用 LibraryWriter（不重复制）。这是测试金字塔的重点，覆盖业务逻辑且毫秒级。

### 3.12 Worker + Job Queue（后台队列 + SSE）
- **职责**：接收扫描/处理请求 → 入队 → 单 worker **顺序**处理（尊重模型显存，OMLX 负责换模型）→ 把每个片段的开始/完成/失败作为**进度事件**通过 SSE 推给前端。
- **实现**：`asyncio.Queue` + 后台 task；进度用 `asyncio` 事件广播给 SSE 连接。Job 状态（total/done/error）持久化到仓储，便于刷新页面后恢复。
- **独立测**：注入假编排器，验证队列顺序、进度事件序列、job 状态推进；SSE 用 FastAPI TestClient 断言事件流。

### 3.13 SubtitleExporter（字幕导出，独立工具——v1 之外）

> 与 per-clip 流水线**完全解耦**：输入是一段**已剪辑完成的成片**（不一定在素材库里），**重新转写**对齐成片自己的时间轴，导出 **iTT（FCP 原生）+ SRT**，**不入库、不分类、不复制源视频**。任务清单见 `tasks/17-subtitle-export.md`。

- **职责**：成片 → `mlx-whisper` **转写**（按成片口语语言）→ 格式化为 iTT/SRT → 写入用户选定的输出文件夹。
- **复用**：`MetadataProbe`（`fps`/`duration`）、`Transcriber`（`Transcript{full_text, segments:[Segment]}`）、Worker 队列 + SSE、`output_language` 配置、`/api/open`。
- **语言：只转写、不翻译**。`output_language` 表示**成片本身的口语语言**（用户自知）；`Transcriber.transcribe` 增 `language: str | None=None`，把它作为 `mlx_whisper` 的 `language` 提示传入（`zh`→中文、`en`→英文），并写入字幕 `xml:lang`。不引入任何翻译（中文成片导出英文字幕等需求留作将来）。
- **纯逻辑格式化**（`subtitle/format.py`，无 IO，本模块测试金矿）：
  ```python
  def to_srt(segments: list[Segment]) -> str: ...                       # HH:MM:SS,mmm
  def to_itt(segments: list[Segment], *, language: str, fps: float) -> str: ...  # TTML, ttp:timeBase="media", HH:MM:SS.mmm
  ```
- **服务**（`pipeline/subtitle_exporter.py`，注入接口）：
  ```python
  def export(self, video_path: Path, out_dir: Path, formats: list[str], language: str) -> list[Path]:
      # probe(fps) → transcribe(language) → 写 <名>.<lang>.{itt,srt}（同名不覆盖）→ 返回路径
  ```
  逐步错误隔离（失败记错误不抛）。`language` 缺省取 `output_language`，同时作为 Whisper 提示与字幕 `xml:lang`。
- **Worker**：新增 job kind `subtitle`，payload `SubtitleRequest{video_path, out_dir, formats, language}`；`enqueue_subtitle / _process_subtitle`；产出路径放**内存结果存储**（避免改 DB schema），由 `GET /api/subtitles/{job_id}` 读取。
- **硬约束**：源视频**只读**（绝不改名/改写）；只在选定文件夹**新建**字幕文件；转写**全本地离线**。
- **去 BGM（见 §3.14）**：成片往往混了 BGM，本工具的 transcriber **恒注入 `VocalSeparator`、强制分离**后再转写，不受 A-roll 流水线开关影响。
- **进度同步（见 `tasks/19-subtitle-progress.md`）**：`export(..., on_progress)` 透传单一 0..1 进度；transcriber 内部把**分离 [0, W] + 转写 [W, 1]**合成（W≈0.4），进度来自拦截 Demucs/mlx-whisper 各自的 tqdm。worker 把 subtitle job 改 `total=100`、节流写 `done` + `job_progress` SSE，前端渲染真实进度条。**仅字幕导出**启用；A-roll 流水线不传 `progress`。
- **iTT 决策**：TTML + `ttp:timeBase="media"` + `HH:MM:SS.mmm` 时钟码 + `xml:lang`；`fps` 读取备用。**验收须真机导入 Final Cut Pro 验证**。
- **独立测**：格式化用黄金串（时码边界/转义/空分段）；服务注入假 probe/transcriber，断言把 `language`（zh/en）透传给 transcribe、按 formats 产出、命名不覆盖、`xml:lang` 正确。

---

### 3.14 VocalSeparator（转写前人声分离，适配器）

> 治理 BGM 污染 transcript：whisper 前抽出人声干声、扔掉伴奏。任务清单见 `tasks/18-vocal-separation.md`。

- **接口**：
  ```python
  class VocalSeparator(Protocol):
      def isolate(self, path: Path) -> np.ndarray: ...   # whisper 就绪的 16k 单声道 float32 干声
  ```
- **真实实现**：`DemucsSeparator`（`adapters/demucs_separator.py`）——
  1. ffmpeg 抽 **44.1kHz 立体声 f32**（Demucs 原生采样率，不能用 16k）；
  2. `demucs.api.Separator("htdemucs", device=<mps|cpu>)` 分离，取 `separated["vocals"]`；
  3. 下混单声道 + 重采样 **16kHz** → `np.float32`（与 whisper 输入一致，drop-in）。
  模型**懒加载**缓存到实例，device 自动选 MPS 回落 CPU；异常抛出由 transcriber 捕获回落原始音频。
- **接线**：构造**一个**共享 `DemucsSeparator`；**字幕导出 transcriber 恒注入**（强制），**A-roll orchestrator transcriber 仅当 `vocal_separation=true` 才注入**（默认关）。
- **依赖**：`demucs`（带入 torchaudio）；`scripts/download_demucs.py` + `make models` 一次性预下载 `htdemucs`（~80MB），之后离线。
- **独立测**：单测用**假 separator**（断言其输出进 whisper、抛异常时回落）；`DemucsSeparator` 走集成测试（真模型，含 BGM 样本）。

---

### 3.15 CutDirector（初剪导演 Agent，独立工具——v1 之外，**beta，持续改进中**）

> 在**已编目素材库**之上，通过**多轮对话**，依据用户给的日期范围 / 目标时长 / 风格 / 节奏 / 画面比例，产出一份**精确到片段内 in/out 的文字分镜表（A-roll 叙事主线 + B-roll 插空）**，供用户照搬到剪辑软件。**不渲染、不导出剪辑工程**（FCPXML 留作后续）。任务清单见 `tasks/25-rough-cut-agent.md`。
>
> **状态：beta。** 已可用并已按真机表现迭代（见下方"首要风险"与"迭代增强"），分镜"质量"仍在持续打磨——默认 prompt、按日期/时间线的组织方式、本地模型稳定性都会继续改进。

- **架构（方案 C：受约束的工具调用环）**：把"会算错、要稳定"的部分（时长是否凑够目标区间、in/out 时间码、表格渲染）交给**确定性代码**；把"需要创意"的部分（挑哪句解说当主线、配哪条 B-roll、节奏松紧）交给 **LLM 工具调用环**。LLM 跑飞时由确定性脚手架 + 护栏兜底。
- **复用**：`CatalogRepository`（检索编目 + transcript segments + 关键帧）、`VisionTagger`+`FrameExtractor`（现场看 B-roll）、现有 OMLX 文本 client（`text_model=Qwen3.6`）、Worker 队列 + SSE。
- **工具集（ports/cutplan.py，LLM 只能调这些）**：
  ```python
  class FootageRetriever(Protocol):
      def search_footage(self, date_from, date_to, roll=None, tags=None, query=None) -> list[ClipBrief]: ...
      def get_clip_detail(self, clip_id: int) -> ClipDetail: ...   # transcript segments + 关键帧 + 元数据
  class BrollInspector(Protocol):
      def inspect_broll(self, clip_id: int) -> VisionResult: ...   # 现场抽帧调 Qwen3-VL 确认画面
  class LLMAgentClient(Protocol):
      def run_tools(self, messages, tools) -> AgentStep: ...        # tool_calls 或 final content（结构化 CutPlan）
  ```
- **in/out 时间码来源**：**A-roll 主线** in/out = 所选 transcript **segment 的边界**（让 LLM 按 segment 序号选段，映射回 `start_s/end_s`，杜绝幻觉时码——沿用 §3.13/`tasks/16` 的约束手法）；**B-roll 插空**优先用已有关键帧切点，没有则取默认窗口，必要时 `inspect_broll` 抽帧确认。
- **护栏（Director 内，确定性）**：最大工具轮数 `cut_max_tool_rounds`（默认 24）；时长校验 `sum(out_s-in_s)` ∈ `[target_min_s, target_max_s]`，超/欠回灌一轮，仍不达标则**照出 + 尾注"未命中目标时长"**；视觉调用预算 `cut_vision_budget`——**初剪页「初剪设置」弹窗可调**（默认 6；设 `0` = **不限**，由用户按机器性能决定，因文本/视觉交替触发 OMLX 换模型、慢，弱机宜限、强机可放开）。**收尾不让 LLM 算术**——时长累计与区间校验全走代码。
- **纯逻辑格式化**（`cutplan/format.py`，无 IO，本模块测试金矿）：
  ```python
  def to_shotlist_markdown(plan: CutPlan) -> str: ...
  # 按章节（=拍摄日期）分组：每章 `## YYYY-MM-DD` + 表：
  #   # | 日期 | in–out 时码 | 时长 | 类型 | 库内文件 | 缩略图 | 内容/台词 | 用途·理由
  # 表尾：总时长 + 是否落在目标区间
  ```
  **缩略图引用**链接 `/api/clips/{id}/thumbnail` 或所选窗口的关键帧帧图。
- **编排**（`cutplan/director.py`，注入接口）：`handle_message(session_id, user_text)` 跑工具调用环 + 护栏，产 `CutPlan` + 助手回复；refine 轮把既有 plan + 对话历史作为上下文重跑相关步骤。
- **会话持久化**：新表 `cut_sessions`/`cut_messages`/`cut_plans`（见 §5），**可重开、可删除**（删会话级联清消息与 plan）。
- **Worker**：新增 job kind `cutplan`，`enqueue_cutplan(session_id, user_text)`/`_process_cutplan`；经 SSE 推**工具活动 + 助手 token + plan ready** 事件。
- **硬约束**：全程**只读编目与副本**，不碰源文件、不渲染、不联网；**素材须先入库**，库里无该日期范围素材时提示先扫描，不现场扫源文件夹。
- **首要风险（已实测命中）**：Qwen3.6 本地 function-calling **不收敛**——多轮工具调用始终不发 `emit_plan`。**已退化为「分阶段受限调用」并设为默认**：检索由 Director 用代码完成（按日期范围查编目），再把紧凑素材清单（A-roll 带逐段时间戳）交给模型结构化补全分镜表 JSON（不依赖多轮 tool-call）。`CutPlanService` 调 `Director.generate(...)`；自治工具环 `Director.run(...)` 保留备用。新增 `LLMAgentClient.complete(...)`。
  - **第二轮实测命中：整片一次性 JSON 仍会跑飞**——让模型一次产出 15–20 分钟跨多天的完整分镜，会陷入复读/超长生成（实测单次 3 万+ token 仍不终止），JSON 无法解析。**已改为「按拍摄日期逐日生成」**：把素材按拍摄日期分组，**每个日期单独一次 `complete()`**，输出小而稳定，再在代码里拼接成按日期分章的 plan（章节直接 = 日期）。补全采样改 `temperature=0.3`、`max_tokens=8192` 抑制复读；某天解析失败则跳过该天并在回复里注明。
- **迭代增强（beta）**：
  - **消息内自然语言参数解析**（`cutplan/request_parse.py`，确定性正则）：从用户中文消息里抽 `date_from/date_to`、`target_min_s/max_s`、`aspect_ratio`，与会话记住的 `RoughCutRequest` 合并；refine 轮无新日期时沿用原范围。此前前端不下发 scoping，检索会拉全库导致模型过载。
  - **可编辑导演 Prompt**：`DEFAULT_CUT_DIRECTOR_PROMPT`（按日期分章、当天按拍摄时间线、A-roll 以 transcript 为主、不依赖既有关键帧）可由用户在初剪页编辑，存 `~/.cutfinder/config.json` 的 `cut_director_prompt`，含 `{aspect}/{target}/{style}` 占位符；可一键重置回自带默认（删除该键）。
  - **当天时间线排序**：每天素材按 `capture_time` 排序后再喂模型，上下文带完整时间戳，分镜还原当天真实行程顺序。
  - **拍摄日期入分镜**：`ClipDetail`/`Shot` 增 `capture_time`/`clip_date`，UI 与 Markdown 分镜表均显示日期列，便于回找素材。
  - **会话自动命名**：首条用户消息自动作为会话标题（不再恒为"未命名"）。
  - **按天 mini-agent**（`tasks/26`）：每个拍摄日期跑一个**scoped 工具调用环**——只给 `get_clip_detail`（深挖 transcript）/`inspect_broll`（按需看 B-roll）/`emit_plan`（收口），不给 `search_footage`（当天素材已确定性检索好喂进上下文）。单日小上下文下本地模型收口可靠；不收敛（超 round-cap 或纯文字回复）的天**回落**到原「每天一次纯 JSON 补全」。开关 `cut_director_mode`（`agent`/`staged`，默认 `agent`）；含**每日去重护栏**（防幻觉重复调用）+ round-cap 半程「必须 emit_plan」催收。不用 named/required 强制收口（OMLX 不稳），靠 `tool_choice="auto"` + 兜底。
  - **实时进度 + 部分分镜先显示**（`tasks/27`）：Director 把逐天/逐片段进度串（检索阶段/本天片段数/clip 文件名/导演思路/回落）与**已完成日期的部分 plan** 写进 store（内存进度 + 覆盖式 `save_plan`），前端 `resumePoll` 轮询增量读取——「第 k/N 天 · 查看片段 #X」实时刷新、已完成日期分镜先渲染、其余标「生成中」；进度 UI 由「单行替换」改为「最近 5 步滚动轨迹」。沿用轮询（无 SSE/线程桥接）。
  - **refine 按日期合并**（`tasks/28` Part A）：`generate(prior_plan=...)` 以旧 plan 为基底建 `merged: dict[拍摄日期 → shots]`，本轮只重做范围内日期——成功覆盖该天、失败保留旧那天、`_flatten` 按日期排序后再 `_build_plan`。修了「增加一份 5/11 把整表替换成只剩 5/11」的 bug（根因：检索按改窄范围只重做该天 + plan 覆盖式保存）；逐天 partial 与最终 plan 都走合并视图，故 refine 中途不闪掉旧日期；缩到无素材的日期返回 `None` plan（service 不覆盖、旧 plan 保留）。`CutPlanService.handle` 取 `get_latest_plan` 作 `prior_plan`。
  - **审片 critic agent**（`tasks/28` Part B，默认关 `cut_critic_enabled`）：全片拼好后跑一次 critic LLM 调用，只评**主观质量**（节奏松紧 / 叙事连贯 / A-roll 主线与 B-roll 空镜配比 / 空镜缺位），输出结构化 `{date, issue, action}` 修订意见；主编排对**被点名日期**复用 Part A 的「重做该日期 → 并入」机制修一轮（最多 1 轮；坏/空 JSON 则跳过、原 plan 不变）。时长校验仍由确定性代码兜底，critic 不碰。
  - **多片段日的 tool 收口修复**（实测：单天 50+ 片段时 agent 从不调工具、直接回落）：根因有二——① **检索/上下文把 agent 废了**：`_build_context` 把每条 A-roll 的 60 条 transcript 分段**内联**进 prompt，单天几十条就撑爆 12000 字符预算、后面片段被截断，且台词已内联→模型没理由再调 `get_clip_detail`。改为**按模式分别建上下文**：agent 用**精简版**（每片段一行 + `[有台词]` 标记，台词靠 `get_clip_detail` 按需取），staged 仍用**完整版**（无工具，需内联台词）。两版的字符预算各成一项设置 `cut_lean_char_budget`（默认 80000）/ `cut_staged_char_budget`（默认 60000），取代原写死的 12000——文本模型可吃 260k token 上下文，故默认放宽，上限只为约束本地 OMLX prefill 开销/内存，并非用来截断。② **回落太急**：首个纯文字回复就放弃→现在**先给一次机会**：先尝试从该 prose 里捞出 `{"shots":[…]}`（模型"直接作答"也认），捞不到就插一条「必须用工具」系统提示重试一次，仍不调工具才回落。导演 day prompt 也加强：明确「标 [有台词] 的片段台词要用 get_clip_detail 取、最后必须 emit_plan、不要纯文字回答」。
  - **回落复用已勘察分析**（`tasks/30`）：`_run_day` 在 tool 循环里把 `inspect_broll` 成功看到的 B-roll 画面描述累积进 `findings`（`vision_used` 自增作成功信号，错误串不记），回落时一并带出；`_gen_one_day` 透传给 `_staged_day`，后者在 prompt 追加「导演已现场勘察过以下 B-roll 画面…」段。这样花掉的视觉预算不再随回落白费，快速模式据**新鲜描述**而非仅存量标签判断。回落进度行显示「带入 N 条已勘察画面」。时长仍**不裁**——超/欠目标只由前端 `within_target` 的 ⚠️ + 一句"素材有限"说明呈现（用户：时长非硬性要求，多为素材限制）。
  - **逐次生成参数移到初剪页**（`tasks/28` UI）：`cut_director_mode`（生成模式 agent/staged）、`cut_max_tool_rounds`（最大工具轮数，仅 agent）、`cut_critic_enabled`（审片复检）、`cut_vision_budget`（视觉确认次数）、`cut_lean_token_budget` / `cut_staged_token_budget`（单日素材目录 token 上限，分 agent / staged 两档）从全局设置页移到**初剪页面**——原「导演 Prompt」弹窗升级为「初剪设置」弹窗（顶部「生成选项」段 + 下方导演 Prompt 文本框），开弹窗 `GET /settings` 回填、保存 `PUT /settings`（触发 director 重建生效）。
  - **素材目录上限改按真实 token 计 + 进度 UI 修复 + B-roll 标签**（2026-06-25）：①「单日素材目录上限」从**字符数**改为**真实 token 数**——`_build_context` 先整目录拼好，调 OMLX `/v1/messages/count_tokens`（与所服务模型同一分词器）拿精确 token，仅在超预算时按实测 chars/token 比例回切；端点不可用则回退字符估算（`_FALLBACK_CHARS_PER_TOKEN=1.8`）。设置项 `cut_lean_char_budget`/`cut_staged_char_budget` 改名 `cut_lean_token_budget`/`cut_staged_token_budget`（默认 50000/40000，范围 1000–200000），UI 中英标签改「token」。新增 `LLMAgentClient.count_tokens()`（`OmlxAgentClient` 用 httpx 实现，best-effort 返回 `None`）。② 前端 `resumePoll` 轮询上限 10 分钟→60 分钟，且超时退出前再同步一次会话——修「长任务（多天 15–20 分钟 vlog）生成完没恢复助手回复」。③ 完成后**保留**进度轨迹（原会清空），渲染**完整可滚动**日志（原仅末 5 步、`max-h-48 overflow-y-auto` + 运行中贴底），完成后也显示。④ `get_clip_detail` 进度文案按 roll 区分：A-roll「的台词」、B-roll「的画面信息」（B-roll 无台词，读的是扫描入库时 VL 已分析存下的画面描述/切点；现场再看一眼仍是 `inspect_broll`「的画面」）。
- **独立测**：格式化用黄金串（章节/缩略图引用/时长尾注/边界）；Director 注入**假 LLMAgentClient（脚本化 tool_calls / 补全字符串）+ 假工具**，断言 A 主线选段映射 in/out、B 插空、时长护栏回灌、最大轮数/视觉预算护栏、按天 agent 收口 + 回落、每日去重护栏、**refine 按日期合并（保留旧日期 / 失败保旧）**、**critic 重做并入 / 坏 JSON 跳过**；Service 断言 `get_latest_plan` 作 `prior_plan` 透传。Retriever/SessionStore 用内存 SQLite（含删除级联）。分镜"质量"不可自动化验收——靠 eval 清单 + 真机抽查。

---

## 4. 外部依赖与 Mock 策略（独立测试的关键）

| 接口(Port) | 真实适配器 | 单元测试替身 | 集成测试(可选, `@pytest.mark.integration`) |
|---|---|---|---|
| MetadataProbe | ffprobe | 返回固定 `VideoMetadata` | 对样本 `.mov` 真解析 |
| ThumbnailMaker/FrameExtractor | ffmpeg | 返回预置图片路径 | 对样本视频真抽帧 |
| SpeechDetector | Silero VAD | 返回设定 `speech_ratio` | 有声/无声样本各一 |
| Transcriber | mlx-whisper | 返回固定 `Transcript` | 短中文语音样本 |
| VocalSeparator | Demucs (`htdemucs`) | 返回固定干声数组 | 含 BGM 样本，验证去伴奏 |
| Summarizer | OMLX 文本 | 返回固定 `SummaryResult` | 需本机 OMLX |
| VisionTagger | OMLX 视觉 | 返回固定 `VisionResult` | 需本机 OMLX |
| LibraryWriter | shutil 复制 | 真跑(轻，临时目录) | — |
| CatalogRepository | SQLite | 内存 SQLite 真跑 | — |

**原则**：单元测试默认 `pytest`（不带标记）全程不碰真实模型/视频/网络，CI 可跑、秒级完成；集成测试打 `integration` 标记，`pytest -m integration` 在本机手动跑，验证真实适配器契约。

---

## 5. 数据模型（SQLite）

```sql
-- 片段主表
CREATE TABLE clips (
  id            INTEGER PRIMARY KEY,
  fingerprint   TEXT UNIQUE NOT NULL,       -- 去重键
  source_path   TEXT NOT NULL,              -- 原文件(只读)
  library_path  TEXT,                       -- 复制后的库内路径
  roll_type     TEXT NOT NULL,              -- 'A' | 'B'
  roll_source   TEXT NOT NULL,              -- 'auto' | 'manual'
  capture_time  TEXT,                       -- ISO; 拍摄时间
  date_source   TEXT NOT NULL,              -- 'embedded' | 'file'
  duration_s    REAL, width INTEGER, height INTEGER, fps REAL, codec TEXT,
  thumbnail_path TEXT,
  summary       TEXT,                       -- A-roll 中文简介
  description   TEXT,                       -- B-roll 画面描述
  status        TEXT NOT NULL,              -- 'pending'|'processing'|'done'|'error'
  error         TEXT,
  created_at    TEXT, processed_at TEXT
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  source TEXT NOT NULL,                      -- 'auto' | 'manual'
  UNIQUE(clip_id, name)
);

CREATE TABLE transcripts (
  clip_id INTEGER PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
  full_text TEXT,
  segments_json TEXT                         -- [{start_s,end_s,text}]
);

CREATE TABLE jobs (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL,                      -- 'running'|'done'|'failed'
  total INTEGER, done INTEGER, failed INTEGER,
  started_at TEXT, finished_at TEXT
);

-- 全文搜索(转写 + 画面描述)
CREATE VIRTUAL TABLE clips_fts USING fts5(
  summary, description, transcript, content=''
);

-- 初剪导演 Agent 会话(§3.15)
CREATE TABLE cut_sessions (
  id INTEGER PRIMARY KEY,
  title TEXT,
  request_json TEXT,                  -- 最近一次 RoughCutRequest
  status TEXT NOT NULL,               -- 'idle'|'running'|'error'
  created_at TEXT, updated_at TEXT
);
CREATE TABLE cut_messages (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                 -- 'user'|'assistant'|'tool'
  content TEXT,
  tool_json TEXT,                     -- 可选: tool_calls / tool_result 原文
  created_at TEXT
);
CREATE TABLE cut_plans (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES cut_sessions(id) ON DELETE CASCADE,
  plan_json TEXT NOT NULL,            -- CutPlan{shots[], total_s, target_*, chapters[]}
  created_at TEXT
);
```

位置：`<库>/.cutfinder/catalog.sqlite`，缩略图在 `<库>/.cutfinder/thumbnails/`。

---

## 6. API 设计（REST + SSE）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/scan` | 触发扫描+处理；body 可选覆盖源文件夹；返回 `job_id` |
| GET | `/api/jobs/{id}` | 查 job 状态(total/done/failed) |
| GET | `/api/jobs/{id}/events` | **SSE** 进度流(每片段 start/done/error) |
| GET | `/api/clips` | 列表；query：`date`、`type=A|B`、`tag`、`q` |
| GET | `/api/clips/{id}` | 详情(简介/描述/标签/转写/元数据/路径) |
| PATCH | `/api/clips/{id}` | 纠正 `roll_type`、编辑 `summary` |
| PUT | `/api/clips/{id}/tags` | 整体替换标签(手动增删) |
| POST | `/api/clips/{id}/reanalyze` | 重新分析单个片段(重跑 AI；保留手动纠正/标签，不重复制)；返回 `job_id` |
| GET | `/api/search?q=` | 跨简介/描述/转写全文搜索(FTS5) |
| GET | `/api/clips/{id}/thumbnail` | 缩略图图片 |
| GET / PUT | `/api/settings` | 读/写配置（统一 `prefs` 视图：库级 prefs + machine-global 键 `OMLX_*`/`TEXT_MODEL`/`VISION_MODEL` 合并，密钥 mask；无历史 `"env"` 分组，`tasks/29`） |
| POST | `/api/subtitles/export` | 字幕导出(§3.13)：body `{video_path, out_dir, formats?, language?}`；返回 `job_id`（复用 `/api/jobs/{id}` + SSE） |
| GET | `/api/subtitles/{job_id}` | 取该导出 job 的产出文件路径(完成后) |
| POST | `/api/pick-file` | 原生选**文件**(macOS `choose file`，视频过滤)；对齐已有 `/api/pick-folder` |
| POST | `/api/cut/sessions` | 初剪 Agent(§3.15)：新建会话(可选 title)→ session |
| GET | `/api/cut/sessions` | 会话列表(id/title/updated_at) |
| GET | `/api/cut/sessions/{id}` | 会话详情(消息历史 + 最近 plan) |
| DELETE | `/api/cut/sessions/{id}` | **删除对话**(级联清消息与 plan) |
| POST | `/api/cut/sessions/{id}/messages` | 发用户消息；body `{text, request?}`→ 入队 `cutplan` job(复用 `/api/jobs/{id}` + SSE) |
| GET | `/api/cut/sessions/{id}/plan` | 最近 plan(含 markdown 分镜表渲染) |
| GET | `/api/cut/prompt` | 当前导演 Prompt(自定义或自带默认)：`{prompt, default, is_default}` |
| PUT | `/api/cut/prompt` | body `{prompt}` → 存自定义导演 Prompt(机器全局) |
| DELETE | `/api/cut/prompt` | 重置为自带默认(删除自定义键) |

- API 层**薄**：只做参数校验(pydantic)、调用编排/仓储、序列化。便于用 FastAPI `TestClient` 配合假仓储/假编排器做接口测试。
- 纠正 `roll_type` 写入 `roll_source='manual'`，重扫不被自动判定覆盖（“记住纠正”）。

---

## 7. 前端模块设计（React）

视觉与组件规范见 [`ui-design.md`](./ui-design.md)（深色 token、A/B 类型色、布局）。每个 feature 自洽，只通过 `api/` 客户端与后端通信：

| 模块 | 职责 | 独立测(Vitest + RTL) |
|---|---|---|
| `api/` | 唯一 HTTP 封装(REST + SSE 订阅) | 用 **MSW** 模拟后端响应 |
| `features/gallery` | 缩略图墙、分页/虚拟滚动 | mock API，断言渲染与空态 |
| `features/filters` | 日期/类型/标签筛选 | 断言筛选触发正确请求参数 |
| `features/search` | 全文搜索框与结果 | mock 搜索响应 |
| `features/detail` | 详情面板：简介、可编辑标签、转写、改 A/B、**重新分析按钮** | 断言编辑触发 PATCH/PUT、重分析触发 POST reanalyze、乐观更新 |
| `features/settings` | 源/库文件夹、OMLX 配置 | 表单校验与保存 |
| `features/jobs` | SSE 进度条、逐个完成提示 | mock SSE 事件流断言进度更新 |
| `features/subtitles` (§3.13) | 选成片/选输出文件夹/勾选 iTT·SRT/进度/产出列表 + Reveal | mock pick/export/SSE，断言请求参数与产出渲染 |
| `features/cutplan` (§3.15) | 左对话框(会话列表可删)/右实时分镜表(章节+缩略图)/复制 Markdown/实时进度轨迹/「初剪设置」弹窗(导演 Prompt + 生成选项) | mock 会话 CRUD/发消息/轮询，断言流式回复、分镜渲染、删除会话、初剪设置弹窗读写 `cut_critic_enabled`/`cut_vision_budget`(PUT /settings) |

- **前后端契约**：以 §6 的请求/响应 schema 为准；前端类型从后端 pydantic 模型生成或手写对齐，降低漂移。

---

## 8. 测试策略（汇总）

**测试金字塔**：

1. **后端单元测试（pytest，主力）**
   - 编排器：注入全部假适配器，覆盖 A/B 分支、错误隔离、幂等。
   - Scanner：临时目录 + 内存仓储，覆盖过滤与去重。
   - 仓储：`:memory:` SQLite 跑真实 SQL，覆盖 CRUD/过滤/FTS。
   - LibraryWriter：临时目录真复制，验证只读原文件、目录结构、重名、保时间。
   - API：`TestClient` + 假编排/假仓储，覆盖路由与校验。
   - 全部不带标记，秒级、可进 CI。

2. **后端集成测试（pytest `-m integration`，手动/本机）**
   - 各适配器对真实 ffmpeg / Silero / whisper / OMLX 跑，验证契约。用极短样本素材，放 `tests/integration` 与小 fixtures。

3. **前端单元/组件测试（Vitest + React Testing Library）**
   - 组件行为 + API 交互（MSW 模拟 HTTP/SSE）。

4. **端到端（Playwright，少量关键流程）**
   - 后端以「假适配器 + 预置 DB」启动（不需真模型），跑：扫描 → 看到缩略图 → 按类型/标签筛选 → 编辑标签/纠正 A/B → 搜索命中。

**样本素材**：用户已在 `testVideo/`（gitignore）提供真实素材——A-roll：`MVI_5298.MP4`（Canon，中文解说）；B-roll：`MVI_5368.MP4`（Canon）、`DJI_20260515175239_0097_D.MP4`（DJI 无人机）。集成测试直接引用这些路径（注意是大文件，跑得较慢）。另可再补 1 段无内嵌时间、1 段非白名单扩展名的小样本，验证日期回退与跳过逻辑。

---

## 9. 配置项与默认值

| 配置 | 默认 | 说明 |
|---|---|---|
| `source_folders` | 空 | 用户指定，可多个（JSON） |
| `library_path` | 空 | 复制目标库（JSON） |
| `extensions` | `.mov .mp4 .m4v` | 扫描白名单（JSON） |
| `OMLX_BASE_URL` | `http://localhost:8000/v1` | OMLX 接口（全局配置 / OS env） |
| `OMLX_API_KEY` | 无（必填） | OMLX 鉴权（全局配置 / OS env，不进 git） |
| `text_model` | `Qwen3.6-35B-A3B` | A-roll 简介/标签（JSON） |
| `vision_model` | `Qwen3-VL-8B-Instruct` | B-roll 画面识别(量化在 OMLX 选) |
| `whisper_model` | `large-v3` | 独立 mlx-whisper |
| `broll_frame_count` | `3` | B-roll 均匀抽帧数 |
| `vad_threshold` | `0.15` | speech_ratio ≥ 阈值判 A-roll |
| `worker_concurrency` | `1` | 顺序处理，尊重模型显存 |
| `output_language` | `zh` | AI 简介/描述语言；字幕导出(§3.13)也沿用 |
| `subtitle_default_formats` | `["itt","srt"]` | 字幕导出 UI 默认格式（可选项） |
| `vocal_separation` | `false` | A-roll 转写前是否用 Demucs 去 BGM（JSON）；仅影响之后 scan 的新片。字幕导出强制分离，不受此项影响 |
| `cut_director_mode` | `agent` | 初剪 Agent(§3.15)生成模式：`agent`=按天 scoped 工具环（不收敛回落 staged）/`staged`=每天一次纯 JSON(`tasks/26`)；**初剪页「初剪设置」弹窗可调** |
| `cut_max_tool_rounds` | `24` | 初剪 Agent 单天工具调用环最大轮数护栏（仅 agent 模式生效）；**初剪页「初剪设置」弹窗可调** |
| `cut_vision_budget` | `6` | 初剪 Agent 单次生成内 `inspect_broll`(现场视觉)调用上限；**初剪页「初剪设置」弹窗可调**，`0`=不限(由机器性能决定，JSON) |
| `cut_critic_enabled` | `false` | 初剪 Agent 审片复检：拼好后跑一轮 critic 评主观质量并对点名日期重做一轮(`tasks/28`)；**初剪页「初剪设置」弹窗可调** |
| `cut_lean_token_budget` | `50000` | 初剪 **agent** 模式单日素材目录 **token** 上限（每片段一行精简版，台词按需取）；按真实 token 计（OMLX `/v1/messages/count_tokens`，端点不可用时回退字符估算）；**初剪页「初剪设置」弹窗可调**，范围 1000–200000 |
| `cut_staged_token_budget` | `40000` | 初剪 **staged** 模式单日素材目录 **token** 上限（内联台词，填得更快）；按真实 token 计（同上）；**初剪页「初剪设置」弹窗可调**，范围 1000–200000 |
| `cut_default_aspect_ratio` | `16:9` | 初剪 Agent 默认画面比例（用户可在对话里覆盖） |
| `cut_director_prompt` | （自带默认） | 初剪 Agent 导演 system prompt；用户可在初剪页编辑、存机器全局 `~/.cutfinder/config.json`，含 `{aspect}/{target}/{style}` 占位符；删除即重置回自带默认 |

---

## 10. 环境与部署（一键安装）

> 目标：换机或重装时不用手动折腾 Mac。原生方案——**Docker 不适用**：MLX/OMLX/Whisper 需直接用 Apple Metal GPU，容器内访问不到 Metal，AI 推理只能原生运行。

### 工具分工

| 工具 | 负责 |
|---|---|
| **mise** (`mise.toml`) | 钉死 Python 与 Node 版本，`mise install` 一键装对版本 |
| **uv** (`pyproject.toml` + `uv.lock`) | 后端 Python 虚拟环境 + 锁定依赖，`uv sync` 精确还原 |
| **Brewfile** | 系统级 `ffmpeg`，`brew bundle` 一键装 |
| **npm/pnpm** (`frontend/package.json` + lockfile) | 前端依赖 |
| **Makefile** | 把上面串成少数几条命令 |

OMLX 端点与密钥通过全局配置（`~/.cutfinder/config.json`）或 OS env vars 注入，后端用 `pydantic-settings` 自动读取；缺失则启动时明确报错。OMLX 是独立菜单栏 App，需单独安装并自行加载文本/视觉模型。

### Makefile 目标

| 命令 | 作用 |
|---|---|
| `make setup` | `mise install` → `brew bundle` → `uv sync` → 前端依赖安装 |
| `make dev` | 同时起后端（FastAPI/uvicorn）与前端（Vite dev server） |
| `make models` | 拉取并缓存 `mlx-whisper` 模型（视觉/文本模型在 OMLX 侧加载） |
| `make check-omlx` | 用全局配置/OS env 的端点/密钥探测 OMLX `/v1/models`，确认接口与所需模型就绪 |
| `make test` | 后端 `pytest`（不含集成）+ 前端 `vitest` |
| `make test-integration` | `pytest -m integration`（需本机 ffmpeg/whisper/OMLX 与样本素材） |
| `make e2e` | Playwright（后端以假适配器 + 预置 DB 启动） |

**换机流程**：装好 OMLX App → `git clone` → 在 `~/.cutfinder/config.json`（或 OS env）中填入 OMLX key → `mise install && make setup` → `make check-omlx` → `make dev`。

### 独立测
- Makefile/脚本无需单测；`make check-omlx` 的探测逻辑（解析 `/v1/models`、校验所需模型是否在列）放在一个小函数里，用假 HTTP 响应做单元测试。

---

## 11. 原生 macOS .app 外壳（Swift 包装器）

> 取代现有 shell 脚本启动器（`packaging/launcher.sh` + `scripts/build-app.sh`）。
> 现状痛点：`Contents/MacOS/CutFinder` 是 bash 脚本，Dock 生命周期靠「脚本保持前台 + 转发 SIGTERM」勉强维持，没有标准应用菜单，点 Dock 图标不会重开 UI，且不利于代码签名/公证。
> 目标：用**最小 Swift/AppKit 包装器**取而代之，得到标准菜单、稳定 Dock 生命周期、点 Dock 重开 UI、可签名/公证；并把「开启/关闭服务」与「首次自动安装所有依赖」做成原生体验。
> **设计决策**（已确认）：① UI 用 **WKWebView 内嵌**现有 web 前端（无浏览器、无标签页）；② 服务**启动即自动开启**，可手动停止/重启；③ 首次启动**自动安装本地依赖**（uv / ffmpeg / Python env / whisper+demucs 模型），**OMLX 仅探测 + 引导**（独立菜单栏 App，无法静默安装）。UI 细节见 ui-design §「原生 App 外壳」。

### 11.1 为什么不再用 shell 脚本

`exec` 进 venv 的 Python 会让 macOS 以为 App 退出、移除 Dock tile（脚本里已有此注释告警）。脚本只能「自己留前台 + 后台跑 uvicorn + trap SIGTERM」，本质是绕过 Dock 生命周期，得不到 `NSApplication` 的菜单、reopen、terminate 钩子。换成真正的 Mach-O 可执行（Swift 编译产物）作为 `CFBundleExecutable`，这些都由系统原生提供。

### 11.2 架构与组件

App target 名 `CutFinder`，编译为 `Contents/MacOS/CutFinder`（真 Mach-O，非脚本）。Swift 源码极薄，**业务仍全在 Python 后端 + web 前端**，Swift 只做「进程管理 + 首次安装 + 窗口宿主」。

| 组件 | 职责 |
|---|---|
| `main.swift` | `NSApplication` 引导，装配 delegate |
| `AppDelegate` | 生命周期、菜单、Dock reopen、退出时停服务 |
| `MainWindowController` | 单窗口，宿主 `WKWebView`；在「安装中 / 运行中 / 错误」三态间切换视图 |
| `ServerController` | 用 `Process` 拉起/停止/重启 uvicorn 子进程；健康探测；端口管理 |
| `Provisioner` | 首次安装流程（payload 同步 + 依赖安装 + 模型下载），逐步上报进度 |
| `DependencyChecker` | 探测 uv / ffmpeg / OMLX 是否就绪 |
| `PayloadManager` | 把 bundle 内 `Resources/payload` 同步到可写运行目录（保留 venv/catalog/用户状态） |
| `SetupView` / `ErrorView` | 原生安装进度视图、错误/引导视图（配色沿用设计 token） |

源码与产物布局：

```
packaging/macapp/            # Swift 包装器源码（swiftc 直接编译，无 .xcodeproj）
  main.swift  AppDelegate.swift  MainWindowController.swift
  ServerController.swift  Provisioner.swift  DependencyChecker.swift
  PayloadManager.swift  SetupView.swift  ErrorView.swift
  CutFinder.entitlements     # Hardened Runtime entitlements
packaging/Info.plist.template  # 复用，微调
packaging/{download_whisper.py,download_demucs.py,check_omlx.py}  # Provisioner 复用
scripts/build-app.sh         # 升级：编译 Swift → 组 bundle → 签名 → dmg → 公证
```

> 构建用 **swiftc**（`-framework Cocoa -framework WebKit`）而非 Xcode 工程，贴合「最小包装器」、CI 友好（只需 Command Line Tools）。`packaging/launcher.sh` 淘汰。

### 11.3 进程与 Dock 生命周期模型

- App 进程（Swift）= `CFBundleExecutable`，**永远是前台 owner**；uvicorn 是它的**子进程**，绝不 `exec` 替换自身 → Dock tile 稳定。
- `applicationDidFinishLaunching`：建主窗口 → 跑首次安装（按需）→ 启动服务 → 健康后加载 WKWebView。
- `applicationShouldHandleReopen(_:hasVisibleWindows:)`：点 Dock 图标且无可见窗口 → 重建/显示主窗口（**点 Dock 重开 UI**），返回 `true`。
- 关闭窗口**不**退出 App：服务继续在后台跑，App 留在 Dock；Dock 点击重开。（满足「服务独立于窗口开关」）
- `applicationShouldTerminate` / `applicationWillTerminate`（⌘Q）：先 `ServerController.stop()` 优雅停子进程（SIGTERM→超时 SIGKILL）再退出 → 不留孤儿服务。
- 单实例：若端口已被占（已有实例在跑），探测到健康端点则只重开窗口、不再起第二个服务。

### 11.4 窗口三态（WKWebView 宿主）

`MainWindowController` 是单窗口，按服务状态切换 contentView：

1. **安装中**：显示原生 `SetupView`（步骤清单 + 进度条 + 可折叠日志），Provisioner 实时回调更新。
2. **运行中**：`WKWebView` 加载 `http://127.0.0.1:<PORT>/`（复用后端静态托管的前端构建产物，`CUTFINDER_STATIC_DIR`）。
3. **错误/引导**：原生 `ErrorView`（如 OMLX 不可达、ffmpeg 缺失），含「重试 / 打开日志 / 打开下载页 / 仍然继续」。

WKWebView 配置：仅允许加载本地 `127.0.0.1` 源；外部链接（如 OMLX 下载页）用 `NSWorkspace.open` 走系统浏览器，不在内嵌 webview 打开。

### 11.5 ServerController（开启 / 停止 / 重启）

- 启动：`Process` 运行 `<runtime>/backend/.venv/bin/python -m uvicorn cutfinder.api.app:app --host 127.0.0.1 --port <PORT> --timeout-graceful-shutdown 5`，记录 PID。
- 健康：轮询 `GET /api/library`（复用现有就绪探针）至 200，再切到运行态加载 webview。
- 停止：向子进程发 SIGTERM，超时回落 SIGKILL；菜单项「停止服务」。
- 重启：stop→start，并 `reload` webview；菜单项「重启服务」。
- 端口：默认 5080，`CUTFINDER_PORT` 可覆盖（沿用现状）。
- 状态对外：以 enum `.idle/.installing/.starting/.running/.stopped/.error` 驱动菜单项启用态与（可选）标题栏状态点。

### 11.6 首次安装流程（自动装齐本地依赖）

首次启动（或菜单「重新运行安装」）按序执行，每步在 `SetupView` 一行（待定/进行中/完成/失败）：

1. **PayloadManager**：`rsync` bundle 内 `Resources/payload` → `~/Library/Application Support/CutFinder/app`，`--exclude .venv/__pycache__`，**保留** venv、catalog、用户状态（与现 launcher 一致，bundle 内永不写入 → 利于签名）。
2. **uv**：缺失则 `curl -LsSf https://astral.sh/uv/install.sh | sh`（装到 `~/.local/bin`）。
3. **ffmpeg/ffprobe**：缺失则 `brew install ffmpeg`；无 Homebrew 时不静默装 brew，转「引导」（给 brew.sh 链接 + 命令）。
4. **Python env**：在运行目录 `backend/` 跑 `uv sync --frozen`（回落 `uv sync`），幂等。
5. **模型**：复用 `download_whisper.py`（large-v3）/ `download_demucs.py`（htdemucs），缺则下载、已存在跳过；体量大，进度纳入安装视图。
6. **OMLX 探测**：复用 `check_omlx.py` 逻辑探 `GET <OMLX_BASE_URL>/models` 并校验所需模型在列。**不可达/缺模型** → 不阻断启动，弹引导（说明 + 「打开 OMLX 下载页」「重试」「仍然继续」）。无 OMLX 时扫描仍能做 VAD/转写/缩略图，但 A-roll 简介与 B-roll 打标会失败——引导文案点明此点。
7. 写**版本戳安装完成标记**；后续启动只做快速存在性检查 + `uv sync --frozen`（满足时近乎瞬时），不重复全量安装。

幂等：payload 同步保 venv/catalog；uv sync、模型下载、探测均可重复安全执行。

### 11.7 沙盒 / 签名 / 公证

- **不开 App Sandbox**：要执行外部工具（uv/brew/python）、写 `~/.local`、读用户任意素材文件夹。→ 走 **Developer ID 直分发**（DMG），非 Mac App Store。
- **Hardened Runtime 开启** + entitlements（因运行用户侧 venv 的 Python / MLX / torch，会 JIT、用 Metal、加载未由我们签名的 dylib）：
  - `com.apple.security.cs.allow-jit`
  - `com.apple.security.cs.allow-unsigned-executable-memory`
  - `com.apple.security.cs.disable-library-validation`
- **关键利好**：venv 与模型都建在 **Application Support（bundle 之外）**，不进签名范围、不受 library validation 约束；bundle 内只有 Swift 二进制 + Python 源 + `.icns`，签名简单（只需签 Swift Mach-O，无需 `--deep` 黑魔法）。
- 流程（`build-app.sh`）：`codesign --options runtime --entitlements packaging/macapp/CutFinder.entitlements --sign "Developer ID Application: …"` → `hdiutil` 出 DMG → `xcrun notarytool submit … --wait` → `xcrun stapler staple`。无签名身份时跳过签名步骤，仍可本地出未签名 .app（开发用）。

### 11.8 与后端/前端的接口（零侵入）

- 后端、前端**不改动**：Swift 只消费现有 `GET /api/library`（健康探针）与后端静态托管的前端构建产物。
- 「开启/关闭服务」是控制 uvicorn 子进程，与 web 内的「扫描 / 任务队列」等业务正交。
- 旧 launcher.sh 的所有职责（payload 同步、uv/ffmpeg 自检、起服务、开 UI）都被 Swift 组件 1:1 接管，行为等价但获得原生生命周期。

### 11.9 测试策略

- Swift 层逻辑刻意薄、以编排为主：核心可测点是 **Provisioner 步骤判定**（哪步该装/该跳/该引导）与 **DependencyChecker/OMLX 探测**——后者沿用 §10 已有的 `check-omlx` 纯函数单测（假 HTTP 响应）。
- 进程管理、菜单、Dock reopen 等以**手动验收清单**覆盖（启动即起服务、停止/重启、关窗不退、Dock 重开、⌘Q 不留孤儿、首次安装断网/缺 ffmpeg/缺 OMLX 的引导）。
- 后端/前端既有单测不受影响。

### 11.10 迁移

- 新增 `packaging/macapp/` Swift 源；`scripts/build-app.sh` 升级为「编译 Swift → 组 bundle → 签名 → dmg → 公证」。
- 删除 `packaging/launcher.sh`（职责迁入 Swift）。`Info.plist.template` 保持（`LSUIElement=false` 即常规 Dock App，符合需求）。

---

## 12. 关键决策汇总

- **隔离手段**：六类外部依赖 + 仓储统一抽象为 `Protocol`，真实实现放 `adapters/`，业务逻辑(`pipeline/`)只依赖接口 → 模块可独立替换与测试。
- **测试边界**：单元测试一律 mock 外部依赖（仓储用内存 SQLite、LibraryWriter 用临时真文件，因其轻）；真实模型/视频只在带标记的集成测试出现。
- **进度**：单 worker 顺序处理 + SSE 实时推进度；job 状态持久化以便刷新恢复。
- **幂等与纠正**：指纹去重；手动纠正的 A/B 标 `manual`，重扫不被覆盖。
- **预留扩展点**：需求 8 关键帧建议可复用 `FrameExtractor` + `VisionTagger`；FCP 字幕导出（§3.13）复用 `Transcriber`（加 `language` 提示）+ 纯逻辑格式化器，作为独立工具挂在 Worker/SSE 上，**不改动 per-clip 流水线接口**。

---

## 13. 待办 / 需后续确认

- 前端 UI 视觉与交互细节（缩略图墙布局、详情面板排版）——可在实现阶段配合设计稿确定。
- ~~样本素材由谁提供~~ —— 已解决：用户在 `testVideo/` 提供（A=`MVI_5298`，B=`MVI_5368`/`DJI_...`）。
- ~~是否需要「重新分析单个片段」（re-analyze）按钮~~ —— 已确定加入（见 §3.11、§6 `POST /api/clips/{id}/reanalyze`）。

*本文档为实现前的详细设计，确认后进入实现计划阶段。*
