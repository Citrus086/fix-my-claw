import Foundation
import Combine

/// MenuBarStore 是 GUI 运行时的单一状态源
/// 使用 AppState 作为权威状态，取代之前分散的多个状态字段
@MainActor
final class MenuBarStore: ObservableObject {
    static let shared = MenuBarStore()
    
    // MARK: - 权威状态
    
    /// 当前权威状态（唯一状态源）
    /// 只能通过 send(_:) 方法修改，禁止直接赋值
    @Published private(set) var state: AppState = .uninitialized
    
    /// 状态上下文（不参与状态转换的辅助信息）
    @Published var context = AppStateContext()
    
    // MARK: - 兼容性计算属性（逐步废弃）
    
    /// 旧版 ServiceState 兼容性属性
    @available(*, deprecated, message: "使用 state 替代")
    var legacyState: ServiceState {
        mapToLegacyState(state)
    }
    
    /// 计算有效的显示状态（现在直接返回权威状态）
    var effectiveState: AppState { state }
    
    /// 状态栏标题（用于菜单和 tooltip）
    var statusTitle: String { state.statusTitle }
    
    /// 最后一次检查的相对时间描述
    var lastCheckText: String? { context.lastCheckText }
    
    // MARK: - 便捷访问器
    
    var lastCheckResult: CheckPayload? {
        get { context.lastCheckResult }
        set { context.lastCheckResult = newValue }
    }
    
    var serviceStatus: ServiceStatus? {
        get { context.serviceStatus }
        set { context.serviceStatus = newValue }
    }
    
    var statusPayload: StatusPayload? {
        get { context.statusPayload }
        set { context.statusPayload = newValue }
    }
    
    var lastRepairPresentation: RepairPresentation? {
        get { context.lastRepairPresentation }
        set { context.lastRepairPresentation = newValue }
    }
    
    var isLoading: Bool {
        get { context.isLoading }
        set { context.isLoading = newValue }
    }
    
    var lastError: RuntimeAlert? {
        get { context.lastError }
        set { context.lastError = newValue }
    }
    
    var hasPerformedInitialCheck: Bool {
        get { context.hasPerformedInitialCheck }
        set { context.hasPerformedInitialCheck = newValue }
    }
    
    var dismissedApprovalRequestIDs: Set<String> {
        get { context.dismissedApprovalRequestIDs }
        set { context.dismissedApprovalRequestIDs = newValue }
    }
    
    var activeApprovalDialogRequestID: String? {
        get { context.activeApprovalDialogRequestID }
        set { context.activeApprovalDialogRequestID = newValue }
    }
    
    /// 已处理的修复结果 fingerprint
    var lastHandledRepairFingerprint: String? {
        get { context.lastHandledRepairFingerprint }
        set { context.lastHandledRepairFingerprint = newValue }
    }
    
    /// 最后一次检查时间
    var lastCheckTime: Date? {
        get { context.lastCheckTime }
        set { context.lastCheckTime = newValue }
    }
    
    /// 待处理的 AI 审批请求（从状态中解包）
    var pendingAiRequest: ApprovalRequest? {
        if case .awaitingApproval(let request) = state {
            return request
        }
        return nil
    }
    
    /// 当前修复阶段（从状态中解包）
    var currentRepairStage: String? {
        if case .repairing(let stage) = state {
            return stageDisplayName(stage)
        }
        return nil
    }
    
    // MARK: - 状态转换
    
    /// 发送事件到状态机，执行状态转换
    func send(_ event: AppStateEvent) {
        let newState = AppStateReducer.reduce(state: state, event: event)
        if newState != state {
            state = newState
        }
    }
    
    // MARK: - 上下文更新方法
    
    /// 更新健康检查结果
    func updateHealthCheck(result: CheckPayload, monitoringEnabled: Bool) {
        context.lastCheckResult = result
        context.lastCheckTime = Date()
        context.hasPerformedInitialCheck = true
        send(.healthCheckCompleted(result: result, monitoringEnabled: monitoringEnabled))
    }
    
    /// 更新服务状态
    func updateServiceStatus(_ status: ServiceStatus?) {
        context.serviceStatus = status
    }
    
    /// 更新状态 payload
    func updateStatusPayload(_ payload: StatusPayload?) {
        context.statusPayload = payload
        guard let payload else { return }
        send(.configLoaded(exists: payload.configExists))
        if payload.configExists {
            send(.monitoringToggled(enabled: payload.enabled))
        }
    }
    
    /// 更新修复结果展示
    func updateRepairPresentation(_ presentation: RepairPresentation?, fingerprint: String?) {
        context.lastRepairPresentation = presentation
        context.lastHandledRepairFingerprint = fingerprint
    }
    
    /// 标记审批请求已关闭
    func dismissApprovalRequest(_ requestID: String) {
        context.dismissedApprovalRequestIDs.insert(requestID)
    }
    
    /// 设置当前活动的审批对话框请求 ID
    func setActiveApprovalDialog(requestID: String?) {
        context.activeApprovalDialogRequestID = requestID
    }
    
    /// 检查审批请求是否已被关闭
    func isApprovalRequestDismissed(_ requestID: String) -> Bool {
        context.dismissedApprovalRequestIDs.contains(requestID)
    }
    
    /// 设置加载状态
    func setLoading(_ loading: Bool) {
        context.isLoading = loading
    }
    
    /// 设置错误信息
    func setError(_ error: String?, category: RuntimeAlertCategory = .cliIO) {
        context.lastError = error.map { RuntimeAlert(category: category, message: $0) }
    }
    
    func beginHealthCheck() {
        send(.healthCheckStarted)
    }
    
    func failHealthCheck(_ error: String) {
        send(.healthCheckFailed(error: error))
    }
    
    /// 更新修复阶段（通过状态事件）
    func updateRepairStage(_ stage: String?) {
        if let stage = stage {
            send(.repairProgressed(stage: stage))
        } else {
            send(.repairCompleted)
        }
    }
    
    /// 更新待处理的 AI 审批请求（通过状态事件）
    func updatePendingAiRequest(_ request: ApprovalRequest?) {
        if let request = request {
            send(.approvalRequested(request: request))
        } else {
            send(.approvalExpired)
        }
    }
    
    /// 清除修复状态
    func clearRepairState() {
        // 状态转换通过事件处理
        if case .repairing = state {
            send(.repairCompleted)
        }
        context.isLoading = false
    }
    
    // MARK: - 私有辅助方法
    
    private func mapToLegacyState(_ appState: AppState) -> ServiceState {
        switch appState {
        case .uninitialized: return .unknown
        case .unknown: return .unknown
        case .checking: return .checking
        case .healthy: return .healthy
        case .unhealthy: return .unhealthy
        case .pausedHealthy: return .pausedHealthy
        case .pausedUnhealthy: return .pausedUnhealthy
        case .repairing: return .repairing
        case .awaitingApproval: return .awaitingApproval
        case .noConfig: return .noConfig
        }
    }
    
    private func stageDisplayName(_ stage: RepairStage) -> String {
        switch stage {
        case .starting: return "starting"
        case .pause: return "pause"
        case .pauseCheck: return "pause_check"
        case .terminate: return "terminate"
        case .newSession: return "new"
        case .official: return "official"
        case .backup: return "backup"
        case .aiDecision: return "ai_decision"
        case .aiConfig: return "ai_config"
        case .aiCode: return "ai_code"
        case .final: return "final"
        case .completed: return "completed"
        case .failed: return "failed"
        case .custom(let name): return name
        }
    }
}
