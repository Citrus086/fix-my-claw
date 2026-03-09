import Foundation

// MARK: - 权威状态定义

/// GUI 运行时权威状态
/// 取代之前分散的 `state + effectiveState + currentRepairStage + pendingAiRequest`
enum AppState: Equatable {
    /// 初始状态，尚未完成初始化
    case uninitialized
    
    /// 未知状态，尚未进行过健康检查
    case unknown
    
    /// 已验证健康 + 监控启用
    case healthy
    
    /// 已验证异常 + 监控启用
    case unhealthy(reason: String?)
    
    /// 已验证健康 + 监控暂停
    case pausedHealthy
    
    /// 已验证异常 + 监控暂停
    case pausedUnhealthy(reason: String?)
    
    /// 修复中
    case repairing(stage: RepairStage)
    
    /// 等待 AI 审批
    case awaitingApproval(request: ApprovalRequest)
    
    /// 无配置文件
    case noConfig

    /// 需要先配置 OpenClaw CLI 绝对路径
    case setupRequired
    
    /// 检查中
    case checking
}

/// 修复阶段
enum RepairStage: Equatable {
    case starting
    case pause
    case pauseCheck
    case terminate
    case newSession
    case official
    case backup
    case aiDecision
    case aiConfig
    case aiCode
    case final
    case completed
    case failed
    case custom(String)
    
    var displayName: String {
        switch self {
        case .starting: return "启动中"
        case .pause: return "发送 PAUSE"
        case .pauseCheck: return "PAUSE 后复检"
        case .terminate: return "停止会话"
        case .newSession: return "重建会话"
        case .official: return "官方修复"
        case .backup: return "备份现场"
        case .aiDecision: return "等待 AI 审批"
        case .aiConfig: return "AI 配置修复"
        case .aiCode: return "AI 代码修复"
        case .final: return "最终复检"
        case .completed: return "已完成"
        case .failed: return "失败"
        case .custom(let name): return name
        }
    }
    
    init(rawValue: String) {
        switch rawValue {
        case "starting": self = .starting
        case "pause": self = .pause
        case "pause_check": self = .pauseCheck
        case "terminate": self = .terminate
        case "new": self = .newSession
        case "official": self = .official
        case "backup": self = .backup
        case "ai_decision": self = .aiDecision
        case "ai_config": self = .aiConfig
        case "ai_code": self = .aiCode
        case "final": self = .final
        case "completed": self = .completed
        case "failed": self = .failed
        default: self = .custom(rawValue)
        }
    }
}

// MARK: - 状态属性

extension AppState {
    /// 状态图标
    var icon: String {
        switch self {
        case .uninitialized: return "⚪"
        case .unknown: return "⚪"
        case .checking: return "🟡"
        case .healthy, .pausedHealthy: return "🟢"
        case .unhealthy, .pausedUnhealthy: return "🔴"
        case .repairing: return "🔧"
        case .awaitingApproval: return "❓"
        case .noConfig: return "⚙️"
        case .setupRequired: return "⚙️"
        }
    }
    
    /// 状态描述
    var description: String {
        switch self {
        case .uninitialized: return "初始化中"
        case .unknown: return "未知"
        case .checking: return "检查中..."
        case .healthy: return "健康"
        case .unhealthy(let reason): return reason != nil ? "异常: \(reason!)" : "异常"
        case .pausedHealthy: return "健康 (已暂停)"
        case .pausedUnhealthy(let reason): return reason != nil ? "异常 (已暂停): \(reason!)" : "异常 (已暂停)"
        case .repairing(let stage): return "修复中...(\(stage.displayName))"
        case .awaitingApproval: return "等待审批"
        case .noConfig: return "未配置"
        case .setupRequired: return "等待配置 OpenClaw CLI"
        }
    }
    
    /// 是否启用了监控
    var isMonitoringEnabled: Bool {
        switch self {
        case .healthy, .unhealthy: return true
        default: return false
        }
    }
    
    /// 是否健康
    var isHealthy: Bool {
        switch self {
        case .healthy, .pausedHealthy: return true
        default: return false
        }
    }
    
    /// 是否处于修复中
    var isRepairing: Bool {
        if case .repairing = self { return true }
        return false
    }
    
    /// 是否等待审批
    var isAwaitingApproval: Bool {
        if case .awaitingApproval = self { return true }
        return false
    }
    
    /// 是否可以执行修复
    var canRepair: Bool {
        switch self {
        case .unhealthy, .pausedUnhealthy: return true
        default: return false
        }
    }
    
    /// 状态栏标题（用于菜单和 tooltip）
    var statusTitle: String {
        "\(icon) \(description)"
    }
}

// MARK: - 状态转换事件

enum AppStateEvent {
    case appLaunched
    case configLoaded(exists: Bool)
    case healthCheckStarted
    case healthCheckCompleted(result: CheckPayload, monitoringEnabled: Bool)
    case healthCheckFailed(error: String)
    case monitoringToggled(enabled: Bool)
    case openClawSetupRequired
    case openClawSetupSatisfied
    case repairStarted
    case repairProgressed(stage: String)
    case repairCompleted
    case repairFailed
    case approvalRequested(request: ApprovalRequest)
    case approvalResponded
    case approvalExpired
}

