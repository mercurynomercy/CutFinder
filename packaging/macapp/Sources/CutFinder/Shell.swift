import Foundation

/// Result of running an external command.
struct ShellResult {
    let exitCode: Int32
    let stdout: String
    let stderr: String

    var succeeded: Bool { exitCode == 0 }
}

/// Small helper around `Process` for running commands and capturing exit status
/// + output. Deliberately synchronous: callers run it off the main thread.
enum Shell {
    /// PATH augmented with the locations where uv / brew / ffmpeg typically live,
    /// prepended to whatever the inherited environment already has.
    static func augmentedPATH() -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let extra = [
            "\(home)/.local/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        ].joined(separator: ":")
        let existing = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        return "\(extra):\(existing)"
    }

    /// Environment dictionary with the augmented PATH applied.
    static func augmentedEnvironment(extra: [String: String] = [:]) -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = augmentedPATH()
        for (k, v) in extra { env[k] = v }
        return env
    }

    /// Run an executable directly (no shell), capturing stdout/stderr.
    @discardableResult
    static func run(
        _ executable: URL,
        arguments: [String],
        currentDirectory: URL? = nil,
        environment: [String: String]? = nil
    ) -> ShellResult {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = currentDirectory
        process.environment = environment ?? augmentedEnvironment()

        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        do {
            try process.run()
        } catch {
            return ShellResult(exitCode: -1, stdout: "", stderr: "failed to launch \(executable.path): \(error.localizedDescription)")
        }

        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        return ShellResult(
            exitCode: process.terminationStatus,
            stdout: String(data: outData, encoding: .utf8) ?? "",
            stderr: String(data: errData, encoding: .utf8) ?? ""
        )
    }

    /// Run a command line through `/bin/sh -c`, capturing output.
    @discardableResult
    static func bash(
        _ command: String,
        currentDirectory: URL? = nil,
        environment: [String: String]? = nil
    ) -> ShellResult {
        run(
            URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", command],
            currentDirectory: currentDirectory,
            environment: environment
        )
    }

    /// Locate a tool on the augmented PATH. Returns its absolute path, or nil.
    static func which(_ tool: String) -> String? {
        let result = bash("command -v \(tool)")
        guard result.succeeded else { return nil }
        let path = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        return path.isEmpty ? nil : path
    }
}
