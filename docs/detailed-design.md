# CutFinder 详细设计文档（Detailed Design）

> 配套需求文档：[`docs/proposal.md`](./proposal.md)。本文件把需求拆成可独立开发、独立测试的模块，给出每个模块的职责、接口、输入输出、依赖与测试方式。
> - **范围**：proposal v1（需求 0–7）。

---

## 1. 设计目标与原则

1. **模块强隔离、可独立测试**：每个模块只做一件事，通过明确接口通信，能脱离其他模块单独测。
2. **外部重依赖全部藏在接口后面**：ffmpeg/ffprobe、Silero VAD、mlx-whisper/Qwen3-ASR+ForcedAligner、OMLX（文本+视觉）都通过 Python `Protocol` 抽象，业务逻辑只依赖接口，测试时注入假实现（fake/mock），不碰真实模型、不跑真实视频。
3. **前后端分离**：后端 FastAPI 提供 REST + SSE，前端 React 只通过 HTTP 通信，两端可各自独立开发与测试。
4. **继承 proposal 的四条硬约束**：原文件只读、拍摄时间永不改、全本地离线、扫描幂等。

---

## 2. 总体架构

分层架构，依赖方向**自上而下、单向**（上层依赖下层接口，下层不知道上层）：

```
┌─────────────────────────────────────────────────────────┐
│  前端 (Vite + React + Tailwind + shadcn/ui)              │
│  缩略图墙 / 筛选 / 搜索 / 详情编辑 / 设置 / 进度条(SSE)   │
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
                          ffmpeg/ffprobe · Silero · mlx-whisper/Qwen3-ASR+ForcedAligner · OMLX
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
│   │   │   ├── qwen_transcriber.py  # Qwen3-ASR + ForcedAligner
│   │   │   ├── demucs_separator.py  # VocalSeparator (Demucs)
│   │   │   ├── omlx_text.py     # OpenAI 客户端 → OMLX 文本模型
│   │   │   ├── omlx_vision.py   # OpenAI 客户端 → OMLX 视觉模型
│   │   │   ├── fs_library.py
│   │   │   └── sqlite_repo.py
│   │   ├── pipeline/
│   │   │   ├── orchestrator.py  # per-clip 流水线(纯逻辑，注入接口)
│   │   │   ├── scanner.py       # 扫描+去重(纯逻辑，注入 probe/repo)
│   │   │   ├── worker.py        # 后台队列+SSE 事件
│   │   │   └── subtitle_exporter.py # 独立工具(§3.13)
│   │   ├── cutplan/             # 初剪导演 Agent(§3.15)
│   │   │   ├── director.py      # 导演逻辑(注入接口，纯编排)
│   │   │   ├── prompts.py       # 双语文案 + tool schema(§3.15)
│   │   │   ├── format.py        # 分镜表格式化(纯逻辑，无 IO)
│   │   │   └── request_parse.py # 自然语言参数解析(正则)
│   │   ├── api/
│   │   │   ├── app.py           # FastAPI 应用装配(依赖注入真实适配器)
│   │   │   ├── routes_*.py
│   │   │   └── sse.py
│   │   └── services/            # 服务层(组装模块)
│   │       └── *
│   └── tests/
│       ├── unit/                # 全 mock，无外部依赖
│       ├── integration/         # @pytest.mark.integration，碰真实依赖
│       └── fakes/               # 各 port 的假实现 + 样本素材
└── frontend/
    ├── src/
    │   ├── api/                 # API 客户端(唯一与后端通信处)
    │   ├── styles/tokens.css     # CSS 变量设计系统(§12)
    │   ├── features/{gallery,filters,search,detail,settings,jobs,subtitles,cutplan}/
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
- **真实实现**：`ffprobe -show_format -show_streams -printformat json`，读 `format.tags.creation_time`（QuickTime）。无内嵌时间则回退 `st_birthtime`（macOS），`date_source="file"`。
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
  - **Qwen3-ASR + Qwen3-ForcedAligner**（经 `mlx-audio` 本地运行）—— `adapters/qwen_transcriber.py`：先按 Silero VAD 把音频切成 ≤ `qwen_max_chunk_s`（默认 60，上限 300，受对齐器约 400 秒时间戳范围限制）的片段，逐段用 Qwen3-ASR 出准确中文/中英文本、用 ForcedAligner 出逐字时间戳，偏移回整段时间轴后再归并成字幕 cue。中文更准且时间轴不漂移；OMLX 无法经 HTTP 托管对齐器，故必须本地跑，模型下载到 `models/qwen/`。该选择作用于所有 A-roll 语音处理（编目转写、关键帧、字幕导出）。
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
      def search(self, q: str) -> list[ClipSummary]: ...       # 转写全文/画面描述
      def set_tags(self, clip_id: int, tags: list[Tag]) -> None: ...
      def correct_roll(self, clip_id: int, roll: RollType) -> None: ...
      def update_analysis(self, clip_id: int, r: AnalysisResult) -> None: ...  # re-analyze
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
- **重新分析单个片段（re-analyze）**：对已入库片段强制重跑 AI 分析（VAD→A/B、转写+总结 / 抽帧+视觉），用于换模型或结果不理想时刷新。语义：
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

> 与 per-clip 流水线**完全解耦**：输入是一段**已剪辑完成的成片**（不一定在素材库里），**重新转写**对齐成片自己的时间轴，导出 **iTT（FCP 原生）+ SRT**，**不入库、不分类、不复制源视频**。

- **职责**：成片 → `mlx-whisper` 转写（按成片口语语言）→ 格式化为 iTT/SRT → 写入用户选定的输出文件夹。
- **复用**：`MetadataProbe`（`fps`/`duration`）、`Transcriber`（`Transcript{full_text, segments:[Segment]}`）、Worker 队列 + SSE、`output_language` 配置、`/api/open`。
- **语言**：只转写、不翻译。`output_language` 表示成片本身的口语语言（用户自知）；`Transcriber.transcribe` 增 `language: str | None=None`，把它作为 `mlx_whisper` 的 `language` 提示传入（`zh`→中文、`en`→英文），并写入字幕 `xml:lang`。不引入任何翻译（中文成片导出英文字幕等需求留作将来）。
- **纯逻辑格式化**（`subtitle/format.py`，无 IO）：
  ```python
  def to_srt(segments: list[Segment]) -> str: ...                       # HH:MM:SS,mmm
  def to_itt(segments: list[Segment], *, language: str, fps: float) -> str: ...  # TTML
  ```
- **服务**（`pipeline/subtitle_exporter.py`，注入接口）：
  ```python
  def export(self, video_path: Path, out_dir: Path, formats: list[str], language: str) -> list[Path]:
      # probe(fps) → transcribe(language) → 写 <名>.<lang>.{itt,srt}（同名不覆盖）→ 返回路径
  ```
- **Worker**：新增 job kind `subtitle`，payload `SubtitleRequest{video_path, out_dir, formats, language}`；产出路径放内存结果存储（避免改 DB schema），由 `GET /api/subtitles/{job_id}` 读取。
- **硬约束**：源视频只读（绝不改名/改写）；只在选定文件夹新建字幕文件。
- **去 BGM**（见 §3.14）：成片往往混了 BGM，本工具的 transcriber 恒注入 `VocalSeparator`、强制分离后再转写。
- **进度同步**：`export(..., on_progress)` 透传单一 0..1 进度；transcriber 内部把分离 [0, W] + 转写 [W, 1] 合成（W≈0.4），进度来自拦截 Demucs/mlx-whisper 各自的 tqdm。worker 把 subtitle job 改 `total=100`、节流写 done + SSE，前端渲染真实进度条。
- **iTT 决策**：TTML + `ttp:timeBase="media"` + HH:MM:SS.mmm 时钟码；fps 读取备用。验收须真机导入 Final Cut Pro 验证。
- **独立测**：格式化用黄金串（时码边界/转义/空分段）；服务注入假 probe/transcriber，断言把 `language`（zh/en）透传给 transcribe、按 formats 产出。

### 3.14 VocalSeparator（转写前人声分离，适配器）

> 治理 BGM 污染 transcript：whisper 前抽出人声干声、扔掉伴奏。

- **接口**：
  ```python
  class VocalSeparator(Protocol):
      def isolate(self, path: Path) -> np.ndarray: ...   # whisper 就绪的 16k 单声道 float32
  ```
- **真实实现**：`DemucsSeparator`（`adapters/demucs_separator.py`）——
  1. ffmpeg 抽 **44.1kHz 立体声 f32**（Demucs 原生采样率，不能用 16k）；
  2. `demucs.api.Separator("htdemucs", device=<mps|cpu>)` 分离，取 `separated["vocals"]`；
  3. 下混单声道 + 重采样 **16kHz** → `np.float32`（与 whisper 输入一致，drop-in）。
- **接线**：构造一个共享 `DemucsSeparator`；字幕导出 transcriber 恒注入（强制），A-roll orchestrator transcriber 仅当 `vocal_separation=true` 才注入（默认关）。
- **依赖**：`demucs`；模型懒加载缓存到实例，device 自动选 MPS 回落 CPU。
- **独立测**：单测用假 separator（断言其输出进 whisper、抛异常时回落）；`DemucsSeparator` 走集成测试（真模型，含 BGM 样本）。

### 3.15 CutDirector（初剪导演 Agent，独立工具——v1 之外）

> 在已编目素材库之上，通过多轮对话，依据用户给的日期范围 / 目标时长 / 风格 / 节奏 / 画面比例，产出一份精确到片段内 in/out 的文字分镜表（A-roll 叙事主线 + B-roll 插空），供用户照搬到剪辑软件。不渲染、不导出剪辑工程（FCPXML 留作后续）。

- **架构**：把"会算错、要稳定"的部分交给确定性代码；把"需要创意"的部分交给 LLM 工具调用环。LLM 跑飞时由确定性脚手架 + 护栏兜底。
- **复用**：`CatalogRepository`（检索编目 + transcript segments + 关键帧）、`VisionTagger`+`FrameExtractor`（现场看 B-roll）、现有 OMLX 文本 client。
- **工具集**（`ports/cutplan.py`，LLM 只能调这些）：
  ```python
  class FootageRetriever(Protocol):
      def search_footage(self, date_from, date_to, roll=None, tags=None, query=None) -> list[ClipBrief]: ...
      def get_clip_detail(self, clip_id: int) -> ClipDetail: ...   # transcript segments + 关键帧
  class BrollInspector(Protocol):
      def inspect_broll(self, clip_id: int) -> VisionResult: ...   # 现场抽帧调 Qwen3-VL
  class LLMAgentClient(Protocol):
      def run_tools(self, messages, tools) -> AgentStep: ...        # tool_calls 或 final content
      def complete(self, messages) -> str: ...                       # 纯补全（staged 模式）
      def count_tokens(self, messages) -> int | None: ...           # token 计数（按真实分词器）
  ```
- **in/out 时间码来源**：**A-roll 主线** in/out = 所选 transcript segment 的边界（让 LLM 按 segment 序号选段，映射回 `start_s/end_s`）；**B-roll 插空**优先用已有关键帧切点，没有则取默认窗口，必要时 `inspect_broll` 抽帧确认。
- **护栏**：最大工具轮数 `cut_max_tool_rounds`（默认 24）；时长校验 `sum(out_s-in_s)` ∈ `[target_min_s, target_max_s]`，超/欠回灌一轮；视觉调用预算 `cut_vision_budget`（默认 6，设 0 = 不限）。时长累计与区间校验全走代码。
- **纯逻辑格式化**（`cutplan/format.py`，无 IO）：按章节（=拍摄日期）分组输出 Markdown 分镜表。
- **编排**：`handle_message(session_id, user_text)` 跑工具调用环 + 护栏，产 `CutPlan`；refine 轮把既有 plan + 对话历史作为上下文重跑相关步骤。
- **会话持久化**：新表 `cut_sessions`/`cut_messages`/`cut_plans`（见 §5），可重开、可删除。
- **Worker**：新增 job kind `cutplan`，经 SSE 推工具活动 + 助手 token + plan ready 事件。
- **硬约束**：全程只读编目与副本，不碰源文件、不渲染、不联网；素材须先入库。
- **首要风险**：Qwen3.6 本地 function-calling 不收敛——已退化为「分阶段受限调用」并设为默认：检索由 Director 用代码完成，再把紧凑素材清单交给模型结构化补全分镜表 JSON。
- **按天 mini-agent**：每个拍摄日期跑一个 scoped 工具调用环——只给 `get_clip_detail`/`inspect_broll`/`emit_plan`，不给 `search_footage`（当天素材已确定性检索好喂进上下文）。开关 `cut_director_mode`（agent/staged，默认 agent）；含每日去重护栏 + round-cap 半程催收。
- **实时进度**：Director 把逐天/逐片段进度串与已完成日期的部分 plan 写进 store，前端 `resumePoll` 轮询增量读取——已完成日期分镜先渲染。
- **refine 按日期合并**：以旧 plan 为基底建 `merged`，本轮只重做范围内日期——成功覆盖该天、失败保留旧那天。
- **审片 critic agent**（默认关 `cut_critic_enabled`）：全片拼好后跑一次 critic LLM 调用，只评主观质量（节奏松紧/叙事连贯/A-roll 主线与 B-roll 空镜配比），输出结构化修订意见。
- **多片段日 tool 收口修复**：agent 用精简版上下文（每片段一行 + `[有台词]`），staged 仍用完整版；回落时带入已勘察 B-roll 画面描述。
- **逐次生成参数**：`cut_director_mode`、`cut_max_tool_rounds`、`cut_critic_enabled`、`cut_vision_budget` 从全局设置页移到初剪页面「初剪设置」弹窗。
- **token 上限**：`cut_lean_token_budget`（agent，默认 50000）/ `cut_staged_token_budget`（staged，默认 40000），按真实 token 计。
- **双语支持**：`ui_language`（默认 `en`）控制界面语言与初剪文案；导演/critic prompt 按 `_ZH`/`_EN` 两版切换。
- **独立测**：格式化用黄金串（章节/缩略图引用/时长尾注）；Director 注入假 LLMAgentClient + 假工具，断言 A/B 选段、时长护栏回灌、按天 agent 收口 + 回落、refine 合并。分镜质量不可自动化验收——靠真机抽查。

---

## 4. 外部依赖与 Mock 策略（独立测试的关键）

| 接口(Port) | 真实适配器 | 单元测试替身 | 集成测试(可选, `@pytest.mark.integration`) |
|---|---|---|---|
| MetadataProbe | ffprobe | 返回固定 `VideoMetadata` | 对样本 `.mov` 真解析 |
| ThumbnailMaker/FrameExtractor | ffmpeg | 返回预置图片路径 | 对样本视频真抽帧 |
| SpeechDetector | Silero VAD | 返回设定 `speech_ratio` | 有声/无声样本各一 |
| Transcriber | mlx-whisper / Qwen3-ASR+ForcedAligner | 返回固定 `Transcript` | 短中文语音样本 |
| VocalSeparator | Demucs (`htdemucs`) | 返回固定干声数组 | 含 BGM 样本，验证去伴奏 |
| Summarizer | OMLX 文本 | 返回固定 `SummaryResult` | 需本机 OMLX |
| VisionTagger | OMLX 视觉 | 返回固定 `VisionResult` | 需本机 OMLX |
| LibraryWriter | shutil 复制 | 真跑(轻，临时目录) | — |
| CatalogRepository | SQLite | 内存 SQLite 真跑 | — |

**原则**：单元测试默认 `pytest`（不带标记）全程不碰真实模型/视频/网络，CI 可跑、秒级完成；集成测试打 `integration` 标记，`pytest -m integration` 在本机手动跑。

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

-- 初剪导演 Agent 会话
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

**表说明：**

| 表 | 用途 |
|---|---|
| `clips` | 片段主表，每文件一条记录（指纹去重），含元数据/A-B-roll判定/缩略图路径 |
| `tags` | 片段标签，自动或手动来源，级联删除 |
| `transcripts` | A-roll 转写全文 + segment 数组，与 clips 1:1 级联删除 |
| `jobs` | 扫描/分析任务状态（total/done/error），刷新页可恢复进度 |
| `clips_fts` | FTS5 全文搜索虚拟表，索引 summary + description + transcript |
| `cut_sessions` / `cut_messages` / `cut_plans` | 初剪 Agent 会话、消息历史与分镜表，级联删除 |

**位置：** `<库>/.cutfinder/catalog.sqlite`，缩略图在 `<库>/.cutfinder/thumbnails/`。

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
| GET / PUT | `/api/settings` | 读/写配置（统一 `prefs` 视图：库级 prefs + machine-global 键合并，密钥 mask） |
| POST | `/api/subtitles/export` | 字幕导出(body `{video_path, out_dir, formats?, language?}`)；返回 `job_id` |
| GET | `/api/subtitles/{job_id}` | 取该导出 job 的产出文件路径(完成后) |
| POST | `/api/pick-file` | 原生选文件(macOS `choose file`)；对齐已有 `/api/pick-folder` |
| POST | `/api/cut/sessions` | 初剪 Agent：新建会话(可选 title)→ session |
| GET | `/api/cut/sessions` | 会话列表(id/title/updated_at) |
| GET | `/api/cut/sessions/{id}` | 会话详情(消息历史 + 最近 plan) |
| DELETE | `/api/cut/sessions/{id}` | **删除对话**(级联清消息与 plan) |
| POST | `/api/cut/sessions/{id}/messages` | 发用户消息；body `{text, request?}`→ 入队 `cutplan` job |
| GET | `/api/cut/sessions/{id}/plan` | 最近 plan(含 markdown 分镜表渲染) |
| GET | `/api/cut/prompt` | 当前导演 Prompt(自定义或自带默认)：`{prompt, default, is_default}` |
| PUT | `/api/cut/prompt` | body `{prompt}` → 存自定义导演 Prompt(机器全局) |
| DELETE | `/api/cut/prompt` | 重置为自带默认(删除自定义键) |

- API 层**薄**：只做参数校验(pydantic)、调用编排/仓储、序列化。
- 纠正 `roll_type` 写入 `roll_source='manual'`，重扫不被自动判定覆盖（"记住纠正"）。

---

## 7. 前端模块设计（React）

视觉与组件规范见本章 §12 UI 设计系统。每个 feature 自洽，只通过 `api/` 客户端与后端通信：

| 模块 | 职责 | 独立测(Vitest + RTL) |
|---|---|---|
| `api/` | 唯一 HTTP 封装(REST + SSE 订阅) | 用 **MSW** 模拟后端响应 |
| `features/gallery` | 缩略图墙、分页/虚拟滚动 | mock API，断言渲染与空态 |
| `features/filters` | 日期/类型/标签筛选侧栏 | 断言筛选触发正确请求参数 |
| `features/search` | 全文搜索框与结果高亮 | mock 搜索响应 |
| `features/detail` | 详情面板：简介、可编辑标签、转写、改 A/B、重新分析按钮 | 断言编辑触发 PATCH/PUT、重分析触发 POST reanalyze、乐观更新回滚 |
| `features/settings` | 源/库文件夹、OMLX 配置表单 | 表单校验与保存，`check-omlx` 状态探测 |
| `features/jobs` | SSE 进度条、逐个完成提示(toast) | mock SSE 事件流断言进度更新 |
| `features/subtitles` (§3.13) | 选成片/选输出文件夹/勾选 iTT·SRT/进度条/产出列表 + Reveal | mock pick/export/SSE，断言请求参数与产出渲染 |
| `features/cutplan` (§3.15) | 左对话框(会话列表可删)/右实时分镜表/复制 Markdown/初剪设置弹窗 | mock 会话 CRUD/发消息/轮询，断言流式回复、分镜渲染、设置弹窗读写 |

---

## 8. 测试策略（汇总）

**测试金字塔：**

1. **后端单元测试（pytest，主力）**
   - 编排器：注入全部假适配器，覆盖 A/B 分支、错误隔离、幂等。
   - Scanner：临时目录 + 内存仓储，覆盖过滤与去重。
   - 仓储：`:memory:` SQLite 跑真实 SQL，覆盖 CRUD/过滤/FTS。
   - LibraryWriter：临时目录真复制，验证只读原文件、目录结构、重名、保时间。
   - API：`TestClient` + 假编排/假仓储，覆盖路由与校验。
   - 全部不带标记，秒级、可进 CI。

2. **后端集成测试（pytest `-m integration`，手动/本机）**
   - 各适配器对真实 ffmpeg / Silero / whisper/Qwen3-ASR / OMLX 跑，验证契约。用极短样本素材。

3. **前端单元/组件测试（Vitest + React Testing Library）**
   - 组件行为 + API 交互（MSW 模拟 HTTP/SSE）。

4. **端到端（Playwright，少量关键流程）**
   - 后端以「假适配器 + 预置 DB」启动，跑：扫描 → 看到缩略图 → 按类型/标签筛选 → 编辑标签/纠正 A/B → 搜索命中。

**样本素材：** `testVideo/`（gitignore）—— A-roll：`MVI_5298.MP4`；B-roll：`MVI_5368.MP4`、`DJI_20260515175239_0097_D.MP4`。集成测试直接引用这些路径（大文件跑得较慢）。另可补 1 段无内嵌时间、1 段非白名单扩展名的小样本。

---

## 9. 配置项与默认值

| 键名 | 来源 | 默认值 | 说明 |
|---|---|---|---|
| `source_folders` | JSON | 空列表 | 用户指定，可多个文件夹路径 |
| `library_path` | JSON | 空字符串 | 复制目标库目录 |
| `extensions` | JSON | `.mov .mp4 .m4v` | 扫描白名单扩展名（空格分隔）|
| `OMLX_BASE_URL` | OS env / 全局配置 | `http://localhost:8000/v1` | OMLX API 端点（必填）|
| `OMLX_API_KEY` | OS env / 全局配置 | （无） | OMLX API 密钥（必填，不进 git）|
| `text_model` | JSON | `Qwen3.6-35B-A3B` | A-roll 简介/标签用文本模型名（OMLX）|
| `vision_model` | JSON | `Qwen3-VL-8B-Instruct` | B-roll 画面识别用视觉模型名（OMLX）|
| `whisper_model` | JSON | `large-v3` | mlx-whisper 模型名（仅 whisper 引擎时生效）|
| `transcription_engine` | JSON | `whisper` | 语音转写引擎：`whisper`(mlx-whisper) / `qwen`(Qwen3-ASR+ForcedAligner)|
| `broll_frame_count` | JSON | `3` | B-roll 均匀抽帧数（默认每段 3 张）|
| `vad_threshold` | JSON | `0.15` | speech_ratio ≥ 阈值判 A-roll（范围 0~1）|
| `worker_concurrency` | JSON / env | `1` | 顺序处理，尊重模型显存（OMLX 负责换模型）|
| `output_language` | JSON | `zh` | AI 简介/描述语言；字幕导出也沿用此值（zh=en）|
| `ui_language` | JSON(机器全局) | `en` | 界面/初剪文案语言（EN/ZH），与 output_language 独立；前端 PUT /settings 持久化 |
| `subtitle_default_formats` | JSON | `["itt","srt"]` | 字幕导出 UI 默认格式选项 |
| `vocal_separation` | JSON | `false` | A-roll 转写前是否用 Demucs 去 BGM；仅影响之后 scan 的新片。字幕导出强制分离不受此项影响 |
| `qwen_max_chunk_s` | JSON | `60` | Qwen3-ASR 单段最大时长（秒，上限 300）|
| `cut_director_mode` | JSON(初剪页弹窗) | `agent` | 初剪 Agent 生成模式：`agent`=按天 scoped 工具环 / `staged`=每天一次纯 JSON |
| `cut_max_tool_rounds` | JSON(初剪页弹窗) | `24` | 初剪 Agent 单天工具调用环最大轮数（仅 agent 模式）|
| `cut_vision_budget` | JSON(初剪页弹窗) | `6` | 初剪 Agent inspect_broll 调用上限；0 = 不限（由机器性能决定）|
| `cut_critic_enabled` | JSON(初剪页弹窗) | `false` | 初剪 Agent 审片复检开关：拼好后跑一轮 critic 评主观质量 |
| `cut_lean_token_budget` | JSON(初剪页弹窗) | `50000` | 初剪 **agent** 模式单日素材目录 token 上限（精简版上下文）；范围 1000–200000 |
| `cut_staged_token_budget` | JSON(初剪页弹窗) | `40000` | 初剪 **staged** 模式单日素材目录 token 上限（完整版上下文，内联台词）；范围 1000–200000 |
| `cut_default_aspect_ratio` | JSON(初剪页弹窗) | `16:9` | 初剪 Agent 默认画面比例（用户可在对话中覆盖）|
| `cut_director_prompt` | JSON(机器全局) | （自带默认 `_ZH`/`_EN`） | 初剪 Agent 导演 system prompt；用户可编辑，删除即重置回默认。含 `{aspect}/{target}/{style}` 占位符 |

