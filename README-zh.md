# CutFinder

> 本地运行的 Vlog 视频素材（footage）智能分类与检索工具。灵感来自 [Argus](https://github.com/discoposse/argus)。

**English docs → [README.md](./README.md)**

把一堆 A-roll（有中文解说）和 B-roll（纯空镜）自动**分类、打标签、生成简介与缩略图**，让你之后能按日期 / 类型 / 标签 / 台词快速找回任意一段素材。面向 macOS（Apple Silicon）+ Final Cut Pro 工作流，**全程离线、AI 全本地**。

> **状态：核心功能已打通并可端到端运行。** 后端适配器、编排层、API 装配层（`create_app`）、前端均已实现并接通；`make test-unit`（367 单元测试）、前端 `vitest`（190 项）、`npm run build`（类型干净）、`make check-omlx`、`make dev` 均可跑通。模型推理链路（文本/视觉/转写/VAD）通过真实 OMLX + 本地集成测试验证（见[测试](#测试)）。

---

## 它能做什么

- **自动区分 A-roll / B-roll**：检测有无人声解说（Silero VAD），可手动纠正且会被记住。
- **A-roll 简介 + 标签**：`mlx-whisper` 转写中文解说 → Qwen 文本模型总结，转写全文一并保存可搜索。
- **B-roll 画面标签 + 描述**：抽帧交给视觉模型识别画面内容。
- **界面语言可选（中 / 英）**：整套 UI 文案可在「设置」页切换**英文 / 中文**（默认英文，按设备记忆），与下面的 **AI 输出语言**相互独立、互不影响。
- **AI 输出语言可选**：简介/画面描述可在「设置」页切换**中文 / 英文**（默认中文）。
- **按拍摄日期 + 类型自动归档并重命名**：复制到 `库/YYYY-MM-DD/A-roll(或 B-roll)/`，并按类型顺序重命名为 `A-0001.ext` / `B-0001.ext`（每个日期/类型目录各自计数）。即使 AI 分析失败，原文件仍按日期+类型归档（状态标为 `partial`），AI 简介/标签为尽力而为。详情面板显示新副本路径（File destination），原始源路径折叠在 Source file 里。
- **缩略图墙 + 多维检索**：按拍摄日期**分组展示**（每个日期一个区块，带粘性日期标题），左侧侧栏内置搜索框（按文件名 / 简介 / 描述 / 标签即时过滤），并支持按日期 / 类型 / 标签筛选（可折叠过滤面板）与按拍摄日期的新/旧排序；标签过滤按使用频率排序、可搜索、超量折叠。分析未完成的片段（`partial`）在缩略图上有「部分」标记，一眼可辨。
- **一键打开 / 在 Finder 中查看**：缩略图与详情面板可一键用默认播放器打开视频；日期分组标题可一键在 Finder 中打开该日期文件夹（macOS `open`）。
- **重新分析单个片段**：换模型或结果不佳时一键重跑 AI，保留你的手动纠正与标签。分类判错时，可在详情面板切换 A/B 类型——副本会自动**移动**到正确的 A-roll/B-roll 目录并重命名，`library_path` 同步更新。
- **关键帧推荐（剪辑切点 + 精选帧）**：为每段素材给出最多 N 条（默认 3，可配置）排序的剪辑建议——**A-roll 由文本模型基于转写选段**、**B-roll 由 Qwen3-VL 基于采样帧挑选**，每条含 in/out 时码、代表帧与一句理由。扫描完成后可自动排队（设置开关），也可在详情面板按需生成；画廊卡片有「已有建议」角标。
- **片段拍摄日期显示**：缩略图卡片和详情面板均展示片段的拍摄时间（优先使用嵌入 capture time，回退到文件创建时间）。
- **任务队列管理**：单独的「任务队列」页可查看所有扫描/重分析任务，支持删除、重试失败项、全局暂停/恢复；队列暂停时扫描会自动提示并可选恢复。
- **原生文件夹选择**：设置页选「素材文件夹 / 素材库」时弹出 macOS 原生选择框，返回真实绝对路径（浏览器选择器拿不到绝对路径）。
- **设置页绑定素材库**：首次使用选/填一个绝对路径即可绑定库，**运行时热生效、无需重启**（也支持 `CUTFINDER_LIBRARY` 环境变量）。设置页每项选项均有中文说明文字。
- **扫描后自动刷新**：Scan 完成后自动轮询任务状态并刷新缩略图墙，无需手动操作。
- **深色专业界面**：近黑面板让缩略图突出，A-roll/B-roll 以颜色+图标区分，贴近 FCP 调性（见 [`doc/ui-design.md`](./doc/ui-design.md)）。

### 不破坏原素材（核心约束）

- **原文件只读**，所有整理只发生在复制出来的新素材库里。
- **拍摄时间永不改变**（内嵌 QuickTime/EXIF 时间不被写）。复制保留文件的修改/访问时间，并在 macOS 上额外保留**创建时间**（birth time），重命名/重定位均为同卷 rename，不改任何时间戳。
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
make setup                      # mise install + brew bundle + uv sync + npm install
```

> OMLX 配置可在**设置页**里填（见步骤 2），无需 `.env`。若你偏好用 `.env`，再 `cp .env.example .env` 并填值。

> 没有 mise？先 `brew install mise`，或手动执行：
> ```bash
> cd backend && uv sync           # Python 依赖（含 pytest / mypy / ruff，已随 uv sync 安装）
> cd ../frontend && npm install   # Vite + React + Tailwind
> ```

### 2. 配置 OMLX 连接

需要配置三项：OMLX 地址、API key、（可选）Whisper 模型路径。两种方式，任选其一：

- **设置页（推荐，无需 `.env`）**：启动后打开 http://localhost:5080 → 「设置」→ **OMLX connection** 填写 Base URL / API key / Whisper 路径 → 保存。这些值存到 `~/.cutfinder/config.json`（**全机共用**，换素材库不用重填），保存即生效。

- **`.env`（可选，用于临时覆盖）**：在**仓库根目录**放一个 `.env`：

  ```ini
  # OMLX 本地推理服务器（OpenAI 兼容）。默认假设 :8000；按你的实际端口改。
  OMLX_BASE_URL=http://localhost:8000/v1
  OMLX_API_KEY=your-omlx-key
  ```

  `make dev` / `make check-omlx` / `make test-integration` 会自动加载它；手动用 `uvicorn` 起后端则先 `set -a; source .env; set +a` 导出。

> **优先级**（高→低）：**设置页全局配置**（`~/.cutfinder/config.json`）> **环境变量 / `.env`**。设置页是权威来源——存进去的值始终生效，即使 `.env` 设了同一个键也不会被它盖掉（注意 `make dev` 会把 `.env` 导出成环境变量，所以两者属于同一层「兜底」）。`.env` / 环境变量只用于填设置页尚未配置的键。

### 3. 验证 OMLX 就绪

```bash
make check-omlx                 # 校验文本/视觉模型是否已加载
# → OMLX OK — models: [...]
#   All required text/vision models are present.
```

> `make check-omlx` 只读 `.env` / 环境变量，**不读**设置页存的全局配置。若你走 UI 配置（无 `.env`），可跳过这步，直接在应用里扫描时验证；或临时 `OMLX_BASE_URL=... OMLX_API_KEY=... make check-omlx`。

### 4. 启动开发服务器（推荐：一条命令同时起前后端）

```bash
make dev
# 后端 → http://localhost:5081 （FastAPI）
# 前端 → http://localhost:5080 （Vite，/api 已代理到后端 5081）
```

打开 **http://localhost:5080**，按 `Ctrl+C` 同时停止两个服务。

### 5. 绑定素材库（首次使用）

素材库目录用于存放整理后的副本、缩略图与 SQLite 目录（都在 `<库>/.cutfinder/`）。两种方式：

- **设置页（推荐）**：打开 http://localhost:5080 → 「设置」→ **Set up your library** → 点 **Choose…** 用 macOS 原生选择框选目录（或手填绝对路径）→ **运行时热生效、无需重启**，且选择会被记住（持久化到 `~/.cutfinder`）。
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

### 下载模型（首次使用前，可选预热）

```bash
make models                     # 预下载 mlx-whisper large-v3-mlx + Demucs htdemucs
```

两个模型都会下载到项目的 **`models/` 目录**（已 gitignore）。其实**无需手动运行**——首次使用时会自动下载到 `models/whisper/` 和 `models/demucs/`，`make models` 只是提前预热，免得首次运行卡在下载上。无需配置任何路径。

---

## 测试

### 后端（pytest）

```bash
cd backend

uv run pytest tests/unit             # 仅单元测试（367 项，无需外部服务，秒级）
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
make test-unit         # 后端单元测试（快，tests/unit，无外部依赖）—— 日常用这个
make test              # 后端全量（含 -m integration；本机有 OMLX/.env 时会真跑，可能慢/挂起）
make test-integration  # 仅跑 -m integration（自动加载 .env；需 ffmpeg/OMLX）
make e2e               # Playwright e2e
```

> Vitest 仍需手动进入 frontend/: `cd frontend && npx vitest run`

### 已知遗留项（不影响运行）

- 真实集成测试中**视觉/文本打标的输出文本可能中英混杂**（Qwen3-VL-8B / 文本模型的模型/prompt 表现，非适配器 bug）；结构化结果（description/summary + tags）始终有效。
- **AI 简介为非确定性**：OMLX 调用使用 `temperature=0.7`（并已去掉会让量化模型陷入复读循环的严格 `json_schema`，改为宽松解析），对清晰素材稳定，对**噪声/含糊音轨**的边缘片段可能无法生成简介 —— 此时片段仍会被归档（状态 `partial`），可手动重分析。

---

## 文档

- [需求文档 `doc/proposal.md`](./doc/proposal.md) —— 目标、需求、范围、技术选型
- [详细设计 `doc/detailed-design.md`](./doc/detailed-design.md) —— 模块、接口、数据模型、API、测试与部署
- [UI 设计系统 `doc/ui-design.md`](./doc/ui-design.md) —— 配色/字体/间距 token、组件规范、页面布局（深色优先）
- [任务清单 `doc/tasks/`](./doc/tasks/progress.md) —— 各模块最小任务与总体进度
- [`CLAUDE.md`](./CLAUDE.md) —— 给 AI 协作者的项目约束与架构速览

---

## 打包为 macOS App（CutFinder.app）

把整个应用打包成一个可拖入「应用程序」文件夹的 `CutFinder.app`（自安装启动器）：

```bash
make app          # → dist/CutFinder.app（以及 dist/CutFinder.dmg）
```

把 `dist/CutFinder.app` 拖到 `/Applications`，双击即可：

- 首次启动会**自建运行环境**——用 `uv` 安装 Python 依赖、检测/安装 ffmpeg（有 Homebrew 时自动 `brew install ffmpeg`），随后启动本地服务并在浏览器打开（默认 `http://127.0.0.1:5080`）。之后启动是秒开。
- 运行环境写在 `~/Library/Application Support/CutFinder/`（**不写进 .app 包内**，便于更新/签名）；日志在同目录 `launch.log`。
- `.app` 内置了**预构建的前端**与后端源码，由同一个服务同时提供 UI 与 API（运行时**不需要 Node**）。

> ⚠️ 两件事仍需另行准备（无法塞进我们的 .app）：
> 1. **OMLX** 是独立的第三方菜单栏 App（本地模型服务器），需自行安装并加载 `Qwen` 模型；
> 2. **Whisper 模型**（约 3GB）与 **Demucs htdemucs** 模型在首次使用时自动下载到项目 `models/` 目录（或用 `make models` 预热）。
>
> 该 .app 未做 Apple 代码签名/公证，首次打开可能需「右键 → 打开」放行。品牌图源在 `branding/`。

---

## 路线图

- **v1**：需求 0–7（自定义文件夹、保留拍摄时间、A/B 判定、A-roll 简介、日期+类型归档、标签、缩略图、接 OMLX）—— 已完成。
- **已完成（v1 之外）**：关键帧（剪辑切点）建议（需求 8）；打包为自安装 `CutFinder.app`（`make app`）。
- **后续 / TODO**：
  - **原生 .app 外壳（Swift/ObjC 包装器）**：当前是 shell 脚本 .app，Dock 退出靠 SIGTERM。换成最小原生壳可获得标准应用菜单、稳定的 Dock 生命周期、点击 Dock 图标重开 UI、以及未来代码签名/公证。
  - **导出 transcript 为 Final Cut Pro 可导入的字幕**（A-roll 已有带时间轴的 `Segment`，纯文本格式化即可导出 iTT / SRT；后端可加 `GET /api/clips/{id}/transcript.srt|.itt` + 详情面板「导出字幕」按钮，无需再调模型）。
  - Final Cut Pro 深度集成（FCPXML / 关键词导出；可与上一条合并：把字幕作为 caption 轨道随片段灌入 FCP）。
  - PyInstaller 全离线包 / Tauri 原生窗口。
