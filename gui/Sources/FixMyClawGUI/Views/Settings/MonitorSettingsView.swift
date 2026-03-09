import SwiftUI

@MainActor
struct MonitorSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "监控轮询", description: "控制健康检查和修复冷却的基础节奏。")

            IntField(
                title: "检查间隔",
                value: binding(
                    default: 60,
                    get: { $0.monitor.intervalSeconds },
                    set: { $0.monitor.intervalSeconds = $1 }
                ),
                unit: "秒",
                range: 10...3600
            )

            IntField(
                title: "探测超时",
                value: binding(
                    default: 30,
                    get: { $0.monitor.probeTimeoutSeconds },
                    set: { $0.monitor.probeTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 5...300
            )

            IntField(
                title: "修复冷却",
                value: binding(
                    default: 300,
                    get: { $0.monitor.repairCooldownSeconds },
                    set: { $0.monitor.repairCooldownSeconds = $1 }
                ),
                unit: "秒",
                range: 0...86400
            )

            SectionHeader(title: "状态与日志路径", description: "fix-my-claw 自身状态目录和运行日志位置。")

            TextFieldRow(
                title: "状态目录",
                text: binding(
                    default: "~/.fix-my-claw",
                    get: { $0.monitor.stateDir },
                    set: { $0.monitor.stateDir = $1 }
                )
            )

            TextFieldRow(
                title: "日志文件",
                text: binding(
                    default: "~/.fix-my-claw/fix-my-claw.log",
                    get: { $0.monitor.logFile },
                    set: { $0.monitor.logFile = $1 }
                )
            )

            PickerRow(
                title: "日志级别",
                selection: binding(
                    default: "INFO",
                    get: { $0.monitor.logLevel },
                    set: { $0.monitor.logLevel = $1 }
                ),
                options: ["DEBUG", "INFO", "WARNING", "ERROR"]
            )

            SectionHeader(title: "日志轮转", description: "控制单文件大小、备份份数和保留天数。")

            IntField(
                title: "单文件上限",
                value: binding(
                    default: 5_242_880,
                    get: { $0.monitor.logMaxBytes },
                    set: { $0.monitor.logMaxBytes = $1 }
                ),
                unit: "字节",
                range: 1_024...104_857_600
            )

            IntField(
                title: "备份份数",
                value: binding(
                    default: 5,
                    get: { $0.monitor.logBackupCount },
                    set: { $0.monitor.logBackupCount = $1 }
                ),
                unit: "份",
                range: 0...100
            )

            IntField(
                title: "保留天数",
                value: binding(
                    default: 30,
                    get: { $0.monitor.logRetentionDays },
                    set: { $0.monitor.logRetentionDays = $1 }
                ),
                unit: "天",
                range: 0...3650
            )
        }
    }
}
