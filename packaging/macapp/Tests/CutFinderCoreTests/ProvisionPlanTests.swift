import XCTest
@testable import CutFinderCore

final class ProvisionPlanTests: XCTestCase {
    private func env(
        uv: Bool = false,
        ffmpeg: Bool = false,
        brew: Bool = false,
        pythonEnv: Bool = false,
        models: Bool = false,
        omlx: Bool = false
    ) -> EnvironmentProbe {
        EnvironmentProbe(
            uvInstalled: uv,
            ffmpegInstalled: ffmpeg,
            brewInstalled: brew,
            pythonEnvReady: pythonEnv,
            modelsPresent: models,
            omlxReady: omlx
        )
    }

    private func action(_ plan: [PlannedStep], _ step: ProvisionStep) -> StepAction {
        plan.first { $0.step == step }!.action
    }

    func testPlanOrderMatchesAllCases() {
        let plan = ProvisionPlanner.plan(for: env())
        XCTAssertEqual(plan.map { $0.step }, ProvisionStep.allCases)
    }

    func testPayloadAlwaysRuns() {
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env()), .payload), .run)
        XCTAssertEqual(
            action(ProvisionPlanner.plan(for: env(uv: true, ffmpeg: true, brew: true, pythonEnv: true, models: true, omlx: true)), .payload),
            .run
        )
    }

    func testUvBranches() {
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(uv: false)), .uv), .run)
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(uv: true)), .uv), .skip)
    }

    func testFfmpegPresentSkips() {
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(ffmpeg: true)), .ffmpeg), .skip)
    }

    func testFfmpegAbsentWithBrewRuns() {
        XCTAssertEqual(
            action(ProvisionPlanner.plan(for: env(ffmpeg: false, brew: true)), .ffmpeg),
            .run
        )
    }

    func testFfmpegAbsentNoBrewGuides() {
        XCTAssertEqual(
            action(ProvisionPlanner.plan(for: env(ffmpeg: false, brew: false)), .ffmpeg),
            .guide("ffmpeg-no-brew")
        )
    }

    func testPythonEnvBranches() {
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(pythonEnv: false)), .pythonEnv), .run)
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(pythonEnv: true)), .pythonEnv), .skip)
    }

    func testModelsBranches() {
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(models: false)), .models), .run)
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(models: true)), .models), .skip)
    }

    func testOmlxBranches() {
        XCTAssertEqual(
            action(ProvisionPlanner.plan(for: env(omlx: false)), .omlx),
            .guide("omlx-missing")
        )
        XCTAssertEqual(action(ProvisionPlanner.plan(for: env(omlx: true)), .omlx), .skip)
    }

    func testFreshMachineFullPlan() {
        let plan = ProvisionPlanner.plan(for: env())
        XCTAssertEqual(plan, [
            PlannedStep(step: .payload, action: .run),
            PlannedStep(step: .uv, action: .run),
            PlannedStep(step: .ffmpeg, action: .guide("ffmpeg-no-brew")),
            PlannedStep(step: .pythonEnv, action: .run),
            PlannedStep(step: .models, action: .run),
            PlannedStep(step: .omlx, action: .guide("omlx-missing")),
        ])
    }

    func testFullySetUpFullPlan() {
        let plan = ProvisionPlanner.plan(for: env(
            uv: true, ffmpeg: true, brew: true, pythonEnv: true, models: true, omlx: true
        ))
        XCTAssertEqual(plan, [
            PlannedStep(step: .payload, action: .run),
            PlannedStep(step: .uv, action: .skip),
            PlannedStep(step: .ffmpeg, action: .skip),
            PlannedStep(step: .pythonEnv, action: .skip),
            PlannedStep(step: .models, action: .skip),
            PlannedStep(step: .omlx, action: .skip),
        ])
    }
}
