# CutFinder 任务总览

> All development tasks overview. Each module one entry, checked when fully complete (code implemented + automated tests pass).
> Based on: proposal.md, detailed-design.md.

## 阶段0 · 基础 (Foundation)
- [x] **01 项目脚手架** — Directory structure, domain models, ports interfaces, uv/mise/Brewfile/test framework

## 阶段1 · 适配器 (External Dependency Adapters, independent of each other)
- [x] **02 Config配置** — pydantic-settings for global config + JSON preferences
- [x] **03 MetadataProbe元数据** — ffprobe parsing capture time/duration/resolution
- [x] **04 Media缩略图/抽帧** — ffmpeg representative frame + uniform sampling
- [x] **05 SpeechDetector人声检测** — Silero VAD speech_ratio for A/B classification
- [x] **06 Transcriber语音转写** — mlx-whisper / Qwen3-ASR+ForcedAligner dual engine
- [x] **07 Summarizer文本总结** — OMLX Qwen3.6 structured output {summary, tags}
- [x] **08 VisionTagger画面识别** — OMLX Qwen3-VL base64 frames
- [x] **09 LibraryWriter库文件组织** — shutil.copy2 preserving times, date/type directory
- [x] **10 CatalogRepository仓储** — SQLite CRUD + FTS5 full-text search

## 阶段2 · 核心逻辑 (Core Logic)
- [x] **11 Scanner扫描去重** — sha256 fingerprint + extension filtering
- [x] **12 Orchestrator流水线编排** — A/B branching, error isolation, idempotency, re-analyze
- [x] **13 Worker队列+SSE** — asyncio.Queue + progress event broadcasting

## 阶段3 · 接口 (API Layer)
- [x] **14 API层(FastAPI)** — REST+SSE routes, pydantic validation

## 阶段4 · 前端 (Frontend)
- [x] **15 Frontend** — Vite+React+Tailwind, gallery/filters/search/detail/settings/jobs/cutplan/subtitles

## 阶段5 · 集成与部署 (Integration & Deployment)
- [x] **16 环境/部署** — mise+uv+Brewfile, make setup/dev/test

## 阶段6 · 增强功能 (Enhancements — All Implemented)
- [x] **17 关键帧推荐** — A-roll transcript / B-roll vision, detail panel + gallery badge
- [x] **18 字幕导出** — Finished video → mlx-whisper transcription → iTT/SRT, forced vocal separation
- [x] **19 转写前置人声分离** — Demucs htdemucs for BGM removal, optional toggle
- [x] **20 字幕进度同步** — tqdm interception for separation+transcription two phases, real progress bar
- [~] **21 原生macOS .app** — Swift/AppKit wrapper, WKWebView embedding, auto-install on first boot
- [x] **22 关键帧设置开关** — keyframe_auto default off, config + UI
- [x] **23 库文件删除同步清理** — orphan detection + DB/thumbnail/keyframe cascade delete
- [x] **24 照片分析入库** — Pillow image probe, photo roll type, HEIC support
- [x] **25 进度条恢复** — jobs API + resumePoll, restore after page refresh
- [~] **26 初剪导演Agent** — Multi-turn dialogue generating shotlist, constrained tool-call loop
- [~] **27 初剪按天mini-agent** — Per-day scoped tool loop + fallback, dedup guardrail
- [~] **28 初剪实时进度** — Per-day/per-clip status, completed dates' shotlist shown first
- [x] **29 初剪refine按日合并+审片critic** — prior_plan merge, subjective quality review
- [x] **30 设置统一config.json** — Remove env grouping, global keys merged into prefs view
- [x] **31 初剪fallback复用勘察分析** — agent inspect_broll descriptions passed to staged mode

## Milestones (里程碑)
- [x] **可跑通单元测试** — make test all green (e.g., 538+ unit tests)
- [x] **后端 API 可用** — create_app real assembly, uvicorn starts fine
- [x] **真实推理链路已验证** — Real OMLX + ffmpeg/mlx-whisper/Silero integration tests pass

## TODO (待办)
- [x] **全链路端到端** — Scan → classify → archive → retrieve 贯通脚本已通过，各组件分别验证 + 集成测试覆盖
- [x] **字幕导出真机验证** — iTT/SRT 输出已在真实 FCP import 测试中通过
- [x] **人声分离真样本验证** — 含 BGM 音频对比开启/关闭 Demucs，transcript 质量确认提升
- [x] **初剪 Agent 真机 eval** — Tasks 26/27/28：在真实 vlog 素材上定性评估通过
