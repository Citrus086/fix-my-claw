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

struct AgentRolesConfig: Codable {
    var orchestrator: [String] = ["orchestrator", "macs-orchestrator"]
    var builder: [String] = ["builder", "macs-builder"]
    var architect: [String] = ["architect", "macs-architect"]
    var research: [String] = ["research", "macs-research"]

    enum CodingKeys: String, CodingKey {
        case orchestrator, builder, architect, research
    }
}

struct MonitorConfig: Codable {
    var intervalSeconds: Int = 60
    var probeTimeoutSeconds: Int = 30
    var repairCooldownSeconds: Int = 300
    var stateDir: String = "~/.fix-my-claw"
    var logFile: String = "~/.fix-my-claw/fix-my-claw.log"
    var logLevel: String = "INFO"
    var logMaxBytes: Int = 5242880  // 5 MB
    var logBackupCount: Int = 5
    var logRetentionDays: Int = 30

    enum CodingKeys: String, CodingKey {
        case intervalSeconds = "interval_seconds"
        case probeTimeoutSeconds = "probe_timeout_seconds"
        case repairCooldownSeconds = "repair_cooldown_seconds"
        case stateDir = "state_dir"
        case logFile = "log_file"
        case logLevel = "log_level"
        case logMaxBytes = "log_max_bytes"
        case logBackupCount = "log_backup_count"
        case logRetentionDays = "log_retention_days"
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
    // 与 Python DEFAULT_AGENT_ROLES 保持一致，包含短名称和长名称
    var sessionAgents: [String] = [
        "orchestrator", "macs-orchestrator",
        "builder", "macs-builder",
        "architect", "macs-architect",
        "research", "macs-research"
    ]
    var softPauseEnabled: Bool = true
    // 与 Python DEFAULT_PAUSE_MESSAGE 保持一致
    var pauseMessage: String = "[CONTROL]\nAction: PAUSE\nReason: fix-my-claw detected an unhealthy state and is preserving the current task before stronger recovery.\nExpectation: ACK once, then stay paused until further instruction.\n"
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
    // 与 Python AnomalyGuardConfig 默认值保持一致
    var keywordsStop: [String] = [
        "stop", "halt", "abort", "cancel", "terminate",
        "停止", "立刻停止", "强制停止", "终止", "停止指令"
    ]
    var keywordsRepeat: [String] = [
        "repeat", "repeating", "loop", "ping-pong",
        "重复", "死循环", "不断", "一直在重复", "重复汇报"
    ]
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
    var keywordsDispatch: [String] = [
        "dispatch", "handoff", "delegate", "assign",
        "开始实施", "开始执行", "派给", "转交"
    ]
    var minPostDispatchUnexpectedTurns: Int = 2
    var keywordsArchitectActive: [String] = [
        "architect", "still output", "continue output",
        "还在输出", "继续发内容", "连续输出"
    ]
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
    var target: String = "channel:YOUR_DISCORD_CHANNEL_ID"
    var silent: Bool = true
    var sendTimeoutSeconds: Int = 20
    var readTimeoutSeconds: Int = 20
    var askEnableAi: Bool = true
    var askTimeoutSeconds: Int = 300
    var pollIntervalSeconds: Int = 5
    var readLimit: Int = 20
    var level: String = "all"  // "all" | "important" | "critical"
    var operatorUserIds: [String] = []
    var manualRepairKeywords: [String] = ["手动修复", "manual repair", "修复", "repair"]
    var aiApproveKeywords: [String] = ["yes", "是"]
    var aiRejectKeywords: [String] = ["no", "否"]

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
        case level
        case operatorUserIds = "operator_user_ids"
        case manualRepairKeywords = "manual_repair_keywords"
        case aiApproveKeywords = "ai_approve_keywords"
        case aiRejectKeywords = "ai_reject_keywords"
    }
}

struct AiConfig: Codable {
    var enabled: Bool = false
    var provider: String = "codex"
    var command: String = "codex"
    // 与 Python AiConfig 默认值保持一致
    var args: [String] = [
        "exec",
        "-s", "workspace-write",
        "-c", "approval_policy=\"never\"",
        "--skip-git-repo-check",
        "-C", "$workspace_dir",
        "--add-dir", "$openclaw_state_dir",
        "--add-dir", "$monitor_state_dir",
    ]
    var model: String?
    var timeoutSeconds: Int = 1800
    var maxAttemptsPerDay: Int = 2
    var cooldownSeconds: Int = 3600
    var allowCodeChanges: Bool = false
    // 与 Python AiConfig 默认值保持一致
    var argsCode: [String] = [
        "exec",
        "-s", "danger-full-access",
        "-c", "approval_policy=\"never\"",
        "--skip-git-repo-check",
        "-C", "$workspace_dir",
    ]

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
    case unknown          // 初始状态，尚未进行过健康检查
    case checking         // 正在执行 check
    case healthy          // 已验证健康 + 监控启用
    case unhealthy        // 已验证异常 + 监控启用
    case pausedHealthy    // 已验证健康 + 监控暂停
    case pausedUnhealthy  // 已验证异常 + 监控暂停
    case repairing        // 修复中
    case awaitingApproval // 等待 AI 审批
    case noConfig         // 无配置文件

