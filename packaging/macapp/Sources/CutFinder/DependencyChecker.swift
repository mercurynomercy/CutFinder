import Foundation
import CutFinderCore

/// Probes the machine environment to build an `EnvironmentProbe`, the input to
/// `ProvisionPlanner`.
enum DependencyChecker {
    /// Build a full probe of the current environment for the given paths.
    static func probe(paths: PayloadPaths) -> EnvironmentProbe {
        EnvironmentProbe(
            uvInstalled: toolExists("uv"),
            ffmpegInstalled: toolExists("ffmpeg") && toolExists("ffprobe"),
            brewInstalled: toolExists("brew"),
            pythonEnvReady: FileManager.default.isExecutableFile(atPath: paths.venvPython.path),
            modelsPresent: modelsPresent(paths: paths),
            omlxReady: omlxStatus() == .ready
        )
    }

    /// Whether a CLI tool resolves on the augmented PATH.
    static func toolExists(_ tool: String) -> Bool {
        Shell.which(tool) != nil
    }

    /// Whether the demucs model weights are present.
    ///
    /// Only demucs (~80 MB vocal separation) is provisioned at first launch.
    /// The speech model (whisper *or* Qwen3-ASR, per the `transcription_engine`
    /// pref) is intentionally *not* checked here: it downloads lazily on the
    /// first A-roll transcription, so users who never transcribe never pay for
    /// it. CutFinder stores demucs under `<runtime>/models/demucs/checkpoints`
    /// (torch-hub layout), *not* the global torch cache. The download step is
    /// skipped only once demucs is actually on disk.
    static func modelsPresent(paths: PayloadPaths) -> Bool {
        let fm = FileManager.default
        let demucs = paths.modelsDir
            .appendingPathComponent("demucs", isDirectory: true)
            .appendingPathComponent("checkpoints", isDirectory: true)
        return fm.fileExists(atPath: demucs.path)
    }

    /// Synchronously query OMLX `/models` and evaluate readiness.
    static func omlxStatus(timeout: TimeInterval = 3) -> OMLXStatus {
        let data = fetchOMLXModels(timeout: timeout)
        return OMLXProbe.evaluate(responseData: data, required: AppConfig.requiredOMLXModels)
    }

    /// Blocking GET of `<OMLX_BASE_URL>/models`; returns the body or nil.
    static func fetchOMLXModels(timeout: TimeInterval) -> Data? {
        guard let url = URL(string: AppConfig.omlxBaseURL + "/models") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout

        // Add auth header if API key is configured.
        if let header = AppConfig.omlxAuthHeader {
            request.setValue(header, forHTTPHeaderField: "Authorization")
        }

        let semaphore = DispatchSemaphore(value: 0)
        var body: Data?
        let task = URLSession.shared.dataTask(with: request) { data, response, _ in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                body = data
            }
            semaphore.signal()
        }
        task.resume()
        _ = semaphore.wait(timeout: .now() + timeout + 1)
        return body
    }
}
