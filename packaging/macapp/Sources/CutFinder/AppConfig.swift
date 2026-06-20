import Foundation

/// App-wide constants shared by the controllers and views.
enum AppConfig {
    /// Default local server port; overridable via `CUTFINDER_PORT`.
    static var port: Int {
        if let raw = ProcessInfo.processInfo.environment["CUTFINDER_PORT"],
           let value = Int(raw), value > 0 {
            return value
        }
        return 5080
    }

    // MARK: - Global config (settings UI)

    private static let _globalKeys = ["OMLX_BASE_URL", "OMLX_API_KEY", "TEXT_MODEL", "VISION_MODEL"]

    /// Read `~/.cutfinder/config.json` and return non-empty values for known keys.
    private static func _readGlobalConfig() -> [String: String] {
        let path = NSHomeDirectory().appending("/.cutfinder/config.json")
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let dict = (try? JSONSerialization.jsonObject(with: data, options: []) as? [String: Any]) else {
            return [:]
        }
        var result = [String: String]()
        for key in _globalKeys {
            if let value = dict[key] as? String, !value.isEmpty {
                result[key] = value
            }
        }
        return result
    }

    /// Base URL of the OMLX OpenAI-compatible server.
    /// Precedence: env var > `~/.cutfinder/config.json` (settings UI) > default.
    static var omlxBaseURL: String {
        if let raw = ProcessInfo.processInfo.environment["OMLX_BASE_URL"], !raw.isEmpty {
            return raw
        }
        let cfg = _readGlobalConfig()
        return cfg["OMLX_BASE_URL"] ?? "http://localhost:8000/v1"
    }

    /// API key for OMLX authentication. Returns nil when no key is available.
    static var omlxApiKey: String? {
        if let raw = ProcessInfo.processInfo.environment["OMLX_API_KEY"], !raw.isEmpty {
            return raw
        }
        let cfg = _readGlobalConfig()
        return cfg["OMLX_API_KEY"]
    }

    /// Read a single value from `~/.cutfinder/config.json`, or return the default.
    private static func readGlobalConfigValue(for key: String, defaultValue: String) -> String {
        let cfg = _readGlobalConfig()
        return cfg[key] ?? defaultValue
    }

    /// Authorization header value for OMLX requests, or nil if no key configured.
    static var omlxAuthHeader: String? {
        guard let key = omlxApiKey, !key.isEmpty else { return nil }
        return "Bearer \(key)"
    }

    /// Models OMLX must expose for A-roll text + B-roll vision.
    /// Reads from config (settings UI) with fallback to hardcoded defaults.
    static var requiredOMLXModels: [String] {
        let text = readGlobalConfigValue(for: "TEXT_MODEL", defaultValue: "Qwen3.6-35B-A3B")
        let vision = readGlobalConfigValue(for: "VISION_MODEL", defaultValue: "Qwen3-VL-8B-Instruct")
        return [text, vision]
    }

    /// Public download/info page for OMLX, opened from the guidance view.
    static let omlxDownloadURL = URL(string: "https://github.com/jundot/omlx")!

    /// Homebrew install info page.
    static let homebrewURL = URL(string: "https://brew.sh")!

    /// CutFinder documentation page (placeholder; repo README).
    static let docsURL = URL(string: "https://github.com/discoposse/argus")!

    /// Version string written into the setup-complete marker.
    static let setupVersion = "1"

    /// Local UI URL for the running server.
    static func localURL(port: Int = AppConfig.port) -> URL {
        URL(string: "http://127.0.0.1:\(port)/")!
    }
}
