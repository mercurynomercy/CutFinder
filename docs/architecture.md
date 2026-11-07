# CutFinder 架构图（Mermaid 源）

图形版：[`architecture.svg`](./architecture.svg) / [`architecture.png`](./architecture.png)。
本文件是可维护的文本源，改动结构时同步更新两者即可。

```mermaid
flowchart TB
  subgraph MAC["客户端 · 单台 Apple Silicon Mac（全程离线）"]
    direction TB
    subgraph FE["Web 前端 · Vite + React + TS + Tailwind"]
      GAL["Gallery 缩略图墙"]
      FLT["Filters / Search<br/>A·Broll 日期 标签 全文"]
      DET["Detail 摘要·转录·标签修正"]
      CUT["Cut Plan Chat 粗剪会话"]
      SUB["Subtitles 导出 iTT/SRT/FCPXML"]
      JOB["Jobs Queue / Logs"]
      SET["Settings BaseURL·模型·语音引擎"]
      LNC["Launcher 选库"]
    end
    SHELL["macOS 原生壳 packaging/macapp<br/>.app bundle 托管 uvicorn + WebView"]
  end

  subgraph API["API 服务层 · FastAPI（create_app + LibraryContext 运行时可换库）"]
    R1["routes.py<br/>/scan /jobs /clips /search /thumbnail /keyframes"]
    R2["cut_routes.py<br/>/cut/sessions /messages /plan"]
    R3["settings_routes.py<br/>GET·PUT /settings + openai/test"]
    R4["library_routes.py 绑定库·孤儿清理"]
    R5["subtitles / schemas"]
  end

  subgraph ORCH["编排 & 后台执行 · pipeline/"]
    WQ["WorkerQueue<br/>asyncio 单并发 + SSE 广播"]
    ORC["Orchestrator<br/>逐 clip 步骤编排·错误隔离"]
    SCN["Scanner<br/>递归扫描·指纹去重"]
    CPS["CutPlanService<br/>意图解析·preflight 预算"]
    DIR["CutDirector<br/>per-day mini-agent + Critic"]
    SX["SubtitleExporter"]
    DOM["domain/ Clip·Job·Transcript·Shot·CutPlan"]
  end

  subgraph PORTS["ports/ 抽象接口（六边形边界）"]
    P1["probe"] --- P2["media"] --- P3["speech"] --- P4["ai"] --- P5["cutplan"] --- P6["repository"] --- P7["library"]
  end

  subgraph ADP["adapters/ 实现"]
    A1["ffmpeg_probe · ffmpeg_media · pillow_image"]
    A2["sqlite_repo · sqlite_footage · fs_library(copy2)"]
    A3["openai_text · openai_vision · openai_agent · broll_inspector"]
    A4["silero_vad · mlx_whisper · qwen_transcriber · demucs_separator"]
  end

  subgraph SRV["OpenAI 兼容推理服务器 · localhost（OMLX / LM Studio / Ollama / vLLM）"]
    EP["POST /v1/chat/completions<br/>OPENAI_BASE_URL / API_KEY · 换 model 名切换"]
    M1["Qwen3.6-35B-A3B → A-roll 摘要+标签"]
    M2["Qwen3-VL-8B-Instruct → B-roll 视觉标签"]
    MEM["显存调度：LRU 换入换出 · pinning · per-model TTL"]
  end

  subgraph AUD["本地语音子系统 · 独立进程（服务器不提供音频）"]
    VAD["Silero VAD → A/B 判型"]
    ENG{"transcription_engine"}
    WH["whisper: mlx-whisper large-v3（默认）"]
    QW["qwen: Qwen3-ASR + ForcedAligner 逐字时间轴"]
    DEM["Demucs 人声分离（前置，可选）"]
  end

  DISK[("存储<br/>源库只读 → &lt;library&gt;/YYYY-MM-DD/{A-roll,B-roll}<br/>.cutfinder/catalog.sqlite · thumbnails/")]

  FE -- "HTTP JSON + SSE" --> API
  API --> ORCH
  ORCH -. 依赖 .-> PORTS
  PORTS -. 实现 .-> ADP
  A3 -- HTTP --> EP
  A1 --> DISK
  A2 --> DISK
  EP --> M1 & M2
  A4 --> SRV
  A4 --> AUD
  VAD --> ENG --> WH & QW
  DEM --> WH
```

## 逐条 clip 流水线

```mermaid
flowchart LR
  S["Scanner 扫描源目录"] --> D["指纹去重（幂等）"]
  D --> PR["ffprobe 元数据<br/>拍摄时间优先"]
  PR --> TH["ffmpeg 缩略图"]
  TH --> V{"Silero VAD 有声?"}
  V -- 有声 A-roll --> TR["转录（whisper / qwen-ASR+对齐）"]
  TR --> SU["Qwen3.6 摘要 + 中文标签"]
  V -- 无声 B-roll --> KF["关键帧抽取"]
  KF --> VL["Qwen3-VL 视觉标签 + 描述"]
  SU & VL --> DB[("写入 catalog.sqlite")]
  DB --> CP["copy2 副本 →<br/>&lt;library&gt;/YYYY-MM-DD/{A-roll,B-roll}/"]
```

## 硬约束

1. 原始素材**只读**：不移动、不改名、不改写，所有归档动作发生在目标库副本上。
2. **拍摄时间永不改变**：读取内嵌 QuickTime/EXIF 时间，副本用 `shutil.copy2` 保留文件系统时间。
3. **完全本地/离线**：画面与音频不出本机，全部推理跑在 Apple Silicon 上。
4. **重扫幂等**：按文件指纹去重，只处理新文件，不重复复制。
