import Foundation
import SwiftUI

@MainActor
struct RepairSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    private let defaults = RepairConfig()

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "自动修复基础", description: "日常建议只调整这里的开关和时间参数。下面两段会直接改变修复动作本身。")

            Toggle(
                "启用自动修复",
                isOn: binding(
                    default: true,
                    get: { $0.repair.enabled },
                    set: { $0.repair.enabled = $1 }
                )
            )

            Toggle(
                "启用会话控制",
                isOn: binding(
                    default: true,
                    get: { $0.repair.sessionControlEnabled },
                    set: { $0.repair.sessionControlEnabled = $1 }
                )
            )

            Toggle(
                "启用软暂停",
                isOn: binding(
                    default: true,
                    get: { $0.repair.softPauseEnabled },
                    set: { $0.repair.softPauseEnabled = $1 }
                )
            )

            IntField(
                title: "会话活跃窗口",
                value: binding(
                    default: 30,
                    get: { $0.repair.sessionActiveMinutes },
                    set: { $0.repair.sessionActiveMinutes = $1 }
                ),
                unit: "分钟",
                range: 1...1_440
            )

            IntField(
                title: "PAUSE 等待",
                value: binding(
                    default: 20,
                    get: { $0.repair.pauseWaitSeconds },
                    set: { $0.repair.pauseWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...600
            )

            IntField(
                title: "命令超时",
                value: binding(
                    default: 120,
                    get: { $0.repair.sessionCommandTimeoutSeconds },
                    set: { $0.repair.sessionCommandTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...3_600
            )

            IntField(
                title: "阶段间隔",
                value: binding(
                    default: 1,
                    get: { $0.repair.sessionStageWaitSeconds },
                    set: { $0.repair.sessionStageWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...300
            )

            IntField(
                title: "步骤超时",
                value: binding(
                    default: 600,
                    get: { $0.repair.stepTimeoutSeconds },
                    set: { $0.repair.stepTimeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...7_200
            )

            IntField(
                title: "步骤后等待",
                value: binding(
                    default: 2,
                    get: { $0.repair.postStepWaitSeconds },
                    set: { $0.repair.postStepWaitSeconds = $1 }
                ),
                unit: "秒",
                range: 0...300
            )

            SectionHeader(
                title: "危险高级项：会话控制文案",
                description: "这些内容会原样发给 OpenClaw。误改后，可能导致 PAUSE/停止/新会话控制完全失效。",
                actionTitle: "恢复默认文案",
                action: restoreRepairMessageDefaults
            )

            MultilineTextField(
                title: "PAUSE 消息",
                description: "多行文本会原样写入 `repair.pause_message`。默认来源: fix-my-claw 内置 `DEFAULT_PAUSE_MESSAGE`。",
                text: binding(
                    default: defaults.pauseMessage,
                    get: { $0.repair.pauseMessage },
                    set: { $0.repair.pauseMessage = $1 }
                ),
                minHeight: 120,
                message: pauseMessageValidationMessage,
                messageTone: .warning
            )

            TextFieldRow(
                title: "停止命令",
                text: binding(
                    default: "/stop",
                    get: { $0.repair.terminateMessage },
                    set: { $0.repair.terminateMessage = $1 }
                ),
                description: "默认值: `/stop`。发送给当前 OpenClaw 会话。",
                message: simpleCommandValidationMessage(
                    for: configManager.config?.repair.terminateMessage ?? defaults.terminateMessage,
                    label: "停止命令"
                ),
                messageTone: .warning
            )

            TextFieldRow(
                title: "新会话命令",
                text: binding(
                    default: "/new",
                    get: { $0.repair.newMessage },
                    set: { $0.repair.newMessage = $1 }
                ),
                description: "默认值: `/new`。用于在强修复后拉起新会话。",
                message: simpleCommandValidationMessage(
                    for: configManager.config?.repair.newMessage ?? defaults.newMessage,
                    label: "新会话命令"
                ),
                messageTone: .warning
            )

            SectionHeader(
                title: "危险高级项：官方修复步骤",
                description: "这里会直接驱动官方修复流程。后端当前只允许 `openclaw ...` 命令，其他命令保存后会被过滤。",
                actionTitle: "恢复默认步骤",
                action: restoreOfficialStepsDefaults
            )

            CommandListEditor(
                title: "official_steps",
                description: "每行一条命令，含空格参数请用引号。默认来源: fix-my-claw 内置官方修复步骤。",
                text: commandListBinding(
                    default: defaults.officialSteps,
                    get: { $0.repair.officialSteps },
                    set: { $0.repair.officialSteps = $1 }
                ),
                message: officialStepsValidationMessage,
                messageTone: .warning
            )
        }
    }
}

private extension RepairSettingsView {
    var pauseMessageValidationMessage: String? {
        let message = configManager.config?.repair.pauseMessage ?? defaults.pauseMessage
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "PAUSE 消息为空时，会话控制阶段只能依赖 stop/new，风险较高。"
        }
        if !message.contains("[CONTROL]") || !message.localizedCaseInsensitiveContains("PAUSE") {
            return "建议保留 `[CONTROL]` 和 `PAUSE` 语义，避免 Agent 把它当成普通聊天内容。"
        }
        return nil
    }

    func simpleCommandValidationMessage(for command: String, label: String) -> String? {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "\(label) 不能为空。"
        }
        if !trimmed.hasPrefix("/") {
            return "\(label) 当前不是 slash 命令。确认目标会话真的能理解这个文本。"
        }
        return nil
    }

    var officialStepsValidationMessage: String? {
        let steps = configManager.config?.repair.officialSteps ?? defaults.officialSteps
        if steps.isEmpty {
            return "步骤列表为空时，官方修复阶段会被直接跳过。"
        }

        let invalid = steps.compactMap { step -> String? in
            guard let command = step.first else { return nil }
            let base = URL(fileURLWithPath: command).lastPathComponent
            return base == "openclaw" ? nil : command
        }

        if let firstInvalid = invalid.first {
            return "检测到非白名单命令 `\(firstInvalid)`。后端保存时会把这类步骤直接过滤掉。"
        }

        return nil
    }

    func restoreRepairMessageDefaults() {
        guard var config = configManager.config else { return }
        config.repair.pauseMessage = defaults.pauseMessage
        config.repair.terminateMessage = defaults.terminateMessage
        config.repair.newMessage = defaults.newMessage
        configManager.config = config
    }

    func restoreOfficialStepsDefaults() {
        guard var config = configManager.config else { return }
        config.repair.officialSteps = defaults.officialSteps
        configManager.config = config
    }
}
