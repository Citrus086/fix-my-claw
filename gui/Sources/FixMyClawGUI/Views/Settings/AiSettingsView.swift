import SwiftUI

@MainActor
struct AiSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "AI 修复基础", description: "控制 AI provider、命令和限流。")

            Toggle(
                "启用 AI 修复",
                isOn: binding(
                    default: false,
                    get: { $0.ai.enabled },
                    set: { $0.ai.enabled = $1 }
                )
            )

            Toggle(
                "允许代码修改",
                isOn: binding(
                    default: false,
                    get: { $0.ai.allowCodeChanges },
                    set: { $0.ai.allowCodeChanges = $1 }
                )
            )

            TextFieldRow(
                title: "Provider",
                text: binding(
                    default: "codex",
                    get: { $0.ai.provider },
                    set: { $0.ai.provider = $1 }
                )
            )

            TextFieldRow(
                title: "执行命令",
                text: binding(
                    default: "codex",
                    get: { $0.ai.command },
                    set: { $0.ai.command = $1 }
                )
            )

            TextFieldRow(
                title: "模型",
                text: binding(
                    default: "",
                    get: { $0.ai.model ?? "" },
                    set: { $0.ai.model = $1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $1 }
                )
            )

            IntField(
                title: "执行超时",
                value: binding(
                    default: 1_800,
                    get: { $0.ai.timeoutSeconds },
                    set: { $0.ai.timeoutSeconds = $1 }
                ),
                unit: "秒",
                range: 1...21_600
            )

            IntField(
                title: "每日最大次数",
                value: binding(
                    default: 2,
                    get: { $0.ai.maxAttemptsPerDay },
                    set: { $0.ai.maxAttemptsPerDay = $1 }
                ),
                unit: "次",
                range: 0...100
            )

            IntField(
                title: "冷却时间",
                value: binding(
                    default: 3_600,
                    get: { $0.ai.cooldownSeconds },
                    set: { $0.ai.cooldownSeconds = $1 }
                ),
                unit: "秒",
                range: 0...172_800
            )

            SectionHeader(title: "AI 命令参数", description: "每行一个参数，顺序会原样保留。")

            LineListEditor(
                title: "args",
                description: "配置型 AI 修复命令参数。",
                text: lineListBinding(
                    default: [],
                    get: { $0.ai.args },
                    set: { $0.ai.args = $1 }
                )
            )

            LineListEditor(
                title: "args_code",
                description: "代码型 AI 修复命令参数。",
                text: lineListBinding(
                    default: [],
                    get: { $0.ai.argsCode },
                    set: { $0.ai.argsCode = $1 }
                )
            )
        }
    }
}
