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
- [x] [**21「扫描后自动整理关键帧」设置开关**](./21-keyframe-toggle.md) — 已实现：task 16 已有 `keyframe_auto` 基建（pref + 设置开关 + worker 接线），实测有效默认为「开」（`Prefs.keyframe_auto=True`）。按用户决策改为**默认关**：`config.Prefs`/`schemas.PrefsOut`/前端 checkbox 默认 + mock 全部 `False`。后端 58 测试通过。
- [x] [**22 库文件删除 → 同步清理（DB + 缩略图 + 关键帧）**](./22-library-sync-delete.md) — 已实现「带确认的手动对账」：`Orchestrator.find_orphaned_clips()`（仅查副本是否在盘，源只读）+ `delete_clips()`（删 DB 行 + 缩略图 + 关键帧帧目录）；API `GET/POST /api/library/orphans`，**整库不可达 → `library_reachable=False` 不提议删除**；入口在顶部 ⋮ 菜单「清理已删除的文件」+ 二次确认（不必进设置）。后端 +4 单测、前端 +2 测试（App 菜单流程）。
- [x] [**23 照片（静态图片）分析入库**](./23-photo-analysis.md) — 已实现：独立 **photo** roll 类型，归档到 `<库>/<date>/photos/photo-0001.<ext>`（源只读、保留时间）。新增 Pillow 适配器（`PillowImageProbe` 读 EXIF 拍摄时间+尺寸、`PillowThumbnailMaker` 出 JPEG 预览，HEIC 经 pillow-heif）；`Orchestrator._process_photo` 走预览→Qwen3-VL 描述/标签→归档，**无 VAD/转写/关键帧/重分析**。扫描合并视频+照片扩展名。前端：照片筛选项、详情面板降级（隐藏 A/B 切换、关键帧、重分析）、画廊角标。**真机验证** EXIF/HEIC/预览通过。后端 +9 单测（444）。
- [x] [**24 刷新页面后进度条恢复（dashboard + 字幕导出）**](./24-progress-resume.md) — 已实现（纯前端）：后端已有 `GET /api/jobs`（含 kind/done/total）+ `GET /api/jobs/{id}/events` SSE。App 挂载时领回活跃的非字幕 job → 顶部进度条恢复（JobsPanel 自带轮询+SSE 重订阅）；字幕页挂载时领回活跃 subtitle job → 恢复进度条。前端 +2 测试。
- [~] [**20 原生 macOS .app 外壳（Swift 包装器）**](./20-native-app.md) — **代码实现完成 + 自动校验通过，GUI/首装/签名待手动验收**。取代 shell 脚本启动器，换成 SwiftPM 构建的 Swift/AppKit 包装器（WKWebView 内嵌现有 web 前端），得到标准应用菜单、稳定 Dock 生命周期、点 Dock 图标重开 UI、代码签名/公证能力，并把「开启/关闭服务」「首次自动装齐依赖」做成原生体验。设计见 `detailed-design.md` §11 与 `ui-design.md` §9。
  - **已确认决策**：① UI 用 **WKWebView 内嵌**现有 web 前端；② 服务**启动即自动开启**，菜单可停止/重启；③ 首次启动**自动安装本地依赖**（uv / ffmpeg / Python env / whisper+demucs 模型），**OMLX 仅探测 + 引导**；④ 构建/测试用 **SwiftPM**（非 raw swiftc，以满足「完整单测」）。
  - **已落地**：`packaging/macapp/`（SwiftPM：`CutFinderCore` 纯逻辑库 + `CutFinder` AppKit 可执行）。`swift build`/`-c release` 零错误；`CutFinderCore` **30 项 XCTest 全绿**（ProvisionPlanner / OMLXProbe / PayloadPaths）。`scripts/build-app.sh` 升级为 前端→payload→`swift build -c release`→bundle→（有身份）codesign+hardened entitlements→dmg→（有 profile）公证；新增 `CutFinder.entitlements`；删除 `packaging/launcher.sh`。后端/前端零改动。
  - **待手动验收**（无人环境不执行）：双击 .app 首装→自动起服务→WKWebView 展示 UI；菜单开启/停止/重启；关窗不退 + Dock 重开 + ⌘Q 无孤儿；真实 `codesign`+公证（需 Developer ID）。详见 `20-native-app.md`「手动验收清单 / 当前状态」。
- [x] [**16 关键帧推荐（剪辑切点 + 精选帧，需求 8）**](./16-keyframes.md) — 已实现：A-roll 文本/transcript、B-roll 视觉；扫描后自动排队 + 按需；详情面板建议列表 + 画廊角标 + 设置项。后端 +17 单测、前端 +3 测试，mypy/ruff/tsc 干净。
- [ ] [**17 字幕导出（独立成片 → FCP iTT/SRT）**](./17-subtitle-export.md) — 已设计、待实现。**独立工具**：选一段已剪辑成片 → `mlx-whisper` 重新转写（语言跟随 `output_language`，只转写不翻译）→ 导出 iTT + SRT 到用户选定文件夹；不入库、不分类、源视频只读。设计见 `17-subtitle-export.md` 与 `detailed-design.md` §3.13。
  - 进阶（更后）：FCPXML 深度集成（字幕作为 caption 轨道随片段灌入 FCP）。
