import AppKit

/// ApprovalCoordinator 收敛 AI 审批对话框。
/// Step 4 起改为统一的非阻塞 alert presenter。
@MainActor
final class ApprovalCoordinator {
    static let shared = ApprovalCoordinator()

    private let alertPresenter = AlertPresenter.shared

    private init() {}

    func presentApproval(prompt: String, onDecision: @escaping @MainActor (String) -> Void) {
        alertPresenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: "AI 修复确认",
                informativeText: """
                \(prompt)

                你也可以在 Discord 回复 yes/no。谁先提交有效决定，谁生效；另一侧选择会自动失效。
                """,
                style: .informational,
                buttonTitles: ["启用修复（是）", "跳过修复（否）"]
            ) { response in
                switch response {
                case .alertFirstButtonReturn:
                    onDecision("yes")
                case .alertSecondButtonReturn:
                    onDecision("no")
                default:
                    onDecision("no")
                }
            }
        )
    }
}
