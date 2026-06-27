# Docs Consolidation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Rewrite and consolidate all CutFinder docs into a clean, maintainable set of 3 files (proposal + detailed-design+ui-design merged + tasks README), removing incremental update history and consolidating 32 task files into one.

**Architecture:** Each doc is rewritten once from scratch, extracting content from existing docs and git history. No code changes — documentation only.

**Tech Stack:** Markdown files, manual review.

## Global Constraints
- All docs stay in Chinese (中文) unless a section is explicitly bilingual.
- `doc/images/` directory with screenshots must be preserved untouched.
- `.DS_Store` stays unchanged (gitignored).
- Git history of old task files is preserved — just delete the `.md` files.
- Content accuracy: every claim must match current codebase state (verify against `cutfinder/` structure).
- No "TBD", "TODO", or placeholder text in final output.

---

### Task 1: Rewrite `doc/proposal.md` (精简需求文档)

**Files:**
- Overwrite: `doc/proposal.md`

**Interfaces:**
- Consumes content from existing `proposal.md`, `detailed-design.md` (for tech stack details), `CLAUDE.md`.
- Produces: clean, concise requirements doc.

**Content structure (all in Chinese):**

1. **标题+概述**: 名称、灵感来源(Argus)、面向人群(Vlog创作者)、运行形态(本地Web App, localhost)
2. **核心设计原则**: 原文件只读、拍摄时间永不改变、全本地离线、幂等可重跑
3. **用户需求清单**: 需求0-8表格(标注v1包含/已实现/后续), v1范围边界
4. **技术栈**: 后端(Python+FastAPI)、数据库(SQLite)、前端(Vite+React+Tailwind+shardcn/ui)、视频处理(ffmpeg/ffprobe)、AI模型(OMLX, Qwen3.6-35B-A3B文本/Qwen3-VL-8B视觉/Silero VAD/Whisper/Demucs)
5. **处理流水线**: 扫描→去重→元数据+缩略图→VAD判定A/B→(A:转写+总结 / B:抽帧+视觉标签)→写入SQLite→复制到库目录
6. **分类与浏览**: 目录结构、标签来源(自动+手动)、筛选/搜索/详情功能
7. **配置项**: 全局配置(OMLX端点/密钥)、JSON偏好设置
8. **v1范围边界**: 包含(需求0-7+附加功能)、不包含/已实现项
9. **关键风险与对策**: 复制安全、时间保护、磁盘空间、AI准确性

**Self-test:**
- [ ] 所有需求编号(0-8)与现有代码一致
- [ ] 技术栈选型准确,模型名正确(Qwen3.6-35B-A3B / Qwen3-VL-8B-Instruct)
- [ ] 已实现功能标注正确(关键帧、字幕导出、初剪Agent等)
- [ ] 无增量更新记录堆积

**Commit:** `git add doc/proposal.md && git commit -m "docs(proposal): rewrite and simplify requirements document"`

---

### Task 2: Merge & Rewrite `doc/detailed-design.md` + UI Design (合并详细设计)

**Files:**
- Overwrite: `doc/detailed-design.md` (吸收原 ui-design.md 内容)
- Delete: `doc/ui-design.md`

**Interfaces:**
- Consumes content from existing detailed-design.md, ui-design.md, CLAUDE.md.
- Produces: one comprehensive design doc with merged UI section.

**Content structure:**

1. **设计目标与原则**: 模块隔离、外部依赖抽象(Protocol)、前后端分离
2. **总体架构**: 分层架构图(Frontend → API → Orchestrator/Queue → Domain Modules + Ports → Adapters)、建议代码结构
3. **后端模块详细设计** (§1-§15): 每个模块的职责/接口/输入输出依赖/独立测试方式
   - Config, MetadataProbe, ThumbnailMaker/FrameExtractor, SpeechDetector, Transcriber (含Qwen3-ASR+ForcedAligner), Summarizer, VisionTagger, LibraryWriter, CatalogRepository (含FTS5), Scanner, Orchestrator(含re-analyze), Worker+JobQueue, SubtitleExporter (§3.13), VocalSeparator (§3.14), CutDirector (§3.15)
   - **精简**: 去掉增量更新记录,保留核心设计决策和关键实现细节(如in/out时间码来源、护栏参数)
