import Foundation

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
