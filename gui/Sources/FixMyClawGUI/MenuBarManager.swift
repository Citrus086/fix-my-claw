import AppKit
import SwiftUI
import UserNotifications

@MainActor
class MenuBarManager: ObservableObject {
    static let shared = MenuBarManager()

    @Published var state: ServiceState = .unknown
    @Published var lastCheckResult: CheckPayload?
    @Published var isLoading = false
    @Published var lastError: String?
    @Published var statusPayload: StatusPayload?
    @Published var serviceStatus: ServiceStatus?

    let cli = CLIWrapper()

    private var statusTimer: Timer?
    private var lastCheckTime: Date?
    private let hasShownWelcomeKey = "fixMyClawGUI.hasShownWelcome"

    var statusTitle: String {
        "\(state.icon) \(state.description)"
    }

    var lastCheckText: String? {
        guard let time = lastCheckTime else { return nil }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return "上次检查: \(formatter.localizedString(for: time, relativeTo: Date()))"
    }

    func start() {
        Task {
            await initialSetup()
            await refreshStatus()
            startPolling()
        }
    }

    private var hasShownWelcome: Bool {
        get { UserDefaults.standard.bool(forKey: hasShownWelcomeKey) }
        set { UserDefaults.standard.set(newValue, forKey: hasShownWelcomeKey) }
    }

    private func initialSetup() async {
        let cliExists = FileManager.default.isExecutableFile(atPath: cli.binaryPath)
        if !cliExists {
            lastError = "未找到 fix-my-claw CLI"
            return
        }

        if !ConfigManager.shared.configExists {
            do {
                _ = try await cli.initializeConfig()
                _ = try? await cli.disableMonitoring()
                ConfigManager.shared.loadConfig()
            } catch {
                lastError = "初始化配置失败: \(error.localizedDescription)"
            }
        } else {
            ConfigManager.shared.loadConfig()
        }

        await refreshServiceStatus()
        if !hasShownWelcome, serviceStatus?.installed == false {
            hasShownWelcome = true
            showWelcomeDialog()
        }
    }

