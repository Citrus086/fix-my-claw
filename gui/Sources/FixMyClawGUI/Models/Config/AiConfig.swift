import Foundation

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
