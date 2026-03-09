import AppKit
import Darwin
import SwiftUI
import UserNotifications

struct ApprovalRequest: Decodable {
    let requestId: String
    let prompt: String

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case prompt
    }
}

private struct RepairProgress: Decodable {
    let stage: String
    let status: String
    let attemptDir: String?
    let timestamp: Double

    enum CodingKeys: String, CodingKey {
        case stage
        case status
        case attemptDir = "attempt_dir"
        case timestamp
    }
}

private struct ApprovalDecision: Decodable {
    let requestId: String
    let decision: String
    let source: String?

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case decision
        case source
    }
}

@MainActor
class MenuBarManager: ObservableObject {
    static let shared = MenuBarManager()

    @Published var state: ServiceState = .unknown
    @Published var lastCheckResult: CheckPayload?
    @Published var isLoading = false
    @Published var lastError: String?
    @Published var statusPayload: StatusPayload?
    @Published var serviceStatus: ServiceStatus?
    @Published var currentRepairStage: String?
    @Published var pendingAiRequest: ApprovalRequest?
    @Published var lastRepairPresentation: RepairPresentation?

    let cli = CLIWrapper()

    private var statusTimer: Timer?
    private var checkTimer: Timer?
    private var approvalTimer: Timer?
    private var repairProgressTimer: Timer?
    private var lastCheckTime: Date?
    private var activeApprovalDialogRequestID: String?
    private var dismissedApprovalRequestIDs = Set<String>()
    private let hasShownWelcomeKey = "fixMyClawGUI.hasShownWelcome"
    private let approvalActiveFileName = "ai_approval.active.json"
    private let approvalDecisionFileName = "ai_approval.decision.json"
    private let repairProgressFileName = "repair_progress.json"
    private let repairResultFileName = "repair_result.json"
    private var lastHandledRepairFingerprint: String?

    /// 是否已经执行过首次健康检查
    private var hasPerformedInitialCheck = false

    /// 计算有效的显示状态（综合考虑修复中/审批中/健康态）
    var effectiveState: ServiceState {
        // 优先显示修复中状态
        if currentRepairStage != nil {
            return .repairing
        }
        // 其次显示审批中状态
        if pendingAiRequest != nil {
            return .awaitingApproval
        }
        return state
    }