    func toggleMonitoring() {
        guard !isLoading else { return }

        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                if state.isMonitoringEnabled {
                    _ = try await cli.disableMonitoring()
                } else {
                    _ = try await cli.enableMonitoring()
                }
                await refreshStatus()
            } catch {
                lastError = error.localizedDescription
            }
        }
    }

    func performCheck() {
        guard !isLoading else { return }

        Task {
            isLoading = true
            let previousState = state
            state = .checking

            do {
                let result = try await cli.check()
                lastCheckResult = result
                lastCheckTime = Date()

                if previousState.isHealthy != result.healthy {
                    sendStateChangeNotification(healthy: result.healthy, reason: result.reason)
                }

                await refreshStatus()
            } catch {
                lastError = error.localizedDescription
                await refreshStatus()
            }
            isLoading = false
        }
    }

    func performRepair(force: Bool = false) {
        guard !isLoading else { return }

        Task {
            isLoading = true
            defer { isLoading = false }

            // 显示 AI 修复询问对话框
            let aiDecision = showAiRepairDialog()
            
            if aiDecision == "no" {
                // 用户选择不启用 AI 修复
                lastError = "用户取消了 AI 修复"
                await refreshStatus()
                return
            }
            
            // 用户选择启用 AI 修复，创建 GUI 标志文件
            let flagPath = await writeGuiAskFlag(decision: "yes")
            lastError = nil
            
            do {
                let serviceWasRunning = serviceStatus?.running == true
                if serviceWasRunning {
                    try await cli.stopService()
                }

                let result = try await cli.repair(force: force)

                if serviceWasRunning {
                    try? await cli.startService()
                }

                await refreshStatus()
                sendRepairNotification(result: result)
                
                // 修复完成后删除 GUI 标志文件
                try? FileManager.default.removeItem(at: flagPath)
            } catch {
                lastError = "修复失败: \(error.localizedDescription)"
                await refreshStatus()
            }
        }
    }

    func installService() {
        guard !isLoading else { return }
        Task {
            isLoading = true
            defer { isLoading = false }
            do {
                try await cli.installService(configPath: ConfigManager.shared.defaultConfigPath)
                await refreshStatus()
            } catch {
                lastError = "安装服务失败: \(error.localizedDescription)"
            }
        }
    }

    func uninstallService() {
        guard !isLoading else { return }
        Task {
            isLoading = true
            defer { isLoading = false }
            do {
                try await cli.uninstallService()
                await refreshStatus()
            } catch {
                lastError = "卸载服务失败: \(error.localizedDescription)"
            }
        }
    }

    func startService() {
        guard !isLoading else { return }
        Task {
            isLoading = true
            defer { isLoading = false }
            do {
                try await cli.startService()
                await refreshStatus()
            } catch {
                lastError = "启动服务失败: \(error.localizedDescription)"
            }
        }
    }

    func stopService() {
        guard !isLoading else { return }
        Task {
            isLoading = true
            defer { isLoading = false }
            do {
                try await cli.stopService()
                await refreshStatus()
            } catch {
                lastError = "停止服务失败: \(error.localizedDescription)"
            }
        }
    }

    func openLogFile() {
        Task {
            do {
                let logPath = try await cli.getLogPath(configPath: ConfigManager.shared.defaultConfigPath)
                let url = URL(fileURLWithPath: (logPath as NSString).expandingTildeInPath)
                NSWorkspace.shared.open(url)
            } catch {
                lastError = error.localizedDescription
            }
        }
    }

    func openAttemptsFolder() {
        Task {
            do {
                let attemptsPath = try await cli.getAttemptsPath(configPath: ConfigManager.shared.defaultConfigPath)
                let url = URL(fileURLWithPath: (attemptsPath as NSString).expandingTildeInPath)
                NSWorkspace.shared.open(url)
            } catch {
                lastError = error.localizedDescription
            }
        }
    }

    func refreshStatus() async {
        await refreshServiceStatus()
        await syncStatus()
    }

    private func refreshServiceStatus() async {
        do {
            serviceStatus = try await cli.getServiceStatus()
        } catch {
            serviceStatus = nil
        }
    }

    private func syncStatus() async {
        do {
            let status = try await cli.getStatus(configPath: ConfigManager.shared.defaultConfigPath)
            statusPayload = status

            guard status.configExists else {
                state = .noConfig
                return
            }

            let isEnabled = status.enabled
            let isHealthy = lastCheckResult?.healthy ?? true

            switch (isEnabled, isHealthy) {
            case (true, true): state = .healthy
            case (true, false): state = .unhealthy
            case (false, true): state = .pausedHealthy
            case (false, false): state = .pausedUnhealthy
            }
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func startPolling() {
        statusTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { await self?.refreshStatus() }
        }
    }

    private func showWelcomeDialog() {
        let alert = NSAlert()
        alert.messageText = "欢迎使用 fix-my-claw"
        alert.informativeText = """
        fix-my-claw 可以监控 OpenClaw 并在检测到异常时自动修复。

        要启用 24/7 后台监控，请安装后台服务。如果不安装，你也可以通过菜单栏手动触发检查和修复。
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "安装后台服务")
        alert.addButton(withTitle: "稍后安装")
        alert.addButton(withTitle: "仅手动控制")

        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            installService()
        case .alertThirdButtonReturn:
            hasShownWelcome = true
        default:
            break
        }
    }

    private func sendStateChangeNotification(healthy: Bool, reason: String?) {
        let content = UNMutableNotificationContent()
        if healthy {
            content.title = "🟢 OpenClaw 已恢复"
            content.body = "系统状态恢复正常"
        } else {
            content.title = "🔴 OpenClaw 异常"
            content.body = reason ?? "检测到异常状态"
        }
        content.sound = .default

        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    private func sendRepairNotification(result: RepairResult) {
        let content = UNMutableNotificationContent()
        if result.fixed {
            content.title = "✅ 修复完成"
            content.body = "OpenClaw 已成功修复"
        } else if result.attempted {
            content.title = "⚠️ 修复未成功"
            content.body = "已尝试修复但问题仍存在，建议人工介入"
        } else {
            content.title = "⏸️ 修复跳过"
            if let cooldown = result.details.cooldownRemainingSeconds {
                content.body = "冷却期中，剩余 \(cooldown) 秒"
            } else if result.details.alreadyHealthy == true {
                content.body = "系统已处于健康状态"
            } else {
                content.body = "不满足修复条件"
            }
        }

        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    // MARK: - AI Repair Dialog Helper Methods
    
    private func showAiRepairDialog() -> String {
        let alert = NSAlert()
        alert.messageText = "AI 修复确认"
        alert.informativeText = """
        fix-my-claw 检测到异常，是否启用 Codex 智能修复？
        
        AI 修复会使用 GPT-4o 分析问题并生成修复代码，可能会消耗 API 配额。
        
        选项：
        • 启用修复（是/Yes）- 启用 Codex 修复，备份 OpenClaw 配置后自动执行
        • 跳过修复（否/No）- 跳过 AI 修复，继续使用官方修复流程
        
        提示：你也可以通过 Discord 回复 yes/no 来确认修复。
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "启用修复（是）")
        alert.addButton(withTitle: "跳过修复（否）")
        
        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            return "yes"
        case .alertSecondButtonReturn:
            return "no"
        default:
            return "no"
        }
    }
    
    private func writeGuiAskFlag(decision: String) async -> URL {
        // 使用固定的全局标志文件路径
        let configPath = ConfigManager.shared.defaultConfigPath
        let stateDir = (configPath as NSString).deletingLastPathComponent
        let flagPath = URL(fileURLWithPath: stateDir + "/gui.ask.flag")
        
        // 写入标志文件
        let flagData: [String: Any] = ["decision": decision, "timestamp": Date().timeIntervalSince1970]
        if let data = try? JSONSerialization.data(withJSONObject: flagData, options: [.prettyPrinted]) {
            try? data.write(to: flagPath)
        }
        
        return flagPath
    }
}

// MARK: - Build Menu Extension

