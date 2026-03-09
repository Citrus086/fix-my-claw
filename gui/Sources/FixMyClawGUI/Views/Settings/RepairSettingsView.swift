import SwiftUI

@MainActor
struct RepairSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "自动修复开关", description: "基础修复流和会话控制策略。")

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

            SectionHeader(title: "会话文案", description: "PAUSE / stop / new 向 OpenClaw 发送的控制内容。")

            MultilineTextField(
                title: "PAUSE 消息",
                description: "多行文本会原样写入 `repair.pause_message`.",
                text: binding(
                    default: "",
                    get: { $0.repair.pauseMessage },
                    set: { $0.repair.pauseMessage = $1 }
                ),
                minHeight: 120
            )

            TextFieldRow(
                title: "停止命令",
                text: binding(
                    default: "/stop",
                    get: { $0.repair.terminateMessage },
                    set: { $0.repair.terminateMessage = $1 }
                )
            )

            TextFieldRow(
                title: "新会话命令",
                text: binding(
                    default: "/new",
                    get: { $0.repair.newMessage },
                    set: { $0.repair.newMessage = $1 }
                )
            )

            SectionHeader(title: "官方修复步骤", description: "每行一条命令，按顺序执行；含空格参数请用引号。")

            CommandListEditor(
                title: "official_steps",
                description: "示例: `openclaw doctor --repair`",
                text: commandListBinding(
                    default: [["openclaw", "doctor", "--repair"], ["openclaw", "gateway", "restart"]],
                    get: { $0.repair.officialSteps },
                    set: { $0.repair.officialSteps = $1 }
                )
            )
        }
    }
}
