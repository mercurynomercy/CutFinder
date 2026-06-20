# 20 原生 macOS .app 外壳（Swift 包装器）

> 依据：[`detailed-design.md`](../detailed-design.md) §11、[`ui-design.md`](../ui-design.md) §9、[`detailed-design.md`](../detailed-design.md) §10（部署/依赖）。
> 现状问题：`Contents/MacOS/CutFinder` 是 bash 脚本（`packaging/launcher.sh`），靠「脚本留前台 + 后台跑 uvicorn + 转发 SIGTERM」勉强维持 Dock 生命周期；`exec` 进 venv 的 Python 会让系统以为 App 退出、移除 Dock tile。没有标准应用菜单，点 Dock 图标不重开 UI，也不利于代码签名/公证。

## 目标

用**最小 Swift/AppKit 包装器**取代 shell 启动器，得到：标准应用菜单、稳定 Dock 生命周期、点 Dock 图标重开 UI、代码签名/公证能力；并把「开启/关闭服务」与「首次自动安装所有依赖」做成原生体验。**后端/前端零改动**——Swift 只做进程管理 + 首次安装 + 窗口宿主。

### 已确认决策（来自用户）

| 维度 | 决策 |
|---|---|
| UI 呈现 | **WKWebView 内嵌**现有 web 前端（无浏览器、无标签页） |
| 服务启动 | **启动即自动开启**（首次安装→自动 start→展示 UI）；菜单可停止/重启 |
| 首次安装 | **自动装本地依赖**：uv / ffmpeg / Python env / whisper+demucs 模型 |
| OMLX | **仅探测 + 引导**（独立菜单栏 App，无法静默安装；缺失不阻断、弹下载引导） |
| 构建 | **swiftc** 直接编译（`-framework Cocoa -framework WebKit`），无 `.xcodeproj` |
| 分发 | Developer ID 直分发（DMG）+ 公证；**非** Mac App Store（不开 App Sandbox） |

### 硬约束

- **bundle 内永不写入**：payload 同步到 `~/Library/Application Support/CutFinder/app`，venv/模型/catalog 都建在 bundle 之外 → 利于签名、更新干净。
- **绝不 `exec` 进子进程**：Swift 二进制始终是 `CFBundleExecutable` 与前台 owner，uvicorn 是其子进程 → Dock tile 稳定。
- **退出无孤儿**：⌘Q / 退出前先优雅停服务（SIGTERM→超时 SIGKILL）。
- 源素材只读等后端既有约束不受影响。

---

## 设计要点

- **组件**（`packaging/macapp/`，swiftc 编译为 `Contents/MacOS/CutFinder`）：
  - `main.swift`：`NSApplication` 引导。
  - `AppDelegate`：生命周期、菜单、Dock reopen、退出停服务。
  - `MainWindowController`：单窗口宿主 `WKWebView`，在「安装中 / 运行中 / 错误」三态切换 contentView。
  - `ServerController`：`Process` 拉起/停止/重启 uvicorn；`GET /api/library` 健康探测；端口（默认 5080，`CUTFINDER_PORT` 覆盖）；状态 enum 驱动菜单启用态。
  - `Provisioner`：首次安装步骤编排，逐步回调进度。
  - `DependencyChecker`：探测 uv / ffmpeg / OMLX。
  - `PayloadManager`：`rsync` bundle `Resources/payload` → Application Support，保留 venv/catalog。
  - `SetupView` / `ErrorView`：原生安装进度 / 错误引导视图，配色复用设计 token。
- **Dock 生命周期**：`applicationShouldHandleReopen` 无窗口时重开主窗口；关窗不退（服务后台续跑）；`applicationShouldTerminate` 先停服务。单实例：端口已健康则只重开窗口。
- **窗口三态**：安装中=`SetupView`；运行中=`WKWebView` 加载 `http://127.0.0.1:PORT/`（后端静态托管前端，`CUTFINDER_STATIC_DIR`）；错误=`ErrorView`。外部链接走 `NSWorkspace`（系统浏览器）。
- **首次安装序**：payload 同步 → uv（缺则 astral 安装脚本）→ ffmpeg（缺则 `brew install ffmpeg`，无 brew 转引导）→ `uv sync --frozen`（回落 `uv sync`）→ 模型（复用 `download_whisper.py`/`download_demucs.py`，已存在跳过）→ OMLX 探测（复用 `check_omlx.py`，缺失弹引导不阻断）→ 写版本戳完成标记。幂等可重跑。
- **签名/公证**：不开 App Sandbox；Hardened Runtime + entitlements `allow-jit` / `allow-unsigned-executable-memory` / `disable-library-validation`（运行用户侧 venv 的 Python/MLX/torch）。venv/模型在 bundle 外 → 只需签 Swift Mach-O（无需 `--deep`）。

---

## 任务清单

> **实现状态（自动化完成边界）**：构建/测试改用 **SwiftPM**（`packaging/macapp/Package.swift`，`swift test`），非原文档设想的 raw `swiftc`。
> `[x]` = 已实现且通过本机自动校验（`swift build`/`swift build -c release` 零错误、`swift test` 30 项全绿、`bash -n`、`plutil -lint`）。
> GUI/Dock/首次安装/uvicorn 启动等**运行期行为**无法在无人环境自动执行——相关组件**已实现且编译通过，运行待手动验收**（见下方「手动验收清单」与「完成标准」）。

### Swift 包装器（`packaging/macapp/`，SwiftPM：`CutFinderCore` 库 + `CutFinder` 可执行）

