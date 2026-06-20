import Foundation

/// Decodable shape of an OpenAI-compatible `/v1/models` response:
/// `{ "data": [ { "id": String } ] }`.
public struct OMLXModelList: Decodable {
    public struct Model: Decodable {
        public let id: String
    }
    public let data: [Model]
}

/// Result of evaluating OMLX readiness against the set of required model ids.
public enum OMLXStatus: Equatable {
    case ready
    case missingModels([String])
    case unreachable
}

/// Pure parsing/evaluation of OMLX `/v1/models` responses. No networking here.
public enum OMLXProbe {
    /// Decode the response body and return the list of model ids.
    public static func parseModelIDs(from data: Data) throws -> [String] {
        let list = try JSONDecoder().decode(OMLXModelList.self, from: data)
        return list.data.map { $0.id }
    }

    /// Evaluate readiness.
    /// - nil or non-decodable data → `.unreachable`.
    /// - otherwise: compute which `required` ids are missing (case-sensitive
    ///   exact match). Empty → `.ready`; non-empty → `.missingModels([...])`,
    ///   preserving the order in which they appear in `required`.
    public static func evaluate(responseData: Data?, required: [String]) -> OMLXStatus {
        guard let data = responseData,
              let ids = try? parseModelIDs(from: data) else {
            return .unreachable
        }
        let present = Set(ids)
        let missing = required.filter { !present.contains($0) }
        return missing.isEmpty ? .ready : .missingModels(missing)
    }
}
