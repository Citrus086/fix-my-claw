import Foundation
import XCTest

/// Helper for loading contract fixtures from the shared contracts/fixtures directory.
enum FixtureLoader {
    /// Load a fixture file as Data.
    /// - Parameter name: Fixture filename (e.g., "config.show.v1.json")
    /// - Returns: The file contents as Data
    static func loadData(name: String) throws -> Data {
        let url = try resolveFixtureURL(name: name)
        return try Data(contentsOf: url)
    }

    /// Load a fixture file as decoded JSON.
    /// - Parameters:
    ///   - name: Fixture filename (e.g., "config.show.v1.json")
    ///   - type: The Decodable type to decode to
    /// - Returns: The decoded object
    static func load<T: Decodable>(_ type: T.Type, from name: String) throws -> T {
        let data = try loadData(name: name)
        return try JSONDecoder().decode(type, from: data)
    }

    /// Load a fixture file as a raw JSON dictionary.
    /// - Parameter name: Fixture filename
    /// - Returns: The JSON as [String: Any]
    static func loadJSON(name: String) throws -> [String: Any] {
        let data = try loadData(name: name)
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw FixtureError.invalidJSON(name)
        }
        return json
    }

    /// Resolve the URL for a fixture file.
    /// Looks in:
    /// 1. ../../../contracts/fixtures/ (relative to test file, for SPM)
    /// 2. $(SRCROOT)/../contracts/fixtures/ (for Xcode)
    private static func resolveFixtureURL(name: String) throws -> URL {
        // From gui/Tests/FixMyClawGUITests/ need to go up 3 levels to reach project root
        let testFileDir = URL(fileURLWithPath: #file).deletingLastPathComponent()
        let spmRelativeURL = testFileDir
            .deletingLastPathComponent()  // Tests/
            .deletingLastPathComponent()  // gui/
            .deletingLastPathComponent()  // project root
            .appendingPathComponent("contracts/fixtures/\(name)")

        if FileManager.default.fileExists(atPath: spmRelativeURL.path) {
            return spmRelativeURL
        }

        // Try Xcode SRCROOT environment variable
        if let srcroot = ProcessInfo.processInfo.environment["SRCROOT"] {
            let xcodeURL = URL(fileURLWithPath: srcroot)
                .appendingPathComponent("../contracts/fixtures/\(name)")
            if FileManager.default.fileExists(atPath: xcodeURL.path) {
                return xcodeURL
            }
        }

        throw FixtureError.notFound(name)
    }
}

enum FixtureError: LocalizedError {
    case notFound(String)
    case invalidJSON(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let name):
            return "Fixture not found: \(name)"
        case .invalidJSON(let name):
            return "Invalid JSON in fixture: \(name)"
        }
    }
}
