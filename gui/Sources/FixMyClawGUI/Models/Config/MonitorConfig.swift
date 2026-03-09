import Foundation

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