4. **外部依赖与Mock策略**: 表格(接口→真实适配器→单元测试替身→集成测试)
5. **数据模型**: SQLite schema (DDL + 表说明), 存储位置
6. **API设计**: REST+SSE路由表格(扫描/作业队列/片段CRUD+重分析/搜索/设置/字幕导出/初剪Agent)
7. **前端模块设计**: 各feature职责+独立测试方式(api/gallery/filters/search/detail/settings/jobs/subtitles/cutplan)
8. **测试策略**: 后端单元/集成、前端Vitest+RTL、Playwright E2E
9. **配置项与默认值**: 完整表格(所有pref键名+默认值+说明,含初剪参数)
10. **环境与部署**: 工具分工(mise/uv/Brewfile/npm)、Makefile目标、换机流程
11. **原生macOS .app外壳**: 为什么不用shell脚本、架构组件(7个Swift类)、进程与Dock生命周期、窗口三态、ServerController、首次安装流程(7步)、沙盒/签名/公证
12. **UI设计系统** (原 ui-design.md 合并而来):
    - 12.1 设计方向(近黑面板、一个主色+两个内容色、等宽数字)
    - 12.2 颜色Token (浅色默认 + 深色可切换,含完整表格:表面/文字/主色/A-B-roll语义状态)
    - 12.3 字体Token (Inter/PingFang SC + JetBrains Mono,字号阶梯)
    - 12.4 间距/圆角/阴影
    - 12.5 组件规范 (按钮、标签Chip、缩略图卡片、输入搜索、进度条)
    - 12.6 关键页面布局 (应用骨架+缩略图墙、片段详情右抽屉、设置页)
    - 12.7 可访问性/质量清单 (对比度、焦点可见、图标按钮aria-label等)
    - 12.8 CSS变量落地 (`:root` + `[data-theme="dark"]`)
    - 12.9 Tailwind/shadcn映射、字体引入
    - 12.10 原生macOS App外壳 (窗口三态、SetupView、ErrorView、应用菜单)
13. **关键决策汇总**: 隔离手段、测试边界、进度机制、幂等与纠正
14. **待办/需后续确认**: 精简为当前仍开放的问题

**Self-test:**
- [ ] UI设计内容完整保留(颜色token、字体、组件规范、页面布局、原生App外壳)
- [ ] 后端模块设计无遗漏(15个模块全部有描述+接口)
- [ ] API路由表格完整
- [ ] 配置项默认值表准确(含初剪参数)
- [ ] SQLite schema完整(6张表+FTS5)
- [ ] 无增量更新记录堆积

**Commit:** `git add doc/detailed-design.md doc/ui-design.md && git rm doc/ui-design.md && git commit -m "docs(detailed-design): merge ui-design into detailed design, remove incremental update history"`

---

### Task 3: Consolidate `doc/tasks/` into Single README.md

**Files:**
- Create: `doc/tasks/README.md` (new consolidated overview)
- Existing files consumed from all 32 task files in `doc/tasks/`

**Interfaces:**
- Consumes content from all 32 task files + progress.md.
- Produces: one consolidated tasks overview with completion status.

**Content structure:**

