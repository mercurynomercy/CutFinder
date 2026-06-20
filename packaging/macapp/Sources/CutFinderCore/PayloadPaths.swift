import Foundation

/// Pure path computation for the app's out-of-bundle runtime location.
///
/// Per the hard constraint, nothing is ever written inside the .app bundle:
/// the payload is synced to `~/Library/Application Support/CutFinder`, and the
/// venv / models / catalog all live outside the bundle.
///
/// `home` is injectable so paths can be unit-tested against a temp directory.
public struct PayloadPaths {
    public let home: URL

    public init(home: URL) {
        self.home = home
    }

    /// `<home>/Library/Application Support/CutFinder`
    public var supportDir: URL {
        home
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Application Support", isDirectory: true)
            .appendingPathComponent("CutFinder", isDirectory: true)
    }

    /// `<supportDir>/app`
    public var runtimeDir: URL {
        supportDir.appendingPathComponent("app", isDirectory: true)
    }

    /// `<runtimeDir>/backend`
    public var backendDir: URL {
        runtimeDir.appendingPathComponent("backend", isDirectory: true)
    }

    /// `<backendDir>/.venv/bin/python`
    public var venvPython: URL {
        backendDir
            .appendingPathComponent(".venv", isDirectory: true)
            .appendingPathComponent("bin", isDirectory: true)
            .appendingPathComponent("python", isDirectory: false)
    }

    /// `<runtimeDir>/frontend/dist`
    public var frontendDist: URL {
        runtimeDir
            .appendingPathComponent("frontend", isDirectory: true)
            .appendingPathComponent("dist", isDirectory: true)
    }

    /// `<supportDir>/launch.log`
    public var logFile: URL {
        supportDir.appendingPathComponent("launch.log", isDirectory: false)
    }

    /// `<supportDir>/.setup-complete`
    public var setupMarker: URL {
        supportDir.appendingPathComponent(".setup-complete", isDirectory: false)
    }

    /// Paths excluded when rsyncing the bundle payload into the support dir,
    /// so the user-side venv and caches are preserved.
    public static let rsyncExcludes: [String] = ["backend/.venv", "__pycache__"]

    /// Convenience instance rooted at the current user's home directory.
    public static func userDefault() -> PayloadPaths {
        PayloadPaths(home: FileManager.default.homeDirectoryForCurrentUser)
    }
}
