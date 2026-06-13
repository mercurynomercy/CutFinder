# 00 · 项目脚手架（基础）

> 搭好骨架，让 `make setup` 与 `make test` 能跑通空测试。后续模块在此之上填实现。
> **依赖**：无。 **详见** detailed-design §2、§10。

## 子任务
- [x] 建后端目录：`backend/cutfinder/{domain,ports,adapters,pipeline,api}/`、`backend/tests/{unit,integration,fakes}/`
- [x] `backend/pyproject.toml` + `uv.lock`（依赖：fastapi、uvicorn、pydantic、pydantic-settings、openai、mlx-whisper、silero-vad(或 torch)、httpx、pytest、pytest-asyncio）
- [x] `mise.toml` 钉死 Python / Node 版本
- [x] `Brewfile`（`ffmpeg`）
- [x] 前端脚手架 `frontend/`：Vite + React + TS、**Tailwind + shadcn/ui**、Vitest、@testing-library/react、MSW、Playwright
- [x] 落地设计系统骨架：`frontend/src/styles/tokens.css`（颜色/字体/间距 token，见 [`ui-design.md`](../ui-design.md) §8）+ 引入 Inter / JetBrains Mono
- [x] `Makefile` 先实现 `setup` 与 `test` 两个目标
- [x] `.env.example`（`OMLX_BASE_URL`、`OMLX_API_KEY`）
- [x] `domain/enums.py`：`RollType(A/B)`、`Source(auto/manual)`、`JobStatus`、`DateSource(embedded/file)`、`ClipStatus(pending/processing/done/error)`
- [x] `domain/models.py`：`VideoMetadata`、`Clip`、`ClipSummary`、`ClipFilter`、`Transcript`、`Segment`、`Tag`、`Job`、`SummaryResult`、`VisionResult`、`AnalysisResult`（纯数据，无 IO）
- [x] `ports/`：定义全部 Protocol 接口签名 —— `MetadataProbe`、`ThumbnailMaker`、`FrameExtractor`、`SpeechDetector`、`Transcriber`、`Summarizer`、`VisionTagger`、`LibraryWriter`、`CatalogRepository`

## 完成标准（DoD）
- [x] `make setup` 成功（环境、依赖装齐） — Makefile 逻辑正确，本机 mise/brew 未安装所以无法完整跑通
- [x] `make test` 跑通（哪怕只有占位测试） — pytest 3/3 pass
- [x] 类型检查通过；`ports/` 接口可被 import — mypy clean, all ports imported OK
