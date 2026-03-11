import AppKit
import Combine
import SwiftUI
import UserNotifications

/// MenuBarManager 是 GUI 运行时的协调 façade
/// 职责：
/// - 协调 Store、Services、MenuBuilder 之间的交互
/// - 管理轮询调度（Timer）
/// - 处理审批弹窗流程
/// - 投递本地通知
/// 
/// 不直接持有状态（由 MenuBarStore 管理）
/// 不直接执行 CLI 调用（由 RuntimeServices 管理）
/// 不直接构建菜单（由 MenuBuilder 管理）
@MainActor
class MenuBarManager: ObservableObject {
    static let shared = MenuBarManager()
    
    // MARK: - 依赖
    
    let store = MenuBarStore.shared
    let services = RuntimeServices.shared
    private let scheduler = RuntimeScheduler()
    private let windowCoordinator = WindowCoordinator.shared
    private let approvalCoordinator = ApprovalCoordinator.shared
    private var cancellables = Set<AnyCancellable>()
    
    private let lastNotificationSequenceKeyPrefix = "fixMyClawGUI.lastNotificationSequence"
    private var startupHealthCheckPending = false
    
    // MARK: - 计算属性（转发自 Store）
    
    var state: AppState { store.state }
    var effectiveState: AppState { store.effectiveState }
    var statusTitle: String { store.statusTitle }
    var lastCheckText: String? { store.lastCheckText }
    var lastCheckResult: CheckPayload? { store.lastCheckResult }
    var serviceStatus: ServiceStatus? { store.serviceStatus }
    var currentRepairStage: String? { store.currentRepairStage }
    var pendingAiRequest: ApprovalRequest? { store.pendingAiRequest }
    var lastRepairPresentation: RepairPresentation? { store.lastRepairPresentation }
    var isLoading: Bool { store.isLoading }
    var lastError: RuntimeAlert? { store.lastError }
    
    /// 暴露 lastError 的 Publisher 供外部订阅
    var lastErrorPublisher: AnyPublisher<RuntimeAlert?, Never> {
        store.$context.map(\.lastError).eraseToAnyPublisher()
    }
    
    // MARK: - 生命周期

