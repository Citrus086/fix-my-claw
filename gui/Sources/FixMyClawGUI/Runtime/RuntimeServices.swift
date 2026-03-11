import Foundation

// MARK: - Service Protocols

/// 状态服务协议
@MainActor
protocol StatusServiceProtocol: Sendable {
    func getStatus(configPath: String?) async throws -> StatusPayload
    func getServiceStatus(configPath: String?) async throws -> ServiceStatus
    func checkHealth(configPath: String?) async throws -> CheckPayload
}

/// 修复服务协议
@MainActor
protocol RepairServiceProtocol: Sendable {
    func repair(force: Bool, configPath: String?) async throws -> RepairResult
    func getRepairProgress() -> RepairProgressInfo?
    func getRepairResult() -> PersistedRepairResult?
}

/// 审批服务协议
@MainActor
protocol ApprovalServiceProtocol: Sendable {
    func getPendingRequest() -> ApprovalRequest?
    func getDecision() -> ApprovalDecision?
    func submitDecision(request: ApprovalRequest, decision: String) -> Bool
}

/// 配置服务协议
@MainActor
protocol ConfigServiceProtocol: Sendable {
    func getConfig(configPath: String?) async throws -> AppConfig
    func setConfig(_ config: AppConfig, configPath: String?) async throws
}

/// 后台服务管理协议
@MainActor
protocol DaemonServiceProtocol: Sendable {
    func installService(configPath: String?) async throws
    func startService(configPath: String?) async throws
    func reconcileService(configPath: String?) async throws -> ServiceReconcileResult
    func stopService() async throws
}

// MARK: - Data Structures

/// 修复进度信息
struct RepairProgressInfo: Decodable {
    let stage: String
    let status: String
    let attemptDir: String?
    let timestamp: Double
    
    enum CodingKeys: String, CodingKey {
        case stage
        case status
        case attemptDir = "attempt_dir"
        case timestamp
    }
}

/// 审批请求
struct ApprovalRequest: Decodable, Equatable {
    let requestId: String
    let prompt: String
    
    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case prompt
    }
}

/// 审批决策
struct ApprovalDecision: Decodable {
    let requestId: String
    let decision: String
    let source: String?
    
    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case decision
        case source
    }
}

// MARK: - RuntimeServices

/// RuntimeServices 是 GUI 运行时的 IO 层统一入口
/// 负责所有 CLI 调用、文件读取/写入，不持有状态
@MainActor
final class RuntimeServices {
    static let shared = RuntimeServices()
    
    let cli = CLIWrapper()
    
    // 文件路径常量
    private let approvalActiveFileName = "ai_approval.active.json"
    private let approvalDecisionFileName = "ai_approval.decision.json"
    private let repairProgressFileName = "repair_progress.json"
    private let repairResultFileName = "repair_result.json"
    private let notificationEventsFileName = "notification_events.json"
    
    private var configPath: String { ConfigManager.shared.defaultConfigPath }
    
    private init() {}
    
    // MARK: - 状态目录
    
    private func stateDirectoryURL() -> URL {
        if let configured = ConfigManager.shared.config?.monitor.stateDir, !configured.isEmpty {
            return URL(fileURLWithPath: (configured as NSString).expandingTildeInPath)
        }
        return ConfigManager.shared.defaultStateDirectoryURL
    }

    func currentStateDirectoryURL() -> URL {
        stateDirectoryURL()
    }
}

// MARK: - StatusServiceProtocol

extension RuntimeServices: StatusServiceProtocol {
    func getStatus(configPath: String?) async throws -> StatusPayload {
        try await cli.getStatus(configPath: configPath ?? self.configPath)
    }
    
    func getServiceStatus(configPath: String?) async throws -> ServiceStatus {
        try await cli.getServiceStatus(configPath: configPath ?? self.configPath)
    }
    
    func checkHealth(configPath: String?) async throws -> CheckPayload {
        try await cli.check(configPath: configPath ?? self.configPath)
    }
}

// MARK: - RepairServiceProtocol

extension RuntimeServices: RepairServiceProtocol {
    func repair(force: Bool, configPath: String?) async throws -> RepairResult {
        try await cli.repair(force: force, configPath: configPath ?? self.configPath)
    }
    
    func getRepairProgress() -> RepairProgressInfo? {
        let url = stateDirectoryURL().appendingPathComponent(repairProgressFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RepairProgressInfo.self, from: data)
    }
    
