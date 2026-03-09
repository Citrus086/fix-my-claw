import AppKit
import Combine
import SwiftUI

@MainActor
final class MenuBarController: NSObject, NSApplicationDelegate {
    private let manager = MenuBarManager.shared
    private var statusItem: NSStatusItem?
    private var settingsWindow: NSWindow?
    private var cancellables = Set<AnyCancellable>()
    private var lastPresentedError: String?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupStatusItem()
        bindManager()
        manager.start()
    }

    private func setupStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem = item
        updateStatusItem()
    }

    private func bindManager() {
        manager.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.updateStatusItem()
            }
            .store(in: &cancellables)

        manager.$lastError
            .compactMap { $0 }
            .removeDuplicates()
            .receive(on: RunLoop.main)
            .sink { [weak self] message in
                self?.presentErrorIfNeeded(message)
            }
            .store(in: &cancellables)
    }

    private func updateStatusItem() {
        guard let statusItem else { return }
        // 使用 effectiveState 让菜单栏图标真正反映修复中/审批中状态
        statusItem.button?.title = manager.effectiveState.icon
        statusItem.button?.toolTip = manager.statusTitle
        statusItem.menu = manager.buildMenu()
    }

    private func presentErrorIfNeeded(_ message: String) {
        guard lastPresentedError != message else { return }
        lastPresentedError = message
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "fix-my-claw GUI 错误"
        alert.informativeText = message
        alert.addButton(withTitle: "确定")
        alert.runModal()
    }

    @objc func toggleMonitoring() {
        manager.toggleMonitoring()
    }

    @objc func performCheck() {
        manager.performCheck()
    }

    @objc func performRepair() {
        manager.performRepair()
    }

    @objc func showPendingApproval() {
        manager.showPendingApprovalDialog()
    }

    @objc func installService() {
        manager.installService()
    }

    @objc func createDefaultConfig() {
        manager.createDefaultConfig()
    }

    @objc func uninstallService() {
        let alert = NSAlert()
        alert.messageText = "确认卸载"
        alert.informativeText = "确定要卸载后台监控服务吗？"
        alert.alertStyle = .warning
        alert.addButton(withTitle: "卸载")
        alert.addButton(withTitle: "取消")

        if alert.runModal() == .alertFirstButtonReturn {
            manager.uninstallService()
        }
    }

    @objc func startService() {
        manager.startService()
    }

    @objc func stopService() {
        manager.stopService()
    }

    @objc func openLog() {
        manager.openLogFile()
    }

    @objc func openAttempts() {
        manager.openAttemptsFolder()
    }

    @objc func showLastResult() {
        guard let result = manager.lastCheckResult else { return }
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = result.healthy ? "OpenClaw 当前健康" : "OpenClaw 当前异常"
        var lines = [
            "reason: \(result.reason ?? "-")",
            "health probe exit: \(result.health.exitCode)",
            "status probe exit: \(result.status.exitCode)",
        ]
        if let anomaly = result.anomalyGuard, anomaly.triggered {
            lines.append("anomaly_guard: triggered")
        }
        alert.informativeText = lines.joined(separator: "\n")
        alert.addButton(withTitle: "确定")
        alert.runModal()
    }

    @objc func openSettings() {
        if let settingsWindow {
            settingsWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let hostingController = NSHostingController(
            rootView: SettingsView().environmentObject(ConfigManager.shared)
        )
        let window = NSWindow(contentViewController: hostingController)
        window.title = "fix-my-claw 设置"
        window.setContentSize(NSSize(width: 500, height: 400))
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.isReleasedWhenClosed = false
        window.center()
        settingsWindow = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showAbout() {
        NSApp.activate(ignoringOtherApps: true)
        NSApplication.shared.orderFrontStandardAboutPanel([
            NSApplication.AboutPanelOptionKey.applicationName: "fix-my-claw GUI",
            NSApplication.AboutPanelOptionKey.applicationVersion: "0.1.0",
        ])
    }

    @objc func quitWithServiceStop() {
        manager.stopServiceThenQuit()
    }
}
