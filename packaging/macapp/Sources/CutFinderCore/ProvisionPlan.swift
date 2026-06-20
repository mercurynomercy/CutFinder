import Foundation

/// One step of the first-run provisioning sequence.
public enum ProvisionStep: String, CaseIterable {
    case payload
    case uv
    case ffmpeg
    case pythonEnv
    case models
    case omlx
}

/// What to do for a given step.
/// - `.run`: perform it.
/// - `.skip`: already satisfied.
/// - `.guide`: can't be done automatically; show guidance (associated value is
///   a short reason key).
public enum StepAction: Equatable {
    case run
    case skip
    case guide(String)
}

/// Probe of the current machine environment, the input to planning.
public struct EnvironmentProbe: Equatable {
    public var uvInstalled: Bool
    public var ffmpegInstalled: Bool
    public var brewInstalled: Bool
    public var pythonEnvReady: Bool
    public var modelsPresent: Bool
    public var omlxReady: Bool

    public init(
        uvInstalled: Bool,
        ffmpegInstalled: Bool,
        brewInstalled: Bool,
        pythonEnvReady: Bool,
        modelsPresent: Bool,
        omlxReady: Bool
    ) {
        self.uvInstalled = uvInstalled
        self.ffmpegInstalled = ffmpegInstalled
        self.brewInstalled = brewInstalled
        self.pythonEnvReady = pythonEnvReady
        self.modelsPresent = modelsPresent
        self.omlxReady = omlxReady
    }
}

/// A step paired with its planned action.
public struct PlannedStep: Equatable {
    public let step: ProvisionStep
    public let action: StepAction

    public init(step: ProvisionStep, action: StepAction) {
        self.step = step
        self.action = action
    }
}

/// Decides, per step, whether to run / skip / guide based on the environment.
public enum ProvisionPlanner {
    /// Returns a plan in `ProvisionStep.allCases` order.
    public static func plan(for env: EnvironmentProbe) -> [PlannedStep] {
        ProvisionStep.allCases.map { step in
            PlannedStep(step: step, action: action(for: step, env: env))
        }
    }

    private static func action(for step: ProvisionStep, env: EnvironmentProbe) -> StepAction {
        switch step {
        case .payload:
            // rsync is idempotent; always run.
            return .run
        case .uv:
            return env.uvInstalled ? .skip : .run
        case .ffmpeg:
            if env.ffmpegInstalled { return .skip }
            return env.brewInstalled ? .run : .guide("ffmpeg-no-brew")
        case .pythonEnv:
            return env.pythonEnvReady ? .skip : .run
        case .models:
            return env.modelsPresent ? .skip : .run
        case .omlx:
            // Never auto-installed; never blocks.
            return env.omlxReady ? .skip : .guide("omlx-missing")
        }
    }
}
