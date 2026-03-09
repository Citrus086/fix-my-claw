import Foundation

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
