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

    /// Whether the whisper + demucs model weights are present.
    ///
    /// CutFinder stores models under `<runtime>/models/` (see
    /// `cutfinder.config.WHISPER_MODELS_DIR` / `DEMUCS_MODELS_DIR`), *not* the
    /// global `~/.cache` Hugging Face / torch caches. We check both there:
    /// whisper at `models/whisper/whisper-large-v3-mlx`, demucs at
    /// `models/demucs/checkpoints` (torch-hub layout). Both must exist to call
    /// models present, so the download step is skipped (and stays offline) only
    /// once both are actually on disk.
    static func modelsPresent(paths: PayloadPaths) -> Bool {
        let fm = FileManager.default
        let models = paths.modelsDir
        let whisper = models
            .appendingPathComponent("whisper", isDirectory: true)
            .appendingPathComponent("whisper-large-v3-mlx", isDirectory: true)
        let demucs = models
            .appendingPathComponent("demucs", isDirectory: true)
            .appendingPathComponent("checkpoints", isDirectory: true)
        let whisperOK = fm.fileExists(atPath: whisper.path)
        let demucsOK = fm.fileExists(atPath: demucs.path)
        return whisperOK && demucsOK
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
