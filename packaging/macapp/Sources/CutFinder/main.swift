import Cocoa

// Explicit NSApplication bootstrap. A file named main.swift hosts top-level code,
// so we don't use @main here.
let app = NSApplication.shared
app.setActivationPolicy(.regular)

let delegate = AppDelegate()
app.delegate = delegate

app.run()
