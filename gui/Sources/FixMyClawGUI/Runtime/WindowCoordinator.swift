import AppKit
import SwiftUI

@MainActor
enum WelcomeDialogChoice {
    case installService
    case remindLater
    case manualOnly
}

/// WindowCoordinator 收敛 GUI 的窗口和通用弹窗管理。
/// Step 4 起改为统一的非阻塞 alert presenter + 设置窗口生命周期管理。
@MainActor
final class WindowCoordinator {
    static let shared = WindowCoordinator()

    private let alertPresenter = AlertPresenter.shared
    private var settingsWindow: NSWindow?
    private var settingsWindowCloseObserver: NSObjectProtocol?
    private var lastPresentedError: RuntimeAlert?

    private init() {}

    func presentErrorIfNeeded(_ alert: RuntimeAlert) {
        guard lastPresentedError != alert else { return }
        lastPresentedError = alert

        let content = errorPresentation(for: alert)
        alertPresenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: content.title,
                informativeText: content.message,
                style: content.style,
                buttonTitles: ["确定"]
            ) { _ in }
        )
    }

    func presentUninstallConfirmation(onDecision: @escaping @MainActor (Bool) -> Void) {
        alertPresenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: "确认卸载",
                informativeText: "确定要卸载后台监控服务吗？",
                style: .warning,
                buttonTitles: ["卸载", "取消"]
            ) { response in
                onDecision(response == .alertFirstButtonReturn)
            }
        )
    }

    func showLastResult(_ result: CheckPayload) {
        var lines = [
            "reason: \(result.reason ?? "-")",
            "health probe exit: \(result.health.exitCode)",
            "status probe exit: \(result.status.exitCode)",
        ]
        if let anomaly = result.anomalyGuard, anomaly.triggered {
            lines.append("anomaly_guard: triggered")
        }

        alertPresenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: result.healthy ? "OpenClaw 当前健康" : "OpenClaw 当前异常",
                informativeText: lines.joined(separator: "\n"),
                style: .informational,
                buttonTitles: ["确定"]
            ) { _ in }
        )
    }

    func openSettings(configManager: ConfigManager = .shared) {
        if let settingsWindow {
            settingsWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let hostingController = NSHostingController(
            rootView: SettingsView().environmentObject(configManager)
        )
        let window = NSWindow(contentViewController: hostingController)
        window.title = "fix-my-claw 设置"
        window.setContentSize(NSSize(width: 500, height: 400))
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.isReleasedWhenClosed = false
        window.center()

        settingsWindow = window
        settingsWindowCloseObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.settingsWindow = nil
                if let observer = self?.settingsWindowCloseObserver {
                    NotificationCenter.default.removeObserver(observer)
                    self?.settingsWindowCloseObserver = nil
                }
            }
        }

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func showAbout() {
        NSApp.activate(ignoringOtherApps: true)
        NSApplication.shared.orderFrontStandardAboutPanel([
            NSApplication.AboutPanelOptionKey.applicationName: "fix-my-claw GUI",
            NSApplication.AboutPanelOptionKey.applicationVersion: "0.1.0",
        ])
    }

    func presentWelcomeDialog(onChoice: @escaping @MainActor (WelcomeDialogChoice) -> Void) {
        alertPresenter.present(
            AlertRequest(
                windowTitle: "fix-my-claw",
                messageText: "欢迎使用 fix-my-claw",
                informativeText: """
                fix-my-claw 可以监控 OpenClaw 并在检测到异常时自动修复。

                要启用 24/7 后台监控，请安装后台服务。如果不安装，你也可以通过菜单栏手动触发检查和修复。
                """,
                style: .informational,
                buttonTitles: ["安装后台服务", "稍后安装", "仅手动控制"]
            ) { response in
                switch response {
                case .alertFirstButtonReturn:
                    onChoice(.installService)
                case .alertThirdButtonReturn:
                    onChoice(.manualOnly)
                default:
                    onChoice(.remindLater)
                }
            }
        )
    }

    private func errorPresentation(for alert: RuntimeAlert) -> (title: String, message: String, style: NSAlert.Style) {
        switch alert.category {
        case .cliIO:
            return ("fix-my-claw CLI / IO 错误", alert.message, .warning)
        case .config:
            return ("fix-my-claw 配置错误", alert.message, .warning)
        case .backgroundStatus:
            return ("fix-my-claw 后台状态提示", alert.message, .informational)
        }
    }
}
