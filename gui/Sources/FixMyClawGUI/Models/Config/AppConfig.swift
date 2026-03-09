import Foundation

// MARK: - 可编辑配置模型

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

extension AppConfig {
    init(dto: AppConfigDTO) {
        monitor = dto.monitor
        openclaw = dto.openclaw
        repair = dto.repair
        anomalyGuard = dto.anomalyGuard
        notify = dto.notify
        ai = dto.ai
        agentRoles = dto.agentRoles
    }
}
