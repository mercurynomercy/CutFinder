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
- [ ] [05 Transcriber 语音转写](./05-transcriber.md) — unit tests done (15/15 pass); integration test pending
- [ ] [06 Summarizer 文本总结(OMLX)](./06-summarizer.md)
- [ ] [07 VisionTagger 画面识别(OMLX)](./07-vision-tagger.md)
- [ ] [08 LibraryWriter 库文件组织](./08-library-writer.md)
- [ ] [09 CatalogRepository 仓储](./09-catalog-repository.md)

## 阶段 2 · 核心逻辑
- [ ] [10 Scanner 扫描去重](./10-scanner.md)
- [ ] [11 Orchestrator 流水线编排](./11-orchestrator.md)
- [ ] [12 Worker 队列+SSE](./12-worker-queue.md)

## 阶段 3 · 接口
- [ ] [13 API 层(FastAPI)](./13-api.md)

## 阶段 4 · 前端
- [ ] [14 Frontend 前端](./14-frontend.md)

## 阶段 5 · 集成与部署
- [ ] [15 环境/部署/集成测试](./15-env-deploy.md)

---

### 里程碑
- [ ] **可跑通单元测试**（阶段 0–2 完成，`make test` 全绿）
- [ ] **后端 API 可用**（阶段 3 完成，假数据可访问）
- [ ] **端到端可用**（阶段 4–5 完成，真素材跑通扫描→检索）
