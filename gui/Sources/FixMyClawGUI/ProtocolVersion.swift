import Foundation

private let supportedAPIMajorVersion = 1

private struct APIVersion: Equatable {
    let rawValue: String
    let major: Int
    let minor: Int

    init?(rawValue: String) {
        let parts = rawValue.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 2,
              let major = Int(parts[0]),
              let minor = Int(parts[1]) else {
            return nil
        }
        self.rawValue = rawValue
        self.major = major
        self.minor = minor
    }
}

func validateTopLevelAPIVersion(in data: Data) throws {
    let object = try JSONSerialization.jsonObject(with: data)
    guard let payload = object as? [String: Any] else {
        throw CLIError.decodingFailed(NSError(
            domain: "FixMyClawGUI.ProtocolVersion",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "CLI JSON 顶层不是对象"]
        ))
    }
    try validateTopLevelAPIVersion(in: payload)
}

func validateTopLevelAPIVersion(in payload: [String: Any]) throws {
    guard let rawValue = payload["api_version"] as? String else {
        return
    }
    guard let version = APIVersion(rawValue: rawValue) else {
        throw CLIError.unsupportedAPIVersion(rawValue)
    }
    guard version.major == supportedAPIMajorVersion else {
        throw CLIError.unsupportedAPIVersion(rawValue)
    }
}
