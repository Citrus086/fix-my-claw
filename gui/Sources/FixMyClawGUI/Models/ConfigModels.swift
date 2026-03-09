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
    fileprivate func decodeOrDefault<T: Decodable>(
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

// MARK: - 配置模型解码扩展（提供默认值韧性）

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

extension MonitorConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        intervalSeconds = try container.decodeOrDefault(Int.self, forKey: .intervalSeconds, default: defaults.intervalSeconds)
        probeTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .probeTimeoutSeconds, default: defaults.probeTimeoutSeconds)
        repairCooldownSeconds = try container.decodeOrDefault(Int.self, forKey: .repairCooldownSeconds, default: defaults.repairCooldownSeconds)
        stateDir = try container.decodeOrDefault(String.self, forKey: .stateDir, default: defaults.stateDir)
        logFile = try container.decodeOrDefault(String.self, forKey: .logFile, default: defaults.logFile)
        logLevel = try container.decodeOrDefault(String.self, forKey: .logLevel, default: defaults.logLevel)
        logMaxBytes = try container.decodeOrDefault(Int.self, forKey: .logMaxBytes, default: defaults.logMaxBytes)
        logBackupCount = try container.decodeOrDefault(Int.self, forKey: .logBackupCount, default: defaults.logBackupCount)
        logRetentionDays = try container.decodeOrDefault(Int.self, forKey: .logRetentionDays, default: defaults.logRetentionDays)
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

extension RepairConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        enabled = try container.decodeOrDefault(Bool.self, forKey: .enabled, default: defaults.enabled)
        sessionControlEnabled = try container.decodeOrDefault(Bool.self, forKey: .sessionControlEnabled, default: defaults.sessionControlEnabled)
        sessionActiveMinutes = try container.decodeOrDefault(Int.self, forKey: .sessionActiveMinutes, default: defaults.sessionActiveMinutes)
        sessionAgents = try container.decodeOrDefault([String].self, forKey: .sessionAgents, default: defaults.sessionAgents)
        softPauseEnabled = try container.decodeOrDefault(Bool.self, forKey: .softPauseEnabled, default: defaults.softPauseEnabled)
        pauseMessage = try container.decodeOrDefault(String.self, forKey: .pauseMessage, default: defaults.pauseMessage)
        pauseWaitSeconds = try container.decodeOrDefault(Int.self, forKey: .pauseWaitSeconds, default: defaults.pauseWaitSeconds)
        terminateMessage = try container.decodeOrDefault(String.self, forKey: .terminateMessage, default: defaults.terminateMessage)
        newMessage = try container.decodeOrDefault(String.self, forKey: .newMessage, default: defaults.newMessage)
        sessionCommandTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .sessionCommandTimeoutSeconds, default: defaults.sessionCommandTimeoutSeconds)
        sessionStageWaitSeconds = try container.decodeOrDefault(Int.self, forKey: .sessionStageWaitSeconds, default: defaults.sessionStageWaitSeconds)
        officialSteps = try container.decodeOrDefault([[String]].self, forKey: .officialSteps, default: defaults.officialSteps)
        stepTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .stepTimeoutSeconds, default: defaults.stepTimeoutSeconds)
        postStepWaitSeconds = try container.decodeOrDefault(Int.self, forKey: .postStepWaitSeconds, default: defaults.postStepWaitSeconds)
    }
}

