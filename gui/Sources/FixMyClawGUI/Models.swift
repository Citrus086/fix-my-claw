import Foundation

// MARK: - CLI 输出模型

struct StatusPayload: Codable {
    let enabled: Bool
    let configPath: String
    let configExists: Bool
    let statePath: String
    let lastOkTs: Int?
    let lastRepairTs: Int?
    let lastAiTs: Int?
    let aiAttemptsDay: String?
    let aiAttemptsCount: Int
    
    enum CodingKeys: String, CodingKey {
        case enabled
        case configPath = "config_path"
        case configExists = "config_exists"
        case statePath = "state_path"
        case lastOkTs = "last_ok_ts"
        case lastRepairTs = "last_repair_ts"
        case lastAiTs = "last_ai_ts"
        case aiAttemptsDay = "ai_attempts_day"
        case aiAttemptsCount = "ai_attempts_count"
    }
}

struct CheckPayload: Codable {
    let healthy: Bool
    let probeHealthy: Bool
    let reason: String?
    let health: ProbeResult
    let status: ProbeResult
    let logs: LogsSummary?
    let anomalyGuard: AnomalyGuardResult?
    let loopGuard: AnomalyGuardResult?
    
    enum CodingKeys: String, CodingKey {
        case healthy, reason, health, status, logs
        case probeHealthy = "probe_healthy"
        case anomalyGuard = "anomaly_guard"
        case loopGuard = "loop_guard"
    }
}

struct ProbeResult: Codable {
    let name: String
    let ok: Bool
    let exitCode: Int
    let durationMs: Int
    let argv: [String]
    let stdout: String
    let stderr: String
    
    enum CodingKeys: String, CodingKey {
        case name, ok, argv, stdout, stderr
        case exitCode = "exit_code"
        case durationMs = "duration_ms"
    }
}

struct LogsSummary: Codable {
    let ok: Bool
    let exitCode: Int
    let durationMs: Int
    let argv: [String]
    
    enum CodingKeys: String, CodingKey {
        case ok, argv
        case exitCode = "exit_code"
        case durationMs = "duration_ms"
    }
}

struct AnomalyGuardResult: Codable {
    let enabled: Bool
    let triggered: Bool
    let probeOk: Bool?
    let probeExitCode: Int?
    let metrics: AnomalyMetrics?
    let signals: AnomalySignals?
    
    enum CodingKeys: String, CodingKey {
        case enabled, triggered, metrics, signals
        case probeOk = "probe_ok"
        case probeExitCode = "probe_exit_code"
    }
}

struct AnomalyMetrics: Codable {
    let linesAnalyzed: Int
    let eventsAnalyzed: Int
    let cycleRepeatedTurns: Int
    let pingPongTurns: Int
    
    enum CodingKeys: String, CodingKey {
        case linesAnalyzed = "lines_analyzed"
        case eventsAnalyzed = "events_analyzed"
        case cycleRepeatedTurns = "cycle_repeated_turns"
        case pingPongTurns = "ping_pong_turns"
    }
}

struct AnomalySignals: Codable {
    let repeatTrigger: Bool
    let similarRepeatTrigger: Bool
    let pingPongTrigger: Bool
    let cycleTrigger: Bool
    let stagnationTrigger: Bool
    let autoDispatchTrigger: Bool
    
    enum CodingKeys: String, CodingKey {
        case repeatTrigger = "repeat_trigger"
        case similarRepeatTrigger = "similar_repeat_trigger"
        case pingPongTrigger = "ping_pong_trigger"
        case cycleTrigger = "cycle_trigger"
        case stagnationTrigger = "stagnation_trigger"
        case autoDispatchTrigger = "auto_dispatch_trigger"
    }
}

// MARK: - 完整配置模型（与 Python 端同步）

struct AppConfig: Codable {
    var monitor = MonitorConfig()
    var openclaw = OpenClawConfig()
    var repair = RepairConfig()
    var anomalyGuard = AnomalyGuardConfig()
    var notify = NotifyConfig()
    var ai = AiConfig()

    enum CodingKeys: String, CodingKey {
        case monitor
        case openclaw
        case repair
        case anomalyGuard = "anomaly_guard"
        case notify
        case ai
    }
}

struct MonitorConfig: Codable {
    var intervalSeconds: Int = 60
    var probeTimeoutSeconds: Int = 30
    var repairCooldownSeconds: Int = 300
    var stateDir: String = "~/.fix-my-claw"
    var logFile: String = "~/.fix-my-claw/fix-my-claw.log"
    var logLevel: String = "INFO"

