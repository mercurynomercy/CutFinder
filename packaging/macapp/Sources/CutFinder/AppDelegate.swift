import Cocoa
import CutFinderCore

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuItemValidation {
    private let paths = PayloadPaths.userDefault()
    private let server = ServerController()
    private var windowController: MainWindowController!

    private var serverState: ServerState = .idle

    // Service menu items kept for enable/disable validation.
    private var startItem: NSMenuItem?
    private var stopItem: NSMenuItem?
    private var restartItem: NSMenuItem?

    // MARK: - Launch

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenus()

        windowController = MainWindowController()
        windowController.showWindow(self)
        windowController.showInstalling()

        server.onState = { [weak self] state in
            // Always on main queue (ServerController dispatches there).
            self?.serverState = state
            self?.windowController.updateStatus(state)
        }

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.runFirstRun()
        }
    }

    /// Background: provision (if needed) → start server → show UI.
    private func runFirstRun() {
        DispatchQueue.main.async { self.serverState = .installing }

        let provisioner = Provisioner(paths: paths)
        do {
            try provisioner.run(
                onProgress: { fraction in
                    DispatchQueue.main.async { self.windowController.setup.update(progress: fraction) }
                },
                onStep: { step, status in
                    DispatchQueue.main.async { self.windowController.setup.update(step: step, status: status) }
                },
                onLog: { line in
                    DispatchQueue.main.async { self.windowController.setup.append(log: line) }
                }
            )
        } catch {
            let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            DispatchQueue.main.async {
                self.windowController.showError(
                    title: "安装未完成",
                    message: "首次安装过程中出现错误，无法继续启动服务。可重试或查看日志。",
                    actions: [
                        ErrorView.Action(title: "重试", isPrimary: true) { [weak self] in self?.rerunSetup() },
                        ErrorView.Action(title: "打开日志") { [weak self] in self?.openLog() },
                    ],
                    details: detail
                )
            }
            return
        }

        // Provisioning OK → start the server, then route based on OMLX status.
        startServerThenShowUI()
    }

    private func startServerThenShowUI() {
        server.start(paths: paths)

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let healthy = self.server.pollHealth(timeout: 60)
            DispatchQueue.main.async {
                guard healthy else {
                    self.windowController.showError(
                        title: "服务启动失败",
                        message: "本地服务在超时时间内未就绪，请查看日志后重试。",
                        actions: [
                            ErrorView.Action(title: "重启服务", isPrimary: true) { [weak self] in self?.server.restart(paths: self!.paths) },
                            ErrorView.Action(title: "打开日志") { [weak self] in self?.openLog() },
                        ]
                    )
                    return
                }
                self.routeAfterHealthy()
            }
        }
    }

    /// After the server is healthy, surface the OMLX guidance if needed, then UI.
    private func routeAfterHealthy() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self else { return }
            let status = DependencyChecker.omlxStatus()
            DispatchQueue.main.async {
                if status == .ready {
                    self.proceedToRunning()
                } else {
                    self.showOMLXGuidance(status)
                }
            }
        }
    }

    private func proceedToRunning() {
        windowController.showRunning(url: AppConfig.localURL(port: server.port))
    }

    private func showOMLXGuidance(_ status: OMLXStatus) {
        let detail: String
        switch status {
        case .unreachable: detail = "无法连接 OMLX（\(AppConfig.omlxBaseURL)）。"
        case .missingModels(let models): detail = "缺少模型：\(models.joined(separator: ", "))。"
        case .ready: detail = ""
        }
        windowController.showError(
            title: "未检测到 OMLX 模型服务",
            message: "CutFinder 的「A-roll 简介 / B-roll 画面打标」需要本机的 OMLX（独立 App，负责文本/视觉模型）。扫描、转写、缩略图不受影响，可先继续使用。",
            actions: [
                ErrorView.Action(title: "打开 OMLX 下载页", isPrimary: true) {
                    NSWorkspace.shared.open(AppConfig.omlxDownloadURL)
                },
                ErrorView.Action(title: "重试探测") { [weak self] in self?.routeAfterHealthy() },
                ErrorView.Action(title: "仍然继续") { [weak self] in self?.proceedToRunning() },
            ],
            details: detail
        )
    }

    // MARK: - Dock lifecycle

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            windowController.showWindow(self)
            windowController.window?.makeKeyAndOrderFront(self)
        }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        server.stop {
            DispatchQueue.main.async {
                NSApp.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }

    // MARK: - Menus

    private func buildMenus() {
        let mainMenu = NSMenu()

        // App menu
        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appItem.submenu = appMenu
        let appName = "CutFinder"
        appMenu.addItem(withTitle: "关于 \(appName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = appMenu.addItem(withTitle: "隐藏其他", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Edit menu (standard, for text fields/web view)
        let editItem = NSMenuItem()
        mainMenu.addItem(editItem)
        let editMenu = NSMenu(title: "编辑")
        editItem.submenu = editMenu
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        // View menu
        let viewItem = NSMenuItem()
        mainMenu.addItem(viewItem)
        let viewMenu = NSMenu(title: "显示")
        viewItem.submenu = viewMenu
        viewMenu.addItem(withTitle: "重新加载", action: #selector(reloadUI), keyEquivalent: "r").target = self
        viewMenu.addItem(.separator())
        viewMenu.addItem(withTitle: "进入全屏", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f").keyEquivalentModifierMask = [.command, .control]

        // Service menu
        let serviceItem = NSMenuItem()
        mainMenu.addItem(serviceItem)
        let serviceMenu = NSMenu(title: "服务")
        serviceItem.submenu = serviceMenu
        startItem = serviceMenu.addItem(withTitle: "开启服务", action: #selector(startService), keyEquivalent: "")
        startItem?.target = self
        stopItem = serviceMenu.addItem(withTitle: "停止服务", action: #selector(stopService), keyEquivalent: "")
        stopItem?.target = self
        restartItem = serviceMenu.addItem(withTitle: "重启服务", action: #selector(restartService), keyEquivalent: "")
        restartItem?.target = self
        serviceMenu.addItem(.separator())
        serviceMenu.addItem(withTitle: "在浏览器中打开", action: #selector(openInBrowser), keyEquivalent: "").target = self
        serviceMenu.addItem(withTitle: "打开素材库文件夹", action: #selector(openLibraryFolder), keyEquivalent: "").target = self
        serviceMenu.addItem(withTitle: "打开日志", action: #selector(openLog), keyEquivalent: "").target = self
        serviceMenu.addItem(withTitle: "重新运行安装", action: #selector(rerunSetup), keyEquivalent: "").target = self

        // Window menu
        let windowItem = NSMenuItem()
        mainMenu.addItem(windowItem)
        let windowMenu = NSMenu(title: "窗口")
        windowItem.submenu = windowMenu
        windowMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "缩放", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        NSApp.windowsMenu = windowMenu

        // Help menu
        let helpItem = NSMenuItem()
        mainMenu.addItem(helpItem)
        let helpMenu = NSMenu(title: "帮助")
        helpItem.submenu = helpMenu
        helpMenu.addItem(withTitle: "CutFinder 文档", action: #selector(openDocs), keyEquivalent: "").target = self
        helpMenu.addItem(withTitle: "检查 OMLX 状态", action: #selector(checkOMLX), keyEquivalent: "").target = self

        NSApp.mainMenu = mainMenu
    }

    // MARK: - Menu validation

    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        switch menuItem {
        case startItem:
            // Enabled when not currently running/starting.
            switch serverState {
            case .running, .starting: return false
            default: return true
            }
        case stopItem, restartItem:
            switch serverState {
            case .running: return true
            default: return false
            }
        default:
            return true
        }
    }

    // MARK: - Actions

    @objc private func startService() { server.start(paths: paths) }
    @objc private func stopService() { server.stop() }
    @objc private func restartService() {
        server.restart(paths: paths)
        // Reload the web view once it comes back.
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self, self.server.pollHealth(timeout: 60) else { return }
            DispatchQueue.main.async { self.windowController.reload() }
        }
    }

    @objc private func reloadUI() { windowController.reload() }

    @objc private func openInBrowser() {
        NSWorkspace.shared.open(AppConfig.localURL(port: server.port))
    }

    @objc private func openLibraryFolder() {
        NSWorkspace.shared.open(paths.supportDir)
    }

    @objc private func openLog() {
        NSWorkspace.shared.open(paths.logFile)
    }

    @objc private func rerunSetup() {
        windowController.showInstalling()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.runFirstRun()
        }
    }

    @objc private func openDocs() {
        NSWorkspace.shared.open(AppConfig.docsURL)
    }

    @objc private func checkOMLX() {
        DispatchQueue.global(qos: .utility).async {
            let status = DependencyChecker.omlxStatus()
            DispatchQueue.main.async {
                let alert = NSAlert()
                alert.messageText = "OMLX 状态"
                switch status {
                case .ready:
                    alert.informativeText = "OMLX 就绪，所需模型均在列。"
                case .missingModels(let models):
                    alert.informativeText = "OMLX 可达，但缺少模型：\(models.joined(separator: ", "))。"
                case .unreachable:
                    alert.informativeText = "无法连接 OMLX（\(AppConfig.omlxBaseURL)）。请确认 OMLX 已启动。"
                }
                alert.runModal()
            }
        }
    }
}
