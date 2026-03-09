import AppKit

/// MenuBuilder 负责根据当前状态构建菜单
/// 纯函数式：输入状态，输出 NSMenu，不持有状态，不执行副作用
@MainActor
struct MenuBuilder {
    
    // MARK: - 输入状态
    
    struct MenuState {
        let effectiveState: AppState
        let statusTitle: String
        let lastCheckText: String?
        let serviceStatus: ServiceStatus?
        let currentRepairStage: String?
        let lastRepairPresentation: RepairPresentation?
        let hasPendingAiRequest: Bool
        let lastCheckResult: CheckPayload?
        let isLoading: Bool
    }
    
    // MARK: - 构建入口
    
    static func buildMenu(state: MenuState, target: MenuBarController) -> NSMenu {
        let menu = NSMenu()
        
        // 状态标题
        addStatusSection(to: menu, state: state)
        
        // 修复进度/结果
        addRepairSection(to: menu, state: state)
        
        // AI 审批
        if state.hasPendingAiRequest {
            addAiApprovalSection(to: menu, target: target)
        }
        
        // 服务控制
        addServiceSection(to: menu, state: state, target: target)
        
        // 监控控制
        addMonitoringSection(to: menu, state: state, target: target)
        
        // 操作按钮
        addActionSection(to: menu, state: state, target: target)
        
        // 日志和历史
        addLogSection(to: menu, state: state, target: target)
        
        // 设置和关于
        addSettingsSection(to: menu, target: target)
        
        return menu
    }
    
    // MARK: - 各区块构建
    
