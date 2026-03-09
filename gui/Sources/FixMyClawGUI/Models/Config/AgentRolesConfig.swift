import Foundation

struct AgentRolesConfig: Codable {
    var orchestrator: [String] = ["orchestrator", "macs-orchestrator"]
    var builder: [String] = ["builder", "macs-builder"]
    var architect: [String] = ["architect", "macs-architect"]
    var research: [String] = ["research", "macs-research"]

    enum CodingKeys: String, CodingKey {
        case orchestrator, builder, architect, research
    }
}

extension AgentRolesConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        orchestrator = try container.decodeOrDefault([String].self, forKey: .orchestrator, default: defaults.orchestrator)
        builder = try container.decodeOrDefault([String].self, forKey: .builder, default: defaults.builder)
        architect = try container.decodeOrDefault([String].self, forKey: .architect, default: defaults.architect)
        research = try container.decodeOrDefault([String].self, forKey: .research, default: defaults.research)
    }
}