    func getRepairResult() -> PersistedRepairResult? {
        let url = stateDirectoryURL().appendingPathComponent(repairResultFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(PersistedRepairResult.self, from: data)
    }

    func getNotificationEvents() -> [PersistedNotificationEvent] {
        let url = stateDirectoryURL().appendingPathComponent(notificationEventsFileName)
        guard let data = try? Data(contentsOf: url) else { return [] }
        guard let store = try? JSONDecoder().decode(PersistedNotificationEventStore.self, from: data) else {
            return []
        }
        return store.events.sorted(by: { $0.sequence < $1.sequence })
    }
}

// MARK: - ApprovalServiceProtocol

extension RuntimeServices: ApprovalServiceProtocol {
    func getPendingRequest() -> ApprovalRequest? {
        let url = stateDirectoryURL().appendingPathComponent(approvalActiveFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ApprovalRequest.self, from: data)
    }
    
    func getDecision() -> ApprovalDecision? {
        let url = stateDirectoryURL().appendingPathComponent(approvalDecisionFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ApprovalDecision.self, from: data)
    }
    
    func submitDecision(request: ApprovalRequest, decision: String) -> Bool {
        let stateDir = stateDirectoryURL()
        let decisionURL = stateDir.appendingPathComponent(approvalDecisionFileName)
        let activeURL = stateDir.appendingPathComponent(approvalActiveFileName)
        
        // 检查请求是否仍然有效
        guard let active = getPendingRequest(), active.requestId == request.requestId else {
            return false
        }
        
        let payload: [String: Any] = [
            "request_id": request.requestId,
            "decision": decision,
            "source": "gui",
        ]
        
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) else {
            return false
        }
        
        // 创建目录（如果不存在）
        try? FileManager.default.createDirectory(
            at: stateDir,
            withIntermediateDirectories: true,
            attributes: nil
        )
        
        // 使用 O_EXCL 确保原子性写入
        let fd = open(decisionURL.path, O_WRONLY | O_CREAT | O_EXCL, 0o600)
        guard fd != -1 else { return false }
        
        let writeSucceeded = data.withUnsafeBytes { rawBuffer -> Bool in
            guard let baseAddress = rawBuffer.baseAddress else { return false }
            var totalWritten = 0
            while totalWritten < data.count {
                let written = Darwin.write(fd, baseAddress.advanced(by: totalWritten), data.count - totalWritten)
                if written <= 0 {
                    return false
                }
                totalWritten += written
            }
            return true
        }
        
        close(fd)
        
        if !writeSucceeded {
            try? FileManager.default.removeItem(at: decisionURL)
            return false
        }
        
        // 写入成功后删除 active 文件
        if let active = getPendingRequest(), active.requestId == request.requestId {
            try? FileManager.default.removeItem(at: activeURL)
        }
        
        return true
    }
}

// MARK: - ConfigServiceProtocol

extension RuntimeServices: ConfigServiceProtocol {
    func getConfig(configPath: String?) async throws -> AppConfig {
        try await cli.getConfig(configPath: configPath ?? self.configPath)
    }
    
    func setConfig(_ config: AppConfig, configPath: String?) async throws {
        try await cli.setConfig(config, configPath: configPath ?? self.configPath)
    }
}

// MARK: - DaemonServiceProtocol

extension RuntimeServices: DaemonServiceProtocol {
    func installService(configPath: String?) async throws {
        try await cli.installService(configPath: configPath ?? self.configPath)
    }
    
    func startService(configPath: String?) async throws {
        try await cli.startService(configPath: configPath ?? self.configPath)
    }

    func reconcileService(configPath: String?) async throws -> ServiceReconcileResult {
        try await cli.reconcileService(configPath: configPath ?? self.configPath)
    }
    
    func stopService() async throws {
        try await cli.stopService()
    }
}

// MARK: - Utility Methods

extension RuntimeServices {
    /// 获取日志路径
    func getLogPath(configPath: String?) async throws -> String {
        let config = try await getConfig(configPath: configPath)
        return config.monitor.logFile
    }
    
    /// 获取尝试记录目录路径
    func getAttemptsPath(configPath: String?) async throws -> String {
        let config = try await getConfig(configPath: configPath)
        return (config.monitor.stateDir as NSString).appendingPathComponent("attempts")
    }
    
    /// 创建默认配置
    func createDefaultConfig(at path: String?, force: Bool) async throws {
        _ = try await cli.initializeConfig(at: path ?? configPath, force: force)
    }
    
    /// 启用监控
    func enableMonitoring(configPath: String?) async throws -> StatusPayload {
        try await cli.enableMonitoring(configPath: configPath ?? self.configPath)
    }
    
    /// 禁用监控
    func disableMonitoring(configPath: String?) async throws -> StatusPayload {
        try await cli.disableMonitoring(configPath: configPath ?? self.configPath)
    }
}
