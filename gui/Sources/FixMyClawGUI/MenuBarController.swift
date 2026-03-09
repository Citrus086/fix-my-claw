import AppKit
import Combine
import SwiftUI

/// MenuBarController 负责 AppKit 生命周期和 action 转发
/// 不再持有业务逻辑，只作为 View 层和 MenuBarManager 之间的桥梁
@MainActor
final class MenuBarController: NSObject, NSApplicationDelegate {
    private let manager = MenuBarManager.shared
    private let windowCoordinator = WindowCoordinator.shared
    private var statusItem: NSStatusItem?
    private var cancellables = Set<AnyCancellable>()
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        setupStatusItem()
        bindManager()
        manager.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        manager.stop()
    }
    
    private func setupStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem = item
        updateStatusItem()
    }
    
    private func bindManager() {
        // 监听 Store 的状态变化（通过 Manager 转发）
        manager.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.updateStatusItem()
            }
            .store(in: &cancellables)
        
        // 监听错误信息
        manager.lastErrorPublisher
            .compactMap { $0 }
            .removeDuplicates()
            .receive(on: RunLoop.main)
            .sink { [weak self] message in
                self?.windowCoordinator.presentErrorIfNeeded(message)
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
    
    // MARK: - Action 转发
    
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
        windowCoordinator.presentUninstallConfirmation { [weak self] confirmed in
            guard confirmed else { return }
            self?.manager.uninstallService()
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
        windowCoordinator.showLastResult(result)
    }
    
    @objc func openSettings() {
        windowCoordinator.openSettings()
    }

    @objc func openOpenClawSetup() {
        manager.openOpenClawSetup()
    }
    
    @objc func showAbout() {
        windowCoordinator.showAbout()
    }
    
    @objc func quitWithServiceStop() {
        manager.stopServiceThenQuit()
    }
}