---

## 10. 环境与部署（一键安装）

> **Docker 不适用**：MLX/OMLX/Whisper 需直接用 Apple Metal GPU，容器内访问不到 Metal。

### 工具分工

| 工具 | 负责 |
|---|---|
| **mise** (`mise.toml`) | 钉死 Python 与 Node 版本，`mise install` 一键装对版本 |
| **uv** (`pyproject.toml` + `uv.lock`) | 后端 Python 虚拟环境 + 锁定依赖，`uv sync` 精确还原 |
| **Brewfile** | 系统级 `ffmpeg`，`brew bundle` 一键装 |
| **npm/pnpm** (`frontend/package.json`) | 前端依赖 |
| **Makefile** | 把上面串成少数几条命令 |

OMLX 端点与密钥通过全局配置（`~/.cutfinder/config.json`）或 OS env vars 注入，后端用 `pydantic-settings` 自动读取；缺失则启动时明确报错。

### Makefile 目标

| 命令 | 作用 |
|---|---|
| `make setup` | `mise install` → `brew bundle` → `uv sync` → 前端依赖安装 |
| `make dev` | 同时起后端（FastAPI/uvicorn）与前端（Vite dev server）|
| `make models` | 拉取并缓存 `mlx-whisper` / demucs 模型（视觉/文本在 OMLX 侧加载）|
| `make check-omlx` | 探测 OMLX `/v1/models`，确认接口与所需模型就绪（含纯函数单测）|
| `make test` | 后端 `pytest`（不含集成）+ 前端 `vitest`|
| `make test-integration` | `pytest -m integration`（需本机 ffmpeg/whisper/Qwen3-ASR/OMLX 与样本素材）|
| `make e2e` | Playwright（后端以假适配器 + 预置 DB 启动）|