```markdown
# CutFinder 任务总览

> 所有开发任务一览。每个模块一个子项,勾选表示整模块完成(代码实现+自动测试通过)。
> 依据: proposal.md, detailed-design.md.

## 阶段0 · 基础
- [x] **01 项目脚手架** — 目录结构、domain模型、ports接口、uv/mise/Brewfile/测试框架
## 阶段1 · 适配器(外部依赖,互相独立)
- [x] **02 Config配置** — pydantic-settings读取全局配置+JSON偏好
- [x] **03 MetadataProbe元数据** — ffprobe解析拍摄时间/时长/分辨率
- [x] **04 Media缩略图/抽帧** — ffmpeg代表帧+均匀采样
- [x] **05 SpeechDetector人声检测** — Silero VAD speech_ratio判定A/B
- [x] **06 Transcriber语音转写** — mlx-whisper / Qwen3-ASR+ForcedAligner双引擎
- [x] **07 Summarizer文本总结** — OMLX Qwen3.6结构化输出{summary, tags}
- [x] **08 VisionTagger画面识别** — OMLX Qwen3-VL base64帧
- [x] **09 LibraryWriter库文件组织** — shutil.copy2保留时间,日期/类型目录
- [x] **10 CatalogRepository仓储** — SQLite CRUD+FTS5全文搜索
## 阶段2 · 核心逻辑
- [x] **11 Scanner扫描去重** — sha256指纹+扩展名过滤
- [x] **12 Orchestrator流水线编排** — A/B分支、错误隔离、幂等、re-analyze
- [x] **13 Worker队列+SSE** — asyncio.Queue+进度事件广播
## 阶段3 · 接口
- [x] **14 API层(FastAPI)** — REST+SSE路由,pydantic校验
## 阶段4 · 前端
- [x] **15 Frontend** — Vite+React+Tailwind, gallery/filters/search/detail/settings/jobs/cutplan/subtitles
## 阶段5 · 集成与部署
- [x] **16 环境/部署** — mise+uv+Brewfile, make setup/dev/test
## 阶段6 · 增强功能(已实现)
- [x] **17 关键帧推荐** — A-roll transcript / B-roll视觉,详情面板+画廊角标
- [x] **18 字幕导出** — 成片→mlx-whisper转写→iTT/SRT,强制人声分离
- [x] **19 转写前置人声分离** — Demucs htdemucs去BGM,可选开关
- [x] **20 字幕进度同步** — tqdm拦截分离+转写两阶段,真实进度条
- [x] **21 原生macOS .app** — Swift/AppKit包装器,WKWebView内嵌,首次安装自动装依赖
- [x] **22 关键帧设置开关** — keyframe_auto默认关,配置+UI
- [x] **23 库文件删除同步清理** — orphan检测+DB/缩略图/关键帧级联删除
- [x] **24 照片分析入库** — Pillow图像probe,photo roll类型,HEIC支持
- [x] **25 进度条恢复** — jobs API+resumePoll,刷新后断点续传
- [x] **26 初剪导演Agent** — 多轮对话生成分镜表,受约束工具调用环
- [x] **27 初剪按天mini-agent** — scoped工具循环+回落,去重护栏
- [x] **28 初剪实时进度** — 逐天/片段状态,已完成日期分镜先显示
- [x] **29 初剪refine按日合并+审片critic** — prior_plan合并,主观质量评审
- [x] **30 设置统一config.json** — 去掉env分组,全局键并入prefs视图
- [x] **31 初剪fallback复用勘察分析** — agent inspect_broll描述带入staged模式
```

Plus 里程碑 section (单元测试通过、后端API可用、真实推理链路验证) and TODO status.

**Self-test:**
- [ ] 所有32个任务编号(01-31 + progress里程碑)都有对应条目
- [ ] 完成状态与实际代码一致(20 native-app和17 subtitle导出标记为~或x)
- [ ] 没有遗漏任何子项

**Commit:** `git add doc/tasks/README.md && git commit -m "docs(tasks): consolidate 32 task files into single README overview"`

---

### Task 4: Delete Individual Task Files + test-checklist.md

**Files:**
- Delete (git rm): all 32 files in `doc/tasks/` except README.md
- Delete (git rm): `doc/test-checklist.md`

**Interfaces:**
- Consumes: none (standalone cleanup)
- Produces: clean doc/ structure

**Steps:**
1. `git rm doc/tasks/0[0-9].md` (remove 00-09)
2. `git rm doc/tasks/1[0-9].md` (remove 10-19)
3. `git rm doc/tasks/2[0-9].md` (remove 20-29)
4. `git rm doc/tasks/3[0].md` (remove 30)
5. `git rm doc/tasks/progress.md`
6. `git rm doc/test-checklist.md`

**Self-test:**
- [ ] `ls doc/tasks/` shows only README.md (plus images/)
- [ ] `git status` confirms all task files deleted

**Commit:** `git rm doc/tasks/0[0-9].md doc/tasks/1[0-9].md doc/tasks/2[0-9].md doc/tasks/30.md doc/tasks/progress.md doc/test-checklist.md && git commit -m "docs: remove individual task files and test checklist (consolidated)"`

---

### Task 5: Final Verification & Commit

**Steps:**
1. Verify no placeholders remain in any doc file (grep for TBD/TODO)
2. Verify all code-referenced paths exist in actual repo (e.g., `cutfinder/domain/models.py`, etc.)
3. Verify git status is clean (only doc changes)

**Commit:** `git add -A && git commit -m "docs: consolidate docs — simplify proposal, merge UI into detailed-design, flatten tasks"`

---

## Self-Review Checklist
1. **Spec coverage:** All 4 doc files addressed (proposal rewritten, detailed-design+ui merged, tasks flattened, test-checklist deleted)
2. **Placeholder scan:** No TBD/TODO in any task description — each has exact file paths, content structure, and self-test
3. **Type consistency:** Task numbering is sequential 1-5, no conflicts
