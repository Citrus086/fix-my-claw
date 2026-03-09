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
