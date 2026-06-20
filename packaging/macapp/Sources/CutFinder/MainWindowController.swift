import Cocoa
import WebKit
import CutFinderCore

/// Single resizable window hosting the three-state content (installing / running
/// / error). Running state embeds a WKWebView pinned to 127.0.0.1.
final class MainWindowController: NSWindowController, WKNavigationDelegate {
    private let container = NSView()
    private var currentContent: NSView?
    private var webView: WKWebView?

    private let statusDot = NSTextField(labelWithString: "●")
    private let statusText = NSTextField(labelWithString: "启动中")

    private let setupView = SetupView(frame: .zero)

    /// Expose the setup view so the AppDelegate can stream provision progress.
    var setup: SetupView { setupView }

    init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1100, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "CutFinder"
        window.minSize = NSSize(width: 900, height: 600)
        window.setFrameAutosaveName("CutFinderMain")
        super.init(window: window)

        container.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = container

        setupTitlebarAccessory()
        window.center()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func setupTitlebarAccessory() {
        statusDot.font = .systemFont(ofSize: 11)
        statusText.font = .systemFont(ofSize: 11)
        statusText.textColor = .secondaryLabelColor

        let stack = NSStackView(views: [statusDot, statusText])
        stack.orientation = .horizontal
        stack.spacing = 4
        stack.edgeInsets = NSEdgeInsets(top: 0, left: 8, bottom: 0, right: 8)

        let accessory = NSTitlebarAccessoryViewController()
        accessory.view = stack
        accessory.layoutAttribute = .right
        window?.addTitlebarAccessoryViewController(accessory)
    }

    // MARK: - State / status dot

    func updateStatus(_ state: ServerState) {
        switch state {
        case .idle:
            statusDot.textColor = .tertiaryLabelColor; statusText.stringValue = "空闲"
        case .installing:
            statusDot.textColor = .systemOrange; statusText.stringValue = "安装中"
        case .starting:
            statusDot.textColor = .controlAccentColor; statusText.stringValue = "启动中"
        case .running:
            statusDot.textColor = .systemGreen; statusText.stringValue = "运行中"
        case .stopped:
            statusDot.textColor = .tertiaryLabelColor; statusText.stringValue = "已停止"
        case .error:
            statusDot.textColor = .systemRed; statusText.stringValue = "错误"
        }
    }

    // MARK: - Three-state content swapping

    private func setContent(_ view: NSView) {
        currentContent?.removeFromSuperview()
        view.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(view)
        NSLayoutConstraint.activate([
            view.topAnchor.constraint(equalTo: container.topAnchor),
            view.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            view.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: container.trailingAnchor),
        ])
        currentContent = view
    }

    func showInstalling() {
        updateStatus(.installing)
        setContent(setupView)
    }

    func showRunning(url: URL) {
        updateStatus(.running)
        let web: WKWebView
        if let existing = webView {
            web = existing
        } else {
            let config = WKWebViewConfiguration()
            web = WKWebView(frame: .zero, configuration: config)
            web.navigationDelegate = self
            webView = web
        }
        setContent(web)
        web.load(URLRequest(url: url))
    }

    func showError(title: String, message: String, actions: [ErrorView.Action], details: String? = nil) {
        updateStatus(.error(title))
        let view = ErrorView(title: title, message: message, actions: actions, details: details)
        setContent(view)
    }

    func reload() {
        webView?.reload()
    }

    // MARK: - WKNavigationDelegate

    /// Keep navigation on 127.0.0.1; route external http(s) links to the system browser.
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }
        let scheme = url.scheme?.lowercased()
        let host = url.host
        if scheme == "http" || scheme == "https" {
            if host == "127.0.0.1" || host == "localhost" {
                decisionHandler(.allow)
            } else {
                NSWorkspace.shared.open(url)
                decisionHandler(.cancel)
            }
            return
        }
        // Non-web schemes (mailto:, etc.) → system handler.
        NSWorkspace.shared.open(url)
        decisionHandler(.cancel)
    }
}
