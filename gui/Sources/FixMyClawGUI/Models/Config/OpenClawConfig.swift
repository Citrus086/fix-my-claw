import Foundation

struct OpenClawConfig: Codable {
    var command: String = "openclaw"
    var stateDir: String = "~/.openclaw"
    var workspaceDir: String = "~/.openclaw/workspace"
    var healthArgs: [String] = ["gateway", "health", "--json"]
    var statusArgs: [String] = ["gateway", "status", "--json"]
    var logsArgs: [String] = ["logs", "--limit", "200", "--plain"]

    enum CodingKeys: String, CodingKey {
        case command
        case stateDir = "state_dir"
        case workspaceDir = "workspace_dir"
        case healthArgs = "health_args"
        case statusArgs = "status_args"
        case logsArgs = "logs_args"
    }
}

extension OpenClawConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        command = try container.decodeOrDefault(String.self, forKey: .command, default: defaults.command)
        stateDir = try container.decodeOrDefault(String.self, forKey: .stateDir, default: defaults.stateDir)
        workspaceDir = try container.decodeOrDefault(String.self, forKey: .workspaceDir, default: defaults.workspaceDir)
        healthArgs = try container.decodeOrDefault([String].self, forKey: .healthArgs, default: defaults.healthArgs)
        statusArgs = try container.decodeOrDefault([String].self, forKey: .statusArgs, default: defaults.statusArgs)
        logsArgs = try container.decodeOrDefault([String].self, forKey: .logsArgs, default: defaults.logsArgs)
    }
}
