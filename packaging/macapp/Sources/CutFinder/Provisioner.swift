import Foundation
import CutFinderCore

/// Per-step status reported back to the SetupView.
enum StepStatus: Equatable {
    case waiting
    case running
    case done
    case skipped
    case guide(String)
    case failed(String)
}

/// Orchestrates the first-run provisioning sequence. All work is synchronous and
/// intended to be invoked off the main thread by the caller.
final class Provisioner {
    /// Thrown when a required (non-guide) step fails hard.
    struct ProvisionError: LocalizedError {
        let step: ProvisionStep
        let detail: String
        var errorDescription: String? { "\(step.rawValue) 步骤失败：\(detail)" }
    }

    private let paths: PayloadPaths

    init(paths: PayloadPaths) {
        self.paths = paths
    }

    /// Run the full plan.
    /// - onProgress: overall fraction in 0...1.
    /// - onStep: per-step status updates.
    /// - onLog: raw command output lines for the disclosure log.
    func run(
        onProgress: @escaping (Double) -> Void,
        onStep: @escaping (ProvisionStep, StepStatus) -> Void,
        onLog: @escaping (String) -> Void
    ) throws {
        let env = DependencyChecker.probe(paths: paths)
        let plan = ProvisionPlanner.plan(for: env)
        onLog("环境探测：uv=\(env.uvInstalled) ffmpeg=\(env.ffmpegInstalled) brew=\(env.brewInstalled) venv=\(env.pythonEnvReady) models=\(env.modelsPresent) omlx=\(env.omlxReady)")

        let total = Double(plan.count)
        for (index, planned) in plan.enumerated() {
            onProgress(Double(index) / total)
            switch planned.action {
            case .skip:
                onStep(planned.step, .skipped)
            case .guide(let reason):
                onStep(planned.step, .guide(reason))
                onLog("跳过 \(planned.step.rawValue)（需手动）：\(reason)")
            case .run:
                onStep(planned.step, .running)
                do {
                    try perform(planned.step, onLog: onLog)
                    onStep(planned.step, .done)
                } catch {
                    let detail = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                    onStep(planned.step, .failed(detail))
                    onLog("失败 \(planned.step.rawValue)：\(detail)")
                    // OMLX never blocks; everything else is fatal.
                    if planned.step != .omlx {
                        throw ProvisionError(step: planned.step, detail: detail)
                    }
                }
            }
        }
        onProgress(1.0)
        writeMarker()
    }

    // MARK: - Step implementations

    private func perform(_ step: ProvisionStep, onLog: @escaping (String) -> Void) throws {
        switch step {
        case .payload:
            try PayloadManager.sync(paths: paths)
            onLog("已同步应用文件 → \(paths.runtimeDir.path)")
        case .uv:
            try installUv(onLog: onLog)
        case .ffmpeg:
            try installFFmpeg(onLog: onLog)
        case .pythonEnv:
            try syncPythonEnv(onLog: onLog)
        case .models:
            downloadModels(onLog: onLog)
        case .omlx:
            // Probe-only; planner only routes here via .guide, but be safe.
            let status = DependencyChecker.omlxStatus()
            onLog("OMLX 状态：\(status)")
            if status != .ready {
                throw ProvisionError(step: .omlx, detail: "OMLX 未就绪：\(status)")
            }
        }
    }

    private func installUv(onLog: @escaping (String) -> Void) throws {
        onLog("安装 uv…")
        let result = Shell.bash("curl -LsSf https://astral.sh/uv/install.sh | sh")
        onLog(result.stdout + result.stderr)
        if !result.succeeded {
            throw ProvisionError(step: .uv, detail: "uv 安装脚本失败，可参考 https://docs.astral.sh/uv/")
        }
    }

    private func installFFmpeg(onLog: @escaping (String) -> Void) throws {
        onLog("通过 Homebrew 安装 ffmpeg…")
        let result = Shell.bash("brew install ffmpeg")
        onLog(result.stdout + result.stderr)
        if !(DependencyChecker.toolExists("ffmpeg") && DependencyChecker.toolExists("ffprobe")) {
            throw ProvisionError(step: .ffmpeg, detail: "ffmpeg 安装后仍未找到，请确认 Homebrew 状态")
        }
    }

    private func syncPythonEnv(onLog: @escaping (String) -> Void) throws {
        onLog("uv sync --frozen…")
        let frozen = Shell.bash("uv sync --frozen", currentDirectory: paths.backendDir)
        onLog(frozen.stdout + frozen.stderr)
        if frozen.succeeded { return }

        onLog("回落 uv sync…")
        let plain = Shell.bash("uv sync", currentDirectory: paths.backendDir)
        onLog(plain.stdout + plain.stderr)
        if !plain.succeeded {
            throw ProvisionError(step: .pythonEnv, detail: "uv sync 失败，详见日志 \(paths.logFile.path)")
        }
    }

    /// Best-effort warm of the demucs vocal-separation model (~80 MB); never
    /// fatal here so a flaky network doesn't block first run (re-runnable from
    /// the menu). The speech model (whisper / Qwen3-ASR) is *not* downloaded
    /// here — it loads lazily on the first A-roll transcription so users who
    /// never transcribe never pay for it.
    private func downloadModels(onLog: @escaping (String) -> Void) {
        let python = pythonInterpreter()
        onLog("下载模型：demucs（人声分离，约 80MB）…")
        let warm = "from cutfinder.adapters.demucs_separator import DemucsSeparator; DemucsSeparator()._ensure_model_loaded()"
        let result = Shell.bash("\(python) -c \(shellEscaped(warm))", currentDirectory: paths.backendDir)
        onLog(result.stdout + result.stderr)
    }

    /// Resolve a python invocation: prefer the venv interpreter, else `uv run python`.
    private func pythonInterpreter() -> String {
        if FileManager.default.isExecutableFile(atPath: paths.venvPython.path) {
            return shellEscaped(paths.venvPython.path)
        }
        return "uv run python"
    }

    private func shellEscaped(_ path: String) -> String {
        "'" + path.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private func writeMarker() {
        try? AppConfig.setupVersion.write(to: paths.setupMarker, atomically: true, encoding: .utf8)
    }
}