**换机流程：** 装好 OMLX App → `git clone` → 在 `~/.cutfinder/config.json`（或 OS env）中填入 OMLX key → `mise install && make setup` → `make check-omlx` → `make dev`。

---

## 11. 原生 macOS .app 外壳（Swift 包装器）

> 取代现有 shell 脚本启动器。用**最小 Swift/AppKit 包装器**，得到标准菜单、稳定 Dock 生命周期、点 Dock 重开 UI。
> **设计决策**：① UI 用 WKWebView 内嵌现有 web 前端；② 服务启动即自动开启，可手动停止/重启；③ 首次启动自动安装本地依赖（uv / ffmpeg / Python env），语音模型懒加载下载，OMLX 仅探测 + 引导。

### 11.1 为什么不再用 shell 脚本

`exec` 进 venv 的 Python 会让 macOS 以为 App 退出、移除 Dock tile。换成真正的 Mach-O 可执行（Swift 编译产物）作为 `CFBundleExecutable`，由系统原生提供菜单、reopen、terminate 钩子。

### 11.2 架构与组件（7 Swift 类）

| 组件 | 职责 |
|---|---|
| `main.swift` | `NSApplication` 引导，装配 delegate |
| `AppDelegate` | 生命周期、菜单、Dock reopen、退出时停服务 |
| `MainWindowController` | 单窗口，宿主 WKWebView；在「安装中 / 运行中 / 错误」三态间切换 |
| `ServerController` | 用 Process 拉起/停止/重启 uvicorn 子进程；健康探测；端口管理 |
| `Provisioner` | 首次安装流程（payload 同步 + 依赖安装 + 模型下载），逐步上报进度 |
| `DependencyChecker` | 探测 uv / ffmpeg / OMLX 是否就绪 |
| `PayloadManager` | 把 bundle 内 Resources/payload 同步到可写运行目录（保留 venv/catalog/用户状态）|

