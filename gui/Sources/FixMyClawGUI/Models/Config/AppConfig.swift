import Foundation

// MARK: - 完整配置模型（与 Python 端同步）

struct AppConfig: Codable {
    var monitor = MonitorConfig()
    var openclaw = OpenClawConfig()
    var repair = RepairConfig()
    var anomalyGuard = AnomalyGuardConfig()
    var notify = NotifyConfig()
    var ai = AiConfig()
    var agentRoles = AgentRolesConfig()

    enum CodingKeys: String, CodingKey {
        case monitor
        case openclaw
        case repair
        case anomalyGuard = "anomaly_guard"
        case notify
        case ai
        case agentRoles = "agent_roles"
    }

    init() {}

    // 自定义解码器，增强对缺失 section 的韧性
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        monitor = try container.decodeIfPresent(MonitorConfig.self, forKey: .monitor) ?? MonitorConfig()
        openclaw = try container.decodeIfPresent(OpenClawConfig.self, forKey: .openclaw) ?? OpenClawConfig()
        repair = try container.decodeIfPresent(RepairConfig.self, forKey: .repair) ?? RepairConfig()
        anomalyGuard = try container.decodeIfPresent(AnomalyGuardConfig.self, forKey: .anomalyGuard) ?? AnomalyGuardConfig()
        notify = try container.decodeIfPresent(NotifyConfig.self, forKey: .notify) ?? NotifyConfig()
        ai = try container.decodeIfPresent(AiConfig.self, forKey: .ai) ?? AiConfig()
        agentRoles = try container.decodeIfPresent(AgentRolesConfig.self, forKey: .agentRoles) ?? AgentRolesConfig()
    }
}

extension KeyedDecodingContainer {
    func decodeOrDefault<T: Decodable>(
        _ type: T.Type,
        forKey key: Key,
        default defaultValue: @autoclosure () -> T
    ) throws -> T {
        try decodeIfPresent(type, forKey: key) ?? defaultValue()
    }
}

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
