import Foundation
import CutFinderCore

/// Manages the uvicorn backend as a child `Process`: start / stop / restart,
/// health polling, single-instance detection. Never `exec`s — the Swift binary
/// stays the foreground owner.
final class ServerController {
    /// Called on the main queue whenever the server state changes.
    var onState: ((ServerState) -> Void)?

    private(set) var state: ServerState = .idle {
        didSet {
            let s = state
            DispatchQueue.main.async { [weak self] in self?.onState?(s) }
        }
    }

    private var process: Process?
    private let queue = DispatchQueue(label: "cutfinder.server")
    private var logHandle: FileHandle?

    let port: Int

    init(port: Int = AppConfig.port) {
        self.port = port
    }

    // MARK: - Lifecycle

    /// Start the server (idempotent). If something already answers the health
    /// endpoint, attach to it instead of launching a second instance.
    func start(paths: PayloadPaths) {
        queue.async { [weak self] in
            guard let self else { return }
            if case .running = self.state, self.process?.isRunning == true { return }

            // Single-instance: an existing healthy server means just use it.
            if self.isHealthy() {
                self.state = .running
                return
            }

            self.state = .starting
            do {
                try self.launch(paths: paths)
            } catch {
                self.state = .error("无法启动服务：\(error.localizedDescription)")
                return
            }

            if self.pollHealth(timeout: 60) {
                self.state = .running
            } else {
                self.state = .error("服务启动超时，请查看日志：\(paths.logFile.path)")
            }
        }
    }

    /// Stop the server gracefully (SIGTERM → timeout → SIGKILL).
    /// - completion: called on the caller's queue context after stop completes.
    func stop(completion: (() -> Void)? = nil) {
        queue.async { [weak self] in
            guard let self else { completion?(); return }
            defer { completion?() }

            guard let process = self.process, process.isRunning else {
                self.process = nil
                self.closeLog()
                self.state = .stopped
                return
            }

            let pid = process.processIdentifier
            process.terminate() // SIGTERM

            let deadline = Date().addingTimeInterval(6)
            while process.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.1)
            }
            if process.isRunning {
                kill(pid, SIGKILL)
                process.waitUntilExit()
            }

            self.process = nil
            self.closeLog()
            self.state = .stopped
        }
    }

    /// Restart: stop then start.
    func restart(paths: PayloadPaths) {
        stop { [weak self] in
            self?.start(paths: paths)
        }
    }

    // MARK: - Launch

    private func launch(paths: PayloadPaths) throws {
        let process = Process()
        let uvicornArgs = [
            "-m", "uvicorn", "cutfinder.api.app:app",
            "--host", "127.0.0.1",
            "--port", String(port),
            "--timeout-graceful-shutdown", "5",
        ]

        let fm = FileManager.default
        if fm.isExecutableFile(atPath: paths.venvPython.path) {
            process.executableURL = paths.venvPython
            process.arguments = uvicornArgs
        } else {
            // Fallback: `uv run` via /bin/sh so PATH resolution applies.
            process.executableURL = URL(fileURLWithPath: "/bin/sh")
            let joined = uvicornArgs.map { "'\($0)'" }.joined(separator: " ")
            process.arguments = ["-c", "exec uv run python \(joined)"]
        }

        process.currentDirectoryURL = paths.backendDir
        process.environment = Shell.augmentedEnvironment(extra: [
            "CUTFINDER_STATIC_DIR": paths.frontendDist.path,
            "CUTFINDER_PORT": String(port),
        ])

        // Append stdout/stderr to the launch log.
        try fm.createDirectory(at: paths.supportDir, withIntermediateDirectories: true)
        if !fm.fileExists(atPath: paths.logFile.path) {
            fm.createFile(atPath: paths.logFile.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: paths.logFile)
        handle.seekToEndOfFile()
        if let header = "\n==================== launch \(Date()) ====================\n".data(using: .utf8) {
            handle.write(header)
        }
        process.standardOutput = handle
        process.standardError = handle
        self.logHandle = handle

        try process.run()
        self.process = process
    }

    private func closeLog() {
        try? logHandle?.close()
        logHandle = nil
    }

    // MARK: - Health

    /// Poll `GET /api/library` until 200 or timeout.
    func pollHealth(timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if isHealthy() { return true }
            Thread.sleep(forTimeInterval: 0.5)
        }
        return false
    }

    /// One blocking health check.
    func isHealthy(timeout: TimeInterval = 2) -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/library") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout

        let semaphore = DispatchSemaphore(value: 0)
        var ok = false
        let task = URLSession.shared.dataTask(with: request) { _, response, _ in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                ok = true
            }
            semaphore.signal()
        }
        task.resume()
        _ = semaphore.wait(timeout: .now() + timeout + 1)
        return ok
    }
}