源码布局：
```
packaging/macapp/            # Swift 包装器（swiftc 直接编译，无 .xcodeproj）
  main.swift AppDelegate.swift MainWindowController.swift
  ServerController.swift Provisioner.swift DependencyChecker.swift
  PayloadManager.swift SetupView.swift ErrorView.swift
  CutFinder.entitlements     # Hardened Runtime entitlements
```

### 11.3 进程与 Dock 生命周期模型

- App 进程（Swift）= `CFBundleExecutable`，**永远是前台 owner**；uvicorn 是它的子进程。
- `applicationDidFinishLaunching`：建主窗口 → 跑首次安装（按需）→ 启动服务 → 健康后加载 WKWebView。
- `applicationShouldHandleReopen`：点 Dock 图标且无可见窗口 → 重建/显示主窗口（**点 Dock 重开 UI**）。
- 关闭窗口不退出 App：服务继续在后台跑，App 留在 Dock。
- `applicationShouldTerminate`（⌘Q）：先停服务再退出 → 不留孤儿。
- 单实例：端口被占时探测健康端点则只重开窗口、不再起第二个服务。

### 11.4 窗口三态（WKWebView 宿主）

`MainWindowController` 按服务状态切换 contentView：
1. **安装中**：原生 `SetupView`（步骤清单 + 进度条 + 可折叠日志）。
2. **运行中**：`WKWebView` 加载 `http://127.0.0.1:<PORT>/`（复用后端静态托管的前端构建产物）。
3. **错误/引导**：原生 `ErrorView`（如 OMLX 不可达、ffmpeg 缺失），含「重试 / 打开日志 / 仍然继续」。

