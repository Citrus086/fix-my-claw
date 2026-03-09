import Foundation

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