extension MenuBarManager {
    func buildMenu() -> NSMenu {
        let menu = NSMenu()

        let statusItem = NSMenuItem(title: statusTitle, action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        menu.addItem(statusItem)

        if let checkText = lastCheckText {
            let timeItem = NSMenuItem(title: checkText, action: nil, keyEquivalent: "")
            timeItem.isEnabled = false
            menu.addItem(timeItem)
        }

        if let serviceStatus {
            let serviceText: String
            if serviceStatus.installed {
                serviceText = serviceStatus.running ? "后台服务: 运行中" : "后台服务: 已停止"
            } else {
                serviceText = "后台服务: 未安装"
            }
            let serviceItem = NSMenuItem(title: serviceText, action: nil, keyEquivalent: "")
            serviceItem.isEnabled = false
            menu.addItem(serviceItem)
        }

        menu.addItem(.separator())

        if let serviceStatus {
            if serviceStatus.installed {
                if serviceStatus.running {
                    let stopServiceItem = NSMenuItem(
                        title: "⏹️ 停止后台服务",
                        action: #selector(MenuBarController.stopService),
                        keyEquivalent: ""
                    )
                    stopServiceItem.target = NSApplication.shared.delegate as? MenuBarController
                    menu.addItem(stopServiceItem)
                } else {
                    let startServiceItem = NSMenuItem(
                        title: "▶️ 启动后台服务",
                        action: #selector(MenuBarController.startService),
                        keyEquivalent: ""
                    )
                    startServiceItem.target = NSApplication.shared.delegate as? MenuBarController
                    menu.addItem(startServiceItem)
                }

                let uninstallServiceItem = NSMenuItem(
                    title: "🗑️ 卸载后台服务",
                    action: #selector(MenuBarController.uninstallService),
                    keyEquivalent: ""
                )
                uninstallServiceItem.target = NSApplication.shared.delegate as? MenuBarController
                menu.addItem(uninstallServiceItem)
            } else {
                let installServiceItem = NSMenuItem(
                    title: "📦 安装后台服务",
                    action: #selector(MenuBarController.installService),
                    keyEquivalent: ""
                )
                installServiceItem.target = NSApplication.shared.delegate as? MenuBarController
                menu.addItem(installServiceItem)
            }

            menu.addItem(.separator())
        }

        switch state {
        case .healthy, .unhealthy:
            let pauseItem = NSMenuItem(
                title: "⏸️ 暂停自动修复",
                action: #selector(MenuBarController.toggleMonitoring),
                keyEquivalent: "s"
            )
            pauseItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(pauseItem)

        case .pausedHealthy, .pausedUnhealthy, .noConfig:
            let startItem = NSMenuItem(
                title: "▶️ 启用自动修复",
                action: #selector(MenuBarController.toggleMonitoring),
                keyEquivalent: "s"
            )
            startItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(startItem)

        case .unknown, .checking:
            let loadingItem = NSMenuItem(title: "⏳ 获取中...", action: nil, keyEquivalent: "")
            loadingItem.isEnabled = false
            menu.addItem(loadingItem)
        }

        let checkItem = NSMenuItem(
            title: "🔍 立即检查",
            action: #selector(MenuBarController.performCheck),
            keyEquivalent: "r"
        )
        checkItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(checkItem)

        if state == .pausedUnhealthy {
            let repairItem = NSMenuItem(
                title: "🩹 立即修复",
                action: #selector(MenuBarController.performRepair),
                keyEquivalent: ""
            )
            repairItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(repairItem)
        } else if state == .unhealthy {
            let repairItem = NSMenuItem(
                title: "🩹 立即修复 (将暂停后台服务)",
                action: #selector(MenuBarController.performRepair),
                keyEquivalent: ""
            )
            repairItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(repairItem)
        }

        menu.addItem(.separator())

        let logItem = NSMenuItem(
            title: "📋 查看日志",
            action: #selector(MenuBarController.openLog),
            keyEquivalent: "l"
        )
        logItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(logItem)

        let attemptsItem = NSMenuItem(
            title: "📁 打开尝试记录",
            action: #selector(MenuBarController.openAttempts),
            keyEquivalent: ""
        )
        attemptsItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(attemptsItem)

        if lastCheckResult != nil {
            let resultItem = NSMenuItem(
                title: "📊 查看上次检查结果",
                action: #selector(MenuBarController.showLastResult),
                keyEquivalent: ""
            )
            resultItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(resultItem)
        }

        menu.addItem(.separator())

        let settingsItem = NSMenuItem(
            title: "⚙️ 设置...",
            action: #selector(MenuBarController.openSettings),
            keyEquivalent: ","
        )
        settingsItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(settingsItem)

        menu.addItem(.separator())

        let aboutItem = NSMenuItem(
            title: "关于 fix-my-claw",
            action: #selector(MenuBarController.showAbout),
            keyEquivalent: ""
        )
        aboutItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(aboutItem)

        let quitItem = NSMenuItem(
            title: "退出",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        menu.addItem(quitItem)

        return menu
    }
}