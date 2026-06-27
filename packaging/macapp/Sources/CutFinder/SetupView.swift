import Cocoa
import CutFinderCore

/// First-run install view: a row per provision step (icon + name + sub-status),
/// an overall progress bar, and a disclosure log. See ui-design §9.2.
final class SetupView: NSView {
    private let titleLabel = NSTextField(labelWithString: "正在准备 CutFinder（首次启动）")
    private let subtitleLabel = NSTextField(labelWithString: "首次需要联网安装运行环境与模型，约几分钟")
    private let progress = NSProgressIndicator()
    private let logTextView = NSTextView()
    private let logScroll = NSScrollView()
    private let disclosure = NSButton()

    private var rows: [ProvisionStep: StepRow] = [:]

    /// Human-readable Chinese names for each step.
    private static let stepNames: [ProvisionStep: String] = [
        .payload: "应用文件",
        .uv: "uv（Python 工具链）",
        .ffmpeg: "ffmpeg",
        .pythonEnv: "Python 运行环境",
        .models: "音频分离模型（demucs）",
        .omlx: "OMLX 模型服务",
    ]

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        build()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        build()
    }

    private func build() {
        wantsLayer = true
        layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor

        titleLabel.font = .systemFont(ofSize: 20, weight: .semibold)
        subtitleLabel.font = .systemFont(ofSize: 12)
        subtitleLabel.textColor = .secondaryLabelColor

        progress.isIndeterminate = false
        progress.minValue = 0
        progress.maxValue = 1
        progress.doubleValue = 0

        // Step rows in canonical order.
        var rowViews: [NSView] = []
        for step in ProvisionStep.allCases {
            let row = StepRow(name: Self.stepNames[step] ?? step.rawValue)
            rows[step] = row
            rowViews.append(row)
        }
        let stepStack = NSStackView(views: rowViews)
        stepStack.orientation = .vertical
        stepStack.alignment = .leading
        stepStack.spacing = 10

        // Log disclosure + text view (collapsed by default).
        disclosure.title = "查看安装日志"
        disclosure.setButtonType(.pushOnPushOff)
        disclosure.bezelStyle = .recessed
        disclosure.target = self
        disclosure.action = #selector(toggleLog)

        logTextView.isEditable = false
        logTextView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        logTextView.textColor = .secondaryLabelColor
        logScroll.documentView = logTextView
        logScroll.hasVerticalScroller = true
        logScroll.borderType = .bezelBorder
        logScroll.isHidden = true
        logScroll.translatesAutoresizingMaskIntoConstraints = false
        logScroll.heightAnchor.constraint(equalToConstant: 160).isActive = true

        let outer = NSStackView(views: [
            titleLabel, subtitleLabel, stepStack, progress, disclosure, logScroll,
        ])
        outer.orientation = .vertical
        outer.alignment = .leading
        outer.spacing = 16
        outer.translatesAutoresizingMaskIntoConstraints = false
        outer.setCustomSpacing(4, after: titleLabel)
        outer.setCustomSpacing(28, after: subtitleLabel)

        addSubview(outer)
        NSLayoutConstraint.activate([
            outer.centerYAnchor.constraint(equalTo: centerYAnchor),
            outer.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 48),
            outer.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -48),
            progress.widthAnchor.constraint(equalTo: outer.widthAnchor),
            logScroll.widthAnchor.constraint(equalTo: outer.widthAnchor),
        ])
    }

    @objc private func toggleLog() {
        logScroll.isHidden = (disclosure.state != .on)
    }

    // MARK: - Public update API (call on main thread)

    func update(step: ProvisionStep, status: StepStatus) {
        rows[step]?.apply(status)
    }

    func update(progress fraction: Double) {
        progress.doubleValue = max(0, min(1, fraction))
    }

    func append(log line: String) {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        logTextView.string += trimmed + "\n"
        logTextView.scrollToEndOfDocument(nil)
    }
}

/// One step row: status glyph + name + sub-status text.
private final class StepRow: NSView {
    private let glyph = NSTextField(labelWithString: "·")
    private let nameLabel: NSTextField
    private let statusLabel = NSTextField(labelWithString: "等待")
    private let spinner = NSProgressIndicator()

    init(name: String) {
        nameLabel = NSTextField(labelWithString: name)
        super.init(frame: .zero)

        glyph.font = .systemFont(ofSize: 14, weight: .bold)
        glyph.textColor = .tertiaryLabelColor
        glyph.alignment = .center
        glyph.setContentHuggingPriority(.required, for: .horizontal)

        nameLabel.font = .systemFont(ofSize: 13)
        statusLabel.font = .systemFont(ofSize: 12)
        statusLabel.textColor = .secondaryLabelColor

        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false

        let stack = NSStackView(views: [glyph, spinner, nameLabel, statusLabel])
        stack.orientation = .horizontal
        stack.spacing = 8
        stack.alignment = .centerY
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: topAnchor),
            stack.bottomAnchor.constraint(equalTo: bottomAnchor),
            stack.leadingAnchor.constraint(equalTo: leadingAnchor),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor),
            glyph.widthAnchor.constraint(equalToConstant: 16),
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func apply(_ status: StepStatus) {
        spinner.stopAnimation(nil)
        switch status {
        case .waiting:
            glyph.stringValue = "·"; glyph.textColor = .tertiaryLabelColor
            statusLabel.stringValue = "等待"; statusLabel.textColor = .secondaryLabelColor
        case .running:
            glyph.stringValue = ""
            spinner.startAnimation(nil)
            statusLabel.stringValue = "进行中…"; statusLabel.textColor = .controlAccentColor
        case .done:
            glyph.stringValue = "✓"; glyph.textColor = .systemGreen
            statusLabel.stringValue = "已就绪"; statusLabel.textColor = .secondaryLabelColor
        case .skipped:
            glyph.stringValue = "✓"; glyph.textColor = .systemGreen
            statusLabel.stringValue = "已就绪"; statusLabel.textColor = .secondaryLabelColor
        case .guide(let reason):
            glyph.stringValue = "⚠"; glyph.textColor = .systemOrange
            statusLabel.stringValue = "需手动（\(reason)）"; statusLabel.textColor = .systemOrange
        case .failed(let detail):
            glyph.stringValue = "⚠"; glyph.textColor = .systemRed
            statusLabel.stringValue = "失败：\(detail)"; statusLabel.textColor = .systemRed
        }
    }
}
