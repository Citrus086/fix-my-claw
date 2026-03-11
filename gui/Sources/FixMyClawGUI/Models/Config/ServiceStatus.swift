import Foundation

struct ServiceStatus: Codable {
    let installed: Bool
    let running: Bool
    let label: String
    let plistPath: String
    let domain: String
    let programPath: String?
    let configPath: String?
    let expectedProgramPath: String?
    let expectedConfigPath: String?
    let drifted: Bool

    init(
        installed: Bool,
        running: Bool,
        label: String,
        plistPath: String,
        domain: String,
        programPath: String? = nil,
        configPath: String? = nil,
        expectedProgramPath: String? = nil,
        expectedConfigPath: String? = nil,
        drifted: Bool = false
    ) {
        self.installed = installed
        self.running = running
        self.label = label
        self.plistPath = plistPath
        self.domain = domain
        self.programPath = programPath
        self.configPath = configPath
        self.expectedProgramPath = expectedProgramPath
        self.expectedConfigPath = expectedConfigPath
        self.drifted = drifted
    }

    enum CodingKeys: String, CodingKey {
        case installed, running, label, domain
        case plistPath = "plist_path"
        case programPath = "program_path"
        case configPath = "config_path"
        case expectedProgramPath = "expected_program_path"
        case expectedConfigPath = "expected_config_path"
        case drifted
    }
}

struct ServiceReconcileResult: Codable {
    let action: String
    let reasons: [String]
    let service: ServiceStatus
}
