import XCTest
@testable import CutFinderCore

final class OMLXProbeTests: XCTestCase {
    private func data(_ s: String) -> Data { Data(s.utf8) }

    func testParseModelIDs() throws {
        let json = #"{"data":[{"id":"a"},{"id":"b"}]}"#
        let ids = try OMLXProbe.parseModelIDs(from: data(json))
        XCTAssertEqual(ids, ["a", "b"])
    }

    func testParseEmpty() throws {
        let ids = try OMLXProbe.parseModelIDs(from: data(#"{"data":[]}"#))
        XCTAssertEqual(ids, [])
    }

    func testParseMalformedThrows() {
        XCTAssertThrowsError(try OMLXProbe.parseModelIDs(from: data("not json")))
    }

    func testEvaluateNilIsUnreachable() {
        XCTAssertEqual(OMLXProbe.evaluate(responseData: nil, required: ["a"]), .unreachable)
    }

    func testEvaluateMalformedIsUnreachable() {
        XCTAssertEqual(
            OMLXProbe.evaluate(responseData: data("<<broken>>"), required: ["a"]),
            .unreachable
        )
    }

    func testEvaluateAllPresentIsReady() {
        let json = #"{"data":[{"id":"Qwen3.6-35B-A3B"},{"id":"Qwen3-VL-8B-Instruct"}]}"#
        let status = OMLXProbe.evaluate(
            responseData: data(json),
            required: ["Qwen3.6-35B-A3B", "Qwen3-VL-8B-Instruct"]
        )
        XCTAssertEqual(status, .ready)
    }

    func testEvaluateNoRequiredIsReady() {
        let json = #"{"data":[{"id":"x"}]}"#
        XCTAssertEqual(OMLXProbe.evaluate(responseData: data(json), required: []), .ready)
    }

    func testEvaluateSomeMissing() {
        let json = #"{"data":[{"id":"Qwen3-VL-8B-Instruct"}]}"#
        let status = OMLXProbe.evaluate(
            responseData: data(json),
            required: ["Qwen3.6-35B-A3B", "Qwen3-VL-8B-Instruct"]
        )
        XCTAssertEqual(status, .missingModels(["Qwen3.6-35B-A3B"]))
    }

    func testEvaluateMissingPreservesRequiredOrder() {
        let json = #"{"data":[]}"#
        let status = OMLXProbe.evaluate(responseData: data(json), required: ["a", "b", "c"])
        XCTAssertEqual(status, .missingModels(["a", "b", "c"]))
    }

    func testEvaluateIsCaseSensitive() {
        let json = #"{"data":[{"id":"qwen"}]}"#
        let status = OMLXProbe.evaluate(responseData: data(json), required: ["Qwen"])
        XCTAssertEqual(status, .missingModels(["Qwen"]))
    }
}
