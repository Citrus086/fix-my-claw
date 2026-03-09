import Foundation

struct ServiceStatus: Codable {
    let installed: Bool
    let running: Bool
    let label: String
    let plistPath: String
    let domain: String

    enum CodingKeys: String, CodingKey {
        case installed, running, label, domain
        case plistPath = "plist_path"
    }
}
