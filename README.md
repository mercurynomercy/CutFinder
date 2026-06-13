# CutFinder

> 本地运行的 Vlog 视频素材（footage）智能分类与检索工具。灵感来自 [Argus](https://github.com/discoposse/argus)。

把一堆 A-roll（有中文解说）和 B-roll（纯空镜）自动**分类、打标签、生成简介与缩略图**，让你之后能按日期 / 类型 / 标签 / 台词快速找回任意一段素材。面向 macOS（Apple Silicon）+ Final Cut Pro 工作流，**全程离线、AI 全本地**。

> **状态：设计阶段（pre-implementation）。** 目前仓库只有设计文档，尚无可运行代码。下面的安装/使用是**规划中的形态**。

---

## 它能做什么

- **自动区分 A-roll / B-roll**：检测有无人声解说（Silero VAD），可手动纠正且会被记住。
- **A-roll 中文简介 + 标签**：`mlx-whisper` 转写中文解说 → Qwen 文本模型总结，转写全文一并保存可搜索。
- **B-roll 画面标签 + 描述**：抽帧交给视觉模型识别画面内容。
- **按拍摄日期 + 类型自动归档**：复制到 `库/YYYY-MM-DD/A-roll(或 B-roll)/`。
- **缩略图墙 + 多维检索**：按日期 / 类型 / 标签筛选，按台词全文搜索。
- **重新分析单个片段**：换模型或结果不佳时一键重跑 AI，保留你的手动纠正与标签。

### 不破坏原素材（核心约束）

- **原文件只读**，所有整理只发生在复制出来的新素材库里。
- **拍摄时间永不改变**（内嵌 QuickTime/EXIF 时间不被写，复制保留文件时间）。
- **离线**，素材不出本机。
- **幂等**，重扫只处理新文件（指纹去重），不重复复制。

---

## 架构概览

```
前端 (Vite + React)
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

## 前置条件

- macOS，Apple Silicon
- [OMLX](https://github.com/jundot/omlx) 已安装，并加载好文本与视觉模型
- [mise](https://mise.jdx.dev/)、[uv](https://docs.astral.sh/uv/)、[Homebrew](https://brew.sh/)

> ⚠️ AI 推理需要 Apple Metal GPU，**不能跑在 Docker 容器里**，只能原生运行。

---

## 安装与运行（规划）

```bash
# 1. 装好 OMLX App 并加载模型

# 2. 克隆
git clone <repo> && cd CutFinder

# 3. 配置密钥/端点
cp .env.example .env       # 填入 OMLX_BASE_URL 与 OMLX_API_KEY

# 4. 一键装环境（mise 装 Python/Node 版本，uv 装后端依赖，brew 装 ffmpeg，npm 装前端）
mise install && make setup

# 5. 验证 OMLX 接口与模型就绪
make check-omlx

# 6. 起前后端
make dev
```

`.env` 示例：

```dotenv
OMLX_BASE_URL=http://localhost:8000/v1
OMLX_API_KEY=your-omlx-key
```

---

## 测试

```bash
make test              # 后端 pytest(单元) + 前端 Vitest，全 mock 外部依赖，秒级
make test-integration  # pytest -m integration，对真实 ffmpeg/whisper/OMLX 跑(需样本素材)
make e2e               # Playwright 关键流程(后端用假适配器+预置 DB)
```

---

## 文档

- [需求文档 `doc/proposal.md`](./doc/proposal.md) —— 目标、需求、范围、技术选型
- [详细设计 `doc/detailed-design.md`](./doc/detailed-design.md) —— 模块、接口、数据模型、API、测试与部署
- [`CLAUDE.md`](./CLAUDE.md) —— 给 AI 协作者的项目约束与架构速览

---

## 路线图

- **v1**：需求 0–7（自定义文件夹、保留拍摄时间、A/B 判定、A-roll 简介、日期+类型归档、标签、缩略图、接 OMLX）
- **后续**：关键帧（剪辑切点）建议、Final Cut Pro 深度集成（FCPXML/关键词）、打包独立 `.app`
