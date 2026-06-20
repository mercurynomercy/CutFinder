import XCTest
@testable import CutFinderCore

final class PayloadPathsTests: XCTestCase {
    private let home = URL(fileURLWithPath: "/tmp/cf-home", isDirectory: true)

    private func paths() -> PayloadPaths {
        PayloadPaths(home: home)
    }

    func testSupportDir() {
        XCTAssertEqual(
            paths().supportDir.path,
            "/tmp/cf-home/Library/Application Support/CutFinder"
        )
    }

    func testRuntimeDir() {
        XCTAssertEqual(
            paths().runtimeDir.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/app"
        )
    }

    func testBackendDir() {
        XCTAssertEqual(
            paths().backendDir.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/app/backend"
        )
    }

    func testVenvPython() {
        XCTAssertEqual(
            paths().venvPython.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/app/backend/.venv/bin/python"
        )
    }

    func testFrontendDist() {
        XCTAssertEqual(
            paths().frontendDist.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/app/frontend/dist"
        )
    }

    func testLogFile() {
        XCTAssertEqual(
            paths().logFile.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/launch.log"
        )
    }

    func testSetupMarker() {
        XCTAssertEqual(
            paths().setupMarker.path,
            "/tmp/cf-home/Library/Application Support/CutFinder/.setup-complete"
        )
    }

    func testRsyncExcludes() {
        XCTAssertEqual(PayloadPaths.rsyncExcludes, ["backend/.venv", "__pycache__"])
    }

    func testUserDefaultUsesHomeDirectory() {
        let expected = FileManager.default.homeDirectoryForCurrentUser
        XCTAssertEqual(PayloadPaths.userDefault().home, expected)
    }
}
