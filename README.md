# CutFinder

> 本地运行的 Vlog 视频素材（footage）智能分类与检索工具。灵感来自 [Argus](https://github.com/discoposse/argus)。

把一堆 A-roll（有中文解说）和 B-roll（纯空镜）自动**分类、打标签、生成简介与缩略图**，让你之后能按日期 / 类型 / 标签 / 台词快速找回任意一段素材。面向 macOS（Apple Silicon）+ Final Cut Pro 工作流，**全程离线、AI 全本地**。

> **状态：核心功能已打通并可端到端运行。** 后端适配器、编排层、API 装配层（`create_app`）、前端均已实现并接通；`make test`（293 单元测试）、前端 `vitest`（167 项）、`make check-omlx`、`make dev` 均可跑通。模型推理链路（文本/视觉/转写/VAD）通过真实 OMLX + 本地集成测试验证（见[测试](#测试)）。

---

## 它能做什么

- **自动区分 A-roll / B-roll**：检测有无人声解说（Silero VAD），可手动纠正且会被记住。
- **A-roll 简介 + 标签**：`mlx-whisper` 转写中文解说 → Qwen 文本模型总结，转写全文一并保存可搜索。
- **B-roll 画面标签 + 描述**：抽帧交给视觉模型识别画面内容。
- **AI 输出语言可选**：简介/画面描述可在「设置」页切换**中文 / 英文**（默认中文）。
- **按拍摄日期 + 类型自动归档**：复制到 `库/YYYY-MM-DD/A-roll(或 B-roll)/`。
- **缩略图墙 + 多维检索**：按日期 / 类型 / 标签筛选，按台词全文搜索。
- **重新分析单个片段**：换模型或结果不佳时一键重跑 AI，保留你的手动纠正与标签。
- **设置页绑定素材库**：首次使用填一个绝对路径即可绑定库，**运行时热生效、无需重启**（也支持 `CUTFINDER_LIBRARY` 环境变量）。
- **深色专业界面**：近黑面板让缩略图突出，A-roll/B-roll 以颜色+图标区分，贴近 FCP 调性（见 [`doc/ui-design.md`](./doc/ui-design.md)）。

### 不破坏原素材（核心约束）

- **原文件只读**，所有整理只发生在复制出来的新素材库里。
- **拍摄时间永不改变**（内嵌 QuickTime/EXIF 时间不被写，复制保留文件时间）。
- **离线**，素材不出本机。
- **幂等**，重扫只处理新文件（指纹去重），不重复复制。

---

## 架构概览

```
前端 (Vite + React + Tailwind，深色优先)  :5080
   │ HTTP (REST + SSE)，经 Vite dev proxy → :5081
API 层 (FastAPI，薄)                       :5081
   │  create_app() 把真实适配器装配到可变 LibraryContext（库可运行时热绑定）
编排层 (Pipeline Orchestrator + 后台队列/SSE 进度)
   │  只依赖接口(Protocol)
适配器层 ── ffmpeg/ffprobe · Silero VAD · mlx-whisper · OMLX(文本+视觉) · SQLite
```

每个外部依赖都藏在接口后面，业务逻辑只依赖接口 → 模块可独立替换与测试。详见 [`doc/detailed-design.md`](./doc/detailed-design.md)。

### 模型服务

| 用途 | 模型（OMLX 上的 id） | 运行方式 |
|---|---|---|
| A-roll 简介/标签（文本） | `Qwen3.6-35B-A3B` | OMLX（OpenAI 兼容接口） |
| B-roll 画面识别（视觉） | `Qwen3-VL-8B` | OMLX（同接口，base64 传帧） |
| A-roll 语音转写 | `mlx-whisper`（默认 `mlx-community/whisper-large-v3-mlx`） | 独立进程（OMLX 不托管音频） |
| A/B 人声检测 | Silero VAD | 本地 |

文本与视觉模型都由 [OMLX](https://github.com/jundot/omlx)（Apple Silicon 本地推理服务器，菜单栏 App）托管。

> ⚠️ 模型名必须与你的 OMLX 实际加载的 id 完全一致。默认视觉模型为 `Qwen3-VL-8B`；如你的 OMLX 暴露的是带后缀的 id，请在「设置」页或 `<库>/.cutfinder/config.json` 里改 `vision_model` / `text_model`。

---

## 要求 (Requirements)

### 必需

| 依赖 | 说明 |
|------|------|
| **macOS + Apple Silicon** | AI 推理依赖 Metal GPU，无法在 Docker / x86_macOS 上运行 |
| [OMLX](https://github.com/jundot/omlx) ≥ 0.1 | Apple Silicon 本地模型服务器（菜单栏 App），需预加载 `Qwen3.6-35B-A3B`（文本）和 `Qwen3-VL-8B`（视觉）两个模型 |
| [uv](https://docs.astral.sh/uv/) | Python 依赖管理（`pip install uv`） |
| **Python ≥ 3.12** | uv 会自动按 `mise.toml` 拉取 3.12 虚拟环境 |
| **Node.js ≥ 20** + `npm` | 前端开发服务器与构建工具 |
| [ffmpeg](https://ffmpeg.org/) (`ffprobe` + `ffmpeg`) | 视频元数据提取与缩略图生成（Homebrew: `brew install ffmpeg`） |

### 可选

- [mise](https://mise.jdx.dev/) — 自动管理 Python / Node 版本（`mise.toml`）
- [Homebrew](https://brew.sh/) — 用于安装 ffmpeg / OMLX

> ⚠️ **AI 推理必须原生运行**，不能跑在 Docker 容器里。

---

## 安装与启动 (Setup & Run)

### 1. 安装依赖

```bash
git clone <repo> && cd CutFinder
cp .env.example .env            # 填入 OMLX_BASE_URL 与 OMLX_API_KEY（见下）
make setup                      # mise install + brew bundle + uv sync + npm install
```

> 没有 mise？先 `brew install mise`，或手动执行：
> ```bash
> cd backend && uv sync           # Python 依赖（含 pytest / mypy / ruff，已随 uv sync 安装）
> cd ../frontend && npm install   # Vite + React + Tailwind
> ```

### 2. 配置 `.env`

```ini
# OMLX 本地推理服务器（OpenAI 兼容）。默认假设 :8000；按你的实际端口改。
OMLX_BASE_URL=http://localhost:8000/v1
OMLX_API_KEY=your-omlx-key
```

`.env` 位于**仓库根目录**。`make dev` / `make check-omlx` / `make test-integration` 都会自动加载它。
若你手动用 `uvicorn` 起后端，请先 `set -a; source .env; set +a` 导出这些变量。

### 3. 验证 OMLX 就绪

```bash
make check-omlx                 # 校验文本/视觉模型是否已加载（读取根 .env）
# → OMLX OK — models: [...]
#   All required text/vision models are present.
```

### 4. 启动开发服务器（推荐：一条命令同时起前后端）

```bash
make dev
# 后端 → http://localhost:5081 （FastAPI）
# 前端 → http://localhost:5080 （Vite，/api 已代理到后端 5081）
```

打开 **http://localhost:5080**，按 `Ctrl+C` 同时停止两个服务。

### 5. 绑定素材库（首次使用）

素材库目录用于存放整理后的副本、缩略图与 SQLite 目录（都在 `<库>/.cutfinder/`）。两种方式：

- **设置页（推荐）**：打开 http://localhost:5080 → 「设置」→ **Set up your library** → 填一个绝对路径 → **运行时热生效、无需重启**，且选择会被记住（持久化到 `~/.cutfinder`）。
- **环境变量**：在根 `.env` 里加 `CUTFINDER_LIBRARY=/path/to/library`，再 `make dev`。

> 未绑定库时后端正常启动，但目录类接口返回 503、「设置」页显示绑定向导，直到你绑定一个库。

### 手动分起（调试用）

```bash
# 终端 1 — 后端（先导出 .env）
cd backend
set -a; source ../.env; set +a
CUTFINDER_LIBRARY=/path/to/library uv run uvicorn cutfinder.api.app:app --reload --port 5081

# 终端 2 — 前端
cd frontend && npx vite        # http://localhost:5080
```

### 下载 Whisper 模型（首次转写前，可选预热）

```bash
make models                     # 预下载 mlx-whisper large-v3-mlx
```

默认下载到 HuggingFace 缓存（`~/.cache/huggingface`）。若想把模型放到自定义目录，在根 `.env` 里设置：

```ini
WHISPER_MODEL_PATH=/Users/you/AI/Models/ASRs/mlx-community/whisper-large-v3-mlx
```

设置后：`make models` 会把模型下载到该目录；运行时 CutFinder 直接从此路径离线加载（覆盖 `whisper_model` 偏好），不再用 HF 缓存。

---

## 测试

### 后端（pytest）

```bash
cd backend

uv run pytest -m "not integration"   # 仅单元测试（293 项，无需外部服务，秒级）
uv run pytest -m integration         # 集成测试（需真实 OMLX / ffmpeg / 样片）
uv run mypy cutfinder/               # 类型检查（strict，clean）
uv run ruff check cutfinder/         # linting（clean）
```

集成测试在缺少 `.env` / OMLX / 样片时会**自动 skip**，不会误报失败。要真正跑 OMLX 链路：

```bash
cd backend
set -a; source ../.env; set +a
uv run pytest -m integration
```

### 前端（Vitest + Playwright）

```bash
cd frontend

npx vitest run                  # 单元/组件测试
npx playwright test             # e2e（自动起 Vite dev server）
```

### Makefile 快捷命令

```bash
make test              # 后端单元测试（uv sync + pytest）
make test-integration  # 仅跑 -m integration（自动加载 .env；需 ffmpeg/OMLX）
make e2e               # Playwright e2e
```

> Vitest 仍需手动进入 frontend/: `cd frontend && npx vitest run`

### 已知遗留项（不影响运行）

- **前端 `npm run build` 的 `tsc -b` 仍有历史遗留类型错误**（与本次改动无关，应用代码早先就未做到 type-clean）。Vitest 不做类型检查，故 `vitest` 全绿、`make dev` 正常；要让 `tsc` 干净需单独清理。
- 真实集成测试中**视觉打标的输出文本可能中英混杂**（Qwen3-VL-8B 的模型/prompt 表现，非适配器 bug）；结构化结果（description + tags）始终有效。

---

## 文档

- [需求文档 `doc/proposal.md`](./doc/proposal.md) —— 目标、需求、范围、技术选型
- [详细设计 `doc/detailed-design.md`](./doc/detailed-design.md) —— 模块、接口、数据模型、API、测试与部署
- [UI 设计系统 `doc/ui-design.md`](./doc/ui-design.md) —— 配色/字体/间距 token、组件规范、页面布局（深色优先）
- [任务清单 `doc/tasks/`](./doc/tasks/progress.md) —— 各模块最小任务与总体进度
- [`CLAUDE.md`](./CLAUDE.md) —— 给 AI 协作者的项目约束与架构速览

---

## 路线图

- **v1**：需求 0–7（自定义文件夹、保留拍摄时间、A/B 判定、A-roll 简介、日期+类型归档、标签、缩略图、接 OMLX）
- **后续**：关键帧（剪辑切点）建议、Final Cut Pro 深度集成（FCPXML/关键词）、打包独立 `.app`
