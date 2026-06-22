# CutFinder

<p align="center">
  <img src="branding/full-logo.png" alt="CutFinder logo" width="200"/>
</p>

## 截图

<p align="center">
  <img src="doc/images/example.png" alt="CutFinder UI — 按日期分组的缩略图墙、筛选面板与详情面板"/>
</p>

<p align="center">
  <img src="doc/images/ai_rough_cut.png" alt="CutFinder 初剪导演（beta）—— 左侧对话、右侧按日期分章的分镜表（含时码与缩略图）"/>
  <br/>
  <em>初剪导演（beta）—— 对话描述需求，得到按日期分章的分镜表。</em>
</p>

> 本地运行的 Vlog 视频素材（footage）智能分类与检索工具。灵感来自 [Argus](https://github.com/discoposse/argus)。

**English docs → [README.md](./README.md)**

把一堆 A-roll（有中文解说）和 B-roll（纯空镜）自动**分类、打标签、生成简介与缩略图**，让你之后能按日期 / 类型 / 标签 / 台词快速找回任意一段素材。面向 macOS（Apple Silicon）+ Final Cut Pro 工作流，**全程离线、AI 全本地**。

> ### ⚠️ 仅支持 Apple Silicon（M 系列）芯片的 Mac（M1 及以上）
> CutFinder **只能跑在 M 系列芯片的 Mac 上**。因为所有模型都用 Apple 的 **MLX** 框架在本地运行 —— OMLX（文本/视觉）、`mlx-whisper` / Qwen3-ASR + ForcedAligner（语音）**都只支持 Apple Silicon**。Intel Mac、Windows、Linux **均不支持**。

---

## 快速开始 —— `make app`

推荐用原生的 **`CutFinder.app`** 来跑 CutFinder：一个用 Swift/AppKit 写的小外壳，把界面装进独立窗口（WKWebView，不开浏览器标签页），托管本地服务，并在**首次启动时自建所需的一切**。一条命令即可构建。

> **有一个前置依赖装在 .app 之外：** [OMLX](https://github.com/jundot/omlx)，本地 Apple Silicon 模型服务器（菜单栏 App）。装好它并加载 `Qwen3.6-35B-A3B`（文本）+ `Qwen3-VL-8B`（视觉）。CutFinder 首次运行会检测它，**缺失时会引导你安装** —— 没有它，扫描 / 转写 / 缩略图仍可用，只有 A-roll 简介和 B-roll 打标需要它。

### 1. 构建 App

```bash
git clone <repo> && cd CutFinder
make app          # → dist/CutFinder.app（以及 dist/CutFinder.dmg）
```

`make app` 用 **SwiftPM** 编译 Swift 外壳并内置预构建的前端，所以**构建机**需要 **Xcode 命令行工具**（`xcode-select --install`）和 Node。而运行*已构建好*的 `.app` 两者都不需要 —— `.app` 自带 UI 与后端源码，由同一个服务同时提供二者（运行时不需要 Node）。

### 2. 安装与首次启动

把 `dist/CutFinder.app` 拖到 `/Applications`，双击即可：

- **首次启动会自建运行环境。** 原生安装界面会显示进度：同步运行时、安装 `uv` 与 `ffmpeg`（有 Homebrew 时自动 `brew install`，否则引导你安装）、创建 Python 环境（`uv sync`）、下载 Whisper + Demucs 模型（约 3GB）。之后启动是秒开。
- **服务自动启动**，UI 加载在 App 自己的窗口里。可用**「服务」菜单**来 启动 / 停止 / 重启 后端，或选「在浏览器中打开」用标签页。
- **标准 Mac App 行为** —— 完整应用菜单；关窗口后服务继续运行；点 Dock 图标重新打开窗口；⌘Q 干净地停止服务（不留孤儿进程）。
- 运行环境写在 `~/Library/Application Support/CutFinder/`（**不写进 .app 包内**，便于更新/签名）；日志在同目录 `launch.log`。

> **未签名的开发版？** 当本机有 Developer ID 签名身份时，`make app` 会用 **Hardened Runtime** 签名（设置了 `CUTFINDER_NOTARY_PROFILE` 时还会公证 + staple）；否则产出未签名的开发版，首次打开需「**右键 → 打开**」放行。因为 Python 环境与模型都在包外，只需签那个很小的 Swift 二进制。

### 3. 开始使用

1. **配置 OMLX** —— **设置 → OMLX 连接** → 填入 Base URL / API key → 保存。存到 `~/.cutfinder/config.json`（**全机共享**；Whisper 模型、人声分离 / 自动关键帧开关也存在这里）。
2. **绑定素材库** —— **设置 → 设置素材库** → 用原生选择器选一个绝对路径。整理后的副本、缩略图和 SQLite 目录都放在这里（全在 `<library>/.cutfinder/` 下）。**改了无需重启**即时生效。
3. **添加源文件夹并扫描** —— 把 CutFinder 指向你的素材文件夹，运行扫描。每个新片段会被判定 A-roll/B-roll、转写/打标、生成缩略图，并复制到 `<library>/YYYY-MM-DD/A-roll(或 B-roll)/`。**照片（`.jpg/.jpeg/.png/.heic`）也会一并入库** —— 作为独立的 **照片** 类型，复制到 `<library>/YYYY-MM-DD/photos/`。重新扫描只处理新文件（按指纹去重）—— 原始文件永不改动。
4. **浏览、检索、纠正** —— 缩略图墙按拍摄日期分组；可按文件名、简介、标签、日期、类型检索/筛选。判错的 A/B 或标签可手动改 —— 改动会被记住。
5. **导出字幕** —— 选一个剪好的成片 → 重新转写（先去掉 BGM）→ 导出 Final Cut Pro 原生的 **iTT + SRT** 到你选的文件夹。

> 想从源码运行（用于开发）？见下方[从源码运行](#从源码运行开发)。

---

## 它能做什么

- **自动区分 A-roll / B-roll**：检测有无人声解说（Silero VAD），可手动纠正且会被记住。
- **A-roll 简介 + 标签**：由可选的语音引擎转写中文解说 → Qwen 文本模型总结，转写全文一并保存可搜索。
- **语音引擎可选（Whisper 或 Qwen3-ASR + ForcedAligner）**：在「设置」里选择；该选择会作用于**所有** A-roll 语音处理（转写、关键帧、字幕导出）。中文 / 中英混合推荐用 Qwen 组合：文本更准，且经本地强制对齐得到真实的逐字时间戳（不会像 whisper 那样时间轴漂移），按 VAD 切段因此能处理超长视频。详见 [模型服务](#模型服务)。
- **B-roll 画面标签 + 描述**：抽帧交给视觉模型识别画面内容。
- **照片入库**：静态照片（`.jpg/.jpeg/.png/.heic`；HEIC 经 `pillow-heif` 解码）与视频一起扫描，作为独立的 **照片** 类型入库：把一张 JPEG 预览交给视觉模型出描述 + 标签，按 EXIF 拍摄时间归档（缺失则回退文件时间），原图复制到 `<library>/YYYY-MM-DD/photos/photo-0001.ext`。照片没有转写、关键帧、重分析。支持的照片后缀可在「设置」里编辑。
- **界面语言可选（中 / 英）**：整套 UI 文案可在「设置」页切换**英文 / 中文**（默认英文，按设备记忆），与下面的 **AI 输出语言**相互独立、互不影响。
- **AI 输出语言可选**：简介/画面描述可在「设置」页切换**中文 / 英文**（默认中文）。
- **按拍摄日期 + 类型自动归档并重命名**：复制到 `库/YYYY-MM-DD/A-roll(或 B-roll)/`（照片在 `.../photos/`），并按类型顺序重命名为 `A-0001.ext` / `B-0001.ext` / `photo-0001.ext`（每个日期/类型目录各自计数）。即使 AI 分析失败，原文件仍按日期+类型归档（状态标为 `partial`），AI 简介/标签为尽力而为。详情面板显示新副本路径（File destination），原始源路径折叠在 Source file 里。
- **缩略图墙 + 多维检索**：按拍摄日期**分组展示**（每个日期一个区块，带粘性日期标题），左侧侧栏内置搜索框（按文件名 / 简介 / 描述 / 标签即时过滤），并支持按日期 / 类型 / 标签筛选（可折叠过滤面板）与按拍摄日期的新/旧排序；标签过滤按使用频率排序、可搜索、超量折叠。分析未完成的片段（`partial`）在缩略图上有「部分」标记，一眼可辨。
- **一键打开 / 在 Finder 中查看**：缩略图与详情面板可一键用默认播放器打开视频；日期分组标题可一键在 Finder 中打开该日期文件夹（macOS `open`）。
- **重新分析单个片段**：换模型或结果不佳时一键重跑 AI，保留你的手动纠正与标签。分类判错时，可在详情面板切换 A/B 类型——副本会自动**移动**到正确的 A-roll/B-roll 目录并重命名，`library_path` 同步更新。
- **关键帧推荐（剪辑切点 + 精选帧）**：为每段素材给出最多 N 条（默认 3，可配置）排序的剪辑建议——**A-roll 由文本模型基于转写选段**、**B-roll 由 Qwen3-VL 基于采样帧挑选**，每条含 in/out 时码、代表帧与一句理由。扫描完成后可自动排队（设置开关，**默认关**，因其最贵），也可在详情面板按需生成；画廊卡片有「已有建议」角标。
- **初剪导演 —— 对话式分镜表（beta）**：在对话框里描述你想要的成片（日期范围、目标时长、画面比例、风格/节奏），本地 Qwen 文本模型就会基于已编目素材产出一份精确到片段内 in/out 的**分镜表**：**按拍摄日期分章**、每天内**按真实拍摄时间线排序**，以 A-roll 解说为叙事主线（依据转写选段）、配 B-roll 空镜插空。每行显示该片段的日期与文件名，方便快速找素材；整份可一键**复制为 Markdown** 贴进剪辑软件。日期/时长/比例等参数直接从你的消息里解析，生成时**按每个拍摄日期分别跑一遍**以保证本地模型的稳定性，**导演 Prompt 完全可在对话框内编辑**（并可一键恢复自带默认）。全程**只读编目**，不渲染、不导出剪辑工程。**目前为 beta，会持续改进。**
- **片段拍摄日期显示**：缩略图卡片和详情面板均展示片段的拍摄时间（优先使用嵌入 capture time，回退到文件创建时间）。
- **任务队列管理**：单独的「任务队列」页可查看所有扫描/重分析任务，支持删除、重试失败项、全局暂停/恢复；队列暂停时扫描会自动提示并可选恢复。
- **进度条刷新后不丢**：刷新页面后，扫描/关键帧进度条与字幕导出进度条会自动重新挂接到后台仍在跑的任务（活儿没停，只是 UI 一度丢了引用），不必重新触发。
- **素材库清理**：如果你直接在素材库目录里删了副本，顶部 **⋮ 菜单 →「清理已删除的文件」** 会在二次确认后清掉它们残留的目录记录（及缩略图/关键帧）；若素材库不可达（如外接盘未挂载）则跳过，绝不误删整个目录。原始源文件永不被动。
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
适配器层 ── ffmpeg/ffprobe · Silero VAD · mlx-whisper / Qwen3-ASR+ForcedAligner · OMLX(文本+视觉) · Pillow(照片) · SQLite
```

每个外部依赖都藏在接口后面，业务逻辑只依赖接口 → 模块可独立替换与测试。详见 [`doc/detailed-design.md`](./doc/detailed-design.md)。

### 模型服务

| 用途                     | 模型（OMLX 上的 id）                                       | 运行方式                    |
| ------------------------ | ---------------------------------------------------------- | --------------------------- |
| A-roll 简介/标签（文本） | `Qwen3.6-35B-A3B`                                          | OMLX（OpenAI 兼容接口）     |
| B-roll 画面识别（视觉）  | `Qwen3-VL-8B`                                              | OMLX（同接口，base64 传帧） |
| 照片描述 + 标签（视觉）  | `Qwen3-VL-8B`                                              | OMLX（照片的 JPEG 预览以 base64 传入） |
| A-roll 语音转写          | **语音引擎，「设置」里可选：** `mlx-whisper`（默认 `mlx-community/whisper-large-v3-mlx`）**或** Qwen3-ASR + ForcedAligner（`mlx-community/Qwen3-ASR-1.7B-8bit` + `Qwen3-ForcedAligner-0.6B-8bit`） | 独立本地进程（OMLX 不托管音频） |
| A/B 人声检测             | Silero VAD                                                 | 本地                        |

**语音引擎（设置 → 语音引擎）。** 一个选项决定**所有** A-roll 语音处理 —— 编目转写、关键帧推理、字幕导出：

- **Whisper** —— `mlx-whisper` large-v3，英文较稳。
- **Qwen3-ASR + ForcedAligner**（中文 / 中英混合推荐）—— Qwen3-ASR 的中文文本远比 whisper 准确，ForcedAligner 给出真实的逐字时间戳，因此长片段的字幕也不会像 whisper 那样越到后面越漂移。音频先按静音（Silero VAD）切成片段（默认 60 秒，上限 300 秒 —— 对齐器单段只能标注约 400 秒内的时间戳），所以能处理任意长度的视频。两个模型都通过 `mlx-audio` 本地运行（OMLX 无法经 HTTP 托管对齐器）。

文本与视觉模型都由 [OMLX](https://github.com/jundot/omlx)（Apple Silicon 本地推理服务器，菜单栏 App）托管。

> ⚠️ 模型名必须与你的 OMLX 实际加载的 id 完全一致。默认视觉模型为 `Qwen3-VL-8B`；如你的 OMLX 暴露的是带后缀的 id，请在「设置」页或 `<库>/.cutfinder/config.json` 里改 `vision_model` / `text_model`。

---

## 要求 (Requirements)

### 必需

| 依赖                                                 | 说明                                                                                                           |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **macOS + Apple Silicon**                            | AI 推理依赖 Metal GPU，无法在 Docker / x86_macOS 上运行                                                        |
| [OMLX](https://github.com/jundot/omlx) ≥ 0.1         | Apple Silicon 本地模型服务器（菜单栏 App），需预加载 `Qwen3.6-35B-A3B`（文本）和 `Qwen3-VL-8B`（视觉）两个模型 |
| [uv](https://docs.astral.sh/uv/)                     | Python 依赖管理（`pip install uv`）                                                                            |
| **Python ≥ 3.12**                                    | uv 会自动按 `mise.toml` 拉取 3.12 虚拟环境                                                                     |
| **Node.js ≥ 20** + `npm`                             | 前端开发服务器与构建工具                                                                                       |
| [ffmpeg](https://ffmpeg.org/) (`ffprobe` + `ffmpeg`) | 视频元数据提取与缩略图生成（Homebrew: `brew install ffmpeg`）                                                  |

### 可选

- [mise](https://mise.jdx.dev/) — 自动管理 Python / Node 版本（`mise.toml`）
- [Homebrew](https://brew.sh/) — 用于安装 ffmpeg / OMLX

> ⚠️ **AI 推理必须原生运行**，不能跑在 Docker 容器里。

---

## 从源码运行（开发）

> 用于日常开发。若只是想**使用** CutFinder，请改用 [`make app`](#快速开始--make-app) 构建原生 App。

### 1. 安装依赖

```bash
git clone <repo> && cd CutFinder
make setup                      # mise install + brew bundle + uv sync + npm install
```

> OMLX 配置在**设置页**里填（见步骤 2），不用手改配置文件。

> 没有 mise？先 `brew install mise`，或手动执行：
>
> ```bash
> cd backend && uv sync           # Python 依赖（含 pytest / mypy / ruff，已随 uv sync 安装）
> cd ../frontend && npm install   # Vite + React + Tailwind
> ```

### 2. 配置 OMLX 连接

配置两项：OMLX 地址和 API key。两种方式，任选其一：

- **设置页（推荐）**：启动后打开 http://localhost:5080 → 「设置」→ **OMLX connection** 填写 Base URL / API key → 保存。这些值存到 `~/.cutfinder/config.json`（**全机共用**，换素材库不用重填），保存即生效。

- **系统环境变量（可选）**：在 shell 里 `export OMLX_BASE_URL` / `OMLX_API_KEY`（适合 CI / 临时跑）：

  ```bash
  export OMLX_BASE_URL=http://localhost:8000/v1
  export OMLX_API_KEY=your-omlx-key
  ```

> **优先级**（高→低）：**设置页全局配置**（`~/.cutfinder/config.json`）> **系统环境变量**。设置页是权威来源——存进去的值始终生效，即使环境变量设了同一个键也不会被它盖掉；环境变量只用于填设置页尚未配置的键。（已不再使用 `.env` 文件。）

### 3. 验证 OMLX 就绪

```bash
make check-omlx                 # 校验文本/视觉模型是否已加载
# → OMLX OK — models: [...]
#   All required text/vision models are present.
```

> `make check-omlx` 与应用用同一套优先级解析凭据（`~/.cutfinder/config.json` > 系统环境变量），所以无论你走 UI 还是环境变量配置都能用。

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
- **环境变量**：在 shell 里 `export CUTFINDER_LIBRARY=/path/to/library`，再 `make dev`。

> 未绑定库时后端正常启动，但目录类接口返回 503、「设置」页显示绑定向导，直到你绑定一个库。

### 手动分起（调试用）

```bash
# 终端 1 — 后端（OMLX 配置来自 ~/.cutfinder/config.json 或 export 的环境变量）
cd backend
CUTFINDER_LIBRARY=/path/to/library uv run uvicorn cutfinder.api.app:app --reload --port 5081

# 终端 2 — 前端
cd frontend && npx vite        # http://localhost:5080
```

### 下载模型（首次使用前，可选预热）

```bash
make models                     # 预下载 mlx-whisper large-v3-mlx + Demucs htdemucs
```

模型会下载到项目的 **`models/` 目录**（已 gitignore）。其实**无需手动运行**——首次使用时会自动下载：whisper 到 `models/whisper/`、Demucs 到 `models/demucs/`，选择 **Qwen** 语音引擎时 Qwen3-ASR + ForcedAligner 到 `models/qwen/`。`make models` 只是提前预热默认模型，免得首次运行卡在下载上。无需配置任何路径。

---

## 测试

### 后端（pytest）

```bash
cd backend

uv run pytest tests/unit             # 仅单元测试（515 项，无需外部服务，秒级）
uv run pytest -m integration         # 集成测试（需真实 OMLX / ffmpeg / 样片）
uv run mypy cutfinder/               # 类型检查（strict，clean）
uv run ruff check cutfinder/         # linting（clean）
```

集成测试在缺少 OMLX / 样片时会**自动 skip**，不会误报失败。要真正跑 OMLX 链路，先配好 OMLX（设置页或环境变量），再：

```bash
cd backend
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
make test              # 后端全量（含 -m integration；配好 OMLX 时会真跑，可能慢/挂起）
make test-integration  # 仅跑 -m integration（需 ffmpeg + 已配置的 OMLX）
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

> 品牌图源在 `branding/`。
