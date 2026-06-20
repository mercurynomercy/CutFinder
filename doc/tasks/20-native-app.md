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

### Swift 包装器（`packaging/macapp/`）

- [ ] `main.swift` + `AppDelegate`：`NSApplication` 引导、标准应用菜单 + 「服务」菜单、Dock reopen、退出停服务。
- [ ] `MainWindowController`：单窗口 + `WKWebView` 宿主，三态视图切换；记忆窗口尺寸/位置；标题栏服务状态点（色+文字）。
- [ ] `ServerController`：`Process` 启动/停止/重启 uvicorn；健康轮询 `GET /api/library`；状态 enum；端口管理 + 单实例探测。
- [ ] `PayloadManager`：payload → Application Support 同步（排除 `.venv`/`__pycache__`，保留 venv/catalog/用户状态）。
- [ ] `DependencyChecker`：uv / ffmpeg / OMLX 探测（OMLX 复用 `check_omlx.py` 逻辑）。
- [ ] `Provisioner`：首次安装步骤编排（uv / ffmpeg / `uv sync` / 模型 / OMLX 探测），逐步进度回调 + 版本戳完成标记。
- [ ] `SetupView`：步骤清单 + 进度条 + 可折叠日志（图标+文字，沿用 token）。
- [ ] `ErrorView`：OMLX/ffmpeg/`uv sync`/端口占用等引导（主/次操作分离，外链走系统浏览器）。
- [ ] `CutFinder.entitlements`：Hardened Runtime entitlements。

### 打包 / 构建

- [ ] `scripts/build-app.sh` 升级：构建前端 → 组 payload → **swiftc 编译** Swift 源为 `Contents/MacOS/CutFinder` → 生成 `.icns` → 组 bundle → `codesign`（有身份时）→ DMG → `notarytool` 公证 + `stapler`（有身份时）。
- [ ] `packaging/Info.plist.template`：保留 `LSUIElement=false`（常规 Dock App）；按需补 `CFBundleExecutable`/版本占位（沿用现状）。
- [ ] 删除 `packaging/launcher.sh`（职责迁入 Swift）；`Makefile` `app` 目标指向新 build 流程。

### 测试

- [ ] `Provisioner` 步骤判定：哪步该装/该跳/该引导（纯逻辑，可对决策函数单测）。
- [ ] OMLX 探测：沿用 §10 `check-omlx` 纯函数单测（假 HTTP 响应）。
- [ ] 手动验收清单：启动即起服务并展示 UI；停止/重启；关窗不退、Dock 点击重开；⌘Q 不留孤儿；首次安装在「断网 / 缺 ffmpeg 且无 brew / 缺 OMLX / 端口被占」下的引导与回落。
- [ ] 回归：后端/前端既有单测不受影响。

---

## 完成标准

1. 双击 `.app`：首次自动装齐本地依赖（uv/ffmpeg/Python env/whisper+demucs 模型），随后自动起服务并在 **WKWebView 原生窗口**展示现有 UI；OMLX 缺失给引导但不阻断。
2. 标准应用菜单可用；「服务」菜单可**开启/停止/重启**，菜单项随状态启用/禁用。
3. Dock 生命周期稳定：关窗不退、点 Dock 重开窗口、⌘Q 先停服务无孤儿进程。
4. 可 `codesign` + 公证（有 Developer ID 时）；无身份时仍能本地出未签名 `.app`（开发用）。
5. bundle 内零写入；venv/模型/catalog 全在 Application Support；重跑安装幂等。
6. 后端/前端零改动；Provisioner/OMLX 探测单测全绿，手动验收清单通过。
