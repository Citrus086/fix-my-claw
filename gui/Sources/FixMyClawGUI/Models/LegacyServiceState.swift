import Foundation

// MARK: - Legacy ServiceState 兼容层
// 注意：ServiceState 是旧的状态枚举，已被 Runtime/AppStateMachine.swift 中的 AppState 取代。
// 保留此文件是为了兼容仍在使用 ServiceState 的代码，后续应逐步迁移到 AppState。

enum ServiceState: Equatable {
    case unknown          // 初始状态，尚未进行过健康检查
    case checking         // 正在执行 check
    case healthy          // 已验证健康 + 监控启用
    case unhealthy        // 已验证异常 + 监控启用
    case pausedHealthy    // 已验证健康 + 监控暂停
    case pausedUnhealthy  // 已验证异常 + 监控暂停
    case repairing        // 修复中
    case awaitingApproval // 等待 AI 审批
    case noConfig         // 无配置文件

    var icon: String {
        switch self {
        case .unknown: return "⚪"
        case .checking: return "🟡"
        case .healthy, .pausedHealthy: return "🟢"
        case .unhealthy, .pausedUnhealthy: return "🔴"
        case .repairing: return "🔧"
        case .awaitingApproval: return "❓"
        case .noConfig: return "⚙️"
        }
    }

    var description: String {
        switch self {
        case .unknown: return "未知"
        case .checking: return "检查中..."
        case .healthy: return "健康"
        case .unhealthy: return "异常"
        case .pausedHealthy: return "健康 (已暂停)"
        case .pausedUnhealthy: return "异常 (已暂停)"
        case .repairing: return "修复中"
        case .awaitingApproval: return "等待审批"
        case .noConfig: return "未配置"
        }
    }

    var isMonitoringEnabled: Bool {
        switch self {
        case .healthy, .unhealthy: return true
        default: return false
        }
    }

    var isHealthy: Bool {
        switch self {
        case .healthy, .pausedHealthy: return true
        default: return false
        }
    }
}