    private static func addStatusSection(to menu: NSMenu, state: MenuState) {
        // 状态标题
        let statusItem = NSMenuItem(title: state.statusTitle, action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        menu.addItem(statusItem)
        
        // 上次检查时间
        if let checkText = state.lastCheckText {
            let timeItem = NSMenuItem(title: checkText, action: nil, keyEquivalent: "")
            timeItem.isEnabled = false
            menu.addItem(timeItem)
        }
        
        // 后台服务状态
        if let serviceStatus = state.serviceStatus {
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
        
        // 当前修复阶段
        if let stage = state.currentRepairStage {
            let stageItem = NSMenuItem(
                title: "当前阶段: \(localizedStageName(stage))",
                action: nil,
                keyEquivalent: ""
            )
            stageItem.isEnabled = false
            menu.addItem(stageItem)
        }
    }
    
    private static func addRepairSection(to menu: NSMenu, state: MenuState) {
        guard let presentation = state.lastRepairPresentation else { return }
        
        let summaryItem = NSMenuItem(
            title: "最近\(presentation.source.label): \(presentation.menuSummary)",
            action: nil,
            keyEquivalent: ""
        )
        summaryItem.isEnabled = false
        menu.addItem(summaryItem)
        
        let bodyItem = NSMenuItem(title: presentation.body, action: nil, keyEquivalent: "")
        bodyItem.isEnabled = false
        menu.addItem(bodyItem)
        
        if let menuDetail = presentation.menuDetail {
            let detailItem = NSMenuItem(title: menuDetail, action: nil, keyEquivalent: "")
            detailItem.isEnabled = false
            menu.addItem(detailItem)
        }
        
        if let attemptLabel = presentation.attemptLabel {
            let attemptItem = NSMenuItem(title: "尝试目录: \(attemptLabel)", action: nil, keyEquivalent: "")
            attemptItem.isEnabled = false
            menu.addItem(attemptItem)
        }
    }
    
    private static func addAiApprovalSection(to menu: NSMenu, target: MenuBarController) {
        let aiApprovalItem = NSMenuItem(
            title: "🟡 等待 AI 修复确认...",
            action: #selector(MenuBarController.showPendingApproval),
            keyEquivalent: ""
        )
        aiApprovalItem.target = target
        menu.addItem(aiApprovalItem)
        menu.addItem(.separator())
    }
    
    private static func addServiceSection(to menu: NSMenu, state: MenuState, target: MenuBarController) {
        guard let serviceStatus = state.serviceStatus else { return }
        
        if serviceStatus.installed {
            if serviceStatus.running {
                let stopServiceItem = NSMenuItem(
                    title: "⏹️ 停止后台服务",
                    action: #selector(MenuBarController.stopService),
                    keyEquivalent: ""
                )
                stopServiceItem.target = target
                menu.addItem(stopServiceItem)
            } else {
                let startServiceItem = NSMenuItem(
                    title: "▶️ 启动后台服务",
                    action: #selector(MenuBarController.startService),
                    keyEquivalent: ""
                )
                startServiceItem.target = target
                menu.addItem(startServiceItem)
            }
            
            let uninstallServiceItem = NSMenuItem(
                title: "🗑️ 卸载后台服务",
                action: #selector(MenuBarController.uninstallService),
                keyEquivalent: ""
            )
            uninstallServiceItem.target = target
            menu.addItem(uninstallServiceItem)
        } else {
            let installServiceItem = NSMenuItem(
                title: "📦 安装后台服务",
                action: #selector(MenuBarController.installService),
                keyEquivalent: ""
            )
            installServiceItem.target = target
            menu.addItem(installServiceItem)
        }
        
        menu.addItem(.separator())
    }
    
    private static func addMonitoringSection(to menu: NSMenu, state: MenuState, target: MenuBarController) {
        switch state.effectiveState {
        case .healthy, .unhealthy(_):
            let pauseItem = NSMenuItem(
                title: "⏸️ 暂停自动修复",
                action: #selector(MenuBarController.toggleMonitoring),
                keyEquivalent: "s"
            )
            pauseItem.target = target
            menu.addItem(pauseItem)
            
        case .pausedHealthy, .pausedUnhealthy(_):
            let startItem = NSMenuItem(
                title: "▶️ 启用自动修复",
                action: #selector(MenuBarController.toggleMonitoring),
                keyEquivalent: "s"
            )
            startItem.target = target
            menu.addItem(startItem)
            
        case .noConfig:
            let createConfigItem = NSMenuItem(
                title: "⚙️ 创建默认配置",
                action: #selector(MenuBarController.createDefaultConfig),
                keyEquivalent: ""
            )
            createConfigItem.target = target
            menu.addItem(createConfigItem)
            
        case .uninitialized, .unknown, .checking:
            let loadingItem = NSMenuItem(title: "⏳ 获取中...", action: nil, keyEquivalent: "")
            loadingItem.isEnabled = false
            menu.addItem(loadingItem)
            
        case .repairing(_):
            let repairingItem = NSMenuItem(title: "🔧 修复中...", action: nil, keyEquivalent: "")
            repairingItem.isEnabled = false
            menu.addItem(repairingItem)
            
        case .awaitingApproval(_):
            let approvalItem = NSMenuItem(title: "❓ 等待 AI 审批...", action: nil, keyEquivalent: "")
            approvalItem.isEnabled = false
            menu.addItem(approvalItem)
        }
    }
    
    private static func addActionSection(to menu: NSMenu, state: MenuState, target: MenuBarController) {
        // 立即检查
        let checkItem = NSMenuItem(
            title: "🔍 立即检查",
            action: #selector(MenuBarController.performCheck),
            keyEquivalent: "r"
        )
        checkItem.target = target
        menu.addItem(checkItem)
        
        // 立即修复（仅在异常状态显示）
        if case .pausedUnhealthy(_) = state.effectiveState {
            let repairItem = NSMenuItem(
                title: "🩹 立即修复",
                action: #selector(MenuBarController.performRepair),
                keyEquivalent: ""
            )
            repairItem.target = target
            menu.addItem(repairItem)
        } else if case .unhealthy(_) = state.effectiveState {
            let repairItem = NSMenuItem(
                title: "🩹 立即修复 (将暂停后台服务)",
                action: #selector(MenuBarController.performRepair),
                keyEquivalent: ""
            )
            repairItem.target = target
            menu.addItem(repairItem)
        }
    }
    
    private static func addLogSection(to menu: NSMenu, state: MenuState, target: MenuBarController) {
        menu.addItem(.separator())
        
        let logItem = NSMenuItem(
            title: "📋 查看日志",
            action: #selector(MenuBarController.openLog),
            keyEquivalent: "l"
        )
        logItem.target = target
        menu.addItem(logItem)
        
        let attemptsItem = NSMenuItem(
            title: "📁 打开尝试记录",
            action: #selector(MenuBarController.openAttempts),
            keyEquivalent: ""
        )
        attemptsItem.target = target
        menu.addItem(attemptsItem)
        
        // 查看上次检查结果
        if state.lastCheckResult != nil {
            let resultItem = NSMenuItem(
                title: "📊 查看上次检查结果",
                action: #selector(MenuBarController.showLastResult),
                keyEquivalent: ""
            )
            resultItem.target = target
            menu.addItem(resultItem)
        }
    }
    
    private static func addSettingsSection(to menu: NSMenu, target: MenuBarController) {
        menu.addItem(.separator())
        
        let settingsItem = NSMenuItem(
            title: "⚙️ 设置...",
            action: #selector(MenuBarController.openSettings),
            keyEquivalent: ","
        )
        settingsItem.target = target
        menu.addItem(settingsItem)
        
        menu.addItem(.separator())
        
        let aboutItem = NSMenuItem(
            title: "关于 fix-my-claw",
            action: #selector(MenuBarController.showAbout),
            keyEquivalent: ""
        )
        aboutItem.target = target
        menu.addItem(aboutItem)
        
        let quitItem = NSMenuItem(
            title: "退出",
            action: #selector(MenuBarController.quitWithServiceStop),
            keyEquivalent: "q"
        )
        quitItem.target = target
        menu.addItem(quitItem)
    }
}