### 11.5 ServerController（开启 / 停止 / 重启）

- 启动：`Process` 运行 venv python uvicorn，记录 PID。
- 健康：轮询 `GET /api/library`（复用现有就绪探针）至 200。
- 停止：SIGTERM → 超时 SIGKILL；菜单项「停止服务」。
- 重启：stop→start，reload webview。
- 端口：默认 5080，`CUTFINDER_PORT` 可覆盖。
- 状态 enum：`.idle/.installing/.starting/.running/.stopped/.error`，驱动菜单项启用态与标题栏状态点。

### 11.6 首次安装流程（7 步）

| 步骤 | 内容 |
|---|---|
| 1. PayloadManager | `rsync` bundle Resources/payload → Application Support/CutFinder/app，保留 venv/catalog |
| 2. uv | 缺失则 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| 3. ffmpeg/ffprobe | 缺失则 `brew install ffmpeg`；无 Homebrew → 引导（给链接）|
| 4. Python env | `uv sync --frozen`，幂等 |
| 5. 模型预热 | **仅 demucs**（~80MB）；语音模型 whisper/Qwen3-ASR 首次转写时懒加载下载 |
| 6. OMLX 探测 | `GET <OMLX_BASE_URL>/models`，不可达 → 引导（不阻断启动）|
| 7. 版本戳标记完成 | 后续只做快速存在性检查 + uv sync，不重复全量安装 |

### 11.7 沙盒 / 签名 / 公证

- **不开 App Sandbox**：要执行外部工具、写 `~/.local`。走 Developer ID 直分发（DMG）。
- **Hardened Runtime**：JIT、Metal、加载未签名 dylib 需要 entitlements。
- **关键利好**：venv 与模型在 Application Support（bundle 之外），不进签名范围；只需签 Swift Mach-O。
- **流程**：`codesign --options runtime ... → hdiutil 出 DMG → notarytool submit … –wait → stapler staple`。