    enum CodingKeys: String, CodingKey {
        case intervalSeconds = "interval_seconds"
        case probeTimeoutSeconds = "probe_timeout_seconds"
        case repairCooldownSeconds = "repair_cooldown_seconds"
        case stateDir = "state_dir"
        case logFile = "log_file"
        case logLevel = "log_level"
    }
}

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

struct RepairConfig: Codable {
    var enabled: Bool = true
    var sessionControlEnabled: Bool = true
    var sessionActiveMinutes: Int = 30
    var sessionAgents: [String] = ["macs-orchestrator", "macs-builder", "macs-architect", "macs-research"]
    var softPauseEnabled: Bool = true
    var pauseMessage: String = ""
    var pauseWaitSeconds: Int = 20
    var terminateMessage: String = "/stop"
    var newMessage: String = "/new"
    var sessionCommandTimeoutSeconds: Int = 120
    var sessionStageWaitSeconds: Int = 1
    var officialSteps: [[String]] = [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]]
    var stepTimeoutSeconds: Int = 600
    var postStepWaitSeconds: Int = 2

    enum CodingKeys: String, CodingKey {
        case enabled
        case sessionControlEnabled = "session_control_enabled"
        case sessionActiveMinutes = "session_active_minutes"
        case sessionAgents = "session_agents"
        case softPauseEnabled = "soft_pause_enabled"
        case pauseMessage = "pause_message"
        case pauseWaitSeconds = "pause_wait_seconds"
        case terminateMessage = "terminate_message"
        case newMessage = "new_message"
        case sessionCommandTimeoutSeconds = "session_command_timeout_seconds"
        case sessionStageWaitSeconds = "session_stage_wait_seconds"
        case officialSteps = "official_steps"
        case stepTimeoutSeconds = "step_timeout_seconds"
        case postStepWaitSeconds = "post_step_wait_seconds"
    }
}

struct AnomalyGuardConfig: Codable {
    var enabled: Bool = true
    var windowLines: Int = 200
    var probeTimeoutSeconds: Int = 30
    var keywordsStop: [String] = []
    var keywordsRepeat: [String] = []
    var maxRepeatSameSignature: Int = 3
    var minCycleRepeatedTurns: Int = 4
    var maxCyclePeriod: Int = 4
    var stagnationEnabled: Bool = true
    var stagnationMinEvents: Int = 8
    var stagnationMinRoles: Int = 2
    var stagnationMaxNovelClusterRatio: Double = 0.34
    var minSignatureChars: Int = 16
    var autoDispatchCheck: Bool = true
    var dispatchWindowLines: Int = 20
    var keywordsDispatch: [String] = []
    var minPostDispatchUnexpectedTurns: Int = 2
    var keywordsArchitectActive: [String] = []
    var similarityEnabled: Bool = true
    var similarityThreshold: Double = 0.82
    var similarityMinChars: Int = 12
    var maxSimilarRepeat: Int = 4

    enum CodingKeys: String, CodingKey {
        case enabled
        case windowLines = "window_lines"
        case probeTimeoutSeconds = "probe_timeout_seconds"
        case keywordsStop = "keywords_stop"
        case keywordsRepeat = "keywords_repeat"
        case maxRepeatSameSignature = "max_repeat_same_signature"
        case minCycleRepeatedTurns = "min_cycle_repeated_turns"
        case maxCyclePeriod = "max_cycle_period"
        case stagnationEnabled = "stagnation_enabled"
        case stagnationMinEvents = "stagnation_min_events"
        case stagnationMinRoles = "stagnation_min_roles"
        case stagnationMaxNovelClusterRatio = "stagnation_max_novel_cluster_ratio"
        case minSignatureChars = "min_signature_chars"
        case autoDispatchCheck = "auto_dispatch_check"
        case dispatchWindowLines = "dispatch_window_lines"
        case keywordsDispatch = "keywords_dispatch"
        case minPostDispatchUnexpectedTurns = "min_post_dispatch_unexpected_turns"
        case keywordsArchitectActive = "keywords_architect_active"
        case similarityEnabled = "similarity_enabled"
        case similarityThreshold = "similarity_threshold"
        case similarityMinChars = "similarity_min_chars"
        case maxSimilarRepeat = "max_similar_repeat"
    }
}

