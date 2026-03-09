import SwiftUI

@MainActor
struct IdSettingsView: View, ConfigBindable {
    @EnvironmentObject var configManager: ConfigManager

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionHeader(title: "会话 Agent IDs", description: "有权接收会话控制命令的 Agent 列表，每行一个。")

            LineListEditor(
                title: "session_agents",
                description: "会被写入 `repair.session_agents`.",
                text: lineListBinding(
                    default: [],
                    get: { $0.repair.sessionAgents },
                    set: { $0.repair.sessionAgents = $1 }
                )
            )

            SectionHeader(title: "Agent 角色别名", description: "异常检测时用于识别各类角色的别名。")

            LineListEditor(
                title: "orchestrator",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.orchestrator },
                    set: { $0.agentRoles.orchestrator = $1 }
                )
            )

            LineListEditor(
                title: "builder",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.builder },
                    set: { $0.agentRoles.builder = $1 }
                )
            )

            LineListEditor(
                title: "architect",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.architect },
                    set: { $0.agentRoles.architect = $1 }
                )
            )

            LineListEditor(
                title: "research",
                description: "每行一个别名。",
                text: lineListBinding(
                    default: [],
                    get: { $0.agentRoles.research },
                    set: { $0.agentRoles.research = $1 }
                )
            )

            SectionHeader(title: "通知接收人", description: "频道场景下，哪些用户被当作操作员。")

            LineListEditor(
                title: "operator_user_ids",
                description: "每行一个 Discord user id。",
                text: lineListBinding(
                    default: [],
                    get: { $0.notify.operatorUserIds },
                    set: { $0.notify.operatorUserIds = $1 }
                )
            )
        }
    }
}
