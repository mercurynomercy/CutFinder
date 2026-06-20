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
- [ ] **20 · 原生 macOS .app 外壳（Swift 包装器）** — 已设计、待实现。取代 shell 脚本启动器（`packaging/launcher.sh` + `scripts/build-app.sh`，现靠脚本留前台 + 转发 SIGTERM 撑 Dock 生命周期），换成最小 Swift/AppKit 包装器，得到标准应用菜单、稳定 Dock 生命周期、点 Dock 图标重开 UI、代码签名/公证能力，并把「开启/关闭服务」「首次自动装齐依赖」做成原生体验。设计见 `detailed-design.md` §11 与 `ui-design.md` §9。
  - **已确认决策**：① UI 用 **WKWebView 内嵌**现有 web 前端（无浏览器/标签页）；② 服务**启动即自动开启**，菜单可停止/重启；③ 首次启动**自动安装本地依赖**（uv / ffmpeg / Python env / whisper+demucs 模型），**OMLX 仅探测 + 引导**（独立菜单栏 App，无法静默安装，缺失不阻断、弹下载引导）。
  - **要点**：Swift 二进制作 `CFBundleExecutable`、uvicorn 为其子进程（绝不 `exec`）→ Dock tile 稳定、⌘Q 先停服务无孤儿；venv/模型建在 Application Support（bundle 外）→ 签名只需签 Swift Mach-O，Hardened Runtime + JIT/Metal/disable-library-validation entitlements，Developer ID 直分发(DMG)+公证。后端/前端零改动。
  - **落地**：新增 `packaging/macapp/`（swiftc 编译，无 .xcodeproj），`scripts/build-app.sh` 升级为 编译→组 bundle→签名→dmg→公证；删除 `packaging/launcher.sh`。测试以 Provisioner 步骤判定 + OMLX 探测纯函数单测 + 手动验收清单覆盖。
- [x] [**16 关键帧推荐（剪辑切点 + 精选帧，需求 8）**](./16-keyframes.md) — 已实现：A-roll 文本/transcript、B-roll 视觉；扫描后自动排队 + 按需；详情面板建议列表 + 画廊角标 + 设置项。后端 +17 单测、前端 +3 测试，mypy/ruff/tsc 干净。
- [ ] [**17 字幕导出（独立成片 → FCP iTT/SRT）**](./17-subtitle-export.md) — 已设计、待实现。**独立工具**：选一段已剪辑成片 → `mlx-whisper` 重新转写（语言跟随 `output_language`，只转写不翻译）→ 导出 iTT + SRT 到用户选定文件夹；不入库、不分类、源视频只读。设计见 `17-subtitle-export.md` 与 `detailed-design.md` §3.13。
  - 进阶（更后）：FCPXML 深度集成（字幕作为 caption 轨道随片段灌入 FCP）。
- [x] [**18 转写前置人声分离（去 BGM）**](./18-vocal-separation.md) — 已实现：whisper 前用 **Demucs**（`htdemucs`）抽干声扔伴奏，治 BGM 污染 transcript。新增 `VocalSeparator` port + `DemucsSeparator` adapter；`MlxWhisperTranscriber` 可注入 separator（失败回落原始音频）+ `condition_on_previous_text=False`；字幕导出**强制**分离，A-roll 流水线 UI 开关 `vocal_separation` **默认关**。后端 +1（405 单测）、前端 +2（195 测试），mypy/ruff/tsc 干净（仅余历史告警）。设计见 `18-vocal-separation.md` 与 `detailed-design.md` §3.14。
  - 修复：`DemucsSeparator` 原用 `demucs.api`（4.1.0a 才有），装的 demucs 4.0.1 无此模块、运行时必崩；改用 `demucs.pretrained.get_model` + `demucs.apply.apply_model`（含 mix 归一化）。已**真机验证**：htdemucs 真下载、MPS 跑通、集成测试通过（19s 样本 → 正确 16k 单声道干声，约实时）。
  - 待手动验证（需真样本）：对一段**含 BGM** 成片对比开启分离前后 transcript，确认音乐被去除。
- [x] [**19 字幕导出进度条同步（分离+转写两阶段）**](./19-subtitle-progress.md) — 已实现：`patch_tqdm` 拦截 Demucs/mlx-whisper 内部 tqdm，进度引到字幕导出 job（`total=100` + 节流 SSE），前端渲染真实进度条 + 阶段标签（分离[0,0.4]→转写[0.4,1]）。仅字幕导出，A-roll 流水线不传 progress、行为不变。后端 +10 单测（415）、前端 +1（196），mypy/ruff/tsc 干净。**真库验证**：demucs 与 whisper（含子模块遮蔽坑）tqdm 拦截均生效、回调单调收尾 1.0。设计见 `19-subtitle-progress.md` 与 `detailed-design.md` §3.13。