    private init() {
        store.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        ConfigManager.shared.$config
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.refreshStateObservation()
            }
            .store(in: &cancellables)
    }
    
    func start() {
        store.send(.appLaunched)
        startScheduling()
        Task {
            await pollRepairProgress()
            await pollApprovalRequest()
            await initialSetup()
            primeNotificationEventCursorIfNeeded()
            guard await ensureOpenClawCommandConfigured(continueStartupCheckOnSuccess: true) else {
                return
            }
            await ensureServiceReadyForGUI()
            await performInitialHealthCheck()
        }
    }

    func stop() {
        scheduler.stop()
    }

    func prepareForTermination() async {
        scheduler.stop()
        try? await services.stopService()
    }
    
    /// 启动时的首次健康检查
    private func performInitialHealthCheck() async {
        // 派发配置加载事件
        store.send(.configLoaded(exists: ConfigManager.shared.configExists))
        
        guard ConfigManager.shared.configExists else {
            return
        }

        if store.statusPayload == nil {
            _ = await syncStatus()
        }
        
        do {
            try await refreshHealthSnapshot()
        } catch {
            store.setError("首次健康检查失败: \(error.localizedDescription)", category: .backgroundStatus)
            store.failHealthCheck(error.localizedDescription)
        }
        
        await refreshStatus()
        await syncPersistedRepairResult()
    }
    
    private func initialSetup() async {
        let cliExists = FileManager.default.isExecutableFile(atPath: services.cli.binaryPath)
        if !cliExists {
            store.setError("未找到 fix-my-claw CLI", category: .cliIO)
            return
        }

        await ConfigManager.shared.prepareEditableConfig()
        
        _ = await refreshServiceStatus()
        await syncPersistedRepairResult()
        
        // 派发配置加载事件
        store.send(.configLoaded(exists: ConfigManager.shared.configExists))
    }

    @discardableResult
    private func ensureOpenClawCommandConfigured(
        presentWizardIfNeeded: Bool = true,
        continueStartupCheckOnSuccess: Bool = false
    ) async -> Bool {
        await ConfigManager.shared.prepareEditableConfig()

        if ConfigManager.shared.configExists, ConfigManager.shared.config == nil {
            let message = ConfigManager.shared.lastError ?? "加载配置失败，无法检查 OpenClaw CLI 路径。"
            store.setError(message, category: .config)
            return false
        }

        let configuredCommand = ConfigManager.shared.config?.openclaw.command ?? OpenClawConfig().command
        switch OpenClawCommandValidator.assess(configuredCommand) {
        case .valid(let normalizedPath):
            if configuredCommand != normalizedPath {
                do {
                    _ = try await ConfigManager.shared.saveOpenClawCommand(normalizedPath)
                } catch {
                    let message = "保存 OpenClaw CLI 路径失败: \(error.localizedDescription)"
                    store.setError(message, category: .config)
                    store.send(.openClawSetupRequired)
                    if continueStartupCheckOnSuccess {
                        startupHealthCheckPending = true
                    }
                    if presentWizardIfNeeded {
                        presentOpenClawSetup(guidanceMessage: message)
                    }
                    return false
                }
            }

            store.send(.configLoaded(exists: ConfigManager.shared.configExists))
            store.send(.openClawSetupSatisfied)
            store.setError(nil, category: .config)
            return true

        case .validNodeScript(_, _):
            do {
                let savedPath = try await ConfigManager.shared.saveOpenClawCommand(configuredCommand)
                store.send(.configLoaded(exists: ConfigManager.shared.configExists))
                store.send(.openClawSetupSatisfied)
                store.setError(nil, category: .config)
                if savedPath != configuredCommand {
                    print("[GUI] OpenClaw command normalized to launcher: \(savedPath)")
                }
                return true
            } catch {
                let message = "保存 OpenClaw CLI launcher 失败: \(error.localizedDescription)"
                store.setError(message, category: .config)
                store.send(.openClawSetupRequired)
                if continueStartupCheckOnSuccess {
                    startupHealthCheckPending = true
                }
                if presentWizardIfNeeded {
                    presentOpenClawSetup(guidanceMessage: message)
                }
                return false
            }

        case .requiresNodePath(_, let message):
            store.setError(message, category: .config)
            store.send(.openClawSetupRequired)
            if continueStartupCheckOnSuccess {
                startupHealthCheckPending = true
            }
            if presentWizardIfNeeded {
                presentOpenClawSetup(guidanceMessage: message)
            }
            return false

        case .requiresSetup(let message):
            store.setError(message, category: .config)
            store.send(.openClawSetupRequired)
            if continueStartupCheckOnSuccess {
                startupHealthCheckPending = true
            }
            if presentWizardIfNeeded {
                presentOpenClawSetup(guidanceMessage: message)
            }
            return false
        }
    }

    private func presentOpenClawSetup(guidanceMessage: String? = nil) {
        let fallbackMessage: String?
        switch OpenClawCommandValidator.assess(
            ConfigManager.shared.config?.openclaw.command ?? OpenClawConfig().command
        ) {
        case .requiresNodePath(_, let message), .requiresSetup(let message):
            fallbackMessage = message
        case .valid, .validNodeScript:
            fallbackMessage = nil
        }

        windowCoordinator.openOpenClawSetup(
            configManager: ConfigManager.shared,
            guidanceMessage: guidanceMessage ?? fallbackMessage
        ) { [weak self] in
            guard let self else { return }

            Task { @MainActor [weak self] in
                guard let self else { return }
                await self.resumeAfterOpenClawSetup()
            }
        }
    }

    private func resumeAfterOpenClawSetup() async {
        guard await ensureOpenClawCommandConfigured() else { return }
        primeNotificationEventCursorIfNeeded()
        await ensureServiceReadyForGUI()

        if startupHealthCheckPending && !store.hasPerformedInitialCheck {
            startupHealthCheckPending = false
            await performInitialHealthCheck()
            return
        }

        await refreshStatus()
    }
    
    // MARK: - 状态刷新
    
    private func refreshHealthSnapshot() async throws {
        let result = try await services.checkHealth(configPath: nil)
        let monitoringEnabled = store.statusPayload?.enabled ?? store.state.isMonitoringEnabled
        store.updateHealthCheck(result: result, monitoringEnabled: monitoringEnabled)
    }
    
    private func refreshPostRepairState() async {
        guard ConfigManager.shared.configExists else {
            await refreshStatus()
            return
        }
        
        do {
            try await refreshHealthSnapshot()
        } catch {
            print("[GUI] 修复结束后刷新健康状态失败: \(error.localizedDescription)")
        }
        await refreshStatus()
    }

    private func ensureServiceReadyForGUI(forceRefreshStatus: Bool = false) async {
        guard ConfigManager.shared.configExists else { return }

        do {
            let reconcileResult = try await services.reconcileService(configPath: nil)
            store.updateServiceStatus(reconcileResult.service)
            if forceRefreshStatus {
                _ = await refreshServiceStatus()
            }
        } catch {
            store.setError("后台服务启动失败: \(error.localizedDescription)", category: .cliIO)
        }
    }
    
    func refreshStatus() async {
        _ = await refreshServiceStatus()
        _ = await syncStatus()
    }
    
    private func refreshServiceStatus() async -> Bool {
        do {
            let status = try await services.getServiceStatus(configPath: nil)
            store.updateServiceStatus(status)
            return true
        } catch {
            store.updateServiceStatus(nil)
            return false
        }
    }
    
    private func syncStatus() async -> Bool {
        do {
            let status = try await services.getStatus(configPath: nil)
            store.updateStatusPayload(status)
            return true
        } catch {
            store.setError(error.localizedDescription, category: .backgroundStatus)
            return false
        }
    }
    
    // MARK: - 用户操作
    
    func toggleMonitoring() {
        guard !store.isLoading else { return }
        
        Task {
            guard await ensureOpenClawCommandConfigured() else { return }
            store.setLoading(true)
            defer { store.setLoading(false) }
            
            do {
                let status: StatusPayload
                if store.state.isMonitoringEnabled {
                    status = try await services.disableMonitoring(configPath: nil)
                } else {
                    status = try await services.enableMonitoring(configPath: nil)
                }
                store.updateStatusPayload(status)
                _ = await refreshServiceStatus()
            } catch {
                store.setError(error.localizedDescription, category: .cliIO)
            }
        }
    }
    
    func performCheck() {
        guard !store.isLoading else { return }
        
        Task {
            guard await ensureOpenClawCommandConfigured() else { return }
            store.setLoading(true)
            store.beginHealthCheck()
            
            do {
                try await refreshHealthSnapshot()
                await refreshStatus()
            } catch {
                store.setError(error.localizedDescription, category: .cliIO)
                store.failHealthCheck(error.localizedDescription)
                await refreshStatus()
            }
            store.setLoading(false)
        }
    }
    
    func performRepair(force: Bool = false) {
        guard !store.isLoading else { return }
        
        Task {
            guard await ensureOpenClawCommandConfigured() else { return }
            store.setLoading(true)
            store.updateRepairStage("starting")
            
            var serviceWasRunning = false
            do {
                serviceWasRunning = store.serviceStatus?.running == true
                if serviceWasRunning {
                    try await services.stopService()
                }
                
                let result = try await services.repair(force: force, configPath: nil)
                
                if serviceWasRunning {
                    try? await services.startService(configPath: nil)
                }
                
                await refreshPostRepairState()
                await handleRepairResult(result, source: .manual)
                await syncNotificationEvents()
            } catch {
                store.setError("修复失败: \(error.localizedDescription)", category: .cliIO)
                if serviceWasRunning {
                    try? await services.startService(configPath: nil)
                }
                await refreshStatus()
                await postLocalNotification(title: "❌ 修复失败", body: error.localizedDescription)
            }
            
            store.clearRepairState()
        }
    }
    
    func createDefaultConfig() {
        guard !store.isLoading else { return }
        
        Task {
            store.setLoading(true)
            defer { store.setLoading(false) }
            
            do {
                try await services.createDefaultConfig(at: nil, force: true)
                _ = try? await services.disableMonitoring(configPath: nil)
                await ConfigManager.shared.prepareEditableConfig()
                refreshStateObservation()
                guard await ensureOpenClawCommandConfigured() else {
                    return
                }
                await ensureServiceReadyForGUI()
                await refreshStatus()
                await syncPersistedRepairResult()
                store.setError(nil)
            } catch {
                store.setError("创建默认配置失败: \(error.localizedDescription)", category: .config)
            }
        }
    }
    
    func openOpenClawSetup() {
        presentOpenClawSetup()
    }
    
    func openLogFile() {
        Task {
            do {
                let logPath = try await services.getLogPath(configPath: nil)
                let url = URL(fileURLWithPath: (logPath as NSString).expandingTildeInPath)
                NSWorkspace.shared.open(url)
            } catch {
                store.setError(error.localizedDescription, category: .cliIO)
            }
        }
    }
    
    func openAttemptsFolder() {
        Task {
            do {
                let attemptsPath = try await services.getAttemptsPath(configPath: nil)
                let url = URL(fileURLWithPath: (attemptsPath as NSString).expandingTildeInPath)
                NSWorkspace.shared.open(url)
            } catch {
                store.setError(error.localizedDescription, category: .cliIO)
            }
        }
    }
    
    func quit() {
        NSApplication.shared.terminate(nil)
    }
    
    // MARK: - 调度与状态目录观察

    private func startScheduling() {
        scheduler.start(
            statusAction: { [weak self] in
                guard let self else { return true }
                return await self.runScheduledStatusRefresh()
            },
            healthAction: { [weak self] in
                guard let self else { return true }
                return await self.runScheduledHealthRefresh()
            },
            stateDirectoryURL: currentStateDirectoryURL(),
            fileChangeHandler: { [weak self] in
                self?.handleStateDirectoryChange()
            }
        )
    }

    private func refreshStateObservation() {
        scheduler.refreshStateObservation(
            directoryURL: currentStateDirectoryURL(),
            onChange: { [weak self] in
                self?.handleStateDirectoryChange()
            }
        )
    }

    private func currentStateDirectoryURL() -> URL? {
        let url = services.currentStateDirectoryURL()
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    private func handleStateDirectoryChange() {
        Task {
            await pollRepairProgress()
            await pollApprovalRequest()
            if store.currentRepairStage == nil {
                await syncPersistedRepairResult()
            }
            await syncNotificationEvents()
        }
    }

    private func runScheduledStatusRefresh() async -> Bool {
        if ConfigManager.shared.configExists,
           await ensureOpenClawCommandConfigured(presentWizardIfNeeded: false) {
            await ensureServiceReadyForGUI(forceRefreshStatus: true)
        }
        let serviceRefreshSucceeded = await refreshServiceStatus()
        let statusRefreshSucceeded = await syncStatus()
        await pollRepairProgress()
        await pollApprovalRequest()
        if store.currentRepairStage == nil {
            await syncPersistedRepairResult()
        }
        await syncNotificationEvents()
        return serviceRefreshSucceeded && statusRefreshSucceeded
    }

    private func runScheduledHealthRefresh() async -> Bool {
        guard ConfigManager.shared.configExists else { return true }
        if case .setupRequired = store.state { return true }
        return await periodicHealthCheck()
    }
    
    private func periodicHealthCheck() async -> Bool {
        guard !store.isLoading else { return true }
        guard ConfigManager.shared.configExists else { return true }
        guard await ensureOpenClawCommandConfigured(presentWizardIfNeeded: false) else { return true }
        
        do {
            try await refreshHealthSnapshot()
            await refreshStatus()
            return true
        } catch {
            store.failHealthCheck(error.localizedDescription)
            print("[GUI] 周期性健康检查失败: \(error.localizedDescription)")
            return false
        }
    }
    
    // MARK: - 修复结果处理
    
    private func handleRepairResult(_ result: RepairResult, source: RepairResultSource) async {
        let presentation = result.makePresentation(source: source)
        let isNew = presentation.fingerprint != store.lastHandledRepairFingerprint
        
        if isNew || store.lastRepairPresentation == nil {
            store.updateRepairPresentation(presentation, fingerprint: presentation.fingerprint)
        }
    }
    
    private func syncPersistedRepairResult() async {
        guard let persisted = services.getRepairResult() else { return }
        await handleRepairResult(persisted.result, source: .background)
    }
    
    // MARK: - 修复进度轮询
    
    func pollRepairProgress() async {
        guard let progress = services.getRepairProgress() else {
            // 进度文件被删除表示整个修复流程已结束
            if store.currentRepairStage != nil {
                guard !store.isLoading else { return }
                store.updateRepairStage(nil)
                await refreshPostRepairState()
                await syncPersistedRepairResult()
            } else if store.lastRepairPresentation == nil {
                await syncPersistedRepairResult()
            }
            return
        }
        
        // 更新当前修复阶段显示
        store.updateRepairStage(progress.stage)
    }
    
    // MARK: - AI 审批协调
    
    func pollApprovalRequest() async {
        // 如果已有弹窗显示中，跳过
        guard store.activeApprovalDialogRequestID == nil else { return }
        
        // 检查是否有新的审批请求
        guard let request = services.getPendingRequest() else {
            // 没有活跃请求时，清除 pendingAiRequest
            if store.pendingAiRequest != nil {
                store.updatePendingAiRequest(nil)
            }
            return
        }
        
        // 检查是否已被用户关闭过
        guard !store.isApprovalRequestDismissed(request.requestId) else { return }
        
        // 检查是否已有决策
        if let decision = services.getDecision(), decision.requestId == request.requestId {
            store.dismissApprovalRequest(request.requestId)
            store.updatePendingAiRequest(nil)
            return
        }
        
        // 如果当前 pendingAiRequest 与新请求不同，更新它
        if store.pendingAiRequest?.requestId != request.requestId {
            store.updatePendingAiRequest(request)
        }
        
        // 2秒后自动弹窗
        Task {
            try? await Task.sleep(nanoseconds: UInt64(2 * 1_000_000_000))
            
            // 再次检查条件
            guard store.activeApprovalDialogRequestID == nil else { return }
            guard let pending = store.pendingAiRequest, pending.requestId == request.requestId else { return }
            
            // 检查是否已有决策
            if let decision = services.getDecision(), decision.requestId == request.requestId {
                store.updatePendingAiRequest(nil)
                store.dismissApprovalRequest(request.requestId)
                return
            }
            
            // 复查 active request 文件
            guard let currentActive = services.getPendingRequest(),
                  currentActive.requestId == request.requestId else {
                store.updatePendingAiRequest(nil)
                store.dismissApprovalRequest(request.requestId)
                return
            }
            
            presentApprovalDialog(for: request)
        }
    }
    
    func showPendingApprovalDialog() {
        guard store.activeApprovalDialogRequestID == nil else { return }
        guard let request = store.pendingAiRequest else { return }
        
        // 检查是否已有决策
        if let decision = services.getDecision(), decision.requestId == request.requestId {
            store.updatePendingAiRequest(nil)
            store.dismissApprovalRequest(request.requestId)
            return
        }
        
        // 复查 active request 文件
        guard let currentActive = services.getPendingRequest(),
              currentActive.requestId == request.requestId else {
            store.updatePendingAiRequest(nil)
            store.dismissApprovalRequest(request.requestId)
            return
        }
        
        presentApprovalDialog(for: request)
    }
    
    private func presentApprovalDialog(for request: ApprovalRequest) {
        store.setActiveApprovalDialog(requestID: request.requestId)

        approvalCoordinator.presentApproval(prompt: request.prompt) { [weak self] decision in
            guard let self else { return }

            self.store.dismissApprovalRequest(request.requestId)

            let claimed = self.services.submitDecision(request: request, decision: decision)
            if !claimed, let existing = self.services.getDecision(), existing.requestId == request.requestId {
                print("[GUI] approval request \(request.requestId) already resolved by \(existing.source ?? "another source")")
            }

            self.store.setActiveApprovalDialog(requestID: nil)
            self.store.updatePendingAiRequest(nil)
        }
    }

    // MARK: - 通知

    private func notificationCursorKey() -> String {
        "\(lastNotificationSequenceKeyPrefix).\(services.currentStateDirectoryURL().path)"
    }

    private func primeNotificationEventCursorIfNeeded() {
        let defaults = UserDefaults.standard
        let key = notificationCursorKey()
        guard defaults.object(forKey: key) == nil else { return }
        let maxSequence = services.getNotificationEvents().last?.sequence ?? 0
        defaults.set(maxSequence, forKey: key)
    }

    private func syncNotificationEvents() async {
        let defaults = UserDefaults.standard
        let key = notificationCursorKey()
        guard defaults.object(forKey: key) != nil else {
            primeNotificationEventCursorIfNeeded()
            return
        }

        let events = services.getNotificationEvents()
        guard let latestSequence = events.last?.sequence else { return }

        let lastSeenSequence = defaults.integer(forKey: key)
        for event in events where event.sequence > lastSeenSequence {
            await deliverNotificationEvent(event)
        }
        defaults.set(latestSequence, forKey: key)
    }

    private func deliverNotificationEvent(_ event: PersistedNotificationEvent) async {
        guard let title = event.localTitle?.trimmingCharacters(in: .whitespacesAndNewlines),
              let body = event.localBody?.trimmingCharacters(in: .whitespacesAndNewlines),
              !title.isEmpty,
              !body.isEmpty else {
            return
        }
        await postLocalNotification(title: title, body: body)
    }
    
    nonisolated static func canPostLocalNotifications(
        bundlePath: String = Bundle.main.bundlePath,
        bundleIdentifier: String? = Bundle.main.bundleIdentifier
    ) -> Bool {
        guard !bundlePath.isEmpty, bundlePath.hasSuffix(".app") else {
            return false
        }
        guard let bundleIdentifier, !bundleIdentifier.isEmpty else {
            return false
        }
        return true
    }
    
    private func postLocalNotification(title: String, body: String) async {
        guard Self.canPostLocalNotifications() else {
            print("[GUI] skip local notification outside app bundle: \(title)")
            return
        }
        
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }
    
    // MARK: - 菜单构建
    
    func buildMenu() -> NSMenu {
        let state = MenuBuilder.MenuState(
            effectiveState: store.effectiveState,
            statusTitle: store.statusTitle,
            lastCheckText: store.lastCheckText,
            serviceStatus: store.serviceStatus,
            currentRepairStage: store.currentRepairStage,
            lastRepairPresentation: store.lastRepairPresentation,
            hasPendingAiRequest: store.pendingAiRequest != nil,
            lastCheckResult: store.lastCheckResult,
            isLoading: store.isLoading
        )
        
        guard let target = NSApplication.shared.delegate as? MenuBarController else {
            return NSMenu()
        }
        
        return MenuBuilder.buildMenu(state: state, target: target)
    }
}
