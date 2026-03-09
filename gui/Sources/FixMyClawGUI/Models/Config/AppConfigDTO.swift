import Foundation

// MARK: - CLI 配置传输模型

struct AppConfigDTO: Codable {
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

    init(editable config: AppConfig) {
        monitor = config.monitor
        openclaw = config.openclaw
        repair = config.repair
        anomalyGuard = config.anomalyGuard
        notify = config.notify
        ai = config.ai
        agentRoles = config.agentRoles
    }

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