### 11.8–11.9 测试策略

- Swift 层逻辑薄、以编排为主：核心可测点是 Provisioner 步骤判定与 DependencyChecker/OMLX 探测（沿用 §10 check-omlx 纯函数单测）。
- 进程管理、菜单等以手动验收清单覆盖。

---

## 12. UI 设计系统（合并自 ui-design.md）

> **对接任务**：前端 feature 开发。**技术栈**：Vite + React + Tailwind + shadcn/ui。

### 12.1 设计方向

- **近黑面板、内容为王**：界面用低饱和中性深灰，让视频缩略图成为视觉焦点（参考 FCP / DaVinci / Premiere）。
- **一个主色 + 两个内容色**：主交互色 = 靛蓝；A-roll = 琥珀、B-roll = 青。三者色相分离，且 A/B 永远**颜色 + 图标 + 文字**三重表达（可访问性 `color-not-only`）。
- **数据用等宽字**：时间码、时长、分辨率、文件路径用等宽字（`number_tabular`，防跳动）。
- **克制的动效**：150–250ms，仅状态过渡与进度，尊重 `prefers-reduced-motion`。

### 12.2 颜色 Token（浅色为默认主题，深色可切换）

#### 表面 / 层级（冷中性灰）
| Token | 浅色值 | 用途 |
|---|---|---|
| `--bg-canvas` | `#EEF0F3` | 最底画布（浅灰，非纯白）|
| `--surface-1` | `#FFFFFF` | 侧栏 / 顶栏 / 面板（白，浮于画布）|
| `--surface-2` | `#F6F7F9` | 卡片 / 输入框 |
| `--surface-3` | `#E4E7EC` | hover / 抬起（浅模式下加深一档）|
| `--border` | `#D8DCE2` | 描边 / 分隔线 |
| `--border-strong` | `#BCC2CB` | 输入聚焦前描边 |

深色覆盖：
| Token | `#0E0F11` → 画布 / `#16181B` → surface-1 / `#1E2125` → surface-2 |
|---|---|

#### 文字（on `--surface-1`）
| Token | 浅色值 | 对比度(on surface-1) |
|---|---|---|
| `--text-primary` | `#1A1D21` | ~16:1 ✅ |
| `--text-secondary` | `#4B5563` | ~7.4:1 ✅ |
| `--text-muted` | `#6B7280` | ~4.8:1 ✅（仅次要元信息）|