    var statusTitle: String {
        // 修复中：显示阶段信息
        if let stage = currentRepairStage {
            let localizedStage = localizedStageName(stage)
            return "🔧 修复中...(\(localizedStage))"
        }
        // 审批中
        if pendingAiRequest != nil {
            return "❓ 等待 AI 审批..."
        }
        return "\(effectiveState.icon) \(effectiveState.description)"
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
            // 启动时主动做一次真实健康检查，而不是乐观假设
            await performInitialHealthCheck()
            startPolling()
        }
    }

    /// 启动时的首次健康检查
    private func performInitialHealthCheck() async {
        // 如果没有配置文件，跳过健康检查
        guard ConfigManager.shared.configExists else {
            state = .noConfig
            return
        }

        do {
            try await refreshHealthSnapshot(notifyOnChange: false)
        } catch {
            // 健康检查失败，记录错误但不阻止启动
            lastError = "首次健康检查失败: \(error.localizedDescription)"
            // 保持 unknown 状态，不乐观假设健康
        }

        await refreshStatus()
        await syncPersistedRepairResult(notifyIfNew: false)
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
        await syncPersistedRepairResult(notifyIfNew: false)
        if !hasShownWelcome, serviceStatus?.installed == false {
            hasShownWelcome = true
            showWelcomeDialog()
        }
    }

    private func refreshHealthSnapshot(notifyOnChange: Bool) async throws {
        let previousHealthy = lastCheckResult?.healthy
        let result = try await cli.check()
        lastCheckResult = result
        lastCheckTime = Date()
        hasPerformedInitialCheck = true

        if notifyOnChange, let previousHealthy, previousHealthy != result.healthy {
            sendStateChangeNotification(healthy: result.healthy, reason: result.reason)
        }
    }

    private func refreshPostRepairState() async {
        guard ConfigManager.shared.configExists else {
            await refreshStatus()
            return
        }

        do {
            try await refreshHealthSnapshot(notifyOnChange: false)
        } catch {
            print("[GUI] 修复结束后刷新健康状态失败: \(error.localizedDescription)")
        }
        await refreshStatus()
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
            state = .checking

            do {
                try await refreshHealthSnapshot(notifyOnChange: true)
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
            // 标记为忙碌，防止重入
            isLoading = true
            currentRepairStage = "starting"

            // 发送启动通知（非阻塞）
            let content = UNMutableNotificationContent()
            content.title = "🔧 修复已启动"
            content.body = "修复正在后台运行，请稍候..."
            content.sound = .default
            let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            try? await UNUserNotificationCenter.current().add(request)

            var serviceWasRunning = false
            do {
                serviceWasRunning = serviceStatus?.running == true
                if serviceWasRunning {
                    try await cli.stopService()
                }

                let result = try await cli.repair(force: force)

                if serviceWasRunning {
                    try? await cli.startService()
                }

                await refreshPostRepairState()
                await handleRepairResult(result, source: .manual, notifyIfNew: true)
            } catch {
                lastError = "修复失败: \(error.localizedDescription)"
                // 确保服务被重新启动（如果之前是运行中的）
                if serviceWasRunning {
                    try? await cli.startService()
                }
                await refreshStatus()
                // 发送失败通知
                let errorContent = UNMutableNotificationContent()
                errorContent.title = "❌ 修复失败"
                errorContent.body = error.localizedDescription
                errorContent.sound = .default
                let errorRequest = UNNotificationRequest(identifier: UUID().uuidString, content: errorContent, trigger: nil)
                try? await UNUserNotificationCenter.current().add(errorRequest)
            }

            // 修复完成后清除状态
            isLoading = false
            currentRepairStage = nil
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

            // 关键修复：不再乐观假设健康
            // 如果没有真实的健康检查结果，保持 unknown 状态
            guard let checkResult = lastCheckResult else {
                // 尚未进行过健康检查，保持 unknown
                // 注意：即使监控启用，我们也需要先验证健康状态
                state = .unknown
                return
            }

            let isHealthy = checkResult.healthy

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
        // 快速轮询：服务状态（30秒）
        statusTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { await self?.refreshStatus() }
        }
        // 低频轮询：真实健康检查（5分钟）
        // 确保即使监控服务运行，GUI 也能定期验证健康状态
        checkTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            Task { await self?.periodicHealthCheck() }
        }
        // 高频轮询：修复进度（1秒）
        repairProgressTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { await self?.pollRepairProgress() }
        }
        // 中频轮询：AI 审批（2秒）
        approvalTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { await self?.pollApprovalRequest() }
        }
    }

    /// 周期性健康检查（低频）
    private func periodicHealthCheck() async {
        guard !isLoading else { return }
        guard ConfigManager.shared.configExists else { return }

        do {
            try await refreshHealthSnapshot(notifyOnChange: true)
            await refreshStatus()
        } catch {
            // 静默失败，不干扰用户
            print("[GUI] 周期性健康检查失败: \(error.localizedDescription)")
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

    private func handleRepairResult(_ result: RepairResult, source: RepairResultSource, notifyIfNew: Bool) async {
        let presentation = result.makePresentation(source: source)
        let isNew = presentation.fingerprint != lastHandledRepairFingerprint

        if isNew || lastRepairPresentation == nil {
            lastRepairPresentation = presentation
            lastHandledRepairFingerprint = presentation.fingerprint
        }

        if notifyIfNew, isNew {
            await deliverRepairNotification(presentation)
        }
    }

    private func deliverRepairNotification(_ presentation: RepairPresentation) async {
        let content = UNMutableNotificationContent()
        content.title = presentation.title
        content.body = presentation.body
        content.sound = .default

        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    private func loadRepairResult() -> PersistedRepairResult? {
        let url = approvalStateDirectoryURL().appendingPathComponent(repairResultFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(PersistedRepairResult.self, from: data)
    }

    private func syncPersistedRepairResult(notifyIfNew: Bool) async {
        guard let persisted = loadRepairResult() else { return }
        await handleRepairResult(persisted.result, source: .background, notifyIfNew: notifyIfNew)
    }

    // MARK: - Repair Progress Polling

    private func pollRepairProgress() async {
        guard let progress = loadRepairProgress() else {
            // 进度文件被删除表示整个修复流程已结束（后端调用了 clear_repair_progress）
            if currentRepairStage != nil {
                guard !isLoading else { return }
                currentRepairStage = nil
                await refreshPostRepairState()
                await syncPersistedRepairResult(notifyIfNew: true)
            } else if lastRepairPresentation == nil {
                await syncPersistedRepairResult(notifyIfNew: false)
            }
            return
        }

        // 更新当前修复阶段显示
        currentRepairStage = progress.stage
    }

    private func loadRepairProgress() -> RepairProgress? {
        let url = approvalStateDirectoryURL().appendingPathComponent(repairProgressFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RepairProgress.self, from: data)
    }

    // MARK: - AI Approval Coordination

    private func pollApprovalRequest() async {
        // 如果已有弹窗显示中，跳过
        guard activeApprovalDialogRequestID == nil else { return }

        // 检查是否有新的审批请求
        guard let request = loadApprovalRequest() else {
            // 没有活跃请求时，清除 pendingAiRequest
            if pendingAiRequest != nil {
                pendingAiRequest = nil
            }
            return
        }

        // 检查是否已被用户关闭过
        guard !dismissedApprovalRequestIDs.contains(request.requestId) else { return }

        // 检查是否已有决策（可能来自 Discord 或其他来源）
        if let decision = loadApprovalDecision(), decision.requestId == request.requestId {
            // 请求已被其他来源处理，记录并清理
            dismissedApprovalRequestIDs.insert(request.requestId)
            pendingAiRequest = nil
            return
        }

        // 如果当前 pendingAiRequest 与新请求不同，更新它
        if pendingAiRequest?.requestId != request.requestId {
            pendingAiRequest = request
        }

        // 2秒后自动弹窗，或者用户点击菜单项触发
        Task {
            try? await Task.sleep(nanoseconds: UInt64(2 * 1_000_000_000))
            // 再次检查：是否已有弹窗、请求是否仍有效、是否已有决策
            guard activeApprovalDialogRequestID == nil else { return }
            guard let pending = pendingAiRequest, pending.requestId == request.requestId else { return }
            // 检查是否在等待期间已被其他来源处理
            if let decision = loadApprovalDecision(), decision.requestId == request.requestId {
                pendingAiRequest = nil
                dismissedApprovalRequestIDs.insert(request.requestId)
                return
            }
            // 复查 active request 文件：后端 timeout/invalid-limit 会删除 active 文件但不写 decision
            // 如果 active 文件已不存在或 request_id 不匹配，说明请求已过期
            guard let currentActive = loadApprovalRequest(),
                  currentActive.requestId == request.requestId else {
                // 请求已过期，清理 pendingAiRequest
                pendingAiRequest = nil
                dismissedApprovalRequestIDs.insert(request.requestId)
                return
            }
            presentApprovalDialog(for: request)
        }
    }

    func showPendingApprovalDialog() {
        // 如果已有弹窗显示中，跳过
        guard activeApprovalDialogRequestID == nil else { return }
        guard let request = pendingAiRequest else { return }
        // 检查是否已有决策
        if let decision = loadApprovalDecision(), decision.requestId == request.requestId {
            pendingAiRequest = nil
            dismissedApprovalRequestIDs.insert(request.requestId)
            return
        }
        // 复查 active request 文件：后端 timeout/invalid-limit 会删除 active 文件但不写 decision
        // 如果 active 文件已不存在或 request_id 不匹配，说明请求已过期
        guard let currentActive = loadApprovalRequest(),
              currentActive.requestId == request.requestId else {
            // 请求已过期，清理 pendingAiRequest
            pendingAiRequest = nil
            dismissedApprovalRequestIDs.insert(request.requestId)
            return
        }
        presentApprovalDialog(for: request)
    }

    private func presentApprovalDialog(for request: ApprovalRequest) {
        // 先标记当前正在处理的请求，防止重复弹窗
        activeApprovalDialogRequestID = request.requestId

        NSApp.activate(ignoringOtherApps: true)
        let decision = showAiRepairDialog(prompt: request.prompt)

        // 记录已处理
        dismissedApprovalRequestIDs.insert(request.requestId)

        // 尝试写入决策
        let claimed = claimApprovalDecision(request: request, decision: decision)
        if !claimed, let existing = loadApprovalDecision(), existing.requestId == request.requestId {
            print("[GUI] approval request \(request.requestId) already resolved by \(existing.source ?? "another source")")
        }

        // 清理状态
        activeApprovalDialogRequestID = nil
        pendingAiRequest = nil
    }

    private func showAiRepairDialog(prompt: String) -> String {
        let alert = NSAlert()
        alert.messageText = "AI 修复确认"
        alert.informativeText = """
        \(prompt)

        你也可以在 Discord 回复 yes/no。谁先提交有效决定，谁生效；另一侧选择会自动失效。
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

    private func approvalStateDirectoryURL() -> URL {
        if let configured = ConfigManager.shared.config?.monitor.stateDir, !configured.isEmpty {
            return URL(fileURLWithPath: (configured as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".fix-my-claw")
    }

    private func loadApprovalRequest() -> ApprovalRequest? {
        let url = approvalStateDirectoryURL().appendingPathComponent(approvalActiveFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ApprovalRequest.self, from: data)
    }

    private func loadApprovalDecision() -> ApprovalDecision? {
        let url = approvalStateDirectoryURL().appendingPathComponent(approvalDecisionFileName)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(ApprovalDecision.self, from: data)
    }

    private func claimApprovalDecision(request: ApprovalRequest, decision: String) -> Bool {
        let stateDir = approvalStateDirectoryURL()
        let decisionURL = stateDir.appendingPathComponent(approvalDecisionFileName)
        let activeURL = stateDir.appendingPathComponent(approvalActiveFileName)
        guard let active = loadApprovalRequest(), active.requestId == request.requestId else {
            return false
        }
        let payload: [String: Any] = [
            "request_id": request.requestId,
            "decision": decision,
            "source": "gui",
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) else {
            return false
        }
        try? FileManager.default.createDirectory(
            at: stateDir,
            withIntermediateDirectories: true,
            attributes: nil
        )
        let fd = Darwin.open(decisionURL.path, O_WRONLY | O_CREAT | O_EXCL, 0o600)
        if fd == -1 {
            return false
        }
        let writeSucceeded = data.withUnsafeBytes { rawBuffer -> Bool in
            guard let baseAddress = rawBuffer.baseAddress else { return false }
            var totalWritten = 0
            while totalWritten < data.count {
                let written = Darwin.write(fd, baseAddress.advanced(by: totalWritten), data.count - totalWritten)
                if written <= 0 {
                    return false
                }
                totalWritten += written
            }
            return true
        }
        _ = Darwin.close(fd)
        if !writeSucceeded {
            try? FileManager.default.removeItem(at: decisionURL)
            return false
        }
        if let active = loadApprovalRequest(), active.requestId == request.requestId {
            try? FileManager.default.removeItem(at: activeURL)
        }
        return true
    }

    func stopServiceThenQuit() {
        guard !isLoading else { return }

        Task {
            isLoading = true
            defer { isLoading = false }

            do {
                try await cli.stopService()
            } catch {
                // 如果停止失败，静默退出
            }

            NSApplication.shared.terminate(nil)
        }
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

        if let currentRepairStage {
            let stageItem = NSMenuItem(
                title: "当前阶段: \(localizedStageName(currentRepairStage))",
                action: nil,
                keyEquivalent: ""
            )
            stageItem.isEnabled = false
            menu.addItem(stageItem)
        }

        if let lastRepairPresentation {
            let summaryItem = NSMenuItem(
                title: "最近\(lastRepairPresentation.source.label): \(lastRepairPresentation.menuSummary)",
                action: nil,
                keyEquivalent: ""
            )
            summaryItem.isEnabled = false
            menu.addItem(summaryItem)

            let bodyItem = NSMenuItem(title: lastRepairPresentation.body, action: nil, keyEquivalent: "")
            bodyItem.isEnabled = false
            menu.addItem(bodyItem)

            if let menuDetail = lastRepairPresentation.menuDetail {
                let detailItem = NSMenuItem(title: menuDetail, action: nil, keyEquivalent: "")
                detailItem.isEnabled = false
                menu.addItem(detailItem)
            }

            if let attemptLabel = lastRepairPresentation.attemptLabel {
                let attemptItem = NSMenuItem(title: "尝试目录: \(attemptLabel)", action: nil, keyEquivalent: "")
                attemptItem.isEnabled = false
                menu.addItem(attemptItem)
            }
        }

        // 如果有待处理的 AI 请求，显示确认菜单项
        if let _ = pendingAiRequest {
            let aiApprovalItem = NSMenuItem(
                title: "🟡 等待 AI 修复确认...",
                action: #selector(MenuBarController.showPendingApproval),
                keyEquivalent: ""
            )
            aiApprovalItem.target = NSApplication.shared.delegate as? MenuBarController
            menu.addItem(aiApprovalItem)
            menu.addItem(.separator())
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

        case .repairing:
            let repairingItem = NSMenuItem(title: "🔧 修复中...", action: nil, keyEquivalent: "")
            repairingItem.isEnabled = false
            menu.addItem(repairingItem)

        case .awaitingApproval:
            let approvalItem = NSMenuItem(title: "❓ 等待 AI 审批...", action: nil, keyEquivalent: "")
            approvalItem.isEnabled = false
            menu.addItem(approvalItem)
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
            action: #selector(MenuBarController.quitWithServiceStop),
            keyEquivalent: "q"
        )
        quitItem.target = NSApplication.shared.delegate as? MenuBarController
        menu.addItem(quitItem)

        return menu
    }
}
