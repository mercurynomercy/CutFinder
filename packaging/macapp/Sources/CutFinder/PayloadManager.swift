import Foundation
import CutFinderCore

/// Syncs the bundled `Resources/payload` into the writable runtime directory,
/// preserving the user-side venv / catalog / caches.
enum PayloadManager {
    enum PayloadError: LocalizedError {
        case noBundlePayload
        case syncFailed(String)

        var errorDescription: String? {
            switch self {
            case .noBundlePayload:
                return "找不到打包的应用文件（payload）。开发模式下没有 .app bundle，请通过打包后的 App 运行。"
            case .syncFailed(let detail):
                return "同步应用文件失败：\(detail)"
            }
        }
    }

    /// Resolve the bundled payload directory, or nil if absent (e.g. dev mode).
    static func bundledPayloadDir() -> URL? {
        guard let resourceURL = Bundle.main.resourceURL else { return nil }
        let payload = resourceURL.appendingPathComponent("payload", isDirectory: true)
        return FileManager.default.fileExists(atPath: payload.path) ? payload : nil
    }

    /// rsync `<payload>/` → `runtimeDir`, excluding venv/caches so user state
    /// survives. Idempotent.
    static func sync(paths: PayloadPaths) throws {
        guard let payload = bundledPayloadDir() else {
            throw PayloadError.noBundlePayload
        }

        let fm = FileManager.default
        try fm.createDirectory(at: paths.supportDir, withIntermediateDirectories: true)
        try fm.createDirectory(at: paths.runtimeDir, withIntermediateDirectories: true)

        var args = ["-a", "--delete"]
        for exclude in PayloadPaths.rsyncExcludes {
            args.append("--exclude")
            args.append(exclude)
        }
        // Trailing slash on source copies contents, not the dir itself.
        args.append(payload.path + "/")
        args.append(paths.runtimeDir.path)

        let result = Shell.run(URL(fileURLWithPath: "/usr/bin/rsync"), arguments: args)
        if !result.succeeded {
            throw PayloadError.syncFailed(result.stderr.isEmpty ? result.stdout : result.stderr)
        }
    }
}