深色覆盖：
| Token | 值 | 对比度(on surface-1 #16181B) |
|---|---|---|
| `--text-primary` | `#F2F4F7` | ~15:1 ✅ |
| `--text-secondary` | `#A4ACB9` | ~7:1 ✅ |
| `--text-muted` | `#6B7280` | ~4.6:1 ✅ |

#### 主色（交互 / CTA / 聚焦）
| Token | 浅色值 | 用途 |
|---|---|---|
| `--primary` | `#5256E0`（白字 ~4.7:1 ✅） | 按钮填充 / 链接 / 焦点环 |
| `--primary-hover` | `#4146C4`（加深） | hover |
| `--primary-press` | `#383DB0` | active |
| `--primary-fg` | `#FFFFFF` | 主色按钮上的文字 |
| `--primary-soft` | `#5256E0`@12% | 选中底色 / 高亮区 |

深色覆盖：
| Token | `#6366F1` → primary / `#7077F2` → hover / `#525AE0` → press |
|---|---|

#### 内容类型（A/B-roll / 照片）
| Token | 深色值 | 浅色值 | 含义 | 图标 |
|---|---|---|---|---|
| `--roll-a` | `#F59E0B` 琥珀 | `#B45309` 深琥珀 (~5.3:1 ✅) | A-roll（有解说）| 麦克风 |
| `--roll-b` | `#2DD4BF` 青 | `#0F766E` 深青 (~5.0:1 ✅) | B-roll（纯画面）| 胶片/视频 |
| `--roll-photo` | `#F472B6` 玫红 | `#BE185D` (~>4.5:1) | 照片 | 图片 |

每个 token 均配 `*-soft` 底色变量（如 `--roll-a-soft`）。

#### 语义状态
| Token | 深色值 / 浅色值 | 用途 |
|---|---|---|
| `--success` | `#22C55E` / `#15803D` (~4.7:1 ✅) | 处理完成 / 成功 |
| `--warning` | `#F59E0B` / `#B45309` (~5.3:1 ✅) | 日期来源不确定等提醒 |
| `--danger` / `--error` | `#EF4444` / `#DC2626` (~4.5:1 ✅) | 错误 / 破坏性操作 |
| `--processing` | `#6366F1` / `#5256E0`（同主色） | 处理中 |

**切换交互**：顶栏 ghost 图标按钮（深色态显「太阳」点亮浅色，浅色态显「月亮」切深色），写入 `localStorage`（key `cutfinder-theme`，默认 `light`）。`index.html` 内联早执行脚本在首帧前设 `data-theme`，避免 FOUC。

### 12.3 字体 Token

- **UI 字体**：`Inter`（拉丁，密集 UI）+ `PingFang SC`（中文，macOS 原生）。
- **等宽字体**：`JetBrains Mono`（时间码 / 时长 / 分辨率 / 路径）。
- **字体栈**：
  ```css
  --font-ui:   "Inter", "PingFang SC", -apple-system, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
  ```
- **字号阶梯**（桌面工具偏密，base=14）：

| Token | px | 用途 | line-height |
|---|---|---|---|
| `--text-xs` | 12 | 元信息 / 角标 | 1.4 |
| `--text-sm` | 13 | 标签 / 次要 | 1.5 |
| `--text-base` | 14 | UI 正文 | 1.5 |
| `--text-md` | 15 | **阅读内容**（简介/转写）| 1.6 |
| `--text-lg` | 16 | 区块标题 | 1.4 |
| `--text-xl` | 20 | 面板标题 | 1.3 |
| `--text-2xl` | 24 | 页面标题 | 1.25 |

字重：正文 400 / 标签 500 / 标题 600。阅读型内容用 `--text-md` + line-height 1.6，行宽控制在 60–75 字符。

### 12.4 间距 / 圆角 / 阴影

- **间距**（4px 基准）：`4 8 12 16 20 24 32 40 48`。布局用 8 的倍数，组件内边距用 12/16。
- **圆角**：`--radius-sm: 6px`（按钮/输入/chip）、`--radius-md: 8px`（卡片/缩略图）、`--radius-lg: 10px`（面板/弹窗）。
- **阴影**：深色下克制，靠描边 + 轻抬起。卡片 `--shadow-1: 0 1px 2px rgba(0,0,0,.4)`；弹层/抽屉 `--shadow-2: 0 8px 24px rgba(0,0,0,.5)`。弹窗背景用 backdrop blur（表示可点击外部关闭）。

### 12.5 组件规范

#### 按钮
| 变体 | 样式 | 用途 |
|---|---|---|
| Primary | `--primary` 填充 + 白字 | 每屏唯一主操作（扫描 / 保存）|
| Secondary | `--surface-2` + `--border` 描边 | 次要操作 |
| Ghost | 透明 + hover 显 `--surface-3` | 工具栏图标按钮（≥ 32×32）|
| Danger | `--danger` 描边/填充 | 破坏性操作（与主操作分离）|

- 高度：`sm:28 / md:32(默认) / lg:36`。
- 状态：hover 提亮一档；active `scale .98`；disabled `opacity .4` + 禁用光标。**焦点 2px `--primary` 环 + 2px offset**（不可移除）。异步操作时按钮内置 spinner 并禁用。

#### 标签 Chip
- **基础**：`--surface-2` 底 + `--text-secondary`，圆角 sm。
- **A/B 类型徽标**：同色描边 + 12px 图标 + 文字「A-roll / B-roll」。
- **自动 vs 手动标签**：自动 = 前置小圆点（弱）；手动 = 实心底色（强）。可删标签右侧 `×`，命中区 ≥ 16px。

#### 缩略图卡片（gallery 核心）
```
┌──────────────────────────┐
│ ⬤A-roll            0:42  │  ← 左上 A/B 徽标(色+图标)，右下时长(mono)
│                          │
│        [16:9 帧]          │
│                          │
│ 旅行清晨的海边…  #海 #日出 │  ← 标题/简介一行截断 + 标签
└──────────────────────────┘
```
- 比例 16:9，圆角 md，image-dimension 预留尺寸防 CLS，懒加载。
- hover：轻微 `scale 1.02` + 显示快捷操作（详情/重新分析）。选中：2px `--primary` 环。
- 列表 ≥ 50 项用虚拟滚动（`virtualize-lists`）。

#### 输入 / 搜索
- `--surface-2` 底 + `--border`，聚焦换 `--primary` 环。
- 搜索框前置放大镜图标，支持清除按钮；可显示最近/建议查询。

#### 进度（SSE）
- 顶部 2px 确定性进度条（主色）。任务面板：每片段一行 = 文件名(mono) + 状态图标 + 当前阶段文字。
- 完成弹 toast（3–5s 自动消失，`aria-live=polite`）。

### 12.6 关键页面布局

#### 12.6.1 应用骨架 + 缩略图墙
```
┌─────────────────────────────────────────────────────────────┐
│ CutFinder   🔍[搜索台词/画面…]            [＋扫描]   ⚙设置    │ 顶栏 surface-1
├───────────────┬─────────────────────────────────────────────┤
│ 筛选 (侧栏)   │  全部 1,284 · A-roll 412 · B-roll 872      │
│               │  ┌────┐ ┌────┐ ┌────┐ ┌────┐               │
│ 日期          │  │card│ │card│ │card│ │card│   缩略图网格    │
│  2026-06 ▸   │  └────┘ └────┘ └────┘ └────┘               │
│  2026-05 ▸   │  ┌────┐ ┌────┐                             │
│               │  │card│ │card│                             │
│ 类型          │  └────┘ └────┘                           │
│  ◉全部 ⬤A ⬤B │                                              │
│               │                                              │
│ 标签          │                                              │
│  #海边 #城市   │                                              │
├───────────────┴─────────────────────────────────────────────┤
│ ▸ 处理中 18/40  MVI_5402.MP4 转写中…            ▮▮▮▯▯▯▯45%  │
└─────────────────────────────────────────────────────────────┘
```
- ≥1024px 用侧栏导航；网格响应式：列数随宽度 2→3→4→5。

#### 12.6.2 片段详情（右侧抽屉，从右滑入）
```
┌──────────────────────────────┐
│ MVI_5298.MP4            ✕     │
│ ┌──────────────────────────┐ │
│ │    [视频预览/代表帧]       │ │
│ └──────────────────────────┘ │
│ ⬤A-roll   2026-06-13  0:42   │
│                              │
│ 简介                          │ ← --text-md，可编辑
│ 清晨在海边散步…              │
│                              │
│ 标签   #海边 #日出 ＋          │ 手动可增删
│                              │
│ 转写全文 ▾                    │ 折叠，可搜索高亮
│ 「今天我们来到了…」           │
│                              │
│ 元数据  1920×1080·H.264      │ mono
│ 库内路径 …/2026-06-13/A-roll/ │ mono，可复制
│                              │
│ [改为 B-roll]   [↻ 重新分析]  │
└──────────────────────────────┘
```
- 「重新分析」触发 `POST /api/clips/{id}/reanalyze`，按钮进入 loading；保留手动纠正。
- 编辑简介/标签即时乐观更新，失败回滚 + toast。

#### 12.6.3 设置页
```
连接
  OMLX 接口   [http://localhost:8000/v1]    ● 已连接
模型
  文本模型     [Qwen3.6-35B-A3B    ▾]
  视觉模型     [Qwen3-VL-8B-Instruct▾]
文件夹
  源文件夹     [/Users/…/Footage] [＋添加]
  素材库       [/Users/…/Library]
扫描
  扩展名        [.mov .mp4 .m4v]
  B-roll 抽帧   [3]     VAD 阈值 [0.15]
  人声分离      [ ] A-roll 转写前去 BGM（较慢）
                                    [保存]
```
- **初剪逐次生成参数不在此页**：`cut_director_mode`、`cut_max_tool_rounds` 等属于初剪页「初剪设置」弹窗。
- **统一配置视图**：machine-global 键与库级 prefs 在 `GET /api/settings` 合并为同一 `prefs` 视图。

### 12.7 可访问性 / 质量清单

- **对比度**：所有正文 ≥ 4.5:1；A/B 色块附图标+文字，绝不仅靠颜色。
- **焦点可见**：2px `--primary` 焦点环，键盘 Tab 顺序与视觉一致。
- **图标按钮**：均带 `aria-label`（设置、关闭、重新分析、删除标签）。
- **动效**：150–250ms，仅 transform/opacity；尊重 `prefers-reduced-motion`。
- **空态**：无素材时显「还没有素材，点『扫描』开始」+ 按钮。
- **破坏性确认**：「改为 B-roll / 重新分析」属可逆，无需确认弹窗。
- **等宽对齐**：时长、时间码、元数据用 `--font-mono` + tabular-nums。

### 12.8 CSS 变量落地（tokens.css）

```css
:root {            /* 浅色 = 默认；结构 token 也在此 */
  color-scheme: light;
  --bg-canvas:#EEF0F3; --surface-1:#FFFFFF; --surface-2:#F6F7F9;
  --surface-3:#E4E7EC; --border:#D8DCE2; --border-strong:#BCC2CB;
  --text-primary:#1A1D21; --text-secondary:#4B5563; --text-muted:#6B7280;
  --primary:#5256E0; --primary-hover:#4146C4; --primary-press:#383DB0;
  --roll-a:#B45309; --roll-b:#0F766E;
  --success:#15803D; --warning:#B45309; --error:#DC2626;
  --radius-sm:6px; --radius-md:8px; --radius-lg:10px;
  --font-ui:"Inter","PingFang SC",-apple-system,system-ui,sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,"SF Mono",monospace;
}

[data-theme="dark"] {    /* 深色 = 仅覆盖配色 token */
  color-scheme: dark;
  --bg-canvas:#0E0F11; --surface-1:#16181B; --surface-2:#1E2125;
  --surface-3:#282C31; --border:#2E333A; --border-strong:#3A4048;
  --text-primary:#F2F4F7; --text-secondary:#A4ACB9; --text-muted:#6B7280;
  --primary:#6366F1; --primary-hover:#7077F2; --primary-press:#525AE0;
  --roll-a:#F59E0B; --roll-b:#2DD4BF;
  --success:#22C55E; --warning:#F59E0B; --error:#EF4444;
}
```

**主题切换落地**：`index.html` `<head>` 内联脚本读 `localStorage['cutfinder-theme']`，首帧前设 `data-theme`。`src/theme.ts` 暴露 `getStoredTheme()` / `applyTheme(theme)`（写 data-theme + localStorage）。顶栏 ghost 图标按钮调 `applyTheme`。

### 12.9 Tailwind / shadcn 映射、字体引入

- Token 映射到 `tailwind.config` 的 `theme.extend.colors` 与 `fontFamily`，shadcn/ui 主题变量指向同一套 CSS 变量。
- Inter / JetBrains Mono 用 `@fontsource` 本地引入（离线，`font-display: swap`）；中文走系统 PingFang SC 不额外下载。
- `color-scheme` 随主题切换，适配原生滚动条/表单控件。

### 12.10 原生 macOS App Shell（窗口 / SetupView / ErrorView）

> 配合 §11。原生 Swift/AppKit 包装器把 web UI 用 WKWebView 内嵌为真正的 Mac App。

#### 窗口三态
| 态 | 内容 | 配色 |
|---|---|---|
| 安装中 | `SetupView`：步骤清单 + 进度条 + 可折叠日志 | `--bg-canvas` / `--surface-1` / `--primary` 进度 |
| 运行中 | WKWebView 加载 web UI（http://127.0.0.1:PORT/） | web 自身主题（与 CSS token 一致）|
| 错误/引导 | `ErrorView`：标题 + 说明 + 操作按钮 | `--warning`/`--error` 配图标+文字 |

#### SetupView（首次安装视图）
```
┌─ CutFinder ───────────────  ● 安装中 ─┐
│                                        │
│   ◧ 正在准备 CutFinder（首次启动）      │
│   首次需要联网安装运行环境与模型，约几分钟 │
│                                        │
│   ✓  应用文件          已就绪           │
│   ✓  uv（Python工具链）已安装           │
│   ⟳  ffmpeg          安装中…            │
│   ·  Python运行环境    等待             │
│   ·  AI模型(whisper/demucs) 等待·约3GB │
│   ·  OMLX模型服务      待探测           │
│                                        │
│   ▮▮▮▮▮▯▯ 45%                         │
│   ▸ 查看安装日志                       │
└───────────────────────────────────────┘
```

#### ErrorView（错误/引导视图）
```
┌─ CutFinder ───────────────  ● OMLX未就绪 ─┐
│                                           │
│   ⚠  未检测到 OMLX 模型服务               │
│   CutFinder 的「A-roll简介 / B-roll打标」需要│
│   本机 OMLX（独立 App）。                  │
│   扫描、转写不受影响，可先继续使用。        │
│                                           │
│   [打开 OMLX下载页]  [重试探测]  [继续]    │
│   ▸ 详情/日志                             │
└───────────────────────────────────────────┘
```

#### 应用菜单（标准 + 服务）
```
CutFinder   文件    编辑    显示    服务    窗口    帮助
─────────
CutFinder ▸ 关于 · 偏好设置(端口/开机自启)· 隐藏 · ⌘Q退出
显示     ▸ 重新加载(⌘R)·实际大小·全屏
服务     ▸ 开启/停止/重启 · ─── ·在浏览器中打开·开库文件夹·日志
帮助     ▸ CutFinder文档·检查OMLX状态
```

---

## 13. 关键决策汇总

- **隔离手段**：六类外部依赖 + 仓储统一抽象为 `Protocol`，真实实现放 `adapters/`，业务逻辑(`pipeline/`)只依赖接口 → 模块可独立替换与测试。
- **测试边界**：单元测试一律 mock 外部依赖（仓储用内存 SQLite、LibraryWriter 用临时真文件）；真实模型/视频只在带标记的集成测试出现。
- **进度**：单 worker 顺序处理 + SSE 实时推进度；job 状态持久化以便刷新恢复。
- **幂等与纠正**：指纹去重；手动纠正的 A/B 标 `manual`，重扫不被覆盖。
- **预留扩展点**：关键帧建议可复用 `FrameExtractor` + `VisionTagger`；字幕导出（§3.13）复用 `Transcriber` + 纯逻辑格式化器；初剪导演（§3.15）复用 `CatalogRepository` + OMLX client，均作为独立工具挂在 Worker/SSE 上。

---

## 14. 待办 / 需后续确认

- 前端 UI 视觉与交互细节（缩略图墙布局、详情面板排版）——可在实现阶段配合设计稿确定。

*本文档为实现前的详细设计，确认后进入实现计划阶段。*