enum RuntimeAlertCategory: Equatable {
    case cliIO
    case config
    case backgroundStatus
}

struct RuntimeAlert: Equatable {
    let category: RuntimeAlertCategory
    let message: String
}

// MARK: - 状态机 Reducer

/// AppStateReducer 负责处理状态转换逻辑
/// 纯函数：输入当前状态和事件，输出新状态
struct AppStateReducer {
    static func reduce(state: AppState, event: AppStateEvent) -> AppState {
        switch event {
        case .appLaunched:
            return .uninitialized
            
        case .configLoaded(let exists):
            guard exists else { return .noConfig }
            switch state {
            case .uninitialized, .noConfig:
                return .unknown
            case .setupRequired:
                return .setupRequired
            default:
                return state
            }
            
        case .healthCheckStarted:
            // 只有在非修复/审批状态下才能进入 checking
            if case .repairing = state { return state }
            if case .awaitingApproval = state { return state }
            if case .noConfig = state { return state }
            if case .setupRequired = state { return state }
            return .checking
            
        case .healthCheckCompleted(let result, let monitoringEnabled):
            if case .repairing = state { return state }
            if case .awaitingApproval = state { return state }
            return deriveHealthState(from: result, monitoringEnabled: monitoringEnabled)
            
        case .healthCheckFailed:
            if case .repairing = state { return state }
            if case .awaitingApproval = state { return state }
            if case .healthy = state { return .unknown }
            if case .unhealthy = state { return .unknown }
            if case .pausedHealthy = state { return .unknown }
            if case .pausedUnhealthy = state { return .unknown }
            if case .checking = state { return .unknown }
            return state
            
        case .monitoringToggled(let enabled):
            return toggleMonitoring(state: state, enabled: enabled)

        case .openClawSetupRequired:
            return .setupRequired

        case .openClawSetupSatisfied:
            switch state {
            case .setupRequired, .noConfig, .uninitialized:
                return .unknown
            default:
                return state
            }
            
        case .repairStarted:
            if case .awaitingApproval = state { return state }
            return .repairing(stage: .starting)
            
        case .repairProgressed(let stageRaw):
            if case .awaitingApproval = state { return state }
            return .repairing(stage: RepairStage(rawValue: stageRaw))
            
        case .repairCompleted, .repairFailed:
            // 修复结束后回到未知状态，等待下次健康检查
            return .unknown
            
        case .approvalRequested(let request):
            // 审批请求会覆盖修复状态
            return .awaitingApproval(request: request)
            
        case .approvalResponded, .approvalExpired:
            // 审批结束后回到未知状态
            return .unknown
        }
    }
    
    // MARK: - 私有辅助方法
    
    private static func deriveHealthState(from result: CheckPayload, monitoringEnabled: Bool) -> AppState {
        let isHealthy = result.healthy
        
        switch (monitoringEnabled, isHealthy) {
        case (true, true): return .healthy
        case (true, false): return .unhealthy(reason: result.reason)
        case (false, true): return .pausedHealthy
        case (false, false): return .pausedUnhealthy(reason: result.reason)
        }
    }
    
    private static func toggleMonitoring(state: AppState, enabled: Bool) -> AppState {
        switch state {
        case .healthy:
            return enabled ? state : .pausedHealthy
        case .unhealthy(let reason):
            return enabled ? state : .pausedUnhealthy(reason: reason)
        case .pausedHealthy:
            return enabled ? .healthy : state
        case .pausedUnhealthy(let reason):
            return enabled ? .unhealthy(reason: reason) : state
        default:
            return state
        }
    }
}

// MARK: - 状态上下文

/// AppStateContext 保存与状态相关的额外上下文信息
/// 这些信息不参与状态转换，但用于 UI 展示
struct AppStateContext {
    /// 最后一次健康检查结果
    var lastCheckResult: CheckPayload?
    
    /// 最后一次检查时间
    var lastCheckTime: Date?
    
    /// 后台服务状态
    var serviceStatus: ServiceStatus?
    
    /// 状态 payload
    var statusPayload: StatusPayload?
    
    /// 最后一次修复结果展示
    var lastRepairPresentation: RepairPresentation?
    
    /// 已处理的修复结果 fingerprint
    var lastHandledRepairFingerprint: String?
    
    /// 已关闭的审批请求 ID 集合
    var dismissedApprovalRequestIDs: Set<String> = []
    
    /// 当前正在显示的审批对话框请求 ID
    var activeApprovalDialogRequestID: String?
    
    /// 是否正在执行操作（加载中）
    var isLoading: Bool = false
    
    /// 最后一次错误信息
    var lastError: RuntimeAlert?
    
    /// 是否已经执行过首次健康检查
    var hasPerformedInitialCheck: Bool = false
    
    /// 最后一次检查的相对时间描述
    var lastCheckText: String? {
        guard let time = lastCheckTime else { return nil }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return "上次检查: \(formatter.localizedString(for: time, relativeTo: Date()))"
    }
}
