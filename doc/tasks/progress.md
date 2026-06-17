# CutFinder 总体进度

> 每个模块一个任务文件，勾选表示**整模块完成**（子任务全过 + 完成标准达成）。
> 依据：[`proposal.md`](../proposal.md)、[`detailed-design.md`](../detailed-design.md)、[`ui-design.md`](../ui-design.md)。
> 建议按阶段顺序推进：基础 → 适配器 → 核心 → 接口 → 前端 → 集成。

## 阶段 0 · 基础
- [x] [00 项目脚手架](./00-scaffold.md) — 目录结构、domain 模型、ports 接口、uv/mise/Brewfile、测试框架

## 阶段 1 · 适配器（外部依赖，互相独立）
- [x] [01 Config 配置](./01-config.md)
- [x] [02 MetadataProbe 元数据](./02-metadata-probe.md)
- [x] [03 Media 缩略图/抽帧](./03-media.md)
- [x] [04 SpeechDetector 人声检测](./04-speech-detector.md)
- [x] [05 Transcriber 语音转写](./05-transcriber.md)
- [x] [06 Summarizer 文本总结(OMLX)](./06-summarizer.md)
- [x] [07 VisionTagger 画面识别(OMLX)](./07-vision-tagger.md)
- [x] [08 LibraryWriter 库文件组织](./08-library-writer.md)
- [x] [09 CatalogRepository 仓储](./09-catalog-repository.md)

## 阶段 2 · 核心逻辑
- [x] [10 Scanner 扫描去重](./10-scanner.md)
- [x] [11 Orchestrator 流水线编排](./11-orchestrator.md)
- [x] [12 Worker 队列+SSE](./12-worker-queue.md)

## 阶段 3 · 接口
- [x] [13 API 层(FastAPI)](./13-api.md)

## 阶段 4 · 前端
- [x] [14 Frontend 前端](./14-frontend.md)

## 阶段 5 · 集成与部署
- [x] [15 环境/部署/集成测试](./15-env-deploy.md) — ruff clean；289 单元测试通过（含 `create_app` 装配测试）。
  - 修复：`create_app` 接线层（错误 import / 不完整的 Orchestrator 装配 / 仓储构造），补 `uvicorn ...:app` 模块级入口，Vite `/api` 代理 + 端口（5080/5081），`uv sync` 默认装 dev 依赖，`check-omlx` 改为真实可跑脚本，`settings` 路由读写修正，`record_copy` 仅在仓储提供时调用。
  - 遗留（不影响运行，后续清理）：mypy strict 仍有历史告警；前端 4 个测试套件历史性失败。

---

### 里程碑
- [x] **可跑通单元测试**（289 项，`make test` 全绿）
- [x] **后端 API 可用**（`create_app` 真实装配可启动；`uvicorn ...:app` / `make dev` 可跑通）
- [x] **真实推理链路已验证**（对真实 OMLX + 本地 ffmpeg/mlx-whisper/Silero 跑通集成测试）：
  - 文本总结 `Qwen3.6-35B-A3B` ✓ · 视觉打标 `Qwen3-VL-8B` ✓（真实帧直连返回 description+tags）
  - ffmpeg 元数据/缩略图 ✓ · ffprobe ✓ · Silero VAD 5/5 ✓ · mlx-whisper `whisper-large-v3-mlx` 3/3 ✓
  - 期间补修：`silero-vad`/`onnxruntime` 缺依赖、Whisper 模型 id（`large-v3` → `mlx-community/whisper-large-v3-mlx`）。
- [ ] **全链路端到端**（扫描→分类→归档→检索 的一次性贯通脚本/手测尚未串跑；各环节已分别验证）
  - 备注：视觉集成测试改用真实帧后单测在高负载下推理偏慢；适配器本身已直连验证通过。

---

### 待办 (TODO)
- [ ] **原生 macOS .app 外壳**：现为 shell 脚本启动器（`packaging/launcher.sh` + `scripts/build-app.sh`），Dock 退出依赖 SIGTERM 转发。后续用最小 Swift/ObjC 包装器替代，获得标准应用菜单、稳定的 Dock 生命周期、点击 Dock 图标重开 UI，以及代码签名/公证能力。
- [ ] **关键帧（剪辑切点）推荐（需求 8）** — 进行中。
