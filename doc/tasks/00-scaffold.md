# 00 · 项目脚手架（基础）

> 搭好骨架，让 `make setup` 与 `make test` 能跑通空测试。后续模块在此之上填实现。
> **依赖**：无。 **详见** detailed-design §2、§10。

## 子任务
- [ ] 建后端目录：`backend/cutfinder/{domain,ports,adapters,pipeline,api}/`、`backend/tests/{unit,integration,fakes}/`
- [ ] `backend/pyproject.toml` + `uv.lock`（依赖：fastapi、uvicorn、pydantic、pydantic-settings、openai、mlx-whisper、silero-vad(或 torch)、httpx、pytest、pytest-asyncio）
- [ ] `mise.toml` 钉死 Python / Node 版本
- [ ] `Brewfile`（`ffmpeg`）
- [ ] 前端脚手架 `frontend/`：Vite + React + TS、Vitest、@testing-library/react、MSW、Playwright
- [ ] `Makefile` 先实现 `setup` 与 `test` 两个目标
- [ ] `.env.example`（`OMLX_BASE_URL`、`OMLX_API_KEY`）
- [ ] `domain/enums.py`：`RollType(A/B)`、`Source(auto/manual)`、`JobStatus`、`DateSource(embedded/file)`、`ClipStatus(pending/processing/done/error)`
- [ ] `domain/models.py`：`VideoMetadata`、`Clip`、`ClipSummary`、`ClipFilter`、`Transcript`、`Segment`、`Tag`、`Job`、`SummaryResult`、`VisionResult`、`AnalysisResult`（纯数据，无 IO）
- [ ] `ports/`：定义全部 Protocol 接口签名 —— `MetadataProbe`、`ThumbnailMaker`、`FrameExtractor`、`SpeechDetector`、`Transcriber`、`Summarizer`、`VisionTagger`、`LibraryWriter`、`CatalogRepository`

## 完成标准（DoD）
- [ ] `make setup` 成功（环境、依赖装齐）
- [ ] `make test` 跑通（哪怕只有占位测试）
- [ ] 类型检查通过；`ports/` 接口可被 import