- [x] [**18 转写前置人声分离（去 BGM）**](./18-vocal-separation.md) — 已实现：whisper 前用 **Demucs**（`htdemucs`）抽干声扔伴奏，治 BGM 污染 transcript。新增 `VocalSeparator` port + `DemucsSeparator` adapter；`MlxWhisperTranscriber` 可注入 separator（失败回落原始音频）+ `condition_on_previous_text=False`；字幕导出**强制**分离，A-roll 流水线 UI 开关 `vocal_separation` **默认关**。后端 +1（405 单测）、前端 +2（195 测试），mypy/ruff/tsc 干净（仅余历史告警）。设计见 `18-vocal-separation.md` 与 `detailed-design.md` §3.14。
  - 修复：`DemucsSeparator` 原用 `demucs.api`（4.1.0a 才有），装的 demucs 4.0.1 无此模块、运行时必崩；改用 `demucs.pretrained.get_model` + `demucs.apply.apply_model`（含 mix 归一化）。已**真机验证**：htdemucs 真下载、MPS 跑通、集成测试通过（19s 样本 → 正确 16k 单声道干声，约实时）。
  - 待手动验证（需真样本）：对一段**含 BGM** 成片对比开启分离前后 transcript，确认音乐被去除。
- [x] [**25 初剪导演 Agent（对话生成分镜表）**](./25-rough-cut-agent.md) — **代码实现完成 + 自动测试通过，真机集成 eval 待手动**。**独立工具**：在已编目素材库之上多轮对话，按日期范围/时长/风格/节奏产出**精确到片段内 in/out 的文字分镜表（A-roll 叙事主线 + B-roll 插空，含缩略图 + 章节分组）**供照搬剪辑软件；**方案 C 受约束工具调用环**（确定性脚手架 + 护栏，LLM 只做创意选择），全本地走 Qwen3.6（OMLX），必要时 Qwen3-VL 现场看 B-roll；会话持久化 SQLite、可重开/可删除；**不渲染、不导出剪辑工程**（FCPXML 后续）。后端 +46 单测（490 全绿）、前端 +1 套件（3 测试），mypy/ruff 干净。`cutplan/`（format/director）+ `pipeline/cutplan_service` + `adapters/{sqlite_cutplan,sqlite_footage,omlx_agent,broll_inspector}` + worker `cutplan` job + `api/cut_routes` + `features/cutplan`。设计见 `25-rough-cut-agent.md` 与 `detailed-design.md` §3.15。
- [x] [**19 字幕导出进度条同步（分离+转写两阶段）**](./19-subtitle-progress.md) — 已实现：`patch_tqdm` 拦截 Demucs/mlx-whisper 内部 tqdm，进度引到字幕导出 job（`total=100` + 节流 SSE），前端渲染真实进度条 + 阶段标签（分离[0,0.4]→转写[0.4,1]）。仅字幕导出，A-roll 流水线不传 progress、行为不变。后端 +10 单测（415）、前端 +1（196），mypy/ruff/tsc 干净。**真库验证**：demucs 与 whisper（含子模块遮蔽坑）tqdm 拦截均生效、回调单调收尾 1.0。设计见 `19-subtitle-progress.md` 与 `detailed-design.md` §3.13。
- [~] [**26 初剪导演升级：按天 mini-agent**](./26-rough-cut-per-day-agent.md) — **代码实现完成 + 自动测试通过（526 全绿、ruff/mypy 干净），真机 eval 待手动。** 每天一个 scoped 工具循环（深挖 transcript + 按需看 B-roll + 自然收口），`cut_director_mode` 开关（agent/staged），不收口回落纯 JSON；含**每日去重护栏**防幻觉重复调用 + round-cap 防死循环。
- [~] [**27 初剪实时进度 + 部分分镜先显示**](./27-rough-cut-live-progress.md) — **代码实现完成 + 自动测试通过（后端 526、前端 cutplan 6/6），真机验收待手动。** 逐天/逐片段实时状态（"第 k/N 天 · 查看片段 #X"）+ 已完成日期分镜先显示、其余标注生成中。沿用轮询（无 SSE/线程桥接）：director 把进度串(内存)+部分 plan 写进 store，前端 `resumePoll` 增量读取。把 25 的"每天一次纯 JSON 补全"升级为"每天一个 scoped 工具循环"（`get_clip_detail` 深挖 transcript + 按需 `inspect_broll` 看画面 + 自然收口 `emit_plan`），**确定性 Python 编排**（按天拆分/排序/时长均分/校验/失败兜底）骨架复用 25。实测：单日小上下文下 tool 收口可靠（Qwen3.6 5/5、Gemma4-26b 4/5），**不**用 named/required 强制收口（OMLX 不稳），靠 `tool_choice="auto"` + round-cap 兜底（不收口的天回落纯 JSON）。`cut_director_mode` 开关保留 staged 作 fallback。**v1 不上 critic 审片 agent**（v2）。设计见 `26-rough-cut-per-day-agent.md`。