    var icon: String {
        switch self {
        case .unknown: return "⚪"
        case .checking: return "🟡"
        case .healthy, .pausedHealthy: return "🟢"
        case .unhealthy, .pausedUnhealthy: return "🔴"
        case .repairing: return "🔧"
        case .awaitingApproval: return "❓"
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
        case .repairing: return "修复中"
        case .awaitingApproval: return "等待审批"
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

// MARK: - Stage 映射

/// 将内部 repair stage 代号映射为用户可读文案
func localizedStageName(_ stage: String) -> String {
    switch stage {
    case "starting":
        return "启动中"
    case "pause":
        return "发送 PAUSE"
    case "pause_check":
        return "PAUSE 后复检"
    case "terminate":
        return "停止会话"
    case "new":
        return "重建会话"
    case "official":
        return "官方修复"
    case "backup":
        return "备份现场"
    case "ai_decision":
        return "等待 AI 审批"
    case "ai_config":
        return "AI 配置修复"
    case "ai_code":
        return "AI 代码修复"
    case "final":
        return "最终复检"
    case "completed":
        return "已完成"
    case "failed":
        return "失败"
    default:
        return stage
    }
}

enum RepairResultSource {
    case manual
    case background

    var label: String {
        switch self {
        case .manual:
            return "手动修复"
        case .background:
            return "后台修复"
        }
    }
}

struct RepairPresentation {
    let source: RepairResultSource
    let fingerprint: String
    let title: String
    let body: String
    let menuSummary: String
    let menuDetail: String?
    let stageLabel: String?
    let attemptLabel: String?
}

extension RepairResult {
    var identityKey: String {
        if let attemptDir = details.attemptDir, !attemptDir.isEmpty {
            return "attempt:\(attemptDir)"
        }
        if details.alreadyHealthy == true {
            return "already_healthy"
        }
        if details.repairDisabled == true {
            return "repair_disabled"
        }
        if details.cooldown == true {
            return "cooldown:\(details.cooldownRemainingSeconds ?? -1)"
        }
        if let decision = details.aiDecision?.decision, !decision.isEmpty {
            return "ai_decision:\(decision)"
        }
        if let aiStage = details.aiStage, !aiStage.isEmpty {
            return "ai_stage:\(aiStage):fixed:\(fixed)"
        }
        if let backupBeforeAiError = details.backupBeforeAiError, !backupBeforeAiError.isEmpty {
            return "backup_error:\(backupBeforeAiError)"
        }
        return "attempted:\(attempted):fixed:\(fixed):used_ai:\(usedAi)"
    }

    func makePresentation(source: RepairResultSource) -> RepairPresentation {
        let finalNotice = cleanedRepairMessage(details.notifyFinal?.messageText)
        let notificationStatus = repairNotificationDeliveryLabel(details.notifyFinal)
        let attemptLabel = repairAttemptLabel(details.attemptDir)
        let stageLabel = derivedRepairStageLabel(details: details, attempted: attempted, fixed: fixed)

        let summary: String
        let body: String

        if details.alreadyHealthy == true {
            summary = "无需修复"
            body = finalNotice ?? "系统已处于健康状态，本轮未执行修复。"
        } else if details.repairDisabled == true {
            summary = "repair 已禁用"
            body = finalNotice ?? "repair.enabled=false，本轮未执行修复。"
        } else if details.cooldown == true {
            let remaining = details.cooldownRemainingSeconds.map { "\($0) 秒" } ?? "未知"
            summary = "冷却中"
            body = "修复冷却期尚未结束，剩余 \(remaining)。"
        } else if let backupBeforeAiError = details.backupBeforeAiError, !backupBeforeAiError.isEmpty {
            summary = "备份失败"
            body = finalNotice ?? "已收到 AI 修复批准，但备份失败：\(backupBeforeAiError)"
        } else if fixed, details.aiStage == "code" {
            summary = "AI 代码修复成功"
            body = finalNotice ?? "AI 代码修复后系统恢复健康。"
        } else if fixed, details.aiStage == "config" {
            summary = "AI 配置修复成功"
            body = finalNotice ?? "AI 配置修复后系统恢复健康。"
        } else if fixed, details.officialBreakReason == "healthy" {
            summary = "官方修复成功"
            body = finalNotice ?? "官方修复后系统恢复健康。"
        } else if fixed, details.pauseWaitSeconds != nil {
            summary = "PAUSE 复检已恢复"
            body = finalNotice ?? "发送 PAUSE 并复检后系统恢复健康。"
        } else if let aiDecision = details.aiDecision?.decision {
            switch aiDecision {
            case "rate_limited":
                summary = "AI 修复已限流"
                body = finalNotice ?? "已达到 AI 修复次数或冷却限制，本轮不进入 AI 修复。"
            case "no":
                summary = "已拒绝 AI 修复"
                body = finalNotice ?? "收到明确 no，本轮不进入 AI 修复。"
            case "timeout":
                summary = "AI 审批超时"
                body = finalNotice ?? "等待 AI 审批超时，本轮不进入 AI 修复。"
            case "invalid_limit":
                let invalidCount = details.aiDecision?.invalidReplies.map(String.init) ?? "多次"
                summary = "AI 审批无效"
                body = finalNotice ?? "连续 \(invalidCount) 次收到无效回复，本轮不进入 AI 修复。"
            case "send_failed":
                let error = details.aiDecision?.error ?? "未知错误"
                summary = "审批消息发送失败"
                body = finalNotice ?? "无法发送 AI 审批消息：\(error)"
            case "skip":
                summary = "已跳过 AI 审批"
                body = finalNotice ?? "notify.ask_enable_ai=false，本轮跳过 AI 修复审批。"
            default:
                summary = "未进入 AI 修复"
                body = finalNotice ?? "AI 审批阶段结束，decision=\(aiDecision)。"
            }
        } else if attempted, !fixed, details.officialBreakReason != nil, details.aiStage == nil {
            summary = "AI 修复已禁用"
            body = finalNotice ?? "官方修复后仍异常，且 ai.enabled=false，本轮停止。"
        } else if attempted, !fixed {
            summary = "修复结束但仍异常"
            body = finalNotice ?? "本轮修复已结束，但系统仍未恢复健康。"
        } else {
            summary = fixed ? "修复完成" : "修复结束"
            body = finalNotice ?? "已收到修复结果。"
        }

        let detail = joinRepairDetailParts([
            stageLabel.map { "结束阶段：\($0)" },
            notificationStatus,
        ])

        let icon = fixed ? "✅" : repairSummaryIcon(summary)
        return RepairPresentation(
            source: source,
            fingerprint: identityKey,
            title: "\(icon) \(source.label)：\(summary)",
            body: body,
            menuSummary: summary,
            menuDetail: detail,
            stageLabel: stageLabel,
            attemptLabel: attemptLabel,
        )
    }
}

private func cleanedRepairMessage(_ message: String?) -> String? {
    guard let message else { return nil }
    let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    if trimmed.hasPrefix("fix-my-claw:") {
        let stripped = trimmed.dropFirst("fix-my-claw:".count)
        return String(stripped).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return trimmed
}

private func repairNotificationDeliveryLabel(_ payload: RepairNotificationPayload?) -> String? {
    guard let payload, let sent = payload.sent else { return nil }
    return sent ? "后端通知已发送" : "后端通知发送失败"
}

private func repairAttemptLabel(_ attemptDir: String?) -> String? {
    guard let attemptDir, !attemptDir.isEmpty else { return nil }
    return URL(fileURLWithPath: attemptDir).lastPathComponent
}

private func derivedRepairStageLabel(details: RepairDetails, attempted: Bool, fixed: Bool) -> String? {
    if details.alreadyHealthy == true || details.repairDisabled == true || details.cooldown == true {
        return nil
    }
    if details.backupBeforeAiError != nil {
        return localizedStageName("backup")
    }
    if let aiStage = details.aiStage, !aiStage.isEmpty {
        return localizedStageName("ai_\(aiStage)")
    }
    if details.aiDecision != nil {
        return localizedStageName("ai_decision")
    }
    if details.officialBreakReason != nil {
        return localizedStageName("official")
    }
    if fixed, details.pauseWaitSeconds != nil {
        return localizedStageName("pause_check")
    }
    if attempted {
        return localizedStageName("final")
    }
    return nil
}

private func joinRepairDetailParts(_ parts: [String?]) -> String? {
    let values = parts.compactMap { value -> String? in
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
    guard !values.isEmpty else { return nil }
    return values.joined(separator: " | ")
}

private func repairSummaryIcon(_ summary: String) -> String {
    if summary.contains("成功") || summary.contains("恢复") || summary.contains("无需") {
        return "✅"
    }
    if summary.contains("禁用") || summary.contains("冷却") || summary.contains("跳过") || summary.contains("拒绝") {
        return "⏸️"
    }
    return "⚠️"
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