- [x] `main.swift` + `AppDelegate`：`NSApplication` 引导、标准应用菜单 + 「服务」菜单、Dock reopen、退出停服务。（编译通过；Dock/菜单运行待手动验）
- [x] `MainWindowController`：单窗口 + `WKWebView` 宿主，三态视图切换；记忆窗口尺寸/位置；标题栏服务状态点（色+文字）。（编译通过；GUI 运行待手动验）
- [x] `ServerController`：`Process` 启动/停止/重启 uvicorn；健康轮询 `GET /api/library`；状态 enum；端口管理 + 单实例探测。（编译通过；进程行为运行待手动验）
- [x] `PayloadManager`：payload → Application Support 同步（排除 `.venv`/`__pycache__`，保留 venv/catalog/用户状态）。（编译通过；rsync 运行待手动验）
- [x] `DependencyChecker`：uv / ffmpeg / OMLX 探测（OMLX 探测纯逻辑在 `CutFinderCore.OMLXProbe`，已单测）。
- [x] `Provisioner`：首次安装步骤编排（uv / ffmpeg / `uv sync` / 模型 / OMLX 探测），逐步进度回调 + 版本戳完成标记；步骤判定 `ProvisionPlanner` 在 `CutFinderCore`（已单测）。（编排编译通过；真实安装运行待手动验）
- [x] `SetupView`：步骤清单 + 进度条 + 可折叠日志（图标+文字）。（编译通过；GUI 运行待手动验）
- [x] `ErrorView`：OMLX/ffmpeg/`uv sync`/端口占用等引导（主/次操作分离，外链走系统浏览器）。（编译通过；GUI 运行待手动验）
- [x] `CutFinder.entitlements`：Hardened Runtime entitlements（`allow-jit` / `allow-unsigned-executable-memory` / `disable-library-validation`，`plutil -lint` 通过）。
- [x] `CutFinderCore`（纯逻辑库）：`ProvisionPlanner` / `OMLXProbe` / `PayloadPaths` / `ServerState`，Foundation-only，**30 项 XCTest 全绿**。

### 打包 / 构建

- [x] `scripts/build-app.sh` 升级：构建前端 → 组 payload（含把 `scripts/download_{whisper,demucs}.py` 拷到 `payload/packaging/`）→ **`swift build -c release`** 产物拷为 `Contents/MacOS/CutFinder` → 生成 `.icns` → 组 bundle → `codesign`（有 Developer ID 时，hardened runtime + entitlements，无 `--deep`）→ DMG →（`$CUTFINDER_NOTARY_PROFILE` 存在时）`notarytool` 公证 + `stapler`。`bash -n` 通过；全量出包/签名/公证需真身份手动跑。
- [x] `packaging/Info.plist.template`：保留 `LSUIElement=false`（常规 Dock App）、`CFBundleExecutable=CutFinder`、arm64、`LSMinimumSystemVersion 13.0`（沿用现状，无需改）。
- [x] 删除 `packaging/launcher.sh`（职责迁入 Swift）；`Makefile` `app` 目标已指向 `scripts/build-app.sh`（验证无误）。

### 测试

- [x] `Provisioner` 步骤判定：install/skip/guide 决策（`ProvisionPlanTests`，含 fresh/全装/缺 brew/缺 OMLX 分支）。
- [x] OMLX 探测：`OMLXProbeTests`（合法 JSON→ids、畸形/nil→unreachable、缺模型→missingModels）——以 `CutFinderCore.OMLXProbe` 纯函数实现并测，等价于原 §10 `check-omlx` 设想。
- [ ] 手动验收清单（**待手动验**）：启动即起服务并展示 UI；停止/重启；关窗不退、Dock 点击重开；⌘Q 不留孤儿；首次安装在「断网 / 缺 ffmpeg 且无 brew / 缺 OMLX / 端口被占」下的引导与回落。
- [x] 回归：后端/前端**零改动**（git 改动仅限 `packaging/macapp/` 与 `scripts/build-app.sh`、删 `packaging/launcher.sh`），既有单测不受影响。

---

## 完成标准

1. 双击 `.app`：首次自动装齐本地依赖（uv/ffmpeg/Python env/whisper+demucs 模型），随后自动起服务并在 **WKWebView 原生窗口**展示现有 UI；OMLX 缺失给引导但不阻断。
2. 标准应用菜单可用；「服务」菜单可**开启/停止/重启**，菜单项随状态启用/禁用。
3. Dock 生命周期稳定：关窗不退、点 Dock 重开窗口、⌘Q 先停服务无孤儿进程。
4. 可 `codesign` + 公证（有 Developer ID 时）；无身份时仍能本地出未签名 `.app`（开发用）。
5. bundle 内零写入；venv/模型/catalog 全在 Application Support；重跑安装幂等。
6. 后端/前端零改动；Provisioner/OMLX 探测单测全绿，手动验收清单通过。

### 当前状态（2026-06-20）

- **已自动达成**：全部 Swift 组件实现且 `swift build` / `swift build -c release` 零错误；`CutFinderCore` 纯逻辑 30 项 XCTest 全绿；`build-app.sh` 升级（`bash -n` 通过）+ entitlements（`plutil -lint` 通过）；`launcher.sh` 删除；后端/前端零改动（标准 6 关于「单测全绿/零改动」部分满足）。
- **待手动验收**（需真机运行，本无人环境不执行）：标准 1–3、5 的运行期行为（首次装齐依赖→自动起服务→WKWebView 展示 UI；菜单开关/重启；关窗不退 + Dock 重开 + ⌘Q 无孤儿；bundle 零写入 + App Support venv + 幂等）；标准 4 的真实 `codesign`+公证（需 Developer ID）。
- 产物：`packaging/macapp/.build/release/CutFinder` 为 `Mach-O 64-bit executable arm64`。