struct NotifyConfig: Codable {
    var channel: String = "discord"
    var account: String = "fix-my-claw"
    var target: String = ""
    var silent: Bool = true
    var sendTimeoutSeconds: Int = 20
    var readTimeoutSeconds: Int = 20
    var askEnableAi: Bool = true
    var askTimeoutSeconds: Int = 300
    var pollIntervalSeconds: Int = 5
    var readLimit: Int = 20
    var operatorUserIds: [String] = []

    enum CodingKeys: String, CodingKey {
        case channel
        case account
        case target
        case silent
        case sendTimeoutSeconds = "send_timeout_seconds"
        case readTimeoutSeconds = "read_timeout_seconds"
        case askEnableAi = "ask_enable_ai"
        case askTimeoutSeconds = "ask_timeout_seconds"
        case pollIntervalSeconds = "poll_interval_seconds"
        case readLimit = "read_limit"
        case operatorUserIds = "operator_user_ids"
    }
}

struct AiConfig: Codable {
    var enabled: Bool = false
    var provider: String = "codex"
    var command: String = "codex"
    var args: [String] = []
    var model: String?
    var timeoutSeconds: Int = 1800
    var maxAttemptsPerDay: Int = 2
    var cooldownSeconds: Int = 3600
    var allowCodeChanges: Bool = false
    var argsCode: [String] = []

    enum CodingKeys: String, CodingKey {
        case enabled
        case provider
        case command
        case args
        case model
        case timeoutSeconds = "timeout_seconds"
        case maxAttemptsPerDay = "max_attempts_per_day"
        case cooldownSeconds = "cooldown_seconds"
        case allowCodeChanges = "allow_code_changes"
        case argsCode = "args_code"
    }
}

struct ServiceStatus: Codable {
    let installed: Bool
    let running: Bool
}

// MARK: - GUI 内部状态

enum ServiceState: Equatable {
    case unknown          // 初始/获取中
    case checking         // 正在执行 check
    case healthy          // 健康 + 监控启用
    case unhealthy        // 异常 + 监控启用
    case pausedHealthy    // 健康 + 监控暂停
    case pausedUnhealthy  // 异常 + 监控暂停
    case noConfig         // 无配置文件
    
    var icon: String {
        switch self {
        case .unknown: return "⚪"
        case .checking: return "🟡"
        case .healthy, .pausedHealthy: return "🟢"
        case .unhealthy, .pausedUnhealthy: return "🔴"
        case .noConfig: return "⚙️"
        }
    }
    
    var description: String {
        switch self {
        case .unknown: return "未知"
        case .checking: return "检查中..."
        case .healthy: return "健康"
        case .unhealthy: return "异常"
        case .pausedHealthy: return "健康 (已暂停)"
        case .pausedUnhealthy: return "异常 (已暂停)"
        case .noConfig: return "未配置"
        }
    }
    
    var isMonitoringEnabled: Bool {
        switch self {
        case .healthy, .unhealthy: return true
        default: return false
        }
    }
    
    var isHealthy: Bool {
        switch self {
        case .healthy, .pausedHealthy: return true
        default: return false
        }
    }
}

struct CheckHistoryItem: Identifiable {
    let id = UUID()
    let timestamp: Date
    let result: CheckPayload
}

// MARK: - 修复历史记录

struct RepairRecord: Identifiable {
    let id = UUID()
    let timestamp: Date
    let success: Bool
    let stage: String  // "pause" | "official" | "ai_config" | "ai_code" | "failed"
    let source: String // "auto" | "manual"
    let attemptDir: String
    
    var stageDescription: String {
        switch stage {
        case "pause": return "PAUSE 恢复"
        case "official": return "官方修复"
        case "ai_config": return "AI 配置修复"
        case "ai_code": return "AI 代码修复"
        case "failed": return "修复失败"
        default: return "未知"
        }
    }
    
    var icon: String {
        return success ? "✅" : "❌"
    }
}

// MARK: - CLI 错误

enum CLIError: LocalizedError {
    case commandNotFound(path: String)
    case commandFailed(exitCode: Int32, stderr: String)
    case decodingFailed(Error)
    case timeout
    
    var errorDescription: String? {
        switch self {
        case .commandNotFound(let path):
            return "找不到 fix-my-claw CLI: \(path)"
        case .commandFailed(let code, let err):
            return "命令失败 (退出码 \(code)): \(err)"
        case .decodingFailed(let err):
            return "解析失败: \(err.localizedDescription)"
        case .timeout:
            return "执行超时"
        }
    }
}
