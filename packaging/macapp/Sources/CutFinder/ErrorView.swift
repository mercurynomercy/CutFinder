import Cocoa

/// Guidance / error view: title + message + a row of action buttons, plus a
/// disclosure for details/log. See ui-design §9.3.
final class ErrorView: NSView {
    /// A button action: a title and a handler invoked on click.
    struct Action {
        let title: String
        let isPrimary: Bool
        let handler: () -> Void

        init(title: String, isPrimary: Bool = false, handler: @escaping () -> Void) {
            self.title = title
            self.isPrimary = isPrimary
            self.handler = handler
        }
    }

    private let iconLabel = NSTextField(labelWithString: "⚠")
    private let titleLabel = NSTextField(labelWithString: "")
    private let messageLabel = NSTextField(wrappingLabelWithString: "")
    private let buttonStack = NSStackView()
    private let disclosure = NSButton()
    private let detailScroll = NSScrollView()
    private let detailTextView = NSTextView()

    private var actions: [Action] = []
    private var handlersByTag: [Int: () -> Void] = [:]

    init(title: String, message: String, actions: [Action], details: String? = nil) {
        super.init(frame: .zero)
        build()
        configure(title: title, message: message, actions: actions, details: details)
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        build()
    }

    private func build() {
        wantsLayer = true
        layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor

        iconLabel.font = .systemFont(ofSize: 36)
        iconLabel.textColor = .systemOrange

        titleLabel.font = .systemFont(ofSize: 18, weight: .semibold)
        messageLabel.font = .systemFont(ofSize: 13)
        messageLabel.textColor = .secondaryLabelColor
        messageLabel.preferredMaxLayoutWidth = 460

        buttonStack.orientation = .horizontal
        buttonStack.spacing = 12

        disclosure.title = "详情 / 日志"
        disclosure.setButtonType(.pushOnPushOff)
        disclosure.bezelStyle = .recessed
        disclosure.target = self
        disclosure.action = #selector(toggleDetails)
        disclosure.isHidden = true

        detailTextView.isEditable = false
        detailTextView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        detailTextView.textColor = .secondaryLabelColor
        detailScroll.documentView = detailTextView
        detailScroll.hasVerticalScroller = true
        detailScroll.borderType = .bezelBorder
        detailScroll.isHidden = true
        detailScroll.translatesAutoresizingMaskIntoConstraints = false
        detailScroll.heightAnchor.constraint(equalToConstant: 140).isActive = true

        let outer = NSStackView(views: [
            iconLabel, titleLabel, messageLabel, buttonStack, disclosure, detailScroll,
        ])
        outer.orientation = .vertical
        outer.alignment = .leading
        outer.spacing = 16
        outer.translatesAutoresizingMaskIntoConstraints = false
        outer.setCustomSpacing(8, after: iconLabel)
        outer.setCustomSpacing(8, after: titleLabel)
        outer.setCustomSpacing(24, after: messageLabel)

        addSubview(outer)
        NSLayoutConstraint.activate([
            outer.centerYAnchor.constraint(equalTo: centerYAnchor),
            outer.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 48),
            outer.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -48),
            detailScroll.widthAnchor.constraint(equalTo: outer.widthAnchor),
        ])
    }

    private func configure(title: String, message: String, actions: [Action], details: String?) {
        titleLabel.stringValue = title
        messageLabel.stringValue = message
        self.actions = actions

        buttonStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        handlersByTag.removeAll()
        for (index, action) in actions.enumerated() {
            let button = NSButton(title: action.title, target: self, action: #selector(buttonTapped(_:)))
            button.bezelStyle = .rounded
            button.tag = index
            if action.isPrimary {
                button.keyEquivalent = "\r"
            }
            handlersByTag[index] = action.handler
            buttonStack.addArrangedSubview(button)
        }

        if let details, !details.isEmpty {
            detailTextView.string = details
            disclosure.isHidden = false
        } else {
            disclosure.isHidden = true
        }
    }

    @objc private func buttonTapped(_ sender: NSButton) {
        handlersByTag[sender.tag]?()
    }

    @objc private func toggleDetails() {
        detailScroll.isHidden = (disclosure.state != .on)
    }

    /// Append a line to the detail log (and reveal the disclosure).
    func append(detail line: String) {
        detailTextView.string += line + "\n"
        disclosure.isHidden = false
    }
}
