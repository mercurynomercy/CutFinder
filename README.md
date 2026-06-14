# CutFinder

> 本地运行的 Vlog 视频素材（footage）智能分类与检索工具。灵感来自 [Argus](https://github.com/discoposse/argus)。

把一堆 A-roll（有中文解说）和 B-roll（纯空镜）自动**分类、打标签、生成简介与缩略图**，让你之后能按日期 / 类型 / 标签 / 台词快速找回任意一段素材。面向 macOS（Apple Silicon）+ Final Cut Pro 工作流，**全程离线、AI 全本地**。

> **状态：核心功能已完成。** 阶段 0–14（后端适配器、编排层、API 层、前端）均已实现，`make test` / `uv run mypy` / Vite build 均可跑通。当前处于阶段 15 — 集成测试与部署完善中。

---

## 它能做什么

- **自动区分 A-roll / B-roll**：检测有无人声解说（Silero VAD），可手动纠正且会被记住。
- **A-roll 中文简介 + 标签**：`mlx-whisper` 转写中文解说 → Qwen 文本模型总结，转写全文一并保存可搜索。
- **B-roll 画面标签 + 描述**：抽帧交给视觉模型识别画面内容。
- **按拍摄日期 + 类型自动归档**：复制到 `库/YYYY-MM-DD/A-roll(或 B-roll)/`。
- **缩略图墙 + 多维检索**：按日期 / 类型 / 标签筛选，按台词全文搜索。
- **重新分析单个片段**：换模型或结果不佳时一键重跑 AI，保留你的手动纠正与标签。
- **深色专业界面**：近黑面板让缩略图突出，A-roll/B-roll 以颜色+图标区分，贴近 FCP 调性（见 [`doc/ui-design.md`](./doc/ui-design.md)）。

### 不破坏原素材（核心约束）

- **原文件只读**，所有整理只发生在复制出来的新素材库里。
- **拍摄时间永不改变**（内嵌 QuickTime/EXIF 时间不被写，复制保留文件时间）。
- **离线**，素材不出本机。
- **幂等**，重扫只处理新文件（指纹去重），不重复复制。

---

## 架构概览

```
前端 (Vite + React + Tailwind + shadcn/ui，深色优先)
   │ HTTP (REST + SSE)
API 层 (FastAPI，薄)
   │
编排层 (Pipeline Orchestrator + 后台队列/SSE 进度)
   │  只依赖接口(Protocol)
适配器层 ── ffmpeg/ffprobe · Silero VAD · mlx-whisper · OMLX(文本+视觉) · SQLite
```

每个外部依赖都藏在接口后面，业务逻辑只依赖接口 → 模块可独立替换与测试。详见 [`doc/detailed-design.md`](./doc/detailed-design.md)。

### 模型服务

| 用途 | 模型 | 运行方式 |
|---|---|---|
| A-roll 简介/标签（文本） | `Qwen3.6-35B-A3B` | OMLX（OpenAI 兼容接口） |
| B-roll 画面识别（视觉） | `Qwen3-VL-8B-Instruct` | OMLX（同接口，base64 传帧） |
| A-roll 语音转写 | `mlx-whisper` (large-v3) | 独立进程（OMLX 不托管音频） |
| A/B 人声检测 | Silero VAD | 本地 |

文本与视觉模型都由 [OMLX](https://github.com/jundot/omlx)（Apple Silicon 本地推理服务器，菜单栏 App）托管。

---

## 要求 (Requirements)

### 必需

| 依赖 | 说明 |
|------|------|
| **macOS + Apple Silicon** | AI 推理依赖 Metal GPU，无法在 Docker / x86_macOS 上运行 |
| [OMLX](https://github.com/jundot/omlx) ≥ 0.1 | Apple Silicon 本地模型服务器（菜单栏 App），需预加载 `Qwen3.6-35B-A3B`（文本）和 `Qwen3-VL-8B-Instruct`（视觉）两个模型 |
| [uv](https://docs.astral.sh/uv/) | Python 依赖管理（`pip install uv`） |
| **Python ≥ 3.12** | 系统自带或经 mise/Homebrew 安装 |
| **Node.js ≥ 20** + `npm` | 前端开发服务器与构建工具 |
| [ffmpeg](https://ffmpeg.org/) (`ffprobe` + `ffmpeg`) | 视频元数据提取与缩略图生成（Homebrew: `brew install ffmpeg`） |

### 可选

- [mise](https://mise.jdx.dev/) — 自动管理 Python / Node 版本（`.mise.toml`）
- [Homebrew](https://brew.sh/) — 用于安装 ffmpeg / OMLX

> ⚠️ **AI 推理必须原生运行**，不能跑在 Docker 容器里。

---

## 安装与启动 (Setup & Run)

### 一键安装（推荐）

```bash
git clone <repo> && cd CutFinder
cp .env.example .env            # 填入 OMLX_BASE_URL 与 OMLX_API_KEY
make setup                      # mise install + brew bundle + uv sync + npm install
```

> 没有 mise？先 `brew install mise`，或手动执行：
> ```bash
> cd backend && uv sync          # Python 依赖（pytest / mypy / ruff）
> cd ../frontend && npm install   # Vite + React + Tailwind + shadcn/ui
> ```

### 验证 OMLX 就绪

```bash
make check-omlx                 # 校验文本/视觉模型是否已加载
```

### 启动开发服务器（最简单）

**一条命令同时起前后端：**

```bash
make dev                        # → 后端 localhost:5081 + 前端 http://localhost:5080
```

按 `Ctrl+C` 同时停止两个服务。

### 手动分起（调试用）

```bash
# 终端 1 — 后端
cd backend && uv run uvicorn cutfinder.api.app:app --reload   # localhost:5081

# 终端 2 — 前端
cd frontend && npx vite                                       # http://localhost:5080
```

---

## 测试

### 后端（pytest）

```bash
cd backend

uv run pytest                    # 全部单元 + 集成测试（-m integration 标记的需真实依赖）
uv run pytest -m "not integration"   # 仅单元测试（无需外部服务，秒级）
uv run mypy cutfinder/          # 类型检查（strict mode, clean = no output）
uv run ruff check cutfinder/    # linting + formatting check
```

### 前端（Vitest + Playwright）

```bash
cd frontend

npx vitest run                   # 单元/组件测试（jsdom, mock-ready）
npx vitest                     # watch mode

npx playwright test            # e2e 测试（自动起 Vite dev server）
```

### Makefile 快捷命令

```bash
make test              # 后端 pytest（全部单元 + 集成标记测试）
make test-integration  # 仅跑 -m integration（需 ffmpeg/OMLX）
make e2e               # Playwright e2e（前后端均自动启动/连接）
```

> Vitest 前端测试仍需手动进入 frontend/: `cd frontend && npx vitest run`

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