extension AnomalyGuardConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        enabled = try container.decodeOrDefault(Bool.self, forKey: .enabled, default: defaults.enabled)
        windowLines = try container.decodeOrDefault(Int.self, forKey: .windowLines, default: defaults.windowLines)
        probeTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .probeTimeoutSeconds, default: defaults.probeTimeoutSeconds)
        keywordsStop = try container.decodeOrDefault([String].self, forKey: .keywordsStop, default: defaults.keywordsStop)
        keywordsRepeat = try container.decodeOrDefault([String].self, forKey: .keywordsRepeat, default: defaults.keywordsRepeat)
        maxRepeatSameSignature = try container.decodeOrDefault(Int.self, forKey: .maxRepeatSameSignature, default: defaults.maxRepeatSameSignature)
        minCycleRepeatedTurns = try container.decodeOrDefault(Int.self, forKey: .minCycleRepeatedTurns, default: defaults.minCycleRepeatedTurns)
        maxCyclePeriod = try container.decodeOrDefault(Int.self, forKey: .maxCyclePeriod, default: defaults.maxCyclePeriod)
        stagnationEnabled = try container.decodeOrDefault(Bool.self, forKey: .stagnationEnabled, default: defaults.stagnationEnabled)
        stagnationMinEvents = try container.decodeOrDefault(Int.self, forKey: .stagnationMinEvents, default: defaults.stagnationMinEvents)
        stagnationMinRoles = try container.decodeOrDefault(Int.self, forKey: .stagnationMinRoles, default: defaults.stagnationMinRoles)
        stagnationMaxNovelClusterRatio = try container.decodeOrDefault(Double.self, forKey: .stagnationMaxNovelClusterRatio, default: defaults.stagnationMaxNovelClusterRatio)
        minSignatureChars = try container.decodeOrDefault(Int.self, forKey: .minSignatureChars, default: defaults.minSignatureChars)
        autoDispatchCheck = try container.decodeOrDefault(Bool.self, forKey: .autoDispatchCheck, default: defaults.autoDispatchCheck)
        dispatchWindowLines = try container.decodeOrDefault(Int.self, forKey: .dispatchWindowLines, default: defaults.dispatchWindowLines)
        keywordsDispatch = try container.decodeOrDefault([String].self, forKey: .keywordsDispatch, default: defaults.keywordsDispatch)
        minPostDispatchUnexpectedTurns = try container.decodeOrDefault(Int.self, forKey: .minPostDispatchUnexpectedTurns, default: defaults.minPostDispatchUnexpectedTurns)
        keywordsArchitectActive = try container.decodeOrDefault([String].self, forKey: .keywordsArchitectActive, default: defaults.keywordsArchitectActive)
        similarityEnabled = try container.decodeOrDefault(Bool.self, forKey: .similarityEnabled, default: defaults.similarityEnabled)
        similarityThreshold = try container.decodeOrDefault(Double.self, forKey: .similarityThreshold, default: defaults.similarityThreshold)
        similarityMinChars = try container.decodeOrDefault(Int.self, forKey: .similarityMinChars, default: defaults.similarityMinChars)
        maxSimilarRepeat = try container.decodeOrDefault(Int.self, forKey: .maxSimilarRepeat, default: defaults.maxSimilarRepeat)
    }
}

extension NotifyConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        channel = try container.decodeOrDefault(String.self, forKey: .channel, default: defaults.channel)
        account = try container.decodeOrDefault(String.self, forKey: .account, default: defaults.account)
        target = try container.decodeOrDefault(String.self, forKey: .target, default: defaults.target)
        silent = try container.decodeOrDefault(Bool.self, forKey: .silent, default: defaults.silent)
        sendTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .sendTimeoutSeconds, default: defaults.sendTimeoutSeconds)
        readTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .readTimeoutSeconds, default: defaults.readTimeoutSeconds)
        askEnableAi = try container.decodeOrDefault(Bool.self, forKey: .askEnableAi, default: defaults.askEnableAi)
        askTimeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .askTimeoutSeconds, default: defaults.askTimeoutSeconds)
        pollIntervalSeconds = try container.decodeOrDefault(Int.self, forKey: .pollIntervalSeconds, default: defaults.pollIntervalSeconds)
        readLimit = try container.decodeOrDefault(Int.self, forKey: .readLimit, default: defaults.readLimit)
        level = try container.decodeOrDefault(String.self, forKey: .level, default: defaults.level)
        operatorUserIds = try container.decodeOrDefault([String].self, forKey: .operatorUserIds, default: defaults.operatorUserIds)
        manualRepairKeywords = try container.decodeOrDefault([String].self, forKey: .manualRepairKeywords, default: defaults.manualRepairKeywords)
        aiApproveKeywords = try container.decodeOrDefault([String].self, forKey: .aiApproveKeywords, default: defaults.aiApproveKeywords)
        aiRejectKeywords = try container.decodeOrDefault([String].self, forKey: .aiRejectKeywords, default: defaults.aiRejectKeywords)
    }
}

extension AiConfig {
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let defaults = Self()
        enabled = try container.decodeOrDefault(Bool.self, forKey: .enabled, default: defaults.enabled)
        provider = try container.decodeOrDefault(String.self, forKey: .provider, default: defaults.provider)
        command = try container.decodeOrDefault(String.self, forKey: .command, default: defaults.command)
        args = try container.decodeOrDefault([String].self, forKey: .args, default: defaults.args)
        model = try container.decodeIfPresent(String.self, forKey: .model) ?? defaults.model
        timeoutSeconds = try container.decodeOrDefault(Int.self, forKey: .timeoutSeconds, default: defaults.timeoutSeconds)
        maxAttemptsPerDay = try container.decodeOrDefault(Int.self, forKey: .maxAttemptsPerDay, default: defaults.maxAttemptsPerDay)
        cooldownSeconds = try container.decodeOrDefault(Int.self, forKey: .cooldownSeconds, default: defaults.cooldownSeconds)
        allowCodeChanges = try container.decodeOrDefault(Bool.self, forKey: .allowCodeChanges, default: defaults.allowCodeChanges)
        argsCode = try container.decodeOrDefault([String].self, forKey: .argsCode, default: defaults.argsCode)
    }
}

struct ServiceStatus: Codable {
    let installed: Bool
    let running: Bool
}
